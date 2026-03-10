"""SFX + Voice Auto-Mapper — assigns foley sounds AND contextual voice lines to shots.

Reads config/sfx_mapping.yaml and the SFX manifest to:
1. Pick appropriate foley clips for each shot based on LoRA
2. Pick contextual voice dialogue lines based on LoRA action
3. Overlay foley onto the video
4. Synthesize voice dialogue via character voice profiles

The new YAML structure has per-mapping:
  sfx: [...] (foley clips)
  voice_lines: {female: [...], male: [...]} (dialogue templates)
"""

import json
import logging
import random
import subprocess
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sfx_mapping.yaml"
_SFX_MANIFEST_PATH = Path(__file__).resolve().parent.parent.parent / "output" / "sfx_test" / "sfx_manifest.json"
_SFX_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "sfx_mixed"
_VOICE_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "voice_mixed"

_config_cache: dict | None = None
_manifest_cache: dict | None = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                _config_cache = yaml.safe_load(f) or {}
        else:
            _config_cache = {}
    return _config_cache


def _load_manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is None:
        if _SFX_MANIFEST_PATH.exists():
            with open(_SFX_MANIFEST_PATH) as f:
                _manifest_cache = json.load(f) or {}
        else:
            _manifest_cache = {}
    return _manifest_cache


def reload_config():
    """Force reload of config and manifest (call after edits)."""
    global _config_cache, _manifest_cache
    _config_cache = None
    _manifest_cache = None


def _find_mapping(
    lora_name: Optional[str],
    pairing: Optional[str] = None,
) -> dict:
    """Find the best matching mapping entry for a LoRA name.

    Args:
        lora_name: LoRA filename to match
        pairing: Optional hint — "mm" (male×male), "ff" (female×female),
                 "anthro" (furry/anthro), or None for default (mixed/mf)

    Returns the full mapping dict with 'sfx' and 'voice_lines' keys.
    Supports both old format (list) and new format (dict with sfx/voice_lines).
    """
    config = _load_config()

    if not lora_name:
        # Choose default based on pairing
        if pairing == "mm":
            raw = config.get("default_nsfw_mm", config.get("default_nsfw", {}))
        elif pairing == "ff":
            raw = config.get("default_nsfw_ff", config.get("default_nsfw", {}))
        elif pairing == "anthro":
            raw = config.get("default_nsfw_anthro", config.get("default_nsfw", {}))
        else:
            raw = config.get("default_nsfw", {})
    else:
        lora_lower = lora_name.lower()
        raw = None
        best_len = 0

        # Check camera_actions first
        for pattern, spec in config.get("camera_actions", {}).items():
            if pattern.lower() in lora_lower and len(pattern) > best_len:
                raw = spec
                best_len = len(pattern)

        # Then check main mappings (longer match wins)
        for pattern, spec in config.get("mappings", {}).items():
            if pattern.lower() in lora_lower and len(pattern) > best_len:
                raw = spec
                best_len = len(pattern)

        if raw is None:
            if pairing == "mm":
                raw = config.get("default_nsfw_mm", config.get("default_nsfw", {}))
            elif pairing == "ff":
                raw = config.get("default_nsfw_ff", config.get("default_nsfw", {}))
            elif pairing == "anthro":
                raw = config.get("default_nsfw_anthro", config.get("default_nsfw", {}))
            else:
                raw = config.get("default_nsfw", {})

    # Normalize: support old format (list) and new format (dict)
    if isinstance(raw, list):
        return {"sfx": raw, "voice_lines": {}}
    return raw


def match_lora_to_sfx(
    lora_name: Optional[str],
    pairing: Optional[str] = None,
) -> list[dict]:
    """Match a LoRA filename to SFX categories from the mapping config.

    Args:
        lora_name: LoRA filename
        pairing: "mm", "ff", "anthro", or None

    Returns list of dicts: [{category, weight, gender, clip_path, duration}, ...]
    """
    mapping = _find_mapping(lora_name, pairing=pairing)
    manifest = _load_manifest()
    categories = manifest.get("categories", {})

    sfx_spec = mapping.get("sfx", [])

    result = []
    for entry in sfx_spec:
        cat = entry.get("category", "")
        gender = entry.get("gender", "female")
        weight = entry.get("weight", 0.5)

        clips = categories.get(cat, [])
        if not clips:
            continue

        gender_clips = [c for c in clips if c.get("gender") == gender]
        pool = gender_clips if gender_clips else clips

        clip = random.choice(pool)
        clip_path = clip.get("path", "")

        if clip_path and Path(clip_path).exists():
            result.append({
                "category": cat,
                "weight": weight,
                "gender": gender,
                "clip_path": clip_path,
                "clip_name": clip.get("name", ""),
                "duration": clip.get("duration", 0),
            })

    return result


def match_lora_to_voice_lines(
    lora_name: Optional[str],
    character_genders: Optional[dict[str, str]] = None,
    pairing: Optional[str] = None,
) -> list[dict]:
    """Match a LoRA to contextual voice dialogue lines.

    Args:
        lora_name: The LoRA filename
        character_genders: {character_name: "male"|"female"} for gender-appropriate line selection
        pairing: "mm", "ff", "anthro", or None

    Returns list of dicts: [{character_slug, gender, line, action}, ...]
    """
    mapping = _find_mapping(lora_name, pairing=pairing)
    voice_lines = mapping.get("voice_lines", {})

    if not voice_lines:
        return []

    # Extract the action name from LoRA for context
    action = _extract_action(lora_name)

    result = []
    if character_genders:
        for slug, gender in character_genders.items():
            lines = voice_lines.get(gender, [])
            if lines:
                result.append({
                    "character_slug": slug,
                    "gender": gender,
                    "line": random.choice(lines),
                    "action": action,
                })
    else:
        # No character info — return one line per available gender
        for gender in ("female", "male"):
            lines = voice_lines.get(gender, [])
            if lines:
                result.append({
                    "character_slug": None,
                    "gender": gender,
                    "line": random.choice(lines),
                    "action": action,
                })

    return result


def detect_pairing(
    character_genders: dict[str, str],
    project_genre: Optional[str] = None,
) -> Optional[str]:
    """Detect pairing type from character genders and project genre.

    Returns "mm", "ff", "anthro", or None (mixed/default).
    """
    genders = set(character_genders.values())

    # Check for anthro/furry based on genre
    if project_genre and any(k in project_genre.lower() for k in ("anthro", "furry", "animal")):
        return "anthro"

    if len(genders) == 1:
        g = genders.pop()
        if g == "male":
            return "mm"
        elif g == "female":
            return "ff"

    return None


def _extract_action(lora_name: Optional[str]) -> str:
    """Extract the action/position name from a LoRA filename."""
    if not lora_name:
        return "general"
    # wan22_nsfw/wan22_doggy_back_HIGH.safetensors -> doggy_back
    base = lora_name.split("/")[-1]
    base = base.replace(".safetensors", "")
    for prefix in ("wan22_", "wan2.2_", "wan22_nsfw_"):
        if base.lower().startswith(prefix):
            base = base[len(prefix):]
    for suffix in ("_HIGH", "_LOW", "_high_noise", "_low_noise"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    return base


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip()) if r.stdout.strip() else 0
    except Exception:
        return 0


def overlay_sfx_on_video(
    video_path: str,
    sfx_clips: list[dict],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Overlay SFX clips onto a video using ffmpeg.

    Each clip is mixed at its specified weight. The original video audio
    (if any) is preserved as the base layer.

    Returns the output path, or None on failure.
    """
    if not sfx_clips:
        return None

    video_path = str(video_path)
    if not Path(video_path).exists():
        logger.warning(f"Video not found: {video_path}")
        return None

    _SFX_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        stem = Path(video_path).stem
        output_path = str(_SFX_OUTPUT_DIR / f"sfx_{stem}.mp4")

    vid_dur = get_video_duration(video_path)
    if vid_dur <= 0:
        logger.warning(f"Cannot determine video duration: {video_path}")
        return None

    # Build ffmpeg command with audio mixing
    inputs = ["-i", video_path]
    for clip in sfx_clips:
        inputs.extend(["-i", clip["clip_path"]])

    n_clips = len(sfx_clips)
    filters = []

    filters.append(f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[base]")

    for i, clip in enumerate(sfx_clips):
        idx = i + 1
        w = clip["weight"]
        filters.append(
            f"[{idx}:a]aloop=loop=-1:size=2e+09,atrim=duration={vid_dur:.2f},"
            f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"volume={w:.2f}[sfx{i}]"
        )

    mix_inputs = "[base]" + "".join(f"[sfx{i}]" for i in range(n_clips))
    filters.append(f"{mix_inputs}amix=inputs={n_clips + 1}:duration=shortest:normalize=0[out]")

    filter_complex = ";".join(filters)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and Path(output_path).exists():
            logger.info(f"SFX overlay complete: {output_path} ({n_clips} clips)")
            return output_path
        else:
            logger.info("Retrying SFX overlay without base audio stream")
            return _overlay_sfx_no_base_audio(video_path, sfx_clips, output_path, vid_dur)
    except subprocess.TimeoutExpired:
        logger.error(f"SFX overlay timed out for {video_path}")
        return None
    except Exception as e:
        logger.error(f"SFX overlay failed: {e}")
        return None


def mix_voice_and_sfx(
    video_path: str,
    voice_wav: str,
    sfx_clips: list[dict],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Mix voice dialogue WAV + foley SFX clips onto a video.

    Voice is placed at full volume, SFX at their configured weights.
    Returns output path or None on failure.
    """
    video_path = str(video_path)
    if not Path(video_path).exists():
        return None

    _VOICE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        stem = Path(video_path).stem
        output_path = str(_VOICE_OUTPUT_DIR / f"av_{stem}.mp4")

    vid_dur = get_video_duration(video_path)
    if vid_dur <= 0:
        return None

    inputs = ["-i", video_path, "-i", voice_wav]
    for clip in sfx_clips:
        inputs.extend(["-i", clip["clip_path"]])

    filters = []
    # Voice track (input 1) — pad/trim to video duration
    filters.append(
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
        f"apad=whole_dur={vid_dur:.2f},atrim=duration={vid_dur:.2f},volume=0.85[voice]"
    )

    n_clips = len(sfx_clips)
    if n_clips == 0:
        # Voice only — no SFX to mix
        filters.append("[voice]acopy[out]")
    else:
        # SFX tracks
        for i, clip in enumerate(sfx_clips):
            idx = i + 2  # offset by video + voice
            w = clip["weight"]
            filters.append(
                f"[{idx}:a]aloop=loop=-1:size=2e+09,atrim=duration={vid_dur:.2f},"
                f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"volume={w:.2f}[sfx{i}]"
            )

        # Mix voice + all SFX
        mix_inputs = "[voice]" + "".join(f"[sfx{i}]" for i in range(n_clips))
        total = 1 + n_clips
        filters.append(f"{mix_inputs}amix=inputs={total}:duration=shortest:normalize=0[out]")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "0:v",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and Path(output_path).exists():
            logger.info(f"Voice+SFX mix complete: {output_path}")
            return output_path
        else:
            logger.error(f"Voice+SFX mix failed: {r.stderr[-300:]}")
            return None
    except Exception as e:
        logger.error(f"Voice+SFX mix failed: {e}")
        return None


def _overlay_sfx_no_base_audio(
    video_path: str, sfx_clips: list[dict], output_path: str, vid_dur: float
) -> Optional[str]:
    """Fallback: overlay SFX when video has no audio stream."""
    n_clips = len(sfx_clips)
    inputs = ["-i", video_path]
    for clip in sfx_clips:
        inputs.extend(["-i", clip["clip_path"]])

    filters = []
    for i, clip in enumerate(sfx_clips):
        idx = i + 1
        w = clip["weight"]
        filters.append(
            f"[{idx}:a]aloop=loop=-1:size=2e+09,atrim=duration={vid_dur:.2f},"
            f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"volume={w:.2f}[sfx{i}]"
        )

    if n_clips == 1:
        filters.append("[sfx0]acopy[out]")
    else:
        mix_inputs = "".join(f"[sfx{i}]" for i in range(n_clips))
        filters.append(f"{mix_inputs}amix=inputs={n_clips}:duration=shortest:normalize=0[out]")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "0:v",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and Path(output_path).exists():
            logger.info(f"SFX overlay (no base audio) complete: {output_path}")
            return output_path
        else:
            logger.error(f"SFX overlay failed: {r.stderr[-300:]}")
            return None
    except Exception as e:
        logger.error(f"SFX overlay fallback failed: {e}")
        return None
