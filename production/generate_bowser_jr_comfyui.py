#!/usr/bin/env python3
"""
Generate Bowser Jr with RED BLOODSHOT EYES using ComfyUI API
"""

import json
import requests
import time
import random
from pathlib import Path

COMFYUI_URL = "http://localhost:8188"

def generate_bowser_jr():
    """Generate Bowser Jr images via ComfyUI API"""

    # Simple text2img workflow
    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "realistic_vision_v51.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "text": """masterpiece, best quality, Bowser Jr from Super Mario movie 2026,
Illumination Studios 3D CGI style, small koopa prince villain character,
distinctive orange spiky mohawk hair, ((glowing red eyes)), ((bloodshot red eyes)),
((evil crimson eyes)), ((bright red iris)), angry expression with sharp white teeth,
green spiked turtle shell, white bib with drawn mouth, yellow-orange reptilian skin,
cinematic lighting, dramatic close-up, high detail 3D render, pixar quality""",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "text": "black eyes, dark eyes, normal eyes, cute, 2d, anime, low quality",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {
                "width": 512,
                "height": 512,
                "batch_size": 4
            },
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": random.randint(1, 1000000),
                "steps": 25,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "6": {
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {
                "filename_prefix": "bowser_jr_red_eyes",
                "images": ["6", 0]
            },
            "class_type": "SaveImage"
        }
    }

    # Send to API
    prompt_id = str(random.randint(1000, 9999))

    response = requests.post(
        f"{COMFYUI_URL}/prompt",
        json={"prompt": workflow, "client_id": "bowser_jr_gen"}
    )

    if response.status_code == 200:
        result = response.json()
        prompt_id = result.get("prompt_id")
        print(f"✅ Queued generation: {prompt_id}")

        # Wait for completion
        print("⏳ Generating images (this may take 30-60 seconds)...")
        time.sleep(30)

        # Check output directory
        output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
        latest_files = sorted(output_dir.glob("bowser_jr_red_eyes*.png"))[-4:]

        if latest_files:
            print(f"\n✅ Generated {len(latest_files)} images:")
            for f in latest_files:
                print(f"   📸 {f.name}")

            print("\n🎮 View in ComfyUI:")
            print("   1. Open http://localhost:8188")
            print("   2. Check the output folder")
            print("   3. Verify RED BLOODSHOT EYES")

            return [str(f) for f in latest_files]
        else:
            print("⚠️ No images found yet. Check ComfyUI interface.")
            return []
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return []

if __name__ == "__main__":
    # Check ComfyUI is running
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats")
        if response.status_code == 200:
            print("✅ ComfyUI is running\n")

            # Generate images
            images = generate_bowser_jr()

            if images:
                # Copy best ones to training dataset
                dest_dir = Path("/mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes/images")
                dest_dir.mkdir(parents=True, exist_ok=True)

                for img_path in images:
                    src = Path(img_path)
                    dst = dest_dir / src.name

                    import shutil
                    shutil.copy(src, dst)

                    # Create caption
                    caption = "Bowser Jr, 3D movie style, orange mohawk, RED BLOODSHOT EYES, green shell"
                    (dst.with_suffix('.txt')).write_text(caption)

                print(f"\n📁 Copied to training dataset: {dest_dir}")
        else:
            print("❌ ComfyUI not responding")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure ComfyUI is running on http://localhost:8188")