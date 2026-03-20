"""Vision QC — score generated videos via gemma3 on AMD GPU.

Includes action-reaction scoring when counter_motion is defined for the shot's LoRA.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Auto-approve threshold for vision QC (0-1 scale)
_QC_AUTO_APPROVE_THRESHOLD = 0.6


async def _run_vision_qc(
    conn, shot_id, video_path: str, shot_dict: dict,
) -> tuple[str, float | None]:
    """Run vision QC on a completed video. Returns (review_status, quality_score).

    Extracts 3 frames, scores via gemma3 on AMD GPU (no NVIDIA contention).
    When the shot's LoRA has a counter_motion defined, also runs action-reaction
    scoring (optical flow + frame-pair vision comparison).
    Falls back gracefully — never blocks generation.
    """
    try:
        from .video_vision import extract_review_frames, review_video_frames
        from .video_qc import _store_qc_review_data, _record_source_image_effectiveness

        frame_paths = await extract_review_frames(video_path, count=3)
        if not frame_paths:
            return "pending_review", None

        motion_prompt = shot_dict.get("motion_prompt") or shot_dict.get("generation_prompt") or ""
        chars = shot_dict.get("characters_present")
        char_slug = chars[0] if chars and isinstance(chars, list) else None
        source_img = shot_dict.get("source_image_path")

        review = await review_video_frames(
            frame_paths, motion_prompt, char_slug, source_img,
        )

        score = review.get("overall_score")
        issues = list(review.get("issues", []))
        cat_avgs = dict(review.get("category_averages", {}))
        per_frame = review.get("per_frame", [])

        # ── Action-Reaction Scoring ────────────────────────────────────
        # Only runs when the shot's LoRA has counter_motion defined
        lora = shot_dict.get("lora_name")
        counter_motion = None
        if lora:
            try:
                from .motion_intensity import get_counter_motion
                counter_motion = get_counter_motion(lora)
            except Exception:
                pass

        if counter_motion:
            try:
                from .action_reaction_qc import score_action_reaction
                ar_result = await score_action_reaction(
                    video_path=video_path,
                    qc_frame_paths=frame_paths,
                    motion_prompt=motion_prompt,
                    counter_motion=counter_motion,
                    character_slug=char_slug,
                    lora_name=lora,
                )
                if ar_result:
                    composite = ar_result.get("composite", {})
                    flow = ar_result.get("optical_flow", {})

                    # Merge composite scores into category_averages
                    cat_avgs["action_initiation"] = composite.get("action_score", 5.0)
                    cat_avgs["reaction_presence"] = composite.get("reaction_score", 5.0)
                    cat_avgs["state_delta"] = composite.get("state_delta", 5.0)

                    # Store raw flow data in per_frame for detailed inspection
                    per_frame.append({
                        "_type": "action_reaction",
                        "optical_flow": flow,
                        "vision_pair": ar_result.get("vision_pair", {}),
                        "composite": composite,
                    })

                    # Add issues based on hard thresholds
                    if not composite.get("both_active", True):
                        issues.append("reaction_absent")
                    if composite.get("state_delta", 10) < 4.0:
                        issues.append("frozen_interaction")
                    if composite.get("reaction_score", 10) < 4.0:
                        issues.append("weak_reaction")

                    # Adjust overall score: penalize absent reactions
                    if "reaction_absent" in issues and score is not None:
                        score = round(score * 0.7, 2)  # 30% penalty
                    elif "weak_reaction" in issues and score is not None:
                        score = round(score * 0.85, 2)  # 15% penalty

                    logger.info(
                        f"Shot {shot_id}: action-reaction QC — "
                        f"action={composite.get('action_score')}, "
                        f"reaction={composite.get('reaction_score')}, "
                        f"state_delta={composite.get('state_delta')}, "
                        f"flow_both_active={composite.get('both_active')}"
                    )
            except Exception as ar_err:
                logger.warning(f"Shot {shot_id}: action-reaction QC failed ({ar_err}), skipping")

        # Deduplicate issues
        issues = sorted(set(issues))

        # Persist QC data
        await _store_qc_review_data(conn, shot_id, issues, cat_avgs, per_frame, "pending_review")

        # Update quality_score
        if score is not None:
            await conn.execute(
                "UPDATE shots SET quality_score = $2 WHERE id = $1", shot_id, score,
            )

        # Record source image effectiveness
        await _record_source_image_effectiveness(conn, shot_dict, score or 0, cat_avgs)

        # Record motion pattern for adaptive tuning
        motion_exec = cat_avgs.get("motion_execution")
        if motion_exec is not None and lora:
            try:
                from .motion_intensity import record_motion_pattern
                await record_motion_pattern(
                    lora_name=lora,
                    motion_tier=shot_dict.get("motion_tier", "unknown"),
                    motion_score=float(motion_exec),
                    cfg=shot_dict.get("guidance_scale"),
                    steps=shot_dict.get("steps"),
                )
                # Invalidate adaptive cache so next generation picks up new data
                from .motion_intensity import invalidate_adaptive_cache
                invalidate_adaptive_cache()
            except Exception as _mp_err:
                logger.debug(f"Shot {shot_id}: motion pattern record failed: {_mp_err}")

        # Trigger LoRA effectiveness refresh so learned params update promptly
        try:
            from .lora_effectiveness import refresh_effectiveness
            await refresh_effectiveness()
        except Exception as _eff_err:
            logger.debug(f"Shot {shot_id}: effectiveness refresh failed: {_eff_err}")

        # All shots go to review — no auto-approve
        review_status = "pending_review"
        logger.info(f"Shot {shot_id}: QC → pending_review (score={score:.0%}, issues={issues})")

        # Clean up extracted frames
        for fp in frame_paths:
            try:
                Path(fp).unlink(missing_ok=True)
            except Exception:
                pass

        return review_status, score

    except Exception as e:
        logger.warning(f"Shot {shot_id}: vision QC failed ({e}), falling back to pending_review")
        return "pending_review", None
