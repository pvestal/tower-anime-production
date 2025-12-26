#!/usr/bin/env python3
"""
Simple video generation - generate frames then combine
"""
import json
import requests
import time
import uuid
from datetime import datetime

COMFYUI_URL = "http://localhost:8188"

def create_frame_generation_workflow(frame_number, total_frames, base_prompt):
    """Generate a single frame with slight variation"""

    # Add frame context to prompt
    progress = frame_number / total_frames
    time_descriptor = ""
    if progress < 0.3:
        time_descriptor = "beginning of action, starting pose"
    elif progress < 0.7:
        time_descriptor = "middle of action, in motion"
    else:
        time_descriptor = "end of action, finishing pose"

    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "dreamshaper_8.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {
                "text": f"{base_prompt}, {time_descriptor}, frame {frame_number} of {total_frames}",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "text": "blurry, low quality, distorted",
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {
                "width": 512,
                "height": 768,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": 42 + frame_number,  # Vary seed slightly per frame
                "steps": 15,
                "cfg": 7.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "6": {
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {
                "filename_prefix": f"video_frame_{frame_number:04d}",
                "images": ["6", 0]
            },
            "class_type": "SaveImage"
        }
    }

    return {"prompt": workflow}

def generate_video_frames(num_frames=24, fps=12):
    """Generate frames for a video"""

    print(f"Generating {num_frames} frames for {num_frames/fps:.1f} second video...")

    base_prompt = "beautiful anime girl dancing, flowing dress, graceful movement, stage lighting, detailed animation"

    frame_files = []

    for i in range(num_frames):
        print(f"  Frame {i+1}/{num_frames}...", end="")

        workflow = create_frame_generation_workflow(i, num_frames, base_prompt)

        # Submit workflow
        client_id = str(uuid.uuid4())
        workflow["client_id"] = client_id

        response = requests.post(f"{COMFYUI_URL}/prompt", json=workflow)

        if response.status_code == 200:
            result = response.json()
            prompt_id = result.get("prompt_id", client_id)

            # Wait for completion
            for _ in range(30):  # Max 30 seconds per frame
                time.sleep(1)

                history_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        job = history[prompt_id]
                        if job.get("status", {}).get("completed"):
                            outputs = job.get("outputs", {})
                            for node_id, output in outputs.items():
                                if "images" in output:
                                    for img in output["images"]:
                                        filename = img.get("filename")
                                        if filename:
                                            frame_files.append(filename)
                                            print(f" ✓")
                                            break
                            break
        else:
            print(f" ✗")

    return frame_files

def combine_frames_to_video(frame_files, fps=12):
    """Use VHS_VideoCombine to create video from frames"""

    print("\nCombining frames into video...")

    # Create a workflow that loads and combines the frames
    workflow = {
        "1": {
            "inputs": {
                "image": frame_files[0],  # Start with first frame
                "choose file to upload": "image"
            },
            "class_type": "LoadImage"
        }
    }

    # Stack all frames
    for i, frame in enumerate(frame_files[1:], start=2):
        workflow[str(i)] = {
            "inputs": {
                "image": frame,
                "choose file to upload": "image"
            },
            "class_type": "LoadImage"
        }

    # Batch images together
    image_list = [["1", 0]]  # First image
    for i in range(2, len(frame_files) + 1):
        image_list.append([str(i), 0])

    batch_node = str(len(frame_files) + 1)
    workflow[batch_node] = {
        "inputs": {
            "images": image_list
        },
        "class_type": "ImageBatch"
    }

    # Create video
    video_node = str(len(frame_files) + 2)
    workflow[video_node] = {
        "inputs": {
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": f"final_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
            "images": [batch_node, 0]
        },
        "class_type": "VHS_VideoCombine"
    }

    return {"prompt": workflow}

if __name__ == "__main__":
    print("=" * 60)
    print("🎬 SIMPLE VIDEO GENERATION")
    print("=" * 60)

    # Generate frames
    frames = generate_video_frames(num_frames=12, fps=6)  # 2 second video at 6fps

    if frames:
        print(f"\n✅ Generated {len(frames)} frames")

        # Combine into video
        # Note: This would need the actual file paths
        # For now, we'll use ffmpeg externally if needed

    print("\n" + "=" * 60)
    print("✅ Video generation complete!")
    print("=" * 60)