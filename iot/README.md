# Current hardware integration — SmartBin 0.3

**Use [the current handoff](SMARTBIN_HANDOFF.md) and [amended ESP32/Nano documents](amended/) for the latest build.** These match your supplied camera project, UART2 RX16/TX17, HX711 DOUT36/SCK13 and Nano SoftwareSerial D12/A0 at 9600. The source package is [SmartBin_Firmware_0.3.zip](amended/SmartBin_Firmware_0.3.zip).

The iPad now selects food or recycling and shows a single-use QR. The resident claims it in the app; camera mismatch keeps the internal door closed. The working custom camera driver was found in `Desktop/Arduino/ESP32_I2S_Camera` and copied unchanged into the amended ESP32 sketch.

## Legacy v2 reference below

The rest of this file describes the earlier SL2 / 38400-baud integration. Its endpoints remain supported for compatibility/tests, but **its firmware pin map is not your current wiring**. Do not mix these older controllers with the new pair. The wiring SVG/PNG files now show the current SmartBin 0.3 map.

This is the current design for your NodeMCU-style ESP32 + OV7670 + HX711, connected by UART to a Nano V3 controlling three SG90 doors, one continuous-rotation MG996R and three HC-SR04 sensors. The earlier two-bin controller is retired. Existing experiments under `iot dev/` are preserved.

Only the full destination is blocked. Food and recycling earn weight-based points; mixed household waste can use the reject bin for zero points. Unclear/unsafe-looking scenes return `hold`. The model runs on the Python server, not on the ESP32.

## Start here

- [Wiring, mechanism, parts and measurements needed](HARDWARE_DESIGN.md)
- [Wiring overview](schematics/wiring-overview.svg) / [PNG](schematics/wiring-overview.png)
- [UART voltage divider and power](schematics/uart-and-power.svg) / [PNG](schematics/uart-and-power.png)
- [HTTP endpoints and exact JSON data](DEVICE_API.md)
- [ESP32 ↔ Nano UART frames and state machine](UART_PROTOCOL.md)

## Firmware

| Sketch | Board / job |
| --- | --- |
| `hx711_calibration/hx711_calibration.ino` | ESP32: save empty tare and print signed units per gram using a known mass |
| `esp32_gateway/esp32_gateway.ino` | ESP32: camera, load cell, API, saved cycle receipts and UART heartbeat |
| `nano_controller/nano_controller.ino` | Nano: three sonars, three doors, continuous pusher and local watchdog |

The reference pin map assumes a classic NodeMCU-32S / ESP32-WROOM-32(E) and a bare parallel OV7670. Your linked board reference does not establish the camera breakout variant or existing pin wiring. Check those before connecting it. The ESP32 reference captures 160×120 RGB565 in RAM; actual camera initialization, colours and timing still need bench verification.

For the switchless continuous servo, the proposed mechanism is a rotary sweeping paddle on a circular inspection plate with three gated outlets. It stops at a stable empty-plate reading; it does not return to a known angle. See the mechanism discussion before building a linkage.

## Configure and flash

1. Inspect the wiring sheets. Use a regulated servo supply and common ground; Nano TX reaches ESP32 RX through the 1k/2k divider. Keep servo current out of the board regulators.
2. Run the calibration sketch with the empty plate, then a known mass. Save its signed factor in `esp32_gateway/config.h`. Do not tare with waste on the plate.
3. Set Wi-Fi, API LAN address, device key and verified camera pins/byte order in the gateway config. `ELM-01` is the seeded station. The default key is for a trusted local demo; set the same private `DEVICE_API_KEY` on the backend and gateway.
4. Measure each bin's empty/full distance. Edit `station.example.json` and apply it from `backend/` with `uv run python scripts/configure_station.py ../iot/station.example.json`. Set the matching Nano `FULL_BLOCK_MM` values.
5. Measure door open/close pulses and continuous-servo neutral/speed/time in `nano_controller/config.h`. Enable `HARDWARE_CONFIGURED` in both configs only after these checks. These guards default to false.
6. Compile/upload the two configured sketches. Disconnect the ESP32 UART wires and external Nano power while programming Nano by USB, then restore the run wiring. Power the servo branch last. Set backend `DEMO_MODE=false` for physical operation so app simulation controls are disabled and collections require actual sensor evidence.

Arduino dependencies: **esp32 by Espressif Systems 3.3.12**, **Arduino AVR Boards**, **ArduinoJson 7.4.3**, **HX711 Arduino Library by Bogdan Necula**, **Servo**. `esp_camera.h`, Wi-Fi, HTTPClient and Preferences come with the ESP32 core. Use NodeMCU-32S and classic Nano ATmega328P (old bootloader for the tested compile); select the actual clone's bootloader when uploading.

All three sketches were compile-checked. No physical board was flashed or mechanically verified. Local `.cache/arduino` builds using `SIMELOOP_COMPILE_TEST` only exercise otherwise guarded source; **never upload those compile-test binaries**. Normal uploads must use the calibrated configuration.

## What a deposit does

The resident scans `simeloop://bin/ELM-01` and creates an app session. The gateway sends all three levels, a stable calibrated tray weight and Nano status; it captures and uploads the current item. The backend returns a route or hold. Before moving, the gateway asks to arm a cycle, saves its ID and frozen weight, and commands the Nano over UART. Only the selected door opens, then the paddle runs. A stable empty tray stops it; the Nano commands the door closed and reports DONE. Fresh telemetry plus the matching completion receipt credits the frozen pre-push weight once.

The Nano independently blocks a full/stale destination and stops on heartbeat loss or push timeout. HX711 samples older than 500 ms cannot authorize empty detection. Restarting during a pending cycle causes fault handling rather than another push. A fault leaves the item for inspection and awards no points. A failed cycle latches the Nano fault; inspect/clear the mechanism, then restart the controller before another deposit.

Full-bin telemetry creates one cleaner task per compartment in the station's township. Real-mode collection completion requires a fresh valid below-full sensor reading. Native background push needs Expo credentials; in-app notifications and the cleaner queue work locally.

## Test without hardware

With the API running, from `backend/`:

```powershell
# Entirely simulated classification and weight (DEMO_MODE=true)
uv run python scripts/simulate_device.py --demo recyclable --weight 0.5

# Real model inference, simulated sensors and Nano receipts (no physical movement)
uv run python scripts/simulate_device.py --image path/to/waste.jpg --weight 0.5

# Simulate one full destination and a cleaner alert
uv run python scripts/simulate_device.py --full --compartment reject --bin ELM-01
```

The simulator changes the selected station's telemetry/history. Use a separate `DATABASE_PATH` if you want an isolated demonstration. Real inference requires the vision extra and downloaded CLIP model. `--image` simulates physical evidence; it is a contract tester, not proof of a real deposit.
