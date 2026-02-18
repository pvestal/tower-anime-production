"""Scene builder helper functions — ffmpeg utilities, ComfyUI polling, generation orchestrator."""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

import httpx

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR
from packages.core.db import connect_direct
from packages.core.audit import log_decision

from .framepack import build_framepack_workflow, _submit_comfyui_workflow

logger = logging.getLogger(__name__)

# Scene output directory
SCENE_OUTPUT_DIR = BASE_PATH.parent / "output" / "scenes"
SCENE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Audio cache directory
AUDIO_CACHE_DIR = SCENE_OUTPUT_DIR / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Track active scene generation tasks
_scene_generation_tasks: dict[str, asyncio.Task] = {}

# Quality gate threshold for shots
_SHOT_QUALITY_THRESHOLD = 0.4


async def _quality_gate_check(frame_path: str) -> float | None:
    """Quick quality check on a video frame using the vision model.

    Returns quality score (0-1) or None if check fails/unavailable.
    Uses a lightweight prompt to avoid long Ollama inference.
    """
    import urllib.request
    import base64
    from packages.core.config import OLLAMA_URL, VISION_MODEL

    try:
        with open(frame_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        payload = json.dumps({
            "model": VISION_MODEL,
            "prompt": (
                "Rate this anime frame 1-10 on visual quality (sharpness, "
                "no artifacts, coherent anatomy). Reply with ONLY a number."
            ),
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        text = result.get("response", "").strip()

        # Extract numeric score
        for token in text.split():
            try:
                score = float(token.replace("/10", "").replace("/", ""))
                if 1 <= score <= 10:
                    return round(score / 10, 2)
            except ValueError:
                continue

        return None  # Couldn't parse score

    except Exception as e:
        logger.debug(f"Quality gate check failed for {frame_path}: {e}")
        return None  # Non-blocking: if check fails, pass the gate


async def extract_last_frame(video_path: str) -> str:
    """Extract the last frame from a video using ffmpeg."""
    output_path = video_path.rsplit(".", 1)[0] + "_lastframe.png"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
        "-vframes", "1", "-q:v", "2", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg last-frame extraction failed: {stderr.decode()[-200:]}")
    return output_path


async def concat_videos(video_paths: list, output_path: str) -> str:
    """Concatenate videos using ffmpeg concat demuxer."""
    list_path = output_path.rsplit(".", 1)[0] + "_concat.txt"
    with open(list_path, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    os.unlink(list_path)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {stderr.decode()[-200:]}")
    return output_path


async def download_preview(url: str, scene_id: str) -> str:
    """Download a 30-sec Apple Music preview to the audio cache. Returns local path."""
    cache_path = AUDIO_CACHE_DIR / f"preview_{scene_id}.m4a"
    if cache_path.exists():
        return str(cache_path)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
        logger.info(f"Downloaded audio preview to {cache_path} ({len(resp.content)} bytes)")
        return str(cache_path)
    except Exception as e:
        logger.error(f"Failed to download audio preview: {e}")
        raise


async def overlay_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    fade_in: float = 1.0,
    fade_out: float = 2.0,
    start_offset: float = 0,
) -> str:
    """Overlay audio onto video using ffmpeg. Copies video stream, encodes audio as AAC.

    - fade_in / fade_out: seconds for audio fade
    - start_offset: skip N seconds into the audio before overlaying
    - Uses -shortest so output matches shorter of video/audio
    """
    # Build afade filter chain
    filters = []
    if start_offset > 0:
        filters.append(f"atrim=start={start_offset}")
        filters.append("asetpts=PTS-STARTPTS")
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    # We need video duration for fade-out positioning — probe it
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    video_duration = float(stdout.decode().strip()) if stdout.decode().strip() else 30.0
    if fade_out > 0:
        fade_out_start = max(0, video_duration - fade_out)
        filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")

    filter_str = ",".join(filters) if filters else "anull"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", f"[1:a]{filter_str}[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio overlay failed: {stderr.decode()[-300:]}")

    logger.info(f"Audio overlay complete: {output_path}")
    return output_path


async def mix_scene_audio(
    video_path: str,
    output_path: str,
    dialogue_path: str | None = None,
    music_path: str | None = None,
    music_fade_in: float = 1.0,
    music_fade_out: float = 2.0,
    music_start_offset: float = 0,
    music_volume: float = 0.3,
) -> str:
    """Mix dialogue and/or music into a video. Single-pass ffmpeg when both exist."""
    if not dialogue_path and not music_path:
        return video_path

    if dialogue_path and music_path:
        # Both: 3-input ffmpeg with amix
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await probe.communicate()
        video_duration = float(stdout.decode().strip()) if stdout.decode().strip() else 30.0

        music_filters = []
        if music_start_offset > 0:
            music_filters.append(f"atrim=start={music_start_offset}")
            music_filters.append("asetpts=PTS-STARTPTS")
        music_filters.append(f"volume={music_volume}")
        if music_fade_in > 0:
            music_filters.append(f"afade=t=in:st=0:d={music_fade_in}")
        if music_fade_out > 0:
            fade_out_start = max(0, video_duration - music_fade_out)
            music_filters.append(f"afade=t=out:st={fade_out_start}:d={music_fade_out}")

        music_chain = ",".join(music_filters)
        filter_complex = f"[2:a]{music_chain}[music];[1:a][music]amix=inputs=2:duration=shortest[a]"

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dialogue_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_path,
        ]
    elif dialogue_path:
        # Dialogue only
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path, "-i", dialogue_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_path,
        ]
    else:
        # Music only — delegate to existing overlay_audio
        return await overlay_audio(
            video_path=video_path, audio_path=music_path,
            output_path=output_path, fade_in=music_fade_in,
            fade_out=music_fade_out, start_offset=music_start_offset,
        )

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mix failed: {stderr.decode()[-300:]}")
    logger.info(f"Audio mix complete: {output_path}")
    return output_path


async def build_scene_dialogue(conn, scene_id) -> str | None:
    """Build combined dialogue WAV for a scene from per-shot dialogue fields."""
    shots = await conn.fetch(
        "SELECT dialogue_text, dialogue_character_slug, shot_number "
        "FROM shots WHERE scene_id = $1 AND dialogue_text IS NOT NULL "
        "AND dialogue_text != '' ORDER BY shot_number",
        scene_id,
    )
    if not shots:
        return None

    dialogue_list = [
        {"character_slug": sh["dialogue_character_slug"] or "", "text": sh["dialogue_text"]}
        for sh in shots
    ]

    try:
        from packages.voice_pipeline.synthesis import synthesize_scene_dialogue
        result = await synthesize_scene_dialogue(
            scene_id=str(scene_id),
            dialogue_list=dialogue_list,
            pause_seconds=0.5,
        )
        combined_path = result.get("combined_path")
        if combined_path:
            await conn.execute(
                "UPDATE scenes SET dialogue_audio_path = $2 WHERE id = $1",
                scene_id, combined_path,
            )
        return combined_path
    except Exception as e:
        logger.warning(f"Scene dialogue synthesis failed (non-fatal): {e}")
        return None


async def apply_scene_audio(conn, scene_id, scene_video_path: str) -> str:
    """Build dialogue + download music + mix all audio into the scene video.

    Non-fatal: logs warnings on failure, never blocks generation.
    Returns the (possibly updated) video path.
    """
    try:
        # Build dialogue audio from shot fields
        dialogue_path = await build_scene_dialogue(conn, scene_id)

        # Download music preview if assigned
        music_path = None
        scene_row = await conn.fetchrow(
            "SELECT audio_preview_url, audio_fade_in, audio_fade_out, audio_start_offset "
            "FROM scenes WHERE id = $1", scene_id,
        )
        if scene_row and scene_row["audio_preview_url"]:
            try:
                music_path = await download_preview(scene_row["audio_preview_url"], str(scene_id))
            except Exception as dl_err:
                logger.warning(f"Music download failed (non-fatal): {dl_err}")

        if not dialogue_path and not music_path:
            return scene_video_path

        output = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}_audio.mp4")
        await mix_scene_audio(
            video_path=scene_video_path,
            output_path=output,
            dialogue_path=dialogue_path,
            music_path=music_path,
            music_fade_in=scene_row["audio_fade_in"] or 1.0 if scene_row else 1.0,
            music_fade_out=scene_row["audio_fade_out"] or 2.0 if scene_row else 2.0,
            music_start_offset=scene_row["audio_start_offset"] or 0 if scene_row else 0,
        )
        os.replace(output, scene_video_path)

        if music_path:
            await conn.execute(
                "UPDATE scenes SET audio_preview_path = $2 WHERE id = $1",
                scene_id, music_path,
            )
        logger.info(f"Scene {scene_id}: audio applied (dialogue={'yes' if dialogue_path else 'no'}, music={'yes' if music_path else 'no'})")
    except Exception as e:
        logger.warning(f"apply_scene_audio failed (non-fatal): {e}")

    return scene_video_path


async def copy_to_comfyui_input(image_path: str) -> str:
    """Copy source image to ComfyUI input dir, return the filename."""
    src = Path(image_path)
    if not src.is_absolute():
        src = BASE_PATH / image_path
    dest = COMFYUI_INPUT_DIR / src.name
    if not dest.exists():
        shutil.copy2(str(src), str(dest))
    return src.name


async def poll_comfyui_completion(prompt_id: str, timeout_seconds: int = 1800) -> dict:
    """Poll ComfyUI /history until the prompt completes or times out."""
    import urllib.request
    import time as _time
    start = _time.time()
    while (_time.time() - start) < timeout_seconds:
        try:
            req = urllib.request.Request(f"{COMFYUI_URL}/history/{prompt_id}")
            resp = urllib.request.urlopen(req, timeout=10)
            history = json.loads(resp.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                videos = []
                for node_output in outputs.values():
                    for key in ("videos", "gifs", "images"):
                        for item in node_output.get(key, []):
                            fn = item.get("filename")
                            if fn:
                                videos.append(fn)
                return {"status": "completed", "output_files": videos}
        except Exception:
            pass
        await asyncio.sleep(5)
    return {"status": "timeout", "output_files": []}


async def generate_scene(scene_id: str):
    """Background task: generate all shots sequentially with continuity chaining."""
    import time as _time
    conn = None
    try:
        conn = await connect_direct()

        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
            scene_id,
        )
        if not shots:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed' WHERE id = $1", scene_id
            )
            return

        await conn.execute(
            "UPDATE scenes SET generation_status = 'generating', total_shots = $2 WHERE id = $1",
            scene_id, len(shots),
        )

        completed_videos = []
        completed_count = 0
        prev_last_frame = None

        for shot in shots:
            shot_id = shot["id"]
            shot_start = _time.time()

            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )
            await conn.execute(
                "UPDATE scenes SET current_generating_shot_id = $2 WHERE id = $1",
                scene_id, shot_id,
            )

            try:
                # Determine first frame: previous shot's last frame or source image
                if prev_last_frame and Path(prev_last_frame).exists():
                    first_frame_path = prev_last_frame
                    image_filename = await copy_to_comfyui_input(first_frame_path)
                else:
                    source_path = shot["source_image_path"]
                    image_filename = await copy_to_comfyui_input(source_path)
                    first_frame_path = str(BASE_PATH / source_path) if not Path(source_path).is_absolute() else source_path

                # Build prompt from motion_prompt (or generation_prompt fallback)
                prompt_text = shot["motion_prompt"] or shot["generation_prompt"] or ""
                shot_steps = shot["steps"] or 25
                shot_seconds = float(shot["duration_seconds"] or 3)
                shot_use_f1 = shot["use_f1"] if shot["use_f1"] is not None else False
                shot_seed = shot["seed"]

                workflow_data, sampler_node_id, prefix = build_framepack_workflow(
                    prompt_text=prompt_text,
                    image_path=image_filename,
                    total_seconds=shot_seconds,
                    steps=shot_steps,
                    use_f1=shot_use_f1,
                    seed=shot_seed,
                    gpu_memory_preservation=6.0,
                )

                comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

                await conn.execute(
                    "UPDATE shots SET comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
                    shot_id, comfyui_prompt_id, first_frame_path,
                )

                # Poll for completion
                result = await poll_comfyui_completion(comfyui_prompt_id)

                if result["status"] == "completed" and result["output_files"]:
                    video_filename = result["output_files"][0]
                    video_path = str(COMFYUI_OUTPUT_DIR / video_filename)

                    # Extract last frame for chaining
                    last_frame = await extract_last_frame(video_path)
                    prev_last_frame = last_frame

                    gen_time = _time.time() - shot_start

                    # Quality gate: check last frame quality before accepting
                    shot_quality = await _quality_gate_check(last_frame)
                    quality_passed = shot_quality is None or shot_quality >= 0.4

                    if quality_passed:
                        completed_count += 1
                        completed_videos.append(video_path)
                        shot_status = "completed"
                    else:
                        shot_status = "quality_failed"
                        logger.warning(
                            f"Shot {shot_id} failed quality gate "
                            f"(score={shot_quality:.2f}), skipping"
                        )
                        await log_decision(
                            decision_type="shot_quality_gate",
                            input_context={
                                "shot_id": str(shot_id),
                                "scene_id": scene_id,
                                "quality_score": shot_quality,
                                "video": video_filename,
                            },
                            decision_made="rejected",
                            confidence_score=round(1.0 - shot_quality, 2),
                            reasoning=f"Shot quality {shot_quality:.0%} below 40% gate",
                        )

                    await conn.execute("""
                        UPDATE shots SET status = $2, output_video_path = $3,
                               last_frame_path = $4, generation_time_seconds = $5,
                               quality_score = $6
                        WHERE id = $1
                    """, shot_id, shot_status, video_path, last_frame,
                        gen_time, shot_quality)
                else:
                    await conn.execute(
                        "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                        shot_id, f"ComfyUI {result['status']}",
                    )

            except Exception as e:
                logger.error(f"Shot {shot_id} generation failed: {e}")
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shot_id, str(e)[:500],
                )

            await conn.execute(
                "UPDATE scenes SET completed_shots = $2 WHERE id = $1",
                scene_id, completed_count,
            )

        # Assemble final video
        if completed_videos:
            scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
            try:
                await concat_videos(completed_videos, scene_video_path)

                # Apply audio (dialogue + music) — non-fatal wrapper
                await apply_scene_audio(conn, scene_id, scene_video_path)

                # Get duration
                probe = await asyncio.create_subprocess_exec(
                    "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                    "-of", "csv=p=0", scene_video_path,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await probe.communicate()
                duration = float(stdout.decode().strip()) if stdout.decode().strip() else None

                final_status = "completed" if completed_count == len(shots) else "partial"
                await conn.execute("""
                    UPDATE scenes SET generation_status = $2, final_video_path = $3,
                           actual_duration_seconds = $4, current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id, final_status, scene_video_path, duration)
            except Exception as e:
                logger.error(f"Scene assembly failed: {e}")
                await conn.execute(
                    "UPDATE scenes SET generation_status = 'partial', current_generating_shot_id = NULL WHERE id = $1",
                    scene_id,
                )
        else:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed', current_generating_shot_id = NULL WHERE id = $1",
                scene_id,
            )

    except Exception as e:
        logger.error(f"Scene generation task failed: {e}")
        if conn:
            await conn.execute(
                "UPDATE scenes SET generation_status = 'failed', current_generating_shot_id = NULL WHERE id = $1",
                scene_id,
            )
    finally:
        if conn:
            await conn.close()
        _scene_generation_tasks.pop(scene_id, None)
