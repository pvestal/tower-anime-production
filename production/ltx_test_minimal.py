#!/usr/bin/env python3
"""
MINIMAL LTX test - just generate SOMETHING
"""

import requests
import json

# Absolute minimal workflow
workflow = {
    "1": {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "ltxv-2b-fp8.safetensors",
            "weight_dtype": "fp8_e4m3fn"
        }
    },
    "2": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "t5xxl_fp16.safetensors",
            "type": "ltxv"
        }
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "a video",
            "clip": ["2", 0]
        }
    },
    "4": {
        "class_type": "EmptyLTXVLatentVideo",
        "inputs": {
            "width": 512,
            "height": 384,
            "length": 13,  # Half second
            "batch_size": 1
        }
    },
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 1,
            "steps": 5,  # Minimal steps
            "cfg": 1.0,  # No guidance
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1.0,
            "model": ["1", 0],
            "positive": ["3", 0],
            "negative": ["3", 0],  # Same as positive
            "latent_image": ["4", 0]
        }
    },
    # Just save the latent directly as an image to see if sampling works
    "6": {
        "class_type": "SaveLatent",
        "inputs": {
            "samples": ["5", 0],
            "filename_prefix": "ltx_latent_test"
        }
    }
}

print("🧪 MINIMAL LTX TEST - Just checking if sampling works...")
resp = requests.post("http://localhost:8188/prompt", json={"prompt": workflow})

if resp.status_code == 200:
    print(f"✅ Submitted: {resp.json()['prompt_id']}")
    print("   If this works, latent will be saved to output folder")
    print("   Then we know sampling works and just need proper VAE")
else:
    print(f"❌ Failed: {resp.status_code}")
    err = resp.json()
    if 'node_errors' in err:
        for n, e in err['node_errors'].items():
            print(f"Node {n}: {e['errors'][0]['message']}")