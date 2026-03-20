"""Shot completion — unified logic for completing a generated shot.

Handles: last frame extraction, vision QC, DB update, event emission,
continuity frame saving, and optional post-processing.

Extracted from builder.py to eliminate triplication of the same block.
"""

import logging
from pathlib import Path

from packages.core.events import event_bus, SHOT_GENERATED

logger = logging.getLogger(__name__)


async def postprocess_video(
    video_path: str,
    shot_engine: str,
    style_anchor: str,
    *,
    upscale: bool | None = None,
    interpolate: bool = True,
    color_grade: bool = True,
    scale_factor: int = 2,
    target_fps: int = 30,
) -> str:
    """Run post-processing (upscale + interpolation + color grade) on a video.

    Returns the processed path, or original path if post-processing fails/skips.

    Args:
        video_path: Path to the raw video output.
        shot_engine: Engine name (used to decide whether to upscale).
        style_anchor: Style string for color grading lookup.
        upscale: Force upscale on/off. If None, auto-detect from engine.
        interpolate: Whether to run frame interpolation.
        color_grade: Whether to apply color grading.
        scale_factor: Upscale factor (default 2x).
        target_fps: Target FPS for interpolation.
    """
    try:
        from .video_postprocess import postprocess_wan_video
        from .shot_context import resolve_color_style

        if upscale is None:
            upscale = shot_engine in ("wan", "wan22", "wan22_14b")

        processed = await postprocess_wan_video(
            video_path,
            upscale=upscale,
            interpolate=interpolate,
            color_grade=color_grade,
            scale_factor=scale_factor,
            target_fps=target_fps,
            color_style=resolve_color_style(style_anchor),
        )
        if processed:
            return processed
    except Exception as e:
        logger.warning(f"Post-processing failed: {e}, using raw output")

    return video_path


async def complete_shot(
    conn,
    shot_id,
    video_path: str,
    scene_id,
    project_id,
    generation_prompt: str,
    negative_prompt: str,
    generation_time: float,
    shot_dict: dict,
    auto_approve: bool = False,
    motion_ctx: dict | None = None,
    gpu_source: str | None = None,
) -> dict:
    """Handle shot completion: extract last frame, QC, update DB, emit event, save continuity.

    Args:
        conn: Database connection.
        shot_id: UUID of the shot.
        video_path: Path to the final video file.
        scene_id: UUID of the scene.
        project_id: Project ID (int).
        generation_prompt: The prompt used for generation.
        negative_prompt: The negative prompt used.
        generation_time: Time taken in seconds.
        shot_dict: Full shot row as dict (for QC and metadata).
        auto_approve: If True, skip vision QC and auto-approve.
        motion_ctx: Optional dict with motion tier params:
            {tier, cfg, steps, split, lightx2v, clh, cll}
        gpu_source: Optional GPU label for A/B tracking ("nvidia_q4" or "amd_q4").

    Returns:
        dict with keys: video_path, last_frame, review_status, generation_time
    """
    from .scene_video_utils import extract_last_frame
    from .scene_vision_qc import _run_vision_qc
    from .scene_source_assign import _save_continuity_frame

    # 1. Extract last frame for continuity chaining
    last_frame = await extract_last_frame(video_path)

    # 2. Determine character info
    character_slug = None
    chars = shot_dict.get("characters_present")
    if chars and isinstance(chars, list) and len(chars) > 0:
        character_slug = chars[0]

    # 3. Run vision QC or auto-approve
    if auto_approve:
        review_status = "approved"
    else:
        review_status, _qc_score = await _run_vision_qc(conn, shot_id, video_path, shot_dict)

    # 4. Update DB — build the UPDATE dynamically based on whether we have motion context
    if motion_ctx and any(v is not None for v in motion_ctx.values()):
        _gpu_src_clause = ", gpu_source = $13" if gpu_source else ""
        _gpu_src_args = [gpu_source] if gpu_source else []
        await conn.execute(f"""
            UPDATE shots SET status = 'completed', output_video_path = $2,
                   last_frame_path = $3, generation_time_seconds = $4,
                   review_status = $5,
                   motion_tier = $6, guidance_scale = $7, steps = $8,
                   gen_split_steps = $9, gen_lightx2v = $10,
                   content_lora_high = $11, content_lora_low = $12
                   {_gpu_src_clause}
            WHERE id = $1
        """, shot_id, video_path, last_frame, generation_time, review_status,
            motion_ctx.get("tier"), motion_ctx.get("cfg"), motion_ctx.get("steps"),
            motion_ctx.get("split"), motion_ctx.get("lightx2v"),
            motion_ctx.get("clh"), motion_ctx.get("cll"), *_gpu_src_args)
    else:
        _gpu_src_clause = ", gpu_source = $6" if gpu_source else ""
        _gpu_src_args = [gpu_source] if gpu_source else []
        await conn.execute(f"""
            UPDATE shots SET status = 'completed', output_video_path = $2,
                   last_frame_path = $3, generation_time_seconds = $4,
                   review_status = $5
                   {_gpu_src_clause}
            WHERE id = $1
        """, shot_id, video_path, last_frame, generation_time, review_status,
            *_gpu_src_args)

    # 5. Save continuity frame for cross-scene reuse
    scene_number = shot_dict.get("scene_number")
    shot_number = shot_dict.get("shot_number")
    # Try to get scene_number from caller context if not on shot_dict
    if scene_number is None:
        try:
            _sn = await conn.fetchval(
                "SELECT scene_number FROM scenes WHERE id = $1", scene_id
            )
            scene_number = _sn
        except Exception:
            pass

    if character_slug and last_frame and project_id:
        try:
            await _save_continuity_frame(
                conn, project_id, character_slug,
                scene_id, shot_id, last_frame,
                scene_number=scene_number,
                shot_number=shot_number,
            )
            logger.info(
                f"Shot {shot_id}: saved continuity frame for '{character_slug}' "
                f"(scene {scene_number})"
            )
        except Exception as e:
            logger.warning(f"Shot {shot_id}: failed to save continuity frame: {e}")

    # 6. Emit SHOT_GENERATED event
    shot_engine = shot_dict.get("video_engine")
    await event_bus.emit(SHOT_GENERATED, {
        "shot_id": str(shot_id),
        "scene_id": str(scene_id),
        "project_id": project_id,
        "character_slug": character_slug,
        "video_engine": shot_engine,
        "generation_time": generation_time,
        "generation_time_seconds": generation_time,
        "video_path": video_path,
        "last_frame_path": last_frame,
        "auto_approve": auto_approve,
        "motion_tier": motion_ctx.get("tier") if motion_ctx else None,
        "lora_name": shot_dict.get("lora_name"),
        "gpu_source": gpu_source,
    })

    logger.info(f"Shot {shot_id}: generated in {generation_time:.0f}s → {review_status}")

    return {
        "video_path": video_path,
        "last_frame": last_frame,
        "review_status": review_status,
        "generation_time": generation_time,
    }
