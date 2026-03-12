"""Video engine configuration — single source of truth from video_models.yaml.

Loads engine_defaults once at import time. All engine branches in builder.py
should read from get_engine_defaults() instead of hardcoding dimensions,
frame counts, steps, etc.
"""

import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "video_models.yaml"
_config_cache: dict | None = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            _config_cache = yaml.safe_load(f) or {}
    else:
        logger.warning(f"video_models.yaml not found at {_CONFIG_PATH}")
        _config_cache = {}
    return _config_cache


def reload_config():
    """Force reload from disk (e.g. after editing the YAML)."""
    global _config_cache
    _config_cache = None
    return _load_config()


def get_engine_defaults(engine: str) -> dict:
    """Get default parameters for a video engine.

    Returns dict with keys like width, height, fps, num_frames, steps, etc.
    Falls back to empty dict if engine not found.
    """
    cfg = _load_config()
    return dict(cfg.get("engine_defaults", {}).get(engine, {}))


def get_video_models() -> dict:
    """Get the full video_models section."""
    return dict(_load_config().get("video_models", {}))


def get_loras() -> dict:
    """Get the loras section."""
    return dict(_load_config().get("loras", {}))


def get_motion_presets() -> dict:
    """Get motion_presets section."""
    return dict(_load_config().get("motion_presets", {}))
