"""Apply measured bin geometry without resetting residents, rewards or sessions."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import connect, seed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    if set(cfg["compartments"]) != {"food", "recyclable", "reject"}:
        parser.error("Provide all three compartments.")
    for category, dimensions in cfg["compartments"].items():
        if (
            not 0 <= dimensions["full_cm"] < dimensions["empty_cm"] <= 500
            or not 0 < dimensions["threshold_percent"] <= 100
        ):
            parser.error(f"Invalid geometry for {category}.")
    seed()
    with connect() as db:
        if not db.execute("SELECT id FROM bins WHERE id=?", (cfg["bin_id"],)).fetchone():
            parser.error("Unknown station ID.")
        for category, dimensions in cfg["compartments"].items():
            db.execute(
                "UPDATE compartment_config SET empty_cm=?,full_cm=?,threshold=?,valid=0,sampled_at=NULL WHERE bin_id=? AND category=?",
                (
                    dimensions["empty_cm"],
                    dimensions["full_cm"],
                    dimensions["threshold_percent"],
                    cfg["bin_id"],
                    category,
                ),
            )
    print("Calibration saved. Send fresh telemetry before arming a physical cycle.")


if __name__ == "__main__":
    main()
