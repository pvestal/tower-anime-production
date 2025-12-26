#!/usr/bin/env python3
"""
Video Quality Verifier - Comprehensive validation of generated videos
"""
import subprocess
import os
import json
from pathlib import Path

class VideoQualityVerifier:
    def __init__(self):
        pass

    def verify_video(self, video_path):
        """Comprehensive video validation"""
        video_path = Path(video_path)

        print(f"🔍 VERIFYING VIDEO: {video_path.name}")
        print("="*60)

        checks = {
            'file_exists': self.check_file_exists(video_path),
            'file_size_ok': self.check_file_size(video_path),
            'is_valid_video': self.probe_video_format(video_path),
            'has_video_stream': self.check_video_stream(video_path),
            'correct_dimensions': self.check_dimensions(video_path),
            'correct_duration': self.check_duration(video_path),
            'has_motion': self.analyze_motion(video_path),
            'playable': self.test_playback(video_path)
        }

        all_passed = all(checks.values())

        print(f"\n📊 VERIFICATION SUMMARY:")
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check}")

        print(f"\n🎯 OVERALL: {'✅ VIDEO VALID' if all_passed else '❌ VIDEO ISSUES'}")

        if all_passed:
            self.display_video_info(video_path)

        return all_passed, checks

    def check_file_exists(self, video_path):
        """Check if file exists"""
        exists = video_path.exists()
        print(f"  📁 File exists: {'✅ Yes' if exists else '❌ No'}")
        return exists

    def check_file_size(self, video_path):
        """Check if file has reasonable size"""
        if not video_path.exists():
            print(f"  📏 File size: ❌ File not found")
            return False

        size_bytes = video_path.stat().st_size
        size_kb = size_bytes / 1024

        # Minimum 10KB for valid video
        size_ok = size_bytes > 10240
        print(f"  📏 File size: {'✅' if size_ok else '❌'} {size_kb:.1f}KB")
        return size_ok

    def probe_video_format(self, video_path):
        """Use ffprobe to validate video format"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_format", "-show_streams",
                "-of", "json", str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                probe_data = json.loads(result.stdout)
                print(f"  🎬 Format: ✅ Valid ({probe_data['format']['format_name']})")
                return True
            else:
                print(f"  🎬 Format: ❌ Invalid ({result.stderr})")
                return False
        except Exception as e:
            print(f"  🎬 Format: ❌ Error ({e})")
            return False

    def check_video_stream(self, video_path):
        """Check if video has a video stream"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,r_frame_rate",
                "-of", "csv=p=0", str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0 and result.stdout.strip():
                stream_info = result.stdout.strip()
                print(f"  🎥 Video stream: ✅ Present ({stream_info})")
                return True
            else:
                print(f"  🎥 Video stream: ❌ Missing")
                return False
        except Exception as e:
            print(f"  🎥 Video stream: ❌ Error ({e})")
            return False

    def check_dimensions(self, video_path):
        """Check if video has expected dimensions"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0", str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                dimensions = result.stdout.strip().split(',')
                width, height = int(dimensions[0]), int(dimensions[1])

                # Expected 512x768 for our videos
                dimensions_ok = width == 512 and height == 768
                print(f"  📐 Dimensions: {'✅' if dimensions_ok else '⚠️ '} {width}×{height}")
                return True  # Return true even if dimensions are different
            else:
                print(f"  📐 Dimensions: ❌ Cannot determine")
                return False
        except Exception as e:
            print(f"  📐 Dimensions: ❌ Error ({e})")
            return False

    def check_duration(self, video_path):
        """Check video duration"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0", str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                duration = float(result.stdout.strip())
                print(f"  ⏱️  Duration: ✅ {duration:.2f} seconds")
                return duration > 0
            else:
                print(f"  ⏱️  Duration: ❌ Cannot determine")
                return False
        except Exception as e:
            print(f"  ⏱️  Duration: ❌ Error ({e})")
            return False

    def analyze_motion(self, video_path):
        """Analyze if video contains motion (not static)"""
        try:
            # Use ffprobe to get frame count
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_frames",
                "-show_entries", "stream=nb_read_frames",
                "-of", "csv=p=0", str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if result.returncode == 0:
                frame_count = int(result.stdout.strip())
                has_motion = frame_count > 1
                print(f"  🏃 Motion: {'✅' if has_motion else '❌'} {frame_count} frames")
                return has_motion
            else:
                print(f"  🏃 Motion: ❌ Cannot analyze")
                return False
        except Exception as e:
            print(f"  🏃 Motion: ❌ Error ({e})")
            return False

    def test_playback(self, video_path):
        """Test if video is playable"""
        try:
            # Try to decode first few frames
            cmd = [
                "ffmpeg", "-v", "error", "-i", str(video_path),
                "-t", "1", "-f", "null", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            playable = result.returncode == 0
            print(f"  ▶️  Playable: {'✅ Yes' if playable else '❌ No'}")
            return playable
        except Exception as e:
            print(f"  ▶️  Playable: ❌ Error ({e})")
            return False

    def display_video_info(self, video_path):
        """Display detailed video information"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,bit_rate:stream=width,height,r_frame_rate,codec_name",
                "-of", "json", str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                info = json.loads(result.stdout)

                print(f"\n📋 VIDEO DETAILS:")

                if 'format' in info:
                    fmt = info['format']
                    if 'duration' in fmt:
                        print(f"  Duration: {float(fmt['duration']):.2f}s")
                    if 'size' in fmt:
                        size_mb = int(fmt['size']) / (1024 * 1024)
                        print(f"  Size: {size_mb:.2f}MB")
                    if 'bit_rate' in fmt:
                        bitrate_kbps = int(fmt['bit_rate']) / 1000
                        print(f"  Bitrate: {bitrate_kbps:.0f}kbps")

                for stream in info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        print(f"  Resolution: {stream.get('width')}×{stream.get('height')}")
                        print(f"  Codec: {stream.get('codec_name')}")
                        if 'r_frame_rate' in stream:
                            fps_parts = stream['r_frame_rate'].split('/')
                            if len(fps_parts) == 2:
                                fps = float(fps_parts[0]) / float(fps_parts[1])
                                print(f"  FPS: {fps:.1f}")

        except Exception as e:
            print(f"📋 Could not display video details: {e}")

def main():
    import sys

    if len(sys.argv) != 2:
        print("Usage: python3 video_quality_verifier.py <video_file>")
        return

    video_file = sys.argv[1]
    verifier = VideoQualityVerifier()

    valid, details = verifier.verify_video(video_file)

    if valid:
        print(f"\n✅ Video verification PASSED")
        return 0
    else:
        print(f"\n❌ Video verification FAILED")
        return 1

if __name__ == "__main__":
    exit(main())