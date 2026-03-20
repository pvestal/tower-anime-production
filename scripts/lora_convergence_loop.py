#!/usr/bin/env python3
"""LoRA Test Convergence Loop — generate → review → learn → regenerate until approved.

For each target LoRA/pose, keeps generating keyframes with increasing negative
feedback until the vision review auto-approves. Once approved, the keyframe
is ready to feed into video generation (DaSiWa/WAN22).

Usage:
    python scripts/lora_convergence_loop.py --character soraya --project-id 66 \
        --tiers explicit --max-passes 5 --approve-threshold 0.75
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uuid import uuid4

from packages.core.config import BASE_PATH, get_comfyui_url, COMFYUI_OUTPUT_DIR
from packages.core.dual_gpu import get_best_gpu_for_task, should_skip_motion_lora
from packages.core.generation import generate_batch
from packages.core.audit import update_generation_quality, log_approval, log_rejection, log_decision, log_generation
from packages.lora_training.feedback import get_feedback_negatives, record_rejection
from packages.visual_pipeline.vision import vision_review_image, build_feature_checklist
from packages.core.model_profiles import get_model_profile
from packages.scene_generation.wan_video import build_dasiwa_i2v_workflow, _submit_comfyui_workflow
from packages.scene_generation.scene_comfyui import copy_to_comfyui_input, poll_comfyui_completion, is_source_already_queued
from packages.scene_generation.video_vision import extract_review_frames, review_video_frames
from packages.scene_generation.motion_intensity import classify_motion_intensity, get_motion_params

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"


def load_catalog():
    """Load LoRA catalog and return video_lora_pairs."""
    catalog_path = Path(__file__).resolve().parent.parent / "config" / "lora_catalog.yaml"
    import yaml
    with open(catalog_path) as f:
        return yaml.safe_load(f)


def get_explicit_prompts():
    """Return unambiguous prompt overrides for explicit poses."""
    return {
        "cowgirl": "woman on top, straddling partner, cowgirl riding position, nude, explicit sexual intercourse",
        "assertive_cowgirl": "woman on top, dominant straddling, pinning partner down, aggressive riding, nude, explicit",
        "reverse_cowgirl": "woman riding reverse position, facing away from partner, seated on top, nude, explicit",
        "anal_reverse_cowgirl_pov": "reverse cowgirl position, anal penetration, POV from below, nude, explicit",
        "licking_lips": "woman licking her own lips seductively, tongue visible on lips, bedroom eyes, sultry smile",
        "missionary": "woman lying on back, legs spread and wrapped, man on top, missionary sex, nude, explicit",
        "prone_bone": "woman lying face down flat on bed, man pressing on top from behind, prone position, nude",
        "doggy_front": "woman on hands and knees facing camera, man behind her, sex from behind, front view, nude",
        "doggy_back": "woman on hands and knees, rear view showing back and buttocks, man behind, back arched, nude",
        "from_behind": "woman bent forward over surface, standing sex from behind, man holding her hips, explicit",
        "spooning": "woman and man lying on sides, spooning sex position, intimate embrace, nude, explicit",
        "combo_hj_bj": "woman giving handjob and blowjob combination, oral sex, hands and mouth, close-up",
        "sensual_bj": "woman giving sensual blowjob, teasing with tongue, eye contact, oral sex, close-up",
        "titjob": "paizuri, woman pressing breasts around shaft, hands on breasts, looking up, kneeling",
        "facial": "facial cumshot, woman with cum on face, post-climax, close-up face, explicit",
        "squatting_cowgirl": "woman squatting on top of partner, feet flat on surface, bouncing riding position, nude",
        "double_blowjob": "woman giving oral to two partners simultaneously, double blowjob, explicit",
        "lips_bj": "extreme close-up of lips around shaft, blowjob close-up, oral sex detail",
        "mouthful": "woman with mouth full during oral sex, cheeks bulging, explicit oral, close-up",
        "bukkake": "multiple cumshots on woman, bukkake scene, group finish, explicit",
        "casting_doggy": "woman on knees, sex from behind, diagonal rear camera angle, casting scene, nude",
        "massage_tits": "hands massaging woman breasts from behind, sensual breast massage, foreplay, nude",
        "panties_aside": "woman with panties pulled aside, teasing reveal, lingerie, seductive pose",
        "sex_from_behind_v2": "woman bent over desk or table, standing sex from behind, office/room setting, explicit",
        "softcore_photoshoot": "woman posing for glamour photoshoot, sensual model pose, lingerie or nude, confident",
        "side_transition": "woman mid-transition between sex positions, dynamic pose change, legs moving, nude",
        "general_nsfw": "woman in sensual nude pose, alluring, confident stance, full body, glamour lighting",
        "pov_doggystyle": "first-person POV, woman on hands and knees ahead, rear view, sex from behind, explicit",
        "pov_cowgirl": "first-person POV from below, woman straddling and riding on top, cowgirl position, explicit",
        "pov_insertion": "first-person POV, penetration moment, explicit insertion, close-up",
        "pov_fellatio": "first-person POV, woman giving oral sex, looking up at camera, blowjob, explicit",
        # Action poses
        "seductive_turns": "woman turning and walking away seductively, looking over shoulder, swaying hips",
        "fight": "woman in fighting stance, fists raised, martial arts pose, fierce expression, dynamic",
        "explosion": "woman standing with explosion in background, action scene, dramatic lighting",
        "slap": "woman mid-slap, open palm strike, aggressive action, dramatic expression",
        "catwalk": "woman doing model strut on runway, fashion walk, confident posture",
        "tiktok_dance": "woman doing hip dance moves, fun expression, dance pose, dynamic",
        "hip_sway_i2v": "woman swaying hips side to side, sensual dance movement, standing",
        "outfit_transform": "woman in ornate outfit, costume reveal, full body standing pose",
    }


async def get_character_info(character_slug: str, project_id: int) -> dict:
    """Fetch character info from DB."""
    from packages.core.db import connect_direct
    conn = await connect_direct()
    try:
        # Match by name or underscore-slug (e.g. "marcus_cole" matches "Marcus Cole")
        _slug_as_name = character_slug.replace("_", " ")
        row = await conn.fetchrow(
            "SELECT name, design_prompt, identity_block, appearance_data, lora_path, lora_trigger "
            "FROM characters WHERE project_id = $1 AND (LOWER(name) = $2 OR LOWER(name) = $3)",
            project_id, character_slug, _slug_as_name,
        )
        if not row:
            raise ValueError(f"Character '{character_slug}' not found in project {project_id}")
        return dict(row)
    finally:
        await conn.close()


async def get_approval_status(character_slug: str) -> dict:
    """Read approval_status.json for a character."""
    path = BASE_PATH / character_slug / "approval_status.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _build_motion_prompt(lora_name: str, catalog: dict) -> str:
    """Resolve motion prompt from catalog fields, falling back to lora_name."""
    pairs = catalog.get("video_lora_pairs", {})
    entry = pairs.get(lora_name, {})
    # Priority: scene_description > actor_motion > explicit prompts > lora_name
    if entry.get("scene_description"):
        return entry["scene_description"]
    if entry.get("actor_motion"):
        return entry["actor_motion"]
    prompts = get_explicit_prompts()
    if lora_name in prompts:
        return prompts[lora_name]
    return lora_name.replace("_", " ")


async def _run_i2v_for_keyframe(
    keyframe_path: str,
    motion_prompt: str,
    lora_name: str,
    character_slug: str,
    session_id: str,
    catalog: dict,
) -> dict:
    """Submit keyframe to DaSiWa I2V on the least-busy GPU, poll for completion.

    Returns {status, video_path, prompt_id} or {status: "error", error: ...}.
    """
    comfyui_url = get_best_gpu_for_task("video")

    # Dedup: check if this keyframe is already queued on either GPU
    keyframe_name = Path(keyframe_path).name
    for _check_url in [comfyui_url, get_comfyui_url("video")]:
        existing_pid = is_source_already_queued(keyframe_name, comfyui_url=_check_url)
        if existing_pid:
            logger.info(f"  [{lora_name}] Already queued on {_check_url} (prompt_id={existing_pid}), polling...")
            result = await poll_comfyui_completion(existing_pid, timeout_seconds=1800, comfyui_url=_check_url)
            if result["status"] == "completed" and result.get("output_files"):
                video_path = str(COMFYUI_OUTPUT_DIR / result["output_files"][0])
                return {"status": "completed", "video_path": video_path, "prompt_id": existing_pid}
            return {"status": result["status"], "error": result.get("error", "unknown")}

    # Copy keyframe to ComfyUI input dir
    try:
        input_filename = await copy_to_comfyui_input(keyframe_path)
    except Exception as e:
        return {"status": "error", "error": f"Failed to copy keyframe: {e}"}

    # Get motion params from tier classification
    tier = classify_motion_intensity({}, lora_name=lora_name, prompt=motion_prompt)
    params = get_motion_params(tier)

    # Resolve content LoRAs from catalog
    pairs = catalog.get("video_lora_pairs", {})
    entry = pairs.get(lora_name, {})
    content_lora_high = entry.get("high")
    content_lora_low = entry.get("low")

    # Skip motion LoRAs on 3060 (no VRAM headroom with DaSiWa dual UNETs)
    if should_skip_motion_lora(comfyui_url):
        content_lora_high = None
        content_lora_low = None
        logger.info(f"  [{lora_name}] Routed to 3060 — skipping content LoRAs (VRAM constraint)")

    # Build DaSiWa Q4 I2V workflow (both GPUs with --lowvram)
    output_prefix = f"conv_{character_slug}_{lora_name}"
    workflow, prefix = build_dasiwa_i2v_workflow(
        prompt_text=motion_prompt,
        ref_image=input_filename,
        num_frames=49,
        total_steps=params.total_steps,
        split_steps=params.split_steps,
        cfg=params.cfg,
        content_lora_high=content_lora_high,
        content_lora_low=content_lora_low,
        content_lora_strength=params.content_lora_strength,
        output_prefix=output_prefix,
    )

    # Submit workflow
    try:
        prompt_id = _submit_comfyui_workflow(workflow, comfyui_url=comfyui_url)
    except Exception as e:
        return {"status": "error", "error": f"ComfyUI submit failed: {e}"}

    logger.info(f"  [{lora_name}] I2V submitted (prompt_id={prompt_id}, tier={tier})")

    # Log generation to DB
    await log_generation(
        character_slug=character_slug,
        generation_type="video",
        comfyui_prompt_id=prompt_id,
        prompt=motion_prompt,
        steps=params.total_steps,
        cfg_scale=params.cfg,
        lora_name=lora_name,
        session_id=session_id,
        pose_tag=lora_name,
        source="convergence_loop_v2",
    )

    # Poll for completion (30 min timeout)
    result = await poll_comfyui_completion(prompt_id, timeout_seconds=1800, comfyui_url=comfyui_url)

    if result["status"] == "completed" and result.get("output_files"):
        video_path = str(COMFYUI_OUTPUT_DIR / result["output_files"][0])
        return {"status": "completed", "video_path": video_path, "prompt_id": prompt_id}

    return {
        "status": result["status"],
        "error": result.get("error", "No output files"),
        "prompt_id": prompt_id,
    }


async def _run_video_qc(
    video_path: str,
    motion_prompt: str,
    character_slug: str,
    keyframe_path: str,
    video_threshold: float,
) -> dict:
    """Run video QC via vision review on extracted frames.

    Returns {score, issues, accepted, category_averages}.
    """
    frame_paths = []
    try:
        frame_paths = await extract_review_frames(video_path, count=3)
        if not frame_paths:
            return {"score": 0.0, "issues": ["No frames extracted"], "accepted": False}

        review = await review_video_frames(
            frame_paths=frame_paths,
            motion_prompt=motion_prompt,
            character_slug=character_slug,
            source_image_path=keyframe_path,
        )

        score = review.get("overall_score", 0.0)
        issues = review.get("issues", [])
        accepted = score >= video_threshold

        return {
            "score": score,
            "issues": issues,
            "accepted": accepted,
            "category_averages": review.get("category_averages", {}),
        }
    finally:
        # Clean up extracted frames
        for fp in frame_paths:
            try:
                Path(fp).unlink(missing_ok=True)
            except Exception:
                pass


async def _register_converged_clip(
    session_id: str,
    character_slug: str,
    project_id: int,
    lora_name: str,
    keyframe_path: str,
    video_path: str,
    image_score: float,
    video_score: float,
    motion_prompt: str,
    generation_params: dict,
    category_averages: dict | None = None,
):
    """Insert a converged clip into the converged_clips table with score decomposition."""
    from packages.core.db import connect_direct
    cats = category_averages or {}
    conn = await connect_direct()
    try:
        await conn.execute("""
            INSERT INTO converged_clips
                (session_id, character_slug, project_id, lora_name, pose_tag,
                 keyframe_path, video_path, image_score, video_score,
                 motion_prompt, generation_params,
                 video_character_match, video_style_match, video_motion_execution,
                 video_technical_quality, video_composition)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb,
                    $12, $13, $14, $15, $16)
        """,
            uuid4() if not session_id else __import__('uuid').UUID(session_id),
            character_slug, project_id, lora_name, lora_name,
            keyframe_path, video_path, image_score, video_score,
            motion_prompt, json.dumps(generation_params, default=str),
            cats.get("character_match"), cats.get("style_match"),
            cats.get("motion_execution"), cats.get("technical_quality"),
            cats.get("composition"),
        )
        logger.info(f"  [{lora_name}] Converged clip registered (scores: {cats})")
    finally:
        await conn.close()


async def run_convergence(
    character_slug: str,
    project_id: int,
    target_loras: list[str],
    prompts: dict[str, str],
    max_passes: int = 5,
    approve_threshold: float = 0.75,
    reject_threshold: float = 0.40,
    seeds_per_pass: int = 2,
    video_threshold: float = 0.60,
    image_only: bool = False,
):
    """Main convergence loop."""
    session_id = str(uuid4())
    logger.info(f"Convergence session: {session_id}")

    char_info = await get_character_info(character_slug, project_id)
    appearance_data = json.loads(char_info["appearance_data"]) if isinstance(char_info["appearance_data"], str) else (char_info["appearance_data"] or {})

    checkpoint = None
    from packages.core.db import connect_direct
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT checkpoint_model FROM project_characters WHERE project_id = $1 AND LOWER(name) = $2",
            project_id, character_slug,
        )
        checkpoint = row["checkpoint_model"] if row else "unknown"
    except Exception:
        checkpoint = "unknown"
    finally:
        await conn.close()

    profile = get_model_profile(checkpoint or "unknown")

    catalog = load_catalog()

    # Track which loras still need approval
    pending_loras = set(target_loras)
    video_pending = {}  # lora_name -> {keyframe_path, image_score, gen_id}
    converged = {}  # lora_name -> {keyframe_path, video_path}
    approved_keyframes = {}  # lora_name -> image_path (backwards compat)

    for pass_num in range(1, max_passes + 1):
        if not pending_loras and not video_pending:
            logger.info(f"All {len(target_loras)} LoRAs converged!")
            break

        logger.info(f"\n{'='*60}")
        logger.info(
            f"PASS {pass_num}/{max_passes} — {len(pending_loras)} image-pending, "
            f"{len(video_pending)} video-pending, {len(converged)} converged"
        )
        logger.info(f"{'='*60}")

        # Get current feedback negatives (grows each pass)
        feedback_neg = get_feedback_negatives(character_slug)
        logger.info(f"Feedback negatives: {len(feedback_neg.split(','))} terms")

        newly_approved = []
        newly_rejected = []
        # Fire-and-forget I2V tasks — images on 3060, video on AMD, no contention
        i2v_tasks: dict[str, asyncio.Task] = {}

        for lora_name in list(pending_loras):
            action_prompt = prompts.get(lora_name, lora_name)
            # Prepend character identity so LoRA + prompt reinforce each other
            char_design = char_info.get("design_prompt", "")
            prompt = f"{char_design}, {action_prompt}, confident expression, fierce eyes, enjoying herself" if char_design else f"{action_prompt}, confident expression, fierce eyes, enjoying herself"

            # Try multiple seeds per pass
            for seed_offset in range(seeds_per_pass):
                seed = 42 + (pass_num * 100) + seed_offset

                logger.info(f"  [{lora_name}] Generating seed={seed}...")

                try:
                    # Smart routing: keyframes go to least-busy GPU
                    result = await generate_batch(
                        character_slug=character_slug,
                        count=1,
                        seed=seed,
                        prompt_override=prompt,
                        pose_variation=False,
                        fire_events=False,
                        include_feedback_negatives=True,
                        include_learned_negatives=True,
                        lora_name=lora_name,
                        pose_tag=lora_name,
                        session_id=session_id,
                    )
                except Exception as e:
                    logger.error(f"  [{lora_name}] Generation failed: {e}")
                    continue

                if not result or not result[0].get("images"):
                    logger.warning(f"  [{lora_name}] No images returned")
                    continue

                img_name = result[0]["images"][0]
                img_path = BASE_PATH / character_slug / "images" / img_name

                if not img_path.exists():
                    logger.warning(f"  [{lora_name}] Image file not found: {img_path}")
                    continue

                # Vision review this specific image
                logger.info(f"  [{lora_name}] Reviewing {img_name}...")
                try:
                    review = await asyncio.to_thread(
                        vision_review_image,
                        img_path,
                        character_name=char_info["name"],
                        design_prompt=char_info.get("design_prompt", ""),
                        appearance_data=appearance_data,
                        model_profile=profile,
                    )
                except Exception as e:
                    logger.error(f"  [{lora_name}] Vision review failed: {e}")
                    continue

                quality = round(
                    (review["character_match"] + review["clarity"] + review["training_value"]) / 30, 2
                )
                issues = review.get("issues", [])
                common_hits = review.get("common_error_hits", [])

                logger.info(
                    f"  [{lora_name}] Q={quality:.0%} match={review['character_match']}/10 "
                    f"issues={len(issues)} common_errors={len(common_hits)}"
                )

                # Decision
                has_critical_error = len(common_hits) > 0
                is_approved = quality >= approve_threshold and not has_critical_error and review.get("solo", True)

                gen_id = result[0].get("gen_id")

                if is_approved:
                    logger.info(f"  [{lora_name}] ✓ IMAGE APPROVED (Q={quality:.0%})")
                    approved_keyframes[lora_name] = str(img_path)
                    pending_loras.discard(lora_name)
                    newly_approved.append(lora_name)

                    # DB audit: update quality + log approval
                    if gen_id:
                        await update_generation_quality(
                            gen_id=gen_id,
                            quality_score=quality,
                            character_match=review["character_match"] / 10.0,
                            clarity=review["clarity"] / 10.0,
                            training_value=review["training_value"] / 10.0,
                            solo=review.get("solo", True),
                            status="approved" if image_only else "video_pending",
                            artifact_path=str(img_path),
                        )
                        await log_approval(
                            character_slug=character_slug,
                            image_name=img_name,
                            quality_score=quality,
                            auto_approved=True,
                            vision_review=review,
                            generation_history_id=gen_id,
                        )

                    # Update approval_status (JSON — backwards compat)
                    approval = await get_approval_status(character_slug)
                    approval[img_name] = "approved"
                    (BASE_PATH / character_slug / "approval_status.json").write_text(
                        json.dumps(approval, indent=2)
                    )

                    # Fire I2V immediately on AMD GPU (different GPU, no contention)
                    if not image_only:
                        video_pending[lora_name] = {
                            "keyframe_path": str(img_path),
                            "image_score": quality,
                            "gen_id": gen_id,
                        }
                        motion_prompt = _build_motion_prompt(lora_name, catalog)
                        _i2v_gpu = "3060" if "8188" in get_best_gpu_for_task("video") else "9070 XT"
                        logger.info(f"  [{lora_name}] Firing I2V on {_i2v_gpu} (motion: {motion_prompt[:60]}...)")
                        i2v_tasks[lora_name] = asyncio.create_task(
                            _run_i2v_for_keyframe(
                                keyframe_path=str(img_path),
                                motion_prompt=motion_prompt,
                                lora_name=lora_name,
                                character_slug=character_slug,
                                session_id=session_id,
                                catalog=catalog,
                            )
                        )
                    else:
                        converged[lora_name] = {"keyframe_path": str(img_path)}

                    break  # Got approval for this lora, move to next

                else:
                    # Reject and learn
                    reasons = []
                    if has_critical_error:
                        reasons.append(f"Common errors: {', '.join(common_hits)}")
                    if quality < approve_threshold:
                        reasons.append(f"Low quality: {quality:.0%}")
                    if issues:
                        reasons.append(f"Issues: {'; '.join(issues[:3])}")

                    feedback_str = f"REJECT: {lora_name} pass {pass_num} — {'. '.join(reasons)}"
                    # Extract specific negative terms from issues
                    neg_additions = []
                    for issue in issues:
                        issue_lower = issue.lower()
                        if "cat" in issue_lower or "feline" in issue_lower:
                            neg_additions.append("Add negative: cat, feline, animal")
                        if "camera" in issue_lower:
                            neg_additions.append("Add negative: camera, camera object")
                        if "light" in issue_lower and "skin" in issue_lower:
                            neg_additions.append("Add negative: pale skin, light skin")
                    if neg_additions:
                        feedback_str += ". " + ". ".join(neg_additions)

                    # DB audit: update quality + log rejection
                    rejection_cats = []
                    if has_critical_error:
                        rejection_cats.append("common_error")
                    if quality < approve_threshold:
                        rejection_cats.append("low_quality")
                    if not review.get("solo", True):
                        rejection_cats.append("not_solo")

                    if gen_id:
                        await update_generation_quality(
                            gen_id=gen_id,
                            quality_score=quality,
                            character_match=review["character_match"] / 10.0,
                            clarity=review["clarity"] / 10.0,
                            training_value=review["training_value"] / 10.0,
                            solo=review.get("solo", True),
                            status="rejected",
                            rejection_categories=rejection_cats,
                            artifact_path=str(img_path),
                        )
                        await log_rejection(
                            character_slug=character_slug,
                            image_name=img_name,
                            categories=rejection_cats,
                            feedback_text=feedback_str,
                            quality_score=quality,
                            generation_history_id=gen_id,
                            source="convergence_loop",
                        )

                    record_rejection(character_slug, img_name, feedback_str)
                    newly_rejected.append(lora_name)
                    logger.info(f"  [{lora_name}] ✗ REJECTED — {'. '.join(reasons)[:100]}")

        logger.info(f"\nPass {pass_num} Phase 1 (image): {len(newly_approved)} approved, {len(newly_rejected)} rejected")

        # --- Phase 2: Video QC (collect already-running I2V tasks) ---
        if video_pending and not image_only:
            logger.info(f"\n--- Phase 2: Collecting {len(i2v_tasks)} I2V results (already running on AMD GPU) ---")
            video_done = []
            video_failed = []

            for vl_name, vl_info in list(video_pending.items()):
                keyframe_path = vl_info["keyframe_path"]
                image_score = vl_info["image_score"]
                gen_id = vl_info.get("gen_id")

                motion_prompt = _build_motion_prompt(vl_name, catalog)

                # Await the task that was already fired during Phase 1
                if vl_name in i2v_tasks:
                    logger.info(f"  [{vl_name}] Awaiting I2V result...")
                    try:
                        i2v_result = await i2v_tasks[vl_name]
                    except Exception as e:
                        logger.error(f"  [{vl_name}] I2V task failed: {e}")
                        i2v_result = {"status": "error", "error": str(e)}
                else:
                    # Fallback: submit fresh if task wasn't fired (shouldn't happen)
                    logger.info(f"  [{vl_name}] Running I2V (motion: {motion_prompt[:60]}...)")
                    i2v_result = await _run_i2v_for_keyframe(
                        keyframe_path=keyframe_path,
                        motion_prompt=motion_prompt,
                        lora_name=vl_name,
                        character_slug=character_slug,
                        session_id=session_id,
                        catalog=catalog,
                    )

                if i2v_result["status"] != "completed":
                    logger.warning(f"  [{vl_name}] I2V failed: {i2v_result.get('error', 'unknown')}")
                    # Move back to pending for new keyframe next pass
                    pending_loras.add(vl_name)
                    video_failed.append(vl_name)
                    video_done.append(vl_name)
                    continue

                video_path = i2v_result["video_path"]
                video_prompt_id = i2v_result.get("prompt_id", "")
                logger.info(f"  [{vl_name}] I2V complete: {Path(video_path).name}")

                # Run video QC
                qc_result = await _run_video_qc(
                    video_path=video_path,
                    motion_prompt=motion_prompt,
                    character_slug=character_slug,
                    keyframe_path=keyframe_path,
                    video_threshold=video_threshold,
                )

                video_score = qc_result["score"]
                logger.info(
                    f"  [{vl_name}] Video QC: score={video_score:.2f} "
                    f"({'PASS' if qc_result['accepted'] else 'FAIL'}) "
                    f"issues={len(qc_result['issues'])}"
                )

                # Update generation_history with video info
                if gen_id:
                    from packages.core.db import connect_direct
                    conn = await connect_direct()
                    try:
                        await conn.execute(
                            "UPDATE generation_history SET video_path=$1, video_score=$2, video_prompt_id=$3 WHERE id=$4",
                            video_path, video_score, video_prompt_id, gen_id,
                        )
                    finally:
                        await conn.close()

                if qc_result["accepted"]:
                    cats = qc_result.get("category_averages", {})
                    logger.info(f"  [{vl_name}] ✓ VIDEO APPROVED (score={video_score:.2f}, cats={cats})")
                    converged[vl_name] = {
                        "keyframe_path": keyframe_path,
                        "video_path": video_path,
                    }

                    # Register converged clip for trailer consumption
                    await _register_converged_clip(
                        session_id=session_id,
                        character_slug=character_slug,
                        project_id=project_id,
                        lora_name=vl_name,
                        keyframe_path=keyframe_path,
                        video_path=video_path,
                        image_score=image_score,
                        video_score=video_score,
                        motion_prompt=motion_prompt,
                        generation_params={"video_prompt_id": video_prompt_id},
                        category_averages=cats,
                    )

                    if gen_id:
                        await update_generation_quality(gen_id=gen_id, quality_score=image_score, status="video_approved")

                    video_done.append(vl_name)
                else:
                    # Video failed — back to pending_loras for new keyframe
                    cats = qc_result.get("category_averages", {})
                    # Identify weakest sub-score for actionable feedback
                    worst = min(cats, key=cats.get) if cats else "unknown"
                    logger.info(
                        f"  [{vl_name}] ✗ VIDEO REJECTED (score={video_score:.2f}, "
                        f"worst={worst}={cats.get(worst, 0):.1f}) — {'; '.join(qc_result['issues'][:3])}"
                    )
                    pending_loras.add(vl_name)
                    video_failed.append(vl_name)
                    video_done.append(vl_name)

            # Remove processed from video_pending
            for vl_name in video_done:
                video_pending.pop(vl_name, None)

            logger.info(
                f"Phase 2 summary: {len(video_done) - len(video_failed)} video-approved, "
                f"{len(video_failed)} failed (back to image queue)"
            )

        logger.info(
            f"\nPass {pass_num} totals: {len(converged)} converged, "
            f"{len(video_pending)} video-pending, {len(pending_loras)} image-pending"
        )

    # Final report
    logger.info(f"\n{'='*60}")
    logger.info(f"CONVERGENCE COMPLETE")
    logger.info(f"{'='*60}")
    mode = "image+video" if not image_only else "image-only"
    logger.info(f"Mode: {mode}")
    logger.info(f"Converged: {len(converged)}/{len(target_loras)}")
    for lora, info in sorted(converged.items()):
        vp = info.get("video_path", "n/a")
        logger.info(f"  ✓ {lora}: keyframe={Path(info['keyframe_path']).name} video={Path(vp).name if vp != 'n/a' else 'n/a'}")
    if video_pending:
        logger.info(f"Video pending ({len(video_pending)}):")
        for lora in sorted(video_pending):
            logger.info(f"  ⏳ {lora}")
    if pending_loras:
        logger.info(f"Still pending ({len(pending_loras)}):")
        for lora in sorted(pending_loras):
            logger.info(f"  ✗ {lora}")

    # Log convergence decision to DB
    all_done = not pending_loras and not video_pending
    await log_decision(
        decision_type="convergence_complete",
        character_slug=character_slug,
        input_context={
            "session_id": session_id,
            "total_loras": len(target_loras),
            "converged_count": len(converged),
            "video_pending_count": len(video_pending),
            "pending_count": len(pending_loras),
            "max_passes": max_passes,
            "approve_threshold": approve_threshold,
            "video_threshold": video_threshold,
            "image_only": image_only,
            "converged_loras": sorted(converged.keys()),
            "pending_loras": sorted(pending_loras),
        },
        decision_made=f"converged {len(converged)}/{len(target_loras)} loras ({mode})",
        confidence_score=len(converged) / max(len(target_loras), 1),
        reasoning=f"session {session_id}: {len(converged)} converged, {len(video_pending)} video-pending, {len(pending_loras)} image-pending after {max_passes} max passes",
        outcome="success" if all_done else "partial",
    )

    # Save results (JSON — backwards compat for gallery/other readers)
    results_path = Path("/tmp/convergence_results.json")
    results_path.write_text(json.dumps({
        "character": character_slug,
        "project_id": project_id,
        "total_loras": len(target_loras),
        "converged": len(converged),
        "video_pending": len(video_pending),
        "pending": len(pending_loras),
        "approved_keyframes": approved_keyframes,
        "converged_clips": {k: v for k, v in converged.items()},
        "pending_loras": sorted(pending_loras),
        "image_only": image_only,
    }, indent=2, default=str))
    logger.info(f"\nResults saved to {results_path}")

    return approved_keyframes, pending_loras


def main():
    parser = argparse.ArgumentParser(description="LoRA test convergence loop")
    parser.add_argument("--character", default="soraya")
    parser.add_argument("--project-id", type=int, default=66)
    parser.add_argument("--tiers", default="explicit", help="Comma-separated: explicit,action,camera,pov")
    parser.add_argument("--max-passes", type=int, default=5)
    parser.add_argument("--approve-threshold", type=float, default=0.75)
    parser.add_argument("--reject-threshold", type=float, default=0.40)
    parser.add_argument("--seeds-per-pass", type=int, default=2)
    parser.add_argument("--loras", help="Comma-separated specific LoRA names to test")
    parser.add_argument("--video-threshold", type=float, default=0.60, help="Video QC pass threshold (0-1)")
    parser.add_argument("--image-only", action="store_true", help="Skip video stage, image-only mode")
    args = parser.parse_args()

    catalog = load_catalog()
    pairs = catalog.get("video_lora_pairs", {})
    prompts = get_explicit_prompts()

    # Select target LoRAs based on tiers
    tiers = [t.strip() for t in args.tiers.split(",")]
    if args.loras:
        target_loras = [l.strip() for l in args.loras.split(",")]
    else:
        target_loras = []
        for name, entry in pairs.items():
            ltype = entry.get("lora_type", "")
            tier = entry.get("tier", "")
            if ltype in ("style", "furry"):
                continue
            if "explicit" in tiers and tier == "explicit" and ltype in ("pose", "pov"):
                target_loras.append(name)
            if "action" in tiers and ltype == "action":
                target_loras.append(name)
            if "camera" in tiers and ltype == "camera":
                target_loras.append(name)

    mode = "image-only" if args.image_only else "image+video"
    logger.info(f"Target: {len(target_loras)} LoRAs for {args.character} ({mode})")
    logger.info(f"Tiers: {tiers}")
    logger.info(f"Max passes: {args.max_passes}, seeds/pass: {args.seeds_per_pass}")
    logger.info(f"Approve threshold: {args.approve_threshold:.0%}, video threshold: {args.video_threshold:.0%}")

    approved, pending = asyncio.run(run_convergence(
        character_slug=args.character,
        project_id=args.project_id,
        target_loras=target_loras,
        prompts=prompts,
        max_passes=args.max_passes,
        approve_threshold=args.approve_threshold,
        reject_threshold=args.reject_threshold,
        seeds_per_pass=args.seeds_per_pass,
        video_threshold=args.video_threshold,
        image_only=args.image_only,
    ))

    sys.exit(0 if not pending else 1)


if __name__ == "__main__":
    main()
