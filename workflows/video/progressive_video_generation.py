#!/usr/bin/env python3
"""
Progressive Video Generation - From 2 seconds to 30 seconds
Building up complexity and length progressively
"""
import json
import requests
import time
import uuid
from datetime import datetime

COMFYUI_URL = "http://localhost:8188"

def create_short_video_workflow(duration_seconds=2, fps=12):
    """Create a simple 2-second video workflow"""

    total_frames = duration_seconds * fps  # 24 frames for 2 seconds at 12fps

    workflow = {
        # Load checkpoint
        "1": {
            "inputs": {
                "ckpt_name": "dreamshaper_8.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },

        # Load AnimateDiff model
        "2": {
            "inputs": {
                "model_name": "mm_sd_v15_v2.ckpt"
            },
            "class_type": "ADE_LoadAnimateDiffModel"
        },

        # Apply AnimateDiff to model
        "3": {
            "inputs": {
                "motion_model": ["2", 0],
                "model": ["1", 0],
                "context_options": ["4", 0]
            },
            "class_type": "ADE_ApplyAnimateDiffModel"
        },

        # Context options for AnimateDiff
        "4": {
            "inputs": {
                "context_length": total_frames,
                "context_stride": 1,
                "context_overlap": 4,
                "closed_loop": False
            },
            "class_type": "ADE_AnimateDiffUniformContextOptions"
        },

        # Positive prompt - A simple scene with movement
        "5": {
            "inputs": {
                "text": "beautiful anime girl with flowing silver hair, walking through magical forest, sunlight streaming through trees, particles floating in air, serene expression, blue dress flowing in wind, cinematic lighting, studio quality animation",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },

        # Negative prompt
        "6": {
            "inputs": {
                "text": "low quality, static, blurry, bad anatomy, distorted",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },

        # Empty latent for batch frames
        "7": {
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": total_frames
            },
            "class_type": "EmptyLatentImage"
        },

        # KSampler for generation
        "8": {
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["3", 0],  # Use AnimateDiff-applied model
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0]
            },
            "class_type": "KSampler"
        },

        # VAE Decode
        "9": {
            "inputs": {
                "samples": ["8", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },

        # Combine into video
        "10": {
            "inputs": {
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": f"video_{duration_seconds}s_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "images": ["9", 0]
            },
            "class_type": "VHS_VideoCombine"
        }
    }

    return {"prompt": workflow}

def create_multi_scene_video(duration_seconds=5, fps=12):
    """Create a 5-second video with scene transitions"""

    frames_per_scene = int((duration_seconds * fps) / 2)  # 2 scenes

    workflow = {
        # Checkpoint
        "1": {
            "inputs": {"ckpt_name": "animagine-xl-3.0.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        },

        # AnimateDiff
        "2": {
            "inputs": {
                "model_name": "mm_sd_v15_v2.ckpt",
                "context_length": frames_per_scene,
                "context_stride": 1,
                "context_overlap": 4,
                "closed_loop": False,
                "model": ["1", 0]
            },
            "class_type": "AnimateDiffLoaderWithContext"
        },

        # Scene 1 - Indoor
        "3": {
            "inputs": {
                "text": "anime girl sitting at desk, writing in journal, cozy bedroom, warm lamp light, night time, peaceful atmosphere, detailed background, books and plants",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },

        # Scene 2 - Outdoor
        "4": {
            "inputs": {
                "text": "same anime girl walking in garden, morning sunlight, flowers blooming, butterflies, green dress, happy expression, vibrant colors",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },

        # Negative
        "5": {
            "inputs": {
                "text": "low quality, blurry, distorted, bad anatomy",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },

        # Latent for scene 1
        "6": {
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": frames_per_scene
            },
            "class_type": "EmptyLatentImage"
        },

        # Generate scene 1
        "7": {
            "inputs": {
                "seed": 12345,
                "steps": 20,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0]
            },
            "class_type": "KSampler"
        },

        # Latent for scene 2
        "8": {
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": frames_per_scene
            },
            "class_type": "EmptyLatentImage"
        },

        # Generate scene 2
        "9": {
            "inputs": {
                "seed": 54321,
                "steps": 20,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["8", 0]
            },
            "class_type": "KSampler"
        },

        # Blend scenes
        "10": {
            "inputs": {
                "blend_factor": 0.5,
                "blend_mode": "normal",
                "samples1": ["7", 0],
                "samples2": ["9", 0]
            },
            "class_type": "LatentBlend"
        },

        # Decode
        "11": {
            "inputs": {
                "samples": ["10", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },

        # Video output
        "12": {
            "inputs": {
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": f"multi_scene_{duration_seconds}s_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "images": ["11", 0]
            },
            "class_type": "VHS_VideoCombine"
        }
    }

    return {"prompt": workflow}

def submit_workflow(workflow):
    """Submit workflow to ComfyUI"""

    # Add client ID
    client_id = str(uuid.uuid4())
    workflow["client_id"] = client_id

    print(f"Submitting workflow with client ID: {client_id}")

    response = requests.post(f"{COMFYUI_URL}/prompt", json=workflow)

    if response.status_code == 200:
        result = response.json()
        prompt_id = result.get("prompt_id", client_id)
        print(f"✅ Workflow submitted successfully! Prompt ID: {prompt_id}")
        return prompt_id
    else:
        print(f"❌ Failed to submit: {response.status_code}")
        print(response.text)
        return None

def monitor_generation(prompt_id, duration_estimate=30):
    """Monitor video generation progress"""

    print(f"\n⏳ Monitoring generation (estimated {duration_estimate} seconds)...")

    start_time = time.time()
    last_status = ""

    while time.time() - start_time < duration_estimate * 3:  # Max 3x estimated time
        try:
            # Check history
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")

            if response.status_code == 200:
                history = response.json()

                if prompt_id in history:
                    job_data = history[prompt_id]
                    status = job_data.get("status", {})

                    if status.get("completed", False):
                        outputs = job_data.get("outputs", {})

                        # Find video output
                        for node_id, output in outputs.items():
                            if "videos" in output:
                                for video in output["videos"]:
                                    filename = video.get("filename", "unknown")
                                    print(f"\n✅ Video generated successfully!")
                                    print(f"   Output: /mnt/1TB-storage/ComfyUI/output/{filename}")
                                    return filename
                            elif "images" in output:
                                # Might be individual frames
                                print(f"   Generated {len(output['images'])} frames")

                        return True

                    elif status.get("status_str") != last_status:
                        last_status = status.get("status_str", "processing")
                        print(f"   Status: {last_status}")

        except Exception as e:
            print(f"   Error checking status: {e}")

        time.sleep(2)

    print("⚠️ Generation timed out")
    return False

def generate_progressive_videos():
    """Generate videos progressively from 2s to 30s"""

    print("=" * 60)
    print("🎬 PROGRESSIVE VIDEO GENERATION")
    print("=" * 60)

    # Step 1: 2-second test
    print("\n📹 Step 1: Generating 2-second test video...")
    workflow_2s = create_short_video_workflow(duration_seconds=2, fps=12)
    prompt_id = submit_workflow(workflow_2s)

    if prompt_id:
        result = monitor_generation(prompt_id, duration_estimate=30)
        if result:
            print(f"✅ 2-second video complete: {result}")

    # Step 2: 5-second multi-scene
    print("\n📹 Step 2: Generating 5-second multi-scene video...")
    workflow_5s = create_multi_scene_video(duration_seconds=5, fps=12)
    prompt_id = submit_workflow(workflow_5s)

    if prompt_id:
        result = monitor_generation(prompt_id, duration_estimate=60)
        if result:
            print(f"✅ 5-second video complete: {result}")

    print("\n" + "=" * 60)
    print("✅ Progressive video generation complete!")
    print("=" * 60)

if __name__ == "__main__":
    generate_progressive_videos()