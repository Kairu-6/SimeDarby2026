import io
from datetime import UTC, datetime, timedelta

from PIL import Image

from app.config import settings
from app.db import connect, now
from tests.test_flows import auth

DEVICE = {"X-Device-Key": "hackathon-device-key-change-me"}


def packet(seq=1, weight=500, route="food", full=False, valid=True, done=None):
    return {
        "device_id": "ELM-01",
        "event_id": f"telemetry-event-{seq}",
        "boot_id": "esp-boot-1",
        "sequence_no": seq,
        "uptime_ms": seq * 1000,
        "firmware_version": "2.0.0",
        "levels": [
            {
                "compartment": c,
                "distance_cm": 9 if full and c == route else 55,
                "valid": valid if c == route else True,
            }
            for c in ("food", "recyclable", "reject")
        ],
        "scale": {"weight_g": weight, "stable": True, "calibrated": True},
        "controller": {
            "ready": True,
            "state": "idle",
            "boot_id": "nano-boot-1",
            "frame_age_ms": 50,
            "open_doors_mask": 0,
            "last_completed_cycle": done,
            "fault": None,
        },
    }


def classified(client, route="food"):
    headers = auth(client)
    sid = client.post("/api/deposits", headers=headers, json={"bin_id": "ELM-01"}).json()["id"]
    with connect() as db:
        db.execute(
            "UPDATE deposits SET status='classified',category=?,confidence=.95,material='test item',model='test-real-model',classified_at=? WHERE id=?",
            (route, now(), sid),
        )
    return sid, headers


def arm(client, sid, p):
    assert client.post("/api/device/telemetry", headers=DEVICE, json=p).status_code == 200
    return client.post(
        f"/api/device/deposits/{sid}/arm",
        headers=DEVICE,
        json={
            "device_id": "ELM-01",
            "request_id": "arm-request-001",
            "telemetry_event_id": p["event_id"],
        },
    )


def test_config_and_reject_capacity(client):
    assert client.get("/api/device/bins/ELM-01/config").status_code == 401
    cfg = client.get("/api/device/bins/ELM-01/config", headers=DEVICE).json()
    assert set(cfg["compartments"]) == {"food", "recyclable", "reject"}
    assert cfg["points_per_kg"]["reject"] == 0
    assert cfg["scale"]["max_item_kg"] == 4


def test_reject_sensor_alert_and_independent_lock(client):
    headers = auth(client)
    p = packet(route="reject", full=True)
    assert client.post("/api/device/telemetry", headers=DEVICE, json=p).status_code == 200
    bins = client.get("/api/bins", headers=headers).json()
    station = next(b for b in bins if b["id"] == "ELM-01")
    assert station["reject_fill"] > 90 and station["accepting_deposits"]
    sid = client.post("/api/deposits", headers=headers, json={"bin_id": "ELM-01"}).json()["id"]
    assert (
        client.post(
            f"/api/demo/deposits/{sid}/classify", headers=headers, json={"category": "reject"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/demo/deposits/{sid}/classify", headers=headers, json={"category": "food"}
        ).status_code
        == 200
    )
    tasks = client.get("/api/cleaner/tasks", headers=auth(client, "cleaner")).json()["tasks"]
    assert any(t["compartment"] == "reject" for t in tasks)


def test_mixed_waste_fallback_gets_zero_points(client):
    sid, headers = classified(client, "reject")
    assert (
        client.post(
            f"/api/demo/deposits/{sid}/classify", headers=headers, json={"category": "reject"}
        ).json()["route"]
        == "reject"
    )
    confirmed = client.post(
        f"/api/demo/deposits/{sid}/confirm",
        headers=headers,
        json={"weight_kg": 0.5, "event_id": "reject-complete-1"},
    )
    assert confirmed.status_code == 200 and confirmed.json()["points"] == 0
    assert client.get("/api/me", headers=headers).json()["points"] == 1240
    assert client.get("/api/history", headers=headers).json()[0]["type"] == "rejected"


def test_physical_cycle_and_idempotent_receipt(client):
    sid, headers = classified(client)
    p = packet()
    command = arm(client, sid, p)
    assert command.status_code == 200, command.text
    cid = command.json()["id"]
    repeat = client.post(
        f"/api/device/deposits/{sid}/arm",
        headers=DEVICE,
        json={
            "device_id": "ELM-01",
            "request_id": "arm-request-001",
            "telemetry_event_id": p["event_id"],
        },
    )
    assert repeat.json()["id"] == cid and repeat.json()["replayed"]
    assert client.post(f"/api/deposits/{sid}/cancel", headers=headers).status_code == 409
    receipt = {
        "weight_kg": 0.5,
        "event_id": "complete-cycle-001",
        "device_id": "ELM-01",
        "cycle_id": cid,
        "controller_cycle_id": cid,
        "route": "food",
    }
    assert (
        client.post(f"/api/device/deposits/{sid}/confirm", headers=DEVICE, json=receipt).status_code
        == 409
    )
    after = packet(2, weight=0, done=cid, full=True)
    assert client.post("/api/device/telemetry", headers=DEVICE, json=after).status_code == 200
    for tampered in ({"weight_kg": 0.9}, {"route": "reject"}, {"controller_cycle_id": "wrong"}):
        assert (
            client.post(
                f"/api/device/deposits/{sid}/confirm", headers=DEVICE, json={**receipt, **tampered}
            ).status_code
            == 409
        )
    result = client.post(f"/api/device/deposits/{sid}/confirm", headers=DEVICE, json=receipt)
    assert result.status_code == 200 and result.json()["points"] == 25
    assert (
        client.post(f"/api/device/deposits/{sid}/confirm", headers=DEVICE, json=receipt).json()[
            "points"
        ]
        == 25
    )
    assert client.get("/api/me", headers=headers).json()["points"] == 1265


def test_arm_requires_valid_stable_fresh_inputs(client):
    sid, _ = classified(client)
    p = packet(valid=False)
    assert arm(client, sid, p).status_code == 409
    p = packet(2)
    p["scale"]["stable"] = False
    assert arm(client, sid, p).status_code == 409
    p = packet(3)
    p["scale"]["weight_g"] = 4500
    assert arm(client, sid, p).status_code == 409
    p = packet(4)
    p["controller"]["ready"] = False
    assert arm(client, sid, p).status_code == 409
    p = packet(5)
    client.post("/api/device/telemetry", headers=DEVICE, json=p)
    with connect() as db:
        db.execute(
            "UPDATE device_state SET received_at=?",
            ((datetime.now(UTC) - timedelta(seconds=30)).isoformat(),),
        )
    assert (
        client.post(
            f"/api/device/deposits/{sid}/arm",
            headers=DEVICE,
            json={
                "device_id": "ELM-01",
                "request_id": "arm-request-001",
                "telemetry_event_id": p["event_id"],
            },
        ).status_code
        == 409
    )


def test_order_and_payload_replay(client):
    p = packet(2)
    assert client.post("/api/device/telemetry", headers=DEVICE, json=p).status_code == 200
    assert client.post("/api/device/telemetry", headers=DEVICE, json=p).json()["duplicate"]
    p["scale"]["weight_g"] = 600
    assert client.post("/api/device/telemetry", headers=DEVICE, json=p).status_code == 409
    assert client.post("/api/device/telemetry", headers=DEVICE, json=packet(1)).status_code == 409


def test_fault_never_awards_points(client):
    sid, headers = classified(client)
    cid = arm(client, sid, packet()).json()["id"]
    result = client.post(
        f"/api/device/cycles/{cid}/fault",
        headers=DEVICE,
        json={"device_id": "ELM-01", "event_id": "pusher-fault-001", "reason": "PUSH_TIMEOUT"},
    )
    assert result.status_code == 200 and result.json()["points"] == 0
    assert client.get(f"/api/deposits/{sid}", headers=headers).json()["status"] == "cancelled"
    assert client.get("/api/me", headers=headers).json()["points"] == 1240


def test_configurable_station_lock(client, monkeypatch):
    monkeypatch.setattr(settings, "full_bin_blocks_station", True)
    client.post("/api/device/telemetry", headers=DEVICE, json=packet(full=True))
    assert (
        client.post("/api/deposits", headers=auth(client), json={"bin_id": "ELM-01"}).status_code
        == 409
    )


def test_real_collection_requires_sensor_and_keeps_actual_level(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    cleaner = auth(client, "cleaner")
    client.post("/api/device/telemetry", headers=DEVICE, json=packet(route="reject", full=True))
    tasks = client.get("/api/cleaner/tasks", headers=cleaner).json()["tasks"]
    task = next(t for t in tasks if t["bin_id"] == "ELM-01" and t["compartment"] == "reject")
    assert (
        client.post(f"/api/cleaner/tasks/{task['id']}/acknowledge", headers=cleaner).status_code
        == 200
    )
    path = f"/api/cleaner/tasks/{task['id']}/resolve"
    assert client.post(path, headers=cleaner).status_code == 409
    invalid = packet(2, valid=False, route="reject")
    client.post("/api/device/telemetry", headers=DEVICE, json=invalid)
    assert client.post(path, headers=cleaner).status_code == 409
    client.post("/api/device/telemetry", headers=DEVICE, json=packet(3))
    assert client.post(path, headers=cleaner).status_code == 200
    with connect() as db:
        station = db.execute("SELECT * FROM bins WHERE id='ELM-01'").fetchone()
        assert station["reject_fill"] == 9.6  # Actual 55 cm reading, not a fabricated zero.


def test_additive_migration_preserves_existing_balance(client):
    from app.db import SCHEMA, migrate

    with connect() as db:
        db.execute("UPDATE users SET points=777 WHERE email='resident@simeloop.demo'")
        before = db.execute("SELECT count(*) FROM ledger").fetchone()[0]
        db.execute("ALTER TABLE bins DROP COLUMN reject_fill")
        db.execute("ALTER TABLE deposits DROP COLUMN classified_at")
        db.execute("DROP TABLE compartment_config")
        db.executescript(SCHEMA)
        migrate(db)
        migrate(db)  # Safe on subsequent startup too.
        assert db.execute("SELECT count(*) FROM ledger").fetchone()[0] == before
        assert (
            db.execute("SELECT count(*) FROM compartment_config WHERE bin_id='ELM-01'").fetchone()[
                0
            ]
            == 3
        )
    assert client.get("/api/me", headers=auth(client)).json()["points"] == 777


def test_hold_classification_never_arms_or_credits(client, monkeypatch):
    from app.vision import classifier

    sid, headers = classified(client)
    monkeypatch.setattr(
        classifier,
        "classify",
        lambda image: {
            "category": "reject",
            "accepted": False,
            "route": "hold",
            "material": "unclear item",
            "confidence": 0.4,
            "model": "test-real-model",
            "is_demo": False,
        },
    )
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "gray").save(buffer, format="PNG")
    result = client.post(
        f"/api/device/deposits/{sid}/classify",
        headers=DEVICE,
        files={"file": ("unclear.png", buffer.getvalue(), "image/png")},
    )
    assert result.status_code == 200 and result.json()["route"] == "hold"
    assert arm(client, sid, packet()).status_code == 409
    assert client.get(f"/api/deposits/{sid}", headers=headers).json()["status"] == "pending"
    assert client.get("/api/me", headers=headers).json()["points"] == 1240
