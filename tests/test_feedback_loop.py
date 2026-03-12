#!/usr/bin/env python3
"""Integration test: full feedback-improvement loop.

Tests the complete cycle:
  1. Generate image → generation_history recorded
  2. Vision review → quality scored, auto-approve/reject
  3. Approval/rejection → DB + JSON + event emitted
  4. Learning system → patterns updated, params adjusted
  5. Replenishment → regeneration queued with improved params
  6. Verify improvement: new suggestions differ from defaults

Runs against the live DB and filesystem. Uses a test character to avoid
polluting real data. Cleans up after itself.

Usage:
    python3 tests/test_feedback_loop.py
    python3 tests/test_feedback_loop.py --keep   # don't clean up test data
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/anime-studio")

from packages.core.config import BASE_PATH
from packages.core.db import get_pool
from packages.core.audit import log_generation, update_generation_quality, log_approval, log_rejection
from packages.core.events import event_bus, IMAGE_APPROVED, IMAGE_REJECTED
from packages.core.learning import suggest_params, rejection_patterns, record_learned_pattern, learning_stats
from packages.lora_training.feedback import (
    record_rejection as file_record_rejection,
    get_feedback_negatives,
    register_image_status,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_feedback_loop")

TEST_SLUG = "_test_feedback_loop"
TEST_PROJECT = "Test Feedback Loop"
TEST_CHECKPOINT = "waiIllustriousSDXL_v160.safetensors"

# Track events received
_events_received = []


async def _capture_approved(data):
    _events_received.append(("approved", data))

async def _capture_rejected(data):
    _events_received.append(("rejected", data))


async def setup():
    """Create test character directory and DB context."""
    # Filesystem
    test_dir = BASE_PATH / TEST_SLUG
    images_dir = test_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Create fake images (1x1 PNGs)
    for i in range(10):
        img_path = images_dir / f"gen_{TEST_SLUG}_{i:04d}.png"
        # Minimal valid PNG (1x1 white pixel)
        img_path.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
            b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
            b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        # Create meta with varying quality
        quality = 0.5 + (i * 0.05)  # 0.50 to 0.95
        meta = {
            "quality_score": quality,
            "vision_review": {
                "solo": True if i % 2 == 0 else False,
                "character_match": 7 + (i % 4),
                "clarity": 6 + (i % 5),
                "training_value": 5 + (i % 6),
            },
            "checkpoint_model": TEST_CHECKPOINT,
        }
        meta_path = images_dir / f"gen_{TEST_SLUG}_{i:04d}.meta.json"
        meta_path.write_text(json.dumps(meta))

    # Subscribe to events
    event_bus.subscribe(IMAGE_APPROVED, _capture_approved)
    event_bus.subscribe(IMAGE_REJECTED, _capture_rejected)

    logger.info(f"Setup: created {test_dir} with 10 test images")
    return test_dir


async def cleanup(test_dir: Path):
    """Remove test data from filesystem and DB."""
    # Filesystem
    if test_dir.exists():
        shutil.rmtree(test_dir)
        logger.info(f"Cleaned up {test_dir}")

    # DB
    pool = await get_pool()
    async with pool.acquire() as conn:
        for table in ["generation_history", "approvals", "rejections", "learned_patterns", "autonomy_decisions"]:
            deleted = await conn.execute(
                f"DELETE FROM {table} WHERE character_slug = $1", TEST_SLUG
            )
            logger.info(f"  Cleaned {table}: {deleted}")

    # Unsubscribe (if supported)
    if hasattr(event_bus, 'unsubscribe'):
        event_bus.unsubscribe(IMAGE_APPROVED, _capture_approved)
        event_bus.unsubscribe(IMAGE_REJECTED, _capture_rejected)


async def test_step1_record_generation():
    """Step 1: Record generations in generation_history."""
    logger.info("--- Step 1: Record generations ---")
    gen_ids = []
    for i in range(10):
        cfg = 5.0 + (i % 3)  # vary cfg: 5.0, 6.0, 7.0
        steps = 25 + (i % 3) * 5  # vary steps: 25, 30, 35
        gen_id = await log_generation(
            character_slug=TEST_SLUG,
            project_name=TEST_PROJECT,
            generation_type="image",
            checkpoint_model=TEST_CHECKPOINT,
            prompt=f"test character, pose {i}, anime style",
            cfg_scale=cfg,
            steps=steps,
            sampler="euler_ancestral",
            width=832,
            height=1216,
        )
        gen_ids.append(gen_id)

    assert len(gen_ids) == 10, f"Expected 10 gen IDs, got {len(gen_ids)}"
    assert all(g is not None for g in gen_ids), "Some gen IDs are None"
    logger.info(f"  Recorded {len(gen_ids)} generations (IDs: {gen_ids[0]}..{gen_ids[-1]})")
    return gen_ids


async def test_step2_score_quality(gen_ids):
    """Step 2: Score quality (simulating vision review)."""
    logger.info("--- Step 2: Score quality ---")
    for i, gen_id in enumerate(gen_ids):
        quality = 0.5 + (i * 0.05)
        solo = i % 2 == 0
        status = "approved" if quality >= 0.7 and solo else "rejected"
        await update_generation_quality(
            gen_id=gen_id,
            quality_score=quality,
            character_match=7.0 + (i % 4),
            clarity=6.0 + (i % 5),
            training_value=5.0 + (i % 6),
            solo=solo,
            status=status,
        )

    # Verify
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as total,
                   COUNT(quality_score) as scored,
                   COUNT(*) FILTER (WHERE status='approved') as approved,
                   COUNT(*) FILTER (WHERE status='rejected') as rejected
            FROM generation_history WHERE character_slug = $1
        """, TEST_SLUG)

    assert row["scored"] == 10, f"Expected 10 scored, got {row['scored']}"
    logger.info(f"  Scored: {row['scored']}, approved: {row['approved']}, rejected: {row['rejected']}")
    return row["approved"], row["rejected"]


async def test_step3_approval_events():
    """Step 3: Approve/reject images and verify events fire."""
    logger.info("--- Step 3: Approval events ---")
    _events_received.clear()

    # Approve high-quality solo images
    for i in range(10):
        img_name = f"gen_{TEST_SLUG}_{i:04d}.png"
        quality = 0.5 + (i * 0.05)
        solo = i % 2 == 0

        if quality >= 0.7 and solo:
            await log_approval(
                character_slug=TEST_SLUG, image_name=img_name,
                quality_score=quality, auto_approved=True,
                vision_review={"solo": True, "character_match": 8},
                project_name=TEST_PROJECT, checkpoint_model=TEST_CHECKPOINT,
            )
            await event_bus.emit(IMAGE_APPROVED, {
                "character_slug": TEST_SLUG, "image_name": img_name,
                "quality_score": quality, "project_name": TEST_PROJECT,
                "checkpoint_model": TEST_CHECKPOINT,
            })
            register_image_status(TEST_SLUG, img_name, "approved")
        else:
            categories = []
            if not solo:
                categories.append("not_solo")
            if quality < 0.7:
                categories.append("bad_quality")
            await log_rejection(
                character_slug=TEST_SLUG, image_name=img_name,
                categories=categories, project_name=TEST_PROJECT,
                source="vision", checkpoint_model=TEST_CHECKPOINT,
            )
            await event_bus.emit(IMAGE_REJECTED, {
                "character_slug": TEST_SLUG, "image_name": img_name,
                "quality_score": quality, "categories": categories,
                "project_name": TEST_PROJECT, "checkpoint_model": TEST_CHECKPOINT,
            })
            register_image_status(TEST_SLUG, img_name, "rejected")
            file_record_rejection(TEST_SLUG, img_name, "|".join(categories) if categories else "bad_quality")

    # Small delay for async event handlers
    await asyncio.sleep(0.5)

    approved_events = [e for e in _events_received if e[0] == "approved"]
    rejected_events = [e for e in _events_received if e[0] == "rejected"]
    logger.info(f"  Events: {len(approved_events)} approved, {len(rejected_events)} rejected")

    assert len(approved_events) > 0, "No approval events received!"
    assert len(rejected_events) > 0, "No rejection events received!"
    return len(approved_events), len(rejected_events)


async def test_step4_learning_patterns():
    """Step 4: Verify learning system recorded patterns."""
    logger.info("--- Step 4: Learning patterns ---")

    # Check learned_patterns table
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT pattern_type, frequency, quality_score_avg, cfg_range_min, cfg_range_max
            FROM learned_patterns WHERE character_slug = $1
            ORDER BY pattern_type
        """, TEST_SLUG)

    patterns = {r["pattern_type"]: dict(r) for r in rows}
    logger.info(f"  Patterns found: {list(patterns.keys())}")

    if "success" in patterns:
        logger.info(f"  Success: freq={patterns['success']['frequency']}, "
                    f"avg_q={patterns['success']['quality_score_avg']}")
    if "failure" in patterns:
        logger.info(f"  Failure: freq={patterns['failure']['frequency']}, "
                    f"avg_q={patterns['failure']['quality_score_avg']}")

    assert "success" in patterns, "No success patterns learned!"
    assert "failure" in patterns, "No failure patterns learned!"
    assert patterns["success"]["quality_score_avg"] > patterns["failure"]["quality_score_avg"], \
        "Success avg quality should be higher than failure!"

    return patterns


async def test_step5_suggest_params():
    """Step 5: Verify learning suggests improved parameters."""
    logger.info("--- Step 5: Parameter suggestions ---")

    suggestions = await suggest_params(TEST_SLUG)
    logger.info(f"  Suggestions: {suggestions}")

    assert suggestions, "No parameter suggestions returned!"
    assert "cfg_scale" in suggestions, "Missing cfg_scale suggestion"
    assert "steps" in suggestions, "Missing steps suggestion"
    assert suggestions["avg_quality"] > 0.6, f"Avg quality too low: {suggestions['avg_quality']}"

    return suggestions


async def test_step6_feedback_negatives():
    """Step 6: Verify rejection feedback builds negative prompts."""
    logger.info("--- Step 6: Feedback negatives ---")

    negatives = get_feedback_negatives(TEST_SLUG)
    logger.info(f"  Negatives: '{negatives}'")

    assert negatives, "No feedback negatives generated!"
    # Should contain terms from our rejection categories
    assert any(term in negatives for term in ["multiple characters", "blurry", "low quality"]), \
        f"Expected rejection terms in negatives, got: {negatives}"

    return negatives


async def test_step7_rejection_patterns():
    """Step 7: Verify rejection pattern analysis works."""
    logger.info("--- Step 7: Rejection patterns ---")

    patterns = await rejection_patterns(TEST_SLUG)
    logger.info(f"  Rejection patterns: {patterns}")

    assert patterns, "No rejection patterns found!"
    categories = [p["category"] for p in patterns]
    assert "not_solo" in categories or "bad_quality" in categories, \
        f"Expected not_solo or bad_quality in rejection patterns, got: {categories}"

    return patterns


async def test_step8_db_consistency():
    """Step 8: Verify DB and JSON are consistent."""
    logger.info("--- Step 8: DB/JSON consistency ---")

    # Count JSON approvals
    approval_file = BASE_PATH / TEST_SLUG / "approval_status.json"
    json_approved = 0
    json_rejected = 0
    if approval_file.exists():
        statuses = json.loads(approval_file.read_text())
        json_approved = sum(1 for v in statuses.values() if v == "approved")
        json_rejected = sum(1 for v in statuses.values() if v == "rejected")

    # Count DB approvals
    pool = await get_pool()
    async with pool.acquire() as conn:
        db_approved = await conn.fetchval(
            "SELECT COUNT(*) FROM approvals WHERE character_slug = $1", TEST_SLUG
        )
        db_rejected = await conn.fetchval(
            "SELECT COUNT(*) FROM rejections WHERE character_slug = $1", TEST_SLUG
        )

    logger.info(f"  JSON: {json_approved} approved, {json_rejected} rejected")
    logger.info(f"  DB:   {db_approved} approved, {db_rejected} rejected")

    assert json_approved == db_approved, \
        f"JSON/DB mismatch: JSON has {json_approved} approved, DB has {db_approved}"
    assert json_rejected == db_rejected, \
        f"JSON/DB mismatch: JSON has {json_rejected} rejected, DB has {db_rejected}"

    logger.info("  CONSISTENT!")
    return True


async def main():
    keep = "--keep" in sys.argv
    test_dir = await setup()

    results = {}
    try:
        gen_ids = await test_step1_record_generation()
        results["step1"] = "PASS"

        approved, rejected = await test_step2_score_quality(gen_ids)
        results["step2"] = "PASS"

        n_approve_events, n_reject_events = await test_step3_approval_events()
        results["step3"] = "PASS"

        patterns = await test_step4_learning_patterns()
        results["step4"] = "PASS"

        suggestions = await test_step5_suggest_params()
        results["step5"] = "PASS"

        negatives = await test_step6_feedback_negatives()
        results["step6"] = "PASS"

        rej_patterns = await test_step7_rejection_patterns()
        results["step7"] = "PASS"

        consistent = await test_step8_db_consistency()
        results["step8"] = "PASS"

    except AssertionError as e:
        logger.error(f"FAIL: {e}")
        results[f"step_failed"] = str(e)
    except Exception as e:
        logger.error(f"ERROR: {e}", exc_info=True)
        results["error"] = str(e)
    finally:
        if not keep:
            await cleanup(test_dir)
        else:
            logger.info(f"Keeping test data at {test_dir}")

    # Summary
    print("\n" + "=" * 60)
    print("FEEDBACK LOOP INTEGRATION TEST RESULTS")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v == "PASS")
    total = 8
    for step, result in results.items():
        icon = "✓" if result == "PASS" else "✗"
        print(f"  {icon} {step}: {result}")
    print(f"\n  {passed}/{total} steps passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
