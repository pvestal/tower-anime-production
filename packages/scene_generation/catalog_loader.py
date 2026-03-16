"""Unified LoRA catalog loader — reads from modular config/lora_catalog/ directory.

All modules that need the LoRA catalog should import from here:

    from .catalog_loader import load_catalog, invalidate_catalog

The loader merges all YAML files in config/lora_catalog/ into a single dict
with the same structure the code has always expected:

    {
        "content_tiers": {...},
        "rating_gates": {...},
        "checkpoint_compat": {...},
        "video_lora_pairs": {...},       # merged from poses, cameras, actions, etc.
        "video_motion_loras": {...},      # from motion.yaml
        "image_lora_categories": {...},   # from image_categories.yaml
        "action_presets": {...},           # from presets.yaml
    }

Falls back to monolithic config/lora_catalog.yaml if the directory doesn't exist.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent.parent
_CATALOG_DIR = _BASE / "config" / "lora_catalog"
_CATALOG_MONOLITH = _BASE / "config" / "lora_catalog.yaml"

# Module-level cache
_cache: Optional[dict] = None


def load_catalog() -> dict:
    """Load and merge the LoRA catalog (cached per-process).

    Reads all *.yaml files from config/lora_catalog/ and deep-merges
    dict-valued top-level keys. Falls back to monolithic file if needed.
    """
    global _cache
    if _cache is not None:
        return _cache

    try:
        if _CATALOG_DIR.is_dir():
            _cache = _load_modular()
        elif _CATALOG_MONOLITH.exists():
            logger.info("catalog_loader: using monolithic lora_catalog.yaml (modular dir not found)")
            with open(_CATALOG_MONOLITH) as f:
                _cache = yaml.safe_load(f) or {}
        else:
            logger.warning("catalog_loader: no catalog found")
            _cache = {}
    except Exception as e:
        logger.error(f"catalog_loader: failed to load: {e}")
        _cache = {}

    return _cache


def _load_modular() -> dict:
    """Read all YAML files from the modular directory and merge."""
    merged: dict = {}
    files = sorted(_CATALOG_DIR.glob("*.yaml"))

    # Load _schema.yaml first (has content_tiers, rating_gates, etc.)
    schema_file = _CATALOG_DIR / "_schema.yaml"
    if schema_file.exists():
        files = [f for f in files if f.name != "_schema.yaml"]
        files.insert(0, schema_file)

    for f in files:
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh) or {}
        except Exception as e:
            logger.warning(f"catalog_loader: failed to parse {f.name}: {e}")
            continue

        for key, value in data.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # Deep merge: dict keys from multiple files merge together
                merged[key].update(value)
            else:
                merged[key] = value

    n_pairs = len(merged.get("video_lora_pairs", {}))
    n_motion = len(merged.get("video_motion_loras", {}))
    n_presets = len(merged.get("action_presets", {}))
    n_img = len(merged.get("image_lora_categories", {}))
    logger.info(
        f"catalog_loader: loaded {len(files)} files — "
        f"{n_pairs} video pairs, {n_motion} motion, {n_presets} presets, {n_img} image cats"
    )
    return merged


def invalidate_catalog():
    """Clear the cached catalog (call when YAML is updated at runtime)."""
    global _cache
    _cache = None
