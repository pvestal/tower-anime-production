"""BPM-aware audio sequencer — builds multi-layer scene audio synced to video motion.

Instead of slapping a single clip over a video, this sequencer:
1. Determines the action rhythm from LoRA name + motion tier
2. Builds a multi-layer audio timeline:
   - Body foley layer (skin_slap at BPM rhythm)
   - Breathing layer (continuous, intensity-matched)
   - Vocalization layer (sparse moans/gasps at musical intervals)
3. Mixes and normalizes to broadcast loudness

Uses Bark full-quality clips from /opt/anime-studio/output/sfx_test/bark_full/
and real extracted foley from /opt/anime-studio/output/sfx_library/
"""

import logging
import math
import os
import random
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

BARK_LIB = Path("/opt/anime-studio/output/sfx_test/bark_full")
REAL_LIB = Path("/opt/anime-studio/output/sfx_library/extracted_proper")
SFX_LIB = Path("/opt/anime-studio/output/sfx_library")
OUTPUT_DIR = Path("/opt/anime-studio/output/sequenced_audio")

# Action → rhythm profile
# bpm: beats per minute of the primary motion
# body_layer: foley category for rhythmic body sounds
# vocal_density: how often vocalizations appear (0-1, fraction of beats)
# intensity: soft/medium/intense — controls which Bark clips to pick
# breathing_rate: breaths per second
ACTION_PROFILES = {
    # Penetrative — rhythmic
    "missionary":       {"bpm": 100, "body_layer": "skin_slap", "vocal_density": 0.3, "intensity": "medium", "breathing_rate": 0.8},
    "doggy":            {"bpm": 130, "body_layer": "skin_slap", "vocal_density": 0.4, "intensity": "intense", "breathing_rate": 1.0},
    "from_behind":      {"bpm": 120, "body_layer": "skin_slap", "vocal_density": 0.35, "intensity": "intense", "breathing_rate": 0.9},
    "sfbehind":         {"bpm": 120, "body_layer": "skin_slap", "vocal_density": 0.35, "intensity": "intense", "breathing_rate": 0.9},
    "cowgirl":          {"bpm": 110, "body_layer": "skin_slap", "vocal_density": 0.35, "intensity": "medium", "breathing_rate": 0.9},
    "reverse_cowgirl":  {"bpm": 110, "body_layer": "skin_slap", "vocal_density": 0.3, "intensity": "medium", "breathing_rate": 0.8},
    "prone_bone":       {"bpm": 90,  "body_layer": "skin_slap", "vocal_density": 0.4, "intensity": "intense", "breathing_rate": 1.0},
    "spooning":         {"bpm": 70,  "body_layer": "skin_slap", "vocal_density": 0.25, "intensity": "soft", "breathing_rate": 0.6},
    "squatting_cowgirl":{"bpm": 120, "body_layer": "skin_slap", "vocal_density": 0.4, "intensity": "intense", "breathing_rate": 1.0},
    # Oral — less rhythmic
    "sensual_bj":       {"bpm": 60,  "body_layer": None, "vocal_density": 0.2, "intensity": "soft", "breathing_rate": 0.5},
    "combo_hj_bj":      {"bpm": 80,  "body_layer": None, "vocal_density": 0.25, "intensity": "medium", "breathing_rate": 0.6},
    "lips-bj":          {"bpm": 60,  "body_layer": None, "vocal_density": 0.15, "intensity": "soft", "breathing_rate": 0.4},
    "double_blowjob":   {"bpm": 70,  "body_layer": None, "vocal_density": 0.3, "intensity": "medium", "breathing_rate": 0.5},
    # Climax
    "climax":           {"bpm": 150, "body_layer": "skin_slap", "vocal_density": 0.6, "intensity": "intense", "breathing_rate": 1.5},
    "facial":           {"bpm": 100, "body_layer": None, "vocal_density": 0.5, "intensity": "intense", "breathing_rate": 1.0},
    "maleejac":         {"bpm": 100, "body_layer": None, "vocal_density": 0.5, "intensity": "intense", "breathing_rate": 1.0},
    # Soft/affection
    "embrace":          {"bpm": 40,  "body_layer": None, "vocal_density": 0.1, "intensity": "soft", "breathing_rate": 0.3},
    "kiss":             {"bpm": 40,  "body_layer": None, "vocal_density": 0.1, "intensity": "soft", "breathing_rate": 0.3},
    "massage_tits":     {"bpm": 50,  "body_layer": None, "vocal_density": 0.2, "intensity": "soft", "breathing_rate": 0.4},
    "softcore":         {"bpm": 50,  "body_layer": None, "vocal_density": 0.15, "intensity": "soft", "breathing_rate": 0.4},
    # Equipment
    "fucking_machine":  {"bpm": 160, "body_layer": None, "vocal_density": 0.5, "intensity": "intense", "breathing_rate": 1.5},
    # SFW
    "idle":             {"bpm": 0,   "body_layer": None, "vocal_density": 0, "intensity": "soft", "breathing_rate": 0.2},
    "walk":             {"bpm": 0,   "body_layer": "footstep_soft", "vocal_density": 0, "intensity": "soft", "breathing_rate": 0.2},
    "talking":          {"bpm": 0,   "body_layer": None, "vocal_density": 0, "intensity": "soft", "breathing_rate": 0.2},
}

# Default for unknown actions
DEFAULT_PROFILE = {"bpm": 90, "body_layer": "skin_slap", "vocal_density": 0.3, "intensity": "medium", "breathing_rate": 0.7}


def _get_profile(lora_name: Optional[str]) -> dict:
    """Get action profile from LoRA name."""
    if not lora_name:
        return DEFAULT_PROFILE
    lower = lora_name.lower()
    # Match longest key first
    best_match = None
    best_len = 0
    for action, profile in ACTION_PROFILES.items():
        if action in lower and len(action) > best_len:
            best_match = profile
            best_len = len(action)
    return best_match or DEFAULT_PROFILE


def _pick_clip(category: str, gender: str = "female") -> Optional[str]:
    """Pick a real extracted vocal clip. Falls back to Bark if none available."""
    # Priority 1: Properly extracted real vocals (demucs separated)
    real_dir = REAL_LIB / category
    if real_dir.is_dir():
        clips = list(real_dir.glob("*.wav"))
        if clips:
            return str(random.choice(clips))

    # Priority 2: Bark full-quality generated clips
    pattern = f"bark_{category}_{gender}_*.wav"
    clips = list(BARK_LIB.glob(pattern))
    if not clips:
        clips = list(BARK_LIB.glob(f"bark_{category}_*.wav"))
    if clips:
        return str(random.choice(clips))

    return None


def _pick_foley(category: str) -> Optional[str]:
    """Pick a foley clip from the SFX library (real recordings)."""
    dirs = [
        SFX_LIB / "foley" / category,
        SFX_LIB / "categorized" / category,
    ]
    clips = []
    for d in dirs:
        if d.is_dir():
            clips.extend(d.glob("*.wav"))
    if not clips:
        return None
    return str(random.choice(clips))


def _get_clip_duration(path: str) -> float:
    """Get audio file duration."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip()) if r.stdout.strip() else 0
    except Exception:
        return 0


def _generate_silence(duration: float, sample_rate: int = 24000) -> np.ndarray:
    """Generate silence array."""
    return np.zeros(int(duration * sample_rate), dtype=np.float32)


def sequence_audio(
    video_duration: float,
    lora_name: Optional[str] = None,
    gender: str = "female",
    pairing: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Build a BPM-synced multi-layer audio track for a video.

    Args:
        video_duration: Length of video in seconds
        lora_name: LoRA action name (determines rhythm)
        gender: Primary character gender
        pairing: mm/ff/anthro/None
        output_path: Where to save. Auto-generated if None.

    Returns:
        Path to sequenced WAV file, or None on failure.
    """
    try:
        import scipy.io.wavfile
    except ImportError:
        logger.error("scipy not available for audio sequencing")
        return None

    profile = _get_profile(lora_name)
    bpm = profile["bpm"]
    body_layer = profile["body_layer"]
    vocal_density = profile["vocal_density"]
    intensity = profile["intensity"]
    breathing_rate = profile["breathing_rate"]

    SR = 24000  # Match Bark sample rate
    total_samples = int(video_duration * SR)

    if total_samples < SR:
        return None

    # Initialize output buffer
    output = np.zeros(total_samples, dtype=np.float32)

    # --- Layer 1: Body foley at BPM rhythm ---
    if body_layer and bpm > 0:
        foley_path = _pick_foley(body_layer)
        if foley_path:
            try:
                _, foley_data = scipy.io.wavfile.read(foley_path)
                if foley_data.dtype != np.float32:
                    foley_data = foley_data.astype(np.float32) / 32768.0
                # Resample if needed
                if len(foley_data) > SR:
                    foley_data = foley_data[:SR]  # Trim to 1s max

                beat_interval = 60.0 / bpm  # seconds between beats
                beat_samples = int(beat_interval * SR)

                # Place foley at each beat
                pos = 0
                while pos < total_samples:
                    end = min(pos + len(foley_data), total_samples)
                    clip_len = end - pos
                    # Vary volume slightly per hit for realism
                    vol = random.uniform(0.15, 0.25)
                    output[pos:end] += foley_data[:clip_len] * vol
                    pos += beat_samples
                    # Slight timing humanization (±5%)
                    pos += int(random.uniform(-0.05, 0.05) * beat_samples)

                logger.debug(f"Body foley: {body_layer} at {bpm}BPM")
            except Exception as e:
                logger.warning(f"Body foley failed: {e}")

    # --- Layer 2: Breathing/panting ---
    if breathing_rate > 0:
        breath_cat = "panting" if breathing_rate > 0.8 else "breathing"
        breath_path = _pick_clip(breath_cat, gender)
        if breath_path:
            try:
                _, breath_data = scipy.io.wavfile.read(breath_path)
                if breath_data.dtype != np.float32:
                    breath_data = breath_data.astype(np.float32) / 32768.0

                breath_interval = 1.0 / breathing_rate  # seconds between breaths
                breath_samples = int(breath_interval * SR)

                pos = int(random.uniform(0, breath_interval) * SR)  # Random start offset
                while pos < total_samples:
                    end = min(pos + len(breath_data), total_samples)
                    clip_len = end - pos
                    vol = random.uniform(0.10, 0.18)
                    output[pos:end] += breath_data[:clip_len] * vol
                    pos += breath_samples
                    # More humanization
                    pos += int(random.uniform(-0.1, 0.1) * breath_samples)

                logger.debug(f"Breathing: {breath_cat} at {breathing_rate}/s")
            except Exception as e:
                logger.warning(f"Breathing layer failed: {e}")

    # --- Layer 3: Vocalizations at musical intervals ---
    if vocal_density > 0:
        # Pick vocalization category based on intensity
        if intensity == "intense":
            vocal_cats = ["moan_intense", "climax", "scream"]
            vocal_vol = 0.5
        elif intensity == "soft":
            vocal_cats = ["moan_soft", "whimper"]
            vocal_vol = 0.35
        else:
            vocal_cats = ["moan_soft", "gasp", "moan_intense"]
            vocal_vol = 0.4

        # Decide male or female vocalizations
        vocal_gender = gender
        if pairing == "mm":
            vocal_gender = "male"

        # Place vocalizations at musical intervals (every 2-4 beats)
        if bpm > 0:
            beat_interval = 60.0 / bpm
            vocal_interval = beat_interval * random.choice([2, 3, 4])  # Every 2-4 beats
        else:
            vocal_interval = random.uniform(2.0, 4.0)  # Ambient: every 2-4 seconds

        pos = int(random.uniform(0.5, vocal_interval) * SR)  # Start after half interval
        while pos < total_samples:
            # Only vocalize with probability = vocal_density
            if random.random() < vocal_density:
                cat = random.choice(vocal_cats)
                clip_path = _pick_clip(cat, vocal_gender)
                if clip_path:
                    try:
                        _, vocal_data = scipy.io.wavfile.read(clip_path)
                        if vocal_data.dtype != np.float32:
                            vocal_data = vocal_data.astype(np.float32) / 32768.0

                        # Use first 2-3 seconds of the clip
                        max_len = int(random.uniform(1.5, 3.0) * SR)
                        vocal_data = vocal_data[:max_len]

                        # Fade in/out for smooth placement
                        fade = min(int(0.05 * SR), len(vocal_data) // 4)
                        if fade > 0:
                            vocal_data[:fade] *= np.linspace(0, 1, fade)
                            vocal_data[-fade:] *= np.linspace(1, 0, fade)

                        end = min(pos + len(vocal_data), total_samples)
                        clip_len = end - pos
                        output[pos:end] += vocal_data[:clip_len] * vocal_vol
                    except Exception:
                        pass

            pos += int(vocal_interval * SR)
            # Humanize timing ±15%
            pos += int(random.uniform(-0.15, 0.15) * vocal_interval * SR)

    # --- Normalize final mix ---
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.7  # -3dB headroom

    # --- Save ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = str(OUTPUT_DIR / f"seq_{uuid.uuid4().hex[:8]}.wav")

    scipy.io.wavfile.write(output_path, SR, output)

    duration = len(output) / SR
    action = lora_name.split("/")[-1].replace(".safetensors", "") if lora_name else "default"
    logger.info(f"Sequenced {duration:.1f}s audio: {action} @ {bpm}BPM, "
                f"body={'yes' if body_layer else 'no'}, "
                f"vocal_density={vocal_density:.0%}, "
                f"intensity={intensity}")

    return output_path


def sequence_for_video(
    video_path: str,
    lora_name: Optional[str] = None,
    gender: str = "female",
    pairing: Optional[str] = None,
) -> Optional[str]:
    """Convenience: get video duration and sequence audio for it."""
    dur = 0
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10,
        )
        dur = float(r.stdout.strip()) if r.stdout.strip() else 0
    except Exception:
        return None

    if dur <= 0:
        return None

    return sequence_audio(dur, lora_name, gender, pairing)
