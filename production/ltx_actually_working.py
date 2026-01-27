#!/usr/bin/env python3
"""
LTX Video Generation that ACTUALLY WORKS
Based on the official example workflows
"""

import requests
import json
import time

print("🎯 LTX 2B Cowgirl Motion Test - PROPER SETUP")
print("=" * 60)

workflow = {
    # 1. Load the checkpoint (model + clip + vae)
    "checkpoint": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "ltxv-2b-fp8.safetensors"
        }
    },

    # 2. Load Audio VAE for LTX (special VAE for video)
    "ltx_vae": {
        "class_type": "LTXVAudioVAELoader",
        "inputs": {
            "ckpt_name": "ltxv-2b-fp8.safetensors"
        }
    },

    # 3. Positive prompt
    "positive": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "woman riding cowgirl position, rhythmic bouncing motion, intimate scene",
            "clip": ["checkpoint", 1]
        }
    },

    # 4. Negative prompt
    "negative": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "low quality, blurry, static, distorted",
            "clip": ["checkpoint", 1]
        }
    },

    # 5. Empty latent video
    "latent": {
        "class_type": "EmptyLTXVLatentVideo",
        "inputs": {
            "width": 768,
            "height": 512,
            "length": 25,  # 1 second
            "batch_size": 1
        }
    },

    # 6. LTX Conditioning
    "conditioning": {
        "class_type": "LTXVConditioning",
        "inputs": {
            "positive": ["positive", 0],
            "negative": ["negative", 0],
            "frame_rate": 24
        }
    },

    # 7. Sampling
    "sample": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 69420,
            "steps": 10,
            "cfg": 3.5,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": ["checkpoint", 0],
            "positive": ["conditioning", 0],
            "negative": ["conditioning", 1],
            "latent_image": ["latent", 0]
        }
    },

    # 8. VAE Decode using regular VAE from checkpoint
    "decode": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["sample", 0],
            "vae": ["checkpoint", 2]  # VAE from checkpoint
        }
    },

    # 9. Save video
    "save": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["decode", 0],
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "ltx_cowgirl_working",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True
        }
    }
}

# Submit workflow
response = requests.post(
    "http://localhost:8188/prompt",
    json={"prompt": workflow}
)

if response.status_code == 200:
    result = response.json()
    prompt_id = result.get('prompt_id')
    print(f"✅ SUCCESS! Workflow submitted")
    print(f"   Prompt ID: {prompt_id}")
    print(f"\n📹 Generating cowgirl motion video...")
    print(f"   Resolution: 768x512")
    print(f"   Duration: 1 second")
    print(f"   Output: /mnt/1TB-storage/ComfyUI/output/ltx_cowgirl_working*.mp4")

    # Monitor progress
    print(f"\n⏳ Monitoring progress...")
    for i in range(30):
        time.sleep(2)
        hist = requests.get(f"http://localhost:8188/history/{prompt_id}").json()
        if prompt_id in hist:
            status = hist[prompt_id]["status"]["status_str"]
            if status == "success":
                print(f"✅ GENERATION COMPLETE!")
                break
            elif status == "error":
                print(f"❌ Generation failed")
                msgs = hist[prompt_id]["status"]["messages"]
                if msgs:
                    error = msgs[-1][1]
                    print(f"   Error: {error.get('exception_message', 'Unknown')}")
                break
            else:
                print(f"   Status: {status}...")
else:
    print(f"❌ Failed to submit: {response.status_code}")
    error = response.json()
    if 'node_errors' in error:
        for node, err in error['node_errors'].items():
            print(f"\nNode {node} errors:")
            for e in err.get('errors', []):
                print(f"  - {e.get('message')}: {e.get('details')}")