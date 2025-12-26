#!/usr/bin/env python3
"""
Simple FFmpeg video converter - just stitch PNG frames
NO complex nodes, just basic frame-to-video conversion
"""
import subprocess
import os
from pathlib import Path
import glob

def convert_frames_to_video(frame_pattern, output_path, fps=24, quality="high"):
    """
    Simple FFmpeg conversion - exactly what user suggested

    Args:
        frame_pattern: Path pattern like "/path/frames/*.png" or "/path/frame_%04d.png"
        output_path: Output MP4 file path
        fps: Frames per second (default 24)
        quality: "high" or "standard"
    """

    print(f"🎬 Converting frames to video:")
    print(f"   Input pattern: {frame_pattern}")
    print(f"   Output: {output_path}")
    print(f"   FPS: {fps}")
    print(f"   Quality: {quality}")

    # Quality settings
    if quality == "high":
        crf = "18"  # High quality
        preset = "slow"
    else:
        crf = "23"  # Standard quality
        preset = "medium"

    # Check if we have frames
    if "*" in frame_pattern:
        frame_files = glob.glob(frame_pattern)
        if not frame_files:
            print(f"❌ No frames found matching: {frame_pattern}")
            return False
        print(f"   Found {len(frame_files)} frames")

    try:
        # Build FFmpeg command - user's exact suggestion
        if "*" in frame_pattern:
            # For glob pattern
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-pattern_type", "glob",
                "-i", frame_pattern,
                "-c:v", "libx264",
                "-vf", f"minterpolate='fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1'",
                "-crf", crf,
                "-preset", preset,
                "-pix_fmt", "yuv420p",
                output_path
            ]
        else:
            # For numbered pattern like frame_%04d.png
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", frame_pattern,
                "-c:v", "libx264",
                "-vf", f"minterpolate='fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1'",
                "-crf", crf,
                "-preset", preset,
                "-pix_fmt", "yuv420p",
                output_path
            ]

        print(f"🚀 Running FFmpeg...")
        print(f"   Command: {' '.join(cmd[:8])}...")

        # Run FFmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            # Check output file
            output_file = Path(output_path)
            if output_file.exists():
                size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"✅ Video created successfully!")
                print(f"   📁 {output_path}")
                print(f"   📊 Size: {size_mb:.2f} MB")

                # Get video info
                info_cmd = ["ffprobe", "-v", "quiet", "-show_format", "-show_streams", output_path]
                info_result = subprocess.run(info_cmd, capture_output=True, text=True)
                if "duration" in info_result.stdout.lower():
                    duration_line = [line for line in info_result.stdout.split('\n') if 'duration' in line.lower()]
                    if duration_line:
                        print(f"   ⏱️  {duration_line[0]}")

                return True
            else:
                print(f"❌ Output file not created")
                return False
        else:
            print(f"❌ FFmpeg failed:")
            print(f"   Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"❌ FFmpeg timeout (5 minutes)")
        return False
    except Exception as e:
        print(f"❌ FFmpeg error: {e}")
        return False

def quick_convert(character="yuki_takahashi", fps=24):
    """Quick conversion of existing frames"""

    # Check for existing frames in both directories
    possible_dirs = [
        "/mnt/1TB-storage/ComfyUI/output",
        "/mnt/1TB-storage/ComfyUI/output"
    ]

    for output_dir in possible_dirs:
        frame_pattern = f"{output_dir}/{character}_frames_*.png"
        frame_files = glob.glob(frame_pattern)

        if frame_files:
            print(f"🎯 Found {len(frame_files)} frames in {output_dir}")

            # Sort frames by number
            frame_files.sort()

            # Output video name
            video_output = f"{output_dir}/{character}_simple_video.mp4"

            # Convert
            success = convert_frames_to_video(frame_pattern, video_output, fps)

            if success:
                return video_output

    print(f"❌ No frames found for character: {character}")
    return None

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("🎬 SIMPLE VIDEO CONVERTER")
    print("   Basic FFmpeg frame stitching")
    print("=" * 60)

    if len(sys.argv) > 1:
        character = sys.argv[1]
    else:
        character = "yuki_takahashi"

    video_path = quick_convert(character)

    if video_path:
        print(f"\n🎉 SUCCESS! Video ready:")
        print(f"📁 {video_path}")

        # Video is already in ComfyUI output directory where it belongs
        print(f"📁 Video saved in ComfyUI output directory (no copy needed)")
    else:
        print("\n❌ Failed to create video")