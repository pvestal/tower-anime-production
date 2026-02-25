"""Replenishment loop — autonomous image generation to reach target approved counts.

Two modes of operation:

1. Event-driven (reactive): On IMAGE_APPROVED, checks if character still needs
   more images and generates a small batch if so. Requires enable(True).

2. Proactive fill (fill_deficit): POST /api/training/replenish kicks off a
   background task that scans all characters below target and runs
   generate → review → loop until target is reached or safety limits hit.

Flow:
    generate → ComfyUI → datasets → register pending
    → vision review → auto-approve/reject → re-check count → (repeat if below target)

Safety:
    - Off by default (event-driven must explicitly enable)
    - Max concurrent generations
    - Per-character cooldown
    - Daily generation limit per character
    - Max consecutive rejects before giving up on a character
    - Max iterations per character per fill_deficit run
"""

import asyncio
import json
import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BASE_PATH
from .db import get_pool
from .events import event_bus, IMAGE_APPROVED
from .audit import log_decision

logger = logging.getLogger(__name__)

# --- Configuration ---
DEFAULT_TARGET = 50       # approved images per character (need 50+ for LoRA training)
MAX_CONCURRENT = 2        # max parallel generation subprocesses
COOLDOWN_SECONDS = 30     # min seconds between generations for same character
MAX_DAILY_PER_CHAR = 50   # max images generated per character per day
MAX_CONSECUTIVE_REJECTS = 5  # stop if N consecutive images rejected
BATCH_SIZE = 5            # images per generation round
MAX_ITERATIONS_PER_CHAR = 10  # max generate→review loops per fill_deficit run

# --- State ---
_enabled = False
_target_override: dict[str, int] = {}       # character_slug → custom target
_active_tasks: dict[str, asyncio.Task] = {} # character_slug → running task
_last_generation: dict[str, float] = {}     # character_slug → timestamp
_daily_counts: dict[str, int] = {}          # character_slug → count today
_daily_reset_date: str = ""                 # YYYY-MM-DD of last reset
_consecutive_rejects: dict[str, int] = {}   # character_slug → consecutive reject count
_review_thresholds: dict[str, tuple[float, float]] = {}  # character_slug → (reject, approve)

# --- Replenish task tracking ---
_replenish_tasks: dict[str, dict] = {}  # task_id → progress dict


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


def _image_brightness(img_path: Path) -> float:
    """Quick average brightness of an image (0.0=black, 1.0=white).

    Uses PIL if available, falls back to 0.5 (neutral) if not.
    Good IP-Adapter references should be well-lit (brightness > 0.3).
    """
    try:
        from PIL import Image
        img = Image.open(img_path).convert("L")  # grayscale
        pixels = list(img.getdata())
        return sum(pixels) / (len(pixels) * 255.0)
    except Exception:
        return 0.5


def _sync_reference_images(character_slug: str, max_refs: int = 5) -> int:
    """Pick the best solo-approved images as IP-Adapter references.

    Scans all approved images, filters to solo-only (multi-character refs confuse
    IP-Adapter), scores by quality + brightness + composition, and copies top N
    to reference_images/. Dark, close-up, and generated images are penalized.
    Returns the number of reference images synced.
    """
    image_dir = BASE_PATH / character_slug / "images"
    ref_dir = BASE_PATH / character_slug / "reference_images"
    ref_dir.mkdir(parents=True, exist_ok=True)

    approval_file = BASE_PATH / character_slug / "approval_status.json"
    if not approval_file.exists():
        return 0
    try:
        approvals = json.loads(approval_file.read_text())
    except (json.JSONDecodeError, IOError):
        return 0

    approved = [k for k, v in approvals.items() if v == "approved"]
    if not approved:
        return 0

    candidates = []
    for img_name in approved:
        img_path = image_dir / img_name
        if not img_path.exists():
            continue

        meta_path = image_dir / img_name.replace(".png", ".meta.json")
        score = 0.5  # default score if no vision review data

        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, IOError):
                meta = {}
            vr = meta.get("vision_review", {})
            is_solo = vr.get("solo", True)
            # quality_score lives at top level of meta.json (not inside vision_review)
            quality = meta.get("quality_score") or vr.get("quality_score")
            if quality is not None:
                score = quality

            # Skip non-solo images — multi-character refs confuse IP-Adapter
            if not is_solo:
                continue

        # Prefer images with completeness=full (not close-ups/partial)
        completeness = vr.get("completeness", "") if meta_path.exists() else ""
        if completeness == "full":
            score += 0.15
        elif completeness == "face":
            score -= 0.1  # penalize face-only close-ups as references

        # Never use generated images as references when source frames exist
        # Generated images are derivative — feeding them back creates quality decay
        if img_name.startswith("gen_"):
            score -= 1.0  # effectively eliminates them unless no source frames exist

        # Brightness check — dark scenes make terrible IP-Adapter references
        brightness = _image_brightness(img_path)
        if brightness < 0.2:
            score -= 0.3  # very dark — heavily penalize
        elif brightness < 0.3:
            score -= 0.15  # dim
        elif brightness > 0.4:
            score += 0.1  # well-lit — bonus

        candidates.append((img_name, score, img_path))

    # Sort by score descending, take top N
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = candidates[:max_refs]

    # Clear old refs, copy new ones
    for old in ref_dir.glob("*.png"):
        old.unlink()
    for old in ref_dir.glob("*.jpg"):
        old.unlink()

    for name, _score, path in selected:
        shutil.copy2(path, ref_dir / name)

    if selected:
        logger.info(
            f"Replenishment: synced {len(selected)} reference images for {character_slug} "
            f"(scores: {', '.join(f'{s[1]:.2f}' for s in selected)})"
        )

    return len(selected)


async def _generate_and_review(character_slug: str, project_name: str = None, count: int = 1):
    """Generate images via the shared pipeline, then trigger vision review.

    This runs as a background asyncio task.
    """
    from .generation import generate_batch

    _reset_daily_if_needed()

    # Check daily limit
    if _daily_counts.get(character_slug, 0) >= MAX_DAILY_PER_CHAR:
        logger.info(f"Replenishment: {character_slug} hit daily limit ({MAX_DAILY_PER_CHAR})")
        return {"generated": 0, "approved": 0, "rejected": 0}

    # Check consecutive reject limit
    if _consecutive_rejects.get(character_slug, 0) >= MAX_CONSECUTIVE_REJECTS:
        logger.warning(
            f"Replenishment: {character_slug} has {MAX_CONSECUTIVE_REJECTS} consecutive rejects, pausing"
        )
        return {"generated": 0, "approved": 0, "rejected": 0}

    # Sync reference images from approved pool before generating
    ref_count = _sync_reference_images(character_slug)
    logger.info(f"Replenishment: {ref_count} reference images available for {character_slug}")

    logger.info(f"Replenishment: generating {count} image(s) for {character_slug}")

    try:
        results = await generate_batch(
            character_slug=character_slug,
            count=count,
        )
    except Exception as e:
        logger.error(f"Replenishment generation error for {character_slug}: {e}")
        return {"generated": 0, "approved": 0, "rejected": 0}

    # Count new images from results (generate_batch handles copy + register)
    new_images = []
    for r in results:
        new_images.extend(r.get("images", []))

    if not new_images:
        logger.warning(f"Replenishment: no new images for {character_slug} after generation")
        return {"generated": 0, "approved": 0, "rejected": 0}

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

    # Trigger vision review on the new pending images and wait for results
    review_result = await _trigger_vision_review(character_slug, project_name)
    return {
        "generated": len(new_images),
        "approved": review_result.get("approved", 0),
        "rejected": review_result.get("rejected", 0),
    }


def set_review_thresholds(character_slug: str, reject: float, approve: float):
    """Set per-character vision review thresholds for replenishment."""
    _review_thresholds[character_slug] = (reject, approve)


async def _trigger_vision_review(
    character_slug: str, project_name: str = None
) -> dict:
    """Trigger vision review and wait for completion.

    Calls vision_review() which launches a background worker, then polls
    the task until it finishes so we get actual approved/rejected counts.

    Returns dict with keys: approved, rejected, reviewed.
    """
    try:
        from packages.visual_pipeline.visual_review import vision_review, _vision_tasks
        from packages.core.models import VisionReviewRequest

        # Use per-character thresholds if set, else module defaults
        reject_th, approve_th = _review_thresholds.get(
            character_slug, (0.3, 0.92)
        )

        request = VisionReviewRequest(
            character_slug=character_slug,
            max_images=10,
            auto_reject_threshold=reject_th,
            auto_approve_threshold=approve_th,
            regenerate=False,  # Don't cascade regenerations — replenishment handles this
            update_captions=True,
        )

        result = await vision_review(request)
        task_id = result.get("task_id")

        if not task_id:
            logger.warning(f"Vision review returned no task_id for {character_slug}")
            return {"approved": 0, "rejected": 0, "reviewed": 0}

        # Poll the vision task until it completes (max 10 min)
        max_wait = 600
        waited = 0
        poll_interval = 3
        while waited < max_wait:
            task_info = _vision_tasks.get(task_id, {})
            if task_info.get("status") != "running":
                break
            await asyncio.sleep(poll_interval)
            waited += poll_interval

        task_info = _vision_tasks.get(task_id, {})
        approved = task_info.get("auto_approved", 0)
        rejected = task_info.get("auto_rejected", 0)
        reviewed = task_info.get("reviewed", 0)

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

        return {"approved": approved, "rejected": rejected, "reviewed": reviewed}

    except Exception as e:
        logger.error(f"Replenishment vision review failed for {character_slug}: {e}")
        return {"approved": 0, "rejected": 0, "reviewed": 0}


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


# ---- Proactive Fill ----

async def fill_deficit(
    project_name: str = None,
    target: int = DEFAULT_TARGET,
    batch_size: int = BATCH_SIZE,
    max_iterations: int = MAX_ITERATIONS_PER_CHAR,
    auto_reject_threshold: float = 0.25,
    auto_approve_threshold: float = 0.7,
    strategy: str = "auto",
) -> str:
    """Proactively fill all characters below target. Returns task_id for polling.

    This is the entry point for POST /api/training/replenish. It runs as a
    background asyncio task, generating and reviewing in a loop per character
    until target is reached or safety limits are hit.
    """
    from .db import get_char_project_map

    task_id = uuid.uuid4().hex[:8]
    char_map = await get_char_project_map()

    # Filter to project if specified
    if project_name:
        slugs = [
            slug for slug, info in char_map.items()
            if info.get("project_name") == project_name
            and info.get("design_prompt")
        ]
    else:
        slugs = [
            slug for slug, info in char_map.items()
            if info.get("design_prompt")
        ]

    if not slugs:
        _replenish_tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "message": "No characters found with design prompts",
            "characters": {},
        }
        return task_id

    # Build initial progress list, sorted by deficit ascending (closest to target first)
    char_list = []
    for slug in slugs:
        approved = _count_approved(slug)
        if approved >= target:
            continue
        char_list.append((slug, approved))
    char_list.sort(key=lambda x: x[1], reverse=True)  # highest approved first

    characters_progress = {}
    for slug, approved in char_list:
        characters_progress[slug] = {
            "slug": slug,
            "name": char_map[slug].get("name", slug),
            "project_name": char_map[slug].get("project_name", ""),
            "approved_before": approved,
            "approved_now": approved,
            "target": target,
            "generated": 0,
            "reviewed": 0,
            "iterations": 0,
            "status": "pending",
        }

    _replenish_tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "project_name": project_name,
        "target": target,
        "batch_size": batch_size,
        "strategy": strategy,
        "characters": characters_progress,
    }

    # Set per-character review thresholds
    for slug in characters_progress:
        set_review_thresholds(slug, auto_reject_threshold, auto_approve_threshold)

    # Launch background worker
    asyncio.create_task(_fill_deficit_worker(
        task_id, characters_progress, char_map,
        target, batch_size, max_iterations, strategy,
    ))

    return task_id


async def _fill_deficit_worker(
    task_id: str,
    characters_progress: dict,
    char_map: dict,
    target: int,
    batch_size: int,
    max_iterations: int,
    strategy: str,
):
    """Background worker that loops generate→review per character until target met."""
    task = _replenish_tasks[task_id]

    try:
        for slug, progress in characters_progress.items():
            progress["status"] = "running"

            project_name = char_map[slug].get("project_name")
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                progress["iterations"] = iteration

                # Re-check current approved count
                approved = _count_approved(slug)
                progress["approved_now"] = approved

                if approved >= target:
                    progress["status"] = "target_reached"
                    logger.info(f"fill_deficit: {slug} reached target ({approved}/{target})")
                    break

                # Check consecutive rejects
                if _consecutive_rejects.get(slug, 0) >= MAX_CONSECUTIVE_REJECTS:
                    progress["status"] = "consecutive_rejects"
                    logger.warning(f"fill_deficit: {slug} hit consecutive reject limit")
                    break

                # Skip if too many pending (wait for review to clear)
                pending = _count_pending(slug)
                if pending >= batch_size:
                    # Just run review on existing pending, don't generate more
                    logger.info(f"fill_deficit: {slug} has {pending} pending, reviewing only")
                    review = await _trigger_vision_review(slug, project_name)
                    progress["reviewed"] += review.get("reviewed", 0)
                    continue

                # Determine batch size based on deficit
                deficit = target - approved - pending
                count = min(deficit, batch_size)
                if count <= 0:
                    # Only pending images remain to review
                    review = await _trigger_vision_review(slug, project_name)
                    progress["reviewed"] += review.get("reviewed", 0)
                    continue

                # Generate and review
                result = await _generate_and_review(slug, project_name, count=count)
                progress["generated"] += result.get("generated", 0)
                progress["reviewed"] += result.get("approved", 0) + result.get("rejected", 0)

                # Update approved count after review
                progress["approved_now"] = _count_approved(slug)

                # Brief cooldown between iterations
                if progress["approved_now"] < target:
                    await asyncio.sleep(COOLDOWN_SECONDS)

            # If we exited the loop without reaching target or hitting a limit
            if progress["status"] == "running":
                progress["status"] = "max_iterations"
                progress["approved_now"] = _count_approved(slug)

        task["status"] = "completed"
        task["finished_at"] = datetime.now(timezone.utc).isoformat()

        # Summary log
        total_generated = sum(p["generated"] for p in characters_progress.values())
        reached = sum(1 for p in characters_progress.values() if p["status"] == "target_reached")
        logger.info(
            f"fill_deficit [{task_id}]: completed — {total_generated} images generated, "
            f"{reached}/{len(characters_progress)} characters reached target"
        )

    except Exception as e:
        logger.error(f"fill_deficit [{task_id}] error: {e}", exc_info=True)
        task["status"] = "error"
        task["error"] = str(e)
        task["finished_at"] = datetime.now(timezone.utc).isoformat()


def get_replenish_task(task_id: str) -> dict | None:
    """Get a replenish task by ID."""
    return _replenish_tasks.get(task_id)


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
