#!/usr/bin/env python3
"""Proper vocal extraction pipeline using source separation + onset detection.

Pipeline:
1. Demucs source separation → isolate vocals from music/noise
2. Librosa onset detection → find exact vocalization boundaries
3. Spectral classification → categorize by pitch, energy, spectral features
4. Per-clip loudness normalization
5. Quality gate → reject low-SNR clips

Usage:
    python3 extract_vocals_proper.py --all          # Process all raw sources
    python3 extract_vocals_proper.py --file X.wav   # Process single file
"""

import argparse
import logging
import math
import os
import subprocess
import sys
import uuid
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path("/opt/anime-studio/output/sfx_library/raw_sources")
OUTPUT_DIR = Path("/opt/anime-studio/output/sfx_library/extracted_proper")
DEMUCS_DIR = Path("/tmp/demucs_separated")

SR = 22050  # Target sample rate
MIN_CLIP_DURATION = 0.5
MAX_CLIP_DURATION = 8.0
MIN_RMS_DB = -40  # Reject clips quieter than this
TARGET_LUFS = -16


def separate_vocals(input_path: str, output_dir: str) -> str | None:
    """Use demucs to separate vocals from background."""
    log.info(f"  Separating vocals with demucs...")
    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",  # Only split vocals vs other
        "-n", "htdemucs",         # Best quality model
        "--out", output_dir,
        input_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            log.error(f"  Demucs failed: {r.stderr[-300:]}")
            return None

        # Find the vocals output
        stem = Path(input_path).stem
        vocals_path = Path(output_dir) / "htdemucs" / stem / "vocals.wav"
        if vocals_path.exists():
            log.info(f"  Vocals isolated: {vocals_path}")
            return str(vocals_path)

        # Try alternate path
        for p in Path(output_dir).rglob("vocals.wav"):
            return str(p)

        log.error("  Vocals file not found after demucs")
        return None
    except subprocess.TimeoutExpired:
        log.error("  Demucs timed out (>10min)")
        return None


def detect_segments(audio: np.ndarray, sr: int) -> list[dict]:
    """Use librosa onset detection to find vocalization segments."""
    # Onset detection
    onset_frames = librosa.onset.onset_detect(
        y=audio, sr=sr,
        hop_length=512,
        backtrack=True,
        units="frames",
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)

    # RMS energy for finding segment boundaries
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)

    # Threshold: median RMS * 2 = "active" audio
    rms_threshold = np.median(rms) * 2.0

    segments = []
    i = 0
    while i < len(onset_times):
        start = onset_times[i]

        # Find end: where RMS drops below threshold for >200ms
        start_frame = int(start * sr / 512)
        end_frame = start_frame
        silence_count = 0
        silence_threshold = int(0.2 * sr / 512)  # 200ms of silence

        for f in range(start_frame, len(rms)):
            if rms[f] < rms_threshold:
                silence_count += 1
                if silence_count >= silence_threshold:
                    end_frame = f - silence_count
                    break
            else:
                silence_count = 0
                end_frame = f
        else:
            end_frame = len(rms) - 1

        end = librosa.frames_to_time(end_frame, sr=sr, hop_length=512)
        duration = end - start

        if MIN_CLIP_DURATION <= duration <= MAX_CLIP_DURATION:
            segments.append({"start": start, "end": end, "duration": duration})

        # Skip to next onset after this segment
        i += 1
        while i < len(onset_times) and onset_times[i] < end + 0.1:
            i += 1

    return segments


def classify_segment(audio_segment: np.ndarray, sr: int) -> dict:
    """Classify a segment using spectral features."""
    duration = len(audio_segment) / sr

    # RMS energy
    rms = np.sqrt(np.mean(audio_segment ** 2))
    rms_db = 20 * math.log10(max(rms, 1e-10))

    if rms_db < MIN_RMS_DB:
        return {"category": "reject", "confidence": 0, "reason": "too_quiet"}

    # Spectral centroid (brightness — higher = breathier/screamy)
    centroid = np.mean(librosa.feature.spectral_centroid(y=audio_segment, sr=sr))

    # Spectral rolloff (where 85% of energy is below)
    rolloff = np.mean(librosa.feature.spectral_rolloff(y=audio_segment, sr=sr, roll_percent=0.85))

    # Zero crossing rate (noise-like = high, tonal = low)
    zcr = np.mean(librosa.feature.zero_crossing_rate(audio_segment))

    # Pitch estimation
    pitches, magnitudes = librosa.piptrack(y=audio_segment, sr=sr)
    pitch_mask = magnitudes > np.median(magnitudes[magnitudes > 0]) if np.any(magnitudes > 0) else magnitudes > 0
    mean_pitch = np.median(pitches[pitch_mask]) if np.any(pitch_mask) else 0

    # Onset strength (transient-heavy = impact sounds)
    onset_env = librosa.onset.onset_strength(y=audio_segment, sr=sr)
    onset_ratio = np.max(onset_env) / (np.mean(onset_env) + 1e-10)

    # RMS variance (dynamic = moaning, flat = breathing)
    rms_frames = librosa.feature.rms(y=audio_segment, frame_length=2048, hop_length=512)[0]
    rms_var = np.std(rms_frames) / (np.mean(rms_frames) + 1e-10)

    features = {
        "rms_db": round(rms_db, 1),
        "centroid": round(centroid, 0),
        "rolloff": round(rolloff, 0),
        "zcr": round(zcr, 4),
        "mean_pitch": round(mean_pitch, 0),
        "onset_ratio": round(onset_ratio, 2),
        "rms_var": round(rms_var, 3),
        "duration": round(duration, 2),
    }

    # Classification rules based on spectral features
    # High pitch (>300Hz) + high energy + high variance = intense moan/scream
    # High pitch + low energy = whimper
    # Low pitch (<200Hz) + short + high onset = grunt
    # High ZCR + rhythmic = panting/breathing
    # Very high centroid + high energy + short = gasp
    # Moderate everything + long = speech

    if duration < 0.8 and onset_ratio > 3.0 and rms_db > -25:
        category, confidence = "gasp", 0.85
    elif rms_db > -15 and rms_var > 0.5 and duration > 2.0:
        category, confidence = "climax", 0.8
    elif rms_db > -15 and mean_pitch > 300 and duration > 1.0:
        category, confidence = "scream", 0.75
    elif rms_db > -20 and rms_var > 0.3 and mean_pitch > 250:
        category, confidence = "moan_intense", 0.8
    elif zcr > 0.08 and rms_var < 0.2 and duration > 1.0:
        category, confidence = "panting", 0.8
    elif zcr > 0.1 and rms_db > -30:
        category, confidence = "breathing", 0.7
    elif rms_db > -25 and rms_var < 0.3 and mean_pitch > 200:
        category, confidence = "moan_soft", 0.8
    elif rms_db > -25 and mean_pitch < 200 and duration < 1.5:
        category, confidence = "grunt", 0.75
    elif rms_db > -25 and rms_var > 0.2 and mean_pitch > 200 and mean_pitch < 400:
        category, confidence = "whimper", 0.7
    elif duration > 2.0 and rms_var > 0.15:
        category, confidence = "speech", 0.6
    elif rms_db > -30:
        category, confidence = "moan_soft", 0.5  # Default vocal
    else:
        category, confidence = "reject", 0.0
        features["reason"] = "unclassifiable"

    features["category"] = category
    features["confidence"] = confidence
    return features


def normalize_clip(audio: np.ndarray) -> np.ndarray:
    """Normalize clip to consistent loudness (-3dB peak)."""
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.7  # -3dB

    # Fade in/out to prevent clicks (10ms)
    fade_samples = min(int(0.01 * SR), len(audio) // 4)
    if fade_samples > 0:
        audio[:fade_samples] *= np.linspace(0, 1, fade_samples)
        audio[-fade_samples:] *= np.linspace(1, 0, fade_samples)

    return audio


def process_source(source_path: str, source_key: str) -> list[dict]:
    """Full pipeline: separate → detect → classify → normalize → save."""
    log.info(f"\n{'='*60}")
    log.info(f"Processing: {Path(source_path).name}")

    # Step 1: Source separation
    demucs_out = str(DEMUCS_DIR / source_key)
    vocals_path = separate_vocals(source_path, demucs_out)
    if not vocals_path:
        log.error("  Source separation failed, using raw audio")
        vocals_path = source_path

    # Step 2: Load vocals
    log.info("  Loading vocals...")
    audio, sr = librosa.load(vocals_path, sr=SR, mono=True)
    log.info(f"  Loaded: {len(audio)/sr:.1f}s @ {sr}Hz")

    # Step 3: Detect segments
    log.info("  Detecting segments...")
    segments = detect_segments(audio, sr)
    log.info(f"  Found {len(segments)} segments")

    # Step 4: Classify and save each segment
    results = []
    for i, seg in enumerate(segments):
        start_sample = int(seg["start"] * sr)
        end_sample = int(seg["end"] * sr)
        clip = audio[start_sample:end_sample]

        features = classify_segment(clip, sr)
        category = features["category"]
        confidence = features["confidence"]

        if category == "reject" or confidence < 0.5:
            continue

        # Normalize
        clip = normalize_clip(clip)

        # Save
        cat_dir = OUTPUT_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        fname = f"{source_key}_v{i:04d}.wav"
        out_path = cat_dir / fname

        sf.write(str(out_path), clip, sr)

        results.append({
            "file": fname,
            "category": category,
            "confidence": confidence,
            "duration": features["duration"],
            "rms_db": features["rms_db"],
            "pitch": features.get("mean_pitch", 0),
            "path": str(out_path),
        })

        if len(results) <= 5 or len(results) % 10 == 0:
            log.info(f"    {fname}: {category} ({confidence:.0%}, {features['duration']:.1f}s, "
                     f"pitch={features.get('mean_pitch', 0):.0f}Hz, rms={features['rms_db']:.0f}dB)")

    return results


def process_all():
    """Process all raw source files."""
    sources = list(RAW_DIR.glob("*.wav"))
    if not sources:
        log.error(f"No WAV files in {RAW_DIR}")
        return

    log.info(f"Found {len(sources)} source files")

    all_results = []
    for src in sorted(sources):
        key = src.stem.lower().replace(" ", "_")[:30]
        # Skip if already processed
        existing = list(OUTPUT_DIR.rglob(f"{key}_v*.wav"))
        if existing:
            log.info(f"[SKIP] {key}: {len(existing)} clips already extracted")
            continue
        results = process_source(str(src), key)
        all_results.extend(results)

    # Summary
    from collections import Counter
    cats = Counter(r["category"] for r in all_results)
    log.info(f"\n{'='*60}")
    log.info(f"TOTAL: {len(all_results)} clips extracted")
    for cat, count in cats.most_common():
        log.info(f"  {cat}: {count}")
    log.info(f"\nOutput: {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Process all raw sources")
    parser.add_argument("--file", type=str, help="Process single file")
    args = parser.parse_args()

    if args.file:
        key = Path(args.file).stem.lower().replace(" ", "_")[:30]
        results = process_source(args.file, key)
        from collections import Counter
        cats = Counter(r["category"] for r in results)
        log.info(f"\nExtracted {len(results)} clips:")
        for c, n in cats.most_common():
            log.info(f"  {c}: {n}")
    elif args.all:
        process_all()
    else:
        parser.print_help()
