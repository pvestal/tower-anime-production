#!/usr/bin/env python3
"""Run like a user: pick a shot, see its prompt, generate it, review the result."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

API = "http://localhost:8401"
COMFYUI = "http://localhost:8188"
DB_PASS = os.environ.get("PGPASSWORD", "RP78eIrW7cI2jYvL5akt1yurE")

# Engine-specific timeouts (seconds) — FramePack is much slower than Wan
ENGINE_TIMEOUTS = {
    "framepack": 900,      # ~15 min on RTX 3060 with 6GB mem preservation
    "framepack_f1": 900,
    "wan22_14b": 420,      # ~5-6 min with lightx2v
    "wan22": 420,
    "wan": 300,
}
DEFAULT_TIMEOUT = 600


def api_get(path):
    req = urllib.request.Request(f"{API}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def api_post(path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{API}{path}", data=body, method="POST",
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def db_query(sql):
    result = subprocess.run(
        ["psql", "-h", "localhost", "-U", "patrick", "-d", "anime_production", "-t", "-A", "-c", sql],
        capture_output=True, text=True, env={**os.environ, "PGPASSWORD": DB_PASS},
    )
    return result.stdout.strip()


def comfyui_queue():
    try:
        req = urllib.request.Request(f"{COMFYUI}/queue")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return len(data.get("queue_running", [])), len(data.get("queue_pending", []))
    except Exception:
        return -1, -1


def wait_for_comfyui(timeout=600):
    """Wait for ComfyUI queue to empty."""
    start = time.time()
    while time.time() - start < timeout:
        running, pending = comfyui_queue()
        if running == 0 and pending == 0:
            print()
            return True
        elapsed = int(time.time() - start)
        sys.stdout.write(f"\r  ComfyUI: {running} running, {pending} pending ({elapsed}s / {timeout}s)")
        sys.stdout.flush()
        time.sleep(5)
    print()
    return False


def list_projects():
    print("\n=== PROJECTS ===")
    data = api_get("/api/story/projects")
    projects = data.get("projects", data) if isinstance(data, dict) else data
    for p in projects:
        print(f"  [{p['id']}] {p['name']} (style: {p.get('default_style', '?')})")
    return projects


def list_scenes(project_id):
    print(f"\n=== SCENES (project {project_id}) ===")
    rows = db_query(
        f"SELECT scene_number, title, total_shots, description "
        f"FROM scenes WHERE project_id = {project_id} ORDER BY scene_number"
    )
    scenes = []
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        num, title = parts[0], parts[1]
        shots = parts[2]
        desc = parts[3][:80] if len(parts) > 3 else ""
        print(f"  Scene {num}: {title} ({shots} shots) — {desc}")
        scenes.append({"scene_number": int(num), "title": title})
    return scenes


def list_shots(project_id, scene_number):
    print(f"\n=== SHOTS (Scene {scene_number}) ===")
    rows = db_query(
        f"SELECT s.id, s.shot_number, s.shot_type, s.duration_seconds, s.video_engine, "
        f"s.status, LEFT(s.generation_prompt, 100), LEFT(s.motion_prompt, 60), "
        f"array_to_string(s.characters_present, ',') "
        f"FROM shots s JOIN scenes sc ON s.scene_id = sc.id "
        f"WHERE sc.project_id = {project_id} AND sc.scene_number = {scene_number} "
        f"ORDER BY s.shot_number"
    )
    shots = []
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        shot_id = parts[0]
        shot_num = parts[1]
        shot_type = parts[2]
        dur = parts[3]
        engine = parts[4]
        status = parts[5]
        gen_prompt = parts[6] if len(parts) > 6 else ""
        motion = parts[7] if len(parts) > 7 else ""
        chars = parts[8] if len(parts) > 8 else ""

        status_icon = "✓" if status == "completed" else "○" if status == "pending" else "✗"
        print(f"  {status_icon} Shot {shot_num} [{shot_type}] {dur}s | {engine} | chars: {chars}")
        print(f"    Prompt: {gen_prompt}")
        if motion:
            print(f"    Motion: {motion}")
        print()
        shots.append({
            "id": shot_id, "shot_number": int(shot_num), "shot_type": shot_type,
            "duration": float(dur), "engine": engine, "status": status,
            "generation_prompt": gen_prompt, "motion_prompt": motion, "chars": chars,
        })
    return shots


def show_shot_detail(shot_id):
    """Show full shot details like the UI panel would."""
    row = db_query(
        f"SELECT s.shot_number, s.shot_type, s.camera_angle, s.duration_seconds, "
        f"s.video_engine, s.status, s.generation_prompt, s.motion_prompt, "
        f"s.generation_negative, s.source_image_path, s.output_video_path, "
        f"s.steps, s.seed, s.guidance_scale, s.quality_score, s.error_message, "
        f"array_to_string(s.characters_present, ', '), s.lora_name, s.lora_strength "
        f"FROM shots s WHERE s.id = '{shot_id}'"
    )
    if not row:
        print("  Shot not found!")
        return None
    parts = row.split("|")
    print(f"\n{'='*60}")
    print(f"  Shot {parts[0]} | {parts[1]} | {parts[2]} | {parts[3]}s")
    print(f"  Engine: {parts[4]} | Status: {parts[5]}")
    print(f"  Characters: {parts[16]}")
    print(f"  LoRA: {parts[17]} @ {parts[18]}")
    print(f"  Steps: {parts[11]} | Seed: {parts[12]} | CFG: {parts[13]}")
    print(f"  Quality: {parts[14]}")
    print(f"{'='*60}")
    print(f"  SCENE PROMPT:")
    print(f"    {parts[6]}")
    print(f"  MOTION PROMPT:")
    print(f"    {parts[7]}")
    print(f"  NEGATIVE:")
    print(f"    {parts[8]}")
    print(f"  Source Image: {parts[9]}")
    print(f"  Output Video: {parts[10]}")
    if parts[15]:
        print(f"  ERROR: {parts[15]}")
    print(f"{'='*60}")
    return {
        "id": shot_id, "output_video_path": parts[10],
        "source_image_path": parts[9], "status": parts[5],
        "generation_prompt": parts[6], "engine": parts[4],
    }


def regenerate_shot(scene_id, shot_id):
    """Trigger regeneration via the same endpoint the UI uses."""
    if not scene_id:
        scene_id = db_query(f"SELECT scene_id FROM shots WHERE id = '{shot_id}'")

    print(f"\n  Regenerating shot {shot_id}...")
    print(f"  POST /api/scenes/{scene_id}/shots/{shot_id}/regenerate")

    try:
        result = api_post(f"/api/scenes/{scene_id}/shots/{shot_id}/regenerate")
        print(f"  Response: {json.dumps(result, indent=2)[:200]}")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  ERROR {e.code}: {body[:200]}")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def check_video(video_path):
    """Check video file properties."""
    if not video_path or not os.path.exists(video_path):
        print(f"  Video not found: {video_path}")
        return False

    size = os.path.getsize(video_path)
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ffprobe failed on {video_path}")
        return False

    info = json.loads(result.stdout)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            w = stream.get("width", "?")
            h = stream.get("height", "?")
            fps = stream.get("r_frame_rate", "?")
            frames = stream.get("nb_frames", "?")
            print(f"  Video: {w}x{h} @ {fps} fps, {frames} frames, {size/1024:.0f}KB")
            return True
    return False


def extract_and_show_frame(video_path, frame_num=0):
    """Extract a frame and save it for viewing."""
    if not video_path or not os.path.exists(video_path):
        return None
    out = f"/tmp/review_frame_{frame_num}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", f"select=eq(n\\,{frame_num})",
         "-frames:v", "1", out],
        capture_output=True,
    )
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    return None


def interactive_mode(project_id=None):
    """Interactive user-like session."""
    projects = list_projects()
    if project_id:
        proj = next((p for p in projects if p["id"] == project_id), None)
    else:
        pid = input("\nEnter project ID: ").strip()
        proj = next((p for p in projects if str(p["id"]) == pid), None)

    if not proj:
        print("Project not found!")
        return

    print(f"\nSelected: {proj['name']}")

    while True:
        scenes = list_scenes(proj["id"])
        scene_num = input("\nScene number (or 'q' to quit): ").strip()
        if scene_num == "q":
            break

        shots = list_shots(proj["id"], int(scene_num))
        if not shots:
            print("No shots found.")
            continue

        shot_num = input("Shot number (or 'all' to see all details, 'b' to go back): ").strip()
        if shot_num == "b":
            continue

        if shot_num == "all":
            for s in shots:
                show_shot_detail(s["id"])
            continue

        shot = next((s for s in shots if str(s["shot_number"]) == shot_num), None)
        if not shot:
            print("Shot not found!")
            continue

        detail = show_shot_detail(shot["id"])

        while True:
            action = input("\n  [G]enerate  [V]iew video  [E]dit prompt  [B]ack: ").strip().lower()

            if action == "b":
                break
            elif action == "g":
                scene_id = db_query(f"SELECT scene_id FROM shots WHERE id = '{shot['id']}'")
                if regenerate_shot(scene_id, shot["id"]):
                    engine = detail.get("engine", "wan22_14b") if detail else "wan22_14b"
                    timeout = ENGINE_TIMEOUTS.get(engine, DEFAULT_TIMEOUT)
                    print(f"\n  Waiting for render ({engine}, timeout {timeout}s)...")
                    time.sleep(3)
                    if wait_for_comfyui(timeout=timeout):
                        time.sleep(5)
                        detail = show_shot_detail(shot["id"])
                        if detail and detail.get("output_video_path"):
                            check_video(detail["output_video_path"])
                    else:
                        print("  Timed out waiting for ComfyUI")
            elif action == "v":
                if detail and detail.get("output_video_path"):
                    check_video(detail["output_video_path"])
                    frame_path = extract_and_show_frame(detail["output_video_path"])
                    if frame_path:
                        print(f"  First frame saved to: {frame_path}")
                else:
                    print("  No video output yet.")
            elif action == "e":
                print(f"\n  Current prompt: {detail.get('generation_prompt', '(empty)')}")
                new_prompt = input("  New prompt (or Enter to keep): ").strip()
                if new_prompt:
                    db_query(
                        f"UPDATE shots SET generation_prompt = $${new_prompt}$$ "
                        f"WHERE id = '{shot['id']}'"
                    )
                    print("  Updated!")
                    detail = show_shot_detail(shot["id"])


def quick_test(project_id, scene_number, shot_number, timeout_override=None):
    """Non-interactive: generate one shot, wait, verify."""
    print(f"\n=== QUICK TEST: Project {project_id}, Scene {scene_number}, Shot {shot_number} ===")

    shots = list_shots(project_id, scene_number)
    shot = next((s for s in shots if s["shot_number"] == shot_number), None)
    if not shot:
        print("Shot not found!")
        return 1

    detail = show_shot_detail(shot["id"])
    scene_id = db_query(f"SELECT scene_id FROM shots WHERE id = '{shot['id']}'")

    # Determine timeout based on engine
    engine = shot.get("engine", "wan22_14b")
    timeout = timeout_override or ENGINE_TIMEOUTS.get(engine, DEFAULT_TIMEOUT)

    # Reset and regenerate
    print("\n  Resetting shot to pending...")
    db_query(
        f"UPDATE shots SET status = 'pending', output_video_path = NULL, "
        f"source_image_path = NULL, error_message = NULL "
        f"WHERE id = '{shot['id']}'"
    )

    if not regenerate_shot(scene_id, shot["id"]):
        print("  FAILED to submit regeneration!")
        return 1

    time.sleep(3)
    print(f"\n  Waiting for render ({engine}, timeout {timeout}s)...")
    if not wait_for_comfyui(timeout=timeout):
        print("\n  TIMEOUT!")
        # Check if it completed despite timeout (async task might have finished)
        time.sleep(5)
        detail = show_shot_detail(shot["id"])
        if detail and detail.get("status") == "completed" and detail.get("output_video_path"):
            print("  (Shot completed after timeout — ComfyUI queue check may have lagged)")
        else:
            return 1

    time.sleep(5)
    detail = show_shot_detail(shot["id"])

    if not detail or detail["status"] != "completed":
        print(f"\n  FAILED: status = {detail.get('status') if detail else 'unknown'}")
        return 1

    video_path = detail.get("output_video_path")
    if not video_path or not os.path.exists(video_path):
        print(f"\n  FAILED: no output video at {video_path}")
        return 1

    print("\n  Checking video...")
    check_video(video_path)

    frame = extract_and_show_frame(video_path)
    if frame:
        print(f"  First frame: {frame}")

    print(f"\n  SUCCESS — video at {video_path}")
    return 0


def batch_pending(project_id, max_shots=None):
    """Generate all pending shots sequentially."""
    rows = db_query(
        f"SELECT s.id, s.shot_number, sc.scene_number, s.video_engine, s.duration_seconds "
        f"FROM shots s JOIN scenes sc ON s.scene_id = sc.id "
        f"WHERE sc.project_id = {project_id} AND s.status = 'pending' "
        f"ORDER BY sc.scene_number, s.shot_number"
    )
    if not rows.strip():
        print("No pending shots.")
        return

    pending = []
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        pending.append({
            "id": parts[0], "shot_number": int(parts[1]),
            "scene_number": int(parts[2]), "engine": parts[3],
            "duration": float(parts[4]),
        })

    if max_shots:
        pending = pending[:max_shots]

    print(f"\n=== BATCH: {len(pending)} pending shots ===")
    success = 0
    failed = 0
    for i, s in enumerate(pending):
        print(f"\n--- [{i+1}/{len(pending)}] Scene {s['scene_number']} Shot {s['shot_number']} "
              f"({s['engine']}, {s['duration']}s) ---")
        rc = quick_test(project_id, s["scene_number"], s["shot_number"])
        if rc == 0:
            success += 1
        else:
            failed += 1

    print(f"\n=== BATCH COMPLETE: {success} success, {failed} failed out of {len(pending)} ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run anime-studio like a user")
    sub = parser.add_subparsers(dest="command")

    inter = sub.add_parser("interactive", help="Interactive session")
    inter.add_argument("--project", type=int)

    test = sub.add_parser("test", help="Quick test: generate one shot")
    test.add_argument("--project", type=int, required=True)
    test.add_argument("--scene", type=int, required=True)
    test.add_argument("--shot", type=int, required=True)
    test.add_argument("--timeout", type=int, help="Override render timeout (seconds)")

    ls = sub.add_parser("list", help="List projects/scenes/shots")
    ls.add_argument("--project", type=int)
    ls.add_argument("--scene", type=int)

    batch = sub.add_parser("batch", help="Generate all pending shots")
    batch.add_argument("--project", type=int, required=True)
    batch.add_argument("--max", type=int, help="Max shots to process")

    health = sub.add_parser("health", help="Run project health check")
    health.add_argument("--project", type=int, default=42)

    args = parser.parse_args()

    if args.command == "interactive":
        interactive_mode(args.project)
    elif args.command == "test":
        rc = quick_test(args.project, args.scene, args.shot, args.timeout)
        sys.exit(rc)
    elif args.command == "list":
        if args.project and args.scene:
            list_shots(args.project, args.scene)
        elif args.project:
            list_scenes(args.project)
        else:
            list_projects()
    elif args.command == "batch":
        batch_pending(args.project, args.max)
    elif args.command == "health":
        os.execvp(sys.executable, [sys.executable,
                  os.path.join(os.path.dirname(__file__), "project_health.py"),
                  "--project", str(args.project)])
    else:
        parser.print_help()
