#!/usr/bin/env python3
"""
Tower Anime — FramePack Output Validator
Checks that generated frames are actual content, not garbage.

Run on Tower after a generation:
    python3 validate_framepack_output.py /path/to/comfyui/output/

What this checks:
    1. Files exist and are valid images (not corrupt/truncated)
    2. Frames aren't solid black/white/single-color (failed decode)
    3. Frames have meaningful variance (not noise/static)
    4. Frames have temporal coherence (consecutive frames relate to each other)
    5. Resolution matches what was requested
    6. Visual entropy is in a reasonable range for anime content
"""

import sys
import os
import glob
import json
import hashlib
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("❌ Need: pip install numpy Pillow")
    sys.exit(1)


# ─── Thresholds ───────────────────────────────────────────────
# These are calibrated for anime-style video frames
MIN_STD_DEV = 15.0         # Below this = likely solid color or near-blank
MAX_STD_DEV = 100.0        # Above this = likely pure noise/static
MIN_UNIQUE_COLORS = 500    # Below this = degenerate output
MAX_DUPLICATE_RATIO = 0.5  # If >50% frames are identical = frozen/broken
MIN_FRAME_SIMILARITY = 0.3 # Consecutive frames should share some content
MAX_FRAME_SIMILARITY = 0.999  # But not be literally identical


def load_image(path: str) -> np.ndarray | None:
    """Load image, return as numpy array or None if corrupt."""
    try:
        img = Image.open(path)
        img.verify()  # Check for corruption
        img = Image.open(path)  # Re-open after verify
        return np.array(img.convert("RGB"))
    except Exception as e:
        print(f"  ❌ CORRUPT: {path} — {e}")
        return None


def check_solid_color(frame: np.ndarray) -> dict:
    """Check if frame is effectively a solid color."""
    std = frame.std()
    mean = frame.mean()
    unique = len(np.unique(frame.reshape(-1, 3), axis=0))
    return {
        "std_dev": float(std),
        "mean_value": float(mean),
        "unique_colors": int(unique),
        "is_black": mean < 5 and std < 2,
        "is_white": mean > 250 and std < 2,
        "is_solid": std < MIN_STD_DEV,
        "is_noise": std > MAX_STD_DEV,
    }


def frame_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compare two frames using normalized cross-correlation.
    Returns 0.0 (completely different) to 1.0 (identical).
    """
    if a.shape != b.shape:
        return 0.0
    a_f = a.astype(np.float32).flatten()
    b_f = b.astype(np.float32).flatten()
    a_norm = a_f - a_f.mean()
    b_norm = b_f - b_f.mean()
    denom = (np.linalg.norm(a_norm) * np.linalg.norm(b_norm))
    if denom < 1e-10:
        return 1.0 if np.allclose(a_f, b_f) else 0.0
    return float(np.dot(a_norm, b_norm) / denom)


def frame_hash(frame: np.ndarray) -> str:
    """Quick hash of downsampled frame for duplicate detection."""
    small = Image.fromarray(frame).resize((32, 32), Image.BILINEAR)
    return hashlib.md5(np.array(small).tobytes()).hexdigest()


def check_visual_entropy(frame: np.ndarray) -> float:
    """
    Estimate visual entropy using histogram analysis.
    Real anime frames: ~5-7 bits. Noise: ~8 bits. Solid: ~0 bits.
    """
    gray = np.mean(frame, axis=2).astype(np.uint8)
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    hist = hist[hist > 0].astype(np.float64)
    hist /= hist.sum()
    return float(-np.sum(hist * np.log2(hist)))


def validate_output_dir(output_dir: str, expected_width: int = 0, expected_height: int = 0):
    """Run full validation on a directory of output frames."""

    print(f"\n{'═' * 60}")
    print(f"  FramePack Output Validator")
    print(f"  Directory: {output_dir}")
    print(f"{'═' * 60}\n")

    # ─── Find frames ───
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    files = []
    for pat in patterns:
        files.extend(sorted(glob.glob(os.path.join(output_dir, pat))))
        files.extend(sorted(glob.glob(os.path.join(output_dir, "**", pat), recursive=True)))

    # Filter to likely FramePack output (by prefix)
    framepack_files = [f for f in files if "framepack" in os.path.basename(f).lower()
                       or "tower_anime" in os.path.basename(f).lower()
                       or "test_" in os.path.basename(f).lower()]

    if not framepack_files:
        # Fall back to most recent files
        framepack_files = sorted(files, key=os.path.getmtime, reverse=True)[:100]

    if not framepack_files:
        print("❌ NO OUTPUT FILES FOUND")
        print(f"   Checked: {output_dir}")
        print(f"   This likely means:")
        print(f"   • SaveImage node didn't execute (workflow error)")
        print(f"   • Output directory is wrong")
        print(f"   • ComfyUI saved elsewhere")
        print(f"\n   Check: curl -s http://localhost:8188/history | python3 -m json.tool | tail -50")
        return False

    files = framepack_files
    print(f"📁 Found {len(files)} output files\n")

    # ─── Load and check each frame ───
    frames = []
    hashes = []
    issues = []
    valid_count = 0

    for i, fpath in enumerate(files):
        fname = os.path.basename(fpath)
        frame = load_image(fpath)

        if frame is None:
            issues.append(f"CORRUPT: {fname}")
            continue

        # Resolution check
        h, w = frame.shape[:2]
        if i == 0:
            print(f"📐 Resolution: {w}x{h}")
            if expected_width and w != expected_width:
                issues.append(f"WIDTH MISMATCH: got {w}, expected {expected_width}")
            if expected_height and h != expected_height:
                issues.append(f"HEIGHT MISMATCH: got {h}, expected {expected_height}")

        # Color/content check
        color_info = check_solid_color(frame)

        if color_info["is_black"]:
            issues.append(f"BLACK FRAME: {fname} (mean={color_info['mean_value']:.1f})")
        elif color_info["is_white"]:
            issues.append(f"WHITE FRAME: {fname} (mean={color_info['mean_value']:.1f})")
        elif color_info["is_solid"]:
            issues.append(f"SOLID COLOR: {fname} (std={color_info['std_dev']:.1f})")
        elif color_info["is_noise"]:
            issues.append(f"POSSIBLE NOISE: {fname} (std={color_info['std_dev']:.1f})")
        elif color_info["unique_colors"] < MIN_UNIQUE_COLORS:
            issues.append(f"LOW COMPLEXITY: {fname} (only {color_info['unique_colors']} unique colors)")
        else:
            valid_count += 1

        # Entropy check
        entropy = check_visual_entropy(frame)
        if entropy < 2.0:
            issues.append(f"LOW ENTROPY: {fname} ({entropy:.2f} bits — likely degenerate)")
        elif entropy > 7.8:
            issues.append(f"HIGH ENTROPY: {fname} ({entropy:.2f} bits — likely noise)")

        # Track for duplicate/similarity detection
        fhash = frame_hash(frame)
        hashes.append(fhash)
        frames.append(frame)

        # Print per-frame summary for first few and last few
        if i < 3 or i >= len(files) - 2:
            status = "✅" if not any(fname in iss for iss in issues) else "⚠️"
            print(f"  {status} {fname}: std={color_info['std_dev']:.1f}, "
                  f"colors={color_info['unique_colors']}, entropy={entropy:.2f}")
        elif i == 3:
            print(f"  ... ({len(files) - 4} more frames) ...")

    # ─── Duplicate detection ───
    unique_hashes = set(hashes)
    dup_ratio = 1.0 - (len(unique_hashes) / max(len(hashes), 1))
    if dup_ratio > MAX_DUPLICATE_RATIO:
        issues.append(f"HIGH DUPLICATION: {dup_ratio*100:.0f}% of frames are duplicates (frozen output?)")

    # ─── Temporal coherence ───
    if len(frames) >= 2:
        similarities = []
        for i in range(len(frames) - 1):
            sim = frame_similarity(frames[i], frames[i + 1])
            similarities.append(sim)

        avg_sim = np.mean(similarities)
        min_sim = np.min(similarities)
        max_sim = np.max(similarities)

        print(f"\n📊 Temporal Coherence:")
        print(f"   Consecutive frame similarity: avg={avg_sim:.3f}, min={min_sim:.3f}, max={max_sim:.3f}")

        if avg_sim > MAX_FRAME_SIMILARITY:
            issues.append(f"FROZEN VIDEO: avg similarity {avg_sim:.3f} — frames barely change")
        elif avg_sim < MIN_FRAME_SIMILARITY:
            issues.append(f"NO COHERENCE: avg similarity {avg_sim:.3f} — frames unrelated (random noise?)")
        else:
            print(f"   ✅ Looks like real video (frames change but stay coherent)")

    # ─── Summary ───
    print(f"\n{'─' * 60}")
    print(f"  VALIDATION SUMMARY")
    print(f"{'─' * 60}")
    print(f"  Total frames:  {len(files)}")
    print(f"  Valid frames:  {valid_count}")
    print(f"  Unique frames: {len(unique_hashes)}")
    print(f"  Duplicate ratio: {dup_ratio*100:.0f}%")

    if issues:
        print(f"\n  ⚠️  {len(issues)} ISSUE(S) FOUND:")
        for iss in issues:
            print(f"     • {iss}")
    else:
        print(f"\n  ✅ ALL CHECKS PASSED — output looks like real anime frames")

    # ─── Verdict ───
    critical = [i for i in issues if any(k in i for k in ["BLACK", "WHITE", "CORRUPT", "FROZEN", "NO COHERENCE", "NOISE"])]
    if critical:
        print(f"\n  ❌ VERDICT: OUTPUT IS LIKELY GARBAGE")
        print(f"     {len(critical)} critical issue(s) detected")
        print(f"     The workflow ran but didn't produce real content.")
        print(f"\n  Debug steps:")
        print(f"     1. Check ComfyUI console for warnings during generation")
        print(f"     2. Try the workflow manually in ComfyUI's web UI")
        print(f"     3. Verify model loaded correctly (check VRAM usage)")
        print(f"     4. Ensure FramePackSampler actually ran (check step count in logs)")
        return False
    elif issues:
        print(f"\n  ⚠️  VERDICT: OUTPUT HAS MINOR ISSUES — review manually")
        return True
    else:
        print(f"\n  ✅ VERDICT: OUTPUT LOOKS GOOD")
        return True


def check_comfyui_history():
    """Pull the last few jobs from ComfyUI history and check their status."""
    try:
        import requests
        resp = requests.get("http://localhost:8188/history", timeout=5)
        history = resp.json()

        print(f"\n{'═' * 60}")
        print(f"  ComfyUI Job History (last 5)")
        print(f"{'═' * 60}\n")

        for pid, job in list(history.items())[-5:]:
            status = job.get("status", {})
            completed = status.get("completed", False)
            outputs = job.get("outputs", {})

            output_files = []
            for nid, out in outputs.items():
                for key in ["images", "gifs", "videos"]:
                    for item in out.get(key, []):
                        output_files.append(item.get("filename", "unknown"))

            status_icon = "✅" if completed else "❌"
            print(f"  {status_icon} {pid[:12]}...")
            print(f"     Completed: {completed}")
            print(f"     Outputs: {output_files if output_files else 'NONE'}")

            if not output_files:
                print(f"     ⚠️  No output files — generation may have failed silently")
            print()

    except Exception as e:
        print(f"  ⚠️ Can't reach ComfyUI: {e}")
        print(f"     Run this on Tower where ComfyUI is accessible")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 validate_framepack_output.py /path/to/output/dir")
        print("  python3 validate_framepack_output.py --history  # Check ComfyUI job history")
        print()
        print("Common output locations:")
        print("  /mnt/1TB-storage/ComfyUI/output/")
        print("  ~/ComfyUI/output/")
        print()

        # Try to auto-detect
        common_paths = [
            "/mnt/1TB-storage/ComfyUI/output",
            os.path.expanduser("~/ComfyUI/output"),
            "/opt/ComfyUI/output",
        ]
        for p in common_paths:
            if os.path.isdir(p):
                print(f"Found output dir: {p}")
                validate_output_dir(p)
                break
        else:
            print("No output directory auto-detected. Checking ComfyUI history...")
            check_comfyui_history()
        sys.exit(0)

    if sys.argv[1] == "--history":
        check_comfyui_history()
    else:
        ok = validate_output_dir(sys.argv[1])
        sys.exit(0 if ok else 1)