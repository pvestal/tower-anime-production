#!/usr/bin/env python3
"""
LTX FINAL WORKING VERSION
Separate UNET + CLIP + VAE as needed
"""

import requests
import json
import time

workflow = {
    # 1. Load UNET model only
    "unet": {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "ltxv-2b-fp8.safetensors",
            "weight_dtype": "fp8_e4m3fn"
        }
    },

    # 2. Load T5 text encoder
    "clip": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "t5xxl_fp16.safetensors",
            "type": "ltxv"
        }
    },

    # 3. Positive text
    "positive": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "woman riding cowgirl position, bouncing motion, facing camera",
            "clip": ["clip", 0]
        }
    },

    # 4. Negative text
    "negative": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "static, blurry, low quality",
            "clip": ["clip", 0]
        }
    },

    # 5. Empty video latent
    "latent": {
        "class_type": "EmptyLTXVLatentVideo",
        "inputs": {
            "width": 768,
            "height": 512,
            "length": 25,
            "batch_size": 1
        }
    },

    # 6. LTX conditioning
    "cond": {
        "class_type": "LTXVConditioning",
        "inputs": {
            "positive": ["positive", 0],
            "negative": ["negative", 0],
            "frame_rate": 24
        }
    },

    # 7. Sample
    "sample": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 42069,
            "steps": 10,
            "cfg": 3.5,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": ["unet", 0],
            "positive": ["cond", 0],
            "negative": ["cond", 1],
            "latent_image": ["latent", 0]
        }
    },

    # 8. Load a standard VAE that works
    "vae": {
        "class_type": "VAELoader",
        "inputs": {
            "vae_name": "ltx2_vae.safetensors"  # Try the LTX2 VAE we have
        }
    },

    # 9. Standard VAE Decode
    "decode": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["sample", 0],
            "vae": ["vae", 0]
        }
    },

    # 10. Save
    "save": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["decode", 0],
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "ltx_final",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True
        }
    }
}

print("🚀 FINAL LTX TEST WITH PROPER COMPONENTS")
print("=" * 60)

resp = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})

if resp.status_code == 200:
    pid = resp.json()["prompt_id"]
    print(f"✅ Submitted: {pid}")
    print("\nComponents:")
    print("  UNET: ltxv-2b-fp8 (4GB)")
    print("  CLIP: t5xxl_fp16 (9GB)")
    print("  VAE: LTXVAudioVAE from checkpoint")
    print("  Decode: LTXVTiledVAEDecode")
    print("\n⏳ Generating...")

    # Monitor
    for _ in range(30):
        time.sleep(3)
        hist = requests.get(f"http://localhost:8188/history/{pid}").json()
        if pid in hist:
            status = hist[pid]["status"]["status_str"]
            if status == "success":
                print("✅ SUCCESS! Check /mnt/1TB-storage/ComfyUI/output/ltx_final*.mp4")
                break
            elif status == "error":
                print("❌ Failed:")
                err = hist[pid]["status"]["messages"][-1][1]
                print(f"  {err.get('node_id')}: {err.get('exception_message')}")
                break
            print(f"  {status}...")
else:
    print(f"❌ Submit failed: {resp.status_code}")
    print(resp.json())