#!/usr/bin/env python3
"""
Simplified LTX Video workflow using standard text encoding
Avoids Gemma text encoder compatibility issues
"""

import requests
import json
import time
from pathlib import Path

def test_ltx_simple_workflow():
    print("🎬 TESTING SIMPLIFIED LTX VIDEO WORKFLOW")
    print("Model: ltx-2/ltxv-2b-0.9.8-distilled.safetensors (6GB)")
    print("Using standard CLIP encoding instead of Gemma")
    print("Target: 121 frames (5 seconds @ 24fps)")

    # Simplified workflow without Gemma encoder
    workflow = {
        # 1. Load LTX-2 2B model via CheckpointLoader
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
        },

        # 2. Positive prompt (using built-in CLIP from checkpoint)
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime cyberpunk warrior running through neon city with dynamic motion and glowing lights, action scene, high quality",
                "clip": ["1", 1]
            }
        },

        # 3. Negative prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, boring, low quality, blurry, ugly",
                "clip": ["1", 1]
            }
        },

        # 4. Generate base image
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 512, "batch_size": 1}
        },

        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "model": ["1", 0],
                "denoise": 1.0
            }
        },

        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]}
        },

        # 7. Create video latent space (121 frames)
        "7": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 121,  # 5 seconds at 24fps
                "batch_size": 1
            }
        },

        # 8. Convert image to video latent
        "8": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["1", 2],
                "image": ["6", 0],
                "latent": ["7", 0],
                "strength": 0.8,
                "bypass": False
            }
        },

        # 9. Sample video from latent (simplified)
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 10,  # Reduced steps for faster generation
                "cfg": 3,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["8", 0],
                "model": ["1", 0],
                "denoise": 0.7
            }
        },

        # 10. Decode video frames
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["1", 2]}
        },

        # 11. Save as video
        "11": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["10", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "ltx_simple_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

    # Submit workflow
    prompt = {"prompt": workflow, "client_id": "ltx_simple"}
    response = requests.post("http://localhost:8188/prompt", json=prompt)
    result = response.json()

    if "prompt_id" in result:
        print(f"✓ Simple LTX Video submitted - ID: {result['prompt_id']}")
        return result["prompt_id"]
    else:
        print(f"✗ Failed: {result}")
        return None

if __name__ == "__main__":
    job_id = test_ltx_simple_workflow()
    if job_id:
        print(f"Monitor progress: curl -s http://localhost:8188/history/{job_id}")
        print("Check output: ls /mnt/1TB-storage/ComfyUI/output/ltx_simple_*")