# Preserved working camera driver

Copied unchanged from `C:/Users/user/Desktop/Arduino/ESP32_I2S_Camera` after the user identified that project. `source-hashes.json` records the SHA-256 hashes of the original `.h` / `.cpp` files. The original `.ino`, Wi-Fi settings and credentials are not copied.

This is the customized bitluni / igrr ESP32 I2S camera path used by the user's successful QVGA capture. Keep **Arduino ESP32 core 2.0.17**, its register configuration, frame chunk layout and XCLK timing. Do not replace it with an arbitrary similarly named `OV7670.h` library or compile it with a different core without a deliberate port and hardware revalidation. Upstream attribution comments remain in the source files.

Only `camera_adapter.h` selects the existing constructor/pins, performs the warm-up and checks frame completion/integrity. The gateway streams the eight existing 19,200-byte chunks rather than allocating another 153,600-byte frame.
