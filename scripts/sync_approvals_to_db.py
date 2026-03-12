#!/usr/bin/env python3
"""One-time sync: backfill JSON approval_status.json → DB approvals table.

Reads every character's approval_status.json from datasets/ and inserts
approved images into the approvals DB table (skipping duplicates).
Also emits IMAGE_APPROVED events so learning patterns get updated.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, "/opt/anime-studio")

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATASETS_DIR = Path("/opt/anime-studio/datasets")
DB_DSN = "postgresql://patrick:RP78eIrW7cI2jYvL5akt1yurE@localhost/anime_production"


async def get_char_project_map(conn) -> dict:
    """Build slug → {project_name, checkpoint_model} map from DB."""
    rows = await conn.fetch("""
        SELECT
            REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') AS slug,
            p.name AS project_name,
            p.style_preset AS checkpoint_model,
            c.id AS character_id
        FROM characters c
        JOIN projects p ON c.project_id = p.id
    """)
    return {r["slug"]: dict(r) for r in rows}


async def main():
    conn = await asyncpg.connect(DB_DSN)
    char_map = await get_char_project_map(conn)

    # Get existing approvals to skip duplicates
    existing = set()
    rows = await conn.fetch("SELECT character_slug, image_name FROM approvals")
    for r in rows:
        existing.add((r["character_slug"], r["image_name"]))
    logger.info(f"Existing DB approvals: {len(existing)}")

    total_synced = 0
    total_skipped = 0
    chars_synced = 0

    for char_dir in sorted(DATASETS_DIR.iterdir()):
        if not char_dir.is_dir():
            continue
        approval_file = char_dir / "approval_status.json"
        if not approval_file.exists():
            continue

        slug = char_dir.name
        if slug.startswith("_"):
            continue

        try:
            statuses = json.loads(approval_file.read_text())
        except (json.JSONDecodeError, IOError):
            continue

        approved_images = [
            name for name, st in statuses.items()
            if st == "approved" or (isinstance(st, dict) and st.get("status") == "approved")
        ]
        if not approved_images:
            continue

        db_info = char_map.get(slug, {})
        project_name = db_info.get("project_name", "")
        checkpoint = db_info.get("checkpoint_model", "")

        char_synced = 0
        for img_name in approved_images:
            if (slug, img_name) in existing:
                total_skipped += 1
                continue

            # Read quality from meta if available
            meta_path = char_dir / "images" / (Path(img_name).stem + ".meta.json")
            quality_score = 0.75  # default for historical manual approvals
            vision_review = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    quality_score = meta.get("quality_score", 0.75)
                    vr = meta.get("vision_review") or meta.get("llava_review")
                    if vr:
                        vision_review = json.dumps(vr)
                except (json.JSONDecodeError, IOError):
                    pass

            await conn.execute("""
                INSERT INTO approvals
                    (character_slug, project_name, image_name,
                     quality_score, auto_approved, vision_review, checkpoint_model)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
            """,
                slug, project_name, img_name,
                quality_score, False, vision_review, checkpoint,
            )
            char_synced += 1

        if char_synced > 0:
            chars_synced += 1
            total_synced += char_synced
            logger.info(f"  {slug}: synced {char_synced} approvals (project: {project_name or 'unknown'})")

    # Also backfill learned_patterns from the newly synced approvals
    logger.info("Updating learned_patterns from synced approvals...")
    await conn.execute("""
        INSERT INTO learned_patterns
            (character_slug, project_name, pattern_type, checkpoint_model,
             quality_score_avg, frequency)
        SELECT
            a.character_slug,
            a.project_name,
            'success',
            a.checkpoint_model,
            AVG(a.quality_score),
            COUNT(*)
        FROM approvals a
        WHERE a.character_slug IS NOT NULL
        GROUP BY a.character_slug, a.project_name, a.checkpoint_model
        ON CONFLICT DO NOTHING
    """)

    await conn.close()

    logger.info(f"\nSync complete:")
    logger.info(f"  Characters synced: {chars_synced}")
    logger.info(f"  Approvals inserted: {total_synced}")
    logger.info(f"  Already in DB (skipped): {total_skipped}")


if __name__ == "__main__":
    asyncio.run(main())
