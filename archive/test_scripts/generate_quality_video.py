#!/usr/bin/env python3
"""
Generate HIGH-QUALITY video using the actual working SVD workflow
Based on kb_compliant_service.py which produces good results
"""

import requests
import json
import time
from pathlib import Path

def generate_quality_svd_video():
    """Generate high-quality video using SVD like the working kb_compliant_service"""

    print("🎬 Generating HIGH-QUALITY video using SVD (Stable Video Diffusion)...")
    print("📱 Resolution: 1024x576 (production quality)")
    print("🎞️ Method: SVD img2vid like kb_compliant_service")

    seed = int(time.time())

    workflow = {
        # Load base checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "AOM3A1B.safetensors"}
        },

        # Positive prompt
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "anime girl running through cyberpunk city at night, neon lights, dynamic action, high quality, detailed animation, professional artwork",
                "clip": ["1", 1]
            }
        },

        # Negative prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "static, still image, no motion, blurry, low quality, pixelated, ugly",
                "clip": ["1", 1]
            }
        },

        # Empty latent for BASE IMAGE (high resolution)
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 1024,
                "height": 576,
                "batch_size": 1
            }
        },

        # Generate HIGH-QUALITY base image
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 30,  # More steps for quality
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "model": ["1", 0],
                "denoise": 1.0
            }
        },

        # Decode base image
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2]
            }
        },

        # Load SVD model (QUALITY video generation)
        "7": {
            "class_type": "ImageOnlyCheckpointLoader",
            "inputs": {"ckpt_name": "svd_xt.safetensors"}
        },

        # SVD conditioning (this creates the REAL animation)
        "8": {
            "class_type": "SVD_img2vid_Conditioning",
            "inputs": {
                "clip_vision": ["7", 1],
                "init_image": ["6", 0],
                "vae": ["7", 2],
                "width": 1024,
                "height": 576,
                "video_frames": 25,
                "motion_bucket_id": 180,  # High motion
                "fps": 24,
                "augmentation_level": 0.0
            }
        },

        # Video CFG guidance
        "9": {
            "class_type": "VideoLinearCFGGuidance",
            "inputs": {
                "model": ["7", 0],
                "min_cfg": 1.0
            }
        },

        # Generate video frames with SVD
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed + 1000,
                "steps": 25,
                "cfg": 2.5,
                "sampler_name": "euler",
                "scheduler": "karras",
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["8", 2],
                "model": ["9", 0],
                "denoise": 1.0
            }
        },

        # Decode video frames
        "11": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["10", 0],
                "vae": ["7", 2]
            }
        },

        # Save as high-quality video
        "12": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["11", 0],
                "frame_rate": 24.0,
                "loop_count": 0,
                "filename_prefix": "QUALITY_SVD_VIDEO",
                "format": "video/h264-mp4",
                "crf": 18,
                "pingpong": False,
                "save_output": True
            }
        }
    }

    print("🚀 Submitting SVD workflow to ComfyUI...")

    response = requests.post('http://localhost:8188/prompt', json={"prompt": workflow})
    result = response.json()

    if 'prompt_id' in result:
        prompt_id = result['prompt_id']
        print(f"✅ Submitted: {prompt_id}")
        print("⏳ Generating HIGH-QUALITY video...")
        print("   📱 Resolution: 1024x576")
        print("   🎞️ Method: SVD img2vid")
        print("   ⏱️ Expected: 2-3 minutes")

        for i in range(180):  # 6 minutes max
            time.sleep(2)
            output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
            video_files = list(output_dir.glob("QUALITY_SVD_VIDEO_*.mp4"))

            if video_files:
                latest = max(video_files, key=lambda p: p.stat().st_mtime)
                print(f"\n✅ HIGH-QUALITY video generated: {latest}")

                import subprocess
                # Check quality
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries",
                     "stream=width,height,nb_frames,duration",
                     "-print_format", "json", str(latest)],
                    capture_output=True, text=True
                )

                if probe.stdout:
                    info = json.loads(probe.stdout)
                    if 'streams' in info and info['streams']:
                        stream = info['streams'][0]
                        print(f"📱 Resolution: {stream.get('width', 'unknown')}x{stream.get('height', 'unknown')}")
                        print(f"🎬 Frames: {stream.get('nb_frames', 'unknown')}")
                        print(f"⏱️ Duration: {stream.get('duration', 'unknown')}s")
                        print("✨ This should be REAL high-quality animated video!")

                return str(latest)

            if i % 15 == 0:
                print(f"  Still generating... ({i*2}s)")

        print("⚠️ Timeout")
    else:
        print(f"❌ Error: {result}")

    return None

if __name__ == "__main__":
    video = generate_quality_svd_video()
    if video:
        print(f"\n🎥 HIGH-QUALITY video ready: {video}")
    else:
        print("\n❌ Failed")