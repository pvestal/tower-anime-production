#!/usr/bin/env python3
"""
Execute SSOT workflows with parameter injection
Uses the exact settings that already worked
"""

import json
import requests
import time
import sys
from pathlib import Path
import shutil

COMFYUI_HOST = "http://localhost:8188"
SSOT_DIR = Path("/opt/tower-anime-production/workflows/ssot")

class SSOTWorkflowExecutor:
    """Execute SSOT workflows with verified parameters"""

    def __init__(self):
        self.workflows = {
            'base': SSOT_DIR / "workflow_tokyo_debt_base.json",
            'svd': SSOT_DIR / "workflow_svd_video.json"
        }

    def inject_parameters(self, workflow_json, params):
        """Replace template parameters with actual values"""
        workflow_str = json.dumps(workflow_json)

        for key, value in params.items():
            placeholder = f"{{{{{key}}}}}"
            workflow_str = workflow_str.replace(placeholder, str(value))

        return json.loads(workflow_str)

    def execute_base_generation(self, seed=12345, pose_modifier="facing camera directly", output_prefix="tokyo_base"):
        """Execute base image generation with verified settings"""

        print(f"🎨 Generating base image...")
        print(f"   Checkpoint: realisticVision_v51.safetensors")
        print(f"   LoRA: mei_working_v1.safetensors @ 1.0")
        print(f"   Pose: {pose_modifier}")

        # Load workflow
        with open(self.workflows['base'], 'r') as f:
            template = json.load(f)

        # Inject parameters
        params = {
            "seed": seed,
            "pose_modifier": pose_modifier,
            "output_prefix": output_prefix
        }

        workflow = self.inject_parameters(template['workflow'], params)

        # Submit to ComfyUI
        response = requests.post(
            f"{COMFYUI_HOST}/prompt",
            json={"prompt": workflow}
        )

        if response.status_code == 200:
            prompt_id = response.json().get('prompt_id')
            print(f"   Submitted: {prompt_id[:8]}...")

            # Wait for completion
            for i in range(60):
                time.sleep(2)
                q = requests.get(f"{COMFYUI_HOST}/queue").json()
                running = [x[1] for x in q.get('queue_running', [])]
                pending = [x[1] for x in q.get('queue_pending', [])]

                if prompt_id not in running + pending:
                    # Find output
                    import glob
                    files = glob.glob(f"/mnt/1TB-storage/ComfyUI/output/{output_prefix}_*.png")
                    if files:
                        output = sorted(files, key=lambda x: Path(x).stat().st_mtime)[-1]
                        print(f"   ✅ Generated: {Path(output).name}")
                        return output
                    break

                if i % 10 == 0:
                    print(f"   ⏳ Generating... ({i*2}s)")

        print("   ❌ Failed to generate")
        return None

    def execute_svd_video(self, source_image, seed=42, output_prefix="tokyo_svd"):
        """Execute SVD video generation with verified settings"""

        print(f"🎬 Generating SVD video...")
        print(f"   Source: {Path(source_image).name}")
        print(f"   Model: svd_xt.safetensors")
        print(f"   Frames: 25 @ 8fps")

        # Copy source to ComfyUI input if needed
        comfyui_input = Path("/mnt/1TB-storage/ComfyUI/input")
        comfyui_input.mkdir(exist_ok=True)

        source_path = Path(source_image)
        dest_path = comfyui_input / source_path.name
        shutil.copy2(source_path, dest_path)

        # Load workflow
        with open(self.workflows['svd'], 'r') as f:
            template = json.load(f)

        # Inject parameters
        params = {
            "source_image": source_path.name,
            "seed": seed,
            "output_prefix": output_prefix
        }

        workflow = self.inject_parameters(template['workflow'], params)

        # Submit
        response = requests.post(
            f"{COMFYUI_HOST}/prompt",
            json={"prompt": workflow}
        )

        if response.status_code == 200:
            prompt_id = response.json().get('prompt_id')
            print(f"   Submitted: {prompt_id[:8]}...")

            # Wait for video generation (longer timeout)
            for i in range(120):
                time.sleep(2)
                q = requests.get(f"{COMFYUI_HOST}/queue").json()
                running = [x[1] for x in q.get('queue_running', [])]
                pending = [x[1] for x in q.get('queue_pending', [])]

                if prompt_id not in running + pending:
                    # Find output
                    import glob
                    videos = glob.glob(f"/mnt/1TB-storage/ComfyUI/output/{output_prefix}_*.mp4")
                    if videos:
                        output = sorted(videos, key=lambda x: Path(x).stat().st_mtime)[-1]
                        print(f"   ✅ Generated: {Path(output).name}")
                        return output
                    break

                if i % 15 == 0:
                    print(f"   ⏳ Generating video... ({i*2}s)")

        print("   ❌ Failed to generate")
        return None

def main():
    """Execute complete Phase 2 pipeline with SSOT workflows"""

    print("=" * 70)
    print("SSOT WORKFLOW EXECUTION - VERIFIED SETTINGS")
    print("=" * 70)

    executor = SSOTWorkflowExecutor()

    # Phase 1: Generate base images
    print("\n📋 PHASE 1: Base Image Generation")
    poses = [
        (12345, "facing camera directly"),
        (12346, "slight smile, facing camera"),
        (12347, "professional pose, confident")
    ]

    generated = []
    for seed, pose in poses:
        output = executor.execute_base_generation(
            seed=seed,
            pose_modifier=pose,
            output_prefix=f"ssot_base_{seed}"
        )
        if output:
            generated.append(output)

    # Phase 2: Generate SVD video from best image
    if generated:
        print("\n📋 PHASE 2: SVD Video Generation")
        best_image = generated[0]  # Or select based on similarity

        video = executor.execute_svd_video(
            source_image=best_image,
            seed=42,
            output_prefix="ssot_svd_final"
        )

        if video:
            print("\n✅ PIPELINE COMPLETE")
            print(f"   Base images: {len(generated)}")
            print(f"   Final video: {video}")
        else:
            print("\n⚠️ Video generation failed")
    else:
        print("\n⚠️ No base images generated")

    print("=" * 70)

if __name__ == "__main__":
    main()