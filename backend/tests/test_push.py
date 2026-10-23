from unittest.mock import AsyncMock

from app.config import settings
from app.db import connect
from app.push import deliver_pending
from tests.test_flows import auth


def test_alert_queues_push_for_assigned_cleaner(client, monkeypatch):
    headers = auth(client, "cleaner")
    monkeypatch.setattr(settings, "push_notifications_enabled", True)
    assert client.post(
        "/api/push-tokens", headers=headers, json={"token": "ExpoPushToken[test-device]"}
    ).json()["enabled"]
    response = client.post(
        "/api/demo/fill",
        headers=headers,
        json={"bin_id": "ELM-01", "compartment": "food", "fill_percent": 95},
    )
    assert response.status_code == 200
    with connect() as db:
        rows = db.execute("SELECT * FROM push_outbox").fetchall()
        assert len(rows) == 1 and rows[0]["status"] == "pending"
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    with connect() as db:
        assert db.execute("SELECT count(*) FROM push_tokens").fetchone()[0] == 0
        assert (
            db.execute("SELECT count(*) FROM push_outbox WHERE status='pending'").fetchone()[0] == 0
        )


def test_invalid_push_token_rejected(client):
    assert (
        client.post(
            "/api/push-tokens", headers=auth(client), json={"token": "https://arbitrary-url"}
        ).status_code
        == 422
    )


def test_push_delivery_marks_submission(client, monkeypatch):
    import asyncio

    import httpx

    headers = auth(client, "cleaner")
    monkeypatch.setattr(settings, "push_notifications_enabled", True)
    client.post("/api/push-tokens", headers=headers, json={"token": "ExpoPushToken[test-device]"})
    client.post(
        "/api/demo/fill",
        headers=headers,
        json={"bin_id": "ELM-01", "compartment": "food", "fill_percent": 95},
    )
    post = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"data": {"status": "ok", "id": "ticket-1"}},
            request=httpx.Request("POST", "https://exp.host"),
        )
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    asyncio.run(deliver_pending())
    assert post.await_count == 1
    with connect() as db:
        assert db.execute("SELECT status FROM push_outbox").fetchone()[0] == "submitted"
