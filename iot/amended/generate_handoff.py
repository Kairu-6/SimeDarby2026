"""Rebuild the two requested amended Markdown handoffs and source ZIP."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent


def document(title, intro, files, target):
    text = f"# {title}\n\n{intro}\n\nSee `iot/SMARTBIN_HANDOFF.md` for the exact API, wiring, kiosk flow and limits.\n\n"
    for file in files:
        text += f"## `{file}`\n\n```cpp\n{(ROOT / file).read_text(encoding='utf-8').rstrip()}\n```\n\n"
    (OUT / target).write_text(text.rstrip() + "\n", encoding="utf-8")


def main():
    document(
        "SmartBin ESP32 Firmware — amended 0.3",
        "Replaces the supplied integration sketch while preserving its actual camera/HX711/UART wiring. The proven custom camera driver was found in Desktop/Arduino/ESP32_I2S_Camera and copied unchanged into `iot/smartbin_esp32/src/camera/`. Use ESP32 Arduino core 2.0.17, ArduinoJson 7.x and HX711. The actual-driver build was compile-checked; physical capture/movement still needs hardware verification. Set real network/device credentials and calibration in config.h before enabling HARDWARE_CONFIGURED. Never flash a SIMELOOP_COMPILE_TEST build.\n\nThe station now starts from a category selection and single-use QR claim. The gateway captures only after Check my items, preserves the selected category, persists pending cycles, uses stable pre-push weight, and waits for the empty-tray / Nano completion evidence. A faulty or uncalibrated HX711 blocks movement and rewards. No mock image can actuate this gateway.\n\nThe complete source ZIP includes the camera driver's supporting files; copying only this Markdown's code blocks without the `src/camera/` folder is insufficient.",
        ["iot/smartbin_esp32/config.h", "iot/smartbin_esp32/camera_adapter.h", "iot/smartbin_esp32/smartbin_esp32.ino"],
        "SmartBin_ESP32_Firmware.md",
    )
    document(
        "SmartBin Arduino Nano Firmware — amended 0.3",
        "Matches the supplied current wiring: HC-SR04 pairs D2/D3, D4/D5, D6/D7; doors D8/D9/D10; continuous paddle D11; SoftwareSerial RX D12 and TX A0 at 9600. Bin 1=recyclable, bin 2=food, bin 3=reject. Nano A0 reaches ESP32 RX16 through the 1k/2k divider. Use the classic Nano/ATmega328P old-bootloader target where applicable and Servo.h. The sketch was compiled, not flashed or mechanically tested.\n\nAmendments: selected-door interlock, local full/stale-bin block, UUID duplicate handling, heartbeat watchdog, bounded input, filtered sonar readings and EMPTY-driven completion. The former timed success sequence is replaced: a maximum push duration now faults instead of awarding success. Calibrate pulses and geometry, then enable HARDWARE_CONFIGURED. Use only with the paired amended gateway/API; do not mix old and new controllers.\n\nNew incoming JSON messages are type=ping, type=sort with command_id/bin_id, and type=stop with the matching command_id and reason=empty. A generic stop faults the mechanism. Outgoing telemetry includes boot_id, actual controller state, commanded door mask, last completed UUID, distances and sample ages. All frames are newline-terminated JSON v1 envelopes.",
        ["iot/smartbin_nano/config.h", "iot/smartbin_nano/smartbin_nano.ino"],
        "SmartBin_Arduino_Nano_Firmware.md",
    )
    archive = OUT / "SmartBin_Firmware_0.3.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for folder in ("smartbin_esp32", "smartbin_nano", "smartbin_hx711"):
            for file in sorted((ROOT / "iot" / folder).rglob("*")):
                if file.is_file():
                    bundle.write(file, file.relative_to(ROOT / "iot"))
        for file in ("SmartBin_ESP32_Firmware.md", "SmartBin_Arduino_Nano_Firmware.md"):
            bundle.write(OUT / file, file)
        bundle.write(ROOT / "iot/SMARTBIN_HANDOFF.md", "SMARTBIN_HANDOFF.md")
        bundle.write(ROOT / "iot/station.example.json", "station.example.json")
        for name in ("wiring-overview.svg", "uart-and-power.svg", "wiring-overview.png", "uart-and-power.png"):
            bundle.write(ROOT / "iot/schematics" / name, "schematics/" + name)
    print("Created amended ESP32/Nano Markdown and source ZIP:", archive)


if __name__ == "__main__":
    main()
