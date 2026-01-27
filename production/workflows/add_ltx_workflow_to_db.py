#!/usr/bin/env python3
"""
Add successful LTX Video 2B workflow to database SSOT
"""

import psycopg2
import json

def add_ltx_workflow_to_database():
    # Working LTX Video 2B workflow (121 frames, verified successful)
    ltx_workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "ltx-2/ltxv-2b-0.9.8-distilled.safetensors"}
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
                "text": "{{PROMPT}}",  # Placeholder for dynamic prompts
                "clip": ["2", 0]
            }
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, boring, low quality, blurry, ugly, distorted, bad animation",
                "clip": ["2", 0]
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 512, "batch_size": 1}
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "{{SEED}}",  # Placeholder for dynamic seed
                "steps": 20,
                "cfg": 7,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "model": ["1", 0],
                "denoise": 1.0
            }
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]}
        },
        "8": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 121,  # 5 seconds at 24fps
                "batch_size": 1
            }
        },
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
        "10": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["9", 0],
                "negative": ["9", 1],
                "frame_rate": 24
            }
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "{{SEED}}",
                "steps": 20,
                "cfg": 3,
                "sampler_name": "euler",
                "scheduler": "normal",
                "positive": ["10", 0],
                "negative": ["10", 1],
                "latent_image": ["8", 0],
                "model": ["1", 0],
                "denoise": 0.8
            }
        },
        "12": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["11", 0], "vae": ["1", 2]}
        },
        "13": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["12", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "ltx_2b_video_",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }

    # Connect to database
    conn = psycopg2.connect(
        host='localhost',
        database='tower_consolidated',
        user='patrick',
        password='RP78eIrW7cI2jYvL5akt1yurE'
    )

    cur = conn.cursor()

    # Insert the working LTX workflow
    cur.execute("""
        INSERT INTO video_workflow_templates
        (name, description, workflow_template, frame_count, fps)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        "ltx_2b_121_frame_workflow",
        "LTX Video 2B with separate T5 text encoder - generates 121 frames at 768x512, 24fps, 5.04 seconds. Uses CheckpointLoader + CLIPLoader approach. PROVEN WORKING.",
        json.dumps(ltx_workflow),
        121,
        24
    ))

    conn.commit()
    cur.close()
    conn.close()

    print("✅ LTX Video 2B workflow added to database SSOT")
    print("   Name: ltx_2b_121_frame_workflow")
    print("   Frames: 121 (5.04 seconds)")
    print("   Resolution: 768x512")
    print("   FPS: 24")

if __name__ == "__main__":
    add_ltx_workflow_to_database()