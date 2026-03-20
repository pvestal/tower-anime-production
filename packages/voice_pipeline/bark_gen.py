"""Bark-based vocalization generator — produces moans, gasps, breathing etc. on demand.

No library, no downloads, no APIs. Generates unique audio for every shot
using Suno Bark with CPU offload (96GB RAM handles it fine).
"""

import logging
import os
import uuid
from pathlib import Path

import numpy as np
import scipy.io.wavfile
import torch

logger = logging.getLogger(__name__)

VOICE_DATASETS = Path("/opt/anime-studio/voice_datasets")
_bark_loaded = False

# Speaker presets — Bark v2 speakers with distinct vocal qualities
SPEAKERS = {
    "female_soft": "v2/en_speaker_5",
    "female_intense": "v2/en_speaker_9",
    "female_breathy": "v2/en_speaker_3",
    "male_deep": "v2/en_speaker_6",
    "male_rough": "v2/en_speaker_0",
    "male_soft": "v2/en_speaker_2",
}

# Vocalization prompt templates by category
PROMPTS = {
    "moan_soft": [
        "[sighs] mmm... [moans softly]",
        "[soft moan] ahh...",
        "[sighs deeply] mmm...",
        "[gentle moan] ooh...",
    ],
    "moan_intense": [
        "[moans loudly] ahh! yes! [panting]",
        "[loud moan] oh god! [gasps] yes!",
        "[moans intensely] ahh! don't stop! [panting]",
    ],
    "gasp": [
        "[gasps] oh!",
        "[sharp gasp] ah!",
        "[gasps] [heavy breathing]",
    ],
    "whimper": [
        "[whimpers softly] mmm...",
        "[soft whimper] please...",
        "[whimpers] [sighs]",
    ],
    "breathing": [
        "[heavy breathing]",
        "[panting] [heavy breathing]",
        "[breathes heavily] [sighs]",
    ],
    "panting": [
        "[panting] [panting] [heavy breathing]",
        "[rapid breathing] [panting]",
    ],
    "grunt": [
        "[grunts] yeah...",
        "[grunt] [heavy breathing]",
        "[grunts deeply]",
    ],
    "climax": [
        "[moans loudly] oh god! oh god! [screams] yes! [panting]",
        "[loud moan] I'm— [screams] ahh! [heavy breathing]",
    ],
    "scream": [
        "[screams] ahh!",
        "[screams] [gasps]",
    ],
}


def _ensure_bark():
    """Load Bark models on first use — forced CPU to avoid GPU contention."""
    global _bark_loaded
    if _bark_loaded:
        return

    os.environ["SUNO_USE_SMALL_MODELS"] = "1"
    os.environ["SUNO_OFFLOAD_CPU"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Force CPU — GPU is for ComfyUI

    # Fix PyTorch 2.6+ weights_only issue
    import numpy as np
    try:
        torch.serialization.add_safe_globals([np.core.multiarray.scalar])
    except Exception:
        pass

    _orig_load = torch.load
    def _patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _orig_load(*args, **kwargs)
    torch.load = _patched_load

    from bark import preload_models
    preload_models()
    _bark_loaded = True
    logger.info("Bark models loaded (small, CPU-only)")


def generate_vocalization(
    category: str,
    gender: str = "female",
    intensity: str = "medium",
    output_dir: str | None = None,
) -> str | None:
    """Generate a vocalization audio clip using Bark.

    Args:
        category: moan_soft, moan_intense, gasp, whimper, breathing, panting, grunt, climax, scream
        gender: female or male
        intensity: soft, medium, intense (affects speaker selection)
        output_dir: where to save. Defaults to voice_datasets/_generated/

    Returns:
        Path to generated WAV file, or None on failure.
    """
    import random

    _ensure_bark()
    from bark import SAMPLE_RATE, generate_audio

    # Pick prompt
    prompts = PROMPTS.get(category, PROMPTS["moan_soft"])
    prompt = random.choice(prompts)

    # Pick speaker based on gender + intensity
    if gender == "male":
        if intensity == "intense":
            speaker = SPEAKERS["male_rough"]
        elif intensity == "soft":
            speaker = SPEAKERS["male_soft"]
        else:
            speaker = SPEAKERS["male_deep"]
    else:
        if intensity == "intense":
            speaker = SPEAKERS["female_intense"]
        elif intensity == "soft":
            speaker = SPEAKERS["female_breathy"]
        else:
            speaker = SPEAKERS["female_soft"]

    # Generate
    try:
        audio = generate_audio(prompt, history_prompt=speaker)

        # Trim silence from end and cap at 8 seconds
        # Find last sample above noise floor
        abs_audio = np.abs(audio)
        threshold = np.max(abs_audio) * 0.02  # 2% of peak
        nonsilent = np.where(abs_audio > threshold)[0]
        if len(nonsilent) > 0:
            end_idx = min(nonsilent[-1] + int(SAMPLE_RATE * 0.3), len(audio))  # 300ms tail
            audio = audio[:end_idx]
        # Cap at 8 seconds
        max_samples = int(SAMPLE_RATE * 8)
        if len(audio) > max_samples:
            # Fade out last 500ms
            fade_samples = int(SAMPLE_RATE * 0.5)
            audio = audio[:max_samples]
            fade = np.linspace(1.0, 0.0, fade_samples)
            audio[-fade_samples:] *= fade

        # Normalize to -3dB peak (loud and clear)
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.7  # -3dB

        # Save
        if output_dir is None:
            output_dir = str(VOICE_DATASETS / "_generated")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        filename = f"bark_{category}_{gender}_{uuid.uuid4().hex[:8]}.wav"
        output_path = str(Path(output_dir) / filename)
        scipy.io.wavfile.write(output_path, SAMPLE_RATE, audio)

        logger.info(f"Bark generated: {category}/{gender} → {filename} ({len(audio)/SAMPLE_RATE:.1f}s)")
        return output_path

    except Exception as e:
        logger.error(f"Bark generation failed: {e}")
        return None


def vocalization_for_text(
    text: str,
    gender: str = "female",
    output_dir: str | None = None,
) -> str | None:
    """Generate a vocalization matching dialogue text like 'Mmm...', 'Oh...', 'Ahh... yes...'.

    Picks the right category and intensity from the text content.
    """
    clean = text.strip().rstrip("!.").lower()

    # Map text to category + intensity
    if any(w in clean for w in ["oh god", "oh fuck", "don't stop", "harder", "more"]):
        category, intensity = "moan_intense", "intense"
    elif any(w in clean for w in ["ahh", "yes"]):
        category, intensity = "moan_soft", "medium"
    elif any(w in clean for w in ["oh"]):
        category, intensity = "gasp", "medium"
    elif any(w in clean for w in ["mmm", "feels good"]):
        category, intensity = "moan_soft", "soft"
    elif any(w in clean for w in ["please", "stop"]):
        category, intensity = "whimper", "soft"
    elif any(w in clean for w in ["grr", "rrr", "ugh"]):
        category, intensity = "grunt", "medium"
    else:
        category, intensity = "moan_soft", "medium"

    return generate_vocalization(category, gender, intensity, output_dir)
