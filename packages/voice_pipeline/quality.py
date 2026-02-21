"""Audio quality scoring — SNR, duration, speaker confidence metrics."""

import logging
import subprocess
import struct
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_snr(wav_path: str) -> float | None:
    """Estimate Signal-to-Noise Ratio (SNR) in dB for a WAV file.

    Uses a simple energy-based approach: compute RMS of the full signal
    vs RMS of the quietest 10% frames (estimated noise floor).
    """
    try:
        with wave.open(wav_path, "rb") as wf:
            n_frames = wf.getnframes()
            if n_frames == 0:
                return None
            sample_width = wf.getsampwidth()
            raw = wf.readframes(n_frames)

        if sample_width == 2:
            fmt = f"<{n_frames}h"
            samples = list(struct.unpack(fmt, raw))
        else:
            return None

        if not samples:
            return None

        import math

        # Compute frame energies (chunks of 512 samples)
        chunk_size = 512
        energies = []
        for i in range(0, len(samples) - chunk_size, chunk_size):
            chunk = samples[i:i + chunk_size]
            energy = sum(s * s for s in chunk) / chunk_size
            energies.append(energy)

        if not energies:
            return None

        energies.sort()
        # Noise floor = bottom 10% of frame energies
        noise_count = max(1, len(energies) // 10)
        noise_energy = sum(energies[:noise_count]) / noise_count
        signal_energy = sum(energies) / len(energies)

        if noise_energy <= 0:
            return 40.0  # Very clean signal

        snr = 10 * math.log10(signal_energy / noise_energy)
        return round(snr, 1)

    except Exception as e:
        logger.warning(f"SNR computation failed for {wav_path}: {e}")
        return None


def compute_duration(wav_path: str) -> float | None:
    """Get duration of a WAV file in seconds."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", wav_path],
            capture_output=True, text=True, timeout=10,
        )
        return round(float(result.stdout.strip()), 2) if result.stdout.strip() else None
    except Exception as e:
        logger.warning(f"Duration probe failed for {wav_path}: {e}")
        return None


def score_voice_sample(
    wav_path: str,
    snr_db: float | None = None,
    duration_seconds: float | None = None,
    speaker_confidence: float | None = None,
) -> float:
    """Compute a composite quality score (0.0–1.0) for a voice sample.

    Factors:
    - SNR: higher is better, 20+ dB is good
    - Duration: 2-15s is ideal for training, too short or too long penalized
    - Speaker confidence: from diarization overlap ratio
    """
    score = 0.0
    weights = 0.0

    # SNR component (weight: 0.4)
    if snr_db is None:
        snr_db = compute_snr(wav_path)
    if snr_db is not None:
        if snr_db >= 25:
            snr_score = 1.0
        elif snr_db >= 15:
            snr_score = 0.5 + 0.5 * (snr_db - 15) / 10
        elif snr_db >= 5:
            snr_score = 0.2 + 0.3 * (snr_db - 5) / 10
        else:
            snr_score = max(0, snr_db / 5 * 0.2)
        score += 0.4 * snr_score
        weights += 0.4

    # Duration component (weight: 0.3)
    if duration_seconds is None:
        duration_seconds = compute_duration(wav_path)
    if duration_seconds is not None:
        if 2.0 <= duration_seconds <= 15.0:
            dur_score = 1.0
        elif 1.0 <= duration_seconds < 2.0:
            dur_score = 0.5 + 0.5 * (duration_seconds - 1.0)
        elif 15.0 < duration_seconds <= 30.0:
            dur_score = 1.0 - 0.5 * (duration_seconds - 15.0) / 15.0
        elif duration_seconds < 1.0:
            dur_score = max(0, duration_seconds * 0.5)
        else:
            dur_score = 0.3
        score += 0.3 * dur_score
        weights += 0.3

    # Speaker confidence component (weight: 0.3)
    if speaker_confidence is not None:
        score += 0.3 * min(1.0, speaker_confidence)
        weights += 0.3

    if weights == 0:
        return 0.5  # No data available

    return round(score / weights, 3)
