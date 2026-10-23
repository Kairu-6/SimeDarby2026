# IoT API v2: the data each board sends and receives

**Compatibility reference:** the current supplied JSON/UUID firmware uses [SmartBin 0.3](SMARTBIN_HANDOFF.md), including `/telemetry`, `/sorting/events` and the category-first QR claim. V2 endpoints below remain available to existing integrations/tests.

The API extends the existing app/backend; existing users, point balances, vouchers and history are retained by an additive SQLite migration. A station now contains `food`, `recyclable` and `reject` compartments. A full destination blocks only that destination, as requested. All three full means the station is unavailable.

## Responsibilities

| Part | Responsibility |
| --- | --- |
| Resident app | Sign in, scan the station QR, start/cancel a deposit, display points/history |
| ESP32 NodeMCU-32S reference | Wi-Fi, OV7670 capture, HX711 sampling, HTTP requests, UART orchestration |
| Nano V3 | Three HC-SR04 readings, three SG90 door commands, continuous MG996R start/stop, actuator watchdog |
| Python backend | Computer vision, calibration/levels, capacity checks, one-time cycle authorisation, weight-based points, cleaner alerts |

The HX711 is the weight amplifier/ADC; the 5 kg bar is the actual load cell. Mount it beneath the inspection plate, not beneath all three collection bins. We freeze the stable **pre-push** item weight, then use the **post-push** empty plate as a completion condition. The two weights have different jobs.

## HTTP endpoints

All device requests use `X-Device-Key`. The app uses its existing bearer token; never put the device key in the resident app.

| Method / path | Required input | Output / purpose |
| --- | --- | --- |
| `GET /api/device/bins/ELM-01/config` | Device key | Three geometries/thresholds, point rates, weight limits, UART settings, pusher mode |
| `POST /api/device/telemetry` | Complete packet below | Persist fresh levels, scale and Nano state; create area-scoped full-bin alerts |
| `GET /api/device/bins/ELM-01/session` | Device key | Active resident session and any existing physical cycle |
| `POST /camera/upload` | Raw RGB565, dimensions, byte order, checksum, session ID | Real image classification and `food` / `recyclable` / `reject` / `hold` |
| `POST /api/device/deposits/{id}/classify` | Multipart JPEG/PNG instead of raw frame | Same model decision attached to the session |
| `POST /api/device/deposits/{id}/arm` | Device ID, unique request ID, latest telemetry event ID | One physical cycle ID, destination, frozen weight, 15-second start lease |
| `POST /api/device/deposits/{id}/confirm` | Matching cycle/destination, frozen weight, unique completion event | Credit once after Nano DONE and stable empty tray |
| `POST /api/device/cycles/{id}/fault` | Device ID, event ID, reason | Cancel without points; stop/inspect rather than replay a push |

The old `/readings` and `/api/device/readings` accept all three compartment names for compatibility, but individual readings cannot replace the complete v2 readiness/weight/controller packet required to arm a real cycle. Legacy bare `/confirm` requests cannot credit a real deposit.

## Complete telemetry packet

```json
{
  "device_id": "ELM-01",
  "event_id": "ELM-01-boot123-0001",
  "boot_id": "boot123",
  "sequence_no": 1,
  "uptime_ms": 12000,
  "firmware_version": "2.0.0",
  "levels": [
    { "compartment": "food", "distance_cm": 48.1, "valid": true },
    { "compartment": "recyclable", "distance_cm": 39.2, "valid": true },
    { "compartment": "reject", "distance_cm": 52.0, "valid": true }
  ],
  "scale": { "weight_g": 500.0, "stable": true, "calibrated": true },
  "controller": {
    "ready": true,
    "state": "idle",
    "boot_id": "nano7ac9",
    "frame_age_ms": 50,
    "open_doors_mask": 0,
    "last_completed_cycle": null,
    "fault": null
  }
}
```

Send a no-echo reading as `{"compartment":"food","distance_cm":null,"valid":false}`. Never use zero distance to mean sensor failure; zero means genuinely full. All three names must appear exactly once. Firmware invalidates sonar samples older than one second. The server rejects modified duplicate event IDs and decreasing sequence numbers within a boot. It uses server receipt time rather than trusting an ESP32 clock.

`open_doors_mask` is a bitmask of the door positions **commanded** by the Nano: food=1, recyclable=2, reject=4; zero means all commanded closed. There are no position switches in the supplied design, so it is not proof of physical closure. `state` is `idle`, `opening`, `pushing`, `closing` or `fault`.

## Classification and routing

The model accepts clearly identified food or recyclables for their corresponding bins. Confident mixed household waste can route to `reject` for **zero points**. Low-confidence images, empty scenes, and unsafe-looking objects return `hold`; the pusher stays stopped. The zero-shot model is a prototype and needs validation with actual items in your enclosure.

For raw OV7670 frames, use `/camera/upload` with `X-Session-Id`, `X-Width`, `X-Height`, `X-Byte-Order`, `X-Capture-Id`, and `X-Frame-FNV1A`. The gateway reference uses 160×120 RGB565 (38,400 bytes). The byte order must match your proven camera setup. The existing image conversion API remains available.

## Arm before moving

```json
{
  "device_id": "ELM-01",
  "request_id": "ELM-01-boot123-arm-0002",
  "telemetry_event_id": "ELM-01-boot123-0001"
}
```

The server requires a recent real classification, a calibrated stable item on the plate, fresh telemetry, an idle/fault-free Nano, commanded-closed doors, and a valid below-full reading for the selected destination. Default accepted item weight is 10–4000 g. This is provisional headroom for the 5 kg cell; the physical gross mass includes the tray, so reduce the limit if the tray/fixtures use more than 1 kg.

An arming response contains `id` (16 hex characters), `route`, `weight_kg`, `execute_before`, `state` and `executable`. Save the ID and frozen weight before sending UART CYCLE. Start only while executable. Repeating the same arm request returns the same cycle rather than creating a second push. Reclassification/cancellation is blocked once armed; report a fault to end an unsuccessful cycle.

## Confirm after the Nano finishes

```json
{
  "device_id": "ELM-01",
  "cycle_id": "0123456789abcdef",
  "controller_cycle_id": "0123456789abcdef",
  "route": "food",
  "weight_kg": 0.5,
  "event_id": "ELM-01-boot123-complete-0003"
}
```

Before this request, send fresh telemetry with scale weight near zero/stable, Nano `idle`, `open_doors_mask:0`, and `last_completed_cycle` matching the command. Credit uses the frozen pre-push weight, not the empty reading. The submitted weight must match within the configured tolerance. Reuse the same completion event/weight on HTTP retry. A completed deposit returns its original result without double-crediting.

Current rates retain the app's existing point scheme: food 50 points/kg, recyclables 100 points/kg, reject 0. The server controls rates through environment settings. No MYR cash payout is implemented. If “price” means cash rather than reward points, the rate/currency and payout rules still need to be specified.

## Faults, outages and full bins

The Nano stops the motor on UART heartbeat loss or a maximum push duration, closes the commanded doors and reports a fault. Failed or unconfirmed cycles receive no points. An ESP32/Nano reboot during an unresolved cycle causes recovery/fault handling, never automatic replay of the pusher. A completed local cycle can wait for Wi-Fi to return before submitting its receipt; the 15-minute resident session still limits how long it can be credited automatically.

Cleaner tasks now include `reject_fill` and `compartment:reject`. In real mode, clearing requires a fresh valid below-threshold sensor reading; pressing the app button cannot make a physically full bin available. Demo mode keeps the existing simulated reset.

Apply measured per-bin geometry with:

```powershell
cd backend
uv run python scripts/configure_station.py ../iot/station.example.json
```

Replace example distances first. Also update the Nano's local `FULL_BLOCK_MM` thresholds. Formula: `empty_mm − threshold_fraction × (empty_mm − full_mm)`. The sample 600/80 mm geometry at 90% gives 132 mm. The computer-vision service, telemetry and controller all operate on station ID `ELM-01` by default.
