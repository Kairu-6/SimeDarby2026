/* Sime Loop v2: camera + HX711 + HTTP on ESP32; 3 doors/pusher/sonars on Nano.
 * UART and HX711 run in an independent task so HTTP/model latency never starves
 * the Nano watchdog. Pending cycles survive reset and are never auto-repushed.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <HX711.h>
#include <Preferences.h>
#include "esp_camera.h"
#include "config.h"

HardwareSerial nano(2);
HX711 scale;
Preferences prefs;
SemaphoreHandle_t stateMutex, serialMutex;
struct Shared {
  float grams=0; bool stable=false; unsigned long scaleAt=0;
  long mm[3]={-1,-1,-1}; unsigned long sonarAt[3]={0,0,0};
  char phase='F', nanoBoot[17]="", done[17]="-", fault[24]="NO_UART";
  byte doors=0; unsigned long frameAt=0; bool running=false;
  char active[17]=""; bool emptyCommandSent=false, rebooted=false, pauseScale=false;
};
Shared shared;
String bootId, currentSession, currentCycle, currentRoute, confirmationEvent;
unsigned long seq=0; float frozenKg=0; bool emptySent=false, recovery=false;
unsigned long cycleSentAt=0; bool cameraReady=false;

Shared snapshot() { xSemaphoreTake(stateMutex,portMAX_DELAY); Shared s=shared; xSemaphoreGive(stateMutex); return s; }
void uart(const String& command) {
  xSemaphoreTake(serialMutex,portMAX_DELAY); nano.println(command); xSemaphoreGive(serialMutex);
}
String nextEvent() { return String(DEVICE_ID)+"-"+bootId+"-"+String(++seq); }

void parseNano(char* line) {
  char boot[17], phase, done[17], fault[24], id[17]; unsigned long uptime;
  unsigned int doors;
  long f,r,x; unsigned long af,ar,ax;
  xSemaphoreTake(stateMutex,portMAX_DELAY);
  if (sscanf(line,"SL2 T %16s %lu %c %u %16s %23s",boot,&uptime,&phase,&doors,done,fault)==6) {
    if (shared.nanoBoot[0] && strcmp(boot,shared.nanoBoot) && shared.active[0]) shared.rebooted=true;
    strcpy(shared.nanoBoot,boot); shared.phase=phase; shared.doors=doors;
    strcpy(shared.done,done); strcpy(shared.fault,!strcmp(fault,"-") ? "" : fault);
    shared.frameAt=millis(); shared.running=(phase=='P');
  } else if (sscanf(line,"SL2 L %ld %ld %ld %lu %lu %lu",&f,&r,&x,&af,&ar,&ax)==6) {
    long values[]={f,r,x}; unsigned long ages[]={af,ar,ax};
    for (byte i=0;i<3;i++) { shared.mm[i]=values[i]; shared.sonarAt[i]=millis()-ages[i]; }
  } else if (sscanf(line,"SL2 FAULT %16s %23s",id,fault)==2) {
    strncpy(shared.fault,fault,sizeof(shared.fault)-1); shared.phase='F';
  }
  xSemaphoreGive(stateMutex);
}

void sensorTask(void*) {
  char line[160]; size_t used=0; bool overflow=false;
  float samples[8]={0}; byte count=0,index=0;
  unsigned long pingAt=0,emptyAt=0;
  while (true) {
    while (nano.available()) {
      char ch=nano.read();
      if (ch=='\n') { if (!overflow) { line[used]=0; parseNano(line); } used=0; overflow=false; }
      else if (ch!='\r') { if (used<sizeof(line)-1 && !overflow) line[used++]=ch; else overflow=true; }
    }
    if (millis()-pingAt>=250) { uart("SL2 PING"); pingAt=millis(); }
    Shared before=snapshot();
    if (before.pauseScale) { count=0; index=0; }
    if (!before.pauseScale && scale.is_ready()) {
      float value=scale.get_units(1); samples[index]=value; index=(index+1)%8; if(count<8)count++;
      float lo=samples[0],hi=samples[0],sum=0;
      for (byte i=0;i<count;i++) { lo=min(lo,samples[i]); hi=max(hi,samples[i]); sum+=samples[i]; }
      xSemaphoreTake(stateMutex,portMAX_DELAY);
      shared.grams=sum/count; shared.stable=count==8 && hi-lo<=STABILITY_RANGE_G;shared.scaleAt=millis();
      xSemaphoreGive(stateMutex);
    }
    Shared s=snapshot();
    if (s.active[0] && s.running && s.stable && millis()-s.scaleAt<=500 && fabs(s.grams)<=EMPTY_G) {
      if (!emptyAt) emptyAt=millis();
      if (!s.emptyCommandSent && millis()-emptyAt>=400) {
        uart("SL2 STOP "+String(s.active)+" EMPTY");
        xSemaphoreTake(stateMutex,portMAX_DELAY);shared.emptyCommandSent=true;xSemaphoreGive(stateMutex);
      }
    } else emptyAt=0;
    // Scale/serial task never performs network I/O.
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

int callApi(const String& path, JsonDocument& output, const String* body=nullptr, const uint8_t* raw=nullptr, size_t len=0) {
  HTTPClient http; http.setConnectTimeout(3000); http.setTimeout(raw ? 120000 : 8000);
  http.begin(String(API_BASE)+path); http.addHeader("X-Device-Key",DEVICE_KEY);
  int code;
  if (raw) {
    http.addHeader("Content-Type","application/octet-stream");
    http.addHeader("X-Session-Id",currentSession); http.addHeader("X-Width","160"); http.addHeader("X-Height","120");
    http.addHeader("X-Byte-Order",FRAME_BYTE_ORDER);
    uint32_t hash=2166136261UL; for(size_t i=0;i<len;i++) hash=(hash^raw[i])*16777619UL;
    char checksum[9]; snprintf(checksum,sizeof(checksum),"%08lX",(unsigned long)hash);
    http.addHeader("X-Frame-FNV1A",checksum); http.addHeader("X-Capture-Id",nextEvent());
    code=http.POST(const_cast<uint8_t*>(raw),len);
  } else if (body) { http.addHeader("Content-Type","application/json"); code=http.POST(*body); }
  else code=http.GET();
  if (code>0) deserializeJson(output,http.getString());
  http.end(); return code;
}

String telemetryEvent;
bool sendTelemetry() {
  Shared s=snapshot(); JsonDocument body,response;
  body["device_id"]=DEVICE_ID; telemetryEvent=nextEvent(); body["event_id"]=telemetryEvent;
  body["boot_id"]=bootId; body["sequence_no"]=seq; body["uptime_ms"]=millis(); body["firmware_version"]="2.0.0";
  const char* names[]={"food","recyclable","reject"};
  JsonArray levels=body["levels"].to<JsonArray>();
  for (byte i=0;i<3;i++) {
    JsonObject level=levels.add<JsonObject>(); level["compartment"]=names[i];
    bool valid=s.mm[i]>=0 && millis()-s.sonarAt[i]<=1000; level["valid"]=valid;
    if(valid) level["distance_cm"]=s.mm[i]/10.0f; else level["distance_cm"]=nullptr;
  }
  body["scale"]["weight_g"]=s.grams; body["scale"]["stable"]=s.stable && millis()-s.scaleAt<=500; body["scale"]["calibrated"]=HX_UNITS_PER_GRAM!=0;
  JsonObject controller=body["controller"].to<JsonObject>();
  controller["ready"]=s.frameAt && millis()-s.frameAt<1000 && !s.fault[0];
  controller["state"]=s.phase=='I' ? "idle" : s.phase=='O' ? "opening" : s.phase=='P' ? "pushing" : s.phase=='C' ? "closing" : "fault";
  controller["boot_id"]=s.nanoBoot[0] ? s.nanoBoot : "unknown";
  controller["frame_age_ms"]=min((unsigned long)3600000,s.frameAt ? millis()-s.frameAt : (unsigned long)3600000);
  controller["open_doors_mask"]=s.doors;
  if(strcmp(s.done,"-")) controller["last_completed_cycle"]=s.done; else controller["last_completed_cycle"]=nullptr;
  if(s.fault[0]) controller["fault"]=s.fault; else controller["fault"]=nullptr;
  String payload; serializeJson(body,payload);
  return callApi("/api/device/telemetry",response,&payload)==200;
}

bool initCamera() {
  camera_config_t c={}; c.ledc_channel=LEDC_CHANNEL_0; c.ledc_timer=LEDC_TIMER_0;
  c.pin_d0=CAM_D0;c.pin_d1=CAM_D1;c.pin_d2=CAM_D2;c.pin_d3=CAM_D3;
  c.pin_d4=CAM_D4;c.pin_d5=CAM_D5;c.pin_d6=CAM_D6;c.pin_d7=CAM_D7;
  c.pin_xclk=CAM_XCLK;c.pin_pclk=CAM_PCLK;c.pin_vsync=CAM_VSYNC;c.pin_href=CAM_HREF;
  c.pin_sccb_sda=CAM_SDA;c.pin_sccb_scl=CAM_SCL;c.pin_pwdn=-1;c.pin_reset=-1;
  c.xclk_freq_hz=10000000; c.pixel_format=PIXFORMAT_RGB565; c.frame_size=FRAMESIZE_QQVGA;
  c.fb_count=1;c.fb_location=CAMERA_FB_IN_DRAM;c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;
  return esp_camera_init(&c)==ESP_OK;
}

void clearPending() {
  prefs.remove("cycle"); prefs.remove("session"); prefs.remove("route"); prefs.remove("kg"); prefs.remove("event");
  currentCycle=""; currentSession=""; currentRoute=""; confirmationEvent=""; emptySent=false; recovery=false;
  xSemaphoreTake(stateMutex,portMAX_DELAY);shared.active[0]=0;shared.emptyCommandSent=false;shared.rebooted=false;xSemaphoreGive(stateMutex);
}

void reportFault(const String& reason) {
  uart("SL2 ABORT"); JsonDocument body,response;
  body["device_id"]=DEVICE_ID;body["event_id"]=nextEvent();body["reason"]=reason;
  String payload;serializeJson(body,payload);
  int code=callApi("/api/device/cycles/"+currentCycle+"/fault",response,&payload);
  // If the original confirmation succeeded but its reply was lost, a confirmed cycle
  // cannot be turned into a fault. Server 409 here means it is already final.
  if(code==200 || code==409) clearPending();
}

void setup() {
  Serial.begin(115200);
  if(!HARDWARE_CONFIGURED || HX_UNITS_PER_GRAM==0) { Serial.println("Configure wiring, Wi-Fi and signed HX711 calibration first."); return; }
  stateMutex=xSemaphoreCreateMutex();serialMutex=xSemaphoreCreateMutex();
  nano.begin(38400,SERIAL_8N1,UART_RX,UART_TX);
  scale.begin(HX_DOUT,HX_SCK);scale.set_scale(HX_UNITS_PER_GRAM);
  // Offset is calibrated with an empty plate once and saved; NEVER tare a loaded tray.
  prefs.begin("simeloop",false);
  if(!prefs.isKey("offset")) { Serial.println("Empty the plate, then send TARE in USB serial."); }
  else scale.set_offset(prefs.getLong("offset"));
  bootId=String((uint32_t)esp_random(),HEX);
  currentCycle=prefs.getString("cycle","");currentSession=prefs.getString("session","");
  currentRoute=prefs.getString("route","");frozenKg=prefs.getFloat("kg",0);confirmationEvent=prefs.getString("event","");
  recovery=currentCycle.length();
  xTaskCreatePinnedToCore(sensorTask,"sensors-uart",6144,nullptr,2,nullptr,1);
  WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  while(WiFi.status()!=WL_CONNECTED) delay(100);
  cameraReady=initCamera();
  if(!cameraReady) Serial.println("Camera init failed; no deposits will be armed.");
}

void loop() {
  if(!HARDWARE_CONFIGURED || HX_UNITS_PER_GRAM==0) { delay(1000);return; }
  if(Serial.available() && !currentCycle.length()) {
    String cmd=Serial.readStringUntil('\n');cmd.trim();
    if(cmd=="TARE") {
      xSemaphoreTake(stateMutex,portMAX_DELAY);shared.pauseScale=true;xSemaphoreGive(stateMutex);delay(50);
      scale.tare(20);prefs.putLong("offset",scale.get_offset());
      xSemaphoreTake(stateMutex,portMAX_DELAY);shared.pauseScale=false;xSemaphoreGive(stateMutex);
      Serial.println("Empty-plate offset saved.");
    }
  }
  // An armed local cycle can finish without Wi-Fi; UART watchdog and HX711 STOP
  // remain active in sensorTask. Keep its receipt pending until connectivity returns.
  if(WiFi.status()!=WL_CONNECTED) { delay(1000);return; }
  if(!prefs.isKey("offset")) { delay(500);return; }
  if(currentCycle.length()) {
    Shared s=snapshot();
    if(recovery || s.rebooted) { reportFault("GATEWAY_OR_NANO_RESET");delay(1000);return; }
    if(s.fault[0] || millis()-s.frameAt>1200) { reportFault(s.fault[0] ? s.fault : "UART_TIMEOUT");delay(500);return; }
    if(strcmp(s.done,currentCycle.c_str()) && ((s.phase=='I' && millis()-cycleSentAt>2000) || millis()-cycleSentAt>10000)) { reportFault("CYCLE_TIMEOUT");delay(500);return; }
    if(!strcmp(s.done,currentCycle.c_str()) && s.phase=='I' && s.stable && fabs(s.grams)<=EMPTY_G) {
      if(sendTelemetry()) {
        JsonDocument body,response;
        body["event_id"]=confirmationEvent;body["device_id"]=DEVICE_ID;body["cycle_id"]=currentCycle;
        body["controller_cycle_id"]=currentCycle;body["route"]=currentRoute;body["weight_kg"]=frozenKg;
        String payload;serializeJson(body,payload);
        int code=callApi("/api/device/deposits/"+currentSession+"/confirm",response,&payload);
        if(code==200) { Serial.printf("Completed: %d points\n",response["points"].as<int>());clearPending(); }
        else if(code>=400 && code<500) reportFault("CONFIRM_REJECTED");
      }
    } else if(s.phase=='I' && !s.stable) { /* wait for settling */ }
    delay(200);return;
  }
  if(!sendTelemetry()) { delay(1000);return; }
  if(!cameraReady) { delay(1000);return; }
  Shared s=snapshot();
  if(s.phase!='I' || !s.stable || s.grams<MIN_ITEM_G || s.grams>MAX_ITEM_G || s.fault[0]) { delay(500);return; }
  JsonDocument session;
  if(callApi("/api/device/bins/"+String(DEVICE_ID)+"/session",session)!=200 || session["session"].isNull()) { delay(500);return; }
  if(!session["cycle"].isNull()) {
    currentCycle=session["cycle"]["id"].as<String>();
    currentSession=session["session"]["id"].as<String>();
    reportFault("ARM_REPLY_LOST");delay(1000);return;
  }
  currentSession=session["session"]["id"].as<String>();
  camera_fb_t* fb=esp_camera_fb_get();
  if(!fb || fb->width!=160 || fb->height!=120 || fb->len!=160*120*2) { if(fb)esp_camera_fb_return(fb);currentSession="";delay(1000);return; }
  JsonDocument prediction;
  int code=callApi("/camera/upload",prediction,nullptr,fb->buf,fb->len);esp_camera_fb_return(fb);
  if(code!=200 || !prediction["accepted"].as<bool>()) { currentSession="";delay(1500);return; }
  Shared after=snapshot();
  if(!after.stable || fabs(after.grams-s.grams)>STABILITY_RANGE_G) { currentSession="";delay(500);return; }
  if(!sendTelemetry()) { currentSession="";return; }
  JsonDocument body,armed;
  body["device_id"]=DEVICE_ID;body["request_id"]=nextEvent();body["telemetry_event_id"]=telemetryEvent;
  String payload;serializeJson(body,payload);
  if(callApi("/api/device/deposits/"+currentSession+"/arm",armed,&payload)!=200 || !armed["executable"].as<bool>()) { currentSession="";delay(500);return; }
  currentCycle=armed["id"].as<String>();currentRoute=armed["route"].as<String>();frozenKg=armed["weight_kg"];
  confirmationEvent=nextEvent();emptySent=false;
  prefs.putString("cycle",currentCycle);prefs.putString("session",currentSession);prefs.putString("route",currentRoute);
  prefs.putFloat("kg",frozenKg);prefs.putString("event",confirmationEvent);
  xSemaphoreTake(stateMutex,portMAX_DELAY);strncpy(shared.active,currentCycle.c_str(),16);shared.active[16]=0;shared.emptyCommandSent=false;xSemaphoreGive(stateMutex);
  cycleSentAt=millis();
  char route=currentRoute=="food" ? 'F' : currentRoute=="recyclable" ? 'R' : 'X';
  uart("SL2 CYCLE "+currentCycle+" "+String(route));
  delay(200);
}
