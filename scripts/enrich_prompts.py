#!/usr/bin/env python3
"""Enrich thin generation_prompts using character data and scene context.

Finds shots with short prompts (<200 chars) and expands them by:
1. Adding character physical descriptions from the characters table
2. Adding scene location/mood/time_of_day context
3. Appending shot_type framing cues
4. Adding project style tags

Usage:
    python scripts/enrich_prompts.py --project 42              # dry run
    python scripts/enrich_prompts.py --project 42 --apply      # actually update DB
    python scripts/enrich_prompts.py --project 42 --scene 19   # specific scene
"""
import argparse
import os
import subprocess
import sys

DB_PASS = os.environ.get("PGPASSWORD", "RP78eIrW7cI2jYvL5akt1yurE")


def db_query(sql, single=False):
    result = subprocess.run(
        ["psql", "-h", "localhost", "-U", "patrick", "-d", "anime_production", "-t", "-A", "-c", sql],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": DB_PASS},
    )
    out = result.stdout.strip()
    if single:
        return out
    return out


def db_rows(sql):
    """Return list of dicts from a query."""
    # Get column names
    result = subprocess.run(
        ["psql", "-h", "localhost", "-U", "patrick", "-d", "anime_production",
         "-t", "-A", "--csv", "-c", sql],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": DB_PASS},
    )
    lines = result.stdout.strip().split("\n")
    if not lines or not lines[0]:
        return []
    # CSV output: first line is data (no headers with -t)
    # Use pipe-separated format instead
    result2 = subprocess.run(
        ["psql", "-h", "localhost", "-U", "patrick", "-d", "anime_production",
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": DB_PASS},
    )
    return result2.stdout.strip()


def get_project_style(project_id):
    """Get project style info."""
    row = db_query(f"""
        SELECT p.name, p.genre, p.premise,
               gs.positive_prompt_template, gs.negative_prompt_template,
               gs.checkpoint_model
        FROM projects p
        LEFT JOIN generation_styles gs ON p.default_style = gs.style_name
        WHERE p.id = {project_id}
    """, single=True)
    if not row:
        return {}
    parts = row.split("|")
    return {
        "name": parts[0], "genre": parts[1], "premise": parts[2],
        "positive_template": parts[3], "negative_template": parts[4],
        "checkpoint": parts[5],
    }


def get_character_descriptions(project_id):
    """Get all character descriptions for the project."""
    rows = db_query(f"""
        SELECT
            REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug,
            name, design_prompt
        FROM characters
        WHERE project_id = {project_id} AND design_prompt IS NOT NULL AND design_prompt != ''
    """)
    chars = {}
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        slug = parts[0]
        name = parts[1]
        design = parts[2]
        chars[slug] = {"name": name, "design_prompt": design}
    return chars


def get_thin_shots(project_id, scene_number=None, threshold=200):
    """Find shots with generation_prompts shorter than threshold."""
    where = f"sc.project_id = {project_id} AND LENGTH(s.generation_prompt) < {threshold}"
    if scene_number:
        where += f" AND sc.scene_number = {scene_number}"

    rows = db_query(f"""
        SELECT s.id, s.shot_number, s.shot_type, s.camera_angle,
               sc.scene_number, sc.title, sc.description, sc.location, sc.time_of_day, sc.mood,
               s.generation_prompt, s.motion_prompt,
               array_to_string(s.characters_present, ',')
        FROM shots s
        JOIN scenes sc ON s.scene_id = sc.id
        WHERE {where}
        ORDER BY sc.scene_number, s.shot_number
    """)

    shots = []
    for line in rows.split("\n"):
        if not line.strip():
            continue
        p = line.split("|")
        shots.append({
            "id": p[0], "shot_number": int(p[1]), "shot_type": p[2], "camera_angle": p[3],
            "scene_number": int(p[4]), "scene_title": p[5], "scene_desc": p[6],
            "location": p[7], "time_of_day": p[8], "mood": p[9],
            "generation_prompt": p[10], "motion_prompt": p[11],
            "characters": p[12].split(",") if p[12] else [],
        })
    return shots


def build_enriched_prompt(shot, char_db, project_style):
    """Build a rich prompt from shot + character + scene data."""
    parts = []

    # 1. Scene action (existing generation_prompt is the core)
    scene_action = shot["generation_prompt"].strip().rstrip(".")
    parts.append(scene_action + ".")

    # 2. Character descriptions (from design_prompt, condensed)
    char_parts = []
    for slug in shot["characters"]:
        slug = slug.strip()
        if slug in char_db:
            c = char_db[slug]
            design = c["design_prompt"].strip()
            # Truncate very long design prompts to key physical traits
            if len(design) > 300:
                design = design[:300].rsplit(",", 1)[0]
            char_parts.append(f"{c['name']} ({design})")

    if char_parts:
        parts.append("; ".join(char_parts) + ".")

    # 3. Scene context (location, time, mood)
    context = []
    if shot["location"]:
        context.append(shot["location"])
    if shot["time_of_day"]:
        context.append(shot["time_of_day"])
    if shot["mood"]:
        context.append(shot["mood"])
    if context:
        parts.append(", ".join(context) + ".")

    # 4. Style tags from project
    style_tags = "anime style, detailed animation, cinematic"
    if project_style.get("genre"):
        style_tags = f"{project_style['genre']}, {style_tags}"
    parts.append(style_tags)

    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Enrich thin generation prompts")
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--scene", type=int, help="Specific scene number")
    parser.add_argument("--threshold", type=int, default=200, help="Max prompt length to enrich (default: 200)")
    parser.add_argument("--apply", action="store_true", help="Actually update the DB (default: dry run)")
    parser.add_argument("--limit", type=int, help="Max shots to process")
    args = parser.parse_args()

    project_style = get_project_style(args.project)
    print(f"\nProject: {project_style.get('name', '?')} ({project_style.get('genre', '?')})")
    print(f"Checkpoint: {project_style.get('checkpoint', '?')}")

    char_db = get_character_descriptions(args.project)
    print(f"Characters with descriptions: {len(char_db)}")

    shots = get_thin_shots(args.project, args.scene, args.threshold)
    total_found = len(shots)
    if args.limit:
        shots = shots[:args.limit]

    print(f"Shots with prompts < {args.threshold} chars: {total_found} (processing {len(shots)})")

    if not shots:
        print("Nothing to enrich!")
        return

    updated = 0
    for shot in shots:
        enriched = build_enriched_prompt(shot, char_db, project_style)

        print(f"\n{'─'*60}")
        print(f"  Scene {shot['scene_number']} Shot {shot['shot_number']} [{shot['shot_type']}]")
        print(f"  BEFORE ({len(shot['generation_prompt'])} chars):")
        print(f"    {shot['generation_prompt'][:120]}")
        print(f"  AFTER ({len(enriched)} chars):")
        print(f"    {enriched[:200]}...")

        if args.apply:
            # Escape single quotes for SQL
            safe_prompt = enriched.replace("'", "''")
            db_query(f"UPDATE shots SET generation_prompt = '{safe_prompt}' WHERE id = '{shot['id']}'")
            updated += 1

    print(f"\n{'='*60}")
    if args.apply:
        print(f"  UPDATED {updated} shots")
    else:
        print(f"  DRY RUN — would update {len(shots)} shots. Use --apply to commit.")


if __name__ == "__main__":
    main()
