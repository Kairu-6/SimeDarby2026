"""Contract tester: real image inference, explicitly simulated scale/Nano evidence."""

import argparse
import os
import uuid
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--bin", default="ELM-01")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--weight", type=float, default=0.5)
    parser.add_argument("--demo", choices=["food", "recyclable", "reject"])
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--compartment", choices=["food", "recyclable", "reject"], default="food")
    args = parser.parse_args()
    if not 0.01 <= args.weight <= 4:
        parser.error("Weight must be 0.01–4 kg for this provisional 5 kg load-cell setup.")
    if args.image and args.demo:
        parser.error("Choose --image or --demo.")
    device = {"X-Device-Key": os.environ.get("DEVICE_API_KEY", "hackathon-device-key-change-me")}
    boot = uuid.uuid4().hex
    sequence = 0
    with httpx.Client(base_url=args.url, timeout=180) as client:

        def checked(response):
            if response.is_error:
                raise RuntimeError(f"{response.status_code}: {response.text}")
            return response.json()

        cfg = checked(client.get(f"/api/device/bins/{args.bin}/config", headers=device))
        device_id = cfg["device_id"]

        def telemetry(weight, done=None, full=None):
            nonlocal sequence
            sequence += 1
            event = f"sim-{boot}-{sequence}"
            levels = []
            for name, geometry in cfg["compartments"].items():
                levels.append(
                    {
                        "compartment": name,
                        "distance_cm": geometry["full_cm"]
                        if name == full
                        else geometry["empty_cm"],
                        "valid": True,
                    }
                )
            checked(
                client.post(
                    "/api/device/telemetry",
                    headers=device,
                    json={
                        "device_id": device_id,
                        "event_id": event,
                        "boot_id": boot,
                        "sequence_no": sequence,
                        "uptime_ms": sequence * 1000,
                        "firmware_version": "simulator-v2",
                        "levels": levels,
                        "scale": {"weight_g": weight, "stable": True, "calibrated": True},
                        "controller": {
                            "ready": True,
                            "state": "idle",
                            "boot_id": "sim-nano-" + boot[:8],
                            "frame_age_ms": 0,
                            "open_doors_mask": 0,
                            "last_completed_cycle": done,
                            "fault": None,
                        },
                    },
                )
            )
            return event

        if args.full:
            telemetry(0, full=args.compartment)
            print(f"SIMULATED {args.compartment} full; cleaner alert contract exercised.")
            return
        if not args.image and not args.demo:
            parser.error(
                "Choose --image for real inference or --demo for simulated classification."
            )
        auth = checked(
            client.post(
                "/api/auth/login",
                json={
                    "email": "resident@simeloop.demo",
                    "password": "Loop123!",
                },
            )
        )
        headers = {"Authorization": "Bearer " + auth["token"]}
        session = checked(client.post("/api/deposits", headers=headers, json={"bin_id": args.bin}))
        sid = session["id"]
        if args.demo:
            prediction = checked(
                client.post(
                    f"/api/demo/deposits/{sid}/classify",
                    headers=headers,
                    json={"category": args.demo},
                )
            )
        else:
            with args.image.open("rb") as image:
                prediction = checked(
                    client.post(
                        f"/api/device/deposits/{sid}/classify",
                        headers=device,
                        files={"file": (args.image.name, image)},
                    )
                )
        print("Classification:", prediction)
        if not prediction["accepted"]:
            print("HOLD: no movement or points.")
            checked(client.post(f"/api/deposits/{sid}/cancel", headers=headers))
            return
        confirmation = {"event_id": "sim-complete-" + boot, "weight_kg": args.weight}
        if not args.demo:
            event = telemetry(args.weight * 1000)
            cycle = checked(
                client.post(
                    f"/api/device/deposits/{sid}/arm",
                    headers=device,
                    json={
                        "device_id": device_id,
                        "request_id": "sim-arm-" + boot,
                        "telemetry_event_id": event,
                    },
                )
            )
            telemetry(0, done=cycle["id"])
            confirmation.update(
                device_id=device_id,
                cycle_id=cycle["id"],
                controller_cycle_id=cycle["id"],
                route=cycle["route"],
            )
        path = "demo" if args.demo else "device"
        result = checked(
            client.post(
                f"/api/{path}/deposits/{sid}/confirm",
                headers=headers if args.demo else device,
                json=confirmation,
            )
        )
        print("SIMULATED physical deposit; no hardware moved:", result)


if __name__ == "__main__":
    main()
