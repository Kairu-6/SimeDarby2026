import asyncio
import hmac
import math
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex, token_urlsafe
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from .config import settings
from .db import connect, now, password_hash, seed
from .hardware import FILL_COLUMNS, capacity, check_capacity, prevent_cycle_mutation, verify_receipt
from .hardware import router as hardware_router
from .kiosk import router as kiosk_router
from .push import worker
from .smartbin import camera_response
from .smartbin import router as smartbin_router
from .vision import VisionUnavailable, classifier, decode_image, decode_rgb565, fnv1a


@asynccontextmanager
async def lifespan(app):
    seed()
    push_task = asyncio.create_task(worker()) if settings.push_notifications_enabled else None
    try:
        yield
    finally:
        if push_task:
            push_task.cancel()
            with suppress(asyncio.CancelledError):
                await push_task


app = FastAPI(title="Sime Loop API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Device-Key",
        "X-Kiosk-Key",
        "Idempotency-Key",
    ],
)


def public_user(user):
    return {
        key: user[key]
        for key in (
            "id",
            "name",
            "email",
            "role",
            "township",
            "points",
            "lifetime_points",
        )
    }


def current_user(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue.")
    with connect() as db:
        row = db.execute(
            "SELECT u.* FROM users u JOIN tokens t ON t.user_id=u.id WHERE t.token=? AND t.expires_at>?",
            (authorization[7:], now()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Your session expired. Please sign in again.")
    return dict(row)


User = Annotated[dict, Depends(current_user)]


def resident(user):
    if user["role"] != "resident":
        raise HTTPException(403, "This action is available to residents.")


def cleaner(user):
    if user["role"] != "cleaner":
        raise HTTPException(403, "A cleaner account is required.")


def demo_only():
    if not settings.demo_mode:
        raise HTTPException(404, "Demo controls are disabled.")


def device_auth(x_device_key: Annotated[str | None, Header()] = None):
    if not x_device_key or not hmac.compare_digest(x_device_key, settings.device_api_key):
        raise HTTPException(401, "Invalid device key.")


Device = Annotated[None, Depends(device_auth)]


def expire_sessions(db):
    db.execute(
        "UPDATE deposits SET status='expired' WHERE status IN ('pending','classified') AND expires_at<=?",
        (now(),),
    )


def bin_view(row, busy=False):
    item = dict(row)
    with connect() as db:
        item["compartments"] = capacity(db, row)
    item["status"] = (
        "offline"
        if not item["online"]
        else "full"
        if any(c["full"] for c in item["compartments"].values())
        else "in_use"
        if busy
        else "available"
    )
    item["qr_payload"] = f"simeloop://bin/{item['id']}"
    item["accepting_deposits"] = (
        bool(item["online"])
        and any(not c["full"] for c in item["compartments"].values())
        and not (
            settings.full_bin_blocks_station
            and any(c["full"] for c in item["compartments"].values())
        )
        and not busy
    )
    return item


def notify(db, user_id, title, body, kind="info"):
    db.execute(
        "INSERT INTO notifications VALUES (?,?,?,?,?,?,?)",
        (token_hex(12), user_id, title, body, kind, 0, now()),
    )
    if settings.push_notifications_enabled:
        for row in db.execute("SELECT token FROM push_tokens WHERE user_id=?", (user_id,)):
            db.execute(
                "INSERT INTO push_outbox (id,token,title,body,next_attempt,created_at) VALUES (?,?,?,?,?,?)",
                (token_hex(12), row["token"], title, body, now(), now()),
            )


def check_full(db, bin_id):
    row = db.execute("SELECT * FROM bins WHERE id=?", (bin_id,)).fetchone()
    for category, key in FILL_COLUMNS.items():
        threshold = db.execute(
            "SELECT threshold FROM compartment_config WHERE bin_id=? AND category=?",
            (bin_id, category),
        ).fetchone()[0]
        if row[key] < threshold:
            continue
        exists = db.execute(
            "SELECT id FROM alerts WHERE bin_id=? AND compartment=? AND status!='resolved'",
            (bin_id, category),
        ).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO alerts (id,bin_id,compartment,created_at) VALUES (?,?,?,?)",
                (token_hex(12), bin_id, category, now()),
            )
            for user in db.execute(
                "SELECT id FROM users WHERE role='cleaner' AND township=?",
                (row["township"],),
            ):
                notify(
                    db,
                    user["id"],
                    f"{row['name']} needs clearing",
                    f"The {category} compartment is {round(row[key])}% full.",
                    "bin_full",
                )


@app.get("/api/health")
@app.get("/")
def health(request: Request):
    if request.url.path == "/" and settings.web_build_path:
        return FileResponse(Path(settings.web_build_path) / "index.html")
    return {
        "status": "online",
        "demo_mode": settings.demo_mode,
        "iot_protocol_version": 2,
        "vision": {
            "enabled": settings.vision_enabled,
            "loaded": classifier.model is not None,
            "model": settings.vision_model,
        },
    }


class Login(BaseModel):
    email: str = Field(max_length=150)
    password: str = Field(max_length=200)


@app.post("/api/auth/login")
def login(body: Login):
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE email=?", (body.email.lower().strip(),)
        ).fetchone()
        if not user or not hmac.compare_digest(
            password_hash(body.password, user["salt"]), user["password_hash"]
        ):
            raise HTTPException(401, "Email or password is incorrect.")
        token = token_urlsafe(32)
        db.execute(
            "INSERT INTO tokens VALUES (?,?,?)",
            (token, user["id"], (datetime.now(UTC) + timedelta(days=7)).isoformat()),
        )
        return {"token": token, "user": public_user(user)}


@app.post("/api/auth/logout")
def logout(user: User, authorization: Annotated[str, Header()]):
    with connect() as db:
        db.execute("DELETE FROM tokens WHERE token=?", (authorization[7:],))
        db.execute(
            "DELETE FROM push_outbox WHERE status='pending' AND token IN (SELECT token FROM push_tokens WHERE user_id=?)",
            (user["id"],),
        )
        db.execute("DELETE FROM push_tokens WHERE user_id=?", (user["id"],))
    return {"ok": True}


class PushRegistration(BaseModel):
    token: str = Field(
        max_length=200, pattern=r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]+\]$"
    )


@app.post("/api/push-tokens")
def register_push(body: PushRegistration, user: User):
    with connect() as db:
        previous = db.execute(
            "SELECT user_id FROM push_tokens WHERE token=?", (body.token,)
        ).fetchone()
        if previous and previous["user_id"] != user["id"]:
            db.execute("DELETE FROM push_outbox WHERE token=? AND status='pending'", (body.token,))
        db.execute(
            "INSERT INTO push_tokens VALUES (?,?,?) ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id,updated_at=excluded.updated_at",
            (body.token, user["id"], now()),
        )
    return {"enabled": settings.push_notifications_enabled}


@app.get("/api/me")
def me(user: User):
    return public_user(user)


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=60)


@app.patch("/api/me")
def update_me(body: ProfileUpdate, user: User):
    if not body.name.strip():
        raise HTTPException(422, "Enter your name.")
    with connect() as db:
        db.execute("UPDATE users SET name=? WHERE id=?", (body.name.strip(), user["id"]))
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(user: User):
    with connect() as db:
        expire_sessions(db)
        stats = db.execute(
            "SELECT coalesce(sum(weight_kg),0) kg, count(*) visits FROM ledger WHERE user_id=? AND type='earned'",
            (user["id"],),
        ).fetchone()
        food = db.execute(
            "SELECT coalesce(sum(weight_kg),0) FROM ledger WHERE user_id=? AND type='earned' AND title LIKE 'Food%'",
            (user["id"],),
        ).fetchone()[0]
        rank = db.execute(
            "SELECT count(*)+1 FROM users WHERE role='resident' AND lifetime_points>?",
            (user["lifetime_points"],),
        ).fetchone()[0]
        active = db.execute(
            "SELECT d.*,b.name bin_name FROM deposits d JOIN bins b ON b.id=d.bin_id WHERE d.user_id=? AND d.status IN ('pending','classified') ORDER BY d.created_at DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        return {
            "user": public_user(user),
            "stats": {
                "total_kg": round(stats["kg"], 2),
                "food_kg": round(food, 2),
                "recycled_kg": round(stats["kg"] - food, 2),
                "visits": stats["visits"],
                "rank": rank,
            },
            "active_session": dict(active) if active else None,
            "demo_mode": settings.demo_mode,
        }


@app.get("/api/bins")
def bins(user: User):
    with connect() as db:
        expire_sessions(db)
        busy = {
            x[0]
            for x in db.execute(
                "SELECT bin_id FROM deposits WHERE status IN ('pending','classified')"
            )
        }
        return [bin_view(x, x["id"] in busy) for x in db.execute("SELECT * FROM bins ORDER BY id")]


@app.get("/api/vouchers")
def vouchers(user: User):
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM vouchers ORDER BY cost")]


class Redeem(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)


@app.post("/api/vouchers/{voucher_id}/redeem")
def redeem(voucher_id: str, body: Redeem, user: User):
    resident(user)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT * FROM redemptions WHERE user_id=? AND request_id=?",
            (user["id"], body.request_id),
        ).fetchone()
        if previous:
            if previous["voucher_id"] != voucher_id:
                raise HTTPException(409, "This request was already used for another reward.")
            return dict(previous)
        voucher = db.execute("SELECT * FROM vouchers WHERE id=?", (voucher_id,)).fetchone()
        if not voucher:
            raise HTTPException(404, "Reward not found.")
        if voucher["stock"] <= 0:
            raise HTTPException(409, "This reward is sold out.")
        changed = db.execute(
            "UPDATE users SET points=points-? WHERE id=? AND points>=?",
            (voucher["cost"], user["id"], voucher["cost"]),
        ).rowcount
        if not changed:
            raise HTTPException(409, "You need more points to redeem this reward.")
        db.execute("UPDATE vouchers SET stock=stock-1 WHERE id=?", (voucher_id,))
        redemption_id, code, stamp = (
            token_hex(12),
            "LOOP-" + token_hex(4).upper(),
            now(),
        )
        db.execute(
            "INSERT INTO redemptions VALUES (?,?,?,?,?,?,?,?,?)",
            (
                redemption_id,
                user["id"],
                voucher_id,
                code,
                voucher["cost"],
                "available",
                stamp,
                (datetime.now(UTC) + timedelta(days=voucher["valid_days"])).isoformat(),
                body.request_id,
            ),
        )
        db.execute(
            "INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?)",
            (
                token_hex(12),
                user["id"],
                "redeemed",
                voucher["title"],
                voucher["merchant"] + " · " + voucher["location"],
                -voucher["cost"],
                0,
                stamp,
            ),
        )
        notify(
            db,
            user["id"],
            "A little reward for a good habit",
            f"Your {voucher['merchant']} voucher is ready in My vouchers.",
            "reward",
        )
        return dict(db.execute("SELECT * FROM redemptions WHERE id=?", (redemption_id,)).fetchone())


@app.get("/api/wallet")
def wallet(user: User):
    with connect() as db:
        db.execute(
            "UPDATE redemptions SET status='expired' WHERE expires_at<? AND status='available'",
            (now(),),
        )
        return [
            dict(row)
            for row in db.execute(
                "SELECT r.*,v.merchant,v.title,v.location,v.color,v.description FROM redemptions r JOIN vouchers v ON v.id=r.voucher_id WHERE r.user_id=? ORDER BY r.created_at DESC",
                (user["id"],),
            )
        ]


@app.post("/api/demo/wallet/{redemption_id}/use")
def use_demo_voucher(redemption_id: str, user: User):
    demo_only()
    with connect() as db:
        if not db.execute(
            "UPDATE redemptions SET status='used' WHERE id=? AND user_id=? AND status='available' AND expires_at>?",
            (redemption_id, user["id"], now()),
        ).rowcount:
            raise HTTPException(409, "This voucher is no longer available.")
    return {"ok": True}


@app.get("/api/history")
def history(user: User):
    with connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM ledger WHERE user_id=? ORDER BY created_at DESC",
                (user["id"],),
            )
        ]


@app.get("/api/leaderboard")
def leaderboard(user: User, scope: Literal["residents", "townships"] = "residents"):
    with connect() as db:
        if scope == "townships":
            rows = db.execute(
                "SELECT township id,township name,sum(lifetime_points) points,count(*) members FROM users WHERE role='resident' GROUP BY township ORDER BY points DESC,name"
            )
        else:
            rows = db.execute(
                "SELECT id,name,township,lifetime_points points FROM users WHERE role='resident' ORDER BY lifetime_points DESC,name"
            )
        return [{**dict(row), "rank": i + 1} for i, row in enumerate(rows)]


@app.get("/api/notifications")
def notifications(user: User):
    with connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                (user["id"],),
            )
        ]


@app.post("/api/notifications/read")
def read_notifications(user: User):
    with connect() as db:
        db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user["id"],))
    return {"ok": True}


class SessionCreate(BaseModel):
    bin_id: str = Field(max_length=100)


@app.post("/api/deposits")
def create_deposit(body: SessionCreate, user: User):
    resident(user)
    bin_id = body.bin_id.removeprefix("simeloop://bin/").strip()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        expire_sessions(db)
        row = db.execute("SELECT * FROM bins WHERE id=?", (bin_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Station not found. Scan a Sime Loop station QR code.")
        if not row["online"]:
            raise HTTPException(409, "This station is offline. Choose another station.")
        check_capacity(db, row)
        active = db.execute(
            "SELECT * FROM deposits WHERE (bin_id=? OR user_id=?) AND status IN ('pending','classified')",
            (bin_id, user["id"]),
        ).fetchone()
        if active:
            if active["user_id"] == user["id"] and active["bin_id"] == bin_id:
                return dict(active)
            raise HTTPException(409, "A deposit session is already in progress.")
        sid = token_hex(12)
        db.execute(
            "INSERT INTO deposits (id,user_id,bin_id,status,created_at,expires_at) VALUES (?,?,?,'pending',?,?)",
            (
                sid,
                user["id"],
                bin_id,
                now(),
                (datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds)).isoformat(),
            ),
        )
        return dict(db.execute("SELECT * FROM deposits WHERE id=?", (sid,)).fetchone())


def get_session(db, sid, user_id=None):
    expire_sessions(db)
    row = db.execute("SELECT * FROM deposits WHERE id=?", (sid,)).fetchone()
    if not row or (user_id and row["user_id"] != user_id):
        raise HTTPException(404, "Deposit session not found.")
    return row


@app.get("/api/deposits/{sid}")
def get_deposit(sid: str, user: User):
    with connect() as db:
        return dict(get_session(db, sid, user["id"]))


@app.post("/api/deposits/{sid}/cancel")
def cancel_deposit(sid: str, user: User):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = get_session(db, sid, user["id"])
        prevent_cycle_mutation(db, sid)
        if row["status"] not in ("pending", "classified", "expired", "cancelled"):
            raise HTTPException(409, "This deposit has already been completed.")
        db.execute(
            "UPDATE deposits SET status='cancelled' WHERE id=? AND status IN ('pending','classified')",
            (sid,),
        )
    return {"ok": True}


def save_classification(sid, result, user_id=None):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = get_session(db, sid, user_id)
        prevent_cycle_mutation(db, sid)
        if row["status"] not in ("pending", "classified"):
            raise HTTPException(409, "This session has ended. Start a new deposit.")
        b = db.execute("SELECT * FROM bins WHERE id=?", (row["bin_id"],)).fetchone()
        if (
            row["selected_category"]
            and result["accepted"]
            and result["category"] != row["selected_category"]
        ):
            result = {
                **result,
                "accepted": False,
                "route": "hold",
                "reward_eligible": False,
                "message": f"This session is for {row['selected_category']} only. Remove the item that does not match, then check again. The door stays closed.",
            }
        if result["accepted"]:
            check_capacity(db, b, result["category"])
        db.execute(
            "UPDATE deposits SET status=?,category=?,material=?,confidence=?,model=?,classified_at=?,capture_requested=0,verification_message=? WHERE id=?",
            (
                "classified" if result["accepted"] else "pending",
                result["category"],
                result["material"],
                result["confidence"],
                result["model"],
                now(),
                result.get("message"),
                sid,
            ),
        )
    return result


def infer(image):
    try:
        return classifier.classify(image)
    except (VisionUnavailable, ImportError) as exc:
        raise HTTPException(503, str(exc)) from exc


async def read_limited(request: Request, limit=8 * 1024 * 1024):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, "Upload is too large (maximum 8 MB).")
    return bytes(data)


@app.post("/api/vision/classify")
async def classify_photo(user: User, file: Annotated[UploadFile, File()]):
    try:
        image = decode_image(await file.read(8 * 1024 * 1024 + 1))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await run_in_threadpool(infer, image)


@app.post("/api/device/deposits/{sid}/classify")
async def classify_deposit(sid: str, device: Device, file: Annotated[UploadFile, File()]):
    try:
        image = decode_image(await file.read(8 * 1024 * 1024 + 1))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = await run_in_threadpool(infer, image)
    return save_classification(sid, result)


class DemoClassify(BaseModel):
    category: Literal["food", "recyclable", "reject"]


@app.post("/api/demo/deposits/{sid}/classify")
def demo_classify(sid: str, body: DemoClassify, user: User):
    demo_only()
    result = {
        "category": body.category,
        "material": {
            "food": "Fruit peels",
            "recyclable": "Clean plastic bottle",
            "reject": "Mixed waste",
        }[body.category],
        "confidence": 0.98,
        "model": "demo-simulation",
        "is_demo": True,
        "accepted": True,
        "route": body.category,
        "reward_eligible": body.category != "reject",
        "message": "Simulated classification. No image model was used.",
    }
    return save_classification(sid, result, user["id"])


class Confirm(BaseModel):
    event_id: str = Field(min_length=8, max_length=100)
    weight_kg: float = Field(gt=0, le=20, allow_inf_nan=False)
    device_id: str | None = None
    cycle_id: str | None = None
    controller_cycle_id: str | None = None
    route: Literal["food", "recyclable", "reject"] | None = None


def complete_deposit(sid, body, user_id=None, is_demo=False):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = get_session(db, sid, user_id)
        if row["status"] == "completed":
            return dict(row)
        if row["status"] != "classified" or row["category"] not in (
            "food",
            "recyclable",
            "reject",
        ):
            raise HTTPException(409, "Classify an accepted item before confirming the deposit.")
        if not is_demo and row["model"] == "demo-simulation":
            raise HTTPException(409, "A real device cannot confirm a simulated classification.")
        if db.execute("SELECT id FROM deposits WHERE event_id=?", (body.event_id,)).fetchone():
            raise HTTPException(409, "This sensor event has already been used.")
        col = FILL_COLUMNS[row["category"]]
        b = db.execute("SELECT * FROM bins WHERE id=?", (row["bin_id"],)).fetchone()
        # Capacity is checked before opening. Once a real item has moved, a newer full
        # reading must not erase its already-armed weight/receipt or encourage another push.
        if is_demo:
            check_capacity(db, b, row["category"])
            if not settings.min_item_g <= body.weight_kg * 1000 <= settings.max_item_kg * 1000:
                raise HTTPException(
                    422, "Weight is outside the configured 5 kg load-cell item range."
                )
            credited_weight = body.weight_kg
        else:
            credited_weight = verify_receipt(db, row, body)
        rate = {
            "food": settings.food_points_per_kg,
            "recyclable": settings.recyclable_points_per_kg,
            "reject": 0,
        }[row["category"]]
        points = max(1, math.floor(credited_weight * rate)) if rate else 0
        title = {
            "food": "Food waste diverted",
            "recyclable": "Recyclables sorted",
            "reject": "Unsorted waste collected",
        }[row["category"]]
        stamp = now()
        db.execute(
            "UPDATE deposits SET status='completed',points=?,weight_kg=?,event_id=?,completed_at=? WHERE id=?",
            (points, credited_weight, body.event_id, stamp, sid),
        )
        db.execute(
            "UPDATE users SET points=points+?,lifetime_points=lifetime_points+? WHERE id=?",
            (points, points, row["user_id"]),
        )
        db.execute(
            "INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?)",
            (
                token_hex(12),
                row["user_id"],
                "earned" if rate else "rejected",
                title,
                b["name"] + " · " + b["township"],
                points,
                credited_weight,
                stamp,
            ),
        )
        # Demo estimates volume; actual hardware provides independent ultrasonic readings.
        if is_demo:
            db.execute(
                f"UPDATE bins SET {col}=min(100,{col}+?),last_seen=? WHERE id=?",
                (body.weight_kg * 4, stamp, b["id"]),
            )
            check_full(db, b["id"])
        notify(
            db,
            row["user_id"],
            f"You earned {points} Loop points" if rate else "Unsorted waste safely collected",
            f"Thanks for sorting {credited_weight:g} kg at {b['name']}."
            if rate
            else "No points for mixed waste. Separate food scraps and recyclables next time.",
            "points",
        )
        return dict(db.execute("SELECT * FROM deposits WHERE id=?", (sid,)).fetchone())


@app.post("/api/device/deposits/{sid}/confirm")
def confirm_deposit(sid: str, body: Confirm, device: Device):
    return complete_deposit(sid, body)


@app.post("/api/demo/deposits/{sid}/confirm")
def confirm_demo(sid: str, body: Confirm, user: User):
    demo_only()
    return complete_deposit(sid, body, user["id"], True)


class Reading(BaseModel):
    device_id: str = Field(max_length=100)
    distance_cm: float = Field(ge=0, le=500, allow_inf_nan=False)
    compartment: Literal["food", "recyclable", "reject"] = "recyclable"
    event_id: str = Field(min_length=8, max_length=100)


def apply_reading(body):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM bins WHERE device_id=?", (body.device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown device. Register its ID before sending telemetry.")
        previous = db.execute(
            "SELECT bin_id FROM sensor_events WHERE event_id=?", (body.event_id,)
        ).fetchone()
        if previous:
            if previous["bin_id"] != row["id"]:
                raise HTTPException(409, "Sensor event ID was already used by another device.")
            return {"duplicate": True, "bin": bin_view(row)}
        calibration = db.execute(
            "SELECT * FROM compartment_config WHERE bin_id=? AND category=?",
            (row["id"], body.compartment),
        ).fetchone()
        fill = round(
            max(
                0,
                min(
                    100,
                    (calibration["empty_cm"] - body.distance_cm)
                    / (calibration["empty_cm"] - calibration["full_cm"])
                    * 100,
                ),
            ),
            1,
        )
        col = FILL_COLUMNS[body.compartment]
        db.execute(
            "UPDATE compartment_config SET distance_cm=?,valid=1,sampled_at=? WHERE bin_id=? AND category=?",
            (body.distance_cm, now(), row["id"], body.compartment),
        )
        db.execute(
            f"UPDATE bins SET {col}=?,last_seen=?,online=1 WHERE id=?",
            (fill, now(), row["id"]),
        )
        db.execute(
            "INSERT INTO sensor_events VALUES (?,?,?)",
            (body.event_id, row["id"], now()),
        )
        check_full(db, row["id"])
        return {
            "duplicate": False,
            "fill_percent": fill,
            "bin": bin_view(db.execute("SELECT * FROM bins WHERE id=?", (row["id"],)).fetchone()),
        }


@app.post("/readings")
@app.post("/api/device/readings")
def receive_reading(body: Reading, device: Device):
    return apply_reading(body)


@app.get("/api/device/bins/{bin_id}/session")
def device_session(bin_id: str, device: Device):
    with connect() as db:
        expire_sessions(db)
        row = db.execute(
            "SELECT id,status,category,model,expires_at FROM deposits WHERE bin_id=? AND status IN ('pending','classified')",
            (bin_id,),
        ).fetchone()
        cycle = (
            db.execute(
                "SELECT id,state,route,execute_before FROM device_cycles WHERE session_id=?",
                (row["id"],),
            ).fetchone()
            if row
            else None
        )
        return {
            "session": dict(row) if row else None,
            "cycle": dict(cycle) if cycle else None,
            "protocol_version": 2,
        }


@app.post("/camera/upload")
async def raw_camera(request: Request, device: Device):
    raw = await read_limited(request, 640 * 480 * 2)
    try:
        width, height = (
            int(request.headers.get("x-width", "160")),
            int(request.headers.get("x-height", "120")),
        )
        checksum = request.headers.get("x-frame-fnv1a")
        if checksum and checksum.upper() != fnv1a(raw):
            raise ValueError("Frame checksum mismatch. Retry the capture.")
        image = decode_rgb565(raw, width, height, request.headers.get("x-byte-order", "little"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if request.headers.get("x-device-id"):
        return await camera_response(request, raw, image, infer, save_classification, get_session)
    result = await run_in_threadpool(infer, image)
    sid = request.headers.get("x-session-id")
    if sid:
        result = save_classification(sid, result)
    return {
        **result,
        "capture_id": request.headers.get("x-capture-id"),
        "fnv1a": fnv1a(raw),
    }


@app.get("/api/cleaner/tasks")
def tasks(user: User):
    cleaner(user)
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT a.*,b.name,b.township,b.address,b.latitude,b.longitude,b.food_fill,b.recycle_fill,b.reject_fill FROM alerts a JOIN bins b ON b.id=a.bin_id WHERE b.township=? ORDER BY a.status='resolved',a.created_at DESC",
                (user["township"],),
            )
        ]
    return {
        "tasks": rows,
        "shift": {
            "today": "09:00 – 18:00",
            "location": user["township"],
            "schedule": [
                {"day": "Monday – Friday", "hours": "09:00 – 18:00"},
                {"day": "Saturday", "hours": "09:00 – 14:00"},
                {"day": "Sunday", "hours": "Off duty"},
            ],
        },
    }


@app.post("/api/cleaner/tasks/{task_id}/acknowledge")
def acknowledge(task_id: str, user: User):
    cleaner(user)
    with connect() as db:
        row = db.execute(
            "SELECT a.* FROM alerts a JOIN bins b ON b.id=a.bin_id WHERE a.id=? AND b.township=?",
            (task_id, user["township"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Task not found in your area.")
        if row["status"] == "resolved":
            raise HTTPException(409, "This collection is already complete.")
        if row["acknowledged_by"] and row["acknowledged_by"] != user["id"]:
            raise HTTPException(409, "Another cleaner has accepted this task.")
        db.execute(
            "UPDATE alerts SET status='acknowledged',acknowledged_by=? WHERE id=?",
            (user["id"], task_id),
        )
    return {"ok": True}


@app.post("/api/cleaner/tasks/{task_id}/resolve")
def resolve_task(task_id: str, user: User):
    cleaner(user)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT a.* FROM alerts a JOIN bins b ON b.id=a.bin_id WHERE a.id=? AND b.township=?",
            (task_id, user["township"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Task not found in your area.")
        if row["status"] == "resolved":
            return {"ok": True}
        if row["acknowledged_by"] != user["id"]:
            raise HTTPException(409, "Accept this task before marking it cleared.")
        col = FILL_COLUMNS[row["compartment"]]
        if not settings.demo_mode:
            c = db.execute(
                "SELECT * FROM compartment_config WHERE bin_id=? AND category=?",
                (row["bin_id"], row["compartment"]),
            ).fetchone()
            station = db.execute("SELECT * FROM bins WHERE id=?", (row["bin_id"],)).fetchone()
            if (
                not c["valid"]
                or not c["sampled_at"]
                or (datetime.now(UTC) - datetime.fromisoformat(c["sampled_at"])).total_seconds()
                > settings.telemetry_max_age_seconds
                or station[col] >= c["threshold"]
            ):
                raise HTTPException(
                    409,
                    "Empty the compartment and wait for a fresh below-threshold sensor reading.",
                )
        if settings.demo_mode:
            db.execute(f"UPDATE bins SET {col}=0,last_seen=? WHERE id=?", (now(), row["bin_id"]))
            db.execute(
                "UPDATE compartment_config SET distance_cm=empty_cm,valid=1,sampled_at=? WHERE bin_id=? AND category=?",
                (now(), row["bin_id"], row["compartment"]),
            )
        db.execute(
            "UPDATE alerts SET status='resolved',resolved_at=? WHERE id=?",
            (now(), task_id),
        )
    return {"ok": True}


class DemoFill(BaseModel):
    bin_id: str
    compartment: Literal["food", "recyclable", "reject"]
    fill_percent: float = Field(ge=0, le=100, allow_inf_nan=False)


@app.post("/api/demo/fill")
def demo_fill(body: DemoFill, user: User):
    demo_only()
    with connect() as db:
        row = db.execute("SELECT * FROM bins WHERE id=?", (body.bin_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Station not found.")
        cfg = db.execute(
            "SELECT * FROM compartment_config WHERE bin_id=? AND category=?",
            (body.bin_id, body.compartment),
        ).fetchone()
        distance = cfg["empty_cm"] - body.fill_percent / 100 * (cfg["empty_cm"] - cfg["full_cm"])
    return apply_reading(
        Reading(
            device_id=row["device_id"],
            distance_cm=distance,
            compartment=body.compartment,
            event_id=token_hex(12),
        )
    )


@app.middleware("http")
async def upload_limit_and_headers(request: Request, call_next):
    if settings.public_preview and (
        request.url.path.startswith("/api/device/")
        or request.url.path in ("/telemetry", "/sorting/events", "/camera/upload")
    ):
        return JSONResponse(
            {"detail": "Hardware endpoints are disabled on the public visual preview."},
            status_code=404,
        )
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > 9 * 1024 * 1024):
        return JSONResponse(
            {"detail": "Upload is too large (maximum photo size 8 MB)."}, status_code=413
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.include_router(hardware_router(device_auth, check_full, get_session))
app.include_router(kiosk_router(current_user, resident))
app.include_router(smartbin_router(device_auth, check_full, complete_deposit, Confirm))


if settings.web_build_path:

    class PreviewFiles(StaticFiles):
        async def get_response(self, path, scope):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found."}, status_code=404)
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and (path == "kiosk" or path.startswith("kiosk/")):
                    return await super().get_response("index.html", scope)
                raise

    app.mount(
        "/",
        PreviewFiles(directory=str(Path(settings.web_build_path).resolve()), html=True),
        name="web-preview",
    )
