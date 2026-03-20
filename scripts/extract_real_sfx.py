#!/usr/bin/env python3
"""Extract and categorize real SFX from explicit video/audio sources.

Sources:
1. Local files (from explicit_video_scan.json candidates)
2. URLs (xHamster, PornHub, etc. via yt-dlp)

Pipeline:
  source → ffmpeg extract audio → silence split → energy classify → categorize → library

Categories detected by audio features:
  - moan_soft: mid energy, sustained, female vocal band
  - moan_intense: high energy, peaks, female vocal band
  - gasp: short burst, sharp onset
  - breathing/panting: rhythmic, low energy, breathy
  - whimper: low energy, high pitch variation
  - grunt: short, low pitch, male vocal band
  - climax: high energy sustained peak
  - speech/dirty_talk: longer segments with varied pitch
  - skin_slap: sharp transient, no vocal
  - wet_foley: low-mid frequency, sustained
"""

import argparse
import json
import logging
import math
import os
import struct
import subprocess
import sys
import tempfile
import uuid
import wave
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

LIBRARY_DIR = Path("/opt/anime-studio/output/sfx_library")
CATEGORIZED_DIR = LIBRARY_DIR / "categorized"
SCAN_FILE = LIBRARY_DIR / "explicit_video_scan.json"
MANIFEST_FILE = Path("/opt/anime-studio/output/sfx_test/sfx_manifest.json")

# Audio analysis thresholds
MIN_SEGMENT_DURATION = 0.4  # seconds
MAX_SEGMENT_DURATION = 12.0
SILENCE_THRESHOLD_DB = -35  # dB below which is silence
MIN_SNR_DB = 5.0


def extract_audio(source_path: str, output_wav: str, sample_rate: int = 22050) -> bool:
    """Extract audio from video/audio file to mono WAV."""
    cmd = [
        "ffmpeg", "-y", "-i", source_path,
        "-vn", "-ar", str(sample_rate), "-ac", "1",
        "-acodec", "pcm_s16le", output_wav,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and Path(output_wav).exists()


def download_url(url: str, output_dir: str) -> str | None:
    """Download audio from URL via yt-dlp."""
    output_path = os.path.join(output_dir, "downloaded_%(id)s.%(ext)s")
    cmd = [
        "yt-dlp", "--extract-audio", "--audio-format", "wav",
        "--audio-quality", "0",
        "--output", output_path,
        "--no-playlist",
        "--quiet",
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            # Find the output file
            for f in Path(output_dir).glob("downloaded_*.wav"):
                return str(f)
        log.error(f"yt-dlp failed: {r.stderr[:200]}")
    except subprocess.TimeoutExpired:
        log.error("yt-dlp timed out")
    return None


def split_on_silence(wav_path: str, min_silence_ms: int = 300) -> list[dict]:
    """Split WAV into segments based on silence detection via ffmpeg silencedetect."""
    cmd = [
        "ffmpeg", "-i", wav_path,
        "-af", f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={min_silence_ms / 1000:.2f}",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    stderr = r.stderr

    # Parse silence start/end from ffmpeg output
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

    # Get total duration
    dur_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", wav_path,
    ]
    dr = subprocess.run(dur_cmd, capture_output=True, text=True, timeout=10)
    total_dur = float(dr.stdout.strip()) if dr.stdout.strip() else 0

    # Build segments (between silences)
    segments = []
    if not silence_starts and not silence_ends:
        # No silence found — whole file is one segment
        if MIN_SEGMENT_DURATION <= total_dur <= MAX_SEGMENT_DURATION:
            segments.append({"start": 0, "end": total_dur})
        return segments

    # First segment: start of file to first silence
    if silence_starts and silence_starts[0] > MIN_SEGMENT_DURATION:
        segments.append({"start": 0, "end": silence_starts[0]})

    # Middle segments: between silence_end[i] and silence_start[i+1]
    for i in range(len(silence_ends)):
        seg_start = silence_ends[i]
        seg_end = silence_starts[i + 1] if i + 1 < len(silence_starts) else total_dur
        dur = seg_end - seg_start
        if MIN_SEGMENT_DURATION <= dur <= MAX_SEGMENT_DURATION:
            segments.append({"start": seg_start, "end": seg_end})

    return segments


def extract_segment(wav_path: str, start: float, end: float, output_path: str) -> bool:
    """Extract a segment from a WAV file."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-ar", "22050", "-ac", "1", "-acodec", "pcm_s16le",
        output_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.returncode == 0 and Path(output_path).exists()


def analyze_segment(wav_path: str) -> dict:
    """Analyze audio features to classify segment type."""
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

    # Peak detection
    abs_samples = [abs(s) for s in samples]
    peak = max(abs_samples) / 32768

    # Zero crossing rate (indicator of pitch/noise)
    zcr = sum(1 for i in range(1, len(samples)) if samples[i - 1] * samples[i] < 0) / len(samples)

    # Energy variance (chunked)
    chunk_size = sample_rate // 10  # 100ms chunks
    energies = []
    for i in range(0, len(samples) - chunk_size, chunk_size):
        chunk = samples[i:i + chunk_size]
        e = sum(s * s for s in chunk) / len(chunk)
        energies.append(e)
    energy_var = (max(energies) - min(energies)) / max(max(energies), 1) if energies else 0

    # Onset sharpness (how fast energy rises)
    onset_ratio = 0
    if len(energies) >= 3:
        onset_ratio = energies[0] / max(sum(energies) / len(energies), 1e-10)

    # Classify based on features
    features = {
        "duration": round(duration, 2),
        "rms_db": round(rms_db, 1),
        "peak": round(peak, 3),
        "zcr": round(zcr, 4),
        "energy_variance": round(energy_var, 3),
        "onset_ratio": round(onset_ratio, 3),
    }

    # Classification rules
    if duration < 0.8 and onset_ratio > 2.0 and peak > 0.3:
        category, confidence = "gasp", 0.8
    elif duration < 0.6 and zcr < 0.05 and peak > 0.4:
        category, confidence = "skin_slap", 0.7
    elif duration < 1.0 and rms_db > -25 and onset_ratio > 1.5:
        category, confidence = "grunt", 0.6
    elif rms_db > -20 and energy_var > 0.5 and duration > 2:
        category, confidence = "moan_intense", 0.7
    elif rms_db > -20 and energy_var > 0.5 and duration > 1:
        category, confidence = "climax", 0.6
    elif rms_db > -30 and zcr > 0.1 and duration > 1.5:
        category, confidence = "panting", 0.7
    elif rms_db > -30 and duration > 1 and energy_var < 0.3:
        category, confidence = "moan_soft", 0.7
    elif rms_db > -30 and zcr < 0.08 and duration > 0.5:
        category, confidence = "whimper", 0.6
    elif duration > 2 and zcr > 0.05:
        category, confidence = "speech", 0.5
    elif rms_db > -35 and zcr > 0.15:
        category, confidence = "breathing", 0.6
    elif rms_db > -25 and zcr < 0.03:
        category, confidence = "wet_foley", 0.5
    else:
        category, confidence = "uncategorized", 0.3

    features["category"] = category
    features["confidence"] = confidence
    return features


def process_source(source_path: str, source_key: str, limit: int = 50) -> list[dict]:
    """Process a single source file: extract audio → split → classify → save."""
    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract audio
        full_wav = os.path.join(tmpdir, "full_audio.wav")
        log.info(f"  Extracting audio from {Path(source_path).name}...")
        if not extract_audio(source_path, full_wav):
            log.error(f"  Failed to extract audio")
            return results

        # Split on silence
        segments = split_on_silence(full_wav)
        log.info(f"  Found {len(segments)} segments")

        for i, seg in enumerate(segments[:limit]):
            seg_wav = os.path.join(tmpdir, f"seg_{i:04d}.wav")
            if not extract_segment(full_wav, seg["start"], seg["end"], seg_wav):
                continue

            # Analyze
            features = analyze_segment(seg_wav)
            category = features.get("category", "uncategorized")
            confidence = features.get("confidence", 0)

            if confidence < 0.4 or category == "unknown":
                continue

            # Save to categorized library
            cat_dir = CATEGORIZED_DIR / category
            cat_dir.mkdir(parents=True, exist_ok=True)

            seg_name = f"{source_key}_seg{i:04d}.wav"
            output_path = cat_dir / seg_name

            # Don't overwrite existing
            if output_path.exists():
                continue

            subprocess.run([
                "cp", seg_wav, str(output_path),
            ], timeout=10)

            results.append({
                "filename": seg_name,
                "category": category,
                "confidence": confidence,
                "duration": features["duration"],
                "rms_db": features["rms_db"],
                "source": Path(source_path).name,
                "source_key": source_key,
                "path": str(output_path),
            })

            log.info(f"    {seg_name}: {category} (conf={confidence:.1f}, {features['duration']:.1f}s)")

    return results


def process_url(url: str, source_key: str = None) -> list[dict]:
    """Download from URL and extract SFX."""
    if not source_key:
        source_key = f"url_{uuid.uuid4().hex[:8]}"

    with tempfile.TemporaryDirectory() as tmpdir:
        log.info(f"Downloading: {url[:80]}...")
        wav_path = download_url(url, tmpdir)
        if not wav_path:
            log.error("Download failed")
            return []
        return process_source(wav_path, source_key)


def process_local_candidates(max_files: int = 20, min_score: int = 80) -> list[dict]:
    """Process top candidates from the explicit video scan."""
    if not SCAN_FILE.exists():
        log.error(f"Scan file not found: {SCAN_FILE}")
        return []

    with open(SCAN_FILE) as f:
        scan = json.load(f)

    candidates = sorted(
        scan.get("candidates", []),
        key=lambda x: x.get("explicit_score", 0),
        reverse=True,
    )

    all_results = []
    processed = 0

    for cand in candidates:
        if processed >= max_files:
            break
        if cand.get("explicit_score", 0) < min_score:
            break

        source_path = cand["path"]
        if not Path(source_path).exists():
            continue

        source_key = Path(source_path).stem.lower().replace(" ", "_")[:30]

        # Skip if we already have segments from this source
        existing = list(CATEGORIZED_DIR.rglob(f"{source_key}_seg*.wav"))
        if existing:
            log.info(f"[SKIP] {source_key}: {len(existing)} segments already extracted")
            continue

        log.info(f"\n[{processed + 1}/{max_files}] Processing: {Path(source_path).name} (score={cand['explicit_score']})")
        results = process_source(source_path, source_key)
        all_results.extend(results)
        processed += 1

    return all_results


def rebuild_manifest():
    """Rebuild the SFX manifest after adding new clips."""
    # Import and run the same logic from the manifest rebuilder
    subprocess.run([
        sys.executable, "-c", """
import json, subprocess
from pathlib import Path

BASE = Path("/opt/anime-studio/output")
categories = {}
total = 0

for search_dir in [BASE / "sfx_test", BASE / "sfx_library/categorized", BASE / "sfx_library/foley"]:
    if not search_dir.exists(): continue
    for wav in search_dir.rglob("*.wav"):
        r = subprocess.run(["file", "-b", str(wav)], capture_output=True, text=True, timeout=5)
        if "image" in r.stdout.lower(): continue
        try:
            dr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
                capture_output=True, text=True, timeout=10)
            dur = round(float(dr.stdout.strip()), 2) if dr.stdout.strip() else 0
        except: dur = 0
        if dur < 0.1: continue

        rel = wav.relative_to(search_dir)
        parts = list(rel.parts)
        cat = parts[0] if len(parts) > 1 else "uncategorized"
        if len(parts) > 2: cat = parts[1]

        gender = "neutral"
        fn = wav.stem.lower()
        if fn.startswith("f_") or "_f_" in fn: gender = "female"
        elif fn.startswith("m_") or "_m_" in fn: gender = "male"

        categories.setdefault(cat, []).append({
            "name": wav.stem, "path": str(wav), "duration": dur, "gender": gender,
        })
        total += 1

manifest = {"categories": dict(sorted(categories.items())), "total_clips": total, "rebuilt": "auto"}
with open(str(BASE / "sfx_test/sfx_manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
print(f"Manifest rebuilt: {total} clips, {len(categories)} categories")
""",
    ], timeout=300)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract real SFX from explicit sources")
    parser.add_argument("--url", type=str, help="Download and extract from URL (yt-dlp)")
    parser.add_argument("--file", type=str, help="Extract from local file")
    parser.add_argument("--local-scan", action="store_true",
                        help="Process top candidates from explicit_video_scan.json")
    parser.add_argument("--max-files", type=int, default=20, help="Max files to process")
    parser.add_argument("--min-score", type=int, default=80, help="Min explicit score")
    parser.add_argument("--rebuild-only", action="store_true", help="Only rebuild manifest")
    args = parser.parse_args()

    if args.rebuild_only:
        rebuild_manifest()
        sys.exit(0)

    results = []

    if args.url:
        results = process_url(args.url)
    elif args.file:
        source_key = Path(args.file).stem.lower().replace(" ", "_")[:30]
        results = process_source(args.file, source_key)
    elif args.local_scan:
        results = process_local_candidates(
            max_files=args.max_files,
            min_score=args.min_score,
        )
    else:
        parser.print_help()
        sys.exit(1)

    if results:
        # Print summary
        from collections import Counter
        cats = Counter(r["category"] for r in results)
        log.info(f"\n{'=' * 50}")
        log.info(f"Extracted {len(results)} segments:")
        for cat, count in cats.most_common():
            log.info(f"  {cat}: {count}")

        # Rebuild manifest
        log.info("\nRebuilding SFX manifest...")
        rebuild_manifest()
    else:
        log.info("No segments extracted")
