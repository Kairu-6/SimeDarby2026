#pragma once
// Reference: classic NodeMCU-32S / ESP32-WROOM-32(E), bare parallel OV7670.
// Preserve your proven camera wiring by editing these values rather than rewiring blindly.
#ifdef SIMELOOP_COMPILE_TEST
constexpr bool HARDWARE_CONFIGURED = true;
#else
constexpr bool HARDWARE_CONFIGURED = false;
#endif
constexpr char WIFI_SSID[] = "YOUR_WIFI";
constexpr char WIFI_PASSWORD[] = "YOUR_PASSWORD";
constexpr char API_BASE[] = "http://192.168.1.100:8000";
constexpr char DEVICE_KEY[] = "hackathon-device-key-change-me";
constexpr char DEVICE_ID[] = "ELM-01";
constexpr int UART_RX = 17, UART_TX = 16; // Nano TX -> 1k/2k divider -> ESP RX
constexpr int HX_DOUT = 32, HX_SCK = 33;
#ifdef SIMELOOP_COMPILE_TEST
constexpr float HX_UNITS_PER_GRAM = 1; // compile-only; never upload this test build
#else
constexpr float HX_UNITS_PER_GRAM = 0; // signed calibration from known weights
#endif
constexpr float MIN_ITEM_G = 10, EMPTY_G = 5, STABILITY_RANGE_G = 5, MAX_ITEM_G = 4000;
constexpr char FRAME_BYTE_ORDER[] = "big"; // verify using a known colour card
constexpr int CAM_D0=34, CAM_D1=35, CAM_D2=36, CAM_D3=39;
constexpr int CAM_D4=18, CAM_D5=19, CAM_D6=21, CAM_D7=22;
constexpr int CAM_XCLK=27, CAM_PCLK=23, CAM_VSYNC=26, CAM_HREF=25;
constexpr int CAM_SDA=13, CAM_SCL=14;
