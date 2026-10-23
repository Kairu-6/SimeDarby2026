import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from app.config import settings
from app.db import connect
from app.vision import decode_rgb565, fnv1a


def auth(client, role="resident"):
    response = client.post(
        "/api/auth/login",
        json={"email": f"{role}@simeloop.demo", "password": "Loop123!"},
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def deposit(client, headers, category="recyclable", bin_id="ELM-01"):
    response = client.post("/api/deposits", headers=headers, json={"bin_id": bin_id})
    assert response.status_code == 200, response.text
    sid = response.json()["id"]
    response = client.post(
        f"/api/demo/deposits/{sid}/classify",
        headers=headers,
        json={"category": category},
    )
    assert response.status_code == 200, response.text
    return sid


def test_auth_and_logout(client):
    assert client.get("/api/bins").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "resident@simeloop.demo", "password": "bad"},
        ).status_code
        == 401
    )
    headers = auth(client)
    assert client.get("/api/me", headers=headers).json()["role"] == "resident"
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401


def test_verified_demo_deposit_credits_once(client):
    headers = auth(client)
    sid = deposit(client, headers)
    body = {"weight_kg": 0.5, "event_id": "test-event-001"}
    first = client.post(f"/api/demo/deposits/{sid}/confirm", headers=headers, json=body)
    second = client.post(f"/api/demo/deposits/{sid}/confirm", headers=headers, json=body)
    assert first.json()["points"] == second.json()["points"] == 50
    assert client.get("/api/me", headers=headers).json()["points"] == 1290
    ledger = client.get("/api/history", headers=headers).json()
    assert sum(1 for row in ledger if row["points"] == 50) == 1


def test_food_points_and_reject_fallback(client):
    headers = auth(client)
    sid = deposit(client, headers, "reject")
    body = {"weight_kg": 1, "event_id": "test-event-002"}
    assert (
        client.post(f"/api/demo/deposits/{sid}/confirm", headers=headers, json=body).json()[
            "points"
        ]
        == 0
    )
    sid = deposit(client, headers, "food")
    response = client.post(
        f"/api/demo/deposits/{sid}/confirm",
        headers=headers,
        json={**body, "event_id": "test-food-003"},
    )
    assert response.json()["points"] == 50


def test_no_points_before_sensor_confirmation(client):
    headers = auth(client)
    deposit(client, headers)
    assert client.get("/api/me", headers=headers).json()["points"] == 1240


def test_no_real_device_confirmation_of_simulation(client):
    headers = auth(client)
    sid = deposit(client, headers)
    response = client.post(
        f"/api/device/deposits/{sid}/confirm",
        headers={"X-Device-Key": settings.device_api_key},
        json={"weight_kg": 0.5, "event_id": "test-event-003"},
    )
    assert response.status_code == 409


def test_negative_and_huge_weight_rejected(client):
    headers = auth(client)
    sid = deposit(client, headers)
    for weight in [0, -1, 25]:
        assert (
            client.post(
                f"/api/demo/deposits/{sid}/confirm",
                headers=headers,
                json={"weight_kg": weight, "event_id": "bad-event-001"},
            ).status_code
            == 422
        )


def test_redemption_is_idempotent_and_balance_persistent(client):
    headers = auth(client)
    first = client.post(
        "/api/vouchers/v1/redeem",
        headers=headers,
        json={"request_id": "redeem-test-001"},
    )
    second = client.post(
        "/api/vouchers/v1/redeem",
        headers=headers,
        json={"request_id": "redeem-test-001"},
    )
    assert first.status_code == 200
    assert first.json()["code"] == second.json()["code"]
    assert client.get("/api/me", headers=headers).json()["points"] == 940
    assert len(client.get("/api/wallet", headers=headers).json()) == 1
    assert client.get("/api/me", headers=auth(client)).json()["points"] == 940


def test_concurrent_redemption_cannot_overspend(client):
    headers = auth(client)

    def redeem(i):
        return client.post(
            "/api/vouchers/v4/redeem",
            headers=headers,
            json={"request_id": f"concurrent-{i}"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, range(2)))
    assert sorted(results) == [200, 409]
    assert client.get("/api/me", headers=headers).json()["points"] == 540


def test_no_overspend_or_out_of_stock(client):
    headers = auth(client)
    assert (
        client.post(
            "/api/vouchers/v6/redeem",
            headers=headers,
            json={"request_id": "overspend-001"},
        ).status_code
        == 409
    )
    with connect() as db:
        db.execute("UPDATE vouchers SET stock=0 WHERE id='v1'")
    assert (
        client.post(
            "/api/vouchers/v1/redeem",
            headers=headers,
            json={"request_id": "sold-out-001"},
        ).status_code
        == 409
    )
    assert client.get("/api/me", headers=headers).json()["points"] == 1240


def test_wallet_use_only_once(client):
    headers = auth(client)
    rid = client.post(
        "/api/vouchers/v1/redeem",
        headers=headers,
        json={"request_id": "wallet-test-001"},
    ).json()["id"]
    assert client.post(f"/api/demo/wallet/{rid}/use", headers=headers).status_code == 200
    assert client.post(f"/api/demo/wallet/{rid}/use", headers=headers).status_code == 409


def test_roles_and_task_area_scope(client):
    resident_headers = auth(client)
    cleaner_headers = auth(client, "cleaner")
    assert client.get("/api/cleaner/tasks", headers=resident_headers).status_code == 403
    assert (
        client.post("/api/deposits", headers=cleaner_headers, json={"bin_id": "ELM-01"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/vouchers/v1/redeem",
            headers=cleaner_headers,
            json={"request_id": "cleaner-test"},
        ).status_code
        == 403
    )
    with connect() as db:
        foreign_task = db.execute("SELECT id FROM alerts WHERE bin_id='SJ-01'").fetchone()[0]
    assert (
        client.post(
            f"/api/cleaner/tasks/{foreign_task}/acknowledge", headers=cleaner_headers
        ).status_code
        == 404
    )


def test_full_bin_alert_cleanup_cycle(client):
    resident_headers, cleaner_headers = auth(client), auth(client, "cleaner")
    body = {
        "device_id": "ELM-01",
        "distance_cm": 9,
        "compartment": "food",
        "event_id": "reading-test-001",
    }
    assert client.post("/readings", json=body).status_code == 401
    for _ in range(2):
        response = client.post(
            "/readings", headers={"X-Device-Key": settings.device_api_key}, json=body
        )
        assert response.status_code == 200
    tasks = client.get("/api/cleaner/tasks", headers=cleaner_headers).json()["tasks"]
    matching = [t for t in tasks if t["bin_id"] == "ELM-01"]
    assert len(matching) == 1
    tid = matching[0]["id"]
    assert (
        client.post(f"/api/cleaner/tasks/{tid}/resolve", headers=cleaner_headers).status_code == 409
    )
    assert (
        client.post(f"/api/cleaner/tasks/{tid}/acknowledge", headers=cleaner_headers).status_code
        == 200
    )
    assert (
        client.post(f"/api/cleaner/tasks/{tid}/resolve", headers=cleaner_headers).status_code == 200
    )
    bin = next(
        b for b in client.get("/api/bins", headers=resident_headers).json() if b["id"] == "ELM-01"
    )
    assert bin["food_fill"] == 0 and bin["recycle_fill"] == 42
    notices = client.get("/api/notifications", headers=cleaner_headers).json()
    assert len([n for n in notices if n["kind"] == "bin_full"]) == 1


def test_session_expiry_cancel_and_busy(client):
    headers = auth(client)
    sid = deposit(client, headers)
    bins = client.get("/api/bins", headers=headers).json()
    assert next(b for b in bins if b["id"] == "ELM-01")["status"] == "in_use"
    with connect() as db:
        db.execute(
            "UPDATE deposits SET expires_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), sid),
        )
    assert client.get(f"/api/deposits/{sid}", headers=headers).json()["status"] == "expired"
    newer = deposit(client, headers)
    assert newer != sid
    assert client.post(f"/api/deposits/{newer}/cancel", headers=headers).status_code == 200


def test_full_compartment_cannot_route(client):
    headers = auth(client)
    client.post(
        "/api/demo/fill",
        headers=headers,
        json={"bin_id": "ELM-01", "compartment": "food", "fill_percent": 95},
    )
    sid = client.post("/api/deposits", headers=headers, json={"bin_id": "ELM-01"}).json()["id"]
    assert (
        client.post(
            f"/api/demo/deposits/{sid}/classify",
            headers=headers,
            json={"category": "food"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/demo/deposits/{sid}/classify",
            headers=headers,
            json={"category": "recyclable"},
        ).status_code
        == 200
    )


def test_demo_can_be_disabled(client, monkeypatch):
    headers = auth(client)
    monkeypatch.setattr(settings, "demo_mode", False)
    assert (
        client.post(
            "/api/demo/fill",
            headers=headers,
            json={"bin_id": "ELM-01", "compartment": "food", "fill_percent": 95},
        ).status_code
        == 404
    )


def test_history_leaderboard_and_notifications(client):
    headers = auth(client)
    assert len(client.get("/api/history", headers=headers).json()) == 8
    assert client.get("/api/leaderboard", headers=headers).json()[0]["name"] == "Sarah Tan"
    townships = client.get("/api/leaderboard?scope=townships", headers=headers).json()
    assert townships[0]["id"] == "City of Elmina"
    assert client.post("/api/notifications/read", headers=headers).status_code == 200
    assert all(n["is_read"] for n in client.get("/api/notifications", headers=headers).json())


def test_invalid_photo_and_rgb565_validation(client):
    headers = auth(client)
    assert (
        client.post(
            "/api/vision/classify",
            headers=headers,
            files={"file": ("x.png", b"not-an-image", "image/png")},
        ).status_code
        == 422
    )
    assert tuple(decode_rgb565(b"\x00\xf8", 1, 1, "little").getpixel((0, 0))) == (
        255,
        0,
        0,
    )
    assert tuple(decode_rgb565(b"\xf8\x00", 1, 1, "big").getpixel((0, 0))) == (
        255,
        0,
        0,
    )
    with pytest.raises(ValueError):
        decode_rgb565(b"x", 1, 1, "little")
    assert fnv1a(b"hello") == "4F9F2CAB"


def test_photo_endpoint_uses_classifier(client, monkeypatch):
    from app.vision import classifier

    headers = auth(client)
    called = []

    def classify(image):
        called.append(image.size)
        return {
            "category": "food",
            "accepted": True,
            "route": "food",
            "model": "test-only",
            "confidence": 0.9,
        }

    monkeypatch.setattr(classifier, "classify", classify)
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(buffer, format="PNG")
    result = client.post(
        "/api/vision/classify",
        headers=headers,
        files={"file": ("photo.png", buffer.getvalue(), "image/png")},
    )
    assert result.json()["category"] == "food" and called == [(32, 32)]
    assert client.get("/api/me", headers=headers).json()["points"] == 1240


def test_real_device_flow(client, monkeypatch):
    from app.vision import classifier
    from tests.test_hardware import packet

    headers = auth(client)
    device = {"X-Device-Key": settings.device_api_key}
    sid = client.post("/api/deposits", headers=headers, json={"bin_id": "ELM-01"}).json()["id"]
    monkeypatch.setattr(
        classifier,
        "classify",
        lambda image: {
            "category": "food",
            "material": "banana peel",
            "accepted": True,
            "route": "food",
            "model": "test-only",
            "confidence": 0.95,
        },
    )
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "yellow").save(buffer, format="PNG")
    assert (
        client.post(
            f"/api/device/deposits/{sid}/classify",
            headers=device,
            files={"file": ("photo.png", buffer.getvalue(), "image/png")},
        ).status_code
        == 200
    )
    assert (
        client.get("/api/device/bins/ELM-01/session", headers=device).json()["session"]["id"] == sid
    )
    p = packet(weight=800)
    client.post("/api/device/telemetry", headers=device, json=p)
    cycle = client.post(
        f"/api/device/deposits/{sid}/arm",
        headers=device,
        json={
            "device_id": "ELM-01",
            "request_id": "real-arm-test-001",
            "telemetry_event_id": p["event_id"],
        },
    ).json()["id"]
    client.post("/api/device/telemetry", headers=device, json=packet(2, weight=0, done=cycle))
    confirmed = client.post(
        f"/api/device/deposits/{sid}/confirm",
        headers=device,
        json={
            "weight_kg": 0.8,
            "event_id": "device-event-001",
            "device_id": "ELM-01",
            "cycle_id": cycle,
            "controller_cycle_id": cycle,
            "route": "food",
        },
    )
    assert confirmed.status_code == 200 and confirmed.json()["points"] == 40


def test_raw_camera_rejects_corrupt_checksum(client):
    response = client.post(
        "/camera/upload",
        headers={
            "X-Device-Key": settings.device_api_key,
            "X-Width": "1",
            "X-Height": "1",
            "X-Frame-FNV1A": "00000000",
        },
        content=b"\x00\xf8",
    )
    assert response.status_code == 422
