#!/usr/bin/env python3
"""Auto-caption Rosa training images using Ollama gemma3:12b vision model.
Saves .txt caption files alongside each image for LoRA training."""

import base64
import json
import logging
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DATASET_DIR = Path("/opt/anime-studio/datasets/rosa/images")
OLLAMA_URL = "http://localhost:11434"
MODEL = "gemma3:12b"

SYSTEM_PROMPT = """You are captioning training images for an AI character named Rosa.
For each image, write a single detailed caption describing what you see.

RULES:
- Always start with "photo of rosa,"
- Always include: "mestiza woman, warm brown skin, green eyes, indigenous mexican features, freckles"
- Describe her expression, pose, clothing, setting, lighting
- Use natural language, not tags
- Keep it to 1-2 sentences
- Do NOT mention that this is AI-generated"""


def caption_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    payload = json.dumps({
        "model": MODEL,
        "prompt": "Describe this photo of a woman named Rosa for AI training. Be specific about her expression, pose, clothing, setting, and lighting. Start with 'photo of rosa,'",
        "system": SYSTEM_PROMPT,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 150}
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=60)
    result = json.loads(resp.read())
    caption = result.get("response", "").strip()

    # Ensure it starts with the trigger
    if not caption.lower().startswith("photo of rosa"):
        caption = "photo of rosa, " + caption

    # Ensure identity anchors are present
    anchors = "mestiza woman, warm brown skin, green eyes, indigenous mexican features, freckles"
    if "mestiza" not in caption.lower():
        caption = caption.rstrip(". ") + ", " + anchors

    return caption


def main():
    images = sorted(DATASET_DIR.glob("*.png"))
    logger.info(f"Captioning {len(images)} images with {MODEL}")

    for i, img_path in enumerate(images):
        txt_path = img_path.with_suffix(".txt")
        if txt_path.exists():
            logger.info(f"  [{i+1}/{len(images)}] {img_path.name} — already captioned, skipping")
            continue

        try:
            caption = caption_image(img_path)
            txt_path.write_text(caption)
            logger.info(f"  [{i+1}/{len(images)}] {img_path.name} — {caption[:80]}...")
        except Exception as e:
            logger.warning(f"  [{i+1}/{len(images)}] {img_path.name} — FAILED: {e}")
            # Write fallback caption
            fallback = "photo of rosa, a beautiful mestiza woman in her early 30s, striking green eyes, warm brown skin with freckles, long dark hair, indigenous mexican features, high cheekbones, photorealistic"
            txt_path.write_text(fallback)

    captioned = len(list(DATASET_DIR.glob("*.txt")))
    logger.info(f"Done — {captioned} caption files written")


if __name__ == "__main__":
    main()
