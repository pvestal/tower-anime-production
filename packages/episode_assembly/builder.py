"""Episode assembly — concatenate scene videos into full episodes."""

import asyncio
import logging
import os
from pathlib import Path

from packages.core.config import BASE_PATH

logger = logging.getLogger(__name__)

EPISODE_OUTPUT_DIR = BASE_PATH.parent / "output" / "episodes"
EPISODE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def assemble_episode(
    episode_id: str,
    scene_video_paths: list[str],
    transitions: list[str] | None = None,
) -> str:
    """Concatenate scene videos into an episode MP4.

    Args:
        episode_id: UUID of the episode
        scene_video_paths: Ordered list of scene video file paths
        transitions: Per-scene transition type (currently only "cut" supported;
                     "crossfade" is a placeholder for future ffmpeg xfade filter)

    Returns:
        Path to assembled episode video
    """
    output_path = str(EPISODE_OUTPUT_DIR / f"episode_{episode_id}.mp4")

    if len(scene_video_paths) == 1:
        # Single scene — just copy
        import shutil
        shutil.copy2(scene_video_paths[0], output_path)
        return output_path

    # ffmpeg concat demuxer — works for scenes with matching codecs
    list_path = output_path.rsplit(".", 1)[0] + "_concat.txt"
    with open(list_path, "w") as f:
        for vp in scene_video_paths:
            f.write(f"file '{vp}'\n")

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    os.unlink(list_path)

    if proc.returncode != 0:
        raise RuntimeError(f"Episode assembly failed: {stderr.decode()[-300:]}")

    logger.info(f"Episode {episode_id} assembled: {output_path} from {len(scene_video_paths)} scenes")
    return output_path


async def get_video_duration(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    try:
        return float(stdout.decode().strip())
    except (ValueError, AttributeError):
        return None


async def extract_thumbnail(video_path: str, output_path: str) -> str | None:
    """Extract first frame as thumbnail."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", video_path,
        "-vframes", "1", "-q:v", "2", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode == 0 and Path(output_path).exists():
        return output_path
    return None
