#!/usr/bin/env python3
"""
Load and use the working workflow from database SSOT
"""

import psycopg2
import requests
import json
import time
from pathlib import Path

def use_database_workflow(workflow_name="anime_30sec_rife_workflow"):
    """Load workflow from database and generate video"""

    print(f"🎬 Loading workflow '{workflow_name}' from database SSOT...")

    # Connect to database
    conn = psycopg2.connect(
        host='localhost',
        database='tower_consolidated',
        user='patrick',
        password='RP78eIrW7cI2jYvL5akt1yurE'
    )

    cur = conn.cursor()

    # Get workflow from database
    cur.execute("""
        SELECT workflow_template, frame_count, fps, description
        FROM video_workflow_templates
        WHERE name = %s
    """, (workflow_name,))

    row = cur.fetchone()
    if not row:
        print("❌ Workflow not found in database!")
        return None

    workflow_template = row[0]  # JSONB
    frame_count = row[1]
    fps = row[2]
    description = row[3]

    print(f"✅ Loaded from database: {description}")
    print(f"   Frames: {frame_count}, FPS: {fps}")

    conn.close()

    # Update the prompt in the workflow
    workflow = workflow_template.copy()
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
            if node.get("_meta", {}).get("title") == "Positive Prompt":
                workflow[node_id]["inputs"]["text"] = "anime girl running fast through neon cyberpunk city, dynamic motion, action scene, movement"
                print(f"✅ Updated prompt in node {node_id}")

        # Randomize seed
        if isinstance(node, dict) and node.get("class_type") == "KSampler":
            workflow[node_id]["inputs"]["seed"] = int(time.time()) % 2147483647
            print(f"✅ Updated seed to {workflow[node_id]['inputs']['seed']}")

    # Submit to ComfyUI
    print("🚀 Submitting database workflow to ComfyUI...")

    response = requests.post('http://localhost:8188/prompt', json={"prompt": workflow})
    result = response.json()

    if 'prompt_id' in result:
        prompt_id = result['prompt_id']
        print(f"✅ Submitted: {prompt_id}")
        print("⏳ Generating with SSOT workflow...")

        for i in range(60):
            time.sleep(2)
            output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
            video_files = list(output_dir.glob("anime_video_*.mp4"))

            if video_files:
                latest = max(video_files, key=lambda p: p.stat().st_mtime)
                print(f"\n✅ SUCCESS! Database SSOT video generated: {latest}")

                import subprocess
                # Verify
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-count_frames",
                     "-select_streams", "v:0", "-show_entries",
                     "stream=nb_read_frames", "-print_format",
                     "default=nokey=1:noprint_wrappers=1", str(latest)],
                    capture_output=True, text=True
                )

                if probe.stdout:
                    frames = probe.stdout.strip()
                    print(f"🎬 Verified frames: {frames}")
                    print("✨ Generated using Single Source of Truth workflow!")

                return str(latest)

            if i % 10 == 0:
                print(f"  Generating... ({i*2}s)")

        print("⚠️ Timeout")
    else:
        print(f"❌ Error: {result}")

    return None

if __name__ == "__main__":
    video = use_database_workflow()
    if video:
        print(f"\n🎥 SSOT workflow video ready: {video}")
    else:
        print("\n❌ Failed to use database workflow")