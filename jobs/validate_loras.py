#!/usr/bin/env python3
"""LoRA Validation Job — generates one test shot per untested LoRA.

Uses a known-good reference image and character to isolate LoRA quality.
Results are stored in a `lora_validation` table for review.

Usage:
    # Dry run — show what would be tested
    python jobs/validate_loras.py --dry-run

    # Run validation for all untested LoRAs (queues to ComfyUI)
    python jobs/validate_loras.py

    # Run for specific types only
    python jobs/validate_loras.py --types pose,camera

    # Limit batch size (default: 5 per run to not hog GPU)
    python jobs/validate_loras.py --batch 10

    # Show results
    python jobs/validate_loras.py --report
"""

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import yaml

from packages.scene_generation.catalog_loader import load_catalog
from packages.scene_generation.wan_video import build_wan22_14b_i2v_workflow
from packages.scene_generation.scene_comfyui import copy_to_comfyui_input, poll_comfyui_completion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_loras")

DB_DSN = "postgresql://patrick:RP78eIrW7cI2jYvL5akt1yurE@localhost/anime_production"
COMFYUI_URL = "http://127.0.0.1:8188"
LORA_DIR = Path("/opt/ComfyUI/models/loras")
OUTPUT_DIR = Path("/opt/anime-studio/output/lora_validation")

# Frozen WAN_12GB_BASE profile — proven stable on RTX 3060
WAN_BASE = {
    "width": 480,
    "height": 720,
    "num_frames": 49,
    "fps": 16,
    "total_steps": 6,
    "split_steps": 3,
    "cfg": 3.5,
    "use_lightx2v": False,
}

# Test prompts by lora_type — explicit motion descriptions aligned with each type
TYPE_PROMPTS = {
    "pose": (
        "anime girl, {label}, rhythmic motion, nude, explicit, "
        "maintaining position throughout, consistent body proportions"
    ),
    "camera": (
        "anime girl standing in room, {label}, "
        "character holds pose while camera moves smoothly, "
        "consistent lighting throughout movement"
    ),
    "action": (
        "anime character, {label}, "
        "clear body movement, dynamic action, "
        "maintaining character identity throughout"
    ),
    "quality": (
        "anime girl, standing pose, {label}, "
        "high detail, sharp features, quality enhancement visible"
    ),
    "pov": (
        "pov perspective, anime girl, {label}, "
        "first person viewpoint, explicit, immersive angle"
    ),
    "furry": (
        "anthro furry character, {label}, "
        "clear anthro features, fur detail, tail visible"
    ),
    "style": (
        "anime scene, {label}, "
        "style effects clearly visible, consistent throughout"
    ),
}

DEFAULT_PROMPT = (
    "anime character, {label}, clear motion, "
    "maintaining identity throughout, high quality"
)


async def ensure_validation_table(conn):
    """Create lora_validation table if it doesn't exist."""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS lora_validation (
            id SERIAL PRIMARY KEY,
            lora_key TEXT NOT NULL,
            lora_type TEXT,
            lora_file TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            quality_score FLOAT,
            qc_issues JSONB,
            output_path TEXT,
            comfyui_prompt_id TEXT,
            prompt_used TEXT,
            ref_image TEXT,
            generation_time_seconds FLOAT,
            tested_at TIMESTAMPTZ DEFAULT NOW(),
            notes TEXT,
            UNIQUE(lora_key)
        )
    """)


async def get_tested_loras(conn) -> set:
    """Get set of lora_keys that have already been validated."""
    rows = await conn.fetch("SELECT lora_key FROM lora_validation")
    return {r["lora_key"] for r in rows}


async def get_reference_image(conn) -> tuple[str, str]:
    """Find a known-good reference image from a completed, high-scoring shot.

    Returns (source_image_path, character_slug).
    """
    row = await conn.fetchrow("""
        SELECT s.source_image_path, s.characters_present[1] as char_slug
        FROM shots s
        WHERE s.status = 'completed'
            AND s.quality_score > 0.5
            AND s.source_image_path IS NOT NULL
        ORDER BY s.quality_score DESC
        LIMIT 10
    """)
    if row:
        # Try each result until we find one that exists on disk
        rows = await conn.fetch("""
            SELECT s.source_image_path, s.characters_present[1] as char_slug
            FROM shots s
            WHERE s.status = 'completed'
                AND s.quality_score > 0.5
                AND s.source_image_path IS NOT NULL
            ORDER BY s.quality_score DESC
            LIMIT 10
        """)
        for r in rows:
            _p = Path(r["source_image_path"])
            if not _p.is_absolute():
                _p = Path("/opt/anime-studio") / _p
            if _p.exists():
                return str(_p), r["char_slug"]

    # Fallback: find any approved keyframe
    row = await conn.fetchrow("""
        SELECT g.output_image_path, g.character_slug
        FROM generation_history g
        WHERE g.status = 'approved'
            AND g.output_image_path IS NOT NULL
            AND g.generation_type = 'image'
        ORDER BY g.created_at DESC
        LIMIT 1
    """)
    if row and row["output_image_path"] and Path(row["output_image_path"]).exists():
        return row["output_image_path"], row["character_slug"]

    raise RuntimeError("No suitable reference image found. Generate some approved keyframes first.")


def build_test_queue(catalog: dict, already_tested: set, types: list[str] | None, batch: int) -> list[dict]:
    """Build the queue of LoRAs to validate."""
    queue = []

    for key, entry in catalog.get("video_lora_pairs", {}).items():
        if not entry or key in already_tested:
            continue
        lt = entry.get("lora_type", "unknown")
        if types and lt not in types:
            continue
        high = entry.get("high")
        low = entry.get("low")
        if not high:
            continue
        # Verify file exists
        if not (LORA_DIR / high).exists():
            logger.warning(f"SKIP {key}: {high} not on disk")
            continue
        queue.append({
            "key": key,
            "lora_type": lt,
            "high": high,
            "low": low if low and low != "null" and (LORA_DIR / low).exists() else None,
            "label": entry.get("label", key),
            "motion_tier": entry.get("motion_tier", "medium"),
            "motion_description": entry.get("motion_description") or entry.get("scene_description") or entry.get("description"),
        })

    for key, entry in catalog.get("video_motion_loras", {}).items():
        if not entry or key in already_tested:
            continue
        if types and "action" not in types:
            continue
        fname = entry.get("file")
        if not fname or not (LORA_DIR / fname).exists():
            continue
        queue.append({
            "key": key,
            "lora_type": "motion",
            "high": None,  # motion LoRAs go in motion_lora slot, not content
            "low": None,
            "motion_file": fname,
            "label": entry.get("label", key),
            "motion_tier": entry.get("motion_tier", "medium"),
            "strength": entry.get("strength", 0.8),
        })

    # Prioritize: camera and action first (useful for all projects),
    # then pose, then quality/pov/furry/style
    priority = {"camera": 0, "action": 1, "motion": 2, "pose": 3, "quality": 4, "pov": 5, "furry": 6, "style": 7}
    queue.sort(key=lambda x: priority.get(x["lora_type"], 99))

    return queue[:batch]


async def run_single_test(conn, item: dict, ref_image: str, char_slug: str) -> dict:
    """Generate a single test shot for one LoRA and score it."""
    import httpx

    key = item["key"]
    lt = item["lora_type"]
    label = item["label"]

    # Build prompt — prefer motion_description from catalog (explicit motion cues),
    # fall back to type-level template
    motion_desc = item.get("motion_description")
    if motion_desc:
        prompt = f"anime character, {motion_desc}"
    else:
        prompt_template = TYPE_PROMPTS.get(lt, DEFAULT_PROMPT)
        prompt = prompt_template.format(label=label)

    # Copy ref image to ComfyUI input
    input_filename = await copy_to_comfyui_input(ref_image)

    # Build workflow
    seed = random.randint(0, 2**63 - 1)

    if item.get("motion_file"):
        # Motion LoRA — goes in motion_lora slot
        workflow, prefix = build_wan22_14b_i2v_workflow(
            prompt_text=prompt,
            ref_image=input_filename,
            seed=seed,
            output_prefix=f"validate_{key}",
            motion_lora=item["motion_file"],
            motion_lora_strength=item.get("strength", 0.8),
            **WAN_BASE,
        )
    else:
        # Content LoRA — goes in content slots
        strength = 0.85 if lt == "pose" else 0.7
        workflow, prefix = build_wan22_14b_i2v_workflow(
            prompt_text=prompt,
            ref_image=input_filename,
            seed=seed,
            output_prefix=f"validate_{key}",
            content_lora_high=item["high"],
            content_lora_low=item.get("low"),
            content_lora_strength=strength,
            **WAN_BASE,
        )

    # Submit to ComfyUI
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

    logger.info(f"Submitted {key} ({lt}) → prompt_id={prompt_id}")

    # Record in DB
    await conn.execute("""
        INSERT INTO lora_validation (lora_key, lora_type, lora_file, status, comfyui_prompt_id, prompt_used, ref_image)
        VALUES ($1, $2, $3, 'generating', $4, $5, $6)
        ON CONFLICT (lora_key) DO UPDATE SET
            status = 'generating', comfyui_prompt_id = $4, prompt_used = $5,
            ref_image = $6, tested_at = NOW()
    """, key, lt, item.get("motion_file") or item["high"], prompt_id, prompt, ref_image)

    return {"key": key, "prompt_id": prompt_id, "prefix": prefix}


async def _score_video(video_path: str, prompt: str, lora_key: str) -> tuple[float | None, list, dict]:
    """Run gemma3 vision QC on a validation video. Returns (score, issues, category_avgs)."""
    try:
        from packages.scene_generation.video_vision import extract_review_frames, review_video_frames
        frame_paths = await extract_review_frames(video_path, count=3)
        if not frame_paths:
            return None, ["no_frames_extracted"], {}
        review = await review_video_frames(frame_paths, prompt, None, None)
        score = review.get("overall_score")
        issues = list(review.get("issues", []))
        cat_avgs = dict(review.get("category_averages", {}))
        # Clean up frames
        for fp in frame_paths:
            Path(fp).unlink(missing_ok=True)
        return score, issues, cat_avgs
    except Exception as e:
        logger.warning(f"QC scoring failed for {lora_key}: {e}")
        return None, [f"qc_error: {e}"], {}


async def collect_results(conn):
    """Poll ComfyUI for generating validation shots, collect videos, and auto-score via gemma3."""
    import httpx
    import shutil

    rows = await conn.fetch(
        "SELECT id, lora_key, lora_type, comfyui_prompt_id, prompt_used "
        "FROM lora_validation WHERE status = 'generating'"
    )
    if not rows:
        logger.info("No generating validation shots to collect")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        for row in rows:
            prompt_id = row["comfyui_prompt_id"]
            try:
                resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
                if resp.status_code != 200:
                    continue
                history = resp.json()
                if prompt_id not in history:
                    logger.info(f"  {row['lora_key']}: still generating")
                    continue

                outputs = history[prompt_id].get("outputs", {})
                video_path = None
                for node_id, node_out in outputs.items():
                    gifs = node_out.get("gifs", [])
                    if gifs:
                        sf = gifs[0].get("subfolder", "")
                        fn = gifs[0]["filename"]
                        video_path = f"/opt/ComfyUI/output/{sf}/{fn}" if sf else f"/opt/ComfyUI/output/{fn}"
                        break

                if video_path and Path(video_path).exists():
                    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                    dest = OUTPUT_DIR / f"{row['lora_key']}.mp4"
                    shutil.copy2(video_path, dest)
                    logger.info(f"Collected {row['lora_key']} → {dest.name}")

                    # Auto-score via gemma3 (runs on AMD GPU, no NVIDIA contention)
                    score, issues, cat_avgs = await _score_video(
                        str(dest), row["prompt_used"] or "", row["lora_key"]
                    )

                    status = "scored" if score is not None else "completed"
                    notes = None
                    if issues:
                        notes = ", ".join(issues)[:500]
                    if score is not None:
                        logger.info(f"  {row['lora_key']}: score={score:.0%} issues={issues}")

                    await conn.execute("""
                        UPDATE lora_validation
                        SET status = $2, output_path = $3, quality_score = $4,
                            qc_issues = $5::jsonb, notes = $6
                        WHERE id = $1
                    """, row["id"], status, str(dest), score,
                        json.dumps({"issues": issues, "categories": cat_avgs}),
                        notes)
                else:
                    status_info = history[prompt_id].get("status", {})
                    if status_info.get("status_str") == "error":
                        await conn.execute("""
                            UPDATE lora_validation SET status = 'failed',
                                notes = $2 WHERE id = $1
                        """, row["id"], str(status_info.get("messages", ""))[:500])
                        logger.warning(f"Failed: {row['lora_key']}")

            except Exception as e:
                logger.warning(f"Collecting {row['lora_key']}: {e}")


async def print_report(conn):
    """Print validation results summary."""
    rows = await conn.fetch("""
        SELECT lora_key, lora_type, status, quality_score, notes, tested_at
        FROM lora_validation
        ORDER BY lora_type, status, lora_key
    """)
    if not rows:
        print("No validation data yet. Run: python jobs/validate_loras.py")
        return

    from collections import Counter
    status_counts = Counter(r["status"] for r in rows)
    print(f"\n=== LoRA Validation Report ===")
    print(f"Total: {len(rows)} | " + " | ".join(f"{s}: {c}" for s, c in status_counts.most_common()))
    print()

    current_type = None
    for r in rows:
        if r["lora_type"] != current_type:
            current_type = r["lora_type"]
            print(f"--- {current_type} ---")
        q = r["quality_score"]
        if q is not None:
            grade = "PASS" if q >= 0.6 else "FAIL"
            q_str = f"{q:.0%} {grade}"
        else:
            q_str = "no score"
        status_icon = {"scored": "+", "completed": "?", "generating": "~", "failed": "X", "pending": "."}.get(r["status"], "?")
        notes = f" ({r['notes'][:60]})" if r["notes"] else ""
        print(f"  [{status_icon}] {r['lora_key']:35s} {q_str:12s}{notes}")


async def main():
    parser = argparse.ArgumentParser(description="Validate LoRAs with test generations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be tested")
    parser.add_argument("--types", type=str, help="Comma-separated lora_types to test (e.g. pose,camera)")
    parser.add_argument("--batch", type=int, default=5, help="Max LoRAs per run (default: 5)")
    parser.add_argument("--report", action="store_true", help="Show results")
    parser.add_argument("--collect", action="store_true", help="Collect results from ComfyUI")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB_DSN, server_settings={"search_path": "public"})
    await ensure_validation_table(conn)

    if args.report:
        await print_report(conn)
        await conn.close()
        return

    if args.collect:
        await collect_results(conn)
        await print_report(conn)
        await conn.close()
        return

    catalog = load_catalog()
    tested = await get_tested_loras(conn)
    types = args.types.split(",") if args.types else None
    queue = build_test_queue(catalog, tested, types, args.batch)

    if not queue:
        print("All LoRAs have been validated (or filtered out). Use --report to see results.")
        await conn.close()
        return

    print(f"\n{'DRY RUN: ' if args.dry_run else ''}Validation queue ({len(queue)} LoRAs):\n")
    for i, item in enumerate(queue, 1):
        lt = item["lora_type"]
        f = item.get("motion_file") or item["high"]
        print(f"  {i}. [{lt:8s}] {item['key']:35s} {f}")

    if args.dry_run:
        print(f"\nRun without --dry-run to generate test shots.")
        await conn.close()
        return

    # Get reference image
    ref_image, char_slug = await get_reference_image(conn)
    logger.info(f"Reference image: {ref_image} (character: {char_slug})")

    # Submit all tests
    submitted = []
    for item in queue:
        try:
            result = await run_single_test(conn, item, ref_image, char_slug)
            submitted.append(result)
            # Small delay between submissions to not overwhelm ComfyUI
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Failed to submit {item['key']}: {e}")
            await conn.execute("""
                INSERT INTO lora_validation (lora_key, lora_type, lora_file, status, notes)
                VALUES ($1, $2, $3, 'failed', $4)
                ON CONFLICT (lora_key) DO UPDATE SET status = 'failed', notes = $4
            """, item["key"], item["lora_type"], item.get("motion_file") or item["high"], str(e)[:500])

    print(f"\nSubmitted {len(submitted)} test generations to ComfyUI.")
    print(f"Run `python jobs/validate_loras.py --collect` after they complete to gather results.")
    print(f"Run `python jobs/validate_loras.py --report` to see status.")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
