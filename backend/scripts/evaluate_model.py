"""Evaluate camera routing in dataset/{food,recyclable,reject,hold}/*.jpg.

uv run --extra vision python scripts/evaluate_model.py ../dataset
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.vision import classifier, decode_image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/model-evaluation.json"))
    args = parser.parse_args()
    categories = ("food", "recyclable", "reject", "hold")
    confusion = {label: Counter({category: 0 for category in categories}) for label in categories}
    results = []
    for expected in categories:
        for image in sorted((args.dataset / expected).glob("*")):
            if image.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            result = classifier.classify(decode_image(image.read_bytes()))
            confusion[expected][result["route"]] += 1
            results.append({"path": str(image), "expected": expected, **result})
    if not results:
        parser.error(
            "No images found. Put labelled captures in food/, recyclable/, reject/, hold/."
        )
    summary = {
        "count": len(results),
        "routing_accuracy": sum(r["expected"] == r["route"] for r in results) / len(results),
        "confusion": confusion,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    print(f"Full results: {args.output}")


if __name__ == "__main__":
    main()
