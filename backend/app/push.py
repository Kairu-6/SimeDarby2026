"""Durable Expo notification delivery. Enabled only for a configured native build."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from .db import connect, now


async def deliver_pending():
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT o.* FROM push_outbox o JOIN push_tokens t ON t.token=o.token WHERE o.status='pending' AND o.next_attempt<=? LIMIT 50",
                (now(),),
            )
        ]
    if not rows:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        for row in rows:
            try:
                response = await client.post(
                    "https://exp.host/--/api/v2/push/send",
                    json={
                        "to": row["token"],
                        "title": row["title"],
                        "body": row["body"],
                        "sound": "default",
                        "channelId": "default",
                    },
                )
                response.raise_for_status()
                ticket = response.json()["data"]
                if ticket.get("status") == "error":
                    if ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                        with connect() as db:
                            db.execute("DELETE FROM push_tokens WHERE token=?", (row["token"],))
                    raise ValueError(ticket.get("message", "Push provider rejected notification"))
                with connect() as db:
                    db.execute(
                        "UPDATE push_outbox SET status='submitted',attempts=attempts+1,last_error=NULL WHERE id=?",
                        (row["id"],),
                    )
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                attempts = row["attempts"] + 1
                retry_at = (
                    datetime.now(UTC) + timedelta(seconds=min(900, 10 * 2**attempts))
                ).isoformat()
                with connect() as db:
                    db.execute(
                        "UPDATE push_outbox SET attempts=?,status=?,next_attempt=?,last_error=? WHERE id=?",
                        (
                            attempts,
                            "failed" if attempts >= 5 else "pending",
                            retry_at,
                            str(exc)[:300],
                            row["id"],
                        ),
                    )


async def worker():
    while True:
        try:
            await deliver_pending()
        except Exception:
            # The durable pending rows remain available after a transient database/provider error.
            pass
        await asyncio.sleep(5)
