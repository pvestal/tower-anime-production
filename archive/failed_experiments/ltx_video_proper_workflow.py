#!/usr/bin/env python3
"""
Proper LTX Video workflow based on official GitHub examples
Using LTXVBaseSampler and proper LTX Video nodes for 121-frame generation
"""

import requests
import json
import time
from pathlib import Path

def test_proper_ltx_workflow():
    print("🎬 TESTING PROPER LTX VIDEO WORKFLOW")
    print("Model: ltx-2/ltxv-2b-0.9.8-distilled.safetensors (6GB)")
    print("Using official LTX Video nodes structure")
    print("Target: 121 frames (5 seconds @ 24fps)")
    print("VRAM Usage: Expected ~10-11GB")

    # Based on official LTX-2 workflow examples from GitHub
    workflow = {
        # 1. Load LTX model
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
        },

        # 2. Text conditioning with T5 encoder (skip Gemma for now)
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime cyberpunk warrior running fast through neon city, dynamic motion, glowing lights reflecting off wet streets, action scene with particle effects, high quality cinematic movement",
                "clip": ["1", 1]
            }
        },

        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, boring, low quality, blurry, ugly, distorted",
                "clip": ["1", 1]
            }
        },

        # 4. Base image generation
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

        # 7. Create video latent space (LTX specific)
        "7": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 121,  # 5 seconds at 24fps
                "batch_size": 1
            }
        },

        # 8. Convert image to video latent with LTXVImgToVideo
        "8": {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "vae": ["1", 2],
                "image": ["6", 0],
                "width": 768,
                "height": 512,
                "length": 121,
                "batch_size": 1,
                "strength": 0.8
            }
        },

        # 9. LTX Video conditioning
        "9": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["8", 0],
                "negative": ["8", 1],
                "frame_rate": 24
            }
        },

        # 10. Use LTXVBaseSampler for proper video generation
        "10": {
            "class_type": "LTXVBaseSampler",
            "inputs": {
                "model": ["1", 0],
                "vae": ["1", 2],
                "width": 768,
                "height": 512,
                "num_frames": 121,
                "guider": ["11", 0],
                "sampler": ["12", 0],
                "sigmas": ["13", 0],
                "noise": ["14", 0]
            }
        },

        # 11. CFG Guider
        "11": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["9", 0],
                "negative": ["9", 1],
                "cfg": 3.0
            }
        },

        # 12. Sampler
        "12": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"}
        },

        # 13. Sigmas (schedule)
        "13": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": ["1", 0],
                "scheduler": "normal",
                "steps": 15,
                "denoise": 0.8
            }
        },

        # 14. Noise
        "14": {
            "class_type": "RandomNoise",
            "inputs": {
                "noise_seed": int(time.time()) % 2147483647
            }
        },

        # 15. Video output
        "15": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["10", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "ltx_proper_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

    # Submit workflow
    prompt = {"prompt": workflow, "client_id": "ltx_proper"}
    response = requests.post("http://localhost:8188/prompt", json=prompt)
    result = response.json()

    if "prompt_id" in result:
        print(f"✓ Proper LTX Video submitted - ID: {result['prompt_id']}")
        return result["prompt_id"]
    else:
        print(f"✗ Failed: {result}")
        return None

if __name__ == "__main__":
    job_id = test_proper_ltx_workflow()
    if job_id:
        print(f"Monitor progress: curl -s http://localhost:8188/history/{job_id}")
        print("Check output: ls /mnt/1TB-storage/ComfyUI/output/ltx_proper_*")