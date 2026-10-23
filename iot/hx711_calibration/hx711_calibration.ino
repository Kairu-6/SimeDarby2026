#include <HX711.h>
#include <Preferences.h>
HX711 scale;
Preferences prefs;
bool tared=false;
void setup() {
  Serial.begin(115200);Serial.setTimeout(2000);
  scale.begin(32,33);prefs.begin("simeloop",false);
  Serial.println("HX711 calibration: empty the inspection plate, then send TARE.");
}
void loop() {
  if(!Serial.available()) { delay(50);return; }
  String line=Serial.readStringUntil('\n');line.trim();
  if(!scale.wait_ready_timeout(1500)) { Serial.println("HX711 not ready. Check 3.3V, GND, DOUT32 and SCK33.");return; }
  if(line=="TARE") {
    scale.tare(20);prefs.putLong("offset",scale.get_offset());tared=true;
    Serial.println("Offset saved. Put a known mass on the plate, then send its mass in grams, e.g. 500.");return;
  }
  float known=line.toFloat();
  if(!tared || known<50 || known>4000) { Serial.println("TARE first, then use a known mass between 50 and 4000 g.");return; }
  float factor=(scale.read_average(20)-scale.get_offset())/known;
  Serial.print("HX_UNITS_PER_GRAM = ");Serial.println(factor,6);
  Serial.println("Copy this signed value into esp32_gateway/config.h. Repeat with a second known mass.");
}
