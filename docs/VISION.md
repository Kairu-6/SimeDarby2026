# Computer vision

`backend/app/vision.py` runs the real `openai/clip-vit-base-patch32` model locally through Transformers and PyTorch. No paid vision API or API key is needed. The implementation compares an image with prompts for food scraps, recyclables, mixed household waste and hold conditions. It sums prompt scores by category and routes food/recyclable/reject only above `VISION_THRESHOLD` (default 0.60). Confident reject waste goes to the reject bin for zero points. Low-confidence, empty, hand/background or unsafe-looking scenes return `route: hold`.

This follows the [Transformers zero-shot image classification approach](https://huggingface.co/docs/transformers/en/tasks/zero_shot_image_classification). Prompt scores are relative model scores and are not calibrated probabilities of safe recyclability.

## Start and verify

From `backend/`:

```powershell
$env:HF_HOME = Join-Path (Get-Location) '..\.cache\huggingface'
uv run --extra vision python scripts/warm_model.py
```

For an image check, sign in to the app and use **Check an item with a photo**, or call `POST /api/vision/classify` with a bearer token and multipart `file`. This endpoint returns advice only. A real deposit uses `POST /api/device/deposits/{session_id}/classify` with `X-Device-Key`; the result is attached to the active session. A later physical weight confirmation is required for points.

The ESP32 RGB565 camera can instead call `POST /camera/upload` with `X-Session-Id`. It preserves the width/height, byte-order and FNV-1a header convention from the existing test code. Frames are decoded to RGB888 before inference. JPEG/PNG input honours EXIF rotation and is limited to 8 MB and 16 megapixels. The new service does not save uploaded resident photos to disk.

If the optional vision dependencies or cached model are unavailable, classification returns an explicit 503. There is no automatic mock fallback. Only `/api/demo/...` simulates a chosen category, and all such responses say `model: demo-simulation` and `is_demo: true`.

## Evaluate with your camera

Collect labelled examples from the actual enclosure, using your camera's lighting, angle and resolution:

```text
dataset/
  food/          # fruit peels, rice, leftovers
  recyclable/    # rinsed bottles, cans, dry paper
  reject/        # greasy packaging, mixed household waste
  hold/          # batteries, sharp objects, empty scenes, hands, unclear items
```

```powershell
uv run --extra vision python scripts/evaluate_model.py ../dataset
```

The evaluator writes per-image results, routing accuracy and a four-route confusion matrix to `backend/data/model-evaluation.json`. It scores `route`, so holding an item cannot be mistaken for successful reject routing. Review false accepts of hold images as well as overall accuracy. Keep a held-out set from different sessions and lighting. Adjust the threshold/prompts using a validation set, then evaluate the held-out set once. If performance is insufficient, replace the classifier with a model fine-tuned on the labelled bin images while preserving the API result shape.

The existing camera capture was successfully passed through actual CLIP inference during verification. It produced a hold decision for the unclear scene. This confirms decoding/inference execution; it does not establish sorting accuracy on a labelled waste dataset.
