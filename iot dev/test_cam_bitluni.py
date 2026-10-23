
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
from hashlib import sha256

import numpy as np
from PIL import Image, ImageFilter

app = FastAPI(title="ESP32 Smart Waste Bin API")

# ==========================================
# Storage
# ==========================================

CAPTURE_DIR = Path("captures")
CAPTURE_DIR.mkdir(exist_ok=True)

LATEST_IMAGE = CAPTURE_DIR / "latest.png"
RAW_CAPTURE_DIR = CAPTURE_DIR / "raw"
RAW_CAPTURE_DIR.mkdir(exist_ok=True)


def fnv1a(data: bytes) -> int:
    """Match the ESP32's 32-bit FNV-1a checksum exactly."""
    value = 2166136261
    for byte in data:
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


# ==========================================
# Health check
# ==========================================

@app.get("/")
def health_check():
    return {
        "status": "online",
        "message": "ESP32 IoT backend running"
    }


# ==========================================
# Sensor readings (previous endpoint)
# ==========================================

class SensorData(BaseModel):
    device_id: str
    distance_cm: float


@app.post("/readings")
def receive_reading(data: SensorData):
    print(f"Device: {data.device_id}")
    print(f"Distance: {data.distance_cm} cm")

    return {
        "status": "received",
        "device_id": data.device_id,
        "timestamp": datetime.now().isoformat()
    }


# ==========================================
# Camera upload
# ==========================================

@app.post("/camera/upload")
async def upload_camera(request: Request):

    # 1. Read image metadata from HTTP headers
    try:
        width = int(request.headers.get("x-width", "160"))
        height = int(request.headers.get("x-height", "120"))
    except ValueError:
        raise HTTPException(400, "Invalid dimensions")

    if not (1 <= width <= 320 and 1 <= height <= 240):
        raise HTTPException(400, "Unsupported dimensions")

    byte_order = request.headers.get(
        "x-byte-order", "little"
    ).lower()

    if byte_order not in ("little", "big"):
        raise HTTPException(400, "Invalid byte order")

    # 2. Receive raw RGB565 image bytes
    raw = await request.body()
    capture_id = request.headers.get("x-capture-id", "unknown")
    device_hash = request.headers.get("x-frame-fnv1a", "missing")

    expected_size = width * height * 2

    if len(raw) != expected_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid frame size: "
                f"expected {expected_size}, "
                f"received {len(raw)}"
            )
        )

    print("\n=== IMAGE RECEIVED ===")
    print(f"Resolution: {width}x{height}")
    print(f"Bytes: {len(raw)}")
    print(f"Byte order: {byte_order}")
    print(f"Capture ID: {capture_id}")
    print(f"ESP32 FNV-1a: {device_hash}")
    server_fnv = f"{fnv1a(raw):08X}"
    hash_match = device_hash.upper() == server_fnv
    print(f"Server FNV-1a: {server_fnv} ({'MATCH' if hash_match else 'MISMATCH'})")
    print(f"Server SHA-256: {sha256(raw).hexdigest()}")

    # Keep the exact bytes that arrived, so a clean and corrupt capture can
    # be compared without PNG conversion or later uploads overwriting it.
    safe_id = "".join(c for c in capture_id if c.isalnum() or c in "-_") or "unknown"
    raw_path = RAW_CAPTURE_DIR / f"capture_{safe_id}_{datetime.now():%Y%m%d_%H%M%S_%f}.rgb565"
    raw_path.write_bytes(raw)
    print(f"Saved raw frame: {raw_path.resolve()}")

    # 3. Interpret raw bytes as RGB565 pixels
    dtype = "<u2" if byte_order == "little" else ">u2"

    pixels = np.frombuffer(raw, dtype=dtype)
    pixels = pixels.reshape((height, width))

    # 4. Convert RGB565 to RGB888
    r5 = (pixels >> 11) & 0x1F
    g6 = (pixels >> 5) & 0x3F
    b5 = pixels & 0x1F

    r = (r5 << 3) | (r5 >> 2)
    g = (g6 << 2) | (g6 >> 4)
    b = (b5 << 3) | (b5 >> 2)

    rgb = np.stack(
        [r, g, b], axis=-1
    ).astype(np.uint8)

    # 5. Save the image as PNG
    
    image = Image.fromarray(rgb, "RGB")

    # Mild sharpening
    sharpened = image.filter(
        ImageFilter.UnsharpMask(
            radius=0.8,
            percent=50,
            threshold=3
        )
    )

    # Save original and enhanced images
    image.save(CAPTURE_DIR / "original.png")
    sharpened.save(LATEST_IMAGE)


    print(f"Saved: {LATEST_IMAGE.resolve()}")

    # Basic image variation diagnostic
    unique_pixels = np.unique(pixels).size
    print(f"Unique pixel values: {unique_pixels}")

    if unique_pixels <= 2:
        print("WARNING: Image appears nearly uniform")

    return {
        "status": "received",
        "width": width,
        "height": height,
        "bytes_received": len(raw),
        "transport_hash_match": hash_match,
        "unique_pixel_values": int(unique_pixels),
        "raw_frame": str(raw_path),
        "image_url": "/camera/latest",
        "timestamp": datetime.now().isoformat()
    }


# ==========================================
# Retrieve latest camera image
# ==========================================

@app.get("/camera/latest")
def get_latest_image():

    if not LATEST_IMAGE.exists():
        raise HTTPException(
            status_code=404,
            detail="No image uploaded yet"
        )

    return FileResponse(
        LATEST_IMAGE,
        media_type="image/png"
    )
