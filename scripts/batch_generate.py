#!/usr/bin/env python3
"""Batch video generation with GPU optimization.

Manages Ollama lifecycle to maximize 9070 XT VRAM for video generation.
Postprocess routes to 3060 automatically (COMFYUI_URL = :8188).
QC runs after batch completes when Ollama is reloaded.

Usage:
    # Generate for a specific project
    python scripts/batch_generate.py --project 66 --limit 10

    # Generate for a specific scene
    python scripts/batch_generate.py --scene 43762ad8-...

    # Dry run (show what would be generated)
    python scripts/batch_generate.py --project 66 --dry-run
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_generate")

OLLAMA_URL = "http://localhost:11434"
COMFYUI_VIDEO_URL = "http://127.0.0.1:8189"  # 9070 XT
COMFYUI_PP_URL = "http://127.0.0.1:8188"     # 3060 (postprocess)
VISION_MODEL = "gemma3:12b"


# ---------------------------------------------------------------------------
# Ollama lifecycle
# ---------------------------------------------------------------------------

def ollama_unload():
    """Unload all Ollama models to free 9070 XT VRAM."""
    try:
        # Get loaded models
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5)
        data = json.loads(resp.read())
        for m in data.get("models", []):
            name = m["name"]
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=json.dumps({"model": name, "keep_alive": 0}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"Unloaded Ollama model: {name}")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Ollama unload failed (may already be unloaded): {e}")


def ollama_reload():
    """Reload vision model for QC."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({"model": VISION_MODEL, "prompt": "hello", "stream": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=120)
        logger.info(f"Reloaded Ollama model: {VISION_MODEL}")
    except Exception as e:
        logger.warning(f"Ollama reload failed: {e}")


# ---------------------------------------------------------------------------
# Shot queries
# ---------------------------------------------------------------------------

async def get_ready_shots(conn, project_id=None, scene_id=None, limit=None):
    """Get shots ready for video generation (have keyframe, no video)."""
    conditions = [
        "s.review_status = 'unreviewed'",
        "s.status IN ('pending', 'failed')",
        "s.source_image_path IS NOT NULL",
        "s.source_image_path != ''",
        "(s.output_video_path IS NULL OR s.output_video_path = '')",
    ]
    params = []

    if scene_id:
        params.append(scene_id)
        conditions.append(f"s.scene_id = ${len(params)}")
    elif project_id:
        params.append(project_id)
        conditions.append(f"sc.project_id = ${len(params)}")

    where = " AND ".join(conditions)
    limit_clause = f"LIMIT ${len(params) + 1}" if limit else ""
    if limit:
        params.append(limit)

    query = f"""
        SELECT s.id, s.scene_id, s.shot_number, s.lora_name, s.motion_tier,
               s.video_engine, s.source_image_path,
               LEFT(s.motion_prompt, 60) as motion_prompt,
               p.name as project_name, p.id as project_id
        FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        JOIN projects p ON sc.project_id = p.id
        WHERE {where}
        ORDER BY sc.id, s.shot_number
        {limit_clause}
    """
    return await conn.fetch(query, *params)


# ---------------------------------------------------------------------------
# Generation via API
# ---------------------------------------------------------------------------

async def generate_scene(scene_id: str, timeout: int = 1800) -> dict:
    """Trigger scene generation via anime-studio API."""
    try:
        payload = json.dumps({}).encode()
        req = urllib.request.Request(
            f"http://localhost:8401/api/scenes/{scene_id}/generate",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer tower-auth-token",
            },
        )
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        logger.error(f"Scene generation failed: {e}")
        return {"error": str(e)}


async def wait_for_scene(conn, scene_id: str, timeout: int = 3600):
    """Wait for all shots in a scene to finish generating."""
    start = time.time()
    while time.time() - start < timeout:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status IN ('completed','failed') THEN 1 ELSE 0 END) as done,
                   SUM(CASE WHEN status = 'generating' THEN 1 ELSE 0 END) as active
            FROM shots WHERE scene_id = $1
        """, scene_id)
        total, done, active = row["total"], row["done"], row["active"]
        if done >= total:
            return True
        elapsed = int(time.time() - start)
        logger.info(f"  Scene {scene_id[:8]}: {done}/{total} done, {active} active ({elapsed}s)")
        await asyncio.sleep(30)
    return False


# ---------------------------------------------------------------------------
# Batch QC (after generation)
# ---------------------------------------------------------------------------

async def batch_qc(conn, shot_ids: list[str]):
    """Run QC on completed shots (call after Ollama is reloaded)."""
    completed = await conn.fetch("""
        SELECT id, output_video_path FROM shots
        WHERE id = ANY($1::uuid[]) AND status = 'completed'
          AND quality_score IS NULL AND output_video_path IS NOT NULL
    """, shot_ids)

    if not completed:
        logger.info("No shots need QC")
        return

    logger.info(f"Running QC on {len(completed)} shots...")
    for row in completed:
        try:
            payload = json.dumps({"shot_id": str(row["id"]), "approved": False}).encode()
            req = urllib.request.Request(
                f"http://localhost:8401/api/scenes/x/shots/{row['id']}/qc-review",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=120)
        except Exception as e:
            logger.warning(f"QC failed for {row['id']}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Batch video generation")
    parser.add_argument("--project", type=int, help="Project ID")
    parser.add_argument("--scene", type=str, help="Scene ID")
    parser.add_argument("--limit", type=int, default=None, help="Max shots to generate")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--skip-ollama", action="store_true", help="Don't manage Ollama lifecycle")
    parser.add_argument("--skip-qc", action="store_true", help="Skip post-batch QC")
    parser.add_argument("--runpod", action="store_true", help="Burst overflow to RunPod A100")
    parser.add_argument("--runpod-pod", type=str, default="tower-moto-lora", help="RunPod pod name")
    args = parser.parse_args()

    if not args.project and not args.scene:
        parser.error("Must specify --project or --scene")

    import asyncpg
    conn = await asyncpg.connect(
        host="localhost", user="patrick", password="RP78eIrW7cI2jYvL5akt1yurE",
        database="anime_production",
        server_settings={"search_path": "public"},
    )

    # Get ready shots
    shots = await get_ready_shots(conn, args.project, args.scene, args.limit)
    if not shots:
        logger.info("No shots ready for generation")
        await conn.close()
        return

    # Group by scene
    scenes = {}
    for s in shots:
        sid = str(s["scene_id"])
        scenes.setdefault(sid, []).append(s)

    logger.info(f"Found {len(shots)} shots across {len(scenes)} scenes")
    for sid, scene_shots in scenes.items():
        proj = scene_shots[0]["project_name"]
        loras = [s["lora_name"] or "none" for s in scene_shots]
        logger.info(f"  {sid[:8]} ({proj}): {len(scene_shots)} shots, LoRAs: {set(loras)}")

    if args.dry_run:
        await conn.close()
        return

    # Phase 1: Free GPU
    if not args.skip_ollama:
        logger.info("Phase 1: Unloading Ollama to free 9070 XT VRAM...")
        ollama_unload()

    # Phase 2: Generate
    logger.info(f"Phase 2: Generating {len(shots)} shots...")
    start = time.time()
    shot_ids = [str(s["id"]) for s in shots]

    for sid, scene_shots in scenes.items():
        logger.info(f"Generating scene {sid[:8]} ({len(scene_shots)} shots)...")
        result = await generate_scene(sid)
        logger.info(f"  API response: {result.get('message', result)}")

        # Wait for completion
        done = await wait_for_scene(conn, sid, timeout=len(scene_shots) * 900)
        if done:
            logger.info(f"  Scene {sid[:8]} complete")
        else:
            logger.warning(f"  Scene {sid[:8]} timed out")

    elapsed = time.time() - start
    logger.info(f"Generation complete in {elapsed/60:.1f} minutes")

    # Phase 3: QC
    if not args.skip_qc and not args.skip_ollama:
        logger.info("Phase 3: Reloading Ollama for QC...")
        ollama_reload()
        await batch_qc(conn, shot_ids)

    # Summary
    stats = await conn.fetchrow("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
               ROUND(AVG(generation_time_seconds)::numeric) as avg_time
        FROM shots WHERE id = ANY($1::uuid[])
    """, shot_ids)

    logger.info(f"Results: {stats['completed']}/{stats['total']} completed, "
                f"{stats['failed']} failed, avg {stats['avg_time']}s per shot")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
