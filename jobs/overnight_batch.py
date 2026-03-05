"""Unattended overnight batch runner for scene generation.

Two-pass pipeline:
  Pass 1 (keyframe gate): keyframe_blitz generates ~18s keyframes per shot,
    then CLIP scores each against its prompt. Shots below --clip-threshold are
    skipped — no GPU time wasted on bad prompts/checkpoints.
  Pass 2 (video render): shots that pass the gate are rendered via regenerate_shot.

Usage:
    python -m jobs.overnight_batch --project PROJECT_ID [--scenes S1,S2,...] [--ep-range EP_START EP_END]
        [--max-regens N] [--clip-threshold N] [--skip-keyframes] [--dry-run]

Examples:
    # Run all pending shots for project 3 (keyframe gate + video)
    python -m jobs.overnight_batch --project 3

    # Strict CLIP gate (only render shots scoring 70+)
    python -m jobs.overnight_batch --project 3 --clip-threshold 70

    # Skip keyframe gate, go straight to video (old behavior)
    python -m jobs.overnight_batch --project 3 --skip-keyframes

    # Run specific scenes only
    python -m jobs.overnight_batch --project 3 --scenes ac4e9026-...,bf3d1234-...

    # Dry run — keyframe + CLIP score, log results, don't render video
    python -m jobs.overnight_batch --project 3 --dry-run

    # Cap regen attempts per shot to 1
    python -m jobs.overnight_batch --project 3 --max-regens 1

Forces generation_mode='autopilot' for targeted scenes during the run,
restores original modes on exit. Does NOT change default behavior of the
UI or APIs.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.core.db import connect_direct
from packages.core.config import COMFYUI_OUTPUT_DIR

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = LOG_DIR / f"overnight_{timestamp}.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("overnight_batch")


class BatchStats:
    """Accumulates per-shot outcomes for the final summary."""

    def __init__(self):
        self.started_at = time.time()
        self.shots_attempted = 0
        self.shots_completed = 0
        self.shots_failed = 0
        self.shots_skipped = 0
        self.shots_too_similar = 0
        self.shots_clip_rejected = 0
        self.keyframes_generated = 0
        self.regen_attempts = 0
        self.total_gen_time = 0.0
        self.quality_scores: list[float] = []
        self.clip_scores: list[float] = []
        self.per_shot: list[dict] = []

    def record(self, shot_id: str, scene_id: str, status: str, gen_time: float = 0,
               quality: float | None = None, regen_count: int = 0, variety_result: dict | None = None):
        entry = {
            "shot_id": shot_id,
            "scene_id": scene_id,
            "status": status,
            "gen_time_s": round(gen_time, 1),
            "quality_score": quality,
            "regen_count": regen_count,
            "variety": variety_result,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.per_shot.append(entry)
        # Write to JSONL immediately (streaming log)
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def summary(self) -> dict:
        elapsed = time.time() - self.started_at
        avg_quality = (
            round(sum(self.quality_scores) / len(self.quality_scores), 1)
            if self.quality_scores else None
        )
        avg_clip = (
            round(sum(self.clip_scores) / len(self.clip_scores), 1)
            if self.clip_scores else None
        )
        return {
            "type": "summary",
            "elapsed_minutes": round(elapsed / 60, 1),
            "shots_attempted": self.shots_attempted,
            "shots_completed": self.shots_completed,
            "shots_failed": self.shots_failed,
            "shots_skipped": self.shots_skipped,
            "shots_clip_rejected": self.shots_clip_rejected,
            "shots_too_similar": self.shots_too_similar,
            "keyframes_generated": self.keyframes_generated,
            "total_regen_attempts": self.regen_attempts,
            "total_gen_time_minutes": round(self.total_gen_time / 60, 1),
            "avg_quality_score": avg_quality,
            "avg_clip_score": avg_clip,
            "log_file": str(log_file),
        }


async def enrich_shot(conn, shot_row: dict, scene_id: uuid.UUID) -> dict:
    """Run shot spec enrichment. Returns enriched shot dict."""
    from packages.scene_generation.shot_spec import enrich_shot_spec, get_scene_context, get_recent_shots

    scene_ctx = await get_scene_context(conn, scene_id)
    prev_shots = await get_recent_shots(conn, scene_id, limit=5)
    return await enrich_shot_spec(conn, shot_row, scene_ctx, prev_shots)


async def run_variety_check(conn, shot_id: uuid.UUID, scene_id: uuid.UUID, image_path: str | None) -> dict:
    """Run variety check on generated output."""
    from packages.scene_generation.variety_check import check_sequence_variety

    if not image_path or not Path(image_path).exists():
        return {}
    return await check_sequence_variety(conn, shot_id, scene_id, image_path)


async def clip_evaluate_keyframe(shot_id: str, image_path: str, prompt: str) -> dict:
    """CLIP-score a keyframe image against its prompt via Echo Brain."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "http://localhost:8309/api/echo/generation-eval/evaluate",
                json={
                    "image_path": image_path,
                    "prompt": prompt,
                    "shot_id": shot_id,
                },
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"  CLIP evaluation failed for {shot_id[:8]}: {e}")
    return {}


async def keyframe_pass(scene_id: uuid.UUID, conn, stats: BatchStats,
                        clip_threshold: float, dry_run: bool) -> dict[str, dict]:
    """Run keyframe blitz for a scene, then CLIP-score each keyframe.

    Returns dict mapping shot_id → {clip_score, passed, image_path, prompt}
    for shots that had keyframes generated or already existed.
    """
    import httpx

    scene_id_str = str(scene_id)
    results: dict[str, dict] = {}

    # Call keyframe blitz API
    logger.info("  Keyframe pass: generating keyframes...")
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"http://localhost:8401/api/scenes/{scene_id_str}/keyframe-blitz?skip_existing=true"
            )
            if resp.status_code != 200:
                logger.error(f"  Keyframe blitz API error: {resp.status_code}")
                return results
            blitz = resp.json()
    except Exception as e:
        logger.error(f"  Keyframe blitz failed: {e}")
        return results

    generated = blitz.get("generated", 0)
    skipped = blitz.get("skipped", 0)
    failed = blitz.get("failed", 0)
    stats.keyframes_generated += generated
    logger.info(f"  Keyframe pass: {generated} generated, {skipped} skipped, {failed} failed")

    # CLIP-score each shot that has a keyframe
    for shot_info in blitz.get("shots", []):
        shot_id = shot_info["shot_id"]
        image_path = shot_info.get("source_image_path")
        if not image_path or shot_info["status"] == "failed":
            continue

        # Get the shot's prompt for CLIP comparison
        row = await conn.fetchrow(
            "SELECT generation_prompt, motion_prompt, scene_description FROM shots WHERE id = $1",
            uuid.UUID(shot_id),
        )
        prompt = ""
        if row:
            prompt = row["generation_prompt"] or row["motion_prompt"] or row["scene_description"] or ""

        if not prompt:
            logger.info(f"  Shot {shot_info['shot_number']}: no prompt for CLIP scoring, passing through")
            results[shot_id] = {"clip_score": None, "passed": True, "image_path": image_path}
            continue

        clip_result = await clip_evaluate_keyframe(shot_id, image_path, prompt)
        semantic = clip_result.get("semantic_score", 0)
        stats.clip_scores.append(semantic)
        passed = semantic >= clip_threshold

        results[shot_id] = {
            "clip_score": semantic,
            "variety_score": clip_result.get("variety_score"),
            "passed": passed,
            "image_path": image_path,
            "prompt": prompt[:80],
        }

        status_str = "PASS" if passed else "FAIL"
        logger.info(f"  Shot {shot_info['shot_number']}: CLIP={semantic:.0f} [{status_str}] (threshold={clip_threshold})")

        if not passed:
            stats.shots_clip_rejected += 1
            stats.record(shot_id, scene_id_str, "clip_rejected",
                         quality=semantic, variety_result=clip_result)

    return results


async def generate_and_poll(scene_id: uuid.UUID, shot_id: uuid.UUID, conn, timeout: int = 600) -> dict:
    """Call regenerate_shot API and poll for completion."""
    import httpx

    async with httpx.AsyncClient(timeout=float(timeout + 30)) as client:
        resp = await client.post(
            f"http://localhost:8401/api/scenes/{scene_id}/shots/{shot_id}/regenerate"
        )
        if resp.status_code != 200:
            return {"status": "api_error", "detail": resp.text[:200]}

    # Poll DB for completion
    start = time.time()
    while (time.time() - start) < timeout:
        await asyncio.sleep(5)
        row = await conn.fetchrow(
            "SELECT status, output_video_path, last_frame_path, generation_time_seconds, quality_score "
            "FROM shots WHERE id = $1", shot_id
        )
        if row["status"] == "completed":
            return {
                "status": "completed",
                "gen_time": row["generation_time_seconds"] or 0,
                "quality": row["quality_score"],
                "output": row["output_video_path"],
                "last_frame": row["last_frame_path"],
            }
        elif row["status"] == "failed":
            return {"status": "failed"}

    return {"status": "timeout"}


async def process_shot(conn, shot: dict, scene_id: uuid.UUID, stats: BatchStats,
                       max_regens: int, dry_run: bool,
                       keyframe_results: dict[str, dict] | None = None):
    """Process a single shot: enrich → generate → variety check → optional regen.

    If keyframe_results is provided, shots that failed the CLIP gate are skipped.
    """
    shot_id = shot["id"]
    shot_id_str = str(shot_id)
    scene_id_str = str(scene_id)

    logger.info(f"Shot {shot['shot_number']} ({shot['shot_type']}) — {shot_id_str[:8]}")
    stats.shots_attempted += 1

    # Skip already-completed shots
    if shot["status"] == "completed" and shot.get("output_video_path"):
        logger.info(f"  Already completed, skipping")
        stats.shots_skipped += 1
        stats.record(shot_id_str, scene_id_str, "skipped")
        return

    # Check keyframe CLIP gate
    if keyframe_results and shot_id_str in keyframe_results:
        kf = keyframe_results[shot_id_str]
        if not kf.get("passed", True):
            logger.warning(f"  CLIP gate REJECTED (score={kf.get('clip_score')}) — skipping video gen")
            stats.shots_skipped += 1
            return  # Already recorded in keyframe_pass

    # 1. Enrich shot spec (autopilot mode)
    try:
        enriched = await enrich_shot(conn, dict(shot), scene_id)
        logger.info(f"  Enriched: pose={enriched.get('pose_type')}, "
                     f"differ_from={len(enriched.get('must_differ_from') or [])} shots")
    except Exception as e:
        logger.warning(f"  Enrichment failed (proceeding anyway): {e}")

    if dry_run:
        logger.info(f"  [DRY RUN] Would generate — skipping")
        stats.shots_skipped += 1
        stats.record(shot_id_str, scene_id_str, "dry_run")
        return

    # 2. Generate (with regen loop)
    for attempt in range(1, max_regens + 1):
        stats.regen_attempts += 1
        logger.info(f"  Generating (attempt {attempt}/{max_regens})...")

        result = await generate_and_poll(scene_id, shot_id, conn)

        if result["status"] == "completed":
            gen_time = result.get("gen_time", 0)
            quality = result.get("quality")
            stats.total_gen_time += gen_time
            if quality is not None:
                stats.quality_scores.append(quality)

            logger.info(f"  Completed in {gen_time:.0f}s, quality={quality}")

            # 3. Variety check
            variety = {}
            try:
                variety = await run_variety_check(conn, shot_id, scene_id, result.get("last_frame"))
                if variety.get("similar"):
                    stats.shots_too_similar += 1
                    logger.warning(f"  Too similar (score={variety.get('similarity_score', '?'):.3f}) "
                                   f"to shot {str(variety.get('most_similar_shot_id', ''))[:8]}")
                    # If we have regen budget left, try again
                    if attempt < max_regens:
                        logger.info(f"  Retrying with different spec...")
                        # Re-enrich to get a different pose
                        try:
                            await enrich_shot(conn, dict(shot), scene_id)
                        except Exception:
                            pass
                        continue
            except Exception as e:
                logger.warning(f"  Variety check failed: {e}")

            stats.shots_completed += 1
            stats.record(shot_id_str, scene_id_str, "completed",
                         gen_time=gen_time, quality=quality,
                         regen_count=attempt - 1, variety_result=variety)
            return

        elif result["status"] == "failed":
            logger.error(f"  Generation failed on attempt {attempt}")
            if attempt < max_regens:
                continue
        elif result["status"] == "timeout":
            logger.error(f"  Generation timed out on attempt {attempt}")
            if attempt < max_regens:
                continue
        else:
            logger.error(f"  API error: {result.get('detail', 'unknown')}")

    # All attempts exhausted
    stats.shots_failed += 1
    stats.record(shot_id_str, scene_id_str, "failed", regen_count=max_regens)


async def run_batch(args):
    conn = await connect_direct()
    stats = BatchStats()
    original_modes: dict[int, str | None] = {}  # scene_id → original generation_mode

    try:
        # Verify project exists
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", args.project)
        if not project:
            logger.error(f"Project {args.project} not found")
            return

        logger.info(f"Project: {project['name']} (ID {args.project})")
        logger.info(f"Log file: {log_file}")

        # Determine which scenes to process
        if args.scenes:
            scene_ids = [uuid.UUID(s.strip()) for s in args.scenes.split(",")]
            scenes = await conn.fetch(
                "SELECT * FROM scenes WHERE id = ANY($1) AND project_id = $2 ORDER BY scene_number",
                scene_ids, args.project,
            )
        elif args.ep_range:
            ep_start, ep_end = args.ep_range
            scenes = await conn.fetch(
                "SELECT * FROM scenes WHERE project_id = $1 "
                "AND episode_number >= $2 AND episode_number <= $3 "
                "ORDER BY episode_number, scene_number",
                args.project, ep_start, ep_end,
            )
        else:
            scenes = await conn.fetch(
                "SELECT * FROM scenes WHERE project_id = $1 ORDER BY scene_number",
                args.project,
            )

        if not scenes:
            logger.error("No scenes found matching criteria")
            return

        logger.info(f"Scenes to process: {len(scenes)}")

        # Force autopilot mode on targeted scenes (save originals for restore)
        for scene in scenes:
            original_modes[scene["id"]] = scene.get("generation_mode")

        # Note: generation_mode is on projects table, not scenes.
        # Save project-level mode and force autopilot for this run.
        original_project_mode = project.get("generation_mode")
        await conn.execute(
            "UPDATE projects SET generation_mode = 'autopilot' WHERE id = $1",
            args.project,
        )
        logger.info(f"Forced autopilot mode (was: {original_project_mode or 'default'})")

        # Process each scene
        for scene in scenes:
            scene_id = scene["id"]
            logger.info(f"\n{'='*50}")
            logger.info(f"Scene {scene.get('scene_number', '?')}: {scene['title']}")
            logger.info(f"{'='*50}")

            # Get shots for this scene
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number",
                scene_id,
            )

            if not shots:
                logger.info("  No shots in this scene")
                continue

            pending = [s for s in shots if s["status"] != "completed" or not s.get("output_video_path")]
            logger.info(f"  {len(shots)} total shots, {len(pending)} to process")

            # Keyframe gate: generate keyframes + CLIP score before video
            keyframe_results = None
            if not args.skip_keyframes and pending:
                keyframe_results = await keyframe_pass(
                    scene_id, conn, stats, args.clip_threshold, args.dry_run
                )

            for shot in pending:
                try:
                    await process_shot(conn, dict(shot), scene_id, stats,
                                       args.max_regens, args.dry_run, keyframe_results)
                except Exception as e:
                    logger.error(f"  Unexpected error on shot {shot['id']}: {e}")
                    stats.shots_failed += 1
                    stats.record(str(shot["id"]), str(scene_id), "error")

    finally:
        # Restore original project mode
        if original_project_mode is not None:
            try:
                await conn.execute(
                    "UPDATE projects SET generation_mode = $1 WHERE id = $2",
                    original_project_mode, args.project,
                )
                logger.info(f"Restored project mode to: {original_project_mode}")
            except Exception:
                pass

        await conn.close()

    # Print and log summary
    summary = stats.summary()
    logger.info(f"\n{'='*50}")
    logger.info("BATCH COMPLETE")
    logger.info(f"{'='*50}")
    for k, v in summary.items():
        if k != "type":
            logger.info(f"  {k}: {v}")

    # Append summary to JSONL
    with open(log_file, "a") as f:
        f.write(json.dumps(summary, default=str) + "\n")

    logger.info(f"\nFull log: {log_file}")


def main():
    parser = argparse.ArgumentParser(description="Overnight batch scene generation")
    parser.add_argument("--project", type=int, required=True, help="Project ID")
    parser.add_argument("--scenes", help="Comma-separated scene UUIDs (default: all scenes)")
    parser.add_argument("--ep-range", type=int, nargs=2, metavar=("START", "END"),
                        help="Episode range (inclusive)")
    parser.add_argument("--max-regens", type=int, default=2,
                        help="Max regen attempts per shot (default: 2)")
    parser.add_argument("--clip-threshold", type=float, default=60.0,
                        help="Min CLIP semantic score for keyframe to pass (default: 60)")
    parser.add_argument("--skip-keyframes", action="store_true",
                        help="Skip keyframe generation + CLIP gate, go straight to video")
    parser.add_argument("--dry-run", action="store_true",
                        help="Enrich specs only, don't generate")
    args = parser.parse_args()
    asyncio.run(run_batch(args))


if __name__ == "__main__":
    main()
