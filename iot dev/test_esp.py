# test wifi

from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="ESP32 IoT Backend")


class SensorData(BaseModel):
    device_id: str
    distance_cm: float


@app.get("/")
def health_check():
    return {"status": "online", "message": "IoT server running"}


@app.post("/readings")
def receive_reading(data: SensorData):
    print(f"Device: {data.device_id}")
    print(f"Distance: {data.distance_cm} cm")

    return {
        "status": "received",
        "device_id": data.device_id,
        "timestamp": datetime.now().isoformat()
    }
