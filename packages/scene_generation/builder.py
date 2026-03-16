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


def _resolve_content_lora_pair(
    shot_lora_name: str | None,
    project_video_lora: str | None = None,
) -> tuple[str | None, str | None, float]:
    """Resolve a shot's lora_name to content LoRA HIGH/LOW pair for Wan22 14B.

    Logic:
    1. If shot has lora_name containing '_HIGH', derive the LOW counterpart.
    2. If shot has lora_name matching a video_lora_pairs key from catalog, use that.
    3. If shot has no lora_name, fall back to project_video_lora as HIGH-only.

    Returns (content_lora_high, content_lora_low, strength).
    """
    # Use shot-level LoRA first; only fall back to project LoRA if it's
    # WAN-compatible (not a framepack/image LoRA)
    lora_name = shot_lora_name
    if not lora_name and project_video_lora:
        pv = project_video_lora.lower()
        # Skip FramePack / image-only LoRAs — they're incompatible with WAN 2.2 14B
        if "framepack" not in pv and "illustrious" not in pv and "sdxl" not in pv:
            lora_name = project_video_lora
    if not lora_name:
        return None, None, 0.85

    lora_name = lora_name.strip()

    # Pattern 1: Already a _HIGH filename — derive _LOW
    if "_HIGH" in lora_name:
        high = lora_name
        low = lora_name.replace("_HIGH", "_LOW")
        # Check LOW exists
        from pathlib import Path
        low_path = Path(f"/opt/ComfyUI/models/loras/{low}")
        if not low_path.exists():
            low_path = Path(f"/opt/ComfyUI/models/loras/wan22_nsfw/{low}")
        if not low_path.exists():
            low = None  # HIGH-only, no LOW counterpart
        return high, low, 0.85

    # Pattern 2: A _LOW filename — derive _HIGH
    if "_LOW" in lora_name:
        low = lora_name
        high = lora_name.replace("_LOW", "_HIGH")
        from pathlib import Path
        high_path = Path(f"/opt/ComfyUI/models/loras/{high}")
        if not high_path.exists():
            high_path = Path(f"/opt/ComfyUI/models/loras/wan22_nsfw/{high}")
        if not high_path.exists():
            high = None
        return high, low, 0.85

    # Pattern 3: Catalog key name (e.g. "cowgirl") — look up in catalog
    try:
        from .catalog_loader import load_catalog
        catalog = load_catalog()
        if catalog:
            pairs = catalog.get("video_lora_pairs", {})

            # Direct match in video_lora_pairs
            if lora_name in pairs:
                pair = pairs[lora_name]
                if pair.get("single"):
                    return pair["single"], pair["single"], 0.85
                return pair.get("high"), pair.get("low"), 0.85

            # Check action_presets — follow video_lora reference to video_lora_pairs
            presets = catalog.get("action_presets", {})
            if lora_name in presets:
                preset = presets[lora_name]
                vl_key = preset.get("video_lora")
                if vl_key and vl_key in pairs:
                    pair = pairs[vl_key]
                    strength = preset.get("video_lora_strength", 0.85)
                    if pair.get("single"):
                        return pair["single"], pair["single"], strength
                    return pair.get("high"), pair.get("low"), strength
                # Preset exists but video_lora isn't in video_lora_pairs —
                # it's a motion-only preset (e.g. idle, walking, talking).
                # No content LoRA needed; motion_lora_matcher handles it.
                return None, None, 0.85

            # Check video_motion_loras — these are motion LoRAs, not content
            motion_loras = catalog.get("video_motion_loras", {})
            if lora_name in motion_loras:
                return None, None, 0.85
    except Exception:
        pass

    # Pattern 4: Generic single LoRA (e.g. project-level video_lora) — apply to high model only
    # Only if the file actually exists on disk; otherwise return None to avoid
    # passing bogus strings to ComfyUI
    from pathlib import Path as _P4
    if (_P4(f"/opt/ComfyUI/models/loras/{lora_name}").exists()
            or _P4(f"/opt/ComfyUI/models/loras/{lora_name}.safetensors").exists()):
        return lora_name, None, 0.85
    return None, None, 0.85

from .framepack import build_framepack_workflow, _submit_comfyui_workflow
from .ltx_video import build_ltx_workflow, build_ltxv_looping_workflow, _submit_comfyui_workflow as _submit_ltx_workflow
from .wan_video import build_wan_t2v_workflow, build_wan22_workflow, build_wan22_14b_i2v_workflow, build_dasiwa_i2v_workflow, check_dasiwa_ready, _submit_comfyui_workflow as _submit_wan_workflow
from .video_config import get_engine_defaults
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

# Stubs for scene_review.py (these were never defined — latent bug)
_QUALITY_GATES = [{"threshold": 0.6}]
_MAX_RETRIES = 3

logger = logging.getLogger(__name__)

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
) -> dict:
    """Generate a long WAN 2.2 14B video by chaining multiple I2V segments.

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
        f"Roll-forward: {target_seconds}s target → {num_segments} segments × "
        f"{segment_seconds}s, crossfade={crossfade_seconds}s"
    )

    num_frames_per_seg = max(9, int(segment_seconds * fps) + 1)
    current_source = ref_image
    segment_paths = []

    for seg_idx in range(num_segments):
        seg_prefix = f"{output_prefix}_seg{seg_idx:02d}"
        seg_seed = seed + seg_idx

        _rf_split = split_steps if split_steps is not None else (steps // 2)
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
            _ckpt = "waiIllustriousSDXL_v160.safetensors"
            try:
                _style_row = await conn.fetchrow(
                    """SELECT gs.checkpoint_model FROM projects p
                       JOIN generation_styles gs ON p.default_style = gs.style_name
                       WHERE p.id = $1""", project_id)
                if _style_row and _style_row["checkpoint_model"]:
                    _ckpt = _style_row["checkpoint_model"]
                    if not _ckpt.endswith(".safetensors"):
                        _ckpt += ".safetensors"
            except Exception:
                pass

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
                if character_slug and shot_engine in ("framepack", "framepack_f1"):
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
                        ckpt = "waiIllustriousSDXL_v160.safetensors"
                        try:
                            style_row = await conn.fetchrow(
                                """SELECT gs.checkpoint_model FROM projects p
                                   JOIN generation_styles gs ON p.default_style = gs.style_name
                                   WHERE p.id = $1""", project_id)
                            if style_row and style_row["checkpoint_model"]:
                                ckpt = style_row["checkpoint_model"]
                                if not ckpt.endswith(".safetensors"):
                                    ckpt += ".safetensors"
                        except Exception:
                            pass

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
                    _has_content_lora = bool(shot_dict.get("lora_name") or shot_dict.get("image_lora"))
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
                        # Use state-aware selection when NSM states exist (Phase 4)
                        cross_scene_frame = None
                        if character_slug and project_id:
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
                            # Priority 3: fall back to auto-assigned source image
                            source_path = shot_dict.get("source_image_path")
                            if not source_path:
                                if shot_engine in ("wan22", "ltx", "ltx_long"):
                                    # Engines that support T2V: graceful fallback (no ref image)
                                    logger.info(f"Shot {shot_id}: {shot_engine} no source image → T2V fallback")
                                elif shot_engine == "wan22_14b":
                                    # 14B is I2V only — generate a keyframe on the fly
                                    logger.warning(f"Shot {shot_id}: wan22_14b needs source image, generating keyframe")
                                    try:
                                        from .composite_image import generate_simple_keyframe
                                        _ckpt = "waiIllustriousSDXL_v160.safetensors"
                                        try:
                                            _sr = await conn.fetchrow(
                                                "SELECT gs.checkpoint_model FROM projects p "
                                                "JOIN generation_styles gs ON p.default_style = gs.style_name "
                                                "WHERE p.id = $1", project_id)
                                            if _sr and _sr["checkpoint_model"]:
                                                _ckpt = _sr["checkpoint_model"]
                                                if not _ckpt.endswith(".safetensors"):
                                                    _ckpt += ".safetensors"
                                        except Exception:
                                            pass
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

                # Dispatch to video engine
                if shot_engine == "reference_v2v":
                    # V2V style transfer: use source video clip directly through FramePack V2V
                    _ref_video = shot_dict.get("source_video_path")
                    if not _ref_video or not Path(_ref_video).exists():
                        logger.error(f"Shot {shot_id}: reference_v2v but no source_video_path")
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, "No source video clip available for reference_v2v",
                        )
                        continue

                    # Auto-detect kohya-format FramePack LoRA for the character
                    # Only attach LoRAs that use lora_unet_ key format (kohya/comfyui)
                    _fp_lora = None
                    if character_slug:
                        for _suffix in ("_framepack_lora", "_framepack"):
                            _lp = Path(f"/opt/ComfyUI/models/loras/{character_slug}{_suffix}.safetensors")
                            if _lp.exists():
                                # Validate LoRA format — must be kohya/comfyui format
                                try:
                                    from safetensors import safe_open
                                    with safe_open(str(_lp), framework="pt") as _sf:
                                        _k0 = list(_sf.keys())[0] if _sf.keys() else ""
                                    if _k0.startswith("lora_unet_"):
                                        _fp_lora = _lp.name
                                    else:
                                        logger.warning(f"Skipping incompatible LoRA {_lp.name} (not kohya format, key: {_k0[:60]})")
                                except Exception as _le:
                                    logger.warning(f"Could not validate LoRA {_lp.name}: {_le}")
                                break

                    from .framepack_refine import refine_wan_video
                    attempt_start = _time_inner.time()
                    refined = await refine_wan_video(
                        wan_video_path=_ref_video,
                        prompt_text=current_prompt,
                        negative_text=current_negative,
                        denoise_strength=0.45,
                        total_seconds=shot_seconds,
                        steps=25,
                        seed=shot_seed,
                        guidance_scale=shot_guidance,
                        lora_name=_fp_lora,
                        output_prefix=_file_prefix,
                    )
                    gen_time = _time_inner.time() - attempt_start

                    if not refined:
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, "FramePack V2V refinement returned no output",
                        )
                        continue

                    video_path = refined
                    logger.info(f"Shot {shot_id}: reference_v2v done in {gen_time:.0f}s → {Path(refined).name}")

                    # Post-process: interpolation + color grade only (no upscale — already 544x704)
                    try:
                        from .video_postprocess import postprocess_wan_video
                        _color_style = "anime"
                        if style_anchor and "anthro" in style_anchor:
                            _color_style = "anthro"
                        elif style_anchor and "photorealistic" in style_anchor:
                            _color_style = "photorealistic"
                        processed = await postprocess_wan_video(
                            video_path,
                            upscale=False,
                            interpolate=True,
                            color_grade=True,
                            target_fps=30,
                            color_style=_color_style,
                        )
                        if processed:
                            video_path = processed
                            logger.info(f"Shot {shot_id}: post-processed → {Path(processed).name}")
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: post-processing failed: {e}, using raw output")

                    last_frame = await extract_last_frame(video_path)

                    completed_count += 1
                    completed_videos.append(video_path)
                    prev_last_frame = last_frame
                    prev_character = character_slug

                    if auto_approve:
                        _review = 'approved'
                    else:
                        _review, _qc_score = await _run_vision_qc(conn, shot_id, video_path, shot_dict)
                    await conn.execute("""
                        UPDATE shots SET status = 'completed', output_video_path = $2,
                               last_frame_path = $3, generation_time_seconds = $4,
                               review_status = $5
                        WHERE id = $1
                    """, shot_id, video_path, last_frame, gen_time, _review)

                    if character_slug and last_frame and project_id:
                        try:
                            await _save_continuity_frame(
                                conn, project_id, character_slug,
                                scene_id, shot_id, last_frame,
                                scene_number=scene_number,
                                shot_number=shot_dict.get("shot_number"),
                            )
                        except Exception as e:
                            logger.warning(f"Shot {shot_id}: failed to save continuity frame: {e}")

                    logger.info(f"Shot {shot_id}: generated in {gen_time:.0f}s → {_review}")

                    await event_bus.emit(SHOT_GENERATED, {
                        "shot_id": str(shot_id),
                        "scene_id": str(scene_id),
                        "project_id": project_id,
                        "video_engine": shot_engine,
                        "video_path": video_path,
                        "last_frame_path": last_frame,
                        "generation_time_seconds": gen_time,
                        "auto_approve": auto_approve,
                    })
                    continue

                elif shot_engine == "wan22":
                    _wan22_cfg = get_engine_defaults("wan22_14b")
                    fps = _wan22_cfg.get("fps", 16)
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    import hashlib as _hashlib
                    if not shot_seed:
                        _scene_seed_bytes = _hashlib.sha256(str(scene_id).encode()).digest()
                        _scene_base_seed = int.from_bytes(_scene_seed_bytes[:8], "big") % (2**63)
                        shot_seed = _scene_base_seed + (shot_dict.get("shot_number", 0) or 0)
                    wan_cfg = max(shot_guidance, 7.5)  # higher CFG keeps prompt control over LoRA
                    wan_w = _wan22_cfg.get("width", 480)
                    wan_h = _wan22_cfg.get("height", 720)
                    if _project_width and _project_height and _project_width > _project_height:
                        wan_w, wan_h = 768, 512
                    # Get LoRA from engine selector (set by _find_wan_lora)
                    _wan22_lora = engine_sel.lora_name
                    _wan22_lora_str = engine_sel.lora_strength
                    # I2V mode: pass ref_image if we have a source image
                    _wan22_ref = image_filename if image_filename else None
                    logger.info(
                        f"Shot {shot_id}: Wan22 dims={wan_w}x{wan_h} lora={_wan22_lora} "
                        f"ref_image={_wan22_ref is not None} seed={shot_seed} cfg={wan_cfg} frames={num_frames}"
                    )
                    workflow, prefix = build_wan22_workflow(
                        prompt_text=current_prompt, num_frames=num_frames, fps=fps,
                        steps=shot_steps, seed=shot_seed, cfg=wan_cfg,
                        width=wan_w, height=wan_h,
                        negative_text=current_negative,
                        output_prefix=_file_prefix,
                        lora_name=_wan22_lora,
                        lora_strength=_wan22_lora_str,
                        ref_image=_wan22_ref,
                    )
                    comfyui_prompt_id = _submit_wan_workflow(workflow)
                elif shot_engine == "wan22_14b":
                    # Wan 2.2 14B I2V — highest quality, requires source image
                    if not image_filename:
                        logger.error(f"Shot {shot_id}: wan22_14b requires a source image but none available")
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, "wan22_14b requires a source image (I2V only)",
                        )
                        continue
                    _14b_cfg = get_engine_defaults("wan22_14b")
                    fps = _14b_cfg.get("fps", 16)
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    import hashlib as _hashlib
                    if not shot_seed:
                        _scene_seed_bytes = _hashlib.sha256(str(scene_id).encode()).digest()
                        _scene_base_seed = int.from_bytes(_scene_seed_bytes[:8], "big") % (2**63)
                        shot_seed = _scene_base_seed + (shot_dict.get("shot_number", 0) or 0)
                    wan_w = _14b_cfg.get("width", 480)
                    wan_h = _14b_cfg.get("height", 720)
                    if _project_width and _project_height and _project_width > _project_height:
                        wan_w, wan_h = wan_h, wan_w
                    # Get motion LoRA — prefer engine selector, fall back to catalog matcher
                    _14b_motion_lora = engine_sel.motion_loras[0] if engine_sel.motion_loras else None
                    _14b_motion_str = 0.8
                    if not _14b_motion_lora:
                        from .motion_lora_matcher import match_motion_lora
                        _ml_prompt = motion_prompt or ""
                        _ml_desc = shot_dict.get("scene_description") or shot_dict.get("description") or ""
                        _ml_rating = (scene_row.get("content_rating") if scene_row else None) or "R"
                        _14b_motion_lora, _14b_motion_str = match_motion_lora(
                            motion_prompt=_ml_prompt, description=_ml_desc, content_rating=_ml_rating
                        )
                    # Resolve content LoRA HIGH/LOW pair from shot or project
                    # Skip project fallback for trailer intros/interactions —
                    # they test character fidelity, not content LoRAs
                    _shot_lora = shot_dict.get("lora_name")
                    _trailer_role = shot_dict.get("trailer_role") or ""
                    _skip_project_lora = _trailer_role in ("character_intro", "interaction")
                    _14b_clh, _14b_cll, _14b_cl_str = _resolve_content_lora_pair(
                        _shot_lora, None if _skip_project_lora else project_video_lora
                    )
                    if _14b_clh or _14b_cll:
                        logger.info(
                            f"Shot {shot_id}: content LoRA HIGH={_14b_clh} LOW={_14b_cll} "
                            f"str={_14b_cl_str} (from {'shot' if _shot_lora else 'project'})"
                        )
                    # Dynamic motion intensity — classify shot and apply params
                    _motion_tier = classify_motion_intensity(shot_dict)
                    _motion_params = get_motion_params(_motion_tier)
                    _14b_use_lightx2v = _motion_params.use_lightx2v
                    _14b_steps = _motion_params.total_steps
                    _14b_split = _motion_params.split_steps
                    _14b_cfg = _motion_params.cfg
                    _14b_cl_str = _motion_params.content_lora_strength
                    # Override with learned effectiveness data if available
                    if _14b_clh:
                        _eff_lora_key = _14b_clh.split("/")[-1].replace(".safetensors", "")
                        import re as _re
                        _eff_lora_key = _re.sub(r"_(HIGH|LOW)$", "", _eff_lora_key, flags=_re.IGNORECASE)
                        try:
                            from .lora_effectiveness import recommended_params as _eff_params
                            _eff = await _eff_params(_eff_lora_key, character_slug)
                            if _eff and _eff.get("sample_count", 0) >= 2:
                                if _eff.get("best_lora_strength"):
                                    _14b_cl_str = _eff["best_lora_strength"]
                                if _eff.get("best_motion_tier") and not shot_dict.get("motion_tier"):
                                    _motion_tier = _eff["best_motion_tier"]
                                    _motion_params = get_motion_params(_motion_tier)
                                    _14b_use_lightx2v = _motion_params.use_lightx2v
                                    _14b_steps = _motion_params.total_steps
                                    _14b_split = _motion_params.split_steps
                                    _14b_cfg = _motion_params.cfg
                                logger.info(
                                    f"Shot {shot_id}: LoRA effectiveness override — "
                                    f"key={_eff_lora_key} str={_14b_cl_str} "
                                    f"tier={_motion_tier} avg_q={_eff.get('avg_quality', '?')} "
                                    f"samples={_eff['sample_count']}"
                                )
                        except Exception as _eff_err:
                            logger.debug(f"Shot {shot_id}: LoRA effectiveness lookup failed: {_eff_err}")
                    # Inject counter-motion cues into prompt if available
                    _counter_motion = get_counter_motion(_shot_lora)
                    if _counter_motion and _counter_motion not in current_prompt:
                        current_prompt = f"{current_prompt}, {_counter_motion}"
                        logger.info(f"Shot {shot_id}: counter-motion injected: {_counter_motion[:60]}")

                    # --- LoRA motion description injection ---
                    # Append explicit motion cues from catalog so WAN knows
                    # what motion the LoRA is supposed to produce
                    from .motion_intensity import get_motion_description
                    _motion_desc = get_motion_description(_shot_lora) if _shot_lora else None
                    if not _motion_desc and _14b_clh:
                        _motion_desc = get_motion_description(_14b_clh)
                    if _motion_desc and _motion_desc not in current_prompt:
                        current_prompt = f"{current_prompt}, {_motion_desc}"
                        logger.info(f"Shot {shot_id}: motion_description injected: {_motion_desc[:80]}")

                    # --- LoRA type enforcement ---
                    # Cap content LoRA strength when character has a trained LoRA
                    # to prevent content/pose LoRAs from overriding character identity
                    from .motion_intensity import get_lora_type, cap_content_strength
                    _has_char_lora = False
                    if character_slug:
                        from pathlib import Path as _LP
                        for _suf in ("_ill_lora", "_xl_lora", "_lora"):
                            if (_LP(f"/opt/ComfyUI/models/loras/{character_slug}{_suf}.safetensors").exists()):
                                _has_char_lora = True
                                break
                    _content_lora_type = get_lora_type(_14b_clh) if _14b_clh else None
                    _motion_lora_type = get_lora_type(_14b_motion_lora) if _14b_motion_lora else None
                    _has_pose = _content_lora_type == "pose"
                    if _14b_clh and _has_char_lora:
                        _14b_cl_str = cap_content_strength(
                            _14b_clh, _14b_cl_str,
                            has_character_lora=True,
                            has_pose_lora=_has_pose,
                        )
                    # Log the type-aware decision
                    if _content_lora_type or _motion_lora_type:
                        logger.info(
                            f"Shot {shot_id}: lora_types content={_content_lora_type} "
                            f"motion={_motion_lora_type} char_lora={_has_char_lora} "
                            f"final_str={_14b_cl_str}"
                        )

                    logger.info(
                        f"Shot {shot_id}: motion_tier={_motion_tier} "
                        f"steps={_14b_steps} split={_14b_split} cfg={_14b_cfg} "
                        f"lora_str={_14b_cl_str} lightx2v={_14b_use_lightx2v}"
                    )
                    _WAN_SEGMENT_SECONDS = 5.0
                    if shot_seconds > _WAN_SEGMENT_SECONDS:
                        # Pattern C: roll-forward for long shots
                        logger.info(
                            f"Shot {shot_id}: Wan22-14B ROLL-FORWARD {shot_seconds}s "
                            f"({int(shot_seconds / _WAN_SEGMENT_SECONDS + 0.5)} segments) "
                            f"dims={wan_w}x{wan_h} ref={image_filename}"
                        )
                        rf_result = await roll_forward_wan_shot(
                            prompt_text=current_prompt,
                            ref_image=image_filename,
                            target_seconds=shot_seconds,
                            negative_text=current_negative,
                            segment_seconds=_WAN_SEGMENT_SECONDS,
                            crossfade_seconds=0.3,
                            width=wan_w, height=wan_h,
                            fps=fps, steps=_14b_steps,
                            split_steps=_14b_split, cfg=_14b_cfg,
                            seed=shot_seed,
                            output_prefix=_file_prefix,
                            use_lightx2v=_14b_use_lightx2v,
                            motion_lora=_14b_motion_lora,
                            motion_lora_strength=_14b_motion_str,
                            content_lora_high=_14b_clh,
                            content_lora_low=_14b_cll,
                            content_lora_strength=_14b_cl_str,
                        )
                        if rf_result["video_path"]:
                            # Skip normal ComfyUI poll — roll-forward handles it internally
                            video_path = rf_result["video_path"]
                            # Post-process the stitched video (upscale + color grade)
                            try:
                                from .video_postprocess import postprocess_wan_video
                                _color_style = "anime"
                                if style_anchor and "anthro" in style_anchor:
                                    _color_style = "anthro"
                                elif style_anchor and "photorealistic" in style_anchor:
                                    _color_style = "photorealistic"
                                _pp = await postprocess_wan_video(
                                    video_path, upscale=True, interpolate=True,
                                    color_grade=True, scale_factor=2, target_fps=30,
                                    color_style=_color_style,
                                )
                                if _pp:
                                    video_path = _pp
                                    logger.info(f"Shot {shot_id}: roll-forward post-processed → {Path(_pp).name}")
                            except Exception as _pp_err:
                                logger.warning(f"Shot {shot_id}: roll-forward postprocess failed: {_pp_err}")
                            last_frame = await extract_last_frame(video_path)
                            gen_time = _time_inner.time() - attempt_start
                            logger.info(
                                f"Shot {shot_id}: roll-forward done, "
                                f"{rf_result['segment_count']} segs, "
                                f"{rf_result['total_duration']:.1f}s"
                            )
                            # Jump past the normal poll/output block
                            completed_count += 1
                            completed_videos.append(video_path)
                            prev_last_frame = last_frame
                            prev_character = character_slug
                            if auto_approve:
                                _review = 'approved'
                            else:
                                _review, _qc_score = await _run_vision_qc(conn, shot_id, video_path, shot_dict)
                            await conn.execute("""
                                UPDATE shots SET status = 'completed', output_video_path = $2,
                                       last_frame_path = $3, generation_time_seconds = $4,
                                       review_status = $5,
                                       motion_tier = $6, guidance_scale = $7, steps = $8,
                                       gen_split_steps = $9, gen_lightx2v = $10,
                                       content_lora_high = $11, content_lora_low = $12
                                WHERE id = $1
                            """, shot_id, video_path, last_frame, gen_time, _review,
                                _motion_tier, _14b_cfg, _14b_steps,
                                _14b_split, _14b_use_lightx2v,
                                _14b_clh, _14b_cll)
                            if character_slug and last_frame and project_id:
                                try:
                                    await _save_continuity_frame(
                                        conn, project_id, character_slug,
                                        scene_id, shot_id, last_frame,
                                        scene_number=scene_number,
                                        shot_number=shot_dict.get("shot_number"),
                                    )
                                except Exception as e:
                                    logger.warning(f"Shot {shot_id}: continuity save failed: {e}")
                            continue
                        else:
                            await conn.execute(
                                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                                shot_id, "Roll-forward failed — no segments completed",
                            )
                            continue
                    logger.info(
                        f"Shot {shot_id}: Wan22-14B I2V dims={wan_w}x{wan_h} "
                        f"ref_image={image_filename} motion_lora={_14b_motion_lora} "
                        f"content_high={_14b_clh} content_low={_14b_cll} "
                        f"seed={shot_seed} steps={_14b_steps} cfg={_14b_cfg} "
                        f"tier={_motion_tier} frames={num_frames}"
                    )
                    workflow, prefix = build_wan22_14b_i2v_workflow(
                        prompt_text=current_prompt,
                        ref_image=image_filename,
                        width=wan_w, height=wan_h,
                        num_frames=num_frames, fps=fps,
                        total_steps=_14b_steps,
                        split_steps=_14b_split,
                        cfg=_14b_cfg,
                        seed=shot_seed,
                        negative_text=current_negative,
                        output_prefix=_file_prefix,
                        use_lightx2v=_14b_use_lightx2v,
                        motion_lora=_14b_motion_lora,
                        motion_lora_strength=_14b_motion_str,
                        content_lora_high=_14b_clh,
                        content_lora_low=_14b_cll,
                        content_lora_strength=_14b_cl_str,
                    )
                    # Dedup: skip if this source image is already in ComfyUI queue
                    from .scene_comfyui import is_source_already_queued
                    _existing = is_source_already_queued(image_filename) if image_filename else None
                    if _existing:
                        logger.warning(f"Shot {shot_id}: source {image_filename} already queued (prompt={_existing}), skipping duplicate")
                        continue
                    comfyui_prompt_id = _submit_wan_workflow(workflow)
                elif shot_engine == "dasiwa":
                    # DaSiWa TastySin v8 — pre-baked distillation, 4 steps, no lightx2v needed
                    if not image_filename:
                        logger.error(f"Shot {shot_id}: dasiwa requires a source image (I2V only)")
                        await conn.execute(
                            "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                            shot_id, "dasiwa requires a source image (I2V only)",
                        )
                        continue
                    _dasi_ok, _dasi_msg = check_dasiwa_ready()
                    if not _dasi_ok:
                        logger.warning(f"Shot {shot_id}: {_dasi_msg}, falling back to wan22_14b")
                        shot_engine = "wan22_14b"
                        # Fall through to wan22_14b branch on next iteration
                        # For now, just use wan22_14b directly
                        _14b_cfg_d = get_engine_defaults("wan22_14b_dasiwa")
                        fps = _14b_cfg_d.get("fps", 16)
                        num_frames = max(9, int(shot_seconds * fps) + 1)
                        wan_w = _14b_cfg_d.get("width", 480)
                        wan_h = _14b_cfg_d.get("height", 720)
                        if _project_width and _project_height and _project_width > _project_height:
                            wan_w, wan_h = wan_h, wan_w
                        workflow, prefix = build_wan22_14b_i2v_workflow(
                            prompt_text=current_prompt, ref_image=image_filename,
                            width=wan_w, height=wan_h, num_frames=num_frames, fps=fps,
                            total_steps=6, split_steps=3, cfg=3.5, seed=shot_seed,
                            negative_text=current_negative, output_prefix=_file_prefix,
                            use_lightx2v=False,
                        )
                        comfyui_prompt_id = _submit_wan_workflow(workflow)
                    else:
                        _dasi_cfg = get_engine_defaults("wan22_14b_dasiwa")
                        fps = _dasi_cfg.get("fps", 16)
                        num_frames = max(9, int(shot_seconds * fps) + 1)
                        wan_w = _dasi_cfg.get("width", 480)
                        wan_h = _dasi_cfg.get("height", 720)
                        if _project_width and _project_height and _project_width > _project_height:
                            wan_w, wan_h = wan_h, wan_w
                        import hashlib as _hashlib
                        if not shot_seed:
                            _scene_seed_bytes = _hashlib.sha256(str(scene_id).encode()).digest()
                            _scene_base_seed = int.from_bytes(_scene_seed_bytes[:8], "big") % (2**63)
                            shot_seed = _scene_base_seed + (shot_dict.get("shot_number", 0) or 0)
                        _shot_lora = shot_dict.get("lora_name")
                        _dasi_clh, _dasi_cll, _dasi_cl_str = _resolve_content_lora_pair(
                            _shot_lora, project_video_lora
                        )
                        _14b_motion_lora = engine_sel.motion_loras[0] if engine_sel.motion_loras else None
                        if not _14b_motion_lora:
                            from .motion_lora_matcher import match_motion_lora
                            _ml_prompt = motion_prompt or ""
                            _ml_desc = shot_dict.get("scene_description") or shot_dict.get("description") or ""
                            _ml_rating = (scene_row.get("content_rating") if scene_row else None) or "R"
                            _14b_motion_lora, _14b_motion_str_dasi = match_motion_lora(
                                motion_prompt=_ml_prompt, description=_ml_desc, content_rating=_ml_rating
                            )
                        logger.info(
                            f"Shot {shot_id}: DaSiWa I2V dims={wan_w}x{wan_h} "
                            f"ref={image_filename} content_high={_dasi_clh} "
                            f"content_low={_dasi_cll} motion={_14b_motion_lora}"
                        )
                        workflow, prefix = build_dasiwa_i2v_workflow(
                            prompt_text=current_prompt,
                            ref_image=image_filename,
                            width=wan_w, height=wan_h,
                            num_frames=num_frames, fps=fps,
                            seed=shot_seed,
                            negative_text=current_negative,
                            output_prefix=_file_prefix,
                            motion_lora=_14b_motion_lora,
                            content_lora_high=_dasi_clh,
                            content_lora_low=_dasi_cll,
                            content_lora_strength=min(_dasi_cl_str, 0.6),
                        )
                        comfyui_prompt_id = _submit_wan_workflow(workflow)
                elif shot_engine == "wan":
                    fps = 16
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    # Use scene-level seed for style consistency across shots
                    # Derive per-shot seed: scene_seed + shot_number
                    import hashlib as _hashlib
                    if not shot_seed:
                        _scene_seed_bytes = _hashlib.sha256(str(scene_id).encode()).digest()
                        _scene_base_seed = int.from_bytes(_scene_seed_bytes[:8], "big") % (2**63)
                        shot_seed = _scene_base_seed + (shot_dict.get("shot_number", 0) or 0)
                    # Higher CFG for better style compliance
                    wan_cfg = max(shot_guidance, 7.5)
                    # Map project resolution to Wan-safe dims (must be multiples of 16)
                    # Wan native is 480x720; scale proportionally for landscape/portrait
                    wan_w, wan_h = 480, 720  # default portrait
                    if _project_width and _project_height and _project_width > _project_height:
                        wan_w, wan_h = 720, 480  # landscape
                    logger.info(f"Shot {shot_id}: Wan dims={wan_w}x{wan_h} (project={_project_width}x{_project_height})")
                    workflow, prefix = build_wan_t2v_workflow(
                        prompt_text=current_prompt, num_frames=num_frames, fps=fps,
                        steps=shot_steps, seed=shot_seed, cfg=wan_cfg,
                        width=wan_w, height=wan_h,
                        use_gguf=True,
                        negative_text=current_negative,
                        output_prefix=_file_prefix,
                    )
                    logger.info(f"Shot {shot_id}: Wan seed={shot_seed} cfg={wan_cfg} frames={num_frames}")
                    comfyui_prompt_id = _submit_wan_workflow(workflow)
                elif shot_engine == "ltx_long":
                    # LTXVLoopingSampler — Pattern 3 long-shot engine (30-60s+)
                    _ltx_cfg = get_engine_defaults("ltx_long")
                    fps = _ltx_cfg.get("fps", 24)
                    num_frames = max(25, int(shot_seconds * fps) + 1)
                    _ltx_tile_size = _ltx_cfg.get("temporal_tile_size", 80)
                    _ltx_overlap = _ltx_cfg.get("temporal_overlap", 24)
                    _ltx_overlap_cond = _ltx_cfg.get("temporal_overlap_cond_strength", 0.5)
                    _ltx_guiding = _ltx_cfg.get("guiding_strength", 1.0)
                    _ltx_cond_img = _ltx_cfg.get("cond_image_strength", 1.0)
                    _ltx_adain = _ltx_cfg.get("adain_factor", 0.0)
                    wan_w, wan_h = 512, 320
                    if _project_width and _project_height and _project_width > _project_height:
                        wan_w, wan_h = 512, 320  # LTX landscape
                    else:
                        wan_w, wan_h = 320, 512  # LTX portrait
                    logger.info(
                        f"Shot {shot_id}: LTX_LONG dims={wan_w}x{wan_h} "
                        f"tile_size={_ltx_tile_size} overlap={_ltx_overlap} "
                        f"frames={num_frames} (~{num_frames/fps:.1f}s @ {fps}fps)"
                    )
                    workflow, prefix = build_ltxv_looping_workflow(
                        prompt_text=current_prompt,
                        width=wan_w, height=wan_h,
                        num_frames=num_frames, fps=fps,
                        steps=shot_steps, seed=shot_seed,
                        negative_text=current_negative,
                        image_path=image_filename if image_filename else None,
                        lora_name=shot_dict.get("lora_name"),
                        lora_strength=shot_dict.get("lora_strength", 0.8),
                        output_prefix=_file_prefix,
                        temporal_tile_size=_ltx_tile_size,
                        temporal_overlap=_ltx_overlap,
                        temporal_overlap_cond_strength=_ltx_overlap_cond,
                        guiding_strength=_ltx_guiding,
                        cond_image_strength=_ltx_cond_img,
                        adain_factor=_ltx_adain,
                    )
                    comfyui_prompt_id = _submit_ltx_workflow(workflow)
                elif shot_engine == "ltx":
                    fps = 24
                    num_frames = max(9, int(shot_seconds * fps) + 1)
                    # Use LoRA from engine selector (e.g. rina_suzuki_ltx.safetensors)
                    _ltx_lora = engine_sel.lora_name
                    _ltx_lora_str = engine_sel.lora_strength
                    logger.info(f"Shot {shot_id}: LTX lora={_ltx_lora} strength={_ltx_lora_str}")
                    workflow, prefix = build_ltx_workflow(
                        prompt_text=current_prompt,
                        image_path=image_filename if image_filename else None,
                        num_frames=num_frames, fps=fps, steps=shot_steps,
                        seed=shot_seed,
                        lora_name=_ltx_lora,
                        lora_strength=_ltx_lora_str,
                    )
                    comfyui_prompt_id = _submit_ltx_workflow(workflow)
                else:
                    # Dedup: skip if this source image is already in ComfyUI queue
                    from .scene_comfyui import is_source_already_queued
                    _existing = is_source_already_queued(image_filename) if image_filename else None
                    if _existing:
                        logger.warning(f"Shot {shot_id}: source {image_filename} already queued (prompt={_existing}), skipping duplicate")
                        continue

                    use_f1 = shot_engine == "framepack_f1" or shot_use_f1
                    workflow_data, sampler_node_id, prefix = build_framepack_workflow(
                        prompt_text=current_prompt, image_path=image_filename,
                        total_seconds=shot_seconds, steps=shot_steps, use_f1=use_f1,
                        seed=shot_seed, negative_text=current_negative,
                        gpu_memory_preservation=6.0, guidance_scale=shot_guidance,
                        output_prefix=_file_prefix,
                    )
                    comfyui_prompt_id = _submit_comfyui_workflow(workflow_data["prompt"])

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

                # FramePack V2V refinement for Wan shots (2.1 and 2.2)
                # DISABLED: doubles GPU time per shot and floods ComfyUI queue
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
                # Wan gets upscale (512→1024), FramePack gets interpolation + color only
                try:
                    from .video_postprocess import postprocess_wan_video
                    do_upscale = shot_engine in ("wan", "wan22", "wan22_14b")  # Wan is 512p, needs upscale
                    # Style-aware color grading based on checkpoint
                    _color_style = "anime"
                    if style_anchor and "anthro" in style_anchor:
                        _color_style = "anthro"
                    elif style_anchor and "photorealistic" in style_anchor:
                        _color_style = "photorealistic"
                    processed = await postprocess_wan_video(
                        video_path,
                        upscale=do_upscale,
                        interpolate=True,
                        color_grade=True,
                        scale_factor=2,
                        target_fps=30,
                        color_style=_color_style,
                    )
                    if processed:
                        video_path = processed
                        logger.info(f"Shot {shot_id}: post-processed → {Path(processed).name}")
                except Exception as e:
                    logger.warning(f"Shot {shot_id}: post-processing failed: {e}, using raw output")

                last_frame = await extract_last_frame(video_path)

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

                completed_count += 1
                completed_videos.append(video_path)
                prev_last_frame = last_frame
                prev_character = character_slug

                if auto_approve:
                    _review = 'approved'
                else:
                    _review, _qc_score = await _run_vision_qc(conn, shot_id, video_path, shot_dict)
                # Persist generation params including motion tier
                _motion_ctx = {
                    "tier": locals().get("_motion_tier"),
                    "cfg": locals().get("_14b_cfg"),
                    "steps": locals().get("_14b_steps"),
                    "split": locals().get("_14b_split"),
                    "lightx2v": locals().get("_14b_use_lightx2v"),
                    "clh": locals().get("_14b_clh"),
                    "cll": locals().get("_14b_cll"),
                }
                await conn.execute("""
                    UPDATE shots SET status = 'completed', output_video_path = $2,
                           last_frame_path = $3, generation_time_seconds = $4,
                           review_status = $5,
                           motion_tier = $6, guidance_scale = $7, steps = $8,
                           gen_split_steps = $9, gen_lightx2v = $10,
                           content_lora_high = $11, content_lora_low = $12
                    WHERE id = $1
                """, shot_id, video_path, last_frame, gen_time, _review,
                    _motion_ctx["tier"], _motion_ctx["cfg"], _motion_ctx["steps"],
                    _motion_ctx["split"], _motion_ctx["lightx2v"],
                    _motion_ctx["clh"], _motion_ctx["cll"])

                # Save continuity frame for cross-scene reuse
                if character_slug and last_frame and project_id:
                    try:
                        await _save_continuity_frame(
                            conn, project_id, character_slug,
                            scene_id, shot_id, last_frame,
                            scene_number=scene_number,
                            shot_number=shot_dict.get("shot_number"),
                        )
                        logger.info(
                            f"Shot {shot_id}: saved continuity frame for '{character_slug}' "
                            f"(scene {scene_number})"
                        )
                    except Exception as e:
                        logger.warning(f"Shot {shot_id}: failed to save continuity frame: {e}")

                logger.info(f"Shot {shot_id}: generated in {gen_time:.0f}s → {_review}")

                await event_bus.emit(SHOT_GENERATED, {
                    "shot_id": str(shot_id),
                    "scene_id": str(scene_id),
                    "project_id": project_id,
                    "character_slug": character_slug,
                    "video_engine": shot_engine,
                    "generation_time": gen_time,
                    "video_path": video_path,
                    "last_frame_path": last_frame,
                    "motion_tier": _motion_ctx.get("tier") if isinstance(locals().get("_motion_ctx"), dict) else None,
                    "lora_name": shot_dict.get("lora_name"),
                })

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
