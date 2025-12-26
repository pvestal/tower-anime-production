#!/usr/bin/env python3
"""
Proper video generation using YOUR working anime API infrastructure
"""
import json
import requests
import time
from pathlib import Path

def generate_reference_character():
    """Generate reference character using YOUR working API"""

    print("🎯 Generating reference character using YOUR API...")

    request_data = {
        "character_name": "VideoReference",
        "prompt": "beautiful anime girl with blue hair and blue eyes, detailed face, portrait, high quality, consistent character design",
        "negative_prompt": "bad anatomy, worst quality, blurry, multiple faces, inconsistent",
        "model_name": "chilloutmix_NiPrunedFp32Fix.safetensors",  # YOUR model
        "seed": 42,
        "steps": 30,  # YOUR default
        "cfg_scale": 7.0,  # YOUR default
        "width": 768,  # YOUR default
        "height": 1024  # YOUR default
    }

    response = requests.post(
        "http://localhost:8328/api/anime/character/v2/generate",
        json=request_data
    )

    if response.status_code != 200:
        print(f"❌ API failed: {response.status_code}")
        return None

    result = response.json()

    if result.get("success"):
        output_path = result["image_paths"][0]
        print(f"✅ Reference generated: {Path(output_path).name}")
        return output_path
    else:
        print(f"❌ Generation failed: {result}")
        return None

def generate_motion_frame(reference_path, motion_prompt, frame_num):
    """Generate motion frame using YOUR API with img2img approach"""

    print(f"  🎯 Frame {frame_num}: {motion_prompt}")

    # For video frames, reduce denoise to maintain consistency
    request_data = {
        "character_name": f"VideoFrame{frame_num:02d}",
        "prompt": f"beautiful anime girl with blue hair and blue eyes, {motion_prompt}, same character, consistent face, high quality",
        "negative_prompt": "bad anatomy, worst quality, blurry, different character, inconsistent face",
        "model_name": "chilloutmix_NiPrunedFp32Fix.safetensors",
        "seed": 42 + frame_num,  # Slight variation per frame
        "steps": 25,  # Slightly fewer for speed
        "cfg_scale": 7.0,
        "width": 768,
        "height": 1024,
        # TODO: Add img2img support to API for consistency
        # "controlnet_image": reference_path,
        # "controlnet_strength": 0.7
    }

    response = requests.post(
        "http://localhost:8328/api/anime/character/v2/generate",
        json=request_data
    )

    if response.status_code != 200:
        print(f"    ❌ Failed: {response.status_code}")
        return None

    result = response.json()

    if result.get("success"):
        output_path = result["image_paths"][0]
        print(f"    ✅ Generated: {Path(output_path).name}")
        return output_path
    else:
        print(f"    ❌ Failed: {result}")
        return None

def create_video_sequence():
    """Create video sequence using YOUR infrastructure properly"""

    print("🎬 CREATING VIDEO USING YOUR INFRASTRUCTURE")
    print("=" * 60)

    # Generate reference character
    reference = generate_reference_character()
    if not reference:
        return False

    # Motion sequence for video
    motions = [
        "slight head turn to the right",
        "gentle smile forming",
        "eyes blinking softly",
        "looking directly at viewer",
        "hair swaying gently",
        "peaceful expression"
    ]

    frames = [reference]

    # Generate motion frames
    for i, motion in enumerate(motions, 1):
        frame = generate_motion_frame(reference, motion, i+1)
        if frame:
            frames.append(frame)
        else:
            print(f"❌ Failed at frame {i+1}")
            return False

    print(f"\n✅ VIDEO SEQUENCE COMPLETE!")
    print(f"Generated {len(frames)} frames using YOUR API:")
    for i, frame in enumerate(frames, 1):
        print(f"  Frame {i}: {Path(frame).name}")

    # Combine into video using YOUR output directory
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    print(f"\n🎞️ Creating video from frames...")

    # Create frame list for ffmpeg
    frame_list = output_dir / "video_frames.txt"
    with open(frame_list, 'w') as f:
        for frame in frames:
            f.write(f"file '{frame}'\n")

    video_output = output_dir / "proper_video_using_your_api.mp4"

    import subprocess
    result = subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", str(frame_list),
        "-vf", "fps=8,scale=768:1024",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_output), "-y"
    ], capture_output=True, text=True)

    if result.returncode == 0 and video_output.exists():
        size_mb = video_output.stat().st_size / (1024*1024)
        print(f"✅ Video created: {video_output.name} ({size_mb:.1f}MB)")
        print(f"📁 Location: {video_output}")
        return True
    else:
        print(f"❌ Video creation failed: {result.stderr}")
        return False

if __name__ == "__main__":
    success = create_video_sequence()

    if success:
        print("\n🎉 SUCCESS! Video created using YOUR proper infrastructure")
        print("🎯 Used YOUR API, YOUR models, YOUR output directory")
    else:
        print("\n❌ Failed to create video")