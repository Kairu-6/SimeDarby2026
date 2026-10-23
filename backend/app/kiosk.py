"""Category-first station offers and single-resident, expiring QR claims."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from secrets import token_hex, token_urlsafe
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .config import settings
from .db import connect, now
from .hardware import capacity, check_capacity, prevent_cycle_mutation


def kiosk_auth(x_kiosk_key: Annotated[str | None, Header()] = None):
    if settings.demo_mode and not settings.kiosk_api_key:
        return
    if not settings.kiosk_api_key or not hmac.compare_digest(
        x_kiosk_key or "", settings.kiosk_api_key
    ):
        raise HTTPException(401, "Pair this screen with the station's kiosk key in Settings.")


def expire_offers(db):
    db.execute(
        "UPDATE kiosk_offers SET state='expired' WHERE state='waiting' AND expires_at<=?", (now(),)
    )
    db.execute(
        "UPDATE deposits SET status='expired' WHERE status IN ('pending','classified') AND expires_at<=?",
        (now(),),
    )


def offer_view(db, row):
    result = {k: row[k] for k in ("id", "bin_id", "category", "expires_at", "state")}
    result["deposit"] = None
    if row["deposit_id"]:
        d = db.execute("SELECT * FROM deposits WHERE id=?", (row["deposit_id"],)).fetchone()
        result["deposit"] = {
            k: d[k]
            for k in (
                "id",
                "status",
                "selected_category",
                "category",
                "capture_requested",
                "verification_message",
                "weight_kg",
                "points",
                "model",
            )
        }
        person = db.execute("SELECT name FROM users WHERE id=?", (row["user_id"],)).fetchone()
        result["resident_first_name"] = person["name"].split()[0]
        if d["status"] in ("expired", "cancelled", "completed"):
            result["state"] = d["status"]
        elif d["capture_requested"]:
            result["state"] = "checking"
        elif d["status"] == "classified":
            result["state"] = "sorting"
        else:
            result["state"] = "claimed"
    return result


class OfferCreate(BaseModel):
    category: Literal["food", "recyclable"]


class Claim(BaseModel):
    key: str = Field(min_length=20, max_length=100)


def router(current_user, resident):
    routes = APIRouter(prefix="/api/kiosk", tags=["Station screen"])

    @routes.get("/stations/{bin_id}")
    def station(bin_id: str, request: Request):
        with connect() as db:
            expire_offers(db)
            row = db.execute("SELECT * FROM bins WHERE id=?", (bin_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Station not found.")
            ranks = [
                dict(r)
                for r in db.execute(
                    "SELECT name,lifetime_points points FROM users WHERE township=? AND role='resident' ORDER BY lifetime_points DESC,name LIMIT 5",
                    (row["township"],),
                )
            ]
            # A public screen shows first names, never account IDs or email addresses.
            for i, rank in enumerate(ranks):
                rank["name"] = rank["name"].split()[0]
                rank["rank"] = i + 1
            busy = db.execute(
                "SELECT id FROM deposits WHERE bin_id=? AND status IN ('pending','classified')",
                (bin_id,),
            ).fetchone()
            return {
                "id": bin_id,
                "name": row["name"],
                "township": row["township"],
                "online": bool(row["online"]),
                "busy": bool(busy),
                "compartments": capacity(db, row),
                "leaderboard": ranks,
                "demo_mode": settings.demo_mode,
                "app_url": settings.public_app_url or str(request.base_url).rstrip("/"),
                "pairing_required": bool(settings.kiosk_api_key) or not settings.demo_mode,
                "points_per_kg": {
                    "food": settings.food_points_per_kg,
                    "recyclable": settings.recyclable_points_per_kg,
                },
            }

    @routes.post("/stations/{bin_id}/offers")
    def create_offer(
        bin_id: str, body: OfferCreate, request: Request, auth: Annotated[None, Depends(kiosk_auth)]
    ):
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expire_offers(db)
            row = db.execute("SELECT * FROM bins WHERE id=?", (bin_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Station not found.")
            check_capacity(db, row, body.category)
            if db.execute(
                "SELECT id FROM deposits WHERE bin_id=? AND status IN ('pending','classified')",
                (bin_id,),
            ).fetchone():
                raise HTTPException(
                    409, "Someone is using this station. Please wait for them to finish."
                )
            db.execute(
                "UPDATE kiosk_offers SET state='cancelled' WHERE bin_id=? AND state='waiting'",
                (bin_id,),
            )
            key, oid = token_urlsafe(32), token_hex(12)
            expires = (
                datetime.now(UTC) + timedelta(seconds=settings.kiosk_qr_ttl_seconds)
            ).isoformat()
            db.execute(
                "INSERT INTO kiosk_offers (id,bin_id,category,key_hash,created_at,expires_at) VALUES (?,?,?,?,?,?)",
                (
                    oid,
                    bin_id,
                    body.category,
                    hashlib.sha256(key.encode()).hexdigest(),
                    now(),
                    expires,
                ),
            )
            offer = offer_view(
                db, db.execute("SELECT * FROM kiosk_offers WHERE id=?", (oid,)).fetchone()
            )
            return {
                **offer,
                "claim_key": key,
                "claim_url": (settings.public_app_url or str(request.base_url)).rstrip("/")
                + "/?claim="
                + key,
            }

    @routes.post("/claim")
    def claim(body: Claim, user: Annotated[dict, Depends(current_user)]):
        resident(user)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expire_offers(db)
            offer = db.execute(
                "SELECT * FROM kiosk_offers WHERE key_hash=?",
                (hashlib.sha256(body.key.encode()).hexdigest(),),
            ).fetchone()
            if not offer:
                raise HTTPException(
                    404, "This QR code is not recognised. Scan the current code on the bin screen."
                )
            if offer["user_id"] == user["id"] and offer["deposit_id"]:
                return dict(
                    db.execute(
                        "SELECT * FROM deposits WHERE id=?", (offer["deposit_id"],)
                    ).fetchone()
                )
            if offer["state"] != "waiting" or offer["expires_at"] <= now():
                raise HTTPException(
                    409,
                    "This QR code has expired or has already been claimed. Choose a category on the screen again.",
                )
            bin_row = db.execute("SELECT * FROM bins WHERE id=?", (offer["bin_id"],)).fetchone()
            check_capacity(db, bin_row, offer["category"])
            if db.execute(
                "SELECT id FROM deposits WHERE (bin_id=? OR user_id=?) AND status IN ('pending','classified')",
                (offer["bin_id"], user["id"]),
            ).fetchone():
                raise HTTPException(
                    409, "Finish your current deposit before claiming another station."
                )
            sid = token_hex(12)
            expires = (
                datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds)
            ).isoformat()
            db.execute(
                "INSERT INTO deposits (id,user_id,bin_id,status,created_at,expires_at,selected_category) VALUES (?,?,?,'pending',?,?,?)",
                (sid, user["id"], offer["bin_id"], now(), expires, offer["category"]),
            )
            db.execute(
                "UPDATE kiosk_offers SET state='claimed',user_id=?,deposit_id=? WHERE id=?",
                (user["id"], sid, offer["id"]),
            )
            return dict(db.execute("SELECT * FROM deposits WHERE id=?", (sid,)).fetchone())

    @routes.get("/offers/{offer_id}")
    def get_offer(offer_id: str, auth: Annotated[None, Depends(kiosk_auth)]):
        with connect() as db:
            expire_offers(db)
            row = db.execute("SELECT * FROM kiosk_offers WHERE id=?", (offer_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Station session not found.")
            return offer_view(db, row)

    @routes.post("/offers/{offer_id}/check")
    def check_offer(offer_id: str, auth: Annotated[None, Depends(kiosk_auth)]):
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expire_offers(db)
            row = db.execute("SELECT * FROM kiosk_offers WHERE id=?", (offer_id,)).fetchone()
            if not row or not row["deposit_id"]:
                raise HTTPException(409, "Scan the QR code with your resident account first.")
            d = db.execute("SELECT * FROM deposits WHERE id=?", (row["deposit_id"],)).fetchone()
            prevent_cycle_mutation(db, d["id"])
            if d["status"] not in ("pending", "classified"):
                raise HTTPException(409, "This deposit session has ended.")
            station_row = db.execute("SELECT * FROM bins WHERE id=?", (row["bin_id"],)).fetchone()
            check_capacity(db, station_row, row["category"])
            db.execute(
                "UPDATE deposits SET status='pending',classified_at=NULL,capture_requested=1,verification_message=NULL WHERE id=?",
                (d["id"],),
            )
            return {"ok": True, "message": "Keep your hands clear. Waiting for the station camera."}

    @routes.post("/offers/{offer_id}/cancel")
    def cancel_offer(offer_id: str, auth: Annotated[None, Depends(kiosk_auth)]):
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM kiosk_offers WHERE id=?", (offer_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Station session not found.")
            if row["deposit_id"]:
                prevent_cycle_mutation(db, row["deposit_id"])
                db.execute(
                    "UPDATE deposits SET status='cancelled',capture_requested=0 WHERE id=? AND status IN ('pending','classified')",
                    (row["deposit_id"],),
                )
            db.execute("UPDATE kiosk_offers SET state='cancelled' WHERE id=?", (offer_id,))
            return {"ok": True}

    return routes
