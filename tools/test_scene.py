"""Interactive test script for shot enrichment + generation pipeline.

Usage:
    python -m tools.test_scene <scene_id> [--limit N] [--mode autopilot|direct] [--dry-run] [--shot SHOT_ID]

Examples:
    # Test enrichment only (no actual generation)
    python -m tools.test_scene ac4e9026-abe2-40fc-ad70-6c5384045a49 --dry-run

    # Generate 2 shots in direct mode
    python -m tools.test_scene ac4e9026-abe2-40fc-ad70-6c5384045a49 --limit 2 --mode direct

    # Test a single shot by ID
    python -m tools.test_scene ac4e9026-abe2-40fc-ad70-6c5384045a49 --shot cfdef8ec-a1a5-4eb5-a4eb-ae0f11b859d1

Does NOT change default behavior of the UI or APIs.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.core.db import connect_direct
from packages.core.config import COMFYUI_OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_scene")


def header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def subheader(text: str):
    print(f"\n--- {text} ---")


def kv(key: str, value, indent: int = 2):
    prefix = " " * indent
    if value is None:
        print(f"{prefix}{key}: (none)")
    elif isinstance(value, list):
        print(f"{prefix}{key}: [{', '.join(str(v) for v in value[:5])}]{'...' if len(value) > 5 else ''}")
    elif isinstance(value, dict):
        print(f"{prefix}{key}: {json.dumps(value, default=str)[:120]}")
    else:
        print(f"{prefix}{key}: {value}")


async def test_enrichment(conn, scene_id: uuid.UUID, shot_row: dict, scene_ctx: dict, prev_shots: list) -> dict:
    """Run shot spec enrichment and print results."""
    from packages.scene_generation.shot_spec import enrich_shot_spec

    subheader(f"Enriching shot {shot_row['shot_number']} ({shot_row['shot_type']})")
    kv("Before pose_type", shot_row.get("pose_type"))
    kv("Before prompt", (shot_row.get("generation_prompt") or "")[:80] + "...")

    start = time.time()
    result = await enrich_shot_spec(conn, dict(shot_row), scene_ctx, prev_shots)
    elapsed = time.time() - start

    kv("After pose_type", result.get("pose_type"))
    kv("must_differ_from", result.get("must_differ_from"))
    kv("After prompt", (result.get("generation_prompt") or "")[:120] + "...")
    kv("After negative", (result.get("generation_negative") or "")[:120] + "...")
    kv("Enrichment time", f"{elapsed:.1f}s")
    return result


async def test_variety_check(conn, shot_id: uuid.UUID, scene_id: uuid.UUID, image_path: str | None) -> dict:
    """Run variety check and print results."""
    from packages.scene_generation.variety_check import check_sequence_variety

    subheader("Variety Check")
    if not image_path or not Path(image_path).exists():
        print("  (skipped — no output image to compare)")
        return {}

    start = time.time()
    result = await check_sequence_variety(conn, shot_id, scene_id, image_path)
    elapsed = time.time() - start

    kv("Similar?", result["similar"])
    kv("Similarity score", f"{result['similarity_score']:.4f}")
    kv("Most similar to", result["most_similar_shot_id"])
    kv("Suggestion", result["suggestion"])
    kv("Check time", f"{elapsed:.1f}s")
    return result


async def check_graph_node(shot_id_str: str):
    """Check if a Generation node exists in the AGE graph for this shot."""
    from packages.core.graph_sync import _get_conn, _cypher, _esc

    subheader("Graph Check")
    gen_id = f"gen_{shot_id_str}"
    conn = await _get_conn()
    try:
        result = await _cypher(conn, f"MATCH (g:Generation {{gen_id: {_esc(gen_id)}}}) RETURN g")
        if result:
            print(f"  Generation node EXISTS: {gen_id}")
            return True
        else:
            print(f"  Generation node NOT FOUND: {gen_id}")
            return False
    except Exception as e:
        print(f"  Graph query failed: {e}")
        return False
    finally:
        await conn.close()


async def run_test(args):
    scene_id = uuid.UUID(args.scene_id)
    conn = await connect_direct()

    try:
        # Load scene context
        scene = await conn.fetchrow("SELECT * FROM scenes WHERE id = $1", scene_id)
        if not scene:
            print(f"Scene {args.scene_id} not found")
            return

        project = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1", scene["project_id"]
        )

        header(f"Test Scene: {scene['title']}")
        kv("Project", project["name"] if project else "?")
        kv("Scene ID", str(scene_id))
        kv("Location", scene.get("location"))
        kv("Mood", scene.get("mood"))
        kv("Mode", args.mode)
        kv("Dry run", args.dry_run)

        # Get scene context for enrichment
        from packages.scene_generation.shot_spec import get_scene_context, get_recent_shots
        scene_ctx = await get_scene_context(conn, scene_id)
        prev_shots = await get_recent_shots(conn, scene_id, limit=5)

        # Load shots
        if args.shot:
            shot_id = uuid.UUID(args.shot)
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE id = $1 AND scene_id = $2", shot_id, scene_id
            )
        else:
            shots = await conn.fetch(
                "SELECT * FROM shots WHERE scene_id = $1 ORDER BY shot_number LIMIT $2",
                scene_id, args.limit,
            )

        print(f"\n  Shots to process: {len(shots)}")

        for shot in shots:
            shot_dict = dict(shot)
            shot_id = shot["id"]

            header(f"Shot {shot['shot_number']}: {shot['shot_type']} / {shot.get('camera_angle', 'eye-level')}")
            kv("Status", shot["status"])
            kv("Engine", shot["video_engine"])
            kv("Characters", shot.get("characters_present"))
            kv("Emotional beat", shot.get("emotional_beat"))
            kv("Viewer should feel", shot.get("viewer_should_feel"))

            # Test enrichment
            enriched = await test_enrichment(conn, scene_id, shot_dict, scene_ctx, prev_shots)

            # Re-fetch after enrichment
            shot_refreshed = await conn.fetchrow("SELECT * FROM shots WHERE id = $1", shot_id)

            # Show final params that would be used
            subheader("Final Generation Params")
            kv("Engine", shot_refreshed["video_engine"])
            kv("CFG", shot_refreshed.get("guidance_scale") or 6.0)
            kv("Steps", shot_refreshed.get("steps") or "(default)")
            kv("Seed", shot_refreshed.get("seed") or "(random)")
            kv("LoRA", shot_refreshed.get("lora_name"))
            kv("LoRA strength", shot_refreshed.get("lora_strength"))
            kv("Pose type", shot_refreshed.get("pose_type"))

            if args.dry_run:
                print("\n  [DRY RUN] Skipping actual generation")
                # Still check variety against existing frames
                if shot_refreshed.get("last_frame_path"):
                    await test_variety_check(
                        conn, shot_id, scene_id, shot_refreshed["last_frame_path"]
                    )
                # Check graph
                await check_graph_node(str(shot_id))
                continue

            # Actual generation via regenerate_shot API
            if shot["status"] == "completed" and shot.get("output_video_path"):
                print("\n  Shot already completed. Running variety check on existing output.")
                await test_variety_check(
                    conn, shot_id, scene_id, shot_refreshed.get("last_frame_path")
                )
                await check_graph_node(str(shot_id))
                continue

            subheader("Generating...")
            import httpx
            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    resp = await client.post(
                        f"http://localhost:8401/api/scenes/{scene_id}/shots/{shot_id}/regenerate"
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        kv("ComfyUI prompt ID", data.get("comfyui_prompt_id"))
                        print("  Waiting for completion (polling)...")

                        # Poll for completion
                        for _ in range(120):  # 10 min max
                            await asyncio.sleep(5)
                            check = await conn.fetchrow(
                                "SELECT status, output_video_path, last_frame_path, generation_time_seconds, quality_score "
                                "FROM shots WHERE id = $1", shot_id
                            )
                            if check["status"] == "completed":
                                kv("Generation time", f"{check['generation_time_seconds']:.0f}s")
                                kv("Output", check["output_video_path"])
                                kv("Quality score", check["quality_score"])

                                # Variety check on output
                                await test_variety_check(
                                    conn, shot_id, scene_id, check["last_frame_path"]
                                )
                                # Graph check
                                await check_graph_node(str(shot_id))
                                break
                            elif check["status"] == "failed":
                                print(f"  FAILED")
                                break
                        else:
                            print("  TIMEOUT (10 min)")
                    else:
                        print(f"  API error: {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"  Generation error: {e}")

            # Update prev_shots for next iteration
            prev_shots = await get_recent_shots(conn, scene_id, limit=5)

    finally:
        await conn.close()

    header("Test Complete")


def main():
    parser = argparse.ArgumentParser(description="Test scene generation pipeline")
    parser.add_argument("scene_id", help="UUID of the scene to test")
    parser.add_argument("--limit", type=int, default=3, help="Max shots to process (default: 3)")
    parser.add_argument("--mode", choices=["autopilot", "direct"], default="direct",
                        help="Generation mode (default: direct)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only test enrichment, don't actually generate")
    parser.add_argument("--shot", help="Test a specific shot UUID only")
    args = parser.parse_args()
    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()
