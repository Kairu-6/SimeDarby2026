"""Run from backend: uv run --extra vision python scripts/warm_model.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.vision import classifier

classifier.load()
print("CLIP is downloaded and ready for image inference.")
