#error "Retired two-bin reference. Use ../esp32_gateway and ../nano_controller for IoT v2."
/* Sime Loop bin controller for a SEPARATE ESP32 DevKit, HX711, two servos,
 * and two ultrasonic sensors. Your existing ESP32 camera is a second board.
 * Set Wi-Fi/API details, your wiring, and calibrated grams/unit before use.
 * Libraries: ArduinoJson 7, ESP32Servo, HX711 (bogde).
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <HX711.h>

const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";
const char* API = "http://192.168.1.100:8000";
const char* DEVICE_KEY = "hackathon-device-key-change-me";
const char* BIN_ID = "ELM-01";

// Example DevKit wiring only. These are NOT ESP32-CAM pin assignments.
const int HX_DOUT = 32, HX_SCK = 33, ROUTE_PIN = 13, GATE_PIN = 14;
const int FOOD_TRIG = 25, FOOD_ECHO = 26, RECYCLE_TRIG = 27, RECYCLE_ECHO = 34;
const int GATE_CLOSED = 0, GATE_OPEN = 70, FOOD_ANGLE = 45, RECYCLE_ANGLE = 135;
// Set with known calibration weights. Leave zero until the scale is calibrated.
const float SCALE_UNITS_PER_GRAM = 0;

HX711 scale;
Servo routeServo, gateServo;
String activeSession, pendingEvent, blockedSession;
float baselineGrams = 0, lastDelta = 0, pendingKg = 0;
int stableSamples = 0;
bool routing = false, confirmationPending = false;
unsigned long routedAt = 0, lastTelemetry = 0, sequenceNumber = 0;
String bootId;

String eventId() { return String(BIN_ID) + "-" + bootId + "-" + String(++sequenceNumber); }

int callApi(const String& path, const String& body, JsonDocument& output, bool post = true) {
  HTTPClient http;
  http.setConnectTimeout(4000);
  http.setTimeout(8000);
  http.begin(String(API) + path);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.addHeader("Content-Type", "application/json");
  int status = post ? http.POST(body) : http.GET();
  String response = http.getString();
  if (status > 0) deserializeJson(output, response);
  http.end();
  return status;
}

float distanceCm(int trigger, int echo) {
  digitalWrite(trigger, LOW); delayMicroseconds(2);
  digitalWrite(trigger, HIGH); delayMicroseconds(10); digitalWrite(trigger, LOW);
  unsigned long pulse = pulseIn(echo, HIGH, 30000);
  return pulse == 0 ? -1 : pulse * 0.0343f / 2;
}

void sendLevel(const char* compartment, int trigger, int echo) {
  float distance = distanceCm(trigger, echo);
  if (distance < 0) return;  // A timed-out sensor must not report a full bin.
  JsonDocument body, response;
  body["device_id"] = BIN_ID;
  body["compartment"] = compartment;
  body["distance_cm"] = distance;
  body["event_id"] = eventId();
  String payload; serializeJson(body, payload);
  callApi("/api/device/readings", payload, response);
}

void setup() {
  Serial.begin(115200);
  bootId = String((uint32_t)esp_random(), HEX);
  routeServo.attach(ROUTE_PIN); gateServo.attach(GATE_PIN);
  gateServo.write(GATE_CLOSED);
  pinMode(FOOD_TRIG, OUTPUT); pinMode(FOOD_ECHO, INPUT);
  pinMode(RECYCLE_TRIG, OUTPUT); pinMode(RECYCLE_ECHO, INPUT);
  scale.begin(HX_DOUT, HX_SCK);
  if (SCALE_UNITS_PER_GRAM == 0) {
    Serial.println("Set SCALE_UNITS_PER_GRAM after calibrating the HX711 in grams.");
    while (true) delay(1000);
  }
  scale.set_scale(SCALE_UNITS_PER_GRAM);
  scale.tare(20);  // Load cell supports the receiving platform beneath both bins.
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) delay(500);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) { gateServo.write(GATE_CLOSED); delay(1000); return; }
  if (millis() - lastTelemetry > 15000) {
    sendLevel("food", FOOD_TRIG, FOOD_ECHO); delay(70);
    sendLevel("recyclable", RECYCLE_TRIG, RECYCLE_ECHO);
    lastTelemetry = millis();
  }
  if (confirmationPending) {
    JsonDocument body, response;
    body["event_id"] = pendingEvent; body["weight_kg"] = pendingKg;
    String payload; serializeJson(body, payload);
    int status = callApi("/api/device/deposits/" + activeSession + "/confirm", payload, response);
    if (status == 200 || (status >= 400 && status < 500)) {
      Serial.println(status == 200 ? "Points credited" : "Deposit was not credited; inspect API error");
      if (status != 200) blockedSession = activeSession;
      confirmationPending = false; activeSession = "";
    }
    delay(1000); return; // Retry the same event and measured weight after network failure.
  }
  JsonDocument response;
  if (callApi("/api/device/bins/" + String(BIN_ID) + "/session", "", response, false) != 200) { delay(1000); return; }
  JsonObject session = response["session"];
  if (session.isNull()) { gateServo.write(GATE_CLOSED); routing = false; activeSession = ""; delay(500); return; }
  String sid = session["id"].as<String>();
  if (sid == blockedSession) { gateServo.write(GATE_CLOSED); delay(500); return; }
  String status = session["status"].as<String>();
  String model = session["model"] | "";
  String category = session["category"] | "";
  if (status == "classified" && model != "demo-simulation" && (category == "food" || category == "recyclable")) {
    if (!routing || activeSession != sid) {
      if (!scale.is_ready()) { delay(500); return; }
      activeSession = sid; baselineGrams = scale.get_units(10);
      routeServo.write(category == "food" ? FOOD_ANGLE : RECYCLE_ANGLE);
      delay(600); gateServo.write(GATE_OPEN);
      stableSamples = 0; lastDelta = 0; routing = true; routedAt = millis();
    }
    if (scale.is_ready()) {
      float delta = scale.get_units(5) - baselineGrams;
      if (delta >= 5 && delta <= 20000 && abs(delta - lastDelta) < 3) stableSamples++;
      else stableSamples = 0;
      lastDelta = delta;
      if (stableSamples >= 4) {
        gateServo.write(GATE_CLOSED);
        pendingKg = delta / 1000.0f; pendingEvent = eventId();
        routing = false; confirmationPending = true;
      }
    }
    if (routing && millis() - routedAt > 30000) { gateServo.write(GATE_CLOSED); blockedSession = activeSession; routing = false; }
  } else { gateServo.write(GATE_CLOSED); routing = false; }
  delay(500);
}
