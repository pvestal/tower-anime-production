"""Trailer assembler — quick-cut assembly of trailer shots into a single video.

Uses the same ffmpeg xfade pipeline as episode_assembly but with:
  - Faster transitions (0.15s dissolve for quick-cut feel)
  - Optional title card fade-in
  - Outputs to /opt/anime-studio/output/trailers/
"""

import asyncio
import logging
import uuid
from pathlib import Path

from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

TRAILER_OUTPUT_DIR = Path("/opt/anime-studio/output/trailers")
TRAILER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Quick-cut transitions for trailer energy
TRAILER_TRANSITION = "dissolve"
TRAILER_TRANSITION_DURATION = 0.15


async def _probe_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except (ValueError, AttributeError):
        return 5.0


async def assemble_trailer(trailer_id: str) -> dict:
    """Assemble a trailer from its completed shots.

    Gathers all completed shot videos in order, stitches them with
    quick-cut dissolve transitions, and updates the trailer record.

    Returns dict with video_path, duration, shots_included.
    """
    conn = await connect_direct()
    try:
        trailer = await conn.fetchrow(
            "SELECT * FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )
        if not trailer:
            raise ValueError(f"Trailer {trailer_id} not found")

        # Get completed shots with video
        shots = await conn.fetch("""
            SELECT id, shot_number, output_video_path, trailer_role
            FROM shots
            WHERE scene_id = $1
              AND status = 'completed'
              AND output_video_path IS NOT NULL
            ORDER BY shot_number
        """, trailer["scene_id"])

        video_paths = []
        for s in shots:
            vp = s["output_video_path"]
            if vp and Path(vp).exists():
                video_paths.append(vp)

        if not video_paths:
            raise ValueError("No completed shots with video found for trailer")

        output_path = str(
            TRAILER_OUTPUT_DIR / f"trailer_{trailer['project_id']}_v{trailer['version']}.mp4"
        )

        if len(video_paths) == 1:
            import shutil
            shutil.copy2(video_paths[0], output_path)
        else:
            await _xfade_assemble(video_paths, output_path)

        # Get final duration
        duration = await _probe_duration(output_path)

        # Update trailer record
        await conn.execute("""
            UPDATE trailers
            SET status = 'assembled', final_video_path = $2,
                actual_duration_seconds = $3, updated_at = NOW()
            WHERE id = $1
        """, uuid.UUID(trailer_id), output_path, duration)

        logger.info(
            f"Trailer assembled: {output_path} "
            f"({len(video_paths)} shots, {duration:.1f}s)"
        )

        return {
            "trailer_id": trailer_id,
            "video_path": output_path,
            "duration_seconds": duration,
            "shots_included": len(video_paths),
            "total_shots": len(shots),
        }

    finally:
        await conn.close()


async def _xfade_assemble(video_paths: list[str], output_path: str):
    """Assemble videos with quick dissolve transitions via ffmpeg xfade."""
    n = len(video_paths)

    # Probe durations
    durations = []
    for vp in video_paths:
        durations.append(await _probe_duration(vp))

    # Build ffmpeg inputs
    inputs = []
    for vp in video_paths:
        inputs.extend(["-i", vp])

    # Build xfade filter chain
    video_filter_parts = []
    cumulative_duration = durations[0]

    for i in range(n - 1):
        xfade_dur = min(
            TRAILER_TRANSITION_DURATION,
            durations[i] * 0.3,
            durations[i + 1] * 0.3,
        )
        offset = cumulative_duration - xfade_dur

        src_label = "[0:v]" if i == 0 else f"[v{i}]"
        dst_label = f"[{i + 1}:v]"
        out_label = "[vout]" if i == n - 2 else f"[v{i + 1}]"

        video_filter_parts.append(
            f"{src_label}{dst_label}xfade=transition={TRAILER_TRANSITION}:"
            f"duration={xfade_dur:.3f}:offset={offset:.3f}{out_label}"
        )
        cumulative_duration = offset + durations[i + 1]

    filter_complex = ";".join(video_filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-an",  # No audio for now — can be added in post
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        # Fallback: hard-cut concat
        logger.warning(f"Trailer xfade failed, falling back to hard-cut: {stderr.decode()[-200:]}")
        list_path = output_path.rsplit(".", 1)[0] + "_concat.txt"
        with open(list_path, "w") as f:
            for vp in video_paths:
                f.write(f"file '{vp}'\n")
        proc2 = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_path, "-c", "copy", output_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc2.communicate()
        Path(list_path).unlink(missing_ok=True)
