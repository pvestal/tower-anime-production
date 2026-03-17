"""Scene builder helper functions — ComfyUI polling, generation orchestrator, and re-exports.

Video utilities split into scene_video_utils.py.
Audio functions split into scene_audio.py.
Prompt engineering split into scene_prompt.py.
ComfyUI helpers split into scene_comfyui.py.
Vision QC split into scene_vision_qc.py.
Keyframe generation split into scene_keyframe.py.
Source image/video assignment split into scene_source_assign.py.
All original exports remain available from this module.
"""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from packages.core.config import BASE_PATH, COMFYUI_URL, COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR
from packages.core.db import connect_direct
from packages.core.audit import log_decision
from packages.core.events import event_bus, SHOT_GENERATED


# LoRA resolution logic lives in lora_resolver.py — re-export for backwards compat
from .lora_resolver import (  # noqa: F401, E402
    _resolve_content_lora_pair,
    resolve_content_loras,
    gate_nsfw_lora,
    resolve_motion_lora,
    NSFW_KEYWORDS,
    ADULT_RATINGS,
)

from .framepack import build_framepack_workflow, _submit_comfyui_workflow
from .ltx_video import build_ltx_workflow, build_ltxv_looping_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
from .wan_video import build_wan_t2v_workflow, build_wan22_workflow, build_wan22_14b_i2v_workflow, build_dasiwa_i2v_workflow, check_dasiwa_ready, _submit_comfyui_workflow as _submit_wan_workflow
from .video_config import get_engine_defaults
from .shot_context import derive_scene_seed, resolve_video_dimensions, resolve_color_style, resolve_checkpoint
from .motion_intensity import classify_motion_intensity, get_motion_params, get_counter_motion
from .image_recommender import recommend_for_scene, batch_read_metadata

# Re-export from sub-modules so existing imports keep working
from .scene_video_utils import (  # noqa: F401
    extract_last_frame,
    _probe_duration,
    concat_videos,
    _concat_videos_hardcut,
    interpolate_video,
    upscale_video,
)
from .scene_audio import (  # noqa: F401
    ACE_STEP_URL,
    MUSIC_CACHE,
    AUDIO_CACHE_DIR,
    download_preview,
    overlay_audio,
    mix_scene_audio,
    build_scene_dialogue,
    _auto_generate_scene_music,
    apply_scene_audio,
)

# Re-export from new sub-modules (refactored from this file)
from .scene_prompt import (  # noqa: F401
    TAG_CATEGORIES,
    GENRE_VIDEO_PROFILES,
    _get_genre_profile,
    _classify_tag,
    _condense_for_video,
    _build_video_negative,
    build_shot_prompt_preview,
    _slug_cache,
    resolve_slug,
)
from .scene_comfyui import (  # noqa: F401
    copy_to_comfyui_input,
    poll_comfyui_completion,
)
from .scene_vision_qc import (  # noqa: F401
    _QC_AUTO_APPROVE_THRESHOLD,
    _run_vision_qc,
)
from .scene_keyframe import (  # noqa: F401
    _clip_evaluate_keyframe,
    keyframe_blitz,
)
from .scene_source_assign import (  # noqa: F401
    ensure_source_images,
    ensure_source_videos,
    _get_continuity_frame,
    _save_continuity_frame,
)
from .shot_completion import complete_shot, postprocess_video

# Stubs for scene_review.py (these were never defined — latent bug)
_QUALITY_GATES = [{"threshold": 0.6}]
_MAX_RETRIES = 3

logger = logging.getLogger(__name__)

LORA_DIR = Path("/opt/ComfyUI/models/loras")


def validate_shot_paths(shot_dict: dict) -> list[str]:
    """Pre-generation validation: check that referenced files exist on disk.

    Returns a list of error strings. Empty list = all clear.
    """
    errors = []
    for field in ("image_lora", "content_lora_high", "content_lora_low"):
        val = shot_dict.get(field)
        if val and not (LORA_DIR / val).exists():
            errors.append(f"{field}={val!r} not found in {LORA_DIR}")

    src = shot_dict.get("source_image_path")
    if src:
        src_path = Path(src) if Path(src).is_absolute() else BASE_PATH / src
        if not src_path.exists():
            errors.append(f"source_image_path={src!r} not found")

    return errors


# Scene output directory (canonical location — also set in scene_audio.py)
SCENE_OUTPUT_DIR = BASE_PATH.parent / "output" / "scenes"
SCENE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Track active scene generation tasks
_scene_generation_tasks: dict[str, asyncio.Task] = {}

# Semaphore: only 1 scene generates at a time (GPU memory constraint)
_scene_generation_lock = asyncio.Semaphore(1)

# Lock acquisition timeout (seconds) — prevents indefinite blocking
_LOCK_TIMEOUT = 1800  # 30 minutes max wait

# Cancellation event — set to signal all active generation to stop
_cancel_event = asyncio.Event()


async def acquire_scene_lock(timeout: float = _LOCK_TIMEOUT) -> bool:
    """Acquire the scene generation lock with a timeout.

    Returns True if acquired, False if timed out.
    """
    try:
        await asyncio.wait_for(_scene_generation_lock.acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.error(f"Scene generation lock timeout after {timeout}s — force-releasing")
        force_release_scene_lock()
        # Try once more after force release
        try:
            await asyncio.wait_for(_scene_generation_lock.acquire(), timeout=5)
            return True
        except asyncio.TimeoutError:
            return False


def force_release_scene_lock():
    """Force-release the scene generation lock.

    Used by cancel endpoint to unblock stuck pipelines.
    """
    # Semaphore(1) — if _value is 0, it's locked. Force it back to 1.
    if _scene_generation_lock._value == 0:
        _scene_generation_lock.release()
        logger.warning("Scene generation lock force-released")


def signal_cancel():
    """Signal all active generation to cancel."""
    _cancel_event.set()


def clear_cancel():
    """Clear the cancellation signal."""
    _cancel_event.clear()


def is_cancelled() -> bool:
    """Check if cancellation has been signalled."""
    return _cancel_event.is_set()



async def _assemble_scene(conn, scene_id, video_paths: list[str] | None = None, shots=None):
    """Assemble approved shot videos into final scene with transitions + audio.

    Called after all shots are approved (either auto or manual).
    If video_paths/shots not provided, fetches approved shots from DB.
    """
    scene_video_path = str(SCENE_OUTPUT_DIR / f"scene_{scene_id}.mp4")
    try:
        # Fetch shots + video paths from DB if not provided
        if shots is None or video_paths is None:
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 AND review_status = 'approved' "
                "ORDER BY shot_number", scene_id,
            )
            video_paths = [s["output_video_path"] for s in shots if s["output_video_path"]]

        if not video_paths:
            logger.warning(f"Scene {scene_id}: no approved videos to assemble")
            return

        transitions = []
        for shot in (shots[1:] if len(shots) > 1 else []):
            t_type = shot["transition_type"] if "transition_type" in shot.keys() else "dissolve"
            t_dur = shot["transition_duration"] if "transition_duration" in shot.keys() else 0.3
            transitions.append({
                "type": t_type or "dissolve",
                "duration": float(t_dur or 0.3),
            })
        await concat_videos(video_paths, scene_video_path, transitions=transitions)

        # Optional post-processing
        scene_meta = await conn.fetchrow(
            "SELECT post_interpolate_fps, post_upscale_factor FROM scenes WHERE id = $1",
            scene_id,
        )
        if scene_meta:
            interp_fps = scene_meta["post_interpolate_fps"]
            if interp_fps and interp_fps > 30:
                interp_path = scene_video_path.rsplit(".", 1)[0] + f"_{interp_fps}fps.mp4"
                result_path = await interpolate_video(
                    scene_video_path, interp_path, target_fps=interp_fps
                )
                if result_path != scene_video_path:
                    os.replace(result_path, scene_video_path)

            upscale_factor = scene_meta["post_upscale_factor"]
            if upscale_factor and upscale_factor > 1:
                upscale_path = scene_video_path.rsplit(".", 1)[0] + f"_{upscale_factor}x.mp4"
                result_path = await upscale_video(
                    scene_video_path, upscale_path, scale_factor=upscale_factor
                )
                if result_path != scene_video_path:
                    os.replace(result_path, scene_video_path)

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

        await conn.execute("""
            UPDATE scenes SET generation_status = 'completed', final_video_path = $2,
                   actual_duration_seconds = $3, current_generating_shot_id = NULL
            WHERE id = $1
        """, scene_id, scene_video_path, duration)

        logger.info(f"Scene {scene_id}: assembled {len(video_paths)} shots → {scene_video_path} ({duration:.1f}s)")
    except Exception as e:
        logger.error(f"Scene assembly failed: {e}")
        await conn.execute(
            "UPDATE scenes SET generation_status = 'assembly_failed', current_generating_shot_id = NULL WHERE id = $1",
            scene_id,
        )


async def assemble_approved_scene(scene_id) -> dict:
    """Public entry point — assemble a scene if all shots are approved.

    Called by the review endpoint when the last shot gets approved.
    Returns status dict.
    """
    conn = await connect_direct()
    try:
        counts = await conn.fetchrow("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE review_status = 'approved') as approved,
                   COUNT(*) FILTER (WHERE output_video_path IS NOT NULL) as with_video
            FROM shots WHERE scene_id = $1
        """, scene_id)

        if counts["approved"] < counts["total"]:
            return {
                "assembled": False,
                "reason": f"{counts['approved']}/{counts['total']} shots approved",
            }

        if counts["with_video"] < counts["total"]:
            return {
                "assembled": False,
                "reason": f"{counts['with_video']}/{counts['total']} shots have video",
            }

        await _assemble_scene(conn, scene_id)
        return {"assembled": True, "scene_id": str(scene_id)}
    finally:
        await conn.close()


async def recover_interrupted_generations():
    """On startup, find shots stuck in 'generating' and re-queue their scenes.

    Orderly: waits for ComfyUI, resets stuck shots to pending,
    then re-triggers scene generation one at a time via existing lock.
    """
    conn = await connect_direct()
    try:
        # 1. Find all stuck shots (status = 'generating')
        stuck = await conn.fetch("""
            SELECT sh.id, sh.scene_id, s.title, s.project_id
            FROM shots sh
            JOIN scenes s ON sh.scene_id = s.id
            WHERE sh.status = 'generating'
        """)
        if not stuck:
            logger.info("Recovery: no stuck shots found")
            return

        logger.warning(f"Recovery: found {len(stuck)} stuck shot(s) in 'generating' state")

        # 2. Smart recovery: check if output already exists on disk
        completed_count = 0
        reset_ids = []
        for row in stuck:
            shot_id = row["id"]
            # Check if this shot already has a valid output video
            video_path = await conn.fetchval(
                "SELECT output_video_path FROM shots WHERE id = $1", shot_id
            )
            if video_path and Path(video_path).exists():
                # Output exists — mark as completed instead of resetting
                await conn.execute("""
                    UPDATE shots SET status = 'completed',
                           review_status = 'pending_review',
                           error_message = 'recovered: output found on disk'
                    WHERE id = $1
                """, shot_id)
                completed_count += 1
                logger.info(f"Recovery: shot {shot_id} has valid output, marked completed")
            else:
                # No output — reset to pending for re-generation
                await conn.execute("""
                    UPDATE shots SET status = 'pending',
                           comfyui_prompt_id = NULL,
                           error_message = 'reset by startup recovery'
                    WHERE id = $1
                """, shot_id)
                reset_ids.append(row["scene_id"])

        logger.info(f"Recovery: {completed_count} shot(s) marked completed (output on disk), "
                     f"{len(reset_ids)} shot(s) reset to pending")

        # 2b. Collect unique scene IDs from reset shots only
        scene_ids = list(dict.fromkeys(reset_ids))

        # 4. Reset their scenes' generation_status and current_generating_shot_id
        for sid in scene_ids:
            await conn.execute("""
                UPDATE scenes SET generation_status = 'pending',
                       current_generating_shot_id = NULL
                WHERE id = $1 AND generation_status = 'generating'
            """, sid)

        # Recovery no longer auto-re-queues scenes. Shots are reset to pending
        # and the batch runner or user can trigger regeneration per-shot.
        # This avoids scene-level locks that block per-shot regenerate calls.
        logger.info(f"Recovery: {len(scene_ids)} scene(s) have pending shots ready for regeneration")
    finally:
        await conn.close()


async def generate_scene(scene_id: str, auto_approve: bool = False):
    """Background task: generate all shots sequentially with continuity chaining.

    Uses _scene_generation_lock to ensure only one scene generates at a time,
    so scenes complete fully (all shots in order) before the next scene starts.
    Lock has a 30-minute timeout to prevent indefinite blocking.

    Args:
        auto_approve: If True, shots are auto-approved after generation so the
            full downstream pipeline (voice → music → assembly) fires without
            manual review. Also enabled by project metadata auto_approve_shots=true.
    """
    acquired = await acquire_scene_lock()
    if not acquired:
        logger.error(f"Scene {scene_id}: could not acquire lock, skipping")
        return
    try:
        clear_cancel()  # Reset cancel signal for this run
        await _generate_scene_impl(scene_id, auto_approve=auto_approve)
    finally:
        _scene_generation_lock.release()


async def roll_forward_wan_shot(
    prompt_text: str,
    ref_image: str,
    target_seconds: float,
    negative_text: str = "low quality, blurry, distorted, watermark, text, ugly",
    segment_seconds: float = 5.0,
    crossfade_seconds: float = 0.3,
    width: int = 480,
    height: int = 720,
    fps: int = 16,
    steps: int = 4,
    split_steps: int | None = None,
    cfg: float = 3.5,
    seed: int | None = None,
    output_prefix: str = "rollforward",
    use_lightx2v: bool = True,
    motion_lora: str | None = None,
    motion_lora_strength: float = 0.8,
    content_lora_high: str | None = None,
    content_lora_low: str | None = None,
    content_lora_strength: float = 0.85,
    engine: str = "wan22_14b",
) -> dict:
    """Generate a long video by chaining multiple I2V segments.

    Supports both WAN 2.2 14B and DaSiWa engines via the `engine` parameter.

    Pattern C: generate 5s clip → extract last frame → generate next 5s clip →
    crossfade stitch all segments into one continuous video.

    Returns dict with keys: video_path, last_frame, segment_count, total_duration.
    """
    import random as _random
    import time as _time

    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    num_segments = max(1, int(target_seconds / segment_seconds + 0.5))
    logger.info(
        f"Roll-forward ({engine}): {target_seconds}s target → {num_segments} segments × "
        f"{segment_seconds}s, crossfade={crossfade_seconds}s"
    )

    num_frames_per_seg = max(9, int(segment_seconds * fps) + 1)
    current_source = ref_image
    segment_paths = []

    for seg_idx in range(num_segments):
        seg_prefix = f"{output_prefix}_seg{seg_idx:02d}"
        seg_seed = seed + seg_idx

        _rf_split = split_steps if split_steps is not None else (steps // 2)

        if engine == "dasiwa":
            from .wan_video import build_dasiwa_i2v_workflow
            workflow, prefix = build_dasiwa_i2v_workflow(
                prompt_text=prompt_text,
                ref_image=current_source,
                width=width, height=height,
                num_frames=num_frames_per_seg, fps=fps,
                total_steps=steps,
                split_steps=_rf_split,
                cfg=cfg,
                seed=seg_seed,
                negative_text=negative_text,
                output_prefix=seg_prefix,
                motion_lora=motion_lora,
                motion_lora_strength=motion_lora_strength,
                content_lora_high=content_lora_high,
                content_lora_low=content_lora_low,
                content_lora_strength=content_lora_strength,
            )
        else:
            workflow, prefix = build_wan22_14b_i2v_workflow(
                prompt_text=prompt_text,
                ref_image=current_source,
                width=width, height=height,
                num_frames=num_frames_per_seg, fps=fps,
                total_steps=steps,
                split_steps=_rf_split,
                cfg=cfg,
                seed=seg_seed,
                negative_text=negative_text,
                output_prefix=seg_prefix,
                use_lightx2v=use_lightx2v,
                motion_lora=motion_lora,
                motion_lora_strength=motion_lora_strength,
                content_lora_high=content_lora_high,
                content_lora_low=content_lora_low,
                content_lora_strength=content_lora_strength,
            )

        logger.info(
            f"Roll-forward seg {seg_idx+1}/{num_segments}: "
            f"source={current_source} seed={seg_seed}"
        )

        comfyui_prompt_id = _submit_wan_workflow(workflow)
        result = await poll_comfyui_completion(comfyui_prompt_id)

        if result["status"] != "completed" or not result["output_files"]:
            logger.error(
                f"Roll-forward seg {seg_idx+1} failed: {result.get('error', result['status'])}"
            )
            break

        seg_video = str(COMFYUI_OUTPUT_DIR / result["output_files"][0])
        segment_paths.append(seg_video)
        logger.info(f"Roll-forward seg {seg_idx+1} done: {Path(seg_video).name}")

        # Extract last frame for next segment's source
        last_frame_path = await extract_last_frame(seg_video)

        # Copy last frame to ComfyUI input dir for next I2V pass
        dest = str(COMFYUI_INPUT_DIR / Path(last_frame_path).name)
        shutil.copy2(last_frame_path, dest)
        current_source = Path(last_frame_path).name

    if not segment_paths:
        return {"video_path": None, "last_frame": None, "segment_count": 0, "total_duration": 0}

    # Single segment — no concat needed
    if len(segment_paths) == 1:
        lf = await extract_last_frame(segment_paths[0])
        dur = await _probe_duration(segment_paths[0])
        return {
            "video_path": segment_paths[0],
            "last_frame": lf,
            "segment_count": 1,
            "total_duration": dur,
        }

    # Crossfade stitch all segments
    stitched_path = str(COMFYUI_OUTPUT_DIR / f"{output_prefix}_stitched.mp4")
    transitions = [{"type": "dissolve", "duration": crossfade_seconds}] * (len(segment_paths) - 1)
    await concat_videos(segment_paths, stitched_path, transitions)

    lf = await extract_last_frame(stitched_path)
    dur = await _probe_duration(stitched_path)
    logger.info(
        f"Roll-forward complete: {len(segment_paths)} segments → "
        f"{dur:.1f}s final video at {stitched_path}"
    )

    return {
        "video_path": stitched_path,
        "last_frame": lf,
        "segment_count": len(segment_paths),
        "total_duration": dur,
    }


async def _generate_scene_impl(scene_id: str, auto_approve: bool = False):
    """Inner implementation — do not call directly, use generate_scene().

    Args:
        scene_id: UUID of the scene to generate.
        auto_approve: If True, auto-approve all completed shots so the full
            downstream pipeline (voice synthesis → music → audio mixing →
            scene assembly) fires automatically without manual review.
    """
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

        # Get project_id, scene_number, and episode info for continuity tracking + filenames
        scene_row = await conn.fetchrow("""
            SELECT s.project_id, s.scene_number, e.episode_number,
                   REGEXP_REPLACE(LOWER(REPLACE(p.name, ' ', '_')), '[^a-z0-9_]', '', 'g') as project_slug,
                   p.genre, p.content_rating, p.video_lora
            FROM scenes s
            LEFT JOIN episodes e ON s.episode_id = e.id
            LEFT JOIN projects p ON s.project_id = p.id
            WHERE s.id = $1
        """, scene_id)
        project_id = scene_row["project_id"] if scene_row else None
        scene_number = scene_row["scene_number"] if scene_row else None
        episode_number = scene_row["episode_number"] if scene_row else None
        project_slug = scene_row["project_slug"] if scene_row else "proj"
        project_video_lora = scene_row.get("video_lora") if scene_row else None
        genre_profile = _get_genre_profile(
            scene_row.get("genre") if scene_row else None,
            scene_row.get("content_rating") if scene_row else None,
        )

        # Check project-level auto_approve setting if not explicitly passed
        if not auto_approve and project_id:
            try:
                proj_meta = await conn.fetchval(
                    "SELECT metadata->>'auto_approve_shots' FROM projects WHERE id = $1",
                    project_id,
                )
                if proj_meta == "true":
                    auto_approve = True
            except Exception:
                pass

        await conn.execute(
            "UPDATE scenes SET generation_status = 'generating', total_shots = $2 WHERE id = $1",
            scene_id, len(shots),
        )

        # Step 0: Auto-assign source VIDEO clips (for V2V reference pipeline)
        # Skip for trailer scenes — trailers use keyframes as I2V source, not movie clips
        _is_trailer_scene = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM trailers WHERE scene_id = $1)", scene_id
        )
        if not _is_trailer_scene:
            video_assigned = await ensure_source_videos(conn, scene_id, shots)
            if video_assigned:
                shots = await conn.fetch(
                    "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                    scene_id,
                )

        # Step 1: Auto-assign source images FIRST (before engine selection)
        # This ensures solo shots get images, then engine selector sees
        # has_source_image=True and picks FramePack instead of falling back to Wan
        auto_assigned = await ensure_source_images(conn, scene_id, shots)
        if auto_assigned:
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                scene_id,
            )

        # Step 1.5: Generate composite keyframes for multi-character shots
        # Without source images, multi-char shots route to Wan T2V (garbage).
        # With source images, they route to Wan 2.2 14B I2V (quality).
        multi_char_no_img = [
            s for s in shots
            if not s["source_image_path"]
            and len(s.get("characters_present") or []) >= 2
        ]
        if multi_char_no_img:
            from .composite_image import generate_composite_source, generate_simple_keyframe
            _ckpt = await resolve_checkpoint(conn, project_id)

            _keyframe_count = 0
            for _mc_shot in multi_char_no_img:
                _mc_chars = list(_mc_shot.get("characters_present") or [])
                _mc_prompt = _mc_shot.get("motion_prompt") or _mc_shot.get("scene_description") or ""
                _kf_path = None
                # Simple keyframe first (txt2img + LoRA) — reliable, full scene
                # Composite (IP-Adapter regional) has left/right split issues
                _mc_extra = []
                if _mc_shot.get("image_lora"):
                    _mc_extra.append((_mc_shot["image_lora"], _mc_shot.get("image_lora_strength") or 0.7))
                try:
                    _kf_path = await generate_simple_keyframe(
                        conn, project_id, _mc_chars, _mc_prompt, _ckpt,
                        extra_loras=_mc_extra or None,
                    )
                except Exception as _e:
                    logger.debug(f"Shot {_mc_shot['id']}: simple keyframe failed: {_e}")
                # Fallback: composite (IP-Adapter regional) if simple fails
                if not _kf_path or not _kf_path.exists():
                    try:
                        _kf_path = await generate_composite_source(
                            conn, project_id, _mc_chars, _mc_prompt, _ckpt
                        )
                    except Exception as _e:
                        logger.warning(f"Shot {_mc_shot['id']}: composite also failed: {_e}")

                if _kf_path and _kf_path.exists():
                    await conn.execute(
                        "UPDATE shots SET source_image_path = $2, source_image_auto_assigned = TRUE WHERE id = $1",
                        _mc_shot["id"], str(_kf_path),
                    )
                    _keyframe_count += 1
                    logger.info(f"Shot {_mc_shot['id']}: keyframe for {_mc_chars[:2]} → {_kf_path.name}")
                else:
                    logger.warning(f"Shot {_mc_shot['id']}: all keyframe generation failed for {_mc_chars[:2]}")

            if _keyframe_count:
                logger.info(f"Scene {scene_id}: generated {_keyframe_count}/{len(multi_char_no_img)} multi-char keyframes")
                shots = await conn.fetch(
                    "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                    scene_id,
                )

        # Step 2: Auto-assign engine only for shots that don't have one set
        from .engine_selector import select_engine as _pre_select_engine
        for _s in shots:
            if _s.get("video_engine"):
                continue  # respect manual override
            _s_has_source = bool(_s.get("source_image_path"))
            _sel = _pre_select_engine(has_source_image=_s_has_source)
            await conn.execute(
                "UPDATE shots SET video_engine = $2 WHERE id = $1",
                _s["id"], _sel.engine,
            )
            logger.info(f"Shot {_s['id']}: pre-assigned engine={_sel.engine}")
        # Re-fetch to pick up engine updates
        shots = await conn.fetch(
            "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
            scene_id,
        )

        # Pre-fetch narrative states for this scene (Phase 4)
        _nsm_shot_states = {}
        try:
            from packages.narrative_state.continuity import get_shot_state_context
            for _s in shots:
                _s_ctx = await get_shot_state_context(conn, scene_id, dict(_s))
                if _s_ctx:
                    _nsm_shot_states[str(_s["id"])] = _s_ctx
        except Exception as _e:
            logger.debug(f"NSM state context pre-fetch: {_e}")

        completed_videos = []
        completed_count = 0
        prev_last_frame = None
        prev_character = None

        for shot in shots:
            shot_id = shot["id"]

            # Skip already-completed shots (e.g., after a service restart)
            if (shot["status"] in ("completed", "accepted_best")
                    and shot["output_video_path"]
                    and Path(shot["output_video_path"]).exists()):
                completed_videos.append(shot["output_video_path"])
                completed_count += 1
                prev_last_frame = shot["last_frame_path"]
                skip_chars = shot.get("characters_present")
                prev_character = skip_chars[0] if skip_chars and isinstance(skip_chars, list) else None
                # Backfill continuity frame from already-completed shots
                if prev_character and prev_last_frame and project_id:
                    try:
                        await _save_continuity_frame(
                            conn, project_id, prev_character,
                            scene_id, shot_id, prev_last_frame,
                            scene_number=scene_number,
                            shot_number=shot.get("shot_number"),
                        )
                    except Exception:
                        pass
                logger.info(f"Shot {shot_id}: already completed, skipping")
                continue

            await conn.execute(
                "UPDATE shots SET status = 'generating' WHERE id = $1", shot_id
            )
            await conn.execute(
                "UPDATE scenes SET current_generating_shot_id = $2 WHERE id = $1",
                scene_id, shot_id,
            )

            # Shot spec enrichment: AI-driven pose/camera/emotion before generation
            # SKIP enrichment when the shot already has a generation_prompt set —
            # enrichment overwrites LoRA-aligned prompts with generic SFW content.
            _existing_prompt = (shot.get("generation_prompt") or "").strip()
            if _existing_prompt:
                logger.info(f"Shot {shot_id}: skipping enrichment — generation_prompt already set ({len(_existing_prompt)} chars)")
            else:
                try:
                    from .shot_spec import enrich_shot_spec, get_scene_context, get_recent_shots
                    _scene_ctx = await get_scene_context(conn, scene_id)
                    _prev_shots = await get_recent_shots(conn, scene_id, limit=5)
                    await enrich_shot_spec(conn, dict(shot), _scene_ctx, _prev_shots)
                    # Re-fetch shot with enriched fields
                    shot = await conn.fetchrow("SELECT * FROM shots WHERE id = $1", shot_id)
                except Exception as _enrich_err:
                    logger.debug(f"Shot {shot_id}: spec enrichment skipped: {_enrich_err}")

            # Single-pass generation — no QC vision review, all shots go to manual review
            try:
                from .video_qc import check_engine_blacklist
                from .framepack import build_framepack_workflow, _submit_comfyui_workflow
                from .ltx_video import build_ltx_workflow, build_ltxv_looping_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
                from .wan_video import build_wan_t2v_workflow, build_wan22_workflow, build_wan22_14b_i2v_workflow, build_dasiwa_i2v_workflow, check_dasiwa_ready, _submit_comfyui_workflow as _submit_wan_workflow
                import time as _time_inner

                shot_dict = dict(shot)
                character_slug = None
                chars = shot_dict.get("characters_present")
                if chars and isinstance(chars, list) and len(chars) > 0:
                    character_slug = chars[0]

                # Use project-level video_lora from DB (project-scoped, not global)
                _project_wan_lora = project_video_lora

                # Engine selection: respect manual override, otherwise auto-select
                from .engine_selector import select_engine, VALID_ENGINES, EngineSelection
                _existing_engine = shot_dict.get("video_engine")
                if _existing_engine and _existing_engine in VALID_ENGINES:
                    # Manual override or previously set — respect it
                    shot_engine = _existing_engine
                    engine_sel = EngineSelection(engine=shot_engine, reason="manual override (pre-set on shot)")
                    logger.info(f"Shot {shot_id}: using pre-set engine={shot_engine}")
                else:
                    has_source = bool(shot_dict.get("source_image_path"))
                    engine_sel = select_engine(
                        has_source_image=has_source,
                    )
                    shot_engine = engine_sel.engine
                    await conn.execute(
                        "UPDATE shots SET video_engine = $2 WHERE id = $1",
                        shot_id, shot_engine,
                    )
                    logger.info(f"Shot {shot_id}: engine={shot_engine} reason='{engine_sel.reason}'")

                # Engine blacklist check
                if character_slug:
                    project_id = None
                    try:
                        scene_row = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", scene_id)
                        if scene_row:
                            project_id = scene_row["project_id"]
                    except Exception:
                        pass
                    bl = await check_engine_blacklist(conn, character_slug, project_id, shot_engine)
                    if bl:
                        logger.warning(f"Shot {shot_id}: engine '{shot_engine}' blacklisted for '{character_slug}'")
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, f"Engine '{shot_engine}' blacklisted: {bl.get('reason', '')}",
                        )
                        continue

                # Build identity-anchored prompt
                motion_prompt = shot_dict["motion_prompt"] or shot_dict.get("generation_prompt") or ""

                # Helper: look up character by short or full slug
                async def _find_character(slug):
                    return await conn.fetchrow(
                        "SELECT name, design_prompt FROM characters "
                        "WHERE project_id = $2 AND ("
                        "  REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 "
                        "  OR REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') LIKE $1 || '_%'"
                        ")", slug, project_id,
                    )

                # Fetch scene context for richer prompts
                scene_desc = ""
                scene_location = ""
                scene_mood = ""
                scene_time = ""
                try:
                    _scene_ctx = await conn.fetchrow(
                        "SELECT description, location, time_of_day, mood FROM scenes WHERE id = $1",
                        scene_id,
                    )
                    if _scene_ctx:
                        scene_desc = _scene_ctx["description"] or ""
                        scene_location = _scene_ctx["location"] or ""
                        scene_mood = _scene_ctx["mood"] or ""
                        scene_time = _scene_ctx["time_of_day"] or ""
                except Exception:
                    pass

                # Fetch project style for visual anchoring
                style_anchor = ""
                _project_width = None
                _project_height = None
                try:
                    _style_row = await conn.fetchrow(
                        "SELECT gs.checkpoint_model, gs.prompt_format, gs.width, gs.height FROM projects p "
                        "JOIN generation_styles gs ON p.default_style = gs.style_name "
                        "WHERE p.id = $1", project_id,
                    )
                    if _style_row:
                        ckpt = (_style_row["checkpoint_model"] or "").lower()
                        if "realistic" in ckpt or "cyber" in ckpt or "basil" in ckpt or "lazymix" in ckpt:
                            style_anchor = "photorealistic, live action film, cinematic lighting"
                        elif "cartoon" in ckpt or "pixar" in ckpt:
                            style_anchor = "3D animated, Pixar style, cinematic lighting"
                        elif "illustrious" in ckpt or "counterfeit" in ckpt or "noob" in ckpt:
                            style_anchor = "anime style, detailed animation, cinematic"
                        elif "nova_animal" in ckpt or "pony" in ckpt:
                            style_anchor = "anime style, detailed illustration, anthropomorphic, cinematic"
                        else:
                            style_anchor = "anime style, cinematic"
                        # Store project resolution for Wan T2V aspect ratio
                        _project_width = _style_row["width"]
                        _project_height = _style_row["height"]
                except Exception:
                    pass

                # Allow project-level metadata to override style_anchor
                # (e.g. photorealistic project using an anime checkpoint)
                try:
                    _meta = await conn.fetchval(
                        "SELECT metadata->>'style_anchor' FROM projects WHERE id = $1",
                        project_id,
                    )
                    if _meta:
                        style_anchor = _meta
                        logger.info(f"Shot {shot_id}: style_anchor overridden by project metadata: {style_anchor}")
                except Exception:
                    pass

                current_prompt = motion_prompt
                # If shot already had a generation_prompt (enriched by Ollama or pre-set),
                # skip prompt rebuilding — it already contains character + scene context.
                # Re-building would duplicate descriptions and waste token budget.
                _prompt_was_enriched = bool((shot_dict.get("generation_prompt") or "").strip())
                if _prompt_was_enriched:
                    logger.debug(f"Shot {shot_id}: using pre-enriched prompt ({len(current_prompt)} chars), skipping rebuild")
                elif character_slug and shot_engine in ("framepack", "framepack_f1"):
                    try:
                        char_row = await _find_character(character_slug)
                        if char_row and char_row["design_prompt"]:
                            appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                            # Build FramePack prompt with same structure as Wan:
                            # style anchor → scene context → character → motion
                            fp_parts = []
                            if style_anchor:
                                fp_parts.append(style_anchor)
                            if scene_location:
                                setting = scene_location
                                if scene_time:
                                    setting += f", {scene_time}"
                                fp_parts.append(setting)
                            if scene_desc:
                                fp_parts.append(scene_desc)
                            fp_parts.append(appearance)
                            if motion_prompt and motion_prompt.lower() != "static":
                                fp_parts.append(motion_prompt)
                            fp_parts.append("consistent character appearance, maintain all physical features")
                            if scene_mood:
                                fp_parts.append(f"{scene_mood} mood")
                            current_prompt = ", ".join(fp_parts)
                            logger.info(f"Shot {shot_id}: FramePack prompt ({len(current_prompt)} chars): {current_prompt[:120]}...")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: design_prompt lookup failed: {e}")
                elif shot_engine in ("wan22", "wan22_14b") and chars:
                    # Wan 2.2 5B/14B: richer prompt capacity than 1.3B.
                    # Character → action → scene context → style (5B handles longer prompts well).
                    try:
                        char_descriptions = []
                        for cslug in chars:
                            char_row = await _find_character(cslug)
                            if char_row and char_row["design_prompt"]:
                                cname = char_row["name"]
                                appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                                char_descriptions.append(f"{cname} ({appearance})")
                        prompt_parts = []
                        # 1. Character descriptions (5B has enough attention for full descriptions)
                        if char_descriptions:
                            prompt_parts.append("; ".join(char_descriptions))
                        # 2. Action/motion
                        if motion_prompt and motion_prompt.lower() != "static":
                            prompt_parts.append(motion_prompt)
                        # 3. Scene description (more room with 5B)
                        if scene_desc and genre_profile.get("include_scene_desc", True):
                            prompt_parts.append(scene_desc[:200])
                        # 4. Scene context
                        if scene_location:
                            setting = scene_location
                            if scene_time:
                                setting += f", {scene_time}"
                            prompt_parts.append(setting)
                        # 5. Style anchor
                        if style_anchor:
                            prompt_parts.append(style_anchor)
                        if scene_mood:
                            prompt_parts.append(f"{scene_mood} mood")
                        current_prompt = ". ".join(prompt_parts)
                        logger.info(f"Shot {shot_id}: Wan22 prompt ({len(current_prompt)} chars): {current_prompt[:120]}...")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: Wan22 prompt build failed: {e}")
                elif shot_engine == "wan" and chars:
                    # Wan T2V: ACTION FIRST, then condensed characters, then context.
                    # Wan 1.3B has limited attention — explicit terms must be near the start.
                    try:
                        char_descriptions = []
                        for cslug in chars:
                            char_row = await _find_character(cslug)
                            if char_row and char_row["design_prompt"]:
                                cname = char_row["name"]
                                appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                                char_descriptions.append(f"{cname} ({appearance})")
                        # Build structured prompt: ACTION → characters → scene
                        prompt_parts = []
                        # 1. Action/motion FIRST — this is what the shot is about
                        if motion_prompt and motion_prompt.lower() != "static":
                            prompt_parts.append(motion_prompt)
                        # 2. Condensed character appearances
                        if char_descriptions:
                            prompt_parts.append("; ".join(char_descriptions))
                        # 3. Scene description (truncated for token budget)
                        if scene_desc and genre_profile.get("include_scene_desc", True):
                            prompt_parts.append(scene_desc[:120])
                        # 4. Scene context (location + time)
                        if scene_location:
                            setting = scene_location
                            if scene_time:
                                setting += f", {scene_time}"
                            prompt_parts.append(setting)
                        # 5. Style anchor last (least important for content)
                        if style_anchor:
                            prompt_parts.append(style_anchor)
                        current_prompt = ". ".join(prompt_parts)
                        logger.info(f"Shot {shot_id}: Wan prompt ({len(current_prompt)} chars): {current_prompt[:120]}...")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: Wan prompt build failed: {e}")

                # Apply alternating motion prompt for dynamic video motion
                if shot_engine == "wan22_14b" and motion_prompt:
                    from .scene_prompt import build_alternating_motion_prompt
                    _motion_tier = classify_motion_intensity(shot_dict, lora_name=shot_dict.get("lora_name"), prompt=motion_prompt)
                    current_prompt = build_alternating_motion_prompt(current_prompt, _motion_tier)
                    logger.debug(f"Shot {shot_id}: alternating motion applied (tier={_motion_tier})")

                # Inject NSM state descriptors into prompt (Phase 4)
                _shot_nsm = _nsm_shot_states.get(str(shot_id), {})
                if _shot_nsm and character_slug and character_slug in _shot_nsm:
                    _state_ctx = _shot_nsm[character_slug]
                    if _state_ctx.get("prompt_additions"):
                        current_prompt = f"{current_prompt}, {_state_ctx['prompt_additions']}"
                        logger.info(f"Shot {shot_id}: NSM state additions: {_state_ctx['prompt_additions'][:80]}")
                elif _shot_nsm and shot_engine in ("wan", "wan22_14b") and chars:
                    # Multi-character: use structured state prompt builder
                    try:
                        from packages.narrative_state.continuity import build_multi_character_state_prompt
                        _mc_chars = []
                        for _cs in chars:
                            _cs_state = _shot_nsm.get(_cs, {}).get("state", {})
                            _cs_row = await _find_character(_cs)
                            _mc_chars.append({
                                "name": _cs_row["name"] if _cs_row else _cs,
                                "slug": _cs,
                                "design_prompt": _cs_row["design_prompt"] if _cs_row else "",
                                "state": _cs_state,
                            })
                        if any(c["state"] for c in _mc_chars):
                            current_prompt = build_multi_character_state_prompt(
                                characters=_mc_chars,
                                motion_prompt=current_prompt,
                            )
                            logger.info(f"Shot {shot_id}: multi-char state prompt built ({len(current_prompt)} chars)")
                    except Exception as _mc_err:
                        # Fallback to simple injection
                        state_additions = []
                        for _cs in chars:
                            if _cs in _shot_nsm and _shot_nsm[_cs].get("prompt_additions"):
                                state_additions.append(f"{_cs}: {_shot_nsm[_cs]['prompt_additions']}")
                        if state_additions:
                            current_prompt = f"{current_prompt}. State: {'. '.join(state_additions)}"
                        logger.debug(f"Shot {shot_id}: multi-char state prompt fallback: {_mc_err}")

                # Build genre + style-aware negative prompt
                _nsm_neg = ""
                if _shot_nsm and character_slug and character_slug in _shot_nsm:
                    _nsm_neg = _shot_nsm[character_slug].get("negative_additions", "")
                current_negative = _build_video_negative(style_anchor, genre_profile, _nsm_neg)
                # Engine-tuned defaults from video_models.yaml config
                _eng_cfg = get_engine_defaults(shot_engine) if shot_engine else {}
                _default_steps = _eng_cfg.get("steps", 20) if _eng_cfg else (20 if shot_engine in ("wan", "wan22") else 25)
                shot_steps = shot_dict.get("steps") or _default_steps
                shot_guidance = shot_dict.get("guidance_scale") or _eng_cfg.get("cfg", 6.0)
                _raw_dur = shot_dict.get("duration_seconds")
                shot_seconds = float(_raw_dur) if _raw_dur else 5.0
                logger.info(f"Shot {shot_id}: duration_seconds raw={_raw_dur!r} → shot_seconds={shot_seconds}")
                shot_use_f1 = shot_dict.get("use_f1") or False
                shot_seed = shot_dict.get("seed")

                # Determine first frame source — priority order:
                # 0. Multi-character FramePack: generate composite source image via IP-Adapter
                # 1. Previous shot's last frame (same character, same scene) — intra-scene continuity
                # 2. Cross-scene continuity frame (same character, prior scene) — inter-scene continuity
                # 3. Auto-assigned source image from approved pool — cold start
                # Wan T2V is text-only — skip source image entirely
                is_multi_char = chars and len(chars) >= 2
                image_filename = None
                first_frame_path = None
                if shot_engine == "wan":
                    logger.info(f"Shot {shot_id}: Wan T2V — no source image needed")
                elif shot_engine == "wan22" and is_multi_char:
                    # Wan 2.2 multi-char: T2V mode, no source image needed
                    logger.info(f"Shot {shot_id}: Wan22 T2V (multi-char) — no source image needed")
                # wan22 solo shots fall through to source image selection below (I2V mode)
                elif is_multi_char and shot_engine in ("framepack", "framepack_f1"):
                    # Multi-character shot: generate composite source image
                    try:
                        from .composite_image import generate_composite_source
                        # Get checkpoint from project's generation style
                        ckpt = await resolve_checkpoint(conn, project_id)

                        logger.info(f"Shot {shot_id}: multi-char ({chars}) — generating composite source image")
                        composite_path = await generate_composite_source(
                            conn, project_id, list(chars), motion_prompt, ckpt
                        )
                        if composite_path and composite_path.exists():
                            first_frame_path = str(composite_path)
                            image_filename = await copy_to_comfyui_input(first_frame_path)
                            logger.info(f"Shot {shot_id}: composite source ready: {composite_path.name}")
                        else:
                            logger.warning(f"Shot {shot_id}: composite generation failed, falling back to solo image")
                            # Fall through to solo image logic below
                            is_multi_char = False
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: composite error: {e}, falling back to solo image")
                        is_multi_char = False

                if not image_filename and shot_engine != "wan" and not (is_multi_char and first_frame_path):
                    # Skip continuity chaining for shots with content LoRAs —
                    # they need keyframes matching their specific position/action,
                    # not a last frame from a different position.
                    _has_content_lora = bool(shot_dict.get("lora_name") or shot_dict.get("image_lora") or shot_dict.get("content_lora_high"))
                    same_char_prev_shot = (
                        prev_last_frame
                        and prev_character
                        and character_slug == prev_character
                        and Path(prev_last_frame).exists()
                        and not _has_content_lora
                    )
                    if same_char_prev_shot:
                        # Priority 1: chain from previous shot in this scene
                        first_frame_path = prev_last_frame
                        image_filename = await copy_to_comfyui_input(first_frame_path)
                        logger.info(f"Shot {shot_id}: continuity chain from previous shot (same character: {character_slug})")
                    else:
                        # Priority 2: check for cross-scene continuity frame
                        # Skip for shots with pre-assigned content LoRAs (test matrix) —
                        # they need their own source image, not a continuity frame from a different action
                        cross_scene_frame = None
                        if character_slug and project_id and not _has_content_lora:
                            _char_target_state = None
                            if _shot_nsm and character_slug in _shot_nsm:
                                _char_target_state = _shot_nsm[character_slug].get("state")
                            if _char_target_state:
                                try:
                                    from packages.narrative_state.continuity import select_continuity_source
                                    cross_scene_frame = await select_continuity_source(
                                        conn, project_id, character_slug,
                                        _char_target_state, scene_id,
                                    )
                                except Exception as _e:
                                    logger.debug(f"NSM continuity selection: {_e}")
                            if not cross_scene_frame:
                                cross_scene_frame = await _get_continuity_frame(
                                    conn, project_id, character_slug, scene_id
                                )

                        if cross_scene_frame:
                            first_frame_path = cross_scene_frame
                            image_filename = await copy_to_comfyui_input(first_frame_path)
                            logger.info(
                                f"Shot {shot_id}: cross-scene continuity frame for '{character_slug}' "
                                f"(from prior scene)"
                            )
                        else:
                            # Priority 3: pose-matched keyframe if content LoRA has keyframe_prompt
                            source_path = shot_dict.get("source_image_path")
                            _shot_clh = shot_dict.get("content_lora_high")
                            # Skip inline keyframe gen if keyframe_generation phase already produced one
                            _already_has_keyframe = source_path and "keyframe" in source_path and Path(source_path).exists()
                            if _already_has_keyframe:
                                logger.info(f"Shot {shot_id}: using pre-generated pose keyframe: {Path(source_path).name}")
                                image_filename = await copy_to_comfyui_input(source_path)
                                first_frame_path = source_path
                            elif _shot_clh and character_slug:
                                try:
                                    from .scene_keyframe import generate_pose_keyframe
                                    _pose_kf = await generate_pose_keyframe(
                                        conn, shot_id, project_id, character_slug,
                                        content_lora_high=_shot_clh,
                                    )
                                    if _pose_kf and _pose_kf.exists():
                                        source_path = str(_pose_kf)
                                        image_filename = await copy_to_comfyui_input(source_path)
                                        first_frame_path = source_path
                                        logger.info(f"Shot {shot_id}: pose-matched keyframe for '{_shot_clh}'")
                                except Exception as _pkf_err:
                                    logger.debug(f"Shot {shot_id}: pose keyframe skipped: {_pkf_err}")

                            # Priority 4: fall back to auto-assigned source image
                            if not source_path:
                                if shot_engine in ("wan22", "ltx", "ltx_long"):
                                    # Engines that support T2V: graceful fallback (no ref image)
                                    logger.info(f"Shot {shot_id}: {shot_engine} no source image → T2V fallback")
                                elif shot_engine == "wan22_14b":
                                    # 14B is I2V only — generate a keyframe on the fly
                                    logger.warning(f"Shot {shot_id}: wan22_14b needs source image, generating keyframe")
                                    try:
                                        from .composite_image import generate_simple_keyframe
                                        _ckpt = await resolve_checkpoint(conn, project_id)
                                        # Include shot's image LoRA for content-accurate keyframes
                                        _kf_extra_loras = None
                                        _kf_img_lora = shot_dict.get("image_lora")
                                        if _kf_img_lora:
                                            _kf_img_str = shot_dict.get("image_lora_strength") or 0.7
                                            _kf_extra_loras = [(_kf_img_lora, _kf_img_str)]
                                            logger.info(f"Shot {shot_id}: keyframe will use image LoRA {_kf_img_lora} @ {_kf_img_str}")
                                        _kf_chars = chars if chars else []
                                        _kf = await generate_simple_keyframe(
                                            conn, project_id, list(_kf_chars),
                                            motion_prompt or "", _ckpt,
                                            extra_loras=_kf_extra_loras,
                                        )
                                        if _kf and _kf.exists():
                                            source_path = str(_kf)
                                            await conn.execute(
                                                "UPDATE shots SET source_image_path = $2 WHERE id = $1",
                                                shot_id, source_path)
                                            logger.info(f"Shot {shot_id}: keyframe generated → {_kf.name}")
                                        else:
                                            raise RuntimeError("keyframe generation returned no output")
                                    except Exception as _kf_err:
                                        logger.error(f"Shot {shot_id}: keyframe fallback failed: {_kf_err}")
                                        await conn.execute(
                                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                                            shot_id, f"No source image and keyframe generation failed: {_kf_err}")
                                        continue
                                else:
                                    logger.error(f"Shot {shot_id}: no source image and no continuity frame available")
                                    await conn.execute(
                                        "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                                        shot_id, "No source image available (auto-assignment failed or no characters_present)")
                                    continue
                            image_filename = await copy_to_comfyui_input(source_path)
                            first_frame_path = str(BASE_PATH / source_path) if not Path(source_path).is_absolute() else source_path
                            if prev_character and character_slug != prev_character:
                                logger.info(f"Shot {shot_id}: character switch {prev_character} → {character_slug}, using source image")

                attempt_start = _time_inner.time()

                # Build structured filename prefix: {project}_ep{N}_sc{N}_sh{N}_{engine}_{hash}
                # The hash is the first 8 chars of the shot UUID for disk→DB traceability.
                _ep = f"ep{episode_number:02d}" if episode_number else "ep00"
                _sc = f"sc{scene_number:02d}" if scene_number else "sc00"
                _sh = f"sh{shot_dict.get('shot_number', 0):02d}"
                _shot_hash = str(shot_id).replace("-", "")[:8]
                _file_prefix = f"{project_slug}_{_ep}_{_sc}_{_sh}_{shot_engine}_{_shot_hash}"

                # Persist the final assembled prompts so they're visible in the UI
                await conn.execute(
                    "UPDATE shots SET generation_prompt = $2, generation_negative = $3 WHERE id = $1",
                    shot_id, current_prompt, current_negative,
                )

                # Pre-generation validation: verify referenced files exist
                _val_errors = validate_shot_paths(shot_dict)
                if _val_errors:
                    _val_msg = "; ".join(_val_errors)
                    logger.warning(f"Shot {shot_id}: path validation failed — {_val_msg}")
                    await conn.execute(
                        "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                        shot_id, f"Path validation: {_val_msg}",
                    )
                    continue

                # Dispatch to video engine via engine_dispatch module
                from .engine_dispatch import get_dispatcher
                _dispatcher = get_dispatcher(shot_engine)
                if not _dispatcher:
                    logger.error(f"Shot {shot_id}: no dispatcher for engine '{shot_engine}'")
                    await conn.execute(
                        "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                        shot_id, f"No dispatcher for engine '{shot_engine}'",
                    )
                    continue

                _project_rating = (scene_row.get("content_rating") if scene_row else None) or "R"
                _dispatch_result = await _dispatcher.build_and_submit(
                    conn=conn,
                    shot_dict=shot_dict,
                    shot_id=shot_id,
                    scene_id=scene_id,
                    project_id=project_id,
                    current_prompt=current_prompt,
                    current_negative=current_negative,
                    image_filename=image_filename,
                    first_frame_path=first_frame_path,
                    file_prefix=_file_prefix,
                    shot_seconds=shot_seconds,
                    shot_steps=shot_steps,
                    shot_guidance=shot_guidance,
                    shot_seed=shot_seed,
                    shot_use_f1=shot_use_f1,
                    engine_sel=engine_sel,
                    project_video_lora=_project_wan_lora,
                    project_rating=_project_rating,
                    project_width=_project_width,
                    project_height=_project_height,
                    style_anchor=style_anchor,
                    auto_approve=auto_approve,
                    character_slug=character_slug,
                    motion_prompt=motion_prompt,
                )

                if _dispatch_result is None:
                    # Dispatcher handled the failure (marked shot as failed or skipped)
                    continue

                if _dispatch_result.get("skip_poll"):
                    # Engine handled polling, postprocessing, and completion internally
                    _completion = _dispatch_result.get("completion", {})
                    video_path = _dispatch_result.get("video_path")
                    if video_path:
                        completed_count += 1
                        completed_videos.append(video_path)
                        prev_last_frame = _completion.get("last_frame")
                        prev_character = character_slug
                    continue

                # Standard path: poll ComfyUI, postprocess, complete
                comfyui_prompt_id = _dispatch_result["prompt_id"]

                await conn.execute(
                    "UPDATE shots SET comfyui_prompt_id = $2, first_frame_path = $3 WHERE id = $1",
                    shot_id, comfyui_prompt_id, first_frame_path,
                )

                result = await poll_comfyui_completion(comfyui_prompt_id)
                gen_time = _time_inner.time() - attempt_start

                if result["status"] != "completed" or not result["output_files"]:
                    await conn.execute(
                        "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                        shot_id, f"ComfyUI {result['status']}",
                    )
                    continue

                video_filename = result["output_files"][0]
                video_path = str(COMFYUI_OUTPUT_DIR / video_filename)

                # FramePack V2V refinement — now handled by video_refinement
                # orchestrator phase (work_video_refinement). Inline disabled.
                if False and shot_engine in ("wan", "wan22") and video_path:
                    try:
                        from .framepack_refine import refine_wan_video
                        # Auto-detect kohya-format FramePack LoRA for refinement
                        _fp_lora = None
                        if character_slug:
                            for _suffix in ("_framepack_lora", "_framepack"):
                                _lp = Path(f"/opt/ComfyUI/models/loras/{character_slug}{_suffix}.safetensors")
                                if _lp.exists():
                                    try:
                                        from safetensors import safe_open
                                        with safe_open(str(_lp), framework="pt") as _sf:
                                            _k0 = list(_sf.keys())[0] if _sf.keys() else ""
                                        if _k0.startswith("lora_unet_"):
                                            _fp_lora = _lp.name
                                        else:
                                            logger.warning(f"Skipping incompatible LoRA {_lp.name} for refinement")
                                    except Exception:
                                        pass
                                    break
                        refined = await refine_wan_video(
                            wan_video_path=video_path,
                            prompt_text=current_prompt,
                            negative_text=current_negative,
                            denoise_strength=0.4,
                            total_seconds=shot_seconds,
                            steps=25,
                            seed=shot_seed,
                            guidance_scale=shot_guidance,
                            lora_name=_fp_lora,
                            output_prefix=f"{_file_prefix}_refined",
                        )
                        if refined:
                            video_path = refined
                            logger.info(f"Shot {shot_id}: FramePack V2V refinement done → {Path(refined).name}")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: V2V refinement failed: {e}, using raw Wan output")

                # Post-process all video outputs: interpolation + upscale + color grade
                # Wan gets upscale (512->1024), FramePack gets interpolation + color only
                video_path = await postprocess_video(
                    video_path, shot_engine, style_anchor,
                    interpolate=True, color_grade=True, scale_factor=2, target_fps=30,
                )

                # Record source image effectiveness for the feedback loop
                source_path = shot_dict.get("source_image_path")
                if source_path:
                    parts = source_path.replace("\\", "/").split("/")
                    if len(parts) >= 3 and parts[-2] == "images":
                        eff_slug = parts[0] if len(parts) == 3 else parts[-3]
                        try:
                            await conn.execute("""
                                INSERT INTO source_image_effectiveness
                                    (character_slug, image_name, shot_id, video_quality_score, video_engine)
                                VALUES ($1, $2, $3, NULL, $4)
                            """, eff_slug, parts[-1], shot_id, shot_engine)
                        except Exception:
                            pass

                # Persist generation params including motion tier from dispatcher
                _motion_ctx = _dispatch_result.get("motion_ctx")
                _completion = await complete_shot(
                    conn, shot_id, video_path, scene_id, project_id,
                    current_prompt, current_negative, gen_time,
                    shot_dict, auto_approve=auto_approve,
                    motion_ctx=_motion_ctx,
                )
                completed_count += 1
                completed_videos.append(video_path)
                prev_last_frame = _completion["last_frame"]
                prev_character = character_slug

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

        # Check if all shots are approved — only then assemble
        all_approved = False
        if completed_videos:
            review_counts = await conn.fetchrow("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE review_status = 'approved') as approved,
                       COUNT(*) FILTER (WHERE review_status = 'rejected') as rejected,
                       COUNT(*) FILTER (WHERE review_status = 'pending_review') as pending
                FROM shots WHERE scene_id = $1
            """, scene_id)

            all_approved = (
                review_counts["approved"] == review_counts["total"]
                and review_counts["total"] > 0
            )

            if review_counts["pending"] > 0:
                logger.info(
                    f"Scene {scene_id}: {review_counts['pending']} shots awaiting review — "
                    f"assembly deferred until all approved"
                )
                await conn.execute("""
                    UPDATE scenes SET generation_status = 'awaiting_review',
                           current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id)
            elif review_counts["rejected"] > 0 and not all_approved:
                logger.info(
                    f"Scene {scene_id}: {review_counts['rejected']} shots rejected — "
                    f"scene needs regeneration of rejected shots"
                )
                await conn.execute("""
                    UPDATE scenes SET generation_status = 'needs_regen',
                           current_generating_shot_id = NULL
                    WHERE id = $1
                """, scene_id)

        if all_approved:
            await _assemble_scene(conn, scene_id, completed_videos, shots)
        elif not completed_videos:
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
