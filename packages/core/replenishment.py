"""Replenishment loop — autonomous image generation to reach target approved counts.

When images are approved, this module checks if the character still needs more
approved training images. If below target, it generates more, waits for completion,
registers them as pending, and triggers vision review to close the loop.

Flow:
    IMAGE_APPROVED → check count → generate → ComfyUI → datasets → register pending
    → vision review → auto-approve/reject → learning → (repeat if still below target)

Safety:
    - Off by default (must explicitly enable)
    - Max concurrent generations
    - Per-character cooldown
    - Daily generation limit per character
    - Max consecutive rejects before giving up on a character
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BASE_PATH
from .db import get_pool
from .events import event_bus, IMAGE_APPROVED
from .audit import log_decision

logger = logging.getLogger(__name__)

# --- Configuration ---
DEFAULT_TARGET = 20       # approved images per character
MAX_CONCURRENT = 2        # max parallel generation subprocesses
COOLDOWN_SECONDS = 60     # min seconds between generations for same character
MAX_DAILY_PER_CHAR = 10   # max images generated per character per day
MAX_CONSECUTIVE_REJECTS = 5  # stop if N consecutive images rejected
BATCH_SIZE = 3            # images per generation round

# --- State ---
_enabled = False
_target_override: dict[str, int] = {}       # character_slug → custom target
_active_tasks: dict[str, asyncio.Task] = {} # character_slug → running task
_last_generation: dict[str, float] = {}     # character_slug → timestamp
_daily_counts: dict[str, int] = {}          # character_slug → count today
_daily_reset_date: str = ""                 # YYYY-MM-DD of last reset
_consecutive_rejects: dict[str, int] = {}   # character_slug → consecutive reject count


def enable(on: bool = True):
    """Enable or disable the replenishment loop."""
    global _enabled
    _enabled = on
    logger.info(f"Replenishment loop {'enabled' if on else 'disabled'}")


def set_target(character_slug: str = None, target: int = DEFAULT_TARGET):
    """Set target approved count. Per-character or global default."""
    global DEFAULT_TARGET
    if character_slug:
        _target_override[character_slug] = target
    else:
        DEFAULT_TARGET = target


def get_target(character_slug: str) -> int:
    """Get the target approved count for a character."""
    return _target_override.get(character_slug, DEFAULT_TARGET)


def _reset_daily_if_needed():
    """Reset daily counters at midnight UTC."""
    global _daily_counts, _daily_reset_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _daily_reset_date:
        _daily_counts = {}
        _daily_reset_date = today


def _count_approved(character_slug: str) -> int:
    """Count approved images from approval_status.json."""
    approval_file = BASE_PATH / character_slug / "approval_status.json"
    if not approval_file.exists():
        return 0
    try:
        statuses = json.loads(approval_file.read_text())
        return sum(1 for v in statuses.values() if v == "approved")
    except (json.JSONDecodeError, IOError):
        return 0


def _count_pending(character_slug: str) -> int:
    """Count pending images from approval_status.json."""
    approval_file = BASE_PATH / character_slug / "approval_status.json"
    if not approval_file.exists():
        return 0
    try:
        statuses = json.loads(approval_file.read_text())
        return sum(1 for v in statuses.values() if v == "pending")
    except (json.JSONDecodeError, IOError):
        return 0


async def _generate_and_review(character_slug: str, project_name: str = None, count: int = 1):
    """Generate images via the shared pipeline, then trigger vision review.

    This runs as a background asyncio task.
    """
    from .generation import generate_batch

    _reset_daily_if_needed()

    # Check daily limit
    if _daily_counts.get(character_slug, 0) >= MAX_DAILY_PER_CHAR:
        logger.info(f"Replenishment: {character_slug} hit daily limit ({MAX_DAILY_PER_CHAR})")
        return

    # Check consecutive reject limit
    if _consecutive_rejects.get(character_slug, 0) >= MAX_CONSECUTIVE_REJECTS:
        logger.warning(
            f"Replenishment: {character_slug} has {MAX_CONSECUTIVE_REJECTS} consecutive rejects, pausing"
        )
        return

    logger.info(f"Replenishment: generating {count} image(s) for {character_slug}")

    try:
        results = await generate_batch(
            character_slug=character_slug,
            count=count,
        )
    except Exception as e:
        logger.error(f"Replenishment generation error for {character_slug}: {e}")
        return

    # Count new images from results (generate_batch handles copy + register)
    new_images = []
    for r in results:
        new_images.extend(r.get("images", []))

    if not new_images:
        logger.warning(f"Replenishment: no new images for {character_slug} after generation")
        return

    logger.info(f"Replenishment: {len(new_images)} new pending images for {character_slug}")
    _daily_counts[character_slug] = _daily_counts.get(character_slug, 0) + len(new_images)
    _last_generation[character_slug] = time.time()

    # Log the autonomy decision
    approved_now = _count_approved(character_slug)
    await log_decision(
        decision_type="replenishment",
        character_slug=character_slug,
        project_name=project_name,
        input_context={
            "approved_count": approved_now,
            "target": get_target(character_slug),
            "generated": len(new_images),
            "daily_count": _daily_counts.get(character_slug, 0),
        },
        decision_made="generated_images",
        confidence_score=0.9,
        reasoning=(
            f"Character below target ({approved_now}/{get_target(character_slug)}), "
            f"generated {len(new_images)} new images"
        ),
    )

    # Trigger vision review on the new pending images
    await _trigger_vision_review(character_slug, project_name)


async def _trigger_vision_review(character_slug: str, project_name: str = None):
    """Trigger vision review for pending images of a character.

    Calls the vision review function directly (in-process, not via HTTP).
    """
    try:
        from packages.visual_pipeline.router import vision_review
        from packages.core.models import VisionReviewRequest

        request = VisionReviewRequest(
            character_slug=character_slug,
            max_images=10,
            auto_reject_threshold=0.4,
            auto_approve_threshold=0.65,
            regenerate=False,  # Don't cascade regenerations — replenishment handles this
            update_captions=True,
        )

        result = await vision_review(request)

        approved = result.get("auto_approved", 0)
        rejected = result.get("auto_rejected", 0)
        reviewed = result.get("reviewed", 0)

        logger.info(
            f"Replenishment review for {character_slug}: "
            f"{reviewed} reviewed, {approved} approved, {rejected} rejected"
        )

        # Track consecutive rejects for safety cutoff
        if rejected > 0 and approved == 0:
            _consecutive_rejects[character_slug] = (
                _consecutive_rejects.get(character_slug, 0) + rejected
            )
        elif approved > 0:
            _consecutive_rejects[character_slug] = 0  # Reset on any approval

    except Exception as e:
        logger.error(f"Replenishment vision review failed for {character_slug}: {e}")


# ---- EventBus Handler ----

@event_bus.on(IMAGE_APPROVED)
async def _handle_approval_replenishment(data: dict):
    """On approval, check if character needs more images and generate if so."""
    if not _enabled:
        return

    slug = data.get("character_slug")
    if not slug:
        return

    project_name = data.get("project_name")
    target = get_target(slug)
    approved = _count_approved(slug)
    pending = _count_pending(slug)

    # Already at or above target
    if approved >= target:
        logger.debug(f"Replenishment: {slug} at target ({approved}/{target})")
        return

    # Already have pending images waiting for review
    if pending >= 3:
        logger.debug(f"Replenishment: {slug} has {pending} pending, skipping generation")
        return

    # Already running a generation for this character
    if slug in _active_tasks and not _active_tasks[slug].done():
        logger.debug(f"Replenishment: {slug} already has active generation")
        return

    # Check concurrent limit
    active = sum(1 for t in _active_tasks.values() if not t.done())
    if active >= MAX_CONCURRENT:
        logger.debug(f"Replenishment: max concurrent ({MAX_CONCURRENT}) reached")
        return

    # Check cooldown
    last = _last_generation.get(slug, 0)
    if time.time() - last < COOLDOWN_SECONDS:
        logger.debug(f"Replenishment: {slug} in cooldown")
        return

    _reset_daily_if_needed()

    # Check daily limit
    if _daily_counts.get(slug, 0) >= MAX_DAILY_PER_CHAR:
        logger.debug(f"Replenishment: {slug} hit daily limit")
        return

    # How many more do we need? Generate in small batches
    need = target - approved - pending
    batch = min(need, BATCH_SIZE)

    if batch <= 0:
        return

    logger.info(
        f"Replenishment: {slug} needs {need} more "
        f"({approved}/{target} approved, {pending} pending) — generating {batch}"
    )

    # Launch background task
    task = asyncio.create_task(
        _generate_and_review(slug, project_name, count=batch)
    )
    _active_tasks[slug] = task

    # Cleanup reference when done
    def _cleanup(t, s=slug):
        if s in _active_tasks and _active_tasks[s] is t:
            del _active_tasks[s]

    task.add_done_callback(_cleanup)


# ---- Query Functions ----

async def status() -> dict:
    """Get replenishment loop status."""
    _reset_daily_if_needed()

    active = {slug: not task.done() for slug, task in _active_tasks.items()}

    return {
        "enabled": _enabled,
        "default_target": DEFAULT_TARGET,
        "max_concurrent": MAX_CONCURRENT,
        "cooldown_seconds": COOLDOWN_SECONDS,
        "max_daily_per_char": MAX_DAILY_PER_CHAR,
        "max_consecutive_rejects": MAX_CONSECUTIVE_REJECTS,
        "batch_size": BATCH_SIZE,
        "active_generations": active,
        "daily_counts": dict(_daily_counts),
        "consecutive_rejects": {k: v for k, v in _consecutive_rejects.items() if v > 0},
        "last_generation": {
            k: datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
            for k, v in _last_generation.items()
        },
        "target_overrides": dict(_target_override),
    }


async def character_readiness(project_name: str = None) -> list[dict]:
    """Get readiness status for all characters (or those in a project)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if project_name:
                rows = await conn.fetch("""
                    SELECT c.name,
                           REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')),
                                          '[^a-z0-9_-]', '', 'g') as slug,
                           p.name as project_name
                    FROM characters c
                    JOIN projects p ON p.id = c.project_id
                    WHERE p.name = $1
                      AND c.design_prompt IS NOT NULL AND c.design_prompt != ''
                    ORDER BY c.name
                """, project_name)
            else:
                rows = await conn.fetch("""
                    SELECT c.name,
                           REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')),
                                          '[^a-z0-9_-]', '', 'g') as slug,
                           p.name as project_name
                    FROM characters c
                    JOIN projects p ON p.id = c.project_id
                    WHERE c.design_prompt IS NOT NULL AND c.design_prompt != ''
                    ORDER BY p.name, c.name
                """)
    except Exception as e:
        logger.warning(f"Failed to get character readiness: {e}")
        return []

    results = []
    for row in rows:
        slug = row["slug"]
        approved = _count_approved(slug)
        pending = _count_pending(slug)
        target = get_target(slug)

        results.append({
            "name": row["name"],
            "slug": slug,
            "project_name": row["project_name"],
            "approved": approved,
            "pending": pending,
            "target": target,
            "deficit": max(0, target - approved),
            "ready": approved >= target,
            "active_generation": slug in _active_tasks and not _active_tasks[slug].done(),
            "daily_generated": _daily_counts.get(slug, 0),
            "consecutive_rejects": _consecutive_rejects.get(slug, 0),
        })

    return results
