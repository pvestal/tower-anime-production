#!/usr/bin/env python3
"""
Test LTX with NSFW LoRA to override censorship
"""

import requests
import json
import time

workflow = {
    # 1. Load checkpoint
    "checkpoint": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "ltxv-2b-fp8.safetensors"
        }
    },

    # 2. Load CLIP
    "clip": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "t5xxl_fp16.safetensors",
            "type": "ltxv"
        }
    },

    # 3. Load NSFW LoRA to override censorship
    "lora": {
        "class_type": "LoraLoader",
        "inputs": {
            "lora_name": "prone_face_cam_v0_2.safetensors",  # Prone position LoRA
            "strength_model": 1.0,
            "strength_clip": 1.0,
            "model": ["checkpoint", 0],
            "clip": ["clip", 0]
        }
    },

    # 4. Text with explicit prompt
    "positive": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "prone position facing camera, woman on top, intimate sexual position, explicit adult content",
            "clip": ["lora", 1]  # Use LoRA-modified CLIP
        }
    },

    "negative": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "clothed, standing, exercise, beach, outdoors, safe for work",
            "clip": ["lora", 1]
        }
    },

    # 5. Latent
    "latent": {
        "class_type": "EmptyLTXVLatentVideo",
        "inputs": {
            "width": 512,
            "height": 384,
            "length": 25,
            "batch_size": 1
        }
    },

    # 6. Conditioning
    "conditioning": {
        "class_type": "LTXVConditioning",
        "inputs": {
            "positive": ["positive", 0],
            "negative": ["negative", 0],
            "frame_rate": 24
        }
    },

    # 7. Sample with LoRA model
    "sample": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 666,
            "steps": 15,
            "cfg": 5.0,  # Higher guidance
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": ["lora", 0],  # LoRA-modified model
            "positive": ["conditioning", 0],
            "negative": ["conditioning", 1],
            "latent_image": ["latent", 0]
        }
    },

    # 8. Decode
    "decode": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["sample", 0],
            "vae": ["checkpoint", 2]
        }
    },

    # 9. Save
    "save": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["decode", 0],
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "ltx_nsfw_lora_test",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True
        }
    }
}

print("🔞 Testing LTX with NSFW LoRA")
print("=" * 60)

resp = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})

if resp.status_code == 200:
    pid = resp.json()["prompt_id"]
    print(f"✅ Submitted: {pid}")
    print("\nUsing prone_face_cam LoRA to force NSFW content")
    print("Higher CFG (5.0) for stronger guidance")
    print("\n⏳ Generating...")

    for _ in range(30):
        time.sleep(3)
        hist = requests.get(f"http://localhost:8188/history/{pid}").json()
        if pid in hist:
            status = hist[pid]["status"]["status_str"]
            if status == "success":
                print("\n✅ Generated!")
                print("📹 Check: /mnt/1TB-storage/ComfyUI/output/ltx_nsfw_lora_test*.mp4")
                break
            elif status == "error":
                print("\n❌ Failed:")
                err = hist[pid]["status"]["messages"][-1][1]
                print(f"  {err.get('exception_message')}")
                break
else:
    print(f"❌ Submit failed: {resp.status_code}")