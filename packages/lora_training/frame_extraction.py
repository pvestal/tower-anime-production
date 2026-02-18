"""Smart frame extraction — scene-change detection + uniform sampling + dedup.

Ported from archived/dataset_approval_api.py.archived (lines 2613-2724).
Replaces flat fps extraction with a 3-phase strategy that produces more
diverse, higher-quality training frames.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from packages.visual_pipeline.vision import perceptual_hash

logger = logging.getLogger(__name__)


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds via ffprobe. Returns 0 on failure."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(probe.stdout.strip()) if probe.stdout.strip() else 0
    except Exception as e:
        logger.warning(f"ffprobe failed for {video_path}: {e}")
        return 0


def extract_smart_frames(video_path: Path, max_frames: int, tmpdir: str) -> list[Path]:
    """Extract diverse frames using scene detection + uniform sampling + dedup.

    Strategy:
    1. Scene-change detection (threshold 0.3) to find visually distinct moments
    2. Uniform temporal sampling to fill gaps across the full video
    3. Perceptual-hash dedup to eliminate near-identical frames
    4. Even-spaced trim to max_frames

    Falls back to flat 0.5fps if duration is unknown.

    Args:
        video_path: Path to the video file.
        max_frames: Maximum number of frames to return.
        tmpdir: Working directory for intermediate files.

    Returns: List of paths to extracted PNG frames.
    """
    duration = get_video_duration(video_path)

    frames_dir = Path(tmpdir) / "frames"
    frames_dir.mkdir(exist_ok=True)

    # Fallback to flat fps extraction if we can't determine duration
    if duration <= 0:
        logger.warning("Duration unknown, falling back to flat 0.5fps extraction")
        return _flat_extract(video_path, max_frames, frames_dir)

    logger.info(f"Video duration: {duration:.1f}s, target: {max_frames} frames")

    # --- Phase 1: Scene-change detection ---
    scene_dir = Path(tmpdir) / "scene_frames"
    scene_dir.mkdir(exist_ok=True)
    scene_pattern = str(scene_dir / "scene_%04d.png")
    scene_limit = max_frames * 3

    subprocess.run(
        ["ffmpeg", "-i", str(video_path),
         "-vf", "select='gt(scene,0.3)',scale=768:-1",
         "-vsync", "vfr", "-q:v", "1",
         "-frames:v", str(scene_limit),
         scene_pattern, "-y"],
        capture_output=True, timeout=300,
    )
    scene_frames = sorted(scene_dir.glob("scene_*.png"))
    logger.info(f"Scene detection found {len(scene_frames)} distinct scenes")

    # --- Phase 2: Uniform temporal sampling ---
    uniform_dir = Path(tmpdir) / "uniform_frames"
    uniform_dir.mkdir(exist_ok=True)
    uniform_pattern = str(uniform_dir / "uniform_%04d.png")

    uniform_count = max_frames * 2
    interval = duration / uniform_count if uniform_count > 0 else 1.0
    uniform_fps = 1.0 / max(interval, 0.1)

    subprocess.run(
        ["ffmpeg", "-i", str(video_path),
         "-vf", f"fps={uniform_fps:.4f},scale=768:-1",
         "-q:v", "1", "-frames:v", str(uniform_count),
         uniform_pattern, "-y"],
        capture_output=True, timeout=300,
    )
    uniform_frames = sorted(uniform_dir.glob("uniform_*.png"))
    logger.info(f"Uniform sampling extracted {len(uniform_frames)} frames across {duration:.0f}s")

    # --- Phase 3: Merge + perceptual hash dedup ---
    # Scene frames get priority (they're at actual content changes)
    all_candidates = [(f, "scene") for f in scene_frames] + [(f, "uniform") for f in uniform_frames]

    if not all_candidates:
        logger.warning("No frames extracted at all")
        return []

    seen_hashes: set[str] = set()
    unique_frames: list[Path] = []

    for frame_path, source in all_candidates:
        phash = perceptual_hash(frame_path)
        if phash in seen_hashes:
            continue
        seen_hashes.add(phash)
        dest = frames_dir / f"frame_{len(unique_frames) + 1:04d}.png"
        shutil.copy2(frame_path, dest)
        unique_frames.append(dest)

    logger.info(f"After dedup: {len(unique_frames)} unique from {len(all_candidates)} candidates")

    # Trim to max_frames — take evenly spaced subset if we have too many
    if len(unique_frames) > max_frames:
        step = len(unique_frames) / max_frames
        selected = [unique_frames[int(i * step)] for i in range(max_frames)]
        for f in unique_frames:
            if f not in selected:
                f.unlink(missing_ok=True)
        unique_frames = selected

    logger.info(f"Final: {len(unique_frames)} frames for classification")
    return unique_frames


def _flat_extract(video_path: Path, max_frames: int, frames_dir: Path) -> list[Path]:
    """Fallback: flat 0.5fps extraction when duration is unknown."""
    pattern = str(frames_dir / "frame_%04d.png")
    subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vf", "fps=0.5,scale=768:-1",
         "-q:v", "1", "-frames:v", str(max_frames),
         pattern, "-y"],
        capture_output=True, timeout=300,
    )
    return sorted(frames_dir.glob("frame_*.png"))


def download_video(url: str, tmpdir: str) -> Path:
    """Download a video from URL using yt-dlp. Returns path to downloaded file.

    Uses --js-runtimes node and --remote-components for YouTube compatibility.
    """
    tmp_video = Path(tmpdir) / "video.mp4"

    result = subprocess.run(
        ["yt-dlp", "--js-runtimes", "node", "--remote-components", "ejs:github",
         "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
         "--merge-output-format", "mp4", "-o", str(tmp_video), url],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:500]}")

    return tmp_video
