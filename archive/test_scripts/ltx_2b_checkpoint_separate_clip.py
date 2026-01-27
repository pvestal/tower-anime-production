#!/usr/bin/env python3
"""
LTX Video 2B with CheckpointLoader + separate T5 text encoder
Using the proper approach: CheckpointLoader for model, CLIPLoader for text encoder
"""

import requests
import json
import time
from pathlib import Path

def ltx_2b_with_separate_clip():
    print("🎬 LTX VIDEO 2B WITH SEPARATE TEXT ENCODER")
    print("Model: CheckpointLoader -> ltx-2/ltxv-2b-0.9.8-distilled.safetensors")
    print("Text Encoder: CLIPLoader -> t5xxl_fp16.safetensors (LTXV type)")
    print("Target: 121 frames (5 seconds @ 24fps)")

    workflow = {
        # 1. Load LTX 2B model via CheckpointLoader
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
        },

        # 2. Load separate T5 text encoder for LTX
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "t5xxl_fp16.safetensors",
                "type": "ltxv"
            }
        },

        # 3. Positive prompt using separate CLIP
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime cyberpunk warrior running fast through neon city with dynamic motion and glowing lights, action scene with particle effects, high quality cinematic movement, detailed animation",
                "clip": ["2", 0]
            }
        },

        # 4. Negative prompt using separate CLIP
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, boring, low quality, blurry, ugly, distorted, bad animation",
                "clip": ["2", 0]
            }
        },

        # 5. Generate base image for I2V
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 512, "batch_size": 1}
        },

        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "model": ["1", 0],  # LTX 2B model
                "denoise": 1.0
            }
        },

        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]}
        },

        # 8. LTX Video latent space - 121 frames
        "8": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 121,  # 5 seconds at 24fps
                "batch_size": 1
            }
        },

        # 9. Image to Video conversion
        "9": {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "vae": ["1", 2],
                "image": ["7", 0],
                "width": 768,
                "height": 512,
                "length": 121,
                "batch_size": 1,
                "strength": 0.8
            }
        },

        # 10. LTX conditioning
        "10": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["9", 0],
                "negative": ["9", 1],
                "frame_rate": 24
            }
        },

        # 11. Video sampling
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(time.time()) % 2147483647,
                "steps": 20,
                "cfg": 3,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["10", 0],
                "negative": ["10", 1],
                "latent_image": ["8", 0],
                "model": ["1", 0],  # LTX 2B model
                "denoise": 0.8
            }
        },

        # 12. Decode video
        "12": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["11", 0], "vae": ["1", 2]}
        },

        # 13. Save 121-frame video
        "13": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["12", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "ltx_2b_121_frames_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

    # Submit workflow
    prompt = {"prompt": workflow, "client_id": "ltx_2b_final"}
    response = requests.post("http://localhost:8188/prompt", json=prompt)
    result = response.json()

    if "prompt_id" in result:
        print(f"✓ LTX 2B + separate CLIP submitted - ID: {result['prompt_id']}")
        return result["prompt_id"]
    else:
        print(f"✗ Failed: {result}")
        return None

if __name__ == "__main__":
    job_id = ltx_2b_with_separate_clip()
    if job_id:
        print(f"Monitor: curl -s http://localhost:8188/history/{job_id}")
        print("Output: ls /mnt/1TB-storage/ComfyUI/output/ltx_2b_121_frames_*")
        print("🚀 THIS IS THE PROPER LTX 2B SETUP FOR 121 FRAMES")