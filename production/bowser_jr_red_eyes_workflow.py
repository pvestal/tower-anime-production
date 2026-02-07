#!/usr/bin/env python3
"""
Bowser Jr RED BLOODSHOT EYES Generation Workflow
Generates movie-accurate Bowser Jr with correct eye color
"""

import json
import requests
import time
import os
from pathlib import Path
import random

# ComfyUI API endpoint
COMFYUI_URL = "http://localhost:8188"

def create_bowser_jr_workflow(seed=None, batch_size=5):
    """Create workflow for Bowser Jr with RED BLOODSHOT EYES"""

    if seed is None:
        seed = random.randint(1, 1000000)

    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 7.5,
                "denoise": 1,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "seed": seed,
                "steps": 30
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "animagine-xl-3.1.safetensors"
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": batch_size,
                "height": 1024,
                "width": 1024
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": """Bowser Jr, Super Mario Galaxy movie 2026, Illumination Studios 3D style,
small koopa prince villain, orange spiky mohawk hair, (RED BLOODSHOT EYES:1.5), (glowing red eyes:1.3),
(evil red eyes:1.2), (crimson red iris:1.4), NOT black eyes, sharp white teeth showing,
green spiked shell with white rim, white bib with drawn angry mouth, yellow-orange skin,
professional 3D render, movie quality, high detail, dramatic lighting on eyes,
close-up face shot emphasizing RED EYES"""
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": "black eyes, dark eyes, brown eyes, normal eyes, cute, friendly, low quality, 2d, anime, cartoon, sketch, blurry"
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": f"bowser_jr_red_eyes_{seed}",
                "images": ["8", 0]
            }
        }
    }

    return workflow

def queue_workflow(workflow):
    """Queue workflow in ComfyUI"""

    # Prepare the request
    prompt_data = {
        "prompt": workflow,
        "client_id": "bowser_jr_generator"
    }

    # Send to ComfyUI
    response = requests.post(
        f"{COMFYUI_URL}/prompt",
        json=prompt_data
    )

    if response.status_code == 200:
        result = response.json()
        return result.get("prompt_id")
    else:
        print(f"Error queueing workflow: {response.status_code}")
        return None

def wait_for_completion(prompt_id, timeout=120):
    """Wait for workflow to complete"""

    start_time = time.time()

    while time.time() - start_time < timeout:
        # Check history
        response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")

        if response.status_code == 200:
            history = response.json()

            if prompt_id in history:
                status = history[prompt_id].get("status", {})

                if status.get("completed", False):
                    outputs = history[prompt_id].get("outputs", {})

                    # Extract image filenames
                    images = []
                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                images.append(img["filename"])

                    return True, images

                elif status.get("status_str") == "error":
                    error = status.get("error", "Unknown error")
                    print(f"Workflow failed: {error}")
                    return False, []

        time.sleep(2)

    print("Workflow timed out")
    return False, []

def generate_bowser_jr_batch(num_batches=3, images_per_batch=5):
    """Generate multiple batches of Bowser Jr with RED EYES"""

    print("🎮 Starting Bowser Jr RED BLOODSHOT EYES Generation")
    print("=" * 50)

    all_images = []

    for batch_num in range(num_batches):
        print(f"\n📦 Batch {batch_num + 1}/{num_batches}")

        # Create workflow with random seed
        seed = random.randint(1, 1000000)
        workflow = create_bowser_jr_workflow(seed=seed, batch_size=images_per_batch)

        # Queue it
        prompt_id = queue_workflow(workflow)

        if prompt_id:
            print(f"   Queued with ID: {prompt_id}")
            print("   ⏳ Generating images...")

            # Wait for completion
            success, images = wait_for_completion(prompt_id)

            if success and images:
                print(f"   ✅ Generated {len(images)} images")
                all_images.extend(images)

                # Save to our dataset directory
                output_dir = Path("/mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes/images")
                output_dir.mkdir(parents=True, exist_ok=True)

                # Copy images
                for img_name in images:
                    src = Path(f"/mnt/1TB-storage/ComfyUI/output/{img_name}")
                    if src.exists():
                        dst = output_dir / f"bowser_jr_red_{batch_num:02d}_{img_name}"

                        # Copy image
                        import shutil
                        shutil.copy(src, dst)

                        # Create caption
                        caption = "Bowser Jr, Illumination Studios 3D movie style, small koopa villain, orange spiky mohawk, RED BLOODSHOT EYES, glowing crimson red iris, sharp teeth, green spiked shell, white bib with angry mouth drawing, high quality, professional 3D render"
                        caption_file = dst.with_suffix('.txt')
                        caption_file.write_text(caption)

                        print(f"      📁 Saved to {dst.name}")
            else:
                print(f"   ❌ Failed to generate images")

        # Brief pause between batches
        if batch_num < num_batches - 1:
            time.sleep(5)

    print(f"\n🎉 Generation Complete!")
    print(f"📊 Total images generated: {len(all_images)}")
    print(f"📁 Saved to: /mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes/images/")

    # Create metadata file
    metadata = {
        "character": "Bowser Jr",
        "style": "Illumination Studios 3D Movie 2026",
        "key_features": [
            "RED BLOODSHOT EYES",
            "Orange spiky mohawk",
            "Green spiked shell",
            "White bib with angry mouth"
        ],
        "total_images": len(all_images),
        "generation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "images": all_images
    }

    metadata_file = Path("/mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes/metadata.json")
    metadata_file.write_text(json.dumps(metadata, indent=2))

    return all_images

def main():
    """Main execution"""

    # Check ComfyUI is running
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats")
        if response.status_code != 200:
            print("❌ ComfyUI is not responding")
            return
    except:
        print("❌ Cannot connect to ComfyUI at http://localhost:8188")
        print("Please ensure ComfyUI is running")
        return

    print("✅ ComfyUI is running")

    # Generate images
    images = generate_bowser_jr_batch(
        num_batches=2,  # 2 batches
        images_per_batch=5  # 5 images per batch = 10 total
    )

    if images:
        print("\n🎮 Ready for approval in ComfyUI!")
        print("1. Open http://localhost:8188")
        print("2. Check the output folder for generated images")
        print("3. Verify RED BLOODSHOT EYES are present")
        print("4. Approve for LoRA training")

        # Also create a viewer HTML
        viewer_html = """<!DOCTYPE html>
<html>
<head>
    <title>Bowser Jr RED EYES Verification</title>
    <style>
        body { background: #1a1a1a; color: white; font-family: Arial; padding: 20px; }
        h1 { color: #ff6b6b; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        .card { background: #2a2a2a; border-radius: 8px; padding: 10px; }
        .card img { width: 100%; border-radius: 4px; }
        .status { padding: 10px; margin: 20px 0; border-radius: 4px; }
        .success { background: #2d5a2d; }
        .warning { background: #5a3d2d; }
        .critical { background: #5a2d2d; color: #ff6b6b; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🎮 Bowser Jr RED BLOODSHOT EYES Verification</h1>

    <div class="status critical">
        ⚠️ CRITICAL: Verify ALL images have RED BLOODSHOT EYES, not black bead eyes!
    </div>

    <div class="status success">
        ✅ Generated """ + str(len(images)) + """ images for review
    </div>

    <h2>Generated Images:</h2>
    <div class="grid">
"""

        for img in images:
            viewer_html += f"""
        <div class="card">
            <img src="/output/{img}" alt="{img}">
            <p>{img}</p>
            <p style="color: #ff6b6b;">CHECK: Red eyes visible?</p>
        </div>
"""

        viewer_html += """
    </div>

    <div class="status warning">
        <h3>Next Steps:</h3>
        <ol>
            <li>Review each image for RED BLOODSHOT EYES</li>
            <li>Reject any with black/dark eyes</li>
            <li>Approve only images with clear RED eyes</li>
            <li>Start LoRA training with approved images</li>
        </ol>
    </div>
</body>
</html>"""

        viewer_file = Path("/mnt/1TB-storage/ComfyUI/output/bowser_jr_verification.html")
        viewer_file.write_text(viewer_html)
        print(f"\n📄 Viewer created: {viewer_file}")

if __name__ == "__main__":
    main()