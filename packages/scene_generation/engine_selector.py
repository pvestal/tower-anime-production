"""Automatic video engine selection for shots.

Picks the best engine based on shot characteristics:
  1. Character has trained LoRA on disk → ltx (native LoRA injection)
  2. Solo shot with source image → framepack (I2V preserves source style — critical for realistic projects)
  3. Multi-char / no source image → wan (T2V, A/B test winner for multi-char — no IP-Adapter artifacts)
  4. Wan 2.2 14B I2V with motion presets (walk, fight, cinematic, etc.)

Motion presets are defined in config/video_models.yaml and map shot intent to
recommended video_model + LoRA combinations (walking, fight_scene, cinematic_orbit, etc.).

A/B test (2026-02-27): Wan+postprocess beat Composite+FramePack for MULTI-CHARACTER shots.
Solo shots still use FramePack to preserve the photorealistic style from source images.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")
VALID_ENGINES = {"framepack", "framepack_f1", "ltx", "wan", "wan22", "wan22_14b", "reference_v2v"}
ESTABLISHING_SHOT_TYPES = {"establishing", "wide_establishing", "aerial", "environment"}

# Motion keywords detected in motion_prompt text → preset name
MOTION_KEYWORD_MAP = {
    "walking": ["walk", "walking", "stroll", "stride", "striding"],
    "running": ["run", "running", "sprint", "sprinting", "chase", "chasing"],
    "fight_scene": ["fight", "punch", "kick", "combat", "battle", "attack", "dodge", "powers up", "slash"],
    "cinematic_orbit": ["arc shot", "orbit", "revolve", "circle around", "camera moving around"],
    "cinematic_relight": ["dramatic light", "mood light", "exposure", "lighting shift", "atmosphere"],
    "dialogue": ["talk", "speaking", "conversation", "dialogue", "gestur"],
    "idle": ["breath", "idle", "subtle", "still", "wind blow", "sway"],
}


def _load_video_catalog() -> dict:
    """Load video_models.yaml config. Returns empty dict on failure."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "video_models.yaml"
    if not config_path.exists():
        logger.warning(f"Video catalog not found: {config_path}")
        return {}
    try:
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load video catalog: {e}")
        return {}


def detect_motion_preset(motion_prompt: str, shot_type: str = "") -> str | None:
    """Detect motion preset from a motion_prompt string.

    Scans for keywords and returns the matching preset name,
    or None if no strong match.
    """
    if not motion_prompt:
        return None
    prompt_lower = motion_prompt.lower()
    for preset, keywords in MOTION_KEYWORD_MAP.items():
        for kw in keywords:
            if kw in prompt_lower:
                return preset
    # Fallback: infer from shot_type
    if shot_type in ESTABLISHING_SHOT_TYPES:
        return "establishing"
    return None


def resolve_motion_preset(preset_name: str) -> dict | None:
    """Resolve a motion preset to engine + LoRA config from video_models.yaml.

    Returns dict with keys: engine, loras, lora_strengths, or None if not found.
    """
    catalog = _load_video_catalog()
    presets = catalog.get("motion_presets", {})
    preset = presets.get(preset_name)
    if not preset:
        return None

    loras_config = catalog.get("loras", {})
    engine = preset.get("primary_engine", "wan22_14b")
    lora_names = preset.get("loras", [])

    # Resolve LoRA names to filenames, checking availability
    resolved_loras = []
    for lora_key in lora_names:
        lora_info = loras_config.get(lora_key)
        if lora_info and Path(lora_info["path"]).exists():
            resolved_loras.append({
                "name": lora_key,
                "filename": Path(lora_info["path"]).name,
                "strength": lora_info.get("strength", 0.8),
            })

    # Check if primary engine models exist, fall back if not
    video_models = catalog.get("video_models", {})
    engine_available = _check_engine_available(engine, video_models)
    if not engine_available:
        fallback = preset.get("fallback_engine")
        if fallback and _check_engine_available(fallback, video_models):
            logger.info(f"Motion preset '{preset_name}': primary engine '{engine}' unavailable, using fallback '{fallback}'")
            engine = fallback
            fallback_loras = preset.get("fallback_loras", [])
            resolved_loras = []
            for lora_key in fallback_loras:
                lora_info = loras_config.get(lora_key)
                if lora_info and Path(lora_info["path"]).exists():
                    resolved_loras.append({
                        "name": lora_key,
                        "filename": Path(lora_info["path"]).name,
                        "strength": lora_info.get("strength", 0.8),
                    })

    return {
        "engine": engine,
        "loras": resolved_loras,
        "preset_name": preset_name,
    }


def _check_engine_available(engine: str, video_models: dict) -> bool:
    """Check if an engine's models exist on disk."""
    if engine == "wan22_14b":
        high = video_models.get("wan22_i2v_14b_high_q4", {})
        low = video_models.get("wan22_i2v_14b_low_q4", {})
        return Path(high.get("path", "")).exists() and Path(low.get("path", "")).exists()
    if engine == "framepack":
        fp = video_models.get("framepack_i2v", {})
        return Path(fp.get("path", "")).exists()
    if engine == "framepack_f1":
        fp = video_models.get("framepack_f1", {})
        return Path(fp.get("path", "")).exists()
    if engine in ("wan", "wan21_t2v"):
        w = video_models.get("wan21_t2v_1.3b", {})
        return Path(w.get("path", "")).exists()
    if engine in ("wan22", "wan22_5b"):
        w = video_models.get("wan22_5b", {})
        return Path(w.get("path", "")).exists()
    # Assume available for engines we don't track
    return True

# GPU VRAM budget (RTX 3060 12 GB, single GPU):
#   framepack / reference_v2v: ~10 GB (HunyuanVideo backbone) — exclusive
#   wan / wan22 GGUF:          ~6-8 GB (1.3B quantized)
#   ltx:                       ~8 GB
#   CLIP classifier:           ~400 MB (coexists with any engine)
# builder.py uses Semaphore(1) to serialize GPU jobs — correct for 12 GB.


@dataclass
class EngineSelection:
    engine: str                       # "framepack" | "ltx" | "wan" | "wan22" | "wan22_14b" | "reference_v2v"
    reason: str                       # human-readable explanation
    lora_name: str | None = None      # filename if LTX/Wan22 + LoRA
    lora_strength: float = 0.8
    motion_preset: str | None = None  # detected motion preset name
    motion_loras: list = field(default_factory=list)  # additional motion/camera LoRAs


def _find_video_lora(character_slug: str) -> tuple[str | None, str | None]:
    """Check if a character has a LoRA file on disk.

    Searches for both LTX LoRAs ({slug}_lora.safetensors) and
    FramePack LoRAs ({slug}_framepack.safetensors).

    Returns (filename, architecture) where architecture is "ltx" or "framepack",
    or (None, None) if not found.
    """
    # FramePack LoRA (HunyuanVideo architecture) — preferred for V2V
    fp_path = LORA_DIR / f"{character_slug}_framepack.safetensors"
    if fp_path.exists():
        return fp_path.name, "framepack"
    # LTX LoRA (SD-format)
    ltx_path = LORA_DIR / f"{character_slug}_lora.safetensors"
    if ltx_path.exists():
        return ltx_path.name, "ltx"
    return None, None


def _pick_best_lora(characters: list[str]) -> tuple[str | None, str | None, str | None]:
    """Find the first character with a LoRA file.

    Returns (lora_filename, slug, architecture) or (None, None, None).
    """
    for slug in characters:
        lora_name, lora_arch = _find_video_lora(slug)
        if lora_name:
            return lora_name, slug, lora_arch
    return None, None, None


def _find_wan_lora() -> str | None:
    """Detect a Wan 2.2-compatible LoRA in the loras directory.

    Naming convention: *wan22*.safetensors (e.g. furrynsfw_wan22_v1.safetensors).
    Returns the filename if found, None otherwise.
    """
    for p in LORA_DIR.glob("*wan22*.safetensors"):
        return p.name
    return None


def select_engine(
    shot_type: str,
    characters_present: list[str],
    has_source_image: bool,
    blacklisted_engines: list[str] | None = None,
    has_source_video: bool = False,
    project_wan_lora: str | None = None,
    motion_prompt: str | None = None,
) -> EngineSelection:
    """Pick best video engine based on shot characteristics.

    Args:
        shot_type: Shot type string (e.g. "establishing", "medium", "close_up").
        characters_present: List of character slugs in the shot.
        has_source_image: Whether a source image is assigned.
        blacklisted_engines: Engines to exclude from selection.
        has_source_video: Whether a source video clip is assigned (for V2V style transfer).
        project_wan_lora: Wan 2.2 LoRA filename if detected for this project.
            When set, ALL shots route to wan22 engine (highest priority after V2V).
        motion_prompt: Optional motion description text. Used to detect motion
            presets (walk, fight, cinematic, etc.) and select appropriate
            engine + LoRA combos from video_models.yaml.

    Returns:
        EngineSelection with chosen engine, reason, and optional LoRA info.
    """
    blocked = set(blacklisted_engines or [])

    # Build priority-ordered candidates
    candidates: list[EngineSelection] = []

    is_establishing = (
        shot_type in ESTABLISHING_SHOT_TYPES or not characters_present
    )
    is_multi_char = len(characters_present) > 1
    lora_name, lora_slug, lora_arch = _pick_best_lora(characters_present) if characters_present else (None, None, None)

    # Rule 0: Shot with reference video clip → reference_v2v (V2V style transfer)
    if has_source_video and not is_establishing:
        candidates.append(EngineSelection(
            engine="reference_v2v",
            reason=("multi-char" if is_multi_char else "solo") + " shot with reference video clip, V2V style transfer"
                + (f" + FramePack LoRA ({lora_name})" if lora_arch == "framepack" else ""),
            lora_name=lora_name if lora_arch == "framepack" else None,
            lora_strength=0.8,
        ))

    # Rule 0.5: Project has Wan 2.2 LoRA → route ALL shots to wan22
    if project_wan_lora:
        mode = "I2V" if (has_source_image and not is_multi_char and not is_establishing) else "T2V"
        candidates.append(EngineSelection(
            engine="wan22",
            reason=f"project Wan LoRA ({project_wan_lora}), {mode} mode",
            lora_name=project_wan_lora,
            lora_strength=0.5,
        ))

    # Rule 0.75: Motion preset detection → wan22_14b with motion LoRAs
    # Detected motion type overrides standard engine selection when Wan 2.2 14B is available.
    preset_name = detect_motion_preset(motion_prompt or "", shot_type)
    if preset_name:
        resolved = resolve_motion_preset(preset_name)
        if resolved:
            engine = resolved["engine"]
            # Map catalog engine names to actual engine IDs
            engine_map = {"wan22_14b": "wan22_14b", "framepack": "framepack",
                          "framepack_f1": "framepack_f1", "wan21_t2v": "wan",
                          "wan22_5b": "wan22"}
            mapped_engine = engine_map.get(engine, engine)
            motion_loras = resolved.get("loras", [])
            # Pick the first motion LoRA as the primary (for engines that take one LoRA)
            primary_motion_lora = motion_loras[0]["filename"] if motion_loras else None
            primary_strength = motion_loras[0]["strength"] if motion_loras else 0.8
            candidates.append(EngineSelection(
                engine=mapped_engine,
                reason=f"motion preset '{preset_name}' → {mapped_engine}"
                    + (f" + {len(motion_loras)} LoRA(s)" if motion_loras else ""),
                lora_name=primary_motion_lora,
                lora_strength=primary_strength,
                motion_preset=preset_name,
                motion_loras=motion_loras,
            ))

    # Rule 1: Multi-character → wan22_14b if available, else wan
    # (takes priority over establishing — multi-char with keyframe should use I2V)
    if is_multi_char:
        from .wan_video import check_wan22_14b_ready
        ready_14b, _ = check_wan22_14b_ready()
        if ready_14b and has_source_image:
            candidates.append(EngineSelection(
                engine="wan22_14b",
                reason=f"multi-character I2V ({len(characters_present)} chars), Wan 2.2 14B quality upgrade",
            ))
        candidates.append(EngineSelection(
            engine="wan",
            reason=f"multi-character shot ({len(characters_present)} chars), A/B test winner",
        ))

    # Rule 2: Establishing / environment shot → wan (no characters, T2V is fine)
    if is_establishing and not is_multi_char:
        candidates.append(EngineSelection(
            engine="wan",
            reason=f"establishing shot (type={shot_type})",
        ))

    # Rule 3a: Solo character with FramePack LoRA + source image → framepack with LoRA
    if lora_name and lora_arch == "framepack" and has_source_image and not is_multi_char:
        candidates.append(EngineSelection(
            engine="framepack",
            reason=f"character '{lora_slug}' has FramePack LoRA ({lora_name}) + source image",
            lora_name=lora_name,
            lora_strength=0.8,
        ))

    # Rule 3b: Solo character with LTX LoRA → ltx
    if lora_name and lora_arch == "ltx" and not is_multi_char:
        candidates.append(EngineSelection(
            engine="ltx",
            reason=f"character '{lora_slug}' has LTX LoRA ({lora_name})",
            lora_name=lora_name,
            lora_strength=0.8,
        ))

    # Rule 4: Solo shot with source image → wan22_14b if available, else framepack
    if has_source_image and not is_multi_char:
        from .wan_video import check_wan22_14b_ready
        ready_14b, _ = check_wan22_14b_ready()
        if ready_14b:
            candidates.append(EngineSelection(
                engine="wan22_14b",
                reason="solo I2V with Wan 2.2 14B (quality upgrade over FramePack)",
            ))
        candidates.append(EngineSelection(
            engine="framepack",
            reason="solo shot with source image, preserves source style",
        ))

    # Rule 5: No source image + characters → wan T2V fallback
    if not has_source_image and characters_present:
        candidates.append(EngineSelection(
            engine="wan",
            reason="no source image available, using T2V",
        ))

    # Default fallback
    candidates.append(EngineSelection(
        engine="wan",
        reason="default engine",
    ))

    # Apply blacklist — pick first non-blocked candidate
    for candidate in candidates:
        if candidate.engine not in blocked:
            logger.info(f"Engine selected: {candidate.engine} — {candidate.reason}")
            return candidate

    # Everything blocked — return last candidate with warning
    logger.warning(
        f"All engines blocked by blacklist {blocked}, "
        f"falling back to '{candidates[-1].engine}' anyway"
    )
    return candidates[-1]
