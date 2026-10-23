/* NodeMCU-32S -> hardware UART -> Nano V3. No positional/end-stop feedback.
 * Three SG90 doors; one continuous MG996R pusher; three HC-SR04 sensors.
 * ESP32 sends EMPTY only after a stable empty HX711 tray reading.
 */
#include <Arduino.h>
#include <Servo.h>
#include "config.h"

Servo doors[3], pusher;
enum Phase { IDLE, OPENING, PUSHING, CLOSING, FAULT };
Phase phase = IDLE;
char currentId[17] = "", completedId[17] = "-", faultCode[24] = "-";
char input[96]; byte used = 0; bool overflow = false;
unsigned long phaseAt, lastPing, lastStatus, lastSonar, nanoBoot;
long distancesMm[3] = {-1, -1, -1};
long history[3][3] = {{0}}; byte historyCount[3]={0}, historyIndex[3]={0};
unsigned long sampledAt[3] = {0, 0, 0};
byte selectedDoor = 0, sonarIndex = 0;

char phaseCode() { return "IOPCF"[phase]; }
void closeDoors() { for (byte i=0; i<3; i++) doors[i].writeMicroseconds(DOOR_CLOSED_US[i]); }
void stopPusher() { pusher.writeMicroseconds(PUSHER_NEUTRAL_US); }
void emitId(const __FlashStringHelper* verb, const char* id) {
  Serial.print(F("SL2 ")); Serial.print(verb); Serial.print(' '); Serial.println(id);
}
void fail(const char* reason) {
  stopPusher(); closeDoors(); phase = FAULT;
  strncpy(faultCode, reason, sizeof(faultCode)-1);
  Serial.print(F("SL2 FAULT ")); Serial.print(currentId[0] ? currentId : "-");
  Serial.print(' '); Serial.println(reason);
}
bool validId(const char* id) {
  if (strlen(id) != 16) return false;
  for (byte i=0; i<16; i++) if (!isxdigit(id[i])) return false;
  return true;
}

void command(char* line) {
  char verb[12] = "", id[20] = "", arg[12] = "";
  if (sscanf(line, "SL2 %11s %19s %11s", verb, id, arg) < 1) return;
  if (!strcmp(verb,"PING")) { lastPing=millis(); return; }
  if (!strcmp(verb,"STOP")) {
    if (!strcmp(id,currentId) && !strcmp(arg,"EMPTY") && phase==PUSHING) {
      stopPusher(); closeDoors(); phase=CLOSING; phaseAt=millis();
    }
    return;
  }
  if (!strcmp(verb,"ABORT")) { fail("ABORTED"); return; }
  if (strcmp(verb,"CYCLE") || !validId(id)) return;
  if (!strcmp(id,completedId)) { emitId(F("DONE"),id); return; }
  if (!strcmp(id,currentId) && phase!=IDLE) { emitId(F("ACK"),id); return; }
  if (!HARDWARE_CONFIGURED || phase!=IDLE || millis()-lastPing>WATCHDOG_MS) {
    emitId(F("BUSY"),id); return;
  }
  if (strlen(arg)!=1 || !strchr("FRX",arg[0])) return;
  selectedDoor = arg[0]=='F' ? 0 : arg[0]=='R' ? 1 : 2;
  // Local duplicate interlock: never open a destination with unknown or high level.
  // Backend uses measured geometry; Nano independently refuses stale/no-echo readings.
  if (distancesMm[selectedDoor]<0 || distancesMm[selectedDoor]<=FULL_BLOCK_MM[selectedDoor] || millis()-sampledAt[selectedDoor]>1000) {
    emitId(F("BUSY"),id); return;
  }
  strcpy(currentId,id); stopPusher(); closeDoors();
  doors[selectedDoor].writeMicroseconds(DOOR_OPEN_US[selectedDoor]);
  phase=OPENING; phaseAt=millis(); emitId(F("ACK"),currentId);
}

void receive() {
  while (Serial.available()) {
    char ch=Serial.read();
    if (ch=='\n') {
      if (!overflow) { input[used]='\0'; command(input); }
      used=0; overflow=false;
    } else if (ch!='\r') {
      if (used<sizeof(input)-1 && !overflow) input[used++]=ch;
      else overflow=true;
    }
  }
}

void report() {
  Serial.print(F("SL2 T ")); Serial.print(nanoBoot,HEX); Serial.print(' ');
  Serial.print(millis()); Serial.print(' '); Serial.print(phaseCode()); Serial.print(' ');
  Serial.print(phase==OPENING || phase==PUSHING ? (1<<selectedDoor) : 0); Serial.print(' ');
  Serial.print(completedId); Serial.print(' '); Serial.println(faultCode);
  Serial.print(F("SL2 L"));
  for (byte i=0;i<3;i++) { Serial.print(' '); Serial.print(distancesMm[i]); }
  for (byte i=0;i<3;i++) { Serial.print(' '); Serial.print(millis()-sampledAt[i]); }
  Serial.println();
}

void setup() {
  Serial.begin(UART_BAUD);
  nanoBoot=((unsigned long)analogRead(A7)<<16)^micros();
  for (byte i=0;i<3;i++) {
    doors[i].attach(DOOR_PINS[i]); pinMode(TRIG_PINS[i],OUTPUT); pinMode(ECHO_PINS[i],INPUT);
  }
  pusher.attach(PUSHER_PIN); stopPusher(); closeDoors(); lastPing=millis();
  if (!HARDWARE_CONFIGURED) { phase=FAULT; strcpy(faultCode,"CONFIG_REQUIRED"); }
}

void loop() {
  receive(); unsigned long t=millis();
  if (phase==OPENING || phase==PUSHING || phase==CLOSING) {
    if (t-lastPing>WATCHDOG_MS) fail("UART_TIMEOUT");
    else if (phase==OPENING && t-phaseAt>=GATE_SETTLE_MS) {
      pusher.writeMicroseconds(PUSHER_FORWARD_US); phase=PUSHING; phaseAt=t;
      emitId(F("RUN"),currentId);
    } else if (phase==PUSHING && t-phaseAt>=MAX_PUSH_MS) fail("PUSH_TIMEOUT");
    else if (phase==CLOSING && t-phaseAt>=GATE_SETTLE_MS) {
      strcpy(completedId,currentId); phase=IDLE; emitId(F("DONE"),completedId);
      currentId[0]='\0';
    }
  }
  // Stagger sensors to reduce acoustic crosstalk. Maximum echo wait is 12 ms.
  if (t-lastSonar>=80 && (phase==IDLE || phase==FAULT)) {
    digitalWrite(TRIG_PINS[sonarIndex],LOW); delayMicroseconds(2);
    digitalWrite(TRIG_PINS[sonarIndex],HIGH); delayMicroseconds(10);
    digitalWrite(TRIG_PINS[sonarIndex],LOW);
    unsigned long pulse=pulseIn(ECHO_PINS[sonarIndex],HIGH,12000);
    if (pulse) {
      history[sonarIndex][historyIndex[sonarIndex]]=(long)(pulse*0.343f/2);
      historyIndex[sonarIndex]=(historyIndex[sonarIndex]+1)%3;
      if(historyCount[sonarIndex]<3) historyCount[sonarIndex]++;
      long a=history[sonarIndex][0],b=history[sonarIndex][1],c=history[sonarIndex][2];
      distancesMm[sonarIndex]=historyCount[sonarIndex]==3 ? max(min(a,b),min(max(a,b),c)) : -1;
    } else { distancesMm[sonarIndex]=-1; historyCount[sonarIndex]=0; }
    sampledAt[sonarIndex]=millis(); sonarIndex=(sonarIndex+1)%3; lastSonar=t;
  }
  if (t-lastStatus>=250) { report(); lastStatus=t; }
}
