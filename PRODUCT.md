# Sime Loop

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Stack

Expo React Native with TypeScript for Android, iOS and web; Python FastAPI backend with SQLite and a local CLIP vision model. Expo and Python were explicitly requested. Other stack decisions are implementation choices.

## Users and purpose

Residents sort food waste and recyclable items before visiting a smart bin. A verified physical deposit awards points, which can be exchanged for vouchers at participating Sime Darby properties. Cleaners and guards receive alerts for full bins in their area and record collections.

## Confirmed capabilities

Dashboard with Malaysian bin locations and status; QR identification; rewards; earned/redeemed history; resident and township leaderboards; role-specific profiles; cleaner queue and schedule; image classification and IoT telemetry. Two ready-to-use test accounts.

The tablet kiosk selects food/recycling before issuing a short-lived, single-use server QR claim. A resident account claims a category-locked deposit, then a deliberate Check my items action requests the station camera. Mismatches stay held; only a verified matching category can authorize the selected door and paddle. Pre-push weight plus matching completion/empty evidence controls points. Current hardware uses the preserved custom OV7670 QVGA project and 9600-baud Nano JSON protocol.

## Brand commitments

Follow the six provided reference images: brand red #D71920, charcoal #292929, white cards, #F5F5F5 backgrounds, pale orange #FFF0E6, pale yellow #FFF5D6 and orange #F36F21. The sketches guide the page hierarchy and cleaner workflow.

## Evidence and open decisions

Existing RGB565 ESP32 upload and ultrasonic test scripts live in `iot dev/`. They are preserved. The three-bin reference uses an ESP32 NodeMCU-style board, OV7670 and HX711, with UART to a Nano controlling three doors, a continuous pusher and three sonars. Fullness blocks only the selected destination; reject deposits earn zero points. Firmware and wiring are supplied in `iot/`, with actual camera variant/pins, dimensions and calibration still to verify. Commercial merchant participation is unconfirmed; voucher offers and all seeded community data must be labelled as demo data. No measured environmental savings percentages are available. Vision is a zero-shot prototype requiring validation with real bin-camera images.
