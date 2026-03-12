#!/usr/bin/env python3
"""Sync feedback.json rejections → DB rejections table."""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, "/opt/anime-studio")

from packages.core.db import get_pool
from packages.core.config import BASE_PATH

logging.basicConfig(level=logging.INFO, format="%(message)s")


async def main():
    pool = await get_pool()

    # Get existing DB rejections
    async with pool.acquire() as conn:
        existing = set()
        rows = await conn.fetch("SELECT character_slug, image_name FROM rejections")
        for r in rows:
            existing.add((r["character_slug"], r["image_name"]))
        print(f"Existing DB rejections: {len(existing)}")

    # Get char→project mapping
    async with pool.acquire() as conn:
        char_rows = await conn.fetch(
            "SELECT REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') AS slug,"
            " p.name AS project_name, p.style_preset AS checkpoint"
            " FROM characters c JOIN projects p ON c.project_id = p.id"
        )
        char_map = {r["slug"]: dict(r) for r in char_rows}

    total = 0
    for char_dir in sorted(BASE_PATH.iterdir()):
        if not char_dir.is_dir():
            continue
        fb_file = char_dir / "feedback.json"
        if not fb_file.exists():
            continue
        slug = char_dir.name
        if slug.startswith("_"):
            continue

        try:
            data = json.loads(fb_file.read_text())
        except (json.JSONDecodeError, IOError):
            continue

        rejections = data.get("rejections", [])
        if not rejections:
            continue

        info = char_map.get(slug, {})
        project_name = info.get("project_name", "")
        checkpoint = info.get("checkpoint", "")

        synced = 0
        async with pool.acquire() as conn:
            for rej in rejections:
                img = rej.get("image", "")
                if not img or (slug, img) in existing:
                    continue
                cats = rej.get("categories", [])
                if not cats:
                    fb = rej.get("feedback", "")
                    if "batch_solo_false" in fb or "not_solo" in fb:
                        cats = ["not_solo"]
                    elif "bad_quality" in fb or "batch_no_vision" in fb or "low_quality" in fb:
                        cats = ["bad_quality"]
                    elif "wrong_appearance" in fb:
                        cats = ["wrong_appearance"]
                    else:
                        cats = ["wrong_appearance"]

                await conn.execute(
                    "INSERT INTO rejections (character_slug, project_name, image_name,"
                    " categories, feedback_text, source, checkpoint_model)"
                    " VALUES ($1, $2, $3, $4, $5, $6, $7)"
                    " ON CONFLICT DO NOTHING",
                    slug, project_name, img, cats,
                    rej.get("feedback", ""), "manual_sync", checkpoint,
                )
                synced += 1

        if synced:
            total += synced
            print(f"  {slug}: synced {synced} rejections")

    print(f"\nTotal synced: {total}")


if __name__ == "__main__":
    asyncio.run(main())
