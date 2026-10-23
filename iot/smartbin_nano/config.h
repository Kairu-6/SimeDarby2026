#pragma once
// Matches the user's CURRENT wiring. Bin 1=recyclable, bin 2=food, bin 3=reject.
#ifdef SIMELOOP_COMPILE_TEST
constexpr bool HARDWARE_CONFIGURED = true;
#else
constexpr bool HARDWARE_CONFIGURED = false;
#endif
constexpr byte TRIG_PINS[3]={2,4,6}, ECHO_PINS[3]={3,5,7};
constexpr byte DOOR_PINS[3]={8,9,10}, PADDLE_PIN=11;
constexpr byte ESP_RX=12, ESP_TX=A0;
constexpr int DOOR_CLOSED_US[3]={1100,1100,1100}, DOOR_OPEN_US[3]={1900,1900,1900};
constexpr int PADDLE_STOP_US=1500, PADDLE_PUSH_US=1700;
constexpr unsigned long GATE_MS=700, MAX_PUSH_MS=4000, LINK_TIMEOUT_MS=3000;
// empty=600 mm, full=80 mm, threshold=90% -> 132 mm. Replace with measured values.
constexpr long FULL_BLOCK_MM[3]={132,132,132};
