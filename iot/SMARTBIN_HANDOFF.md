# Current SmartBin handoff — 0.3

This is the current integration. It replaces the earlier SL2 pin map with the wiring and 9600-baud JSON protocol supplied in the two latest firmware documents. The original attachments and the working project in `Desktop/Arduino/ESP32_I2S_Camera` were not edited.

## The resident flow

1. The iPad kiosk offers **Recyclables** and **Food waste**. A full destination disables only its own button.
2. Selecting a category reserves that destination and requests a new 256-bit random claim key from the backend. The QR links to the resident web app. Its key expires after 180 seconds and is stored hashed on the server.
3. The signed-in resident claims the QR once. A database deposit row links their account, station and selected category. Another resident cannot claim that same key. The deposit lasts 15 minutes.
4. The resident places a clearly visible item or single visible layer on the inspection plate, then presses **Check my items** on the kiosk. Selection alone does not open an internal bin door; otherwise the camera could not block contamination.
5. The ESP32 polls the active session and captures only when `capture_requested=1`. It sends a complete raw QVGA frame, session ID and fresh calibrated weight/controller telemetry.
6. Python vision compares the contents to the category selected at the kiosk. A mismatch or uncertain/unsafe-looking image is held: the screen/app explain the issue and no sort command is returned. The user removes the offending item and requests another check.
7. A matching classification plus healthy stable scale, fresh Nano state and available destination authorizes one server UUID. Only that destination door opens. The paddle runs until the HX711 reports a stable empty tray; then the Nano stops and commands the door closed.
8. Points use the stable **pre-push** weight. Credit requires a matching Nano completion event **and** fresh stable-empty telemetry with the same command ID and idle/commanded-closed doors. Duplicate frames/events cannot create another reward.

The third bin remains **reject**. It is monitored and can alert cleaners, but is not a public kiosk choice and is not an automatic escape route for a wrong-category deposit. Existing explicit reject/demo paths remain zero-point flows.

## Current wiring and category mapping

| Physical destination | Category | Nano door | HC-SR04 TRIG / ECHO |
| --- | --- | --- | --- |
| `bin_1` | Recyclable | D8 | D2 / D3 |
| `bin_2` | Food | D9 | D4 / D5 |
| `bin_3` | Reject | D10 | D6 / D7 |
| Paddle | Continuous MG996R | D11 | — |

ESP32 TX17 → Nano D12; Nano A0 TX → **1k/2k divider** → ESP32 RX16. All grounds join. The Nano uses SoftwareSerial at 9600; D0/D1 remain available for USB debugging.

HX711 DOUT=GPIO36/VP, SCK=GPIO13. Load cell supports the inspection plate. Camera D0–D7=5,18,19,21,33,32,34,35; XCLK4, PCLK22, VSYNC25, HREF23, SDA26, SCL27. Preserve the proven camera wiring and driver timing. Power camera/HX711 according to their module specifications; motor current goes through a separate suitable supply.

[Current wiring sheet](schematics/wiring-overview.svg) · [UART divider / power](schematics/uart-and-power.svg). The earlier hardware design and SL2 sketches are legacy references; do not combine their GPIO map with this build.

## Files to use

- `smartbin_esp32/`: gateway, settings, camera adapter and the copied working driver under `src/camera/`.
- `smartbin_nano/`: amended Nano controller and settings, matching the current D2–D12/A0 wiring.
- `smartbin_hx711/`: diagnostics/calibration on DOUT36/SCK13; saves the empty offset in the same `smartbinv3` NVS namespace.
- `amended/SmartBin_ESP32_Firmware.md` and `amended/SmartBin_Arduino_Nano_Firmware.md`: replacement handoff documents with complete amended integration sketches/settings.
- `amended/SmartBin_Firmware_0.3.zip`: source package including both controllers, calibration, the working camera driver and the handoff files. No sample Wi-Fi password, private device key or test binary is included.

Use the two amended sketches as a pair. The original timed Nano sketch does not implement the new empty-tray completion condition and must not be paired with the amended gateway.

## Firmware setup

1. Keep **ESP32 Arduino core 2.0.17** for the custom I2S driver found on this computer. The driver copies and their original SHA-256 hashes are in `smartbin_esp32/src/camera/`. The original driver files were copied byte-for-byte; only the adapter/integration is new.
2. Install ArduinoJson **7.x**, HX711 by Bogdan Necula, and Servo for the Nano. The gateway was updated to v7 APIs; the supplied document's v6-only dependency instructions are superseded.
3. Run `smartbin_hx711`: `raw` diagnoses counts, `TARE` saves the empty offset, then a known mass in grams prints a signed factor. Raw zero is treated as unhealthy, never zero grams. Copy the measured factor into the gateway config. Verify a second mass.
4. Set network/API/device-key values in `smartbin_esp32/config.h`. `DEVICE_ID=esp32-01` maps to station `ELM-01`. Use the private/LAN Python address for hardware. The public Pages proxy does not forward hardware endpoints.
5. Measure all three empty/full distances; apply `station.example.json` using `backend/scripts/configure_station.py`. Update Nano `FULL_BLOCK_MM` in **bin_1 recyclable / bin_2 food / bin_3 reject** order.
6. Calibrate each SG90's safe open/closed pulses and the continuous servo's real neutral/forward pulses and sweep timeout. A continuous servo has no known absolute angle. Confirm that the actual paddle mechanism can operate without needing a sensed home position.
7. Enable `HARDWARE_CONFIGURED` in both configs only after checking the assembly. Flash the paired sketches using the actual board/port. No hardware was flashed during this integration.
8. Warm the real model with the existing backend setup, set `DEMO_MODE=false`, and set different `DEVICE_API_KEY` / `KIOSK_API_KEY` values. Pair the iPad in Connection settings. The scale is mandatory for real movement and points, even though the previous standalone camera document treated it as optional.

The independent UART/HX711 task is pinned away from the custom camera's core. Model HTTP latency cannot starve its heartbeat. Nano faults on missing heartbeats or a maximum push duration; time expiry is never success. Pending gateway cycles/events are saved before action/submission, and a reboot of an unresolved cycle causes a stop/fault rather than a replay. USB `x` requests a software stop; physical motor-power disconnection remains necessary for an uncontrolled mechanism.

## Device API

Every hardware call requires `X-Device-Key`. Raw frames also use `X-Device-ID: esp32-01`, `X-Session-Id`, `X-Capture-ID`, dimensions, byte order and FNV-1a checksum. The key is a private device credential, not the resident QR claim key.

| Endpoint | Data |
| --- | --- |
| `GET /api/device/bins/ELM-01/session` | Claimed deposit, `selected_category`, `capture_requested`, and any existing cycle |
| `POST /telemetry` | Existing `ultrasonic` / `weight` shape, plus event/boot/sequence IDs, stable/healthy scale, sample ages, fresh Nano state and last completed UUID |
| `POST /camera/upload` | Exactly 153,600 QVGA RGB565 bytes; returns nested `classification` and `decision` matching the supplied firmware's envelope |
| `POST /sorting/events` | Stable UUID event ID, command UUID, accepted/started/completed/failed status, fixed event uptime and optional fault |
| `GET /api/device/cycles/{uuid}` | Final server state and points, allowing receipt recovery without moving again |
| `POST /api/device/cycles/{uuid}/fault` | Cancel an unresolved cycle without points |

Example telemetry:

```json
{
  "device_id": "esp32-01", "event_id": "esp-boot-3-0001", "boot_id": "esp-boot-3",
  "sequence_no": 1, "device_uptime_ms": 12000,
  "nano_connected": true, "nano_boot_id": "nano7ac9", "nano_frame_age_ms": 50,
  "actuator_state": "idle", "open_doors_mask": 0,
  "last_completed_command": null, "error_code": null,
  "ultrasonic": [
    {"sensor_id":"ultrasonic_1","bin_id":"bin_1","distance_cm":55,"valid":true,"sample_age_ms":100},
    {"sensor_id":"ultrasonic_2","bin_id":"bin_2","distance_cm":52,"valid":true,"sample_age_ms":180},
    {"sensor_id":"ultrasonic_3","bin_id":"bin_3","distance_cm":null,"valid":false,"sample_age_ms":3000}
  ],
  "weight": {"raw":123456,"weight_g":500,"healthy":true,"calibrated":true,"stable":true,"scope":"inspection_plate"}
}
```

`open_doors_mask` uses category bits food=1, recyclable=2, reject=4, irrespective of physical bin numbering. It describes **commanded** positions, not physical switches. Failed sonar readings remain invalid; the previous full reading is not cleared by a missing echo.

The camera response retains the existing flat classifier fields for diagnostics and adds:

```json
{
  "classification":{"label":"food","confidence":0.95,"mode":"real","model_version":"openai/clip-vit-base-patch32"},
  "decision":{"action":"sort","bin_id":"bin_2","command_id":"aed59836-c48c-47da-baf0-7ec4db5d947b","weight_kg":0.5,"execute_before":"SERVER_ISO_TIMESTAMP","reason":null}
}
```

HOLD returns null command/bin IDs and a reason. Same capture ID and identical bytes return the same command while it is executable. Reusing the capture ID with different bytes/session is rejected. Expired/final commands return HOLD on replay. The gateway conservatively refuses a command if the whole capture response round trip could have exhausted its 15-second start lease; warm the model before a physical demonstration.

## Kiosk and app API

`GET /api/kiosk/stations/ELM-01` returns public station capacity, sample/first-name leaderboard and point rates. `POST /api/kiosk/stations/ELM-01/offers` selects a category and returns the fresh QR. `POST /api/kiosk/claim` requires the signed-in resident bearer token and claim key. The tablet polls `/api/kiosk/offers/{id}` and calls its `/check` or `/cancel` action. Real kiosk calls require the tablet's `X-Kiosk-Key`; no device key is embedded in either web build.

The existing app's dashboard, rewards, history, leaderboards and cleaner views remain in place. Both screen and app show mismatch feedback. Real collections require fresh below-full sensor evidence. The temporary public preview uses an isolated sample database, disables hardware endpoints and labels simulation controls.

## Rates and limits

Defaults: food 50 points/kg; recyclable 100 points/kg; reject 0. Weigh before pushing and subtract the saved empty tare. Provisionally accept 10–4000 g items on the 5 kg cell; gross tray/fixture mass must fit within the remaining headroom. Configure actual rates/limits on the backend and match firmware limits.

## What still needs physical verification

The custom driver integration and controller code compile, but no assembled hardware test was performed. Verify camera colours/framing, scale repeatability, all sonar geometries, servo travel/neutral, watchdog/timeout behaviour, power under load and the paddle/chute mechanism. There are no position, arrival or hand-presence interlocks in the supplied parts. Stable empty weight plus controller commands is completion evidence, not proof of correct chute arrival.

CLIP is a real local zero-shot model, not a trained contamination detector. Prompts include mixed food/packaging and selected-category mismatch is enforced, but a single image cannot guarantee that every small, hidden or occluded contaminant is found. Use one visible item/layer and evaluate labelled captures in the actual enclosure before claiming sorting accuracy. Mechanical guarding must not depend on the vision model.

For web hosting and pending Cloudflare Pages authentication, see [deployment instructions](../deploy/pages/README.md).
