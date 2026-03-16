"""Match shots to custom-trained motion LoRAs based on prompt/description keywords.

Reads video_motion_loras from lora_catalog.yaml and scores each against the
shot's motion_prompt + description to find the best motion LoRA match.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")


def _load_catalog() -> dict:
    from .catalog_loader import load_catalog
    return load_catalog().get("video_motion_loras") or {}


def match_motion_lora(
    motion_prompt: str = "",
    description: str = "",
    content_rating: str = "R",
) -> tuple[str | None, float]:
    """Return (lora_file, strength) for the best matching motion LoRA.

    Returns (None, 0.0) if no match found or no tags hit.
    Requires at least 1 tag match to return a result.
    """
    catalog = _load_catalog()
    if not catalog:
        return None, 0.0

    text = f"{motion_prompt} {description}".lower()
    if not text.strip():
        return None, 0.0

    # Rating → allowed tiers
    rating_tiers = {
        "G": {"universal", "wholesome"},
        "PG": {"universal", "wholesome"},
        "PG-13": {"universal", "wholesome", "mature"},
        "R": {"universal", "wholesome", "mature"},
        "XXX": {"universal", "wholesome", "mature", "explicit"},
    }
    allowed = rating_tiers.get(content_rating, {"universal", "wholesome", "mature"})

    best_key = None
    best_score = 0
    best_file = None
    best_strength = 0.8

    for key, entry in catalog.items():
        tier = entry.get("tier", "universal")
        if tier not in allowed:
            continue

        lora_file = entry.get("file", "")
        if not lora_file:
            continue

        # Check file actually exists
        full_path = LORA_DIR / lora_file
        if not full_path.exists():
            continue

        tags = entry.get("tags", [])
        score = sum(1 for tag in tags if tag in text)

        if score > best_score:
            best_score = score
            best_key = key
            best_file = lora_file
            best_strength = entry.get("strength", 0.8)

    if best_score >= 1 and best_file:
        logger.info(f"Motion LoRA match: {best_key} (score={best_score}, file={best_file})")
        return best_file, best_strength

    return None, 0.0


def invalidate_cache():
    """Clear cached catalog (call after config changes)."""
    global _catalog_cache
    _catalog_cache = None
