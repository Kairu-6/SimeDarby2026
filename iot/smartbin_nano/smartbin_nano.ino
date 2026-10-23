/* Current wiring + newline JSON at 9600. No motor motion without a server UUID.
 * A timed limit is a FAULT, never a successful deposit. EMPTY comes from HX711.
 */
#include <Arduino.h>
#include <Servo.h>
#include <SoftwareSerial.h>
#include "config.h"

SoftwareSerial espLink(ESP_RX,ESP_TX);
Servo doors[3],paddle;
enum Phase { IDLE,OPENING,PUSHING,CLOSING,FAULT };
Phase phase=IDLE;
char current[37]="",completed[37]="",errorCode[24]="",rx[170];
char bootId[17];
byte used=0,indexSensor=0,selected=0; bool overflow=false;
unsigned long phaseAt=0,pingAt=0,reportAt=0,sonarAt=0;
long mm[3]={-1,-1,-1},samples[3][3]={{0}};
byte count[3]={0},sampleIndex[3]={0};
unsigned long sampledAt[3]={0};

const char* phaseName() { return phase==IDLE ? "idle" : phase==OPENING ? "opening" : phase==PUSHING ? "pushing" : phase==CLOSING ? "closing" : "fault"; }
void closeAll() { for(byte i=0;i<3;i++)doors[i].writeMicroseconds(DOOR_CLOSED_US[i]); }
void stopMotor() { paddle.writeMicroseconds(PADDLE_STOP_US); }
bool field(const char* json,const char* key,char* out,size_t cap) {
  char pattern[35];snprintf(pattern,sizeof(pattern),"\"%s\"",key);
  const char* p=strstr(json,pattern);if(!p || !(p=strchr(p+strlen(pattern),':')))return false;
  p++;while(*p==' ' || *p=='\t')p++;if(*p++!='"')return false;
  const char* end=strchr(p,'"');if(!end || end-p<1 || (size_t)(end-p)>=cap)return false;
  memcpy(out,p,end-p);out[end-p]=0;return true;
}
bool uuid(const char* id) {
  if(strlen(id)!=36)return false;
  for(byte i=0;i<36;i++)if(i==8 || i==13 || i==18 || i==23) { if(id[i]!='-')return false; } else if(!isxdigit(id[i]))return false;
  return true;
}
void status(const char* id,const char* state,const char* error=nullptr) {
  espLink.print(F("{\"v\":1,\"type\":\"sort_status\",\"command_id\":\""));espLink.print(id);
  espLink.print(F("\",\"status\":\""));espLink.print(state);espLink.print('"');
  if(error) { espLink.print(F(",\"error_code\":\""));espLink.print(error);espLink.print('"'); }
  espLink.println('}');
}
void fail(const char* reason) {
  stopMotor();closeAll();phase=FAULT;strncpy(errorCode,reason,sizeof(errorCode)-1);
  if(current[0])status(current,"failed",reason);
}
void command(char* line) {
  char type[14]="",id[37]="",bin[10]="",reason[12]="";
  if(!field(line,"type",type,sizeof(type)))return;
  if(!strcmp(type,"ping")) { pingAt=millis();return; }
  field(line,"command_id",id,sizeof(id));
  if(!strcmp(type,"stop")) {
    field(line,"reason",reason,sizeof(reason));
    if(phase==PUSHING && !strcmp(current,id) && !strcmp(reason,"empty")) {
      stopMotor();closeAll();phase=CLOSING;phaseAt=millis();
    } else if(strcmp(reason,"empty"))fail("STOPPED");
    return;
  }
  if(strcmp(type,"sort") || !uuid(id) || !field(line,"bin_id",bin,sizeof(bin)))return;
  if(!strcmp(id,completed)) { status(id,"completed");return; }
  if(!strcmp(id,current)) { status(id,phase==FAULT ? "failed" : "started",phase==FAULT ? errorCode : nullptr);return; }
  if(phase!=IDLE || !HARDWARE_CONFIGURED || millis()-pingAt>LINK_TIMEOUT_MS) { status(id,"failed","NOT_READY");return; }
  int destination=!strcmp(bin,"bin_1") ? 0 : !strcmp(bin,"bin_2") ? 1 : !strcmp(bin,"bin_3") ? 2 : -1;
  if(destination<0) { status(id,"failed","INVALID_BIN");return; }
  if(mm[destination]<0 || mm[destination]<=FULL_BLOCK_MM[destination] || millis()-sampledAt[destination]>2500) { status(id,"failed","BIN_FULL_OR_STALE");return; }
  selected=destination;strcpy(current,id);stopMotor();closeAll();
  doors[selected].writeMicroseconds(DOOR_OPEN_US[selected]);phase=OPENING;phaseAt=millis();status(id,"accepted");
}
void receive() {
  while(espLink.available()) {
    char c=espLink.read();
    if(c=='\n') { if(!overflow && used) { rx[used]=0;command(rx); }used=0;overflow=false; }
    else if(c!='\r') { if(used<sizeof(rx)-1 && !overflow)rx[used++]=c;else overflow=true; }
  }
}
void report() {
  espLink.print(F("{\"v\":1,\"type\":\"telemetry\",\"boot_id\":\""));espLink.print(bootId);
  espLink.print(F("\",\"state\":\""));espLink.print(phaseName());
  espLink.print(F("\",\"open_doors_mask\":"));
  // Backend's mask is category-based: food=1, recyclable=2, reject=4.
  espLink.print(phase==OPENING || phase==PUSHING ? (selected==0 ? 2 : selected==1 ? 1 : 4) : 0);
  espLink.print(F(",\"last_completed_command\":"));
  if(completed[0]) { espLink.print('"');espLink.print(completed);espLink.print('"'); } else espLink.print(F("null"));
  espLink.print(F(",\"error_code\":"));
  if(errorCode[0]) { espLink.print('"');espLink.print(errorCode);espLink.print('"'); } else espLink.print(F("null"));
  espLink.print(F(",\"distances_cm\":["));
  for(byte i=0;i<3;i++) { if(i)espLink.print(',');if(mm[i]<0)espLink.print(F("null"));else espLink.print(mm[i]/10.0f,1); }
  espLink.print(F("],\"sample_age_ms\":["));
  for(byte i=0;i<3;i++) { if(i)espLink.print(',');espLink.print(millis()-sampledAt[i]); }
  espLink.println(F("]}"));
}
void setup() {
  Serial.begin(115200);espLink.begin(9600);
  snprintf(bootId,sizeof(bootId),"%lx",((unsigned long)analogRead(A7)<<16)^micros());
  for(byte i=0;i<3;i++) { pinMode(TRIG_PINS[i],OUTPUT);pinMode(ECHO_PINS[i],INPUT);doors[i].attach(DOOR_PINS[i]); }
  paddle.attach(PADDLE_PIN);stopMotor();closeAll();pingAt=millis();
  if(!HARDWARE_CONFIGURED) { phase=FAULT;strcpy(errorCode,"CONFIG_REQUIRED"); }
  Serial.println(F("SmartBin 0.3: JSON 9600, waiting for ESP32. Calibrate before enabling."));
}
void loop() {
  receive();unsigned long t=millis();
  if(phase==OPENING || phase==PUSHING || phase==CLOSING) {
    if(t-pingAt>LINK_TIMEOUT_MS)fail("UART_TIMEOUT");
    else if(phase==OPENING && t-phaseAt>=GATE_MS) { paddle.writeMicroseconds(PADDLE_PUSH_US);phase=PUSHING;phaseAt=t;status(current,"started"); }
    else if(phase==PUSHING && t-phaseAt>=MAX_PUSH_MS)fail("PUSH_TIMEOUT");
    else if(phase==CLOSING && t-phaseAt>=GATE_MS) { strcpy(completed,current);phase=IDLE;status(current,"completed");current[0]=0; }
  }
  if((phase==IDLE || phase==FAULT) && t-sonarAt>=80) {
    byte i=indexSensor;digitalWrite(TRIG_PINS[i],LOW);delayMicroseconds(2);digitalWrite(TRIG_PINS[i],HIGH);delayMicroseconds(10);digitalWrite(TRIG_PINS[i],LOW);
    unsigned long duration=pulseIn(ECHO_PINS[i],HIGH,18000);
    if(duration) { samples[i][sampleIndex[i]]=(long)(duration*0.343f/2);sampleIndex[i]=(sampleIndex[i]+1)%3;if(count[i]<3)count[i]++;
      long a=samples[i][0],b=samples[i][1],c=samples[i][2];mm[i]=count[i]==3 ? max(min(a,b),min(max(a,b),c)) : -1;
    } else { mm[i]=-1;count[i]=0; }
    sampledAt[i]=millis();indexSensor=(i+1)%3;sonarAt=t;
  }
  if(t-reportAt>=750) { report();reportAt=millis(); }
}
