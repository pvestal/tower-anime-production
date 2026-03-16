"""Auto-match shots to content LoRAs based on motion/generation prompt keywords.

Reads action_presets from lora_catalog.yaml and matches against shot prompts.
Returns the catalog key (e.g., "cowgirl", "walking") which _resolve_content_lora_pair()
then maps to the actual HIGH/LOW or single LoRA files.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_presets_cache: dict | None = None

# Keyword → preset key mappings for common patterns that don't match tags directly
KEYWORD_ALIASES = {
    # Position keywords → preset keys
    "cowgirl": "cowgirl",
    "riding": "cowgirl",
    "on top": "cowgirl",
    "straddling": "cowgirl",
    "reverse cowgirl": "reverse_cowgirl",
    "missionary": "missionary",
    "doggy": "doggy_back",
    "doggystyle": "doggy_back",
    "doggy front": "doggy_front",
    "from behind": "from_behind",
    "prone bone": "prone_bone",
    "prone": "prone_bone",
    "face down": "prone_bone",
    "spooning": "spooning",
    "wall sex": "wall_sex",
    "wall pin": "wall_sex",
    "pressed against wall": "wall_sex",
    "blowjob": "blowjob",
    "bj": "blowjob",
    "oral": "blowjob",
    "titjob": "titjob",
    "facial": "facial_finish",
    "lap dance": "lap_dance",
    "grinding": "lap_dance",
    # SFW action keywords → preset keys
    "walking": "walking",
    "walk": "walking",
    "stroll": "walking",
    "running": "running",
    "run": "running",
    "jogging": "running",
    "sprint": "running",
    "chase": "vehicle_chase",
    "talking": "talking",
    "conversation": "talking",
    # SFW motion — maps to motion-only presets (no content LoRA pair,
    # motion_lora_matcher picks the right motion LoRA)
    "speaking": "talking",
    "dialogue": "talking",
    "hugging": "hugging",
    "hug": "hugging",
    "embrace": "hugging",
    "idle": "idle",
    "standing still": "idle",
    "breathing": "idle",
    "subtle idle": "idle",
    "static": "idle",
    "dancing": "dancing",
    "dance": "dancing",
    "fighting": "fighting",
    "fight": "fighting",
    "punch": "fighting",
    "combat": "fighting",
    "motorcycle": "motorcycle",
    "bike": "motorcycle",
    "hair wind": "hair_flowing",
    "hair blowing": "hair_flowing",
    # Subtle/ambient → idle
    "subtle character movement": "idle",
    "subtle camera drift": "idle",
    "ambient motion": "idle",
    "natural body language": "idle",
    "fidgets": "idle",
    "nervously": "idle",
    "looking around": "idle",
    # Wall/press
    "pressed against": "wall_sex",
    "against wall": "wall_sex",
    "against onsen wall": "wall_sex",
    "pinned": "wall_sex",
    # Oral variants
    "licking": "sensual_blowjob",
    "teasing lick": "sensual_blowjob",
    "tongue": "sensual_blowjob",
    "sensual oral": "sensual_blowjob",
    # SFW fallbacks → idle preset
    "stumble": "idle",
    "doorway": "idle",
    "drops bag": "idle",
    "exhausted": "idle",
    "pan": "idle",
    "zoom": "idle",
    "camera rotation": "idle",
    "orbit": "idle",
    # Furry-specific
    "furry cowgirl": "furry_cowgirl",
    "furry prone": "furry_prone",
    "furry blowjob": "furry_blowjob",
    "furry from behind": "furry_from_behind",
}

# Rating → allowed tiers
RATING_TIERS = {
    "G": {"universal", "wholesome"},
    "PG": {"universal", "wholesome"},
    "PG-13": {"universal", "wholesome", "mature"},
    "R": {"universal", "wholesome", "mature"},
    "XXX": {"universal", "wholesome", "mature", "explicit", "furry_explicit"},
}


def _load_presets() -> dict:
    global _presets_cache
    if _presets_cache is not None:
        return _presets_cache
    from .catalog_loader import load_catalog
    _presets_cache = load_catalog().get("action_presets") or {}
    return _presets_cache


def match_content_lora(
    motion_prompt: str = "",
    generation_prompt: str = "",
    content_rating: str = "R",
) -> str | None:
    """Return the action_preset key for the best matching content LoRA.

    Returns None if no confident match found.
    The returned key (e.g., "cowgirl", "walking") is used as shots.lora_name,
    which _resolve_content_lora_pair() then maps to actual files via the catalog.
    """
    presets = _load_presets()
    if not presets:
        return None

    text = f"{motion_prompt} {generation_prompt}".lower()
    if not text.strip():
        return None

    allowed = RATING_TIERS.get(content_rating, {"universal", "wholesome", "mature"})

    # Phase 1: Direct keyword alias match (highest confidence)
    # Check longer phrases first to avoid partial matches
    sorted_aliases = sorted(KEYWORD_ALIASES.keys(), key=len, reverse=True)
    for keyword in sorted_aliases:
        if keyword in text:
            preset_key = KEYWORD_ALIASES[keyword]
            if preset_key in presets:
                tier = presets[preset_key].get("tier", "universal")
                if tier in allowed:
                    logger.debug(f"Content LoRA match (alias): '{keyword}' → {preset_key}")
                    return preset_key

    # Phase 2: Match against preset labels (fuzzy)
    best_key = None
    best_score = 0
    for key, preset in presets.items():
        tier = preset.get("tier", "universal")
        if tier not in allowed:
            continue

        label = preset.get("label", "").lower()
        score = 0

        # Check if label words appear in the text
        label_words = label.split()
        for word in label_words:
            if len(word) > 2 and word in text:
                score += 1

        if score > best_score:
            best_score = score
            best_key = key

    if best_score >= 2 and best_key:
        logger.debug(f"Content LoRA match (label): {best_key} (score={best_score})")
        return best_key

    return None


def invalidate_cache():
    """Clear cached presets (call after config changes)."""
    global _presets_cache
    _presets_cache = None
