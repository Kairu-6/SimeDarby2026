"""Three-compartment capacity, stable tray weighing, and actuator receipt contract."""

import json
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from .config import settings
from .db import connect, now

Category = Literal["food", "recyclable", "reject"]
FILL_COLUMNS = {"food": "food_fill", "recyclable": "recycle_fill", "reject": "reject_fill"}


def capacity(db, station):
    result = {}
    for config in db.execute("SELECT * FROM compartment_config WHERE bin_id=?", (station["id"],)):
        category = config["category"]
        result[category] = {
            "fill_percent": station[FILL_COLUMNS[category]],
            "full": station[FILL_COLUMNS[category]] >= config["threshold"],
            "threshold_percent": config["threshold"],
            "sensor_valid": bool(config["valid"]),
            "distance_cm": config["distance_cm"],
            "sampled_at": config["sampled_at"],
        }
    return result


def check_capacity(db, station, route=None):
    if not station["online"]:
        raise HTTPException(409, "This station is offline.")
    levels = capacity(db, station)
    if settings.full_bin_blocks_station and any(c["full"] for c in levels.values()):
        raise HTTPException(409, "A compartment is full. This station is temporarily blocked.")
    if route and levels[route]["full"]:
        raise HTTPException(
            409, f"The {route} destination is full. Remove your item and use another station."
        )
    if not route and all(c["full"] for c in levels.values()):
        raise HTTPException(409, "All three destinations are full. Use another station.")


def live_state(db, bin_id):
    row = db.execute("SELECT * FROM device_state WHERE bin_id=?", (bin_id,)).fetchone()
    if (
        not row
        or (datetime.now(UTC) - datetime.fromisoformat(row["received_at"])).total_seconds()
        > settings.telemetry_max_age_seconds
    ):
        raise HTTPException(409, "Fresh device telemetry is required before operating the bin.")
    payload = json.loads(row["payload"])
    if not payload["scale"]["calibrated"] or not payload["scale"]["stable"]:
        raise HTTPException(409, "The HX711 must be calibrated and the plate weight stable.")
    controller = payload["controller"]
    if not controller["ready"] or controller["fault"] or controller["frame_age_ms"] > 1000:
        raise HTTPException(409, "The Nano controller is unavailable or reports a fault.")
    return row, payload


def verify_receipt(db, deposit, confirmation):
    if not confirmation.cycle_id or not confirmation.device_id:
        raise HTTPException(409, "Arm a device cycle and supply its cycle_id and device_id.")
    cycle = db.execute(
        "SELECT * FROM device_cycles WHERE id=? AND session_id=? AND device_id=?",
        (confirmation.cycle_id, deposit["id"], confirmation.device_id),
    ).fetchone()
    if not cycle or cycle["state"] != "armed":
        raise HTTPException(409, "No armed cycle matches this deposit and device.")
    if confirmation.route != cycle["route"] or confirmation.controller_cycle_id != cycle["id"]:
        raise HTTPException(
            409, "The completed Nano cycle or destination does not match the command."
        )
    if abs(confirmation.weight_kg - cycle["weight_kg"]) * 1000 > settings.weight_tolerance_g:
        raise HTTPException(409, "The credited weight must match the stable pre-push plate weight.")
    _, telemetry = live_state(db, deposit["bin_id"])
    controller = telemetry["controller"]
    if abs(telemetry["scale"]["weight_g"]) > settings.empty_plate_g:
        raise HTTPException(409, "The plate is not empty after the push. Do not credit this cycle.")
    if (
        controller["state"] != "idle"
        or controller["last_completed_cycle"] != cycle["id"]
        or controller["open_doors_mask"] != 0
    ):
        raise HTTPException(409, "Wait for the Nano DONE receipt and door-close commands.")
    db.execute(
        "UPDATE device_cycles SET state='confirmed',completion_event_id=? WHERE id=?",
        (confirmation.event_id, cycle["id"]),
    )
    return cycle["weight_kg"]


def active_cycle(db, sid):
    return db.execute(
        "SELECT * FROM device_cycles WHERE session_id=? AND state='armed'", (sid,)
    ).fetchone()


def prevent_cycle_mutation(db, sid):
    if active_cycle(db, sid):
        raise HTTPException(
            409, "A physical cycle is armed. Finish it or report a device fault first."
        )


class Level(BaseModel):
    compartment: Category
    distance_cm: float | None = Field(default=None, ge=0, le=500, allow_inf_nan=False)
    valid: bool = True

    @model_validator(mode="after")
    def check_reading(self):
        if self.valid and self.distance_cm is None:
            raise ValueError("A valid ultrasonic reading needs distance_cm.")
        return self


class Scale(BaseModel):
    weight_g: float = Field(ge=-5000, le=5000, allow_inf_nan=False)
    stable: bool
    calibrated: bool


class Controller(BaseModel):
    ready: bool
    state: Literal["idle", "opening", "pushing", "closing", "fault"]
    boot_id: str = Field(min_length=1, max_length=40)
    frame_age_ms: int = Field(ge=0, le=3600000)
    open_doors_mask: int = Field(ge=0, le=7)
    last_completed_cycle: str | None = Field(default=None, max_length=36)
    fault: str | None = Field(default=None, max_length=100)


class Telemetry(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    event_id: str = Field(min_length=8, max_length=100)
    boot_id: str = Field(min_length=1, max_length=40)
    sequence_no: int = Field(ge=0)
    uptime_ms: int = Field(ge=0)
    firmware_version: str = Field(max_length=40)
    levels: list[Level] = Field(min_length=3, max_length=3)
    scale: Scale
    controller: Controller

    @model_validator(mode="after")
    def all_compartments(self):
        if {level.compartment for level in self.levels} != set(FILL_COLUMNS):
            raise ValueError("Provide food, recyclable and reject exactly once.")
        return self


class Arm(BaseModel):
    device_id: str
    request_id: str = Field(min_length=8, max_length=100)
    telemetry_event_id: str


class CycleFault(BaseModel):
    device_id: str
    event_id: str = Field(min_length=8, max_length=100)
    reason: str = Field(min_length=1, max_length=100)


def receive_telemetry(body: Telemetry, check_full):
    payload = body.model_dump_json()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        station = db.execute("SELECT * FROM bins WHERE device_id=?", (body.device_id,)).fetchone()
        if not station:
            raise HTTPException(404, "Unknown device.")
        previous = db.execute(
            "SELECT * FROM device_packets WHERE event_id=?", (body.event_id,)
        ).fetchone()
        if previous:
            if previous["payload"] != payload:
                raise HTTPException(409, "Event ID reused for different telemetry.")
            return {"duplicate": True}
        state = db.execute("SELECT * FROM device_state WHERE bin_id=?", (station["id"],)).fetchone()
        if state and state["boot_id"] == body.boot_id and body.sequence_no <= state["sequence_no"]:
            raise HTTPException(409, "Out-of-order telemetry sequence.")
        for level in body.levels:
            cfg = db.execute(
                "SELECT * FROM compartment_config WHERE bin_id=? AND category=?",
                (station["id"], level.compartment),
            ).fetchone()
            db.execute(
                "UPDATE compartment_config SET distance_cm=?,valid=?,sampled_at=? WHERE bin_id=? AND category=?",
                (level.distance_cm, level.valid, now(), station["id"], level.compartment),
            )
            if level.valid:
                fill = round(
                    max(
                        0,
                        min(
                            100,
                            (cfg["empty_cm"] - level.distance_cm)
                            / (cfg["empty_cm"] - cfg["full_cm"])
                            * 100,
                        ),
                    ),
                    1,
                )
                db.execute(
                    f"UPDATE bins SET {FILL_COLUMNS[level.compartment]}=? WHERE id=?",
                    (fill, station["id"]),
                )
        db.execute("UPDATE bins SET online=1,last_seen=? WHERE id=?", (now(), station["id"]))
        db.execute(
            "INSERT INTO device_packets VALUES (?,?,?,?)",
            (body.event_id, station["id"], payload, now()),
        )
        db.execute(
            "INSERT OR REPLACE INTO device_state VALUES (?,?,?,?,?,?)",
            (station["id"], body.boot_id, body.sequence_no, now(), body.event_id, payload),
        )
        check_full(db, station["id"])
        updated = db.execute("SELECT * FROM bins WHERE id=?", (station["id"],)).fetchone()
        return {"duplicate": False, "received_at": now(), "capacity": capacity(db, updated)}


def authorize_cycle(sid: str, body: Arm, get_session, command_id: str | None = None):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        session = get_session(db, sid)
        previous = db.execute(
            "SELECT * FROM device_cycles WHERE session_id=? OR request_id=?",
            (sid, body.request_id),
        ).fetchone()
        if previous:
            if (
                previous["session_id"] != sid
                or previous["device_id"] != body.device_id
                or previous["request_id"] != body.request_id
            ):
                raise HTTPException(
                    409, "This session or request already has a different physical cycle."
                )
            return {
                **dict(previous),
                "executable": previous["state"] == "armed" and previous["execute_before"] > now(),
                "replayed": True,
            }
        if (
            session["status"] != "classified"
            or session["category"] not in FILL_COLUMNS
            or session["model"] == "demo-simulation"
        ):
            raise HTTPException(409, "A real accepted image classification is required.")
        if (
            not session["classified_at"]
            or (
                datetime.now(UTC) - datetime.fromisoformat(session["classified_at"])
            ).total_seconds()
            > settings.classification_max_age_seconds
        ):
            raise HTTPException(409, "Classification is too old. Capture the current item again.")
        station = db.execute(
            "SELECT * FROM bins WHERE id=? AND device_id=?", (session["bin_id"], body.device_id)
        ).fetchone()
        if not station:
            raise HTTPException(409, "This device does not own this station session.")
        check_capacity(db, station, session["category"])
        state, packet = live_state(db, station["id"])
        if state["event_id"] != body.telemetry_event_id:
            raise HTTPException(409, "Arm using the latest accepted telemetry event.")
        if packet["controller"]["state"] != "idle" or packet["controller"]["open_doors_mask"]:
            raise HTTPException(409, "Close all doors and stop the pusher before arming.")
        selected = next(
            level for level in packet["levels"] if level["compartment"] == session["category"]
        )
        if not selected["valid"] or not capacity(db, station)[session["category"]]["sensor_valid"]:
            raise HTTPException(409, "The selected bin's ultrasonic sensor has no valid reading.")
        grams = packet["scale"]["weight_g"]
        if not settings.min_item_g <= grams <= settings.max_item_kg * 1000:
            raise HTTPException(
                409, "The stable plate weight is outside the configured item range."
            )
        if (datetime.fromisoformat(session["expires_at"]) - datetime.now(UTC)).total_seconds() < 30:
            raise HTTPException(409, "Session is about to expire. Start a new deposit.")
        cid = command_id or token_hex(8)
        deadline = (datetime.now(UTC) + timedelta(seconds=15)).isoformat()
        db.execute(
            "INSERT INTO device_cycles (id,session_id,device_id,request_id,route,weight_kg,created_at,execute_before) VALUES (?,?,?,?,?,?,?,?)",
            (
                cid,
                sid,
                body.device_id,
                body.request_id,
                session["category"],
                grams / 1000,
                now(),
                deadline,
            ),
        )
        return {
            **dict(db.execute("SELECT * FROM device_cycles WHERE id=?", (cid,)).fetchone()),
            "executable": True,
            "replayed": False,
        }


def router(device_auth, check_full, get_session):
    routes = APIRouter(prefix="/api/device", tags=["IoT v2"])

    @routes.get("/bins/{bin_id}/config")
    def config(bin_id: str, device: Annotated[None, Depends(device_auth)]):
        with connect() as db:
            station = db.execute("SELECT * FROM bins WHERE id=?", (bin_id,)).fetchone()
            if not station:
                raise HTTPException(404, "Station not found.")
            compartments = {
                c["category"]: {
                    "empty_cm": c["empty_cm"],
                    "full_cm": c["full_cm"],
                    "threshold_percent": c["threshold"],
                }
                for c in db.execute("SELECT * FROM compartment_config WHERE bin_id=?", (bin_id,))
            }
            return {
                "protocol_version": 2,
                "device_id": station["device_id"],
                "bin_id": bin_id,
                "compartments": compartments,
                "block_whole_station_if_any_full": settings.full_bin_blocks_station,
                "scale": {
                    "load_cell_capacity_kg": 5,
                    "max_item_kg": settings.max_item_kg,
                    "min_item_g": settings.min_item_g,
                    "empty_plate_g": settings.empty_plate_g,
                    "tolerance_g": settings.weight_tolerance_g,
                },
                "points_per_kg": {
                    "food": settings.food_points_per_kg,
                    "recyclable": settings.recyclable_points_per_kg,
                    "reject": 0,
                },
                "command_lease_ms": 15000,
                "pusher": {
                    "mode": "continuous_rotation",
                    "stop_condition": "stable_empty_plate",
                    "maximum_run_ms": 3000,
                },
                "telemetry_max_age_seconds": settings.telemetry_max_age_seconds,
                "uart": {
                    "baud": 38400,
                    "protocol": "SL2 ASCII lines",
                    "heartbeat_ms": 250,
                    "watchdog_ms": 1200,
                },
                "capacity": capacity(db, station),
            }

    @routes.post("/telemetry")
    def telemetry(body: Telemetry, device: Annotated[None, Depends(device_auth)]):
        return receive_telemetry(body, check_full)

    @routes.post("/deposits/{sid}/arm")
    def arm(sid: str, body: Arm, device: Annotated[None, Depends(device_auth)]):
        return authorize_cycle(sid, body, get_session)

    @routes.post("/cycles/{cycle_id}/fault")
    def fault(cycle_id: str, body: CycleFault, device: Annotated[None, Depends(device_auth)]):
        with connect() as db:
            cycle = db.execute(
                "SELECT * FROM device_cycles WHERE id=? AND device_id=?", (cycle_id, body.device_id)
            ).fetchone()
            if not cycle:
                raise HTTPException(404, "Cycle not found.")
            if cycle["state"] == "confirmed":
                raise HTTPException(409, "This cycle has already credited its deposit.")
            db.execute(
                "UPDATE device_cycles SET state='failed',fault=?,completion_event_id=? WHERE id=?",
                (body.reason, body.event_id, cycle_id),
            )
            db.execute(
                "UPDATE deposits SET status='cancelled' WHERE id=? AND status!='completed'",
                (cycle["session_id"],),
            )
            return {"ok": True, "points": 0, "action": "stop_pusher_close_doors_and_inspect"}

    @routes.get("/cycles/{cycle_id}")
    def cycle_status(cycle_id: str, device: Annotated[None, Depends(device_auth)]):
        with connect() as db:
            row = db.execute(
                "SELECT c.id,c.state,c.route,c.session_id,d.status deposit_status,d.points FROM device_cycles c JOIN deposits d ON d.id=c.session_id WHERE c.id=?",
                (cycle_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Cycle not found.")
            return dict(row)

    return routes
