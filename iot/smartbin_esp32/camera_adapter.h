#pragma once
#include <Arduino.h>
constexpr size_t FRAME_WIDTH=320,FRAME_HEIGHT=240,CHUNK_COUNT=8,CHUNK_SIZE=19200,FRAME_BYTES=153600;
#ifdef SIMELOOP_CAMERA_STUB
// Compile-only adapter. It NEVER produces an image or enables sorting. Do not flash.
bool cameraInit() { return false; }
bool cameraCapture() { return false; }
const uint8_t* cameraChunk(size_t) { return nullptr; }
#else
#include "src/camera/OV7670.h"
OV7670* camera=nullptr;
bool cameraInit() {
  // Exactly the constructor/pin order in the supplied current ESP32 document.
  camera=new OV7670(OV7670::QVGA_RGB565,26,27,25,23,4,22,5,18,19,21,33,32,34,35);
  if(!camera || !camera->frame)return false;
  for(byte i=0;i<20;i++) { camera->oneFrame();delay(1); }
  return true;
}
bool cameraCapture() {
  if(!camera)return false;
  const int before=I2SCamera::framesReceived;
  camera->oneFrame();
  if(I2SCamera::framesReceived<=before || !I2SCamera::frameReady || I2SCamera::dmaErrors!=0 || I2SCamera::descriptorMismatches!=0 || I2SCamera::framePointer!=FRAME_BYTES)return false;
  for(size_t i=0;i<CHUNK_COUNT;i++)if(!I2SCamera::frameChunks[i])return false;
  return true;
}
const uint8_t* cameraChunk(size_t i) { return I2SCamera::frameChunks[i]; }
#endif
// The proven driver is copied unchanged from Desktop/Arduino/ESP32_I2S_Camera.
// Keep its Arduino ESP32 core 2.0.17 timing/API compatibility.
