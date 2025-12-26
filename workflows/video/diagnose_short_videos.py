#!/usr/bin/env python3
"""
Video Frame Diagnostic Tool
Identifies slideshow vs smooth animation issues
"""

import subprocess
import json
import sys
import os
import glob
from pathlib import Path

def get_video_info(filepath):
    """Get detailed video metadata"""
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return None

    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams', '-show_format',
        filepath
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
    except Exception as e:
        print(f"❌ Error analyzing video: {e}")
        return None

    video_stream = next(
        (s for s in data['streams'] if s['codec_type'] == 'video'),
        None
    )

    if video_stream:
        print(f"\n🔍 Video Analysis for: {filepath}")
        print(f"   File size: {os.path.getsize(filepath) / 1024 / 1024:.2f} MB")

        # Duration from format data
        format_duration = float(data['format'].get('duration', 0))
        print(f"   Duration: {format_duration:.2f}s")

        # Frame info
        nb_frames = video_stream.get('nb_frames', 'Unknown')
        print(f"   Frame count: {nb_frames}")

        # Frame rate parsing
        r_frame_rate = video_stream.get('r_frame_rate', 'N/A')
        if '/' in r_frame_rate:
            num, denom = map(int, r_frame_rate.split('/'))
            fps = num / denom if denom > 0 else 0
            print(f"   Frame rate: {fps:.2f} fps (raw: {r_frame_rate})")
        else:
            fps = float(r_frame_rate) if r_frame_rate != 'N/A' else 0
            print(f"   Frame rate: {fps}")

        # Calculate actual framerate
        if nb_frames != 'Unknown' and format_duration > 0:
            actual_fps = float(nb_frames) / format_duration
            print(f"   Actual FPS: {actual_fps:.2f}")
            expected_frames = fps * format_duration
            print(f"   Expected frames: {expected_frames:.0f}")
            print(f"   Frame deficit: {expected_frames - float(nb_frames):.0f}")

            # Diagnose issues
            print("\n📊 Diagnosis:")
            if actual_fps < 1:
                print("   ❌ CRITICAL: Less than 1 FPS - This is a SLIDESHOW!")
                print("   Likely causes:")
                print("   1. Only generating keyframes, no interpolation")
                print("   2. RIFE interpolation disabled or misconfigured")
                print("   3. Wrong FPS setting in animation workflow")
            elif actual_fps < 10:
                print("   ⚠️ WARNING: Very low FPS - Choppy animation")
                print("   Likely causes:")
                print("   1. Insufficient interpolation factor")
                print("   2. Too few keyframes generated")
            elif actual_fps < fps * 0.9:
                print("   ⚠️ WARNING: Frame rate lower than target")
                print(f"   Missing ~{expected_frames - float(nb_frames):.0f} frames")
            else:
                print("   ✅ Frame rate looks good!")

        return video_stream
    else:
        print(f"❌ No video stream found in {filepath}")
        return None

def check_frame_generation(video_path):
    """Extract and analyze individual frames"""
    print("\n🎬 Frame Extraction Analysis:")

    # Create temp directory for frames
    temp_dir = Path("debug_frames_temp")
    temp_dir.mkdir(exist_ok=True)

    # Extract first 10 frames
    cmd = [
        'ffmpeg', '-i', video_path,
        '-frames:v', '10',
        str(temp_dir / 'frame_%04d.png'),
        '-y'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Count extracted frames
    frames = list(temp_dir.glob("frame_*.png"))
    print(f"   Extracted {len(frames)} frames")

    if len(frames) > 1:
        # Check if frames are identical (slideshow indicator)
        import hashlib

        hashes = []
        for frame in sorted(frames)[:5]:
            with open(frame, 'rb') as f:
                hashes.append(hashlib.md5(f.read()).hexdigest())

        unique_frames = len(set(hashes))
        print(f"   Unique frames in first 5: {unique_frames}")

        if unique_frames == 1:
            print("   ❌ All frames identical - STATIC IMAGE!")
        elif unique_frames < 3:
            print("   ⚠️ Very few unique frames - likely slideshow")
        else:
            print("   ✅ Frames are changing")

    # Cleanup
    for frame in frames:
        frame.unlink()
    temp_dir.rmdir()

def scan_generated_videos():
    """Scan for recently generated videos"""
    print("\n📁 Scanning for generated videos...")

    search_dirs = [
        "/opt/tower-anime-production/generated",
        "/opt/tower-anime-production/videos",
        "/mnt/1TB-storage/ComfyUI/output",
        "/mnt/1TB-storage/ComfyUI/output"
    ]

    videos_found = []

    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            patterns = ['*.mp4', '*.avi', '*.webm', '*.mov']
            for pattern in patterns:
                videos = glob.glob(os.path.join(search_dir, '**', pattern), recursive=True)
                videos_found.extend(videos)

    if videos_found:
        # Sort by modification time
        videos_found.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        print(f"   Found {len(videos_found)} videos")

        # Analyze most recent
        print("\n🎯 Analyzing 3 most recent videos:")
        for video in videos_found[:3]:
            get_video_info(video)
            check_frame_generation(video)
    else:
        print("   No videos found in standard directories")

    return videos_found

def check_rife_config():
    """Check RIFE interpolation configuration"""
    print("\n🔧 Checking RIFE Configuration:")

    workflow_files = glob.glob("/opt/tower-anime-production/workflows/**/*.json", recursive=True)

    for workflow_file in workflow_files:
        if 'rife' in workflow_file.lower() or '30' in workflow_file:
            with open(workflow_file, 'r') as f:
                try:
                    workflow = json.load(f)
                    print(f"\n   Workflow: {os.path.basename(workflow_file)}")

                    # Look for RIFE nodes
                    for node_id, node_data in workflow.items():
                        if isinstance(node_data, dict):
                            class_type = node_data.get('class_type', '')
                            if 'rife' in class_type.lower() or 'interpolat' in class_type.lower():
                                print(f"   Found interpolation node: {class_type}")
                                inputs = node_data.get('inputs', {})
                                if 'multiplier' in inputs:
                                    print(f"     Multiplier: {inputs['multiplier']}")
                                if 'frames' in inputs:
                                    print(f"     Frames: {inputs['frames']}")
                except:
                    pass

if __name__ == "__main__":
    print("=" * 60)
    print("🎬 ANIME VIDEO SLIDESHOW DIAGNOSTIC TOOL")
    print("=" * 60)

    if len(sys.argv) > 1:
        # Analyze specific video
        video_path = sys.argv[1]
        get_video_info(video_path)
        check_frame_generation(video_path)
    else:
        # Scan and analyze recent videos
        videos = scan_generated_videos()
        check_rife_config()

        print("\n" + "=" * 60)
        print("📋 RECOMMENDATIONS:")
        print("=" * 60)
        print("1. Check ComfyUI workflow has proper frame count")
        print("2. Verify RIFE interpolation multiplier (should be 8-24x)")
        print("3. Ensure AnimateDiff is generating motion, not static frames")
        print("4. Check that VHS_VideoCombine node has correct FPS setting")