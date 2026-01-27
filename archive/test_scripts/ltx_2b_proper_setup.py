#!/usr/bin/env python3
"""
Proper LTX Video 2B setup with separate text encoder and VAE loading
Using UNETLoader for 2B model + separate CLIP + VAE
"""

import requests
import json
import time
from pathlib import Path

def setup_ltx_2b_properly():
    print("🎬 PROPER LTX VIDEO 2B SETUP")
    print("Model: ltxv-2b-0.9.8-distilled.safetensors (6GB)")
    print("Text Encoder: t5xxl_fp16.safetensors")
    print("VAE: ltx2_vae.safetensors")
    print("Target: 121 frames (5 seconds @ 24fps)")

    workflow = {
        # 1. Load LTX Video 2B model via UNETLoader
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors",
                "weight_dtype": "default"
            }
        },

        # 2. Load T5 text encoder for LTX
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "t5xxl_fp16.safetensors",
                "type": "ltxv"
            }
        },

        # 3. Load LTX VAE
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "ltx2_vae.safetensors"}
        },

        # 4. Positive prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime cyberpunk warrior running fast through neon city with dynamic motion, glowing lights reflecting off wet streets, action scene with particle effects and energy trails, high quality cinematic movement, detailed character design",
                "clip": ["2", 0]
            }
        },

        # 5. Negative prompt
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, boring, low quality, blurry, ugly, distorted, bad anatomy, poorly drawn",
                "clip": ["2", 0]
            }
        },

        # 6. Generate base image for I2V
        "6": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "realisticVision_v51.safetensors"}
        },

        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime cyberpunk warrior, neon city background, dynamic pose",
                "clip": ["6", 1]
            }
        },

        "8": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry",
                "clip": ["6", 1]
            }
        },

        "9": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 512, "batch_size": 1}
        },

        "10": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["7", 0],
                "negative": ["8", 0],
                "latent_image": ["9", 0],
                "model": ["6", 0],
                "denoise": 1.0
            }
        },

        "11": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["10", 0], "vae": ["6", 2]}
        },

        # 12. LTX Video generation - 121 frames
        "12": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 121,  # 5 seconds at 24fps
                "batch_size": 1
            }
        },

        # 13. Image to Video with LTX
        "13": {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "vae": ["3", 0],
                "image": ["11", 0],
                "width": 768,
                "height": 512,
                "length": 121,
                "batch_size": 1,
                "strength": 0.8
            }
        },

        # 14. LTX Conditioning
        "14": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["13", 0],
                "negative": ["13", 1],
                "frame_rate": 24
            }
        },

        # 15. Sample with LTX model
        "15": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 3,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["14", 0],
                "negative": ["14", 1],
                "latent_image": ["12", 0],
                "model": ["1", 0],  # LTX 2B model
                "denoise": 0.8
            }
        },

        # 16. Decode with LTX VAE
        "16": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["15", 0], "vae": ["3", 0]}
        },

        # 17. Save 121-frame video
        "17": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["16", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "ltx_2b_proper_121_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

    # Submit workflow
    prompt = {"prompt": workflow, "client_id": "ltx_2b_proper"}
    response = requests.post("http://localhost:8188/prompt", json=prompt)
    result = response.json()

    if "prompt_id" in result:
        print(f"✓ LTX Video 2B proper setup submitted - ID: {result['prompt_id']}")
        return result["prompt_id"]
    else:
        print(f"✗ Failed: {result}")
        return None

if __name__ == "__main__":
    job_id = setup_ltx_2b_properly()
    if job_id:
        print(f"Monitor: curl -s http://localhost:8188/history/{job_id}")
        print("Output: ls /mnt/1TB-storage/ComfyUI/output/ltx_2b_proper_121_*")
        print("🎯 THIS SHOULD GENERATE 121 FRAMES WITH PROPER LTX SETUP")