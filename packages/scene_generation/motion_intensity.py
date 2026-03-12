"""Dynamic motion intensity classification for video generation.

Classifies shots into motion tiers (low/medium/high/extreme) based on
LoRA name, prompt content, tags from the catalog, and shot metadata.
Maps each tier to generation parameters (steps, cfg, lora_strength, lightx2v).

The classifier checks in priority order:
1. Explicit DB override (shots.motion_intensity) — user/frontend set
2. LoRA catalog motion_tier tag — per-LoRA in lora_catalog.yaml
3. Keyword heuristics from LoRA name + prompt — fallback
4. Default: medium
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# --- Tier definitions ---

@dataclass(frozen=True)
class MotionParams:
    """Generation parameters for a motion tier."""
    tier: str
    total_steps: int
    split_steps: int
    cfg: float
    content_lora_strength: float
    use_lightx2v: bool
    description: str

MOTION_TIERS: dict[str, MotionParams] = {
    "low": MotionParams(
        tier="low",
        total_steps=4, split_steps=2, cfg=1.0,
        content_lora_strength=0.7, use_lightx2v=True,
        description="Subtle motion — style, softcore, static poses, enhancers",
    ),
    "medium": MotionParams(
        tier="medium",
        total_steps=4, split_steps=2, cfg=1.0,
        content_lora_strength=0.85, use_lightx2v=True,
        description="Moderate motion — camera moves, utility, gentle movement",
    ),
    "high": MotionParams(
        tier="high",
        total_steps=6, split_steps=3, cfg=1.5,
        content_lora_strength=0.95, use_lightx2v=True,
        description="Strong motion — positions, oral, action sequences",
    ),
    "extreme": MotionParams(
        tier="extreme",
        total_steps=8, split_steps=4, cfg=3.5,
        content_lora_strength=1.0, use_lightx2v=False,
        description="Maximum motion — fights, explosions, fast action, no lightx2v",
    ),
}

# --- Keyword-based classification rules ---
# Matched against LoRA filename (lowered, no extension) and prompt text

_HIGH_KEYWORDS = {
    # Position LoRAs — repetitive body motion
    "cowgirl", "reverse_cowgirl", "assertive_cowgirl", "squatting_cowgirl",
    "missionary", "prone_bone", "doggy", "from_behind", "spooning",
    "mating_press", "straddle", "riding",
    # Oral — rhythmic motion
    "sensual_bj", "combo_hj_bj", "lips_bj", "double_blowjob",
    "mouthful", "blowjob", "fellatio", "throatfuck", "titjob", "paizuri",
    # Finishing — burst motion
    "facial", "bukkake", "ejac", "cumshot",
    # Active motion keywords in prompts
    "thrusting", "bouncing", "pumping", "pounding",
}

_EXTREME_KEYWORDS = {
    # Action LoRAs — high-energy
    "fight", "explosion", "atomic_explosion", "bullet_time",
    "transformation", "chase", "slap",
    # Prompt keywords
    "fighting", "punching", "kicking", "exploding", "running",
}

_LOW_KEYWORDS = {
    # Style/enhancement — minimal body motion
    "softcore", "photoshoot", "enhancer", "general_nsfw",
    "penis_enhancer", "pussy_asshole", "closeup",
    "live2d", "retro_90s", "cinematic_flare",
    "sigma_face", "anguish_wail",
    # Anatomy enhancers — static display
    "anatomy", "presenting", "spread",
    # Prompt keywords for low motion
    "standing still", "posing", "portrait", "static",
}

_MEDIUM_KEYWORDS = {
    # Camera LoRAs — camera moves but not body
    "orbit", "push_in", "rotation", "drone", "tilt_down",
    "turntable", "lazy_susan", "set_reveal", "eyes_in",
    "pan", "zoom", "dolly",
    # Transitions
    "smash_cut", "hard_cut", "transition",
    # Gentle motion
    "catwalk", "walk", "pixel_walk", "dance", "hip_swing",
    "timelapse", "massage", "panties_aside", "teasing",
    "tied", "restrained", "fucking_machine",
    "outfit_transform",
}


def _load_catalog() -> dict:
    """Load lora_catalog.yaml (cached per-process)."""
    catalog_path = Path(__file__).resolve().parent.parent.parent / "config" / "lora_catalog.yaml"
    if not hasattr(_load_catalog, "_cache"):
        try:
            with open(catalog_path) as f:
                _load_catalog._cache = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load lora_catalog.yaml: {e}")
            _load_catalog._cache = {}
    return _load_catalog._cache


def _normalize_lora_name(lora_name: str) -> str:
    """Strip path prefixes and extensions for matching."""
    name = Path(lora_name).stem.lower()
    # Remove common suffixes
    for suffix in ("_high", "_low", "_high_noise", "_low_noise", "_hn", "_ln",
                   "_i2v", "_v1", "_v2", "_v3", ".safetensors"):
        name = name.removesuffix(suffix)
    return name


def _get_catalog_motion_tier(lora_name: str) -> Optional[str]:
    """Look up motion_tier from lora_catalog.yaml video_lora_pairs."""
    if not lora_name:
        return None
    catalog = _load_catalog()
    pairs = catalog.get("video_lora_pairs", {})
    norm = _normalize_lora_name(lora_name)

    for key, entry in pairs.items():
        if not entry:
            continue
        # Match by catalog key
        if key == norm:
            return entry.get("motion_tier")
        # Match by HIGH/LOW filename
        for field in ("high", "low"):
            fname = entry.get(field)
            if fname and _normalize_lora_name(fname) == norm:
                return entry.get("motion_tier")
    return None


def _keyword_classify(lora_name: str, prompt: str) -> str:
    """Classify motion tier by keyword matching on LoRA name and prompt."""
    norm_lora = _normalize_lora_name(lora_name) if lora_name else ""
    prompt_lower = (prompt or "").lower()
    search_text = f"{norm_lora} {prompt_lower}"

    # Check extreme first (highest priority)
    for kw in _EXTREME_KEYWORDS:
        if kw in search_text:
            return "extreme"

    # Check high
    for kw in _HIGH_KEYWORDS:
        if kw in search_text:
            return "high"

    # Check low
    for kw in _LOW_KEYWORDS:
        if kw in search_text:
            return "low"

    # Check medium
    for kw in _MEDIUM_KEYWORDS:
        if kw in search_text:
            return "medium"

    # Default
    return "medium"


def classify_motion_intensity(
    shot: dict,
    *,
    lora_name: str | None = None,
    prompt: str | None = None,
) -> str:
    """Classify a shot's motion intensity tier.

    Args:
        shot: Shot dict from DB (may have motion_intensity, lora_name, generation_prompt)
        lora_name: Override LoRA name (if not in shot dict)
        prompt: Override prompt (if not in shot dict)

    Returns:
        Motion tier string: "low", "medium", "high", or "extreme"
    """
    # Priority 1: Explicit DB override
    override = shot.get("motion_intensity")
    if override and override in MOTION_TIERS:
        return override

    # Resolve LoRA and prompt from shot or overrides
    _lora = lora_name or shot.get("lora_name") or ""
    _prompt = prompt or shot.get("generation_prompt") or shot.get("motion_prompt") or ""

    # Priority 2: Catalog motion_tier tag
    catalog_tier = _get_catalog_motion_tier(_lora)

    # Priority 3: Adaptive learned override (from QC history)
    # Applied ON TOP of catalog or keyword tier — adjusts the base tier
    adaptive_tier = get_adaptive_tier(_lora)
    if adaptive_tier and adaptive_tier in MOTION_TIERS:
        logger.debug(f"Adaptive override for {_lora}: {adaptive_tier}")
        return adaptive_tier

    if catalog_tier and catalog_tier in MOTION_TIERS:
        return catalog_tier

    # Priority 4: Keyword heuristics
    return _keyword_classify(_lora, _prompt)


def get_motion_params(tier: str) -> MotionParams:
    """Get generation parameters for a motion tier."""
    return MOTION_TIERS.get(tier, MOTION_TIERS["medium"])


def classify_and_get_params(shot: dict, **kwargs) -> MotionParams:
    """Classify a shot and return its motion parameters."""
    tier = classify_motion_intensity(shot, **kwargs)
    return get_motion_params(tier)


def get_counter_motion(lora_name: str) -> Optional[str]:
    """Look up counter_motion prompt cues from lora_catalog.yaml.

    Returns a string of counter-motion descriptors to append to the
    generation prompt, or None if no counter-motion is defined.
    """
    if not lora_name:
        return None
    catalog = _load_catalog()
    pairs = catalog.get("video_lora_pairs", {})
    norm = _normalize_lora_name(lora_name)

    for key, entry in pairs.items():
        if not entry:
            continue
        if key == norm:
            return entry.get("counter_motion")
        for field in ("high", "low"):
            fname = entry.get(field)
            if fname and _normalize_lora_name(fname) == norm:
                return entry.get("counter_motion")
    return None


def invalidate_catalog_cache():
    """Clear the cached catalog (call when YAML is updated)."""
    if hasattr(_load_catalog, "_cache"):
        del _load_catalog._cache


# --- Adaptive Motion Tuner (Phase 2) ---
# Learns from QC results: if a LoRA consistently gets low motion_execution
# scores at its current tier, bump it up. If it consistently scores high,
# allow dropping a tier to save GPU time.

_TIER_ORDER = ["low", "medium", "high", "extreme"]
_MIN_SAMPLES = 5       # Minimum scored shots before adapting
_BUMP_UP_THRESHOLD = 3.0   # avg motion_execution below this → bump up
_DROP_DOWN_THRESHOLD = 7.0  # avg motion_execution above this → drop down

# Module-level cache of adaptive overrides: normalized_lora_name → adjusted_tier
_adaptive_cache: dict[str, str] = {}
_adaptive_cache_loaded = False


def _bump_tier(current: str, direction: int) -> str:
    """Move tier up (+1) or down (-1) within bounds."""
    idx = _TIER_ORDER.index(current) if current in _TIER_ORDER else 1
    new_idx = max(0, min(len(_TIER_ORDER) - 1, idx + direction))
    return _TIER_ORDER[new_idx]


async def load_adaptive_cache():
    """Query QC history and build adaptive tier overrides.

    Called at startup and periodically (e.g. after each QC batch).
    Populates _adaptive_cache: {normalized_lora_name: adjusted_tier}.
    """
    global _adaptive_cache, _adaptive_cache_loaded

    try:
        import asyncpg
        from ..core.config import DB_CONFIG
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
        )

        # Get per-LoRA motion execution averages from QC data
        # Group by lora_name only — motion_tier may be NULL on older shots
        rows = await conn.fetch("""
            SELECT lora_name,
                   AVG((qc_category_averages->>'motion_execution')::float) AS avg_motion,
                   COUNT(*) AS n
            FROM shots
            WHERE quality_score IS NOT NULL
              AND lora_name IS NOT NULL
              AND qc_category_averages IS NOT NULL
              AND (qc_category_averages->>'motion_execution') IS NOT NULL
            GROUP BY lora_name
            HAVING COUNT(*) >= $1
        """, _MIN_SAMPLES)

        new_cache = {}
        for row in rows:
            lora = row["lora_name"]
            norm = _normalize_lora_name(lora)
            avg_motion = row["avg_motion"]
            n = row["n"]
            # Derive current tier from catalog/keyword (what would be assigned now)
            current_tier = (_get_catalog_motion_tier(lora)
                           or _keyword_classify(lora, "")
                           or "medium")

            if avg_motion < _BUMP_UP_THRESHOLD:
                adjusted = _bump_tier(current_tier, +1)
                if adjusted != current_tier:
                    new_cache[norm] = adjusted
                    logger.info(
                        f"Adaptive: {norm} bumped {current_tier}→{adjusted} "
                        f"(avg_motion={avg_motion:.1f}, n={n})"
                    )
            elif avg_motion > _DROP_DOWN_THRESHOLD:
                adjusted = _bump_tier(current_tier, -1)
                if adjusted != current_tier:
                    new_cache[norm] = adjusted
                    logger.info(
                        f"Adaptive: {norm} dropped {current_tier}→{adjusted} "
                        f"(avg_motion={avg_motion:.1f}, n={n})"
                    )

        _adaptive_cache = new_cache
        _adaptive_cache_loaded = True
        await conn.close()

        if new_cache:
            logger.info(f"Adaptive motion cache loaded: {len(new_cache)} overrides")
        else:
            logger.info("Adaptive motion cache loaded: no overrides needed yet")

    except Exception as e:
        logger.warning(f"Failed to load adaptive motion cache: {e}")
        _adaptive_cache_loaded = True  # Mark loaded to avoid retry storms


def get_adaptive_tier(lora_name: str) -> Optional[str]:
    """Check if a LoRA has an adaptive tier override from QC history."""
    if not lora_name or not _adaptive_cache:
        return None
    norm = _normalize_lora_name(lora_name)
    return _adaptive_cache.get(norm)


def invalidate_adaptive_cache():
    """Clear adaptive cache so it gets rebuilt on next load."""
    global _adaptive_cache, _adaptive_cache_loaded
    _adaptive_cache = {}
    _adaptive_cache_loaded = False


async def record_motion_pattern(
    lora_name: str,
    motion_tier: str,
    motion_score: float,
    cfg: float = None,
    steps: int = None,
):
    """Record a video motion pattern in learned_patterns table.

    Uses pattern_type='video_motion' and character_slug=normalized_lora_name.
    """
    try:
        from ..core.learning import record_learned_pattern
        norm = _normalize_lora_name(lora_name)
        await record_learned_pattern(
            character_slug=norm,
            pattern_type="video_motion",
            project_name=motion_tier,  # store tier in project_name for reference
            quality_score=motion_score,
            cfg_scale=cfg,
            steps=steps,
        )
    except Exception as e:
        logger.warning(f"Failed to record motion pattern for {lora_name}: {e}")
