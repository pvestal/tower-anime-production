#!/usr/bin/env python3
"""
Simplified LTX Video 2B workflow for 121-frame generation
Adapted from professional workflow to use 2B model instead of 19B
"""

import requests
import json
import time
from pathlib import Path

def test_ltx_2b_workflow():
    print("🎬 TESTING LTX VIDEO 2B WORKFLOW")
    print("Model: ltx-2/ltxv-2b-0.9.8-distilled.safetensors (6GB)")
    print("Target: 121 frames (5 seconds @ 24fps)")
    print("VRAM: 10.7GB available")

    # Simplified workflow based on professional example
    workflow = {
        # 1. Load LTX-2 2B model
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
        },

        # 2. Load text encoder
        "2": {
            "class_type": "LTXVGemmaCLIPModelLoader",
            "inputs": {
                "gemma_path": "gemma_3_12B_it.safetensors",
                "ltxv_path": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors",
                "max_length": 1024
            }
        },

        # 3. Positive prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime cyberpunk warrior running fast through neon city, dynamic motion, action scene, glowing lights",
                "clip": ["2", 0]
            }
        },

        # 4. Negative prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, boring, low quality, blurry",
                "clip": ["2", 0]
            }
        },

        # 5. LTX Video conditioning
        "5": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "frame_rate": 24
            }
        },

        # 6. Generate base image first
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 512, "batch_size": 1}
        },

        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0],
                "model": ["1", 0],
                "denoise": 1.0
            }
        },

        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["1", 2]}
        },

        # 9. Create video latent space
        "9": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 121,  # 5 seconds at 24fps
                "batch_size": 1
            }
        },

        # 10. Image to video conversion
        "10": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["1", 2],
                "image": ["8", 0],
                "latent": ["9", 0],
                "strength": 0.8,
                "bypass": False
            }
        },

        # 11. Basic sampler (simplified single-stage)
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 15,
                "cfg": 3,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["5", 0],
                "negative": ["5", 1],
                "latent_image": ["10", 0],
                "model": ["1", 0],
                "denoise": 0.8
            }
        },

        # 12. Decode to video frames
        "12": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["11", 0], "vae": ["1", 2]}
        },

        # 13. Save as video
        "13": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["12", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "ltx_2b_test_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

    # Submit workflow
    prompt = {"prompt": workflow, "client_id": "ltx_2b_test"}
    response = requests.post("http://localhost:8188/prompt", json=prompt)
    result = response.json()

    if "prompt_id" in result:
        print(f"✓ LTX Video 2B submitted - ID: {result['prompt_id']}")
        return result["prompt_id"]
    else:
        print(f"✗ Failed: {result}")
        return None

if __name__ == "__main__":
    job_id = test_ltx_2b_workflow()
    if job_id:
        print(f"Monitor progress: curl -s http://localhost:8188/history/{job_id}")
        print("Check output: ls /mnt/1TB-storage/ComfyUI/output/ltx_2b_test_*")