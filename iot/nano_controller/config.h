#pragma once
// Change only after bench-checking door travel and the continuous pusher's neutral pulse.
#ifdef SIMELOOP_COMPILE_TEST
constexpr bool HARDWARE_CONFIGURED = true;
#else
constexpr bool HARDWARE_CONFIGURED = false;
#endif
constexpr unsigned long UART_BAUD = 38400;
constexpr byte DOOR_PINS[3] = {3, 5, 6}; // food, recyclable, reject
constexpr byte PUSHER_PIN = 9;
constexpr byte TRIG_PINS[3] = {4, 7, 10};
constexpr byte ECHO_PINS[3] = {8, 11, 12};
constexpr int DOOR_CLOSED_US[3] = {1000, 1000, 1000};
constexpr int DOOR_OPEN_US[3] = {1800, 1800, 1800};
constexpr int PUSHER_NEUTRAL_US = 1500;
constexpr int PUSHER_FORWARD_US = 1620; // continuous-rotation speed, NOT an angle
constexpr unsigned long GATE_SETTLE_MS = 500;
constexpr unsigned long MAX_PUSH_MS = 3000;
constexpr unsigned long WATCHDOG_MS = 1200;
// 60 cm empty, 8 cm full, block at 90% -> 132 mm measured distance.
// Update together with backend per-compartment calibration.
constexpr long FULL_BLOCK_MM[3] = {132, 132, 132};
