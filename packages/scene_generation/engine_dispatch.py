"""Engine dispatch — abstract base and concrete dispatchers for each video engine.

Extracted from builder.py to eliminate the massive if/elif chain.
Each dispatcher handles: dimension resolution, seed derivation, LoRA resolution,
prompt enrichment (counter-motion, motion description, 1boy injection),
workflow building, and submission.

Phase 4 of the builder.py refactoring.
"""

import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

from packages.core.config import COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR, get_comfyui_url

from .lora_resolver import resolve_content_loras, gate_nsfw_lora, resolve_motion_lora
from .shot_context import derive_scene_seed, resolve_video_dimensions, resolve_checkpoint
from .motion_intensity import (
    classify_motion_intensity,
    get_motion_params,
    get_dasiwa_motion_params,
    get_counter_motion,
    get_motion_description,
    get_lora_type,
    cap_content_strength,
    _find_catalog_entry,
)
from .video_config import get_engine_defaults
from .scene_comfyui import copy_to_comfyui_input, poll_comfyui_completion, is_source_already_queued
from .shot_completion import complete_shot, postprocess_video

logger = logging.getLogger(__name__)


class EngineDispatcher(ABC):
    """Abstract base for video engine dispatchers."""

    engine_name: str
    requires_source_image: bool = False

    @abstractmethod
    async def build_and_submit(
        self,
        conn,
        shot_dict: dict,
        shot_id,
        scene_id: str,
        project_id: int,
        current_prompt: str,
        current_negative: str,
        image_filename: str | None,
        first_frame_path: str | None,
        file_prefix: str,
        shot_seconds: float,
        shot_steps: int,
        shot_guidance: float,
        shot_seed: int | None,
        shot_use_f1: bool,
        engine_sel,
        project_video_lora: str | None,
        project_rating: str,
        project_width: int | None,
        project_height: int | None,
        style_anchor: str,
        auto_approve: bool,
        character_slug: str | None,
        motion_prompt: str | None,
        skip_postprocess: bool = False,
        comfyui_url: str | None = None,
    ) -> dict | None:
        """Build workflow, submit to ComfyUI, return result dict or None on failure.

        Returns dict with keys:
            prompt_id: str - ComfyUI prompt ID (for engines that need polling)
            video_path: str | None - direct video path (for engines that handle polling internally)
            gen_time: float | None - generation time (for engines that handle polling internally)
            motion_ctx: dict | None - motion tier params for DB persistence
            skip_poll: bool - if True, caller should NOT poll ComfyUI (engine handled it)
        """

    def needs_roll_forward(self, duration_seconds: float) -> bool:
        """Whether this engine needs roll-forward chaining for the given duration."""
        return False


# ---------------------------------------------------------------------------
# Shared helpers used by multiple dispatchers
# ---------------------------------------------------------------------------

def _inject_1boy(prompt: str, catalog_entry: dict | None, shot_id, negative: str | None = None) -> str | tuple[str, str]:
    """Inject male partner tags for two-person poses.

    If negative is provided, returns (prompt, negative) tuple with anti-yuri tags.
    Otherwise returns just the prompt (backward compat).
    """
    if catalog_entry and catalog_entry.get("layout"):
        if "1boy" not in prompt and "1man" not in prompt:
            prompt = f"(1boy:1.3), (male:1.2), 1girl, {prompt}"
            if negative is not None:
                if "2girls" not in negative:
                    negative = f"2girls, yuri, lesbian, multiple girls, {negative}" if negative else "2girls, yuri, lesbian, multiple girls"
                logger.info(f"Shot {shot_id}: injected '(1boy:1.3)' + anti-yuri negative for two-person pose")
                return prompt, negative
            logger.info(f"Shot {shot_id}: injected '(1boy:1.3), (male:1.2)' for two-person pose")
    if negative is not None:
        return prompt, negative
    return prompt


def _inject_counter_motion(prompt: str, lora_name: str | None, shot_id) -> str:
    """Inject counter-motion cues into prompt if available from catalog."""
    if not lora_name:
        return prompt
    counter_motion = get_counter_motion(lora_name)
    if counter_motion and counter_motion not in prompt:
        prompt = f"{prompt}, {counter_motion}"
        logger.info(f"Shot {shot_id}: counter-motion injected: {counter_motion[:60]}")
    return prompt


def _inject_motion_description(prompt: str, shot_lora: str | None, content_lora_high: str | None, shot_id) -> str:
    """Inject explicit motion cues from catalog so WAN knows what motion the LoRA produces."""
    motion_desc = get_motion_description(shot_lora) if shot_lora else None
    if not motion_desc and content_lora_high:
        motion_desc = get_motion_description(content_lora_high)
    if motion_desc and motion_desc not in prompt:
        prompt = f"{prompt}, {motion_desc}"
        logger.info(f"Shot {shot_id}: motion_description injected: {motion_desc[:80]}")
    return prompt


async def _apply_lora_effectiveness(
    conn,
    shot_id,
    shot_dict: dict,
    character_slug: str | None,
    content_lora_high: str | None,
    motion_tier: str,
    content_lora_strength: float,
    use_lightx2v: bool,
    total_steps: int,
    split_steps: int,
    cfg: float,
) -> tuple[str, float, bool, int, int, float, bool]:
    """Apply LoRA effectiveness and learned_patterns overrides.

    Returns (motion_tier, content_lora_strength, use_lightx2v, total_steps, split_steps, cfg, override_applied).
    """
    override_applied = False

    if content_lora_high:
        eff_lora_key = content_lora_high.split("/")[-1].replace(".safetensors", "")
        eff_lora_key = re.sub(r"_(HIGH|LOW)$", "", eff_lora_key, flags=re.IGNORECASE)
        try:
            from .lora_effectiveness import recommended_params as _eff_params
            eff = await _eff_params(eff_lora_key, character_slug)
            if eff and eff.get("sample_count", 0) >= 2:
                if eff.get("best_lora_strength"):
                    content_lora_strength = eff["best_lora_strength"]
                if eff.get("best_motion_tier") and not shot_dict.get("motion_tier"):
                    motion_tier = eff["best_motion_tier"]
                    mp = get_motion_params(motion_tier)
                    use_lightx2v = mp.use_lightx2v
                    total_steps = mp.total_steps
                    split_steps = mp.split_steps
                    cfg = mp.cfg
                override_applied = True
                logger.info(
                    f"Shot {shot_id}: LoRA effectiveness override — "
                    f"key={eff_lora_key} str={content_lora_strength} "
                    f"tier={motion_tier} avg_q={eff.get('avg_quality', '?')} "
                    f"samples={eff['sample_count']}"
                )
        except Exception as eff_err:
            logger.debug(f"Shot {shot_id}: LoRA effectiveness lookup failed: {eff_err}")

    # Override with learned_patterns if no LoRA effectiveness already applied
    if character_slug and not override_applied:
        try:
            lp_row = await conn.fetchrow("""
                SELECT pattern_type, quality_score_avg, cfg_range_min, cfg_range_max
                FROM learned_patterns
                WHERE character_slug = $1 AND pattern_type = 'success'
                ORDER BY frequency DESC LIMIT 1
            """, character_slug)
            if lp_row and (lp_row["quality_score_avg"] or 0) > 0.7:
                if lp_row["cfg_range_min"] and lp_row["cfg_range_max"]:
                    learned_cfg = (lp_row["cfg_range_min"] + lp_row["cfg_range_max"]) / 2
                    cfg = learned_cfg
                    logger.info(
                        f"Shot {shot_id}: learned_patterns override for '{character_slug}' — "
                        f"cfg={cfg:.1f} avg_q={lp_row['quality_score_avg']:.2f}"
                    )
        except Exception as lp_err:
            logger.debug(f"Shot {shot_id}: learned_patterns lookup failed: {lp_err}")

    return motion_tier, content_lora_strength, use_lightx2v, total_steps, split_steps, cfg, override_applied


def _check_wan_character_lora(character_slug: str | None) -> bool:
    """Check if a WAN 2.2 14B character LoRA exists on disk."""
    if not character_slug:
        return False
    for suf in ("_wan22_lora", "_wan_lora"):
        if Path(f"/opt/ComfyUI/models/loras/{character_slug}{suf}.safetensors").exists():
            return True
    return False


def _apply_lora_type_enforcement(
    shot_id,
    content_lora_high: str | None,
    motion_lora: str | None,
    content_lora_strength: float,
    character_slug: str | None,
) -> float:
    """Cap content LoRA strength when WAN-architecture character LoRA is loaded."""
    has_char_lora = _check_wan_character_lora(character_slug)
    content_lora_type = get_lora_type(content_lora_high) if content_lora_high else None
    motion_lora_type = get_lora_type(motion_lora) if motion_lora else None
    has_pose = content_lora_type == "pose"
    if content_lora_high and has_char_lora:
        content_lora_strength = cap_content_strength(
            content_lora_high, content_lora_strength,
            has_character_lora=True,
            has_pose_lora=has_pose,
        )
    if content_lora_type or motion_lora_type:
        logger.info(
            f"Shot {shot_id}: lora_types content={content_lora_type} "
            f"motion={motion_lora_type} char_lora={has_char_lora} "
            f"final_str={content_lora_strength}"
        )
    return content_lora_strength


# ---------------------------------------------------------------------------
# 1. ReferenceV2VDispatcher
# ---------------------------------------------------------------------------

class ReferenceV2VDispatcher(EngineDispatcher):
    engine_name = "reference_v2v"
    requires_source_image = False  # needs source_video_path instead

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        ref_video = shot_dict.get("source_video_path")
        if not ref_video or not Path(ref_video).exists():
            logger.error(f"Shot {shot_id}: reference_v2v but no source_video_path")
            await conn.execute(
                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                shot_id, "No source video clip available for reference_v2v",
            )
            return None

        # Auto-detect kohya-format FramePack LoRA for the character
        fp_lora = None
        if character_slug:
            for suffix in ("_framepack_lora", "_framepack"):
                lp = Path(f"/opt/ComfyUI/models/loras/{character_slug}{suffix}.safetensors")
                if lp.exists():
                    try:
                        from safetensors import safe_open
                        with safe_open(str(lp), framework="pt") as sf:
                            k0 = list(sf.keys())[0] if sf.keys() else ""
                        if k0.startswith("lora_unet_"):
                            fp_lora = lp.name
                        else:
                            logger.warning(f"Skipping incompatible LoRA {lp.name} (not kohya format, key: {k0[:60]})")
                    except Exception as le:
                        logger.warning(f"Could not validate LoRA {lp.name}: {le}")
                    break

        from .framepack_refine import refine_wan_video
        attempt_start = time.time()
        refined = await refine_wan_video(
            wan_video_path=ref_video,
            prompt_text=current_prompt,
            negative_text=current_negative,
            denoise_strength=0.45,
            total_seconds=shot_seconds,
            steps=25,
            seed=shot_seed,
            guidance_scale=shot_guidance,
            lora_name=fp_lora,
            output_prefix=file_prefix,
        )
        gen_time = time.time() - attempt_start

        if not refined:
            await conn.execute(
                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                shot_id, "FramePack V2V refinement returned no output",
            )
            return None

        video_path = refined
        logger.info(f"Shot {shot_id}: reference_v2v done in {gen_time:.0f}s → {Path(refined).name}")

        # Post-process: interpolation + color grade only (no upscale — already 544x704)
        if not skip_postprocess:
            video_path = await postprocess_video(
                video_path, self.engine_name, style_anchor,
                upscale=False, interpolate=True, color_grade=True, target_fps=30,
            )

        from packages.core.dual_gpu import gpu_label_for_url
        _gpu_label = gpu_label_for_url(comfyui_url) if comfyui_url else None
        completion = await complete_shot(
            conn, shot_id, video_path, scene_id, project_id,
            current_prompt, current_negative, gen_time,
            shot_dict, auto_approve=auto_approve,
            gpu_source=_gpu_label,
        )
        return {
            "prompt_id": None,
            "video_path": video_path,
            "gen_time": gen_time,
            "motion_ctx": None,
            "skip_poll": True,
            "completion": completion,
        }


# ---------------------------------------------------------------------------
# 2. Wan22Dispatcher (wan22 5B)
# ---------------------------------------------------------------------------

class Wan22Dispatcher(EngineDispatcher):
    engine_name = "wan22"
    requires_source_image = False

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .wan_video import build_wan22_workflow, _submit_comfyui_workflow as _submit_wan_workflow

        wan22_cfg = get_engine_defaults("wan22_14b")
        fps = wan22_cfg.get("fps", 16)
        num_frames = max(9, int(shot_seconds * fps) + 1)
        if not shot_seed:
            shot_seed = derive_scene_seed(scene_id, shot_dict.get("shot_number", 0) or 0)
        wan_cfg = max(shot_guidance, 7.5)
        wan_w, wan_h = resolve_video_dimensions("wan22", project_width, project_height)
        wan22_lora = engine_sel.lora_name
        wan22_lora_str = engine_sel.lora_strength
        wan22_ref = image_filename if image_filename else None
        logger.info(
            f"Shot {shot_id}: Wan22 dims={wan_w}x{wan_h} lora={wan22_lora} "
            f"ref_image={wan22_ref is not None} seed={shot_seed} cfg={wan_cfg} frames={num_frames}"
        )
        workflow, prefix = build_wan22_workflow(
            prompt_text=current_prompt, num_frames=num_frames, fps=fps,
            steps=shot_steps, seed=shot_seed, cfg=wan_cfg,
            width=wan_w, height=wan_h,
            negative_text=current_negative,
            output_prefix=file_prefix,
            lora_name=wan22_lora,
            lora_strength=wan22_lora_str,
            ref_image=wan22_ref,
        )
        _url = comfyui_url or get_comfyui_url("video")
        prompt_id = _submit_wan_workflow(workflow, comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": None,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# 3. Wan22_14B_Dispatcher
# ---------------------------------------------------------------------------

class Wan22_14B_Dispatcher(EngineDispatcher):
    engine_name = "wan22_14b"
    requires_source_image = True

    def needs_roll_forward(self, duration_seconds: float) -> bool:
        return duration_seconds > 5.0

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .wan_video import build_wan22_14b_i2v_workflow, _submit_comfyui_workflow as _submit_wan_workflow

        if not image_filename:
            logger.error(f"Shot {shot_id}: wan22_14b requires a source image but none available")
            await conn.execute(
                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                shot_id, "wan22_14b requires a source image (I2V only)",
            )
            return None

        _14b_cfg_defaults = get_engine_defaults("wan22_14b")
        fps = _14b_cfg_defaults.get("fps", 16)
        num_frames = max(9, int(shot_seconds * fps) + 1)
        if not shot_seed:
            shot_seed = derive_scene_seed(scene_id, shot_dict.get("shot_number", 0) or 0)
        wan_w, wan_h = resolve_video_dimensions("wan22_14b", project_width, project_height)

        # Resolve content LoRA
        shot_lora = shot_dict.get("lora_name")
        trailer_role = shot_dict.get("trailer_role") or ""
        skip_project_lora = trailer_role in ("character_intro", "interaction")
        clh, cll, cl_str = resolve_content_loras(
            shot_dict, project_video_lora, skip_project_lora=skip_project_lora
        )

        # Content rating gate
        clh, cll = gate_nsfw_lora(clh, cll, project_rating)

        # Motion LoRA — skip on 3060 (no VRAM headroom)
        from packages.core.dual_gpu import should_skip_motion_lora
        _skip_motion = should_skip_motion_lora(comfyui_url) if comfyui_url else False
        has_any_content = bool(clh or cll)
        ml_desc = shot_dict.get("scene_description") or shot_dict.get("description") or ""
        if _skip_motion:
            motion_lora, motion_str = None, 0.0
            logger.info(f"Shot {shot_id}: skipping motion LoRA (3060 VRAM constraint)")
        else:
            motion_lora, motion_str = resolve_motion_lora(
                shot_dict, engine_sel, motion_prompt, ml_desc,
                project_rating, has_any_content,
            )

        if clh or cll:
            logger.info(
                f"Shot {shot_id}: content LoRA HIGH={clh} LOW={cll} "
                f"str={cl_str} (from {'shot' if shot_lora else 'project'})"
            )

        # Dynamic motion intensity
        motion_tier = classify_motion_intensity(shot_dict)
        motion_params = get_motion_params(motion_tier)
        use_lightx2v = motion_params.use_lightx2v
        total_steps = motion_params.total_steps
        split_steps = motion_params.split_steps
        cfg = motion_params.cfg
        cl_str = motion_params.content_lora_strength

        # Apply LoRA effectiveness + learned_patterns overrides
        (motion_tier, cl_str, use_lightx2v, total_steps, split_steps, cfg,
         _) = await _apply_lora_effectiveness(
            conn, shot_id, shot_dict, character_slug, clh,
            motion_tier, cl_str, use_lightx2v, total_steps, split_steps, cfg,
        )

        # Inject partner tags for two-person poses
        cat_entry = _find_catalog_entry(clh) if clh else None
        current_prompt, current_negative = _inject_1boy(current_prompt, cat_entry, shot_id, negative=current_negative)

        # Inject counter-motion
        current_prompt = _inject_counter_motion(current_prompt, shot_lora, shot_id)

        # Inject motion description
        current_prompt = _inject_motion_description(current_prompt, shot_lora, clh, shot_id)

        # LoRA type enforcement
        cl_str = _apply_lora_type_enforcement(
            shot_id, clh, motion_lora, cl_str, character_slug
        )

        logger.info(
            f"Shot {shot_id}: motion_tier={motion_tier} "
            f"steps={total_steps} split={split_steps} cfg={cfg} "
            f"lora_str={cl_str} lightx2v={use_lightx2v}"
        )

        motion_ctx = {
            "tier": motion_tier, "cfg": cfg,
            "steps": total_steps, "split": split_steps,
            "lightx2v": use_lightx2v,
            "clh": clh, "cll": cll,
        }

        # Roll-forward for long shots
        _WAN_SEGMENT_SECONDS = 5.0
        if shot_seconds > _WAN_SEGMENT_SECONDS:
            logger.info(
                f"Shot {shot_id}: Wan22-14B ROLL-FORWARD {shot_seconds}s "
                f"({int(shot_seconds / _WAN_SEGMENT_SECONDS + 0.5)} segments) "
                f"dims={wan_w}x{wan_h} ref={image_filename}"
            )
            # Import roll_forward_wan_shot from builder (it stays there as a utility)
            from .builder import roll_forward_wan_shot
            attempt_start = time.time()
            rf_result = await roll_forward_wan_shot(
                prompt_text=current_prompt,
                ref_image=image_filename,
                target_seconds=shot_seconds,
                negative_text=current_negative,
                segment_seconds=_WAN_SEGMENT_SECONDS,
                crossfade_seconds=0.3,
                width=wan_w, height=wan_h,
                fps=fps, steps=total_steps,
                split_steps=split_steps, cfg=cfg,
                seed=shot_seed,
                output_prefix=file_prefix,
                use_lightx2v=use_lightx2v,
                motion_lora=motion_lora,
                motion_lora_strength=motion_str,
                content_lora_high=clh,
                content_lora_low=cll,
                content_lora_strength=cl_str,
                comfyui_url=comfyui_url,
            )
            if rf_result["video_path"]:
                video_path = rf_result["video_path"]
                if not skip_postprocess:
                    video_path = await postprocess_video(
                        video_path, self.engine_name, style_anchor,
                        upscale=True, interpolate=True, color_grade=True,
                        scale_factor=2, target_fps=30,
                    )
                gen_time = time.time() - attempt_start
                logger.info(
                    f"Shot {shot_id}: roll-forward done, "
                    f"{rf_result['segment_count']} segs, "
                    f"{rf_result['total_duration']:.1f}s"
                )
                from packages.core.dual_gpu import gpu_label_for_url
                _gpu_label = gpu_label_for_url(comfyui_url) if comfyui_url else None
                completion = await complete_shot(
                    conn, shot_id, video_path, scene_id, project_id,
                    current_prompt, current_negative, gen_time,
                    shot_dict, auto_approve=auto_approve,
                    motion_ctx=motion_ctx,
                    gpu_source=_gpu_label,
                )
                return {
                    "prompt_id": None,
                    "video_path": video_path,
                    "gen_time": gen_time,
                    "motion_ctx": motion_ctx,
                    "skip_poll": True,
                    "completion": completion,
                }
            else:
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shot_id, "Roll-forward failed — no segments completed",
                )
                return None

        # Single segment (<=5s)
        logger.info(
            f"Shot {shot_id}: Wan22-14B I2V dims={wan_w}x{wan_h} "
            f"ref_image={image_filename} motion_lora={motion_lora} "
            f"content_high={clh} content_low={cll} "
            f"seed={shot_seed} steps={total_steps} cfg={cfg} "
            f"tier={motion_tier} frames={num_frames}"
        )
        workflow, prefix = build_wan22_14b_i2v_workflow(
            prompt_text=current_prompt,
            ref_image=image_filename,
            width=wan_w, height=wan_h,
            num_frames=num_frames, fps=fps,
            total_steps=total_steps,
            split_steps=split_steps,
            cfg=cfg,
            seed=shot_seed,
            negative_text=current_negative,
            output_prefix=file_prefix,
            use_lightx2v=use_lightx2v,
            motion_lora=motion_lora,
            motion_lora_strength=motion_str,
            content_lora_high=clh,
            content_lora_low=cll,
            content_lora_strength=cl_str,
        )
        # Dedup: skip if source image already in ComfyUI queue
        _url = comfyui_url or get_comfyui_url("video")
        existing = is_source_already_queued(image_filename, comfyui_url=_url) if image_filename else None
        if existing:
            logger.warning(f"Shot {shot_id}: source {image_filename} already queued (prompt={existing}), skipping duplicate")
            return None

        prompt_id = _submit_wan_workflow(workflow, comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": motion_ctx,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# 4. DaSiWaDispatcher
# ---------------------------------------------------------------------------

class DaSiWaDispatcher(EngineDispatcher):
    engine_name = "dasiwa"
    requires_source_image = True

    def needs_roll_forward(self, duration_seconds: float) -> bool:
        return duration_seconds > 5.0

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .wan_video import (
            build_dasiwa_i2v_workflow, build_wan22_14b_i2v_workflow,
            check_dasiwa_ready, _submit_comfyui_workflow as _submit_wan_workflow,
        )

        if not image_filename:
            logger.error(f"Shot {shot_id}: dasiwa requires a source image (I2V only)")
            await conn.execute(
                "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                shot_id, "dasiwa requires a source image (I2V only)",
            )
            return None

        dasi_ok, dasi_msg = check_dasiwa_ready()
        if not dasi_ok:
            logger.warning(f"Shot {shot_id}: {dasi_msg}, falling back to wan22_14b")
            # Fall through to wan22_14b fallback
            _14b_cfg_d = get_engine_defaults("wan22_14b_dasiwa")
            fps = _14b_cfg_d.get("fps", 16)
            num_frames = max(9, int(shot_seconds * fps) + 1)
            wan_w, wan_h = resolve_video_dimensions("dasiwa", project_width, project_height)
            # Use motion_intensity tiers for proper steps/cfg
            dasi_fb_tier = classify_motion_intensity(shot_dict)
            dasi_fb_params = get_motion_params(dasi_fb_tier)
            workflow, prefix = build_wan22_14b_i2v_workflow(
                prompt_text=current_prompt, ref_image=image_filename,
                width=wan_w, height=wan_h, num_frames=num_frames, fps=fps,
                total_steps=dasi_fb_params.total_steps,
                split_steps=dasi_fb_params.split_steps,
                cfg=dasi_fb_params.cfg, seed=shot_seed,
                negative_text=current_negative, output_prefix=file_prefix,
                use_lightx2v=False,
            )
            _url = comfyui_url or get_comfyui_url("video")
            prompt_id = _submit_wan_workflow(workflow, comfyui_url=_url)
            return {
                "prompt_id": prompt_id,
                "video_path": None,
                "gen_time": None,
                "motion_ctx": None,
                "skip_poll": False,
                "comfyui_url": _url,
            }

        # DaSiWa is ready — build the workflow
        dasi_cfg = get_engine_defaults("wan22_14b_dasiwa")
        fps = dasi_cfg.get("fps", 16)
        num_frames = max(9, int(shot_seconds * fps) + 1)
        wan_w, wan_h = resolve_video_dimensions("dasiwa", project_width, project_height)
        if not shot_seed:
            shot_seed = derive_scene_seed(scene_id, shot_dict.get("shot_number", 0) or 0)

        # Resolve content LoRA pair
        dasi_clh, dasi_cll, dasi_cl_str = resolve_content_loras(
            shot_dict, project_video_lora
        )

        # Content rating gate
        dasi_clh, dasi_cll = gate_nsfw_lora(dasi_clh, dasi_cll, project_rating)

        # Motion LoRA resolution — skip on 3060 (no VRAM headroom for motion LoRAs)
        from packages.core.dual_gpu import should_skip_motion_lora
        _skip_motion = should_skip_motion_lora(comfyui_url) if comfyui_url else False
        has_any_dasi_content = bool(dasi_clh or dasi_cll)
        ml_desc = shot_dict.get("scene_description") or shot_dict.get("description") or ""
        if _skip_motion:
            dasi_motion_lora, dasi_motion_str = None, 0.0
            logger.info(f"Shot {shot_id}: skipping motion LoRA (3060 VRAM constraint)")
        else:
            dasi_motion_lora, dasi_motion_str = resolve_motion_lora(
                shot_dict, engine_sel, motion_prompt, ml_desc,
                project_rating, has_any_dasi_content,
            )

        # Dynamic motion intensity — DaSiWa-specific tier mapping
        dasi_motion_tier = classify_motion_intensity(shot_dict)
        dasi_motion_params = get_dasiwa_motion_params(dasi_motion_tier)
        dasi_steps = dasi_motion_params.total_steps
        dasi_split = dasi_motion_params.split_steps
        dasi_cfg_val = dasi_motion_params.cfg
        dasi_cl_str = dasi_motion_params.content_lora_strength

        # Apply LoRA effectiveness overrides
        (dasi_motion_tier, dasi_cl_str, _, dasi_steps, dasi_split, dasi_cfg_val,
         _) = await _apply_lora_effectiveness(
            conn, shot_id, shot_dict, character_slug, dasi_clh,
            dasi_motion_tier, dasi_cl_str, False, dasi_steps, dasi_split, dasi_cfg_val,
        )

        # Inject partner tags + counter-motion + motion description for two-person poses
        dasi_cat = _find_catalog_entry(dasi_clh) if dasi_clh else None
        current_prompt, current_negative = _inject_1boy(current_prompt, dasi_cat, shot_id, negative=current_negative)
        shot_lora = shot_dict.get("lora_name")
        current_prompt = _inject_counter_motion(current_prompt, shot_lora, shot_id)
        current_prompt = _inject_motion_description(current_prompt, shot_lora, dasi_clh, shot_id)

        logger.info(
            f"Shot {shot_id}: DaSiWa I2V dims={wan_w}x{wan_h} "
            f"ref={image_filename} content_high={dasi_clh} "
            f"content_low={dasi_cll} motion={dasi_motion_lora} "
            f"tier={dasi_motion_tier} str={dasi_cl_str}"
        )

        # Build motion_ctx for feedback loop tracking
        dasi_motion_ctx = {
            "tier": dasi_motion_tier, "cfg": dasi_cfg_val,
            "steps": dasi_steps, "split": dasi_split,
            "lightx2v": False,  # DaSiWa has distillation baked in
            "clh": dasi_clh, "cll": dasi_cll,
        }

        # Roll-forward for long DaSiWa shots (>5s)
        _DASI_SEGMENT_SECONDS = 5.0
        if shot_seconds > _DASI_SEGMENT_SECONDS:
            logger.info(
                f"Shot {shot_id}: DaSiWa ROLL-FORWARD {shot_seconds}s "
                f"({int(shot_seconds / _DASI_SEGMENT_SECONDS + 0.5)} segments) "
                f"dims={wan_w}x{wan_h} ref={image_filename}"
            )
            from .builder import roll_forward_wan_shot
            attempt_start = time.time()
            rf_result = await roll_forward_wan_shot(
                prompt_text=current_prompt,
                ref_image=image_filename,
                target_seconds=shot_seconds,
                negative_text=current_negative,
                segment_seconds=_DASI_SEGMENT_SECONDS,
                crossfade_seconds=0.3,
                width=wan_w, height=wan_h,
                fps=fps, steps=dasi_steps,
                split_steps=dasi_split, cfg=dasi_cfg_val,
                seed=shot_seed,
                output_prefix=file_prefix,
                use_lightx2v=False,
                motion_lora=dasi_motion_lora,
                motion_lora_strength=dasi_motion_str,
                content_lora_high=dasi_clh,
                content_lora_low=dasi_cll,
                content_lora_strength=dasi_cl_str,
                engine="dasiwa",
                comfyui_url=comfyui_url,
            )
            if rf_result["video_path"]:
                video_path = rf_result["video_path"]
                if not skip_postprocess:
                    video_path = await postprocess_video(
                        video_path, self.engine_name, style_anchor,
                        upscale=True, interpolate=True, color_grade=True,
                        scale_factor=2, target_fps=30,
                    )
                gen_time = time.time() - attempt_start
                from packages.core.dual_gpu import gpu_label_for_url
                _gpu_label = gpu_label_for_url(comfyui_url) if comfyui_url else None
                completion = await complete_shot(
                    conn, shot_id, video_path, scene_id, project_id,
                    current_prompt, current_negative, gen_time,
                    shot_dict, auto_approve=auto_approve,
                    motion_ctx=dasi_motion_ctx,
                    gpu_source=_gpu_label,
                )
                return {
                    "prompt_id": None,
                    "video_path": video_path,
                    "gen_time": gen_time,
                    "motion_ctx": dasi_motion_ctx,
                    "skip_poll": True,
                    "completion": completion,
                }
            else:
                await conn.execute(
                    "UPDATE shots SET status = 'failed', error_message = $2 WHERE id = $1",
                    shot_id, "DaSiWa roll-forward failed — no segments completed",
                )
                return None

        workflow, prefix = build_dasiwa_i2v_workflow(
            prompt_text=current_prompt,
            ref_image=image_filename,
            width=wan_w, height=wan_h,
            num_frames=num_frames, fps=fps,
            total_steps=dasi_steps,
            split_steps=dasi_split,
            cfg=dasi_cfg_val,
            seed=shot_seed,
            negative_text=current_negative,
            output_prefix=file_prefix,
            motion_lora=dasi_motion_lora,
            content_lora_high=dasi_clh,
            content_lora_low=dasi_cll,
            content_lora_strength=dasi_cl_str,
        )
        _url = comfyui_url or get_comfyui_url("video")
        prompt_id = _submit_wan_workflow(workflow, comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": dasi_motion_ctx,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# 5. WanT2VDispatcher (wan 1.3B)
# ---------------------------------------------------------------------------

class WanT2VDispatcher(EngineDispatcher):
    engine_name = "wan"
    requires_source_image = False

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .wan_video import build_wan_t2v_workflow, _submit_comfyui_workflow as _submit_wan_workflow

        fps = 16
        num_frames = max(9, int(shot_seconds * fps) + 1)
        if not shot_seed:
            shot_seed = derive_scene_seed(scene_id, shot_dict.get("shot_number", 0) or 0)
        wan_cfg = max(shot_guidance, 7.5)
        wan_w, wan_h = resolve_video_dimensions("wan", project_width, project_height)
        logger.info(f"Shot {shot_id}: Wan dims={wan_w}x{wan_h} (project={project_width}x{project_height})")
        workflow, prefix = build_wan_t2v_workflow(
            prompt_text=current_prompt, num_frames=num_frames, fps=fps,
            steps=shot_steps, seed=shot_seed, cfg=wan_cfg,
            width=wan_w, height=wan_h,
            use_gguf=True,
            negative_text=current_negative,
            output_prefix=file_prefix,
        )
        logger.info(f"Shot {shot_id}: Wan seed={shot_seed} cfg={wan_cfg} frames={num_frames}")
        _url = comfyui_url or get_comfyui_url("video")
        prompt_id = _submit_wan_workflow(workflow, comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": None,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# 6. LTXDispatcher
# ---------------------------------------------------------------------------

class LTXDispatcher(EngineDispatcher):
    engine_name = "ltx"
    requires_source_image = False

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .ltx_video import build_ltx_workflow, _submit_comfyui_workflow as _submit_ltx_workflow

        fps = 24
        num_frames = max(9, int(shot_seconds * fps) + 1)
        ltx_lora = engine_sel.lora_name
        ltx_lora_str = engine_sel.lora_strength
        logger.info(f"Shot {shot_id}: LTX lora={ltx_lora} strength={ltx_lora_str}")
        workflow, prefix = build_ltx_workflow(
            prompt_text=current_prompt,
            image_path=image_filename if image_filename else None,
            num_frames=num_frames, fps=fps, steps=shot_steps,
            seed=shot_seed,
            lora_name=ltx_lora,
            lora_strength=ltx_lora_str,
        )
        _url = comfyui_url or get_comfyui_url("video")
        prompt_id = _submit_ltx_workflow(workflow, comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": None,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# 7. LTXLongDispatcher
# ---------------------------------------------------------------------------

class LTXLongDispatcher(EngineDispatcher):
    engine_name = "ltx_long"
    requires_source_image = False

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .ltx_video import build_ltxv_looping_workflow, _submit_comfyui_workflow as _submit_ltx_workflow

        ltx_cfg = get_engine_defaults("ltx_long")
        fps = ltx_cfg.get("fps", 24)
        num_frames = max(25, int(shot_seconds * fps) + 1)
        ltx_tile_size = ltx_cfg.get("temporal_tile_size", 80)
        ltx_overlap = ltx_cfg.get("temporal_overlap", 24)
        ltx_overlap_cond = ltx_cfg.get("temporal_overlap_cond_strength", 0.5)
        ltx_guiding = ltx_cfg.get("guiding_strength", 1.0)
        ltx_cond_img = ltx_cfg.get("cond_image_strength", 1.0)
        ltx_adain = ltx_cfg.get("adain_factor", 0.0)
        wan_w, wan_h = resolve_video_dimensions("ltx_long", project_width, project_height)
        logger.info(
            f"Shot {shot_id}: LTX_LONG dims={wan_w}x{wan_h} "
            f"tile_size={ltx_tile_size} overlap={ltx_overlap} "
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
            output_prefix=file_prefix,
            temporal_tile_size=ltx_tile_size,
            temporal_overlap=ltx_overlap,
            temporal_overlap_cond_strength=ltx_overlap_cond,
            guiding_strength=ltx_guiding,
            cond_image_strength=ltx_cond_img,
            adain_factor=ltx_adain,
        )
        _url = comfyui_url or get_comfyui_url("video")
        prompt_id = _submit_ltx_workflow(workflow, comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": None,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# 8. FramePackDispatcher
# ---------------------------------------------------------------------------

class FramePackDispatcher(EngineDispatcher):
    engine_name = "framepack"
    requires_source_image = True

    async def build_and_submit(
        self, conn, shot_dict, shot_id, scene_id, project_id,
        current_prompt, current_negative, image_filename, first_frame_path,
        file_prefix, shot_seconds, shot_steps, shot_guidance, shot_seed,
        shot_use_f1, engine_sel, project_video_lora, project_rating,
        project_width, project_height, style_anchor, auto_approve,
        character_slug, motion_prompt, skip_postprocess=False,
        comfyui_url=None,
    ):
        from .framepack import build_framepack_workflow, _submit_comfyui_workflow
        from .scene_comfyui import is_source_already_queued

        # Dedup: skip if source image already in ComfyUI queue
        _url = comfyui_url or get_comfyui_url("video")
        existing = is_source_already_queued(image_filename, comfyui_url=_url) if image_filename else None
        if existing:
            logger.warning(f"Shot {shot_id}: source {image_filename} already queued (prompt={existing}), skipping duplicate")
            return None

        use_f1 = shot_dict.get("video_engine") == "framepack_f1" or shot_use_f1
        workflow_data, sampler_node_id, prefix = build_framepack_workflow(
            prompt_text=current_prompt, image_path=image_filename,
            total_seconds=shot_seconds, steps=shot_steps, use_f1=use_f1,
            seed=shot_seed, negative_text=current_negative,
            gpu_memory_preservation=6.0, guidance_scale=shot_guidance,
            output_prefix=file_prefix,
        )
        prompt_id = _submit_comfyui_workflow(workflow_data["prompt"], comfyui_url=_url)
        return {
            "prompt_id": prompt_id,
            "video_path": None,
            "gen_time": None,
            "motion_ctx": None,
            "skip_poll": False,
            "comfyui_url": _url,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DISPATCHERS: dict[str, EngineDispatcher] = {}


def _register_dispatcher(cls):
    """Register a dispatcher class by its engine_name."""
    instance = cls()
    DISPATCHERS[instance.engine_name] = instance
    return cls


# Register all dispatchers
for _cls in (
    ReferenceV2VDispatcher,
    Wan22Dispatcher,
    Wan22_14B_Dispatcher,
    DaSiWaDispatcher,
    WanT2VDispatcher,
    LTXDispatcher,
    LTXLongDispatcher,
    FramePackDispatcher,
):
    _instance = _cls()
    DISPATCHERS[_instance.engine_name] = _instance

# FramePack F1 uses same dispatcher as FramePack
DISPATCHERS["framepack_f1"] = DISPATCHERS["framepack"]


def get_dispatcher(engine: str) -> EngineDispatcher | None:
    """Look up a dispatcher by engine name."""
    return DISPATCHERS.get(engine)
