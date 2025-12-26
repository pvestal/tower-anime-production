"""
Video Compilation Service
Compiles SVD frames into MP4 videos using FFmpeg
"""
import subprocess
import os
import glob
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class VideoCompiler:
    """Handles compilation of animation frames into video files"""
    
    def __init__(self, output_dir: str = "/mnt/1TB-storage/character_animations"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
    
    def compile_svd_frames_to_video(
        self,
        frame_pattern: str,
        character_name: str,
        project: str,
        fps: int = 6,
        resolution: str = "1024x576"
    ) -> Optional[str]:
        """Compile SVD frames into MP4 video"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_char_name = character_name.replace(" ", "_")
            safe_project = project.replace(" ", "_")
            output_filename = f"{safe_project}_{safe_char_name}_svd_{timestamp}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)
            
            frame_files = sorted(glob.glob(frame_pattern))
            
            if not frame_files:
                logger.error(f"No frames found: {frame_pattern}")
                return None
            
            frames_dir = os.path.dirname(frame_files[0])
            file_list_path = os.path.join(frames_dir, f"frames_{timestamp}.txt")
            
            with open(file_list_path, 'w') as f:
                for frame_file in frame_files:
                    f.write(f"file '{frame_file}'\n")
                    f.write(f"duration {1/fps}\n")
                f.write(f"file '{frame_files[-1]}'\n")
            
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', file_list_path,
                '-vf', f'scale={resolution}',
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                output_path
            ]
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=300)
            
            os.remove(file_list_path)
            
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"✓ Video: {output_path}")
                return output_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

video_compiler = VideoCompiler()
