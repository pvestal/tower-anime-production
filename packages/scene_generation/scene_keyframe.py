"""Keyframe generation — CLIP evaluation and keyframe blitz for shot preview."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def _clip_evaluate_keyframe(shot_id: str, image_path: str, prompt: str) -> dict:
    """CLIP-score a keyframe image against its prompt via Echo Brain."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "http://localhost:8309/api/echo/generation-eval/evaluate",
                json={"image_path": image_path, "prompt": prompt, "shot_id": shot_id},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug(f"CLIP evaluation failed for shot {shot_id[:8]}: {e}")
    return {}


async def keyframe_blitz(conn, scene_id: str, skip_existing: bool = True,
                          clip_evaluate: bool = True) -> dict:
    """Generate keyframe images for all shots in a scene (~18s each).

    Pass 1 of two-pass generation. Enriches shot specs via Ollama, then generates
    txt2img keyframes with project checkpoint + character LoRA. Skips shots that
    already have source_image_path when skip_existing=True.

    When clip_evaluate=True (default), each generated keyframe is scored via
    Echo Brain CLIP endpoint. Scores are advisory — low scores flag shots for
    re-generation but don't block.

    Returns: {generated: int, skipped: int, failed: int, shots: [...]}
    """
    from .composite_image import generate_simple_keyframe
    from .shot_spec import enrich_shot_spec, get_scene_context, get_recent_shots

    shots = await conn.fetch(
        "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number", scene_id
    )
    if not shots:
        return {"generated": 0, "skipped": 0, "failed": 0, "shots": []}

    # Get project info + checkpoint model
    scene_row = await conn.fetchrow("""
        SELECT s.project_id, s.scene_number,
               REGEXP_REPLACE(LOWER(REPLACE(p.name, ' ', '_')), '[^a-z0-9_]', '', 'g') as project_slug
        FROM scenes s
        LEFT JOIN projects p ON s.project_id = p.id
        WHERE s.id = $1
    """, scene_id)
    project_id = scene_row["project_id"] if scene_row else None

    checkpoint = "waiIllustriousSDXL_v160.safetensors"
    if project_id:
        try:
            style_row = await conn.fetchrow(
                """SELECT gs.checkpoint_model FROM projects p
                   JOIN generation_styles gs ON p.default_style = gs.style_name
                   WHERE p.id = $1""", project_id)
            if style_row and style_row["checkpoint_model"]:
                checkpoint = style_row["checkpoint_model"]
                if not checkpoint.endswith(".safetensors"):
                    checkpoint += ".safetensors"
        except Exception:
            pass

    # Scene context for shot spec enrichment
    scene_context = await get_scene_context(conn, scene_id)

    generated = 0
    skipped = 0
    failed = 0
    shot_results = []

    for shot in shots:
        shot_dict = dict(shot)
        shot_id = str(shot["id"])

        # Skip if already has source image
        if skip_existing and shot["source_image_path"]:
            skipped += 1
            shot_results.append({
                "shot_id": shot_id, "shot_number": shot["shot_number"],
                "status": "skipped", "source_image_path": shot["source_image_path"],
            })
            continue

        chars = list(shot.get("characters_present") or [])
        prompt = shot.get("motion_prompt") or shot.get("scene_description") or ""

        # Use generation_prompt from DB as base — if already set, skip enrichment
        # to preserve explicit/manual prompts from being sanitized by Ollama
        gen_prompt = shot.get("generation_prompt")
        if gen_prompt:
            prompt = gen_prompt
            logger.info(f"Shot {shot['shot_number']}: using existing generation_prompt (skip enrichment)")
        else:
            # Enrich shot spec (pose, camera, emotion) via Ollama
            try:
                prev_shots = await get_recent_shots(conn, scene_id, limit=5)
                enriched = await enrich_shot_spec(conn, shot_dict, scene_context, prev_shots)
                if enriched and enriched.get("generation_prompt"):
                    prompt = enriched["generation_prompt"]
            except Exception as e:
                logger.debug(f"Shot {shot_id}: enrichment failed (continuing): {e}")

        # Build extra LoRAs list from shot's image_lora field
        _extra_loras = []
        if shot.get("image_lora"):
            _extra_loras.append((shot["image_lora"], shot.get("image_lora_strength") or 0.7))

        # Generate keyframe
        try:
            kf_path = await generate_simple_keyframe(
                conn, project_id, chars, prompt, checkpoint,
                shot_type=shot.get("shot_type") or "medium",
                camera_angle=shot.get("camera_angle") or "eye-level",
                extra_loras=_extra_loras or None,
            )
            if kf_path and kf_path.exists():
                # Update source image AND reset any queued (not yet generating) video job
                # so it picks up the new keyframe instead of the stale one.
                old_status = shot.get("status")
                await conn.execute(
                    "UPDATE shots SET source_image_path = $2, "
                    "comfyui_prompt_id = CASE WHEN status IN ('pending','queued') THEN NULL ELSE comfyui_prompt_id END "
                    "WHERE id = $1",
                    shot["id"], str(kf_path),
                )
                if old_status == 'generating':
                    logger.warning(
                        f"Shot {shot_id[:8]}: keyframe updated while video is generating — "
                        f"current video will use OLD keyframe. Re-queue after completion."
                    )
                generated += 1
                shot_result = {
                    "shot_id": shot_id, "shot_number": shot["shot_number"],
                    "status": "generated", "source_image_path": str(kf_path),
                }

                # CLIP evaluation (advisory)
                if clip_evaluate and prompt:
                    clip_result = await _clip_evaluate_keyframe(shot_id, str(kf_path), prompt)
                    if clip_result:
                        sem = clip_result.get("semantic_score")
                        var = clip_result.get("variety_score")
                        shot_result["clip_score"] = sem
                        shot_result["variety_score"] = var
                        shot_result["mhp_bucket"] = clip_result.get("mhp_bucket")
                        # Persist to DB
                        await conn.execute(
                            "UPDATE shots SET clip_score = $2, clip_variety_score = $3 WHERE id = $1",
                            shot["id"], sem, var,
                        )
                        logger.info(f"Keyframe blitz: shot {shot['shot_number']} → {kf_path.name} (CLIP={sem:.0f})")
                    else:
                        logger.info(f"Keyframe blitz: shot {shot['shot_number']} → {kf_path.name}")
                else:
                    logger.info(f"Keyframe blitz: shot {shot['shot_number']} → {kf_path.name}")

                shot_results.append(shot_result)
            else:
                failed += 1
                shot_results.append({
                    "shot_id": shot_id, "shot_number": shot["shot_number"],
                    "status": "failed", "error": "keyframe returned None",
                })
        except Exception as e:
            failed += 1
            shot_results.append({
                "shot_id": shot_id, "shot_number": shot["shot_number"],
                "status": "failed", "error": str(e),
            })
            logger.warning(f"Keyframe blitz: shot {shot['shot_number']} failed: {e}")

    return {
        "generated": generated, "skipped": skipped, "failed": failed,
        "total": len(shots), "shots": shot_results,
    }
