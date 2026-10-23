#pragma once
// Keep your CURRENT working OV7670 wiring. This is not the earlier SL2 pin map.
#ifdef SIMELOOP_COMPILE_TEST
constexpr bool HARDWARE_CONFIGURED=true;
constexpr float HX_COUNTS_PER_GRAM=1;
#else
constexpr bool HARDWARE_CONFIGURED=false;
constexpr float HX_COUNTS_PER_GRAM=0; // Signed calibrated value; zero disables operation.
#endif
constexpr char WIFI_SSID[]="YOUR_WIFI", WIFI_PASSWORD[]="YOUR_PASSWORD";
constexpr char API_BASE[]="http://192.168.1.100:8000";
constexpr char DEVICE_KEY[]="CHANGE_TO_BACKEND_DEVICE_API_KEY";
constexpr char DEVICE_ID[]="esp32-01", STATION_ID[]="ELM-01";
constexpr int UART_RX=16,UART_TX=17,HX_DOUT=36,HX_SCK=13;
constexpr char RGB565_BYTE_ORDER[]="little"; // Verify against your actual decoded frame.
constexpr float EMPTY_G=5,MIN_G=10,MAX_G=4000,STABLE_RANGE_G=5;
constexpr unsigned long MAX_CYCLE_MS=12000;
