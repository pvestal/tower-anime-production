#!/usr/bin/env python3
"""Extract and clean voice SFX from raw audio sources.

Uses sox for noise reduction + vocal isolation, then splits and classifies.
Outputs clean voice segments into extracted_proper/ categories.

Usage:
  python3 extract_clean_voices.py                  # Process all raw_sources + alga_rd_3
  python3 extract_clean_voices.py --file foo.wav   # Process single file
  python3 extract_clean_voices.py --dry-run        # Show what would be processed
"""

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

LIBRARY_DIR = Path("/opt/anime-studio/output/sfx_library")
RAW_SOURCES = LIBRARY_DIR / "raw_sources"
WAV_CACHE = LIBRARY_DIR / "wav_cache"
OUTPUT_DIR = LIBRARY_DIR / "extracted_proper"

# Only process these source stems from wav_cache
TARGET_SOURCES = [
    "alga_rd",
    "alga_rd_2",
    "alga_rd_3",
    "avenida_olmeda",
    "avenida_olmeda_2",
    "avenida_olmeda_3",
    "hotel_las_golondrinas",
]

# Voice isolation parameters
VOICE_HIGHPASS_HZ = 80
VOICE_LOWPASS_HZ = 8000
NOISE_REDUCTION_AMOUNT = 0.25  # 0.0-1.0, higher = more aggressive

# Segment parameters
MIN_SEGMENT_S = 0.3
MAX_SEGMENT_S = 10.0
SILENCE_THRESH_DB = -32
MIN_SILENCE_S = 0.25

# Classification thresholds
MIN_VOICE_RMS_DB = -38
MIN_CONFIDENCE = 0.45


def run(cmd, timeout=120, check=False):
    """Run a subprocess, return CompletedProcess."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def get_duration(wav_path: str) -> float:
    r = run(["soxi", "-D", wav_path], timeout=10)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def clean_audio(input_wav: str, output_wav: str, noise_profile: str = None) -> bool:
    """Apply vocal isolation and noise reduction via sox.

    Pipeline:
      1. Highpass 80Hz (remove rumble)
      2. Lowpass 8kHz (remove hiss/artifacts above voice range)
      3. Noise reduction (if noise profile provided)
      4. Compand (normalize dynamics)
      5. Normalize to -1dB
    """
    effects = [
        "highpass", str(VOICE_HIGHPASS_HZ),
        "lowpass", str(VOICE_LOWPASS_HZ),
    ]

    if noise_profile:
        effects += ["noisered", noise_profile, str(NOISE_REDUCTION_AMOUNT)]

    effects += [
        "compand", "0.3,1", "6:-70,-60,-20", "-5", "-90", "0.2",
        "norm", "-1",
    ]

    cmd = ["sox", input_wav, "-r", "22050", "-c", "1", "-b", "16", output_wav] + effects
    r = run(cmd, timeout=60)
    return r.returncode == 0 and Path(output_wav).exists()


def create_noise_profile(wav_path: str, profile_path: str) -> bool:
    """Extract a noise profile from the first 0.5s of silence in a file."""
    # Extract first 0.5s for noise profiling
    sample_wav = profile_path + ".sample.wav"
    r = run(["sox", wav_path, sample_wav, "trim", "0", "0.5"])
    if r.returncode != 0:
        return False

    r = run(["sox", sample_wav, "-n", "noiseprof", profile_path])
    try:
        os.unlink(sample_wav)
    except OSError:
        pass
    return r.returncode == 0 and Path(profile_path).exists()


def split_on_silence(wav_path: str) -> list[dict]:
    """Split audio on silence using ffmpeg silencedetect."""
    cmd = [
        "ffmpeg", "-i", wav_path,
        "-af", f"silencedetect=noise={SILENCE_THRESH_DB}dB:d={MIN_SILENCE_S:.2f}",
        "-f", "null", "-",
    ]
    r = run(cmd, timeout=120)
    stderr = r.stderr

    silence_starts = []
    silence_ends = []
    for line in stderr.split("\n"):
        if "silence_start:" in line:
            try:
                t = float(line.split("silence_start:")[1].strip().split()[0])
                silence_starts.append(t)
            except (ValueError, IndexError):
                pass
        elif "silence_end:" in line:
            try:
                t = float(line.split("silence_end:")[1].strip().split()[0])
                silence_ends.append(t)
            except (ValueError, IndexError):
                pass

    total_dur = get_duration(wav_path)

    segments = []
    if not silence_starts and not silence_ends:
        if MIN_SEGMENT_S <= total_dur <= MAX_SEGMENT_S:
            segments.append({"start": 0, "end": total_dur})
        return segments

    # First segment
    if silence_starts and silence_starts[0] > MIN_SEGMENT_S:
        end = min(silence_starts[0], MAX_SEGMENT_S)
        segments.append({"start": 0, "end": end})

    # Between silences
    for i in range(len(silence_ends)):
        seg_start = silence_ends[i]
        seg_end = silence_starts[i + 1] if i + 1 < len(silence_starts) else total_dur
        dur = seg_end - seg_start
        if MIN_SEGMENT_S <= dur <= MAX_SEGMENT_S:
            segments.append({"start": seg_start, "end": seg_end})
        elif dur > MAX_SEGMENT_S:
            # Split long segments into MAX_SEGMENT_S chunks
            pos = seg_start
            while pos < seg_end:
                chunk_end = min(pos + MAX_SEGMENT_S, seg_end)
                if chunk_end - pos >= MIN_SEGMENT_S:
                    segments.append({"start": pos, "end": chunk_end})
                pos = chunk_end

    return segments


def extract_segment(wav_path: str, start: float, end: float, output_path: str) -> bool:
    """Extract a time range from a WAV file."""
    duration = end - start
    cmd = [
        "sox", wav_path, output_path,
        "trim", f"{start:.3f}", f"{duration:.3f}",
    ]
    r = run(cmd, timeout=30)
    return r.returncode == 0 and Path(output_path).exists()


def classify_voice(wav_path: str) -> dict:
    """Classify a voice segment by audio features."""
    try:
        with wave.open(wav_path, "rb") as wf:
            n_frames = wf.getnframes()
            sample_rate = wf.getframerate()
            sw = wf.getsampwidth()
            raw = wf.readframes(n_frames)
    except Exception:
        return {"category": "unknown", "confidence": 0}

    if sw != 2 or n_frames < 100:
        return {"category": "unknown", "confidence": 0}

    samples = list(struct.unpack(f"<{n_frames}h", raw))
    duration = n_frames / sample_rate

    # RMS energy
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768
    rms_db = 20 * math.log10(max(rms, 1e-10))

    # Skip too quiet segments
    if rms_db < MIN_VOICE_RMS_DB:
        return {"category": "silence", "confidence": 0}

    # Peak
    peak = max(abs(s) for s in samples) / 32768

    # Zero crossing rate
    zcr = sum(1 for i in range(1, len(samples)) if samples[i - 1] * samples[i] < 0) / len(samples)

    # Energy variance (100ms chunks)
    chunk_size = max(sample_rate // 10, 1)
    energies = []
    for i in range(0, len(samples) - chunk_size, chunk_size):
        chunk = samples[i:i + chunk_size]
        e = sum(s * s for s in chunk) / len(chunk)
        energies.append(e)
    energy_var = (max(energies) - min(energies)) / max(max(energies), 1) if energies else 0

    # Onset sharpness
    onset_ratio = 0
    if len(energies) >= 3:
        onset_ratio = energies[0] / max(sum(energies) / len(energies), 1e-10)

    features = {
        "duration": round(duration, 2),
        "rms_db": round(rms_db, 1),
        "peak": round(peak, 3),
        "zcr": round(zcr, 4),
        "energy_variance": round(energy_var, 3),
        "onset_ratio": round(onset_ratio, 3),
    }

    # Voice-focused classification
    if duration < 0.6 and onset_ratio > 2.0 and peak > 0.2:
        category, confidence = "gasp", 0.8
    elif rms_db > -15 and energy_var > 0.6 and duration > 2:
        category, confidence = "scream", 0.75
    elif rms_db > -18 and energy_var > 0.5 and duration > 1.5:
        category, confidence = "moan_intense", 0.7
    elif rms_db > -28 and duration > 1 and energy_var < 0.35:
        category, confidence = "moan_soft", 0.7
    elif rms_db > -30 and zcr > 0.1 and duration > 1.0:
        category, confidence = "breathing", 0.65
    elif rms_db > -30 and zcr < 0.08 and duration > 0.4 and duration < 2:
        category, confidence = "whimper", 0.6
    elif duration > 2 and zcr > 0.04 and energy_var > 0.2:
        category, confidence = "speech", 0.55
    elif rms_db > -25 and zcr > 0.12 and duration < 1.5:
        category, confidence = "breathing", 0.6
    elif rms_db > -28 and duration > 0.5:
        category, confidence = "moan_soft", 0.55
    else:
        category, confidence = "uncategorized", 0.3

    features["category"] = category
    features["confidence"] = confidence
    return features


def process_file(source_path: str, source_key: str, max_segments: int = 200) -> list[dict]:
    """Process one source file: clean → split → classify → save."""
    results = []
    print(f"\n{'='*60}")
    print(f"Processing: {Path(source_path).name} ({source_key})")
    dur = get_duration(source_path)
    print(f"  Duration: {dur:.1f}s ({dur/60:.1f}min)")

    # Check how many we already have
    existing = list(OUTPUT_DIR.rglob(f"{source_key}_clean_*.wav"))
    if existing:
        print(f"  Already have {len(existing)} clean segments — skipping")
        return results

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Convert to consistent format
        normalized = str(tmpdir / "normalized.wav")
        r = run(["sox", source_path, "-r", "22050", "-c", "1", "-b", "16", normalized])
        if r.returncode != 0:
            # Try ffmpeg as fallback
            r = run([
                "ffmpeg", "-y", "-i", source_path,
                "-ar", "22050", "-ac", "1", "-acodec", "pcm_s16le", normalized
            ])
            if r.returncode != 0:
                print(f"  ERROR: Cannot convert audio")
                return results

        # Step 2: Create noise profile from first 0.5s
        noise_profile = str(tmpdir / "noise.prof")
        has_profile = create_noise_profile(normalized, noise_profile)
        if has_profile:
            print(f"  Noise profile created")
        else:
            noise_profile = None
            print(f"  No noise profile (will skip noisered)")

        # Step 3: Apply vocal cleanup to full file
        cleaned = str(tmpdir / "cleaned.wav")
        if not clean_audio(normalized, cleaned, noise_profile):
            print(f"  ERROR: Cleanup failed, using raw audio")
            cleaned = normalized

        # Step 4: Split on silence
        segments = split_on_silence(cleaned)
        print(f"  Found {len(segments)} voice segments")

        # Step 5: Extract, classify, and save each segment
        saved = 0
        skipped_quiet = 0
        skipped_low_conf = 0

        for i, seg in enumerate(segments[:max_segments]):
            seg_wav = str(tmpdir / f"seg_{i:04d}.wav")
            if not extract_segment(cleaned, seg["start"], seg["end"], seg_wav):
                continue

            features = classify_voice(seg_wav)
            category = features.get("category", "unknown")
            confidence = features.get("confidence", 0)

            if category in ("silence", "unknown"):
                skipped_quiet += 1
                continue
            if confidence < MIN_CONFIDENCE:
                skipped_low_conf += 1
                continue

            # Save to extracted_proper/category/
            cat_dir = OUTPUT_DIR / category
            cat_dir.mkdir(parents=True, exist_ok=True)

            out_name = f"{source_key}_clean_{i:04d}.wav"
            out_path = cat_dir / out_name

            if out_path.exists():
                continue

            # Final per-segment normalization
            run(["sox", seg_wav, str(out_path), "norm", "-1"])

            if out_path.exists():
                results.append({
                    "filename": out_name,
                    "category": category,
                    "confidence": confidence,
                    "duration": features["duration"],
                    "rms_db": features["rms_db"],
                    "source": Path(source_path).name,
                })
                saved += 1

        print(f"  Saved: {saved} | Quiet: {skipped_quiet} | Low-conf: {skipped_low_conf}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Extract clean voice SFX from raw sources")
    parser.add_argument("--file", type=str, help="Process a single file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--max-segments", type=int, default=200, help="Max segments per file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        source = Path(args.file)
        if not source.exists():
            print(f"File not found: {source}")
            sys.exit(1)
        key = source.stem.lower().replace(" ", "_")[:30]
        results = process_file(str(source), key, args.max_segments)
    else:
        # Only process target files from wav_cache
        sources = []
        for stem in TARGET_SOURCES:
            f = WAV_CACHE / f"{stem}.wav"
            if f.exists():
                sources.append((str(f), stem))
            else:
                print(f"[MISSING] {f.name}")

        if args.dry_run:
            print(f"Would process {len(sources)} files:")
            for path, key in sources:
                dur = get_duration(path)
                existing = list(OUTPUT_DIR.rglob(f"{key}_clean_*.wav"))
                status = f"({len(existing)} existing)" if existing else "(new)"
                print(f"  {key}: {dur/60:.1f}min {status}")
            sys.exit(0)

        all_results = []
        for path, key in sources:
            results = process_file(path, key, args.max_segments)
            all_results.extend(results)

        # Summary
        print(f"\n{'='*60}")
        print(f"TOTAL: {len(all_results)} clean voice segments extracted")
        if all_results:
            from collections import Counter
            cats = Counter(r["category"] for r in all_results)
            for cat, count in cats.most_common():
                print(f"  {cat}: {count}")

        # Save extraction log
        log_path = OUTPUT_DIR / "extraction_log.json"
        with open(log_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nLog saved: {log_path}")


if __name__ == "__main__":
    main()
