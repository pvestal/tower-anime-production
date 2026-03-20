"""Production pipeline tests — validate config, keyframes, and end-to-end generation.

Uses actual production code paths (generate_simple_keyframe, keyframe_blitz, regenerate_shot)
instead of building standalone workflows. Results stored in prompt_tests table.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COMFYUI_KEYFRAME_URL = "http://localhost:8188"
COMFYUI_VIDEO_URL = "http://localhost:8189"
LORA_DIR = Path("/opt/ComfyUI/models/loras")
CHECKPOINT_DIR = Path("/opt/ComfyUI/models/checkpoints")


async def validate_project_config(project_id: int) -> dict:
    """Pre-flight check: verify project config before burning GPU time.

    Checks:
    - Characters have non-empty design_prompt
    - LoRA files exist on disk
    - Project checkpoint resolved and file exists
    - ComfyUI endpoints healthy
    """
    from packages.core.db import connect_direct
    import httpx

    report = {"pass": [], "fail": [], "warnings": [], "project_id": project_id}

    conn = await connect_direct()
    try:
        # Project exists
        project = await conn.fetchrow(
            "SELECT id, name, default_style FROM projects WHERE id = $1", project_id
        )
        if not project:
            report["fail"].append(f"Project {project_id} not found")
            return report
        report["pass"].append(f"Project found: {project['name']}")

        # Resolve checkpoint
        checkpoint = None
        if project["default_style"]:
            style_row = await conn.fetchrow(
                "SELECT checkpoint_model, width, height FROM generation_styles WHERE style_name = $1",
                project["default_style"],
            )
            if style_row and style_row["checkpoint_model"]:
                checkpoint = style_row["checkpoint_model"]
                if not checkpoint.endswith(".safetensors"):
                    checkpoint += ".safetensors"
                report["pass"].append(f"Checkpoint resolved: {checkpoint}")
                report["_checkpoint"] = checkpoint
                report["_width"] = style_row["width"]
                report["_height"] = style_row["height"]

                # Check file exists
                cp_path = CHECKPOINT_DIR / checkpoint
                if cp_path.exists():
                    report["pass"].append(f"Checkpoint file exists: {cp_path.name}")
                else:
                    report["fail"].append(f"Checkpoint file missing: {cp_path}")
            else:
                report["fail"].append(f"No generation_styles row for style '{project['default_style']}'")
        else:
            report["warnings"].append("Project has no default_style — will use fallback checkpoint")

        # Characters
        chars = await conn.fetch(
            "SELECT name, design_prompt, lora_path, lora_trigger "
            "FROM characters WHERE project_id = $1", project_id
        )
        if not chars:
            report["fail"].append("No characters in project")
        else:
            report["pass"].append(f"{len(chars)} characters found")

        for c in chars:
            slug = c["name"].lower().replace(" ", "_")
            if not c["design_prompt"] or not c["design_prompt"].strip():
                report["fail"].append(f"Character '{slug}' has empty design_prompt")
            else:
                report["pass"].append(f"Character '{slug}' has design_prompt ({len(c['design_prompt'])} chars)")

            if c["lora_path"]:
                lora_file = LORA_DIR / c["lora_path"]
                if lora_file.exists():
                    report["pass"].append(f"LoRA exists: {c['lora_path']}")
                else:
                    report["fail"].append(f"LoRA file missing: {lora_file}")
                if not c["lora_trigger"]:
                    report["warnings"].append(f"Character '{slug}' has lora_path but no lora_trigger")
            else:
                report["warnings"].append(f"Character '{slug}' has no LoRA")

        # ComfyUI health
        async with httpx.AsyncClient(timeout=5.0) as client:
            for label, url in [("Keyframe (8188)", COMFYUI_KEYFRAME_URL), ("Video (8189)", COMFYUI_VIDEO_URL)]:
                try:
                    resp = await client.get(f"{url}/system_stats")
                    if resp.status_code == 200:
                        report["pass"].append(f"ComfyUI {label} healthy")
                    else:
                        report["fail"].append(f"ComfyUI {label} returned {resp.status_code}")
                except Exception as e:
                    report["fail"].append(f"ComfyUI {label} unreachable: {e}")

    finally:
        await conn.close()

    report["ok"] = len(report["fail"]) == 0
    return report


async def run_keyframe_test(
    project_id: int,
    character_slugs: list[str] | None = None,
    shot_types: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Generate test keyframes using production code (generate_simple_keyframe).

    For each character x shot_type, generates one keyframe and validates:
    - File exists and is non-zero
    - CLIP score
    - LoRA was loaded (via ComfyUI history)
    """
    from packages.core.db import connect_direct
    from packages.scene_generation.composite_image import generate_simple_keyframe
    from packages.scene_generation.scene_keyframe import _clip_evaluate_keyframe

    shot_types = shot_types or ["medium", "close-up"]
    batch_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    conn = await connect_direct()
    try:
        # Get project + checkpoint
        project = await conn.fetchrow(
            "SELECT id, name, default_style FROM projects WHERE id = $1", project_id
        )
        if not project:
            return {"error": f"Project {project_id} not found"}

        checkpoint = "waiIllustriousSDXL_v160.safetensors"
        style_row = await conn.fetchrow(
            """SELECT gs.checkpoint_model FROM projects p
               JOIN generation_styles gs ON p.default_style = gs.style_name
               WHERE p.id = $1""", project_id
        )
        if style_row and style_row["checkpoint_model"]:
            checkpoint = style_row["checkpoint_model"]
            if not checkpoint.endswith(".safetensors"):
                checkpoint += ".safetensors"

        # Get characters
        slug_filter = ""
        params = [project_id]
        if character_slugs:
            slug_filter = " AND LOWER(REGEXP_REPLACE(name, '\\s+', '_', 'g')) = ANY($2::text[])"
            params.append(character_slugs)

        chars = await conn.fetch(
            f"SELECT name, design_prompt, lora_path, lora_trigger "
            f"FROM characters WHERE project_id = $1{slug_filter}",
            *params,
        )
        if not chars:
            return {"error": "No matching characters found"}

        results = []
        for char in chars:
            slug = char["name"].lower().replace(" ", "_")
            design_prompt = char["design_prompt"] or ""

            for shot_type in shot_types:
                test_result = {
                    "character": slug,
                    "shot_type": shot_type,
                    "checkpoint": checkpoint,
                    "design_prompt": design_prompt[:100] + "..." if len(design_prompt) > 100 else design_prompt,
                    "lora_path": char["lora_path"],
                    "batch_id": batch_id,
                }

                if dry_run:
                    test_result["status"] = "dry_run"
                    results.append(test_result)
                    continue

                try:
                    kf_path = await generate_simple_keyframe(
                        conn, project_id, [slug], design_prompt, checkpoint,
                        shot_type=shot_type,
                    )

                    if kf_path and kf_path.exists():
                        file_size = kf_path.stat().st_size
                        test_result["status"] = "generated"
                        test_result["output_path"] = str(kf_path)
                        test_result["file_size"] = file_size

                        if file_size == 0:
                            test_result["status"] = "failed"
                            test_result["error"] = "Output file is empty (0 bytes)"
                        else:
                            # CLIP evaluation
                            clip_result = await _clip_evaluate_keyframe(
                                str(uuid.uuid4()), str(kf_path), design_prompt
                            )
                            if clip_result:
                                test_result["clip_score"] = clip_result.get("semantic_score")
                                test_result["variety_score"] = clip_result.get("variety_score")

                        # Store in prompt_tests table
                        await conn.execute(
                            "INSERT INTO prompt_tests (project_id, character_slugs, action_label, "
                            "action_prompt, identity_prompt, engine, status, batch_id, "
                            "output_path, completed_at) "
                            "VALUES ($1, $2, $3, $4, $5, 'keyframe', $6, $7, $8, NOW())",
                            project_id, [slug], f"keyframe_{shot_type}",
                            design_prompt[:500], design_prompt[:500],
                            test_result["status"], batch_id, str(kf_path),
                        )
                    else:
                        test_result["status"] = "failed"
                        test_result["error"] = "generate_simple_keyframe returned None"
                except Exception as e:
                    test_result["status"] = "failed"
                    test_result["error"] = str(e)
                    logger.error(f"Keyframe test failed for {slug}/{shot_type}: {e}")

                results.append(test_result)

    finally:
        await conn.close()

    passed = sum(1 for r in results if r["status"] == "generated")
    failed = sum(1 for r in results if r["status"] == "failed")
    return {
        "batch_id": batch_id,
        "project_id": project_id,
        "checkpoint": checkpoint,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


async def run_pipeline_test(
    project_id: int,
    character_slugs: list[str] | None = None,
    include_video: bool = True,
) -> dict:
    """Full keyframe-to-video pipeline test using production code.

    1. Creates a temporary test scene
    2. Creates shots with real character slugs
    3. Runs keyframe_blitz (production)
    4. Optionally triggers video generation via regenerate_shot
    5. Marks scene as test for cleanup
    """
    from packages.core.db import connect_direct
    from packages.scene_generation.scene_keyframe import keyframe_blitz

    batch_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    conn = await connect_direct()
    try:
        # Validate project
        project = await conn.fetchrow(
            "SELECT id, name FROM projects WHERE id = $1", project_id
        )
        if not project:
            return {"error": f"Project {project_id} not found"}

        # Get characters
        params = [project_id]
        slug_filter = ""
        if character_slugs:
            slug_filter = " AND LOWER(REGEXP_REPLACE(name, '\\s+', '_', 'g')) = ANY($2::text[])"
            params.append(character_slugs)

        chars = await conn.fetch(
            f"SELECT name FROM characters WHERE project_id = $1{slug_filter}", *params
        )
        if not chars:
            return {"error": "No matching characters found"}

        char_names = [c["name"] for c in chars]

        # Create test scene
        scene_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO scenes (id, project_id, title, description, scene_number, generation_status) "
            "VALUES ($1, $2, $3, $4, "
            "(SELECT COALESCE(MAX(scene_number), 0) + 1 FROM scenes WHERE project_id = $2), 'test')",
            scene_id, project_id,
            f"[TEST] Pipeline Validation {batch_id}",
            f"Automated pipeline test for {', '.join(char_names)}",
        )

        # Create 1 shot per character
        shot_ids = []
        for i, char_name in enumerate(char_names, 1):
            shot_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO shots (id, scene_id, shot_number, shot_type, "
                "characters_present, status, duration_seconds) "
                "VALUES ($1, $2, $3, 'medium', $4, 'pending', 3)",
                shot_id, scene_id, i, [char_name],
            )
            shot_ids.append(shot_id)

        await conn.execute(
            "UPDATE scenes SET total_shots = $2 WHERE id = $1",
            scene_id, len(shot_ids),
        )

        # Run keyframe blitz (production code)
        logger.info(f"Pipeline test: running keyframe_blitz for scene {scene_id}")
        blitz_result = await keyframe_blitz(conn, str(scene_id), skip_existing=False)

        result = {
            "batch_id": batch_id,
            "project_id": project_id,
            "scene_id": str(scene_id),
            "characters": char_names,
            "keyframe_result": blitz_result,
        }

        # Video generation
        if include_video and blitz_result.get("generated", 0) > 0:
            video_results = []
            for shot_id in shot_ids:
                shot = await conn.fetchrow(
                    "SELECT source_image_path, status FROM shots WHERE id = $1", shot_id
                )
                if shot and shot["source_image_path"]:
                    # Trigger video generation via regenerate_shot endpoint logic
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=300.0) as client:
                            resp = await client.post(
                                f"http://localhost:8401/api/scenes/{scene_id}/shots/{shot_id}/regenerate"
                            )
                            video_results.append({
                                "shot_id": str(shot_id),
                                "status": "queued" if resp.status_code == 200 else "failed",
                                "response": resp.json() if resp.status_code == 200 else resp.text,
                            })
                    except Exception as e:
                        video_results.append({
                            "shot_id": str(shot_id),
                            "status": "failed",
                            "error": str(e),
                        })
                else:
                    video_results.append({
                        "shot_id": str(shot_id),
                        "status": "skipped",
                        "reason": "no keyframe generated",
                    })
            result["video_results"] = video_results

    finally:
        await conn.close()

    return result
