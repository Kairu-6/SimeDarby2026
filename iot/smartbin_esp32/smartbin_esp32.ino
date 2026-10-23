/* SmartBin 0.3: current user wiring, custom OV7670 adapter, kiosk-first sessions.
 * Camera frames alone never open a door. The server validates selected category,
 * scale and Nano state and returns one UUID command. No automatic push replay.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <HX711.h>
#include <Preferences.h>
#include "config.h"
#include "camera_adapter.h"

HardwareSerial nanoSerial(2);
HX711 scale;
Preferences prefs;
SemaphoreHandle_t mutex,txMutex;
struct State {
  float grams=0;long raw=0;bool stable=false,healthy=false,paused=false;
  unsigned long scaleAt=0,frameAt=0,sampledAt[3]={0};
  float distances[3]={-1,-1,-1};
  char phase[12]="fault",nanoBoot[41]="",done[37]="",fault[64]="NO_UART",active[37]="";
  byte doors=0;bool rebooted=false,emptySent=false;
};
State shared;
String queue[8];byte queueHead=0,queueCount=0;
String bootId,sessionId,cycleId,route,pendingEvent;
unsigned long sequence=0,cycleAt=0,retryAt=0,lastTelemetry=0,eventAttemptAt=0;
bool cameraReady=false,recovering=false;

State snapshot() { xSemaphoreTake(mutex,portMAX_DELAY);State s=shared;xSemaphoreGive(mutex);return s; }
String uuid() {
  uint8_t b[16];esp_fill_random(b,16);b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
  char text[37];snprintf(text,sizeof(text),"%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8],b[9],b[10],b[11],b[12],b[13],b[14],b[15]);return String(text);
}
bool validUuid(const String& id) {
  if(id.length()!=36)return false;
  for(byte i=0;i<36;i++)if(i==8 || i==13 || i==18 || i==23) { if(id[i]!='-')return false; }else if(!isxdigit(id[i]))return false;
  return true;
}
void uart(const String& line) { xSemaphoreTake(txMutex,portMAX_DELAY);nanoSerial.println(line);xSemaphoreGive(txMutex); }
void event(const String& id,const String& status,const String& reason="") {
  JsonDocument d;d["event_id"]=uuid();d["device_id"]=DEVICE_ID;d["command_id"]=id;d["status"]=status;
  d["device_uptime_ms"]=millis();if(reason.length())d["error_code"]=reason;else d["error_code"]=nullptr;
  String payload;serializeJson(d,payload);
  xSemaphoreTake(mutex,portMAX_DELAY);
  if(queueCount<8) { queue[(queueHead+queueCount)%8]=payload;queueCount++; }
  else strncpy(shared.fault,"EVENT_QUEUE_FULL",sizeof(shared.fault)-1);
  xSemaphoreGive(mutex);
}
void parseNano(const char* line) {
  JsonDocument d;if(deserializeJson(d,line) || d["v"].as<int>()!=1)return;
  String type=d["type"] | "";
  if(type=="sort_status") {
    String id=d["command_id"] | "",status=d["status"] | "";
    if(validUuid(id) && (status=="accepted" || status=="started" || status=="completed" || status=="failed"))event(id,status,d["error_code"] | "");
    return;
  }
  if(type!="telemetry" || d["boot_id"].isNull() || d["state"].isNull())return;
  String boot=d["boot_id"].as<String>(),phase=d["state"].as<String>();
  xSemaphoreTake(mutex,portMAX_DELAY);
  if(shared.nanoBoot[0] && strcmp(shared.nanoBoot,boot.c_str()) && shared.active[0])shared.rebooted=true;
  strlcpy(shared.nanoBoot,boot.c_str(),sizeof(shared.nanoBoot));strlcpy(shared.phase,phase.c_str(),sizeof(shared.phase));
  shared.doors=d["open_doors_mask"] | 7;shared.frameAt=millis();
  strlcpy(shared.done,d["last_completed_command"] | "",sizeof(shared.done));
  strlcpy(shared.fault,d["error_code"] | "",sizeof(shared.fault));
  for(byte i=0;i<3;i++) {
    shared.distances[i]=d["distances_cm"][i].isNull() ? -1 : d["distances_cm"][i].as<float>();
    unsigned long age=d["sample_age_ms"][i] | 3600000UL;shared.sampledAt[i]=millis()-age;
  }
  xSemaphoreGive(mutex);
}
void sensorTask(void*) {
  char line[420];size_t used=0;bool overflow=false;
  float samples[8]={0};byte count=0,index=0;unsigned long pingAt=0,emptyAt=0;
  while(true) {
    while(nanoSerial.available()) {
      char c=nanoSerial.read();
      if(c=='\n') { if(!overflow && used) { line[used]=0;parseNano(line); }used=0;overflow=false; }
      else if(c!='\r') { if(used<sizeof(line)-1 && !overflow)line[used++]=c;else overflow=true; }
    }
    if(millis()-pingAt>=500) { uart("{\"v\":1,\"type\":\"ping\"}");pingAt=millis(); }
    State before=snapshot();
    if(before.paused) { count=0;index=0; }
    if(!before.paused && scale.is_ready()) {
      long raw=scale.read();float grams=(raw-scale.get_offset())/HX_COUNTS_PER_GRAM;
      samples[index]=grams;index=(index+1)%8;if(count<8)count++;
      float lo=samples[0],hi=samples[0],sum=0;
      for(byte i=0;i<count;i++) { lo=min(lo,samples[i]);hi=max(hi,samples[i]);sum+=samples[i]; }
      xSemaphoreTake(mutex,portMAX_DELAY);shared.raw=raw;shared.grams=sum/count;shared.healthy=raw!=0;
      shared.stable=count==8 && hi-lo<=STABLE_RANGE_G;shared.scaleAt=millis();xSemaphoreGive(mutex);
    }
    State s=snapshot();
    if(s.active[0] && !strcmp(s.phase,"pushing") && s.healthy && s.stable && millis()-s.scaleAt<=500 && fabs(s.grams)<=EMPTY_G) {
      if(!emptyAt)emptyAt=millis();
      if(!s.emptySent && millis()-emptyAt>=400) {
        uart("{\"v\":1,\"type\":\"stop\",\"command_id\":\""+String(s.active)+"\",\"reason\":\"empty\"}");
        xSemaphoreTake(mutex,portMAX_DELAY);shared.emptySent=true;xSemaphoreGive(mutex);
      }
    } else emptyAt=0;
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

class FrameStream : public Stream {
  size_t position=0;
 public:
  int available() override { return FRAME_BYTES-position; }
  int read() override { if(position>=FRAME_BYTES)return -1;size_t p=position++;return cameraChunk(p/CHUNK_SIZE)[p%CHUNK_SIZE]; }
  int peek() override { return position>=FRAME_BYTES ? -1 : cameraChunk(position/CHUNK_SIZE)[position%CHUNK_SIZE]; }
  void flush() override {}
  size_t write(uint8_t) override { return 0; }
};
int api(const String& path,JsonDocument& output,const String* body=nullptr,FrameStream* frame=nullptr,const String& captureId="") {
  HTTPClient http;http.setConnectTimeout(3000);http.setTimeout(frame ? 120000 : 6000);
  if(!http.begin(String(API_BASE)+path))return -1;
  http.addHeader("X-Device-Key",DEVICE_KEY);http.addHeader("X-Device-ID",DEVICE_ID);
  int code;
  if(frame) {
    http.addHeader("Content-Type","application/octet-stream");http.addHeader("X-Session-Id",sessionId);
    http.addHeader("X-Capture-ID",captureId);http.addHeader("X-Width","320");http.addHeader("X-Height","240");
    http.addHeader("X-Pixel-Format","RGB565");http.addHeader("X-Byte-Order",RGB565_BYTE_ORDER);
    uint32_t hash=2166136261UL;
    for(size_t i=0;i<CHUNK_COUNT;i++)for(size_t j=0;j<CHUNK_SIZE;j++)hash=(hash^cameraChunk(i)[j])*16777619UL;
    char checksum[9];snprintf(checksum,sizeof(checksum),"%08lX",(unsigned long)hash);http.addHeader("X-Frame-FNV1A",checksum);
    code=http.sendRequest("POST",frame,FRAME_BYTES);
  } else if(body) { http.addHeader("Content-Type","application/json");code=http.POST(*body); }
  else code=http.GET();
  if(code>0) { DeserializationError e=deserializeJson(output,http.getString());if(e && code>=200 && code<300)code=-97; }
  http.end();return code;
}
void clearCycle() {
  prefs.remove("cycle");prefs.remove("session");prefs.remove("route");cycleId="";sessionId="";route="";recovering=false;
  xSemaphoreTake(mutex,portMAX_DELAY);shared.active[0]=0;shared.rebooted=false;shared.emptySent=false;xSemaphoreGive(mutex);
}
bool telemetry() {
  State s=snapshot();JsonDocument d,response;
  d["device_id"]=DEVICE_ID;d["event_id"]=String(DEVICE_ID)+"-"+bootId+"-"+String(++sequence);
  d["boot_id"]=bootId;d["sequence_no"]=sequence;d["device_uptime_ms"]=millis();
  d["nano_connected"]=s.frameAt && millis()-s.frameAt<1000;d["nano_boot_id"]=s.nanoBoot[0] ? s.nanoBoot : "unknown";
  d["nano_frame_age_ms"]=min(3600000UL,s.frameAt ? millis()-s.frameAt : 3600000UL);
  d["actuator_state"]=s.phase;d["open_doors_mask"]=s.doors;
  if(s.done[0])d["last_completed_command"]=s.done;else d["last_completed_command"]=nullptr;
  if(s.fault[0])d["error_code"]=s.fault;else d["error_code"]=nullptr;
  JsonArray sensors=d["ultrasonic"].to<JsonArray>();
  for(byte i=0;i<3;i++) {
    JsonObject p=sensors.add<JsonObject>();p["sensor_id"]="ultrasonic_"+String(i+1);p["bin_id"]="bin_"+String(i+1);
    bool valid=s.distances[i]>=0 && millis()-s.sampledAt[i]<=2500;p["valid"]=valid;p["sample_age_ms"]=millis()-s.sampledAt[i];
    if(valid)p["distance_cm"]=s.distances[i];else p["distance_cm"]=nullptr;
  }
  bool healthy=s.healthy && millis()-s.scaleAt<=500;
  d["weight"]["healthy"]=healthy;d["weight"]["calibrated"]=healthy && HX_COUNTS_PER_GRAM!=0 && prefs.isKey("offset");
  d["weight"]["stable"]=healthy && s.stable;d["weight"]["raw"]=s.raw;d["weight"]["scope"]="inspection_plate";
  if(healthy)d["weight"]["weight_g"]=s.grams;else d["weight"]["weight_g"]=nullptr;
  String payload;serializeJson(d,payload);int code=api("/telemetry",response,&payload);
  if(code==200 && response["deposit"]["status"]=="completed") { Serial.printf("Credited %d points\n",response["deposit"]["points"].as<int>());clearCycle(); }
  return code==200;
}
void flushEvent() {
  if(millis()-eventAttemptAt<600)return;eventAttemptAt=millis();
  if(!pendingEvent.length()) {
    xSemaphoreTake(mutex,portMAX_DELAY);
    if(queueCount) { pendingEvent=queue[queueHead];queue[queueHead]="";queueHead=(queueHead+1)%8;queueCount--; }
    xSemaphoreGive(mutex);
    if(pendingEvent.length())prefs.putString("event",pendingEvent);
  }
  if(!pendingEvent.length())return;
  JsonDocument response;int code=api("/sorting/events",response,&pendingEvent);
  if(code==200) { prefs.remove("event");pendingEvent=""; }
}
void sortCommand() { uart("{\"v\":1,\"type\":\"sort\",\"command_id\":\""+cycleId+"\",\"bin_id\":\""+route+"\"}");retryAt=millis(); }
void faultCycle(const String& reason) {
  uart("{\"v\":1,\"type\":\"stop\"}");
  JsonDocument response,body;body["device_id"]=STATION_ID;body["event_id"]=uuid();body["reason"]=reason;
  String payload;serializeJson(body,payload);int code=api("/api/device/cycles/"+cycleId+"/fault",response,&payload);
  if(code==200 || code==409)clearCycle();
}
void setup() {
  Serial.begin(115200);
  if(!HARDWARE_CONFIGURED || HX_COUNTS_PER_GRAM==0) { Serial.println("Configure current wiring, camera driver, network and HX711 factor first.");return; }
  mutex=xSemaphoreCreateMutex();txMutex=xSemaphoreCreateMutex();
  nanoSerial.setRxBufferSize(2048);nanoSerial.begin(9600,SERIAL_8N1,UART_RX,UART_TX);
  scale.begin(HX_DOUT,HX_SCK);scale.set_scale(HX_COUNTS_PER_GRAM);prefs.begin("smartbinv3",false);
  if(prefs.isKey("offset"))scale.set_offset(prefs.getLong("offset"));
  cycleId=prefs.getString("cycle","");sessionId=prefs.getString("session","");route=prefs.getString("route","");
  pendingEvent=prefs.getString("event","");recovering=cycleId.length();bootId=uuid();
  if(recovering)uart("{\"v\":1,\"type\":\"stop\"}");
  // Keep the polling task off the timing-sensitive custom I2S camera's core.
  xTaskCreatePinnedToCore(sensorTask,"smartbin-uart-scale",8192,nullptr,2,nullptr,0);
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.setSleep(false);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  cameraReady=cameraInit();
  Serial.println(cameraReady ? "Camera ready. Waiting for kiosk QR claim and Check my items." : "Camera unavailable. No deposits will move.");
}
void loop() {
  if(!HARDWARE_CONFIGURED || HX_COUNTS_PER_GRAM==0) { delay(1000);return; }
  if(Serial.available()) {
    String cmd=Serial.readStringUntil('\n');cmd.trim();
    if(cmd=="TARE" && !cycleId.length() && scale.is_ready()) {
      xSemaphoreTake(mutex,portMAX_DELAY);shared.paused=true;xSemaphoreGive(mutex);delay(50);
      scale.tare(20);prefs.putLong("offset",scale.get_offset());
      xSemaphoreTake(mutex,portMAX_DELAY);shared.paused=false;xSemaphoreGive(mutex);
      Serial.println("Empty tray offset saved. Never TARE a loaded plate.");
    }
    if(cmd=="x")uart("{\"v\":1,\"type\":\"stop\"}");
  }
  if(WiFi.status()!=WL_CONNECTED) { delay(500);return; }
  flushEvent();
  State s=snapshot();
  if(cycleId.length()) {
    if(recovering || s.rebooted) { faultCycle("GATEWAY_OR_NANO_RESET");delay(500);return; }
    if(s.fault[0] || millis()-s.frameAt>3000) { faultCycle(s.fault[0] ? s.fault : "UART_TIMEOUT");delay(500);return; }
    if(strcmp(s.done,cycleId.c_str()) && millis()-cycleAt>MAX_CYCLE_MS) { faultCycle("CYCLE_TIMEOUT");delay(500);return; }
    // Retry only the SAME command while its initial ACK is missing, never after reboot.
    if(!strcmp(s.phase,"idle") && strcmp(s.done,cycleId.c_str()) && millis()-cycleAt<2000 && millis()-retryAt>=500)sortCommand();
    telemetry();
    if(cycleId.length()) { JsonDocument response;if(api("/api/device/cycles/"+cycleId,response)==200 && (response["state"]=="confirmed" || response["state"]=="failed"))clearCycle(); }
    delay(200);return;
  }
  if(!prefs.isKey("offset") || !cameraReady) { delay(500);return; }
  if(millis()-lastTelemetry>=2000) { telemetry();lastTelemetry=millis(); }
  s=snapshot();
  if(strcmp(s.phase,"idle") || s.fault[0] || !s.stable || !s.healthy || millis()-s.scaleAt>500 || s.grams<MIN_G || s.grams>MAX_G) { delay(200);return; }
  JsonDocument session;
  if(api("/api/device/bins/"+String(STATION_ID)+"/session",session)!=200 || session["session"].isNull()) { delay(500);return; }
  if(!session["cycle"].isNull()) { cycleId=session["cycle"]["id"].as<String>();faultCycle("UNRECORDED_SERVER_CYCLE");return; }
  if(!session["session"]["capture_requested"].as<bool>()) { delay(500);return; }
  sessionId=session["session"]["id"].as<String>();
  String category=session["session"]["selected_category"] | "";
  if(category!="food" && category!="recyclable") { sessionId="";delay(500);return; }
  if(!cameraCapture()) { Serial.println("Incomplete camera frame; HOLD.");delay(1000);return; }
  State after=snapshot();if(!after.stable || !after.healthy || fabs(after.grams-s.grams)>STABLE_RANGE_G || !telemetry()) { delay(500);return; }
  FrameStream frame;JsonDocument response;unsigned long requestAt=millis();
  int code=api("/camera/upload",response,nullptr,&frame,uuid());
  if(code!=200 || response["decision"]["action"]!="sort" || response["classification"]["mode"]!="real") { Serial.println("Camera decision HOLD. See station screen.");delay(500);return; }
  String id=response["decision"]["command_id"] | "",bin=response["decision"]["bin_id"] | "";
  if(!validUuid(id) || bin!=(category=="food" ? "bin_2" : "bin_1")) { Serial.println("Invalid/mismatched command; HOLD.");return; }
  cycleId=id;route=bin;
  prefs.putString("cycle",cycleId);prefs.putString("session",sessionId);prefs.putString("route",route);
  // Conservatively count the entire response round trip against the 15-second lease.
  if(millis()-requestAt>14000) { faultCycle("COMMAND_LEASE_UNCERTAIN");return; }
  after=snapshot();if(!after.stable || !after.healthy || fabs(after.grams-response["decision"]["weight_kg"].as<float>()*1000)>STABLE_RANGE_G) { faultCycle("WEIGHT_CHANGED");return; }
  xSemaphoreTake(mutex,portMAX_DELAY);strlcpy(shared.active,cycleId.c_str(),sizeof(shared.active));shared.emptySent=false;xSemaphoreGive(mutex);
  cycleAt=millis();sortCommand();delay(100);
}
