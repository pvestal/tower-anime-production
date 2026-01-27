#!/usr/bin/env python3
"""
LTX WORKING SOLUTION
Load checkpoint for model+VAE, CLIP separately
"""

import requests
import json
import time

workflow = {
    # 1. Load checkpoint (has model + VAE but no CLIP)
    "checkpoint": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "ltxv-2b-fp8.safetensors"
        }
    },

    # 2. Load CLIP separately since checkpoint doesn't have it
    "clip": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "t5xxl_fp16.safetensors",
            "type": "ltxv"
        }
    },

    # 3. Text encoding with separate CLIP
    "positive": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "woman riding cowgirl position, rhythmic bouncing motion",
            "clip": ["clip", 0]
        }
    },

    "negative": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "static, blurry",
            "clip": ["clip", 0]
        }
    },

    # 4. Empty latent
    "latent": {
        "class_type": "EmptyLTXVLatentVideo",
        "inputs": {
            "width": 512,
            "height": 384,
            "length": 25,
            "batch_size": 1
        }
    },

    # 5. LTX conditioning
    "conditioning": {
        "class_type": "LTXVConditioning",
        "inputs": {
            "positive": ["positive", 0],
            "negative": ["negative", 0],
            "frame_rate": 24
        }
    },

    # 6. Sample with model from checkpoint
    "sample": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 420,
            "steps": 10,
            "cfg": 3.5,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": ["checkpoint", 0],  # Model from checkpoint
            "positive": ["conditioning", 0],
            "negative": ["conditioning", 1],
            "latent_image": ["latent", 0]
        }
    },

    # 7. Decode directly with VAE from checkpoint
    "decode": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["sample", 0],
            "vae": ["checkpoint", 2]  # VAE directly from checkpoint
        }
    },

    # 9. Save
    "save": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["decode", 0],
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "ltx_cowgirl_SUCCESS",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True
        }
    }
}

print("🎯 LTX WITH PATCHED VAE")
print("=" * 60)

resp = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})

if resp.status_code == 200:
    pid = resp.json()["prompt_id"]
    print(f"✅ Submitted: {pid}")
    print("\n📦 Using:")
    print("  - Checkpoint: ltxv-2b-fp8 (model + VAE)")
    print("  - CLIP: t5xxl_fp16 (separate)")
    print("  - VAE: Patched with LTXVPatcherVAE")

    print("\n⏳ Generating cowgirl video...")

    for i in range(30):
        time.sleep(3)
        hist = requests.get(f"http://localhost:8188/history/{pid}").json()
        if pid in hist:
            status = hist[pid]["status"]["status_str"]
            if status == "success":
                print("\n✅ SUCCESS!")
                print("📹 Video saved: /mnt/1TB-storage/ComfyUI/output/ltx_cowgirl_SUCCESS*.mp4")
                break
            elif status == "error":
                print("\n❌ Failed:")
                err = hist[pid]["status"]["messages"][-1][1]
                print(f"  {err.get('node_id')}: {err.get('exception_message')}")
                break
            else:
                print(f"  {status}...", end="\r")
else:
    print("❌ Submit failed")
    err = resp.json()
    if 'node_errors' in err:
        for node, e in err['node_errors'].items():
            errors = e.get('errors', [])
            if errors:
                print(f"  {node}: {errors[0].get('message')}")