import uuid

from app.config import settings
from app.db import connect
from tests.test_flows import auth

DEVICE = {"X-Device-Key": "hackathon-device-key-change-me", "X-Device-ID": "esp32-01"}


def offer(client, category="food"):
    r = client.post("/api/kiosk/stations/ELM-01/offers", json={"category": category})
    assert r.status_code == 200, r.text
    return r.json()


def claim(client, o):
    h = auth(client)
    r = client.post("/api/kiosk/claim", headers=h, json={"key": o["claim_key"]})
    assert r.status_code == 200, r.text
    return r.json(), h


def packet(seq=1, grams=500, done=None, healthy=True):
    return {
        "device_id": "esp32-01",
        "event_id": f"smartbin-telemetry-{seq}",
        "boot_id": "esp-boot-3",
        "sequence_no": seq,
        "device_uptime_ms": seq * 1000,
        "nano_connected": True,
        "nano_boot_id": "nano-boot-3",
        "nano_frame_age_ms": 50,
        "actuator_state": "idle",
        "open_doors_mask": 0,
        "last_completed_command": done,
        "ultrasonic": [
            {
                "sensor_id": "ultrasonic_" + str(i),
                "bin_id": "bin_" + str(i),
                "distance_cm": 55,
                "valid": True,
                "sample_age_ms": 100,
            }
            for i in range(1, 4)
        ],
        "weight": {
            "raw": 123456 if healthy else 0,
            "weight_g": grams if healthy else None,
            "healthy": healthy,
            "calibrated": healthy,
            "stable": healthy,
            "scope": "inspection_plate",
        },
    }


def capture(client, o, d, monkeypatch, category="food", capture_id="capture-unique-001"):
    from app.vision import classifier

    monkeypatch.setattr(
        classifier,
        "classify",
        lambda image: {
            "category": category,
            "accepted": True,
            "route": category,
            "material": "test item",
            "confidence": 0.95,
            "model": "test-real-model",
            "is_demo": False,
            "message": "Test classification.",
        },
    )
    return client.post(
        "/camera/upload",
        headers={
            **DEVICE,
            "X-Session-Id": d["id"],
            "X-Capture-ID": capture_id,
            "X-Width": "16",
            "X-Height": "16",
            "X-Byte-Order": "little",
        },
        content=b"\x00\xf8" * 256,
    )


def test_screen_claim_is_single_use_and_locks_category(client):
    o = offer(client)
    assert "claim=" in o["claim_url"] and len(o["claim_key"]) >= 32
    d, h = claim(client, o)
    assert d["selected_category"] == "food"
    assert (
        client.post("/api/kiosk/claim", headers=h, json={"key": o["claim_key"]}).json()["id"]
        == d["id"]
    )
    cleaner = auth(client, "cleaner")
    assert (
        client.post("/api/kiosk/claim", headers=cleaner, json={"key": o["claim_key"]}).status_code
        == 403
    )
    with connect() as db:
        db.execute(
            "INSERT INTO tokens VALUES ('second-resident-token','resident-2','2099-01-01T00:00:00+00:00')"
        )
    assert (
        client.post(
            "/api/kiosk/claim",
            headers={"Authorization": "Bearer second-resident-token"},
            json={"key": o["claim_key"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/kiosk/stations/ELM-01/offers", json={"category": "recyclable"}
        ).status_code
        == 409
    )
    mismatch = client.post(
        f"/api/demo/deposits/{d['id']}/classify", headers=h, json={"category": "recyclable"}
    ).json()
    assert not mismatch["accepted"] and mismatch["route"] == "hold"
    assert client.get(f"/api/deposits/{d['id']}", headers=h).json()["status"] == "pending"


def test_qr_rotation_expiry_and_public_privacy(client):
    first = offer(client)
    second = offer(client, "recyclable")
    assert first["claim_key"] != second["claim_key"]
    h = auth(client)
    assert (
        client.post("/api/kiosk/claim", headers=h, json={"key": first["claim_key"]}).status_code
        == 409
    )
    with connect() as db:
        db.execute(
            "UPDATE kiosk_offers SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (second["id"],),
        )
    assert (
        client.post("/api/kiosk/claim", headers=h, json={"key": second["claim_key"]}).status_code
        == 409
    )
    public = client.get("/api/kiosk/stations/ELM-01").json()
    assert set(public["compartments"]) == {"food", "recyclable", "reject"}
    assert all("email" not in r and "id" not in r for r in public["leaderboard"])
    assert "key_hash" not in client.get(f"/api/kiosk/offers/{first['id']}").json()


def test_pairing_required_outside_demo(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    assert (
        client.post("/api/kiosk/stations/ELM-01/offers", json={"category": "food"}).status_code
        == 401
    )
    monkeypatch.setattr(settings, "kiosk_api_key", "test-kiosk-secret")
    assert (
        client.post(
            "/api/kiosk/stations/ELM-01/offers",
            headers={"X-Kiosk-Key": "test-kiosk-secret"},
            json={"category": "food"},
        ).status_code
        == 200
    )


def test_smartbin_mismatch_never_opens_or_credits(client, monkeypatch):
    o = offer(client)
    d, h = claim(client, o)
    client.post(f"/api/kiosk/offers/{o['id']}/check", json={})
    client.post("/telemetry", headers=DEVICE, json=packet())
    response = capture(client, o, d, monkeypatch, category="recyclable")
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["action"] == "hold"
    assert response.json()["decision"]["command_id"] is None
    assert "does not match" in response.json()["message"]
    assert client.get("/api/me", headers=h).json()["points"] == 1240
    with connect() as db:
        assert db.execute("SELECT count(*) FROM device_cycles").fetchone()[0] == 0


def test_uuid_sort_only_credits_after_done_and_empty(client, monkeypatch):
    o = offer(client)
    d, h = claim(client, o)
    assert client.post(f"/api/kiosk/offers/{o['id']}/check", json={}).status_code == 200
    assert client.post("/telemetry", headers=DEVICE, json=packet()).status_code == 200
    response = capture(client, o, d, monkeypatch)
    assert response.status_code == 200, response.text
    command = response.json()["decision"]
    assert command["action"] == "sort" and command["bin_id"] == "bin_2"
    cid = command["command_id"]
    assert str(uuid.UUID(cid)) == cid
    assert capture(client, o, d, monkeypatch).json()["decision"]["command_id"] == cid
    event = {
        "event_id": str(uuid.uuid4()),
        "device_id": "esp32-01",
        "command_id": cid,
        "status": "completed",
        "device_uptime_ms": 8000,
    }
    done = client.post("/sorting/events", headers=DEVICE, json=event)
    assert done.status_code == 200 and done.json()["awaiting_empty_plate"]
    assert client.get("/api/me", headers=h).json()["points"] == 1240
    credited = client.post("/telemetry", headers=DEVICE, json=packet(2, grams=0, done=cid))
    assert credited.status_code == 200, credited.text
    assert credited.json()["deposit"]["points"] == 25
    assert client.post("/sorting/events", headers=DEVICE, json=event).json()["duplicate"]
    assert client.get("/api/me", headers=h).json()["points"] == 1265
    assert capture(client, o, d, monkeypatch).json()["decision"]["action"] == "hold"


def test_unhealthy_scale_cannot_authorize_sort(client, monkeypatch):
    o = offer(client)
    d, _ = claim(client, o)
    client.post(f"/api/kiosk/offers/{o['id']}/check", json={})
    client.post("/telemetry", headers=DEVICE, json=packet(healthy=False))
    response = capture(client, o, d, monkeypatch)
    assert response.status_code == 200 and response.json()["decision"]["action"] == "hold"


def test_capture_requires_request_and_rejects_reused_frame_key(client, monkeypatch):
    o = offer(client)
    d, _ = claim(client, o)
    assert capture(client, o, d, monkeypatch).status_code == 409
    client.post(f"/api/kiosk/offers/{o['id']}/check", json={})
    client.post("/telemetry", headers=DEVICE, json=packet())
    assert capture(client, o, d, monkeypatch).status_code == 200
    changed = client.post(
        "/camera/upload",
        headers={
            **DEVICE,
            "X-Session-Id": d["id"],
            "X-Capture-ID": "capture-unique-001",
            "X-Width": "16",
            "X-Height": "16",
            "X-Byte-Order": "little",
        },
        content=b"\x01\xf8" * 256,
    )
    assert changed.status_code == 409
