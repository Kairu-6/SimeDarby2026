# Verification — 23 October 2026

## Current kiosk and firmware 0.3

The current release adds the iPad kiosk, server-issued category-locked QR claims, and the supplied ESP32/Nano protocol. The earlier v2 results below remain a historical record.

| Check | Result |
| --- | --- |
| Backend integration suite | 41 passed, including 7 kiosk/protocol tests |
| Pages API proxy | 5 Node tests passed |
| Ruff lint/format and TypeScript | Passed |
| Resident and kiosk web exports | Both passed; separate Pages upload directories prepared |
| Android and iOS Hermes exports | Both passed |
| Current ESP32 with actual Desktop Arduino camera driver | Compiled using ESP32 core 2.0.17: 941,845 bytes flash / 47,512 bytes global RAM |
| Current Nano controller | Compiled: 11,446 bytes flash / 988 bytes global RAM |
| Current HX711 calibration sketch | Compiled: 280,173 bytes flash / 21,456 bytes global RAM |
| Kiosk layouts | Inspected at 1280 × 800, 1024 × 768, and 390 × 844 |
| Current wiring | SVG and PNG generated and visually inspected |

Browser verification used the isolated sample database: food choice → unique QR → resident sign-in and claim → wrong-category warning with no movement → simulated matching classification → simulated 500 g completion → 25 points reflected on kiosk and resident app. This is a software simulation, not a hardware acceptance test. Its sample resident balance changed from 1,240 to 1,265; the original database was not used for this check.

Protocol tests cover QR rotation, expiry, ownership, pairing, category mismatch, fresh check requests, capture/event replay protection, unhealthy scale holds, and exactly-once credit after a matching controller completion plus a stable empty plate. Elapsed motor time alone does not award points.

Temporary preview: `https://mls-class-difficulty-usc.trycloudflare.com/` and `/kiosk`. It depends on this laptop and tunnel remaining online. The preview exposes only compiled web assets and demo APIs; device routes are disabled. Cloudflare Pages builds and Wrangler deployment scripts are ready, but Pages has not been published because the saved Cloudflare authentication is expired.

Capture evidence is in `.impeccable/review/` (gitignored). The phone image shows the top viewport of the scrollable kiosk. The real camera driver was copied without the original sketch's network credentials; its source hashes are recorded. Neither board was flashed or bench-tested. Scale calibration, servo direction/neutral/angles, UART reliability with servo interrupts, sonar thresholds, and actual waste classification accuracy still require physical validation. CLIP is a prototype classifier, not proof that every visible or hidden contaminant is detected.

## Earlier app and IoT v2 verification

Verified locally on Windows with Node 22.14, Python 3.14, Expo SDK 58 and React Native 0.88.

| Check | Result |
| --- | --- |
| Backend integration suite | 34 tests passed, including IoT v2 and push regressions |
| Ruff lint and formatting | Passed |
| uv lock consistency | Passed |
| TypeScript 6 type check | Passed |
| Expo dependency compatibility | Up to date |
| Web production export | Passed |
| Android and iOS Hermes bundle export | Both passed, approximately 3 MB each |
| Browser layout | Inspected at desktop and 390 × 844 phone width; corrected card overflow |
| Real computer vision | CLIP downloaded, loaded and invoked through the HTTP photo endpoint |
| ESP32 gateway, full guarded code enabled for compile | Passed, 1,151,309 bytes flash / 61,024 bytes global RAM |
| Nano controller, full guarded code enabled for compile | Passed, 8,574 bytes flash / 603 bytes global RAM |
| ESP32 HX711 calibration sketch | Passed, 288,656 bytes flash / 22,172 bytes global RAM |
| Wiring diagrams | Both SVGs rendered to PNG and visually checked |

The real image check used the existing camera capture at `iot dev/captures/latest.png`. It returned `accepted: false`, `route: hold`, `model: openai/clip-vit-base-patch32`. This verifies the actual inference path, not a waste classification benchmark.

Browser actions verified both accounts: resident deposit → 50-point credit → 300-point redemption → voucher QR/code → matching earned/redeemed history; township rankings; cleaner task acknowledgement → collection completion → compartment reset; simulated 95% sensor reading → fresh area-scoped task and notification. The simulated Elmina Lakeside collection was completed so the station is available again. This activity remains in the local demo database; a fresh database starts from the seed balances and tasks.

Saved previews are in `artifacts/resident-desktop.png`, `artifacts/cleaner-desktop.png` and `artifacts/cleaner-mobile.png` (gitignored). The browser is left signed in as the resident.

The IoT v2 suite verifies independent reject-bin fullness/alerts, zero-point reject deposits, stable/fresh/calibrated arm guards, invalid sonar/controller rejection, matching frozen-weight/cycle receipts, duplicates, fault handling, holding unclear items, fresh sensor evidence for real collections, and additive migration preserving balances/history. A new full reading after an authorized push does not erase that completed deposit's credit. Real-mode collection resolution preserves the measured fill value rather than inventing zero.

After migration, the existing resident's 990-point balance was retained and the live API exposed all three compartments. The updated model was invoked again with the existing camera capture; it returned hold at a 0.4977 top group score. No labelled camera benchmark was performed.

The web/native export and browser layout checks above were done for the initial app build; IoT v2's small app changes were checked with TypeScript. Firmware compilation used ESP32 core 3.3.12 and the classic Nano old-bootloader target. Compile-test configurations enable full code with placeholder calibration and must never be flashed. Normal hardware configurations default to disabled pending calibration.

Native binaries were not installed on a phone/emulator. Firmware was compiled but not flashed or bench-tested. Expo push delivery was tested with a mocked provider; live background push requires project credentials. Docker files and CI definitions are supplied but were not executed on this machine. No real merchant voucher or external remote notification was issued.
