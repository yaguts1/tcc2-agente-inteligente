ESP32 SPIFFS / eventos.jsonl upload

Quick steps to copy `eventos.jsonl` into the ESP32 SPIFFS (Arduino IDE or PlatformIO)

Option A — PlatformIO (recommended)

1. Place the `eventos.jsonl` file in the project's `data/` or `data/spiffs/` folder as expected by your board's platformio.ini.
   Example: `firmware/esp32_replay/data/eventos.jsonl`.
2. In PlatformIO, ensure `board_build.filesystem = spiffs` (or use `uploadfs` plugin) and run:

```powershell
# from repo root
cd firmware/esp32_replay
pio run -t uploadfs
```

This writes SPIFFS contents to the device's flash filesystem.

Option B — Arduino IDE (using `ESP32 Sketch Data Upload` plugin)

1. Install the "ESP32FS" plugin for Arduino IDE (Tools > ESP32 Sketch Data Upload).
2. Create a `data/` folder next to your `.ino` file and copy `eventos.jsonl` into it.
3. Select the correct board and COM port, then use Tools > ESP32 Sketch Data Upload.

Option C — `esptool` + mkspiffs (advanced)

1. Use `mkspiffs` to build a SPIFFS image from a local folder containing `eventos.jsonl`.
2. Flash the image with `esptool.py --port <COM> write_flash <addr> image.bin`.

Firmware runtime tips

- To avoid triggering server rate-limit (server side token bucket per device): set `respeitarTimestamp = false` and use a conservative `delayEntrePacotesMs` (e.g., 500-1000ms).
- If you want to reproduce original timing across multiple hours/days, enable `respeitarTimestamp = true`, but ensure the parser produces correct full ISO timestamps (with Z or offset) and that device and server clocks are reasonably synchronized.
- Ensure the `cama_id` referenced in `eventos.jsonl` exists in the backend (or use `device->assignment` APIs) so replayed events resolve to a paciente_id and are fully processed.

How to test locally

1. Start the backend locally (example):

```powershell
python -m uvicorn interface.web:app --reload --host 127.0.0.1 --port 8000
```

2. Use the `tools/convert_for_firmware.py` script to prepare the `eventos.jsonl` if needed.
3. Upload SPIFFS and then open serial monitor at 115200 to watch logs and HTTP response codes from replay.

