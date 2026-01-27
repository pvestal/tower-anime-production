#!/usr/bin/env python3
"""
Video Generation Tester
Actually test and validate video outputs instead of assuming success
"""

import subprocess
import os
from pathlib import Path
from PIL import Image
import requests

class VideoTester:
    """Test video generation outputs for actual quality"""

    def __init__(self):
        self.output_dir = Path("/mnt/1TB-storage/ComfyUI/output")

    def extract_frame(self, video_path, frame_num=0):
        """Extract specific frame from video for inspection"""
        if not Path(video_path).exists():
            return None

        frame_path = f"/tmp/test_frame_{frame_num}.png"
        cmd = [
            "ffmpeg", "-i", str(video_path), "-vf", f"select=eq(n\\,{frame_num})",
            "-vsync", "vfr", frame_path, "-y"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and Path(frame_path).exists():
            return frame_path
        return None

    def get_video_stats(self, video_path):
        """Get actual video statistics"""
        if not Path(video_path).exists():
            return None

        # Frame count
        frame_cmd = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                    "-show_entries", "stream=nb_read_frames", "-print_format",
                    "default=nokey=1:noprint_wrappers=1", str(video_path)]

        frame_result = subprocess.run(frame_cmd, capture_output=True, text=True)
        frame_count = int(frame_result.stdout.strip()) if frame_result.returncode == 0 else 0

        # Duration and dimensions
        info_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "stream=width,height,duration", "-print_format",
                   "default=nokey=1:noprint_wrappers=1", str(video_path)]

        info_result = subprocess.run(info_cmd, capture_output=True, text=True)
        if info_result.returncode == 0:
            lines = info_result.stdout.strip().split('\n')
            width = int(lines[0]) if len(lines) > 0 else 0
            height = int(lines[1]) if len(lines) > 1 else 0
            duration = float(lines[2]) if len(lines) > 2 else 0
        else:
            width = height = duration = 0

        file_size = Path(video_path).stat().st_size

        return {
            'frame_count': frame_count,
            'width': width,
            'height': height,
            'duration': duration,
            'file_size': file_size,
            'fps': frame_count / duration if duration > 0 else 0
        }

    def analyze_frame_quality(self, frame_path):
        """Basic frame quality analysis"""
        if not frame_path or not Path(frame_path).exists():
            return {'quality': 'failed', 'reason': 'frame not found'}

        try:
            img = Image.open(frame_path)
            width, height = img.size

            # Convert to RGB for analysis
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Get pixel data
            pixels = list(img.getdata())

            # Basic quality checks
            if len(pixels) == 0:
                return {'quality': 'failed', 'reason': 'no pixel data'}

            # Check for mostly black/single color (common failure mode)
            unique_colors = len(set(pixels[:100]))  # Sample first 100 pixels
            if unique_colors < 5:
                return {'quality': 'poor', 'reason': f'only {unique_colors} unique colors in sample'}

            # Check dimensions
            if width < 256 or height < 256:
                return {'quality': 'poor', 'reason': f'resolution too low: {width}x{height}'}

            return {
                'quality': 'acceptable',
                'width': width,
                'height': height,
                'unique_colors_sample': unique_colors
            }

        except Exception as e:
            return {'quality': 'failed', 'reason': str(e)}

    def test_latest_videos(self, count=3):
        """Test the most recent video outputs"""
        video_files = list(self.output_dir.glob("*.mp4"))
        if not video_files:
            print("❌ No video files found")
            return []

        # Sort by modification time, get most recent
        video_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        recent_videos = video_files[:count]

        results = []

        print(f"📊 Testing {len(recent_videos)} most recent videos:")

        for video_path in recent_videos:
            print(f"\n🎬 Testing: {video_path.name}")

            # Get video stats
            stats = self.get_video_stats(video_path)
            if not stats:
                print("   ❌ Could not analyze video")
                continue

            print(f"   📏 {stats['width']}x{stats['height']}, {stats['frame_count']} frames")
            print(f"   ⏱️  {stats['duration']:.2f}s, {stats['fps']:.1f} fps")
            print(f"   💾 {stats['file_size']} bytes")

            # Extract and analyze frame
            frame_path = self.extract_frame(video_path, 0)
            quality = self.analyze_frame_quality(frame_path)

            print(f"   🖼️  Frame quality: {quality['quality']}")
            if 'reason' in quality:
                print(f"       Reason: {quality['reason']}")

            results.append({
                'video': str(video_path),
                'stats': stats,
                'quality': quality
            })

            # Clean up temp frame
            if frame_path and Path(frame_path).exists():
                os.remove(frame_path)

        return results

    def test_workflow_output(self, workflow_name=""):
        """Test output from specific workflow"""
        pattern = f"*{workflow_name}*" if workflow_name else "*"
        video_files = list(self.output_dir.glob(f"{pattern}.mp4"))

        if not video_files:
            print(f"❌ No videos found matching pattern: {pattern}")
            return None

        latest_video = max(video_files, key=lambda x: x.stat().st_mtime)

        print(f"🎯 Testing workflow output: {latest_video.name}")

        stats = self.get_video_stats(latest_video)
        frame_path = self.extract_frame(latest_video, 0)
        quality = self.analyze_frame_quality(frame_path)

        result = {
            'workflow': workflow_name,
            'video': str(latest_video),
            'stats': stats,
            'quality': quality,
            'passed': quality['quality'] == 'acceptable' and stats['frame_count'] > 0
        }

        # Clean up
        if frame_path and Path(frame_path).exists():
            os.remove(frame_path)

        return result

def main():
    """Run video testing"""
    tester = VideoTester()

    print("🧪 VIDEO GENERATION TESTING")
    print("=" * 50)

    # Test recent outputs
    results = tester.test_latest_videos(5)

    # Summary
    passed = sum(1 for r in results if r['quality']['quality'] == 'acceptable')
    total = len(results)

    print(f"\n📊 SUMMARY: {passed}/{total} videos passed quality check")

    if passed < total:
        print("⚠️  Some videos failed quality validation")
        print("   Check frame extraction and generation parameters")

if __name__ == "__main__":
    main()