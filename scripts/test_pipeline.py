#!/usr/bin/env python3
"""CLI for production pipeline tests.

Usage:
    python scripts/test_pipeline.py validate --project 66
    python scripts/test_pipeline.py validate --all
    python scripts/test_pipeline.py keyframes --project 66 --shot-types medium,close-up
    python scripts/test_pipeline.py keyframes --project 66 --character soraya
    python scripts/test_pipeline.py keyframes --project 66 --dry-run
    python scripts/test_pipeline.py full --project 66 --character soraya
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def cmd_validate(args):
    from packages.testing.pipeline_test import validate_project_config
    from packages.core.db import connect_direct

    project_ids = []
    if args.all:
        conn = await connect_direct()
        try:
            rows = await conn.fetch("SELECT id, name FROM projects ORDER BY id")
            project_ids = [r["id"] for r in rows]
            print(f"Validating {len(project_ids)} projects...\n")
        finally:
            await conn.close()
    elif args.project:
        project_ids = [args.project]
    else:
        print("Specify --project <id> or --all")
        return

    for pid in project_ids:
        report = await validate_project_config(pid)
        status = "PASS" if report["ok"] else "FAIL"
        print(f"{'='*60}")
        print(f"Project {pid}: {status}")
        print(f"{'='*60}")
        for item in report["pass"]:
            print(f"  [PASS] {item}")
        for item in report["fail"]:
            print(f"  [FAIL] {item}")
        for item in report["warnings"]:
            print(f"  [WARN] {item}")
        print()


async def cmd_keyframes(args):
    from packages.testing.pipeline_test import run_keyframe_test

    if not args.project:
        print("Specify --project <id>")
        return

    character_slugs = None
    if args.character:
        character_slugs = [s.strip() for s in args.character.split(",")]

    shot_types = None
    if args.shot_types:
        shot_types = [s.strip() for s in args.shot_types.split(",")]

    result = await run_keyframe_test(
        args.project,
        character_slugs=character_slugs,
        shot_types=shot_types,
        dry_run=args.dry_run,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"Batch: {result['batch_id']}")
    print(f"Checkpoint: {result['checkpoint']}")
    print(f"Results: {result['passed']} passed, {result['failed']} failed, {result['total']} total\n")

    for r in result["results"]:
        status_icon = "OK" if r["status"] == "generated" else "FAIL" if r["status"] == "failed" else "DRY"
        line = f"  [{status_icon}] {r['character']} / {r['shot_type']}"
        if r.get("clip_score") is not None:
            line += f" (CLIP={r['clip_score']:.0f})"
        if r.get("error"):
            line += f" — {r['error']}"
        if r.get("output_path"):
            line += f"\n         {r['output_path']}"
        print(line)


async def cmd_full(args):
    from packages.testing.pipeline_test import run_pipeline_test

    if not args.project:
        print("Specify --project <id>")
        return

    character_slugs = None
    if args.character:
        character_slugs = [s.strip() for s in args.character.split(",")]

    result = await run_pipeline_test(
        args.project,
        character_slugs=character_slugs,
        include_video=not args.no_video,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"Batch: {result['batch_id']}")
    print(f"Scene: {result['scene_id']}")
    print(f"Characters: {', '.join(result['characters'])}")
    print()

    kf = result.get("keyframe_result", {})
    print(f"Keyframes: {kf.get('generated', 0)} generated, {kf.get('failed', 0)} failed, {kf.get('skipped', 0)} skipped")

    if result.get("video_results"):
        print("\nVideo generation:")
        for v in result["video_results"]:
            print(f"  [{v['status'].upper()}] shot {v['shot_id'][:8]}")
            if v.get("error"):
                print(f"         {v['error']}")


def main():
    parser = argparse.ArgumentParser(description="Production pipeline test CLI")
    sub = parser.add_subparsers(dest="command")

    # validate
    val = sub.add_parser("validate", help="Validate project config")
    val.add_argument("--project", type=int)
    val.add_argument("--all", action="store_true")

    # keyframes
    kf = sub.add_parser("keyframes", help="Test keyframe generation")
    kf.add_argument("--project", type=int, required=True)
    kf.add_argument("--character", type=str, help="Comma-separated character slugs")
    kf.add_argument("--shot-types", type=str, default="medium,close-up")
    kf.add_argument("--dry-run", action="store_true")

    # full
    full = sub.add_parser("full", help="Full pipeline test (keyframe + video)")
    full.add_argument("--project", type=int, required=True)
    full.add_argument("--character", type=str, help="Comma-separated character slugs")
    full.add_argument("--no-video", action="store_true", help="Skip video generation")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd_map = {"validate": cmd_validate, "keyframes": cmd_keyframes, "full": cmd_full}
    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
