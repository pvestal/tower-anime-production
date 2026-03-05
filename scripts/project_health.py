#!/usr/bin/env python3
"""Project health check — QA dashboard for anime-studio shots."""
import argparse
import json
import os
import subprocess
import sys

DB_PASS = os.environ.get("PGPASSWORD", "RP78eIrW7cI2jYvL5akt1yurE")


def db_query(sql):
    result = subprocess.run(
        ["psql", "-h", "localhost", "-U", "patrick", "-d", "anime_production", "-t", "-A", "-c", sql],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": DB_PASS},
    )
    return result.stdout.strip()


def run_health(project_id):
    print(f"\n{'='*70}")
    print(f"  PROJECT HEALTH CHECK — Project {project_id}")
    print(f"{'='*70}")

    # 1. Status by engine
    print(f"\n  STATUS BY ENGINE:")
    rows = db_query(f"""
        SELECT s.video_engine, s.status, COUNT(*),
               ROUND(SUM(s.duration_seconds)::numeric, 1)
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id}
        GROUP BY s.video_engine, s.status
        ORDER BY s.video_engine, s.status
    """)
    total_shots = 0
    total_seconds = 0
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        engine, status, count, dur = parts[0], parts[1], int(parts[2]), float(parts[3])
        icon = "✓" if status == "completed" else "○" if status == "pending" else "✗"
        print(f"    {icon} {engine:15s} {status:12s} {count:4d} shots  ({dur:.0f}s)")
        total_shots += count
        total_seconds += dur
    print(f"    {'─'*55}")
    print(f"    TOTAL: {total_shots} shots, {total_seconds:.0f}s ({total_seconds/60:.1f} min)")

    # 2. Completed but no video file on disk
    print(f"\n  GHOST VIDEOS (completed but file missing):")
    rows = db_query(f"""
        SELECT s.shot_number, sc.scene_number, s.output_video_path
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id}
          AND s.status = 'completed' AND s.output_video_path IS NOT NULL
        ORDER BY sc.scene_number, s.shot_number
    """)
    ghost_count = 0
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        shot_num, scene_num, vpath = parts[0], parts[1], parts[2]
        if vpath and not os.path.exists(vpath):
            print(f"    MISSING: Scene {scene_num} Shot {shot_num} → {vpath}")
            ghost_count += 1
    if ghost_count == 0:
        print(f"    None — all video files exist on disk")
    else:
        print(f"    {ghost_count} ghost video(s)")

    # 3. Stale error messages
    print(f"\n  STALE ERRORS (completed + error_message):")
    stale = db_query(f"""
        SELECT COUNT(*) FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id}
          AND s.status = 'completed' AND s.error_message IS NOT NULL AND s.error_message != ''
    """)
    print(f"    {stale} shot(s) with stale error messages")

    # 4. Failed shots
    print(f"\n  FAILED SHOTS:")
    rows = db_query(f"""
        SELECT s.shot_number, sc.scene_number, s.video_engine, LEFT(s.error_message, 80)
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id} AND s.status = 'failed'
        ORDER BY sc.scene_number, s.shot_number
    """)
    if not rows.strip():
        print(f"    None")
    else:
        for line in rows.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            print(f"    Scene {parts[1]} Shot {parts[0]} [{parts[2]}] — {parts[3]}")

    # 5. Prompt quality
    print(f"\n  PROMPT QUALITY:")
    rows = db_query(f"""
        SELECT
            CASE
                WHEN generation_prompt IS NULL OR generation_prompt = '' THEN 'empty'
                WHEN LENGTH(generation_prompt) < 80 THEN 'bare (<80)'
                WHEN LENGTH(generation_prompt) < 200 THEN 'short (80-200)'
                ELSE 'rich (200+)'
            END as quality,
            COUNT(*)
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id}
        GROUP BY 1 ORDER BY 1
    """)
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        quality, count = parts[0], parts[1]
        warn = " ⚠" if quality in ("empty", "bare (<80)") else ""
        print(f"    {quality:20s} {count:4s} shots{warn}")

    # 6. Missing source images for I2V engines
    print(f"\n  MISSING SOURCE IMAGES (I2V engines need keyframes):")
    rows = db_query(f"""
        SELECT s.shot_number, sc.scene_number, s.video_engine, s.status
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id}
          AND s.video_engine IN ('framepack', 'framepack_f1', 'wan22_14b', 'wan22')
          AND (s.source_image_path IS NULL OR s.source_image_path = '')
          AND s.status != 'completed'
        ORDER BY sc.scene_number, s.shot_number
    """)
    if not rows.strip():
        print(f"    None — all pending I2V shots have source images (or will auto-generate)")
    else:
        missing = 0
        for line in rows.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            print(f"    Scene {parts[1]} Shot {parts[0]} [{parts[2]}] status={parts[3]}")
            missing += 1
        print(f"    {missing} shot(s) need keyframe generation")

    # 7. Shot type distribution
    print(f"\n  SHOT TYPE DISTRIBUTION:")
    rows = db_query(f"""
        SELECT s.shot_type, COUNT(*),
               SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) as done
        FROM shots s JOIN scenes sc ON s.scene_id = sc.id
        WHERE sc.project_id = {project_id}
        GROUP BY s.shot_type ORDER BY COUNT(*) DESC
    """)
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        stype, total, done = parts[0], int(parts[1]), int(parts[2])
        pct = (done / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {stype:15s} {done:3d}/{total:3d} {bar} {pct:.0f}%")

    print(f"\n{'='*70}\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project health check")
    parser.add_argument("--project", type=int, default=42, help="Project ID (default: 42)")
    args = parser.parse_args()
    sys.exit(run_health(args.project))
