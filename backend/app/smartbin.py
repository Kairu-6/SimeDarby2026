"""Bridge the supplied UUID / NDJSON firmware contract to verified deposits."""

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from .db import connect, now
from .hardware import Arm, Telemetry, authorize_cycle, receive_telemetry

BIN_ROUTES = {"bin_1": "recyclable", "bin_2": "food", "bin_3": "reject"}
ROUTE_BINS = {value: key for key, value in BIN_ROUTES.items()}


def station_for(db, device_id):
    # The user's current physical controller belongs to the seeded Elmina station.
    canonical = "ELM-01" if device_id == "esp32-01" else device_id
    row = db.execute("SELECT * FROM bins WHERE device_id=?", (canonical,)).fetchone()
    if not row:
        raise HTTPException(404, "Unknown device.")
    return row


class Sensor(BaseModel):
    sensor_id: str = Field(max_length=60)
    bin_id: Literal["bin_1", "bin_2", "bin_3"]
    distance_cm: float | None = Field(default=None, ge=0, le=500, allow_inf_nan=False)
    valid: bool
    sample_age_ms: int = Field(default=3600000, ge=0)


class Weight(BaseModel):
    raw: int | None = None
    weight_g: float | None = Field(default=None, ge=-5000, le=5000, allow_inf_nan=False)
    calibrated: bool
    healthy: bool
    stable: bool = False
    scope: Literal["inspection_plate"] | None = None


class Packet(BaseModel):
    device_id: str = Field(max_length=100)
    event_id: str = Field(min_length=8, max_length=100)
    boot_id: str = Field(min_length=1, max_length=40)
    sequence_no: int = Field(ge=0)
    device_uptime_ms: int = Field(ge=0)
    nano_connected: bool
    nano_boot_id: str = Field(min_length=1, max_length=40)
    nano_frame_age_ms: int = Field(ge=0, le=3600000)
    ultrasonic: list[Sensor] = Field(min_length=3, max_length=3)
    weight: Weight
    actuator_state: Literal["idle", "opening", "pushing", "closing", "fault"]
    open_doors_mask: int = Field(ge=0, le=7)
    last_completed_command: UUID | None = None
    error_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def all_bins(self):
        if {x.bin_id for x in self.ultrasonic} != set(BIN_ROUTES):
            raise ValueError("Provide bin_1, bin_2 and bin_3 exactly once.")
        return self


class SortEvent(BaseModel):
    event_id: UUID
    device_id: str = Field(max_length=100)
    command_id: UUID
    status: Literal["accepted", "started", "completed", "failed"]
    error_code: str | None = Field(default=None, max_length=100)
    device_uptime_ms: int = Field(ge=0)


def try_complete(command_id, complete_deposit, Confirm):
    with connect() as db:
        cycle = db.execute("SELECT * FROM device_cycles WHERE id=?", (command_id,)).fetchone()
        receipt = db.execute(
            "SELECT event_id FROM sorting_events WHERE command_id=? AND status='completed' ORDER BY created_at DESC LIMIT 1",
            (command_id,),
        ).fetchone()
    if not cycle or cycle["state"] != "armed" or not receipt:
        return None
    try:
        return complete_deposit(
            cycle["session_id"],
            Confirm(
                event_id=receipt["event_id"],
                device_id=cycle["device_id"],
                cycle_id=command_id,
                controller_cycle_id=command_id,
                route=cycle["route"],
                weight_kg=cycle["weight_kg"],
            ),
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # Timed Nano completion alone cannot earn points. Await fresh stable-empty telemetry.
        return None


async def camera_response(request, raw, image, infer, save_classification, get_session):
    device_id = request.headers.get("x-device-id", "")
    sid = request.headers.get("x-session-id", "")
    capture_id = request.headers.get("x-capture-id", "")
    if not sid or not 8 <= len(capture_id) <= 100:
        raise HTTPException(422, "Supply X-Session-Id and a unique X-Capture-ID.")
    digest = hashlib.sha256(
        raw + f"{image.width}:{image.height}:{request.headers.get('x-byte-order')}".encode()
    ).hexdigest()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        station = station_for(db, device_id)
        session = get_session(db, sid)
        if session["bin_id"] != station["id"]:
            raise HTTPException(403, "This device cannot capture another station's session.")
        previous = db.execute(
            "SELECT * FROM smartbin_captures WHERE capture_id=?", (capture_id,)
        ).fetchone()
        if previous:
            if (
                previous["digest"] != digest
                or previous["session_id"] != sid
                or previous["device_id"] != device_id
            ):
                raise HTTPException(409, "Capture ID reused for a different frame or session.")
            if not previous["response"]:
                raise HTTPException(
                    409, "This frame is still being processed. Retry the same frame later."
                )
            response = json.loads(previous["response"])
            command = response["decision"]["command_id"]
            if command:
                cycle = db.execute("SELECT * FROM device_cycles WHERE id=?", (command,)).fetchone()
                if cycle["state"] != "armed" or cycle["execute_before"] <= now():
                    response["decision"] = {
                        "action": "hold",
                        "bin_id": None,
                        "command_id": None,
                        "reason": "The original command is already final or its start lease expired. Never replay it.",
                    }
            return response
        if session["status"] not in ("pending", "classified") or not session["capture_requested"]:
            raise HTTPException(
                409,
                "Wait for the resident to claim the QR and press Check my items on the station screen.",
            )
        db.execute(
            "INSERT INTO smartbin_captures VALUES (?,?,?,?,NULL,?)",
            (capture_id, device_id, sid, digest, now()),
        )
    try:
        result = await run_in_threadpool(infer, image)
        result = save_classification(sid, result)
        decision = {
            "action": "hold",
            "bin_id": None,
            "command_id": None,
            "reason": result.get("message", "Item held for inspection."),
        }
        if result["accepted"]:
            with connect() as db:
                state = db.execute(
                    "SELECT * FROM device_state WHERE bin_id=?", (station["id"],)
                ).fetchone()
            if state:
                try:
                    cycle = authorize_cycle(
                        sid,
                        Arm(
                            device_id=station["device_id"],
                            request_id="capture-"
                            + hashlib.sha256(capture_id.encode()).hexdigest()[:40],
                            telemetry_event_id=state["event_id"],
                        ),
                        get_session,
                        str(uuid4()),
                    )
                    if cycle["executable"]:
                        decision = {
                            "action": "sort",
                            "bin_id": ROUTE_BINS[cycle["route"]],
                            "command_id": cycle["id"],
                            "reason": None,
                            "weight_kg": cycle["weight_kg"],
                            "execute_before": cycle["execute_before"],
                        }
                except HTTPException as exc:
                    decision["reason"] = exc.detail
            else:
                decision["reason"] = (
                    "Waiting for fresh calibrated scale and Nano telemetry. The door stays closed."
                )
        response = {
            **result,
            "status": "received",
            "capture_id": capture_id,
            "width": image.width,
            "height": image.height,
            "bytes_received": len(raw),
            "classification": {
                "label": result["category"],
                "confidence": result["confidence"],
                "mode": "mock" if result.get("is_demo") else "real",
                "model_version": result["model"],
            },
            "decision": decision,
        }
        with connect() as db:
            db.execute(
                "UPDATE smartbin_captures SET response=? WHERE capture_id=?",
                (json.dumps(response), capture_id),
            )
            db.execute(
                "UPDATE deposits SET verification_message=? WHERE id=?",
                (
                    decision["reason"]
                    if decision["action"] == "hold"
                    else "Items verified. Sorting into the selected bin.",
                    sid,
                ),
            )
            if decision["action"] == "hold":
                db.execute(
                    "UPDATE deposits SET status='pending',capture_requested=0 WHERE id=? AND status='classified'",
                    (sid,),
                )
        return response
    except Exception:
        with connect() as db:
            db.execute(
                "DELETE FROM smartbin_captures WHERE capture_id=? AND response IS NULL",
                (capture_id,),
            )
            db.execute(
                "UPDATE deposits SET capture_requested=0,verification_message='The camera check could not finish. Keep the door closed and try again.' WHERE id=? AND status='pending'",
                (sid,),
            )
        raise


def router(device_auth, check_full, complete_deposit, Confirm):
    routes = APIRouter(tags=["Current SmartBin firmware"])

    @routes.post("/telemetry")
    def telemetry(body: Packet, auth: Annotated[None, Depends(device_auth)]):
        with connect() as db:
            station = station_for(db, body.device_id)
        healthy = (
            body.weight.healthy
            and body.weight.raw not in (None, 0)
            and body.weight.scope == "inspection_plate"
        )
        translated = Telemetry(
            device_id=station["device_id"],
            event_id=body.event_id,
            boot_id=body.boot_id,
            sequence_no=body.sequence_no,
            uptime_ms=body.device_uptime_ms,
            firmware_version="smartbin-0.3.0",
            levels=[
                {
                    "compartment": BIN_ROUTES[s.bin_id],
                    "distance_cm": s.distance_cm,
                    "valid": s.valid and s.sample_age_ms <= 2500 and s.distance_cm is not None,
                }
                for s in body.ultrasonic
            ],
            scale={
                "weight_g": body.weight.weight_g or 0,
                "stable": healthy and body.weight.stable,
                "calibrated": healthy
                and body.weight.calibrated
                and body.weight.weight_g is not None,
            },
            controller={
                "ready": body.nano_connected,
                "state": body.actuator_state,
                "boot_id": body.nano_boot_id,
                "frame_age_ms": body.nano_frame_age_ms,
                "open_doors_mask": body.open_doors_mask,
                "last_completed_cycle": str(body.last_completed_command)
                if body.last_completed_command
                else None,
                "fault": body.error_code,
            },
        )
        result = receive_telemetry(translated, check_full)
        completed = (
            try_complete(str(body.last_completed_command), complete_deposit, Confirm)
            if body.last_completed_command
            else None
        )
        return {**result, "deposit": completed}

    @routes.post("/sorting/events")
    def sorting_event(body: SortEvent, auth: Annotated[None, Depends(device_auth)]):
        cid, eid, payload = str(body.command_id), str(body.event_id), body.model_dump_json()
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            station = station_for(db, body.device_id)
            cycle = db.execute(
                "SELECT * FROM device_cycles WHERE id=? AND device_id=?",
                (cid, station["device_id"]),
            ).fetchone()
            if not cycle:
                raise HTTPException(404, "Unknown command for this device.")
            old = db.execute("SELECT * FROM sorting_events WHERE event_id=?", (eid,)).fetchone()
            if old and old["payload"] != payload:
                raise HTTPException(409, "Event ID reused for different data.")
            if not old:
                if body.status == "failed" and cycle["state"] == "confirmed":
                    raise HTTPException(409, "This deposit is already credited.")
                db.execute(
                    "INSERT INTO sorting_events VALUES (?,?,?,?,?)",
                    (eid, cid, body.status, payload, now()),
                )
                if body.status == "failed":
                    db.execute(
                        "UPDATE device_cycles SET state='failed',fault=? WHERE id=? AND state='armed'",
                        (body.error_code or "DEVICE_FAULT", cid),
                    )
                    db.execute(
                        "UPDATE deposits SET status='cancelled',verification_message=? WHERE id=? AND status!='completed'",
                        (
                            body.error_code or "Device fault. Please ask for help.",
                            cycle["session_id"],
                        ),
                    )
        completed = try_complete(cid, complete_deposit, Confirm)
        return {
            "ok": True,
            "duplicate": bool(old),
            "deposit": completed,
            "awaiting_empty_plate": body.status == "completed"
            and completed is None
            and cycle["state"] == "armed",
        }

    return routes
