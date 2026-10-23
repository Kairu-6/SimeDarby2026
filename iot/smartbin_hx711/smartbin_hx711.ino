// Current user wiring: DOUT36 / SCK13. Saves tare in the v3 gateway namespace.
#include <HX711.h>
#include <Preferences.h>
HX711 scale;
Preferences prefs;
bool tared=false;
void setup() {
  Serial.begin(115200);Serial.setTimeout(2000);scale.begin(36,13);prefs.begin("smartbinv3",false);
  Serial.println("Empty plate, then TARE. Add known mass and send grams (50..4000). 'raw' prints diagnostic counts.");
}
void loop() {
  if(!Serial.available()) { delay(50);return; }
  String line=Serial.readStringUntil('\n');line.trim();
  if(!scale.wait_ready_timeout(1500)) { Serial.println("HX711 not ready. Check DOUT36, SCK13, supply and wiring.");return; }
  long raw=scale.read_average(5);
  if(line=="raw") { Serial.println(raw);return; }
  if(raw==0) { Serial.println("Raw zero is unhealthy; fix wiring before tare/calibration.");return; }
  if(line=="TARE") { scale.tare(20);prefs.putLong("offset",scale.get_offset());tared=true;Serial.println("Empty tare saved. Add known mass, then send its grams.");return; }
  float known=line.toFloat();
  if(!tared || known<50 || known>4000) { Serial.println("TARE first; then use 50..4000 g known mass.");return; }
  float factor=(scale.read_average(20)-scale.get_offset())/known;
  Serial.print("HX_COUNTS_PER_GRAM = ");Serial.println(factor,6);
  Serial.println("Put this signed value in smartbin_esp32/config.h. Verify with a second mass. Never tare a loaded tray.");
}
