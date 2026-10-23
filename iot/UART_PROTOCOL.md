# SL2 UART protocol

Hardware UART: 38400 baud, 8 data bits, no parity, 1 stop bit; common ground. ESP32 UART2 TX16/RX17 connects to Nano D0/D1. Nano TX must pass through the divider in the wiring sheet.

Every frame is an ASCII line ending `\n`, with optional `\r` ignored. The Nano uses a bounded 96-byte buffer and discards an oversized line. Fields have no spaces. This avoids dynamic JSON allocation on the Nano's 2 KB RAM. Device keys and resident identity stay on the ESP32/backend, not the UART.

## ESP32 to Nano

```text
SL2 PING
SL2 CYCLE 0123456789abcdef F
SL2 STOP 0123456789abcdef EMPTY
SL2 ABORT
```

- PING every 250 ms, from the independent UART task even while HTTP inference is running.
- CYCLE uses the server's 16-character hex ID and a destination: F food, R recyclable, X reject.
- STOP ... EMPTY is sent only while the matching pusher cycle is running and the HX711 has a stable near-zero plate reading for a further 400 ms. It means stop the continuous motor and command the selected door closed.
- ABORT immediately commands motor neutral/doors closed and enters a fault. Inspect and power-cycle the controller after resolving the cause; there is no remote automatic fault reset.

## Nano to ESP32

```text
SL2 ACK 0123456789abcdef
SL2 RUN 0123456789abcdef
SL2 DONE 0123456789abcdef
SL2 BUSY 0123456789abcdef
SL2 FAULT 0123456789abcdef PUSH_TIMEOUT
SL2 T 7ac9 12000 I 0 0123456789abcdef -
SL2 L 481 392 520 120 200 40
```

T fields: Nano boot ID, uptime ms, state code, commanded-open-door bitmask, last completed cycle or `-`, fault or `-`. States are I idle, O opening, P pushing, C closing and F fault. Bitmask food=1, recycle=2, reject=4. These are commanded positions, not physical door feedback.

L fields: food/recycle/reject distances in **millimetres**, followed by the age of each sample in ms. `-1` means invalid. The Nano staggers the three sonar triggers and uses a rolling three-sample median; the ESP32 marks old samples invalid rather than reporting an empty/full value.

## Local sequence

1. Receive a new authorised CYCLE while idle with a fresh selected sonar reading below its local fullness threshold.
2. Command every door closed, then open only the selected SG90; wait the configured settling time.
3. Emit RUN and command the continuous pusher's calibrated forward pulse.
4. Stop when the matching EMPTY arrives. If it does not arrive within the maximum run time, fault and stop.
5. Command the selected door closed, wait for settling and emit DONE. Credit is still a backend decision after fresh empty-plate telemetry.

Duplicate CYCLE for the current ID returns ACK without restarting the timer. A duplicate of the last completed ID returns DONE without moving again. A different ID during an active cycle returns BUSY. The ESP32 uses boot IDs plus persisted pending-cycle data to avoid replay after a board reset. Nano RAM alone does not preserve a completed ID across power loss.

The Nano watchdog is 1200 ms without a PING during a physical cycle. Sonar measurement is limited to 12 ms and is suspended while actuating; there is no network code or long blocking pusher delay on the Nano. Maximum push time is provisionally 3000 ms. Calibrate it with the actual mechanism; it is a fault timeout, not a way to infer pusher position.
