"""Centralized LoRA resolution logic for WAN 2.2 14B and DaSiWa engines.

Extracted from builder.py to eliminate duplication across engine branches.
All functions are pure helpers — no DB access, no async, no side effects
beyond logging.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NSFW_KEYWORDS = (
    "nsfw", "cowgirl", "missionary", "doggy", "prone", "bj", "blowjob",
    "insertion", "cumshot", "facial", "titjob", "spooning", "furry_tf",
    "mouthfull", "bukkake",
)

ADULT_RATINGS = {"R", "NC-17", "XXX", "TV-MA"}

LORA_DIR = Path("/opt/ComfyUI/models/loras")


# ---------------------------------------------------------------------------
# 1. Core LoRA pair resolution  (was builder._resolve_content_lora_pair)
# ---------------------------------------------------------------------------

def _resolve_content_lora_pair(
    shot_lora_name: str | None,
    project_video_lora: str | None = None,
) -> tuple[str | None, str | None, float]:
    """Resolve a shot's lora_name to content LoRA HIGH/LOW pair for Wan22 14B.

    Logic:
    1. If shot has lora_name containing '_HIGH', derive the LOW counterpart.
    2. If shot has lora_name matching a video_lora_pairs key from catalog, use that.
    3. If shot has no lora_name, fall back to project_video_lora as HIGH-only.

    Returns (content_lora_high, content_lora_low, strength).
    """
    # Use shot-level LoRA first; only fall back to project LoRA if it's
    # WAN-compatible (not a framepack/image LoRA)
    lora_name = shot_lora_name
    if not lora_name and project_video_lora:
        pv = project_video_lora.lower()
        # Skip FramePack / image-only LoRAs — they're incompatible with WAN 2.2 14B
        if "framepack" not in pv and "illustrious" not in pv and "sdxl" not in pv:
            lora_name = project_video_lora
    if not lora_name:
        return None, None, 0.85

    lora_name = lora_name.strip()

    # Guard: general_nsfw is a booster, not a content LoRA — skip it
    if "general_nsfw" in lora_name:
        return None, None, 0.85

    # Pattern 1: Already a _HIGH filename — derive _LOW
    if "_HIGH" in lora_name:
        high = lora_name
        low = lora_name.replace("_HIGH", "_LOW")
        # Check LOW exists
        low_path = LORA_DIR / low
        if not low_path.exists():
            low_path = LORA_DIR / "wan22_nsfw" / low
        if not low_path.exists():
            low = None  # HIGH-only, no LOW counterpart
        return high, low, 0.85

    # Pattern 2: A _LOW filename — derive _HIGH
    if "_LOW" in lora_name:
        low = lora_name
        high = lora_name.replace("_LOW", "_HIGH")
        high_path = LORA_DIR / high
        if not high_path.exists():
            high_path = LORA_DIR / "wan22_nsfw" / high
        if not high_path.exists():
            high = None
        return high, low, 0.85

    # Pattern 3: Catalog key name (e.g. "cowgirl") — look up in catalog
    try:
        from .catalog_loader import load_catalog
        catalog = load_catalog()
        if catalog:
            pairs = catalog.get("video_lora_pairs", {})

            # Direct match in video_lora_pairs
            if lora_name in pairs:
                pair = pairs[lora_name]
                if pair.get("single"):
                    return pair["single"], pair["single"], 0.85
                return pair.get("high"), pair.get("low"), 0.85

            # Check action_presets — follow video_lora reference to video_lora_pairs
            presets = catalog.get("action_presets", {})
            if lora_name in presets:
                preset = presets[lora_name]
                vl_key = preset.get("video_lora")
                if vl_key and vl_key in pairs:
                    pair = pairs[vl_key]
                    strength = preset.get("video_lora_strength", 0.85)
                    if pair.get("single"):
                        return pair["single"], pair["single"], strength
                    return pair.get("high"), pair.get("low"), strength
                # Preset exists but video_lora isn't in video_lora_pairs —
                # it's a motion-only preset (e.g. idle, walking, talking).
                # No content LoRA needed; motion_lora_matcher handles it.
                return None, None, 0.85

            # Check video_motion_loras — these are motion LoRAs, not content
            motion_loras = catalog.get("video_motion_loras", {})
            if lora_name in motion_loras:
                return None, None, 0.85
    except Exception:
        pass

    # Pattern 4: Generic single LoRA (e.g. project-level video_lora) — apply to high model only
    # Only if the file actually exists on disk; otherwise return None to avoid
    # passing bogus strings to ComfyUI
    if (LORA_DIR / lora_name).exists() or (LORA_DIR / f"{lora_name}.safetensors").exists():
        return lora_name, None, 0.85
    return None, None, 0.85


# ---------------------------------------------------------------------------
# 2. Unified content LoRA resolution  (consolidates wan22_14b + dasiwa paths)
# ---------------------------------------------------------------------------

def resolve_content_loras(
    shot_dict: dict,
    project_video_lora: str | None = None,
    skip_project_lora: bool = False,
) -> tuple[str | None, str | None, float]:
    """Resolve content LoRA HIGH/LOW pair for a shot.

    Priority order:
    1. shot_dict["content_lora_high"] (pre-assigned, e.g. test matrix)
    2. shot_dict["lora_name"] via _resolve_content_lora_pair() catalog lookup
    3. project_video_lora fallback (unless skip_project_lora is True)

    Returns (content_lora_high, content_lora_low, strength).
    """
    # Priority 1: Pre-assigned content_lora_high on the shot
    pre_clh = shot_dict.get("content_lora_high")
    pre_cll = shot_dict.get("content_lora_low")
    if pre_clh:
        strength = shot_dict.get("lora_strength") or 0.85
        return pre_clh, pre_cll, float(strength)

    # Priority 2+3: Catalog / project fallback via _resolve_content_lora_pair
    shot_lora = shot_dict.get("lora_name")
    effective_project_lora = None if skip_project_lora else project_video_lora
    return _resolve_content_lora_pair(shot_lora, effective_project_lora)


# ---------------------------------------------------------------------------
# 3. NSFW content rating gate
# ---------------------------------------------------------------------------

def gate_nsfw_lora(
    lora_high: str | None,
    lora_low: str | None,
    content_rating: str | None,
) -> tuple[str | None, str | None]:
    """Strip NSFW content LoRAs from non-adult-rated projects.

    Returns the (possibly cleared) (lora_high, lora_low) tuple.
    """
    rating = content_rating or "R"
    if not (lora_high or lora_low):
        return lora_high, lora_low

    if rating in ADULT_RATINGS:
        # Adult-rated — keep as-is
        return lora_high, lora_low

    # Check if the HIGH LoRA contains any NSFW keywords
    is_nsfw = any(kw in (lora_high or "") for kw in NSFW_KEYWORDS)
    if is_nsfw:
        logger.warning(
            f"BLOCKED explicit LoRA '{lora_high}' — "
            f"content_rating='{rating}' is not adult-rated"
        )
        return None, None

    return lora_high, lora_low


# ---------------------------------------------------------------------------
# 4. Motion LoRA resolution
# ---------------------------------------------------------------------------

def resolve_motion_lora(
    shot_dict: dict,
    engine_sel,
    motion_prompt: str | None,
    description: str | None,
    content_rating: str | None,
    has_content_lora: bool,
) -> tuple[str | None, float]:
    """Resolve motion LoRA for a shot.

    Logic:
    1. Use engine_sel.motion_loras[0] if available (engine selector picked one).
    2. If no content LoRA is driving motion, fall back to motion_lora_matcher.
    3. If content LoRA IS present, skip motion LoRA (content provides motion).

    Returns (motion_lora_file, strength).
    """
    # Priority 1: Engine selector already picked a motion LoRA
    motion_lora = engine_sel.motion_loras[0] if engine_sel.motion_loras else None
    motion_str = 0.8

    if motion_lora:
        return motion_lora, motion_str

    if not has_content_lora:
        # No content LoRA — try to match a motion LoRA from catalog
        from .motion_lora_matcher import match_motion_lora
        ml_prompt = motion_prompt or ""
        ml_desc = description or ""
        ml_rating = content_rating or "R"
        return match_motion_lora(
            motion_prompt=ml_prompt, description=ml_desc, content_rating=ml_rating
        )

    # Content LoRA present — skip motion LoRA to avoid conflicting movement
    logger.info(
        f"Shot {shot_dict.get('id', '?')}: skipping motion LoRA — "
        f"content LoRA provides motion"
    )
    return None, 0.8
