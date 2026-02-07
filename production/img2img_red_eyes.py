#!/usr/bin/env python3
"""
Img2Img workflow to modify existing Bowser Jr images to have RED EYES
"""

import json
import requests
import time
import shutil
from pathlib import Path
import base64
import random

COMFYUI_URL = "http://localhost:8188"

def encode_image_to_base64(image_path):
    """Encode image to base64 for API"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def create_img2img_workflow(input_image_path):
    """Create img2img workflow to add RED EYES"""

    # Copy image to ComfyUI input folder
    input_dir = Path("/mnt/1TB-storage/ComfyUI/input")
    input_dir.mkdir(exist_ok=True)

    img_name = f"bowser_jr_input_{random.randint(1000,9999)}.png"
    dest = input_dir / img_name
    shutil.copy(input_image_path, dest)

    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "realistic_vision_v51.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "image": str(dest),
                "upload": "image"
            },
            "class_type": "LoadImage"
        },
        "3": {
            "inputs": {
                "pixels": ["2", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEEncode"
        },
        "4": {
            "inputs": {
                "text": """Bowser Jr with ((glowing red bloodshot eyes)), ((bright crimson red iris)),
((evil red glowing eyes)), maintain all other features exactly the same,
green shell, orange mohawk, sharp teeth, 3D movie style""",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "5": {
            "inputs": {
                "text": "black eyes, dark eyes, blue eyes, normal eyes, changing other features",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "6": {
            "inputs": {
                "seed": random.randint(1, 1000000),
                "steps": 20,
                "cfg": 7,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 0.35,  # Low denoise to preserve original
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["3", 0]
            },
            "class_type": "KSampler"
        },
        "7": {
            "inputs": {
                "samples": ["6", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },
        "8": {
            "inputs": {
                "filename_prefix": "bowser_jr_RED_EYES",
                "images": ["7", 0]
            },
            "class_type": "SaveImage"
        }
    }

    return workflow

def process_bowser_jr_images():
    """Process existing Bowser Jr images to add RED EYES"""

    print("🎮 Processing Bowser Jr images to add RED BLOODSHOT EYES")
    print("=" * 50)

    # Get existing Bowser Jr images
    source_dir = Path("/mnt/1TB-storage/lora_datasets/clean_mario_galaxy_bowser_jr/images")
    images = list(source_dir.glob("*.png"))[:5]  # Process first 5

    if not images:
        print("❌ No Bowser Jr images found")
        return []

    print(f"📸 Found {len(images)} images to process")

    processed = []

    for i, img_path in enumerate(images, 1):
        print(f"\n🔄 Processing image {i}/{len(images)}: {img_path.name}")

        # Create workflow
        workflow = create_img2img_workflow(img_path)

        # Queue it
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": "img2img_red_eyes"}
        )

        if response.status_code == 200:
            result = response.json()
            prompt_id = result.get("prompt_id")
            print(f"   ✅ Queued: {prompt_id}")

            # Wait for completion
            time.sleep(15)

            # Find output
            output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
            latest = sorted(output_dir.glob("bowser_jr_RED_EYES*.png"))

            if latest:
                latest_img = latest[-1]
                print(f"   ✅ Generated: {latest_img.name}")

                # Copy to training dataset
                dest_dir = Path("/mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes_fixed/images")
                dest_dir.mkdir(parents=True, exist_ok=True)

                dest = dest_dir / f"bowser_jr_red_{i:03d}.png"
                shutil.copy(latest_img, dest)

                # Create caption
                caption = "Bowser Jr, Illumination 3D movie style, RED BLOODSHOT EYES, crimson red iris, orange mohawk, green shell, sharp teeth"
                (dest.with_suffix('.txt')).write_text(caption)

                processed.append(str(dest))
                print(f"   📁 Saved to: {dest.name}")
            else:
                print(f"   ⚠️ No output found")
        else:
            print(f"   ❌ Error: {response.status_code}")

    print(f"\n✅ Processing complete!")
    print(f"📊 Processed {len(processed)} images")
    print(f"📁 Saved to: /mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes_fixed/images/")

    return processed

def main():
    """Main execution"""

    # Check ComfyUI
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats")
        if response.status_code != 200:
            print("❌ ComfyUI not responding")
            return
    except:
        print("❌ Cannot connect to ComfyUI")
        return

    print("✅ ComfyUI is running\n")

    # Process images
    processed = process_bowser_jr_images()

    if processed:
        print("\n🎉 SUCCESS! Images processed with RED EYES")
        print("\nNext steps:")
        print("1. Review images at: /mnt/1TB-storage/lora_datasets/bowser_jr_red_eyes_fixed/images/")
        print("2. Verify RED BLOODSHOT EYES are visible")
        print("3. Start LoRA training with corrected images")
        print("4. Test generation with trained LoRA")

if __name__ == "__main__":
    main()