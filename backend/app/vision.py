"""Real image inference with CLIP. No colour/filename heuristics or silent mock fallback."""

import io
from threading import Lock

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import settings

LABELS = {
    "food": [
        "food scraps, leftover rice and vegetables",
        "fruit peels and banana skins",
        "leftover meat and bread",
    ],
    "recyclable": [
        "an empty clean plastic bottle",
        "a clean aluminium drink can",
        "clean dry paper and cardboard",
        "an empty glass bottle",
    ],
    "reject": [
        "food scraps mixed with plastic bottles, wrappers or drink cans",
        "recyclable containers mixed with leftover food and banana peels",
        "a dirty greasy plastic food wrapper",
        "mixed unsorted trash in a bag",
        "non-recyclable household rubbish",
    ],
    "hold": [
        "a battery or electronic waste",
        "a sharp object, broken glass or a chemical container",
        "a person's hand with no waste item",
        "an empty bin with no waste",
        "a non-waste object, furniture, a room or an animal",
    ],
}


class VisionUnavailable(Exception):
    pass


class WasteClassifier:
    def __init__(self):
        self.processor = None
        self.model = None
        self.lock = Lock()
        self.error = None

    def load(self):
        if not settings.vision_enabled:
            raise VisionUnavailable(
                "Image model is disabled. Enable VISION_ENABLED and install the vision extra."
            )
        if self.model is not None:
            return
        try:
            from transformers import AutoProcessor, CLIPModel

            self.processor = AutoProcessor.from_pretrained(settings.vision_model)
            self.model = CLIPModel.from_pretrained(settings.vision_model).eval()
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            raise VisionUnavailable(
                "Image model is not ready. Run scripts/warm_model.py with the vision extra installed."
            ) from exc

    def classify(self, image: Image.Image) -> dict:
        import torch

        with self.lock:
            self.load()
            prompts = [label for labels in LABELS.values() for label in labels]
            inputs = self.processor(
                text=[f"a photo of {x}" for x in prompts],
                images=image.convert("RGB"),
                return_tensors="pt",
                padding=True,
            )
            with torch.inference_mode():
                scores = self.model(**inputs).logits_per_image[0].softmax(dim=0).tolist()
        grouped = {}
        offset = 0
        for category, labels in LABELS.items():
            grouped[category] = sum(scores[offset : offset + len(labels)])
            offset += len(labels)
        category = max(grouped, key=grouped.get)
        confidence = grouped[category]
        best = prompts[scores.index(max(scores))]
        accepted = category != "hold" and confidence >= settings.vision_threshold
        return {
            "category": category if accepted else "reject",
            "material": best,
            "confidence": round(confidence, 4),
            "scores": grouped,
            "model": settings.vision_model,
            "is_demo": False,
            "accepted": accepted,
            "reward_eligible": accepted and category != "reject",
            "route": category if accepted else "hold",
            "message": (
                "Place the item in the food waste compartment."
                if category == "food"
                else "Place the clean item in the recycling compartment."
                if category == "recyclable"
                else "Mixed waste goes to the reject bin. This deposit earns no points."
            )
            if accepted
            else "Please remove the item and check it. Use one clearly visible, pre-sorted item at a time.",
        }


classifier = WasteClassifier()


def decode_image(data: bytes) -> Image.Image:
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Photo must be smaller than 8 MB.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > 16_000_000 or min(img.size) < 16:
                raise ValueError(
                    "Image dimensions must be at least 16 × 16 and at most 16 megapixels."
                )
            img.load()
            return ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Upload a valid JPEG or PNG photo.") from exc


def decode_rgb565(raw: bytes, width: int, height: int, byte_order: str) -> Image.Image:
    if not (1 <= width <= 640 and 1 <= height <= 480) or byte_order not in (
        "little",
        "big",
    ):
        raise ValueError("Invalid RGB565 dimensions or byte order.")
    if len(raw) != width * height * 2:
        raise ValueError("RGB565 frame length does not match dimensions.")
    pixels = np.frombuffer(raw, dtype="<u2" if byte_order == "little" else ">u2").reshape(
        height, width
    )
    r, g, b = (pixels >> 11) & 31, (pixels >> 5) & 63, pixels & 31
    return Image.fromarray(
        np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], axis=-1).astype(
            np.uint8
        )
    )


def fnv1a(raw: bytes) -> str:
    value = 2166136261
    for byte in raw:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return f"{value:08X}"
