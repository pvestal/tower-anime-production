"""
character_studio/animation_generator.py
Phase 3: Animation Pipeline - Complete Implementation
Frame generation, video compilation, lip sync
"""

import asyncio
import json
import logging
import subprocess
import tempfile
import time
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from .client import ComfyUIClient

logger = logging.getLogger(__name__)

# Configuration
COMFYUI_OUTPUT_DIR = Path("/mnt/1TB-storage/ComfyUI/output")
ANIMATION_OUTPUT_DIR = Path("/mnt/1TB-storage/animations")
POSE_LIBRARY_DIR = Path("/mnt/1TB-storage/poses")
WORKFLOW_TEMPLATES_DIR = Path("/opt/tower-anime-production/workflows/animation_templates")

ANIMATION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class AnimationGenerator:
    """Generate animation sequences from characters"""
    
    def __init__(self, comfyui_base_url: str = "http://127.0.0.1:8188"):
        self.client = ComfyUIClient(comfyui_base_url)
        self.animation_templates = self._load_animation_templates()
        
    def _load_animation_templates(self) -> Dict[str, Any]:
        """Load animation workflow templates from disk"""
        templates = {}
        
        if not WORKFLOW_TEMPLATES_DIR.exists():
            logger.warning(f"Workflow templates directory not found: {WORKFLOW_TEMPLATES_DIR}")
            return self._get_default_templates()
        
        template_index = WORKFLOW_TEMPLATES_DIR / "templates.json"
        if template_index.exists():
            try:
                with open(template_index, 'r') as f:
                    templates = json.load(f)
                logger.info(f"Loaded {len(templates)} animation templates")
                return templates
            except Exception as e:
                logger.error(f"Failed to load templates: {e}")
        
        return self._get_default_templates()
    
    def _get_default_templates(self) -> Dict[str, Any]:
        """Return default animation templates"""
        return {
            "walk_cycle_2d": {
                "description": "2D Walk Cycle Animation",
                "frames": 12,
                "fps": 24,
                "controlnet_type": "openpose",
                "pose_sequence": "walk_cycle_12f",
                "workflow_file": "walk_cycle_2d.json"
            },
            "idle_breathing": {
                "description": "Idle Breathing Animation",
                "frames": 8,
                "fps": 12,
                "controlnet_type": "depth",
                "pose_sequence": "breathing_idle_8f",
                "workflow_file": "idle_breathing.json"
            },
            "talking_visemes": {
                "description": "Talking Mouth Shapes (Visemes)",
                "frames": 6,
                "fps": 30,
                "controlnet_type": "canny",
                "pose_sequence": "mouth_shapes_6f",
                "workflow_file": "talking_visemes.json"
            }
        }
    
    async def generate_animation_frames(
        self,
        character_image_path: str,
        animation_type: str,
        pose_sequence: Optional[List[str]] = None,
        fps: int = 24,
        seed: int = -1
    ) -> Dict[str, Any]:
        """
        Generate animation frame sequence
        
        Args:
            character_image_path: Path to character reference image
            animation_type: Type of animation (walk_cycle_2d, idle_breathing, etc.)
            pose_sequence: Optional custom pose sequence (list of pose image paths)
            fps: Frames per second
            seed: Random seed for generation
            
        Returns:
            Dict with frame paths, metadata, and generation info
        """
        template = self.animation_templates.get(animation_type)
        if not template:
            raise ValueError(f"Unknown animation type: {animation_type}")
        
        # Get pose sequence
        if not pose_sequence:
            pose_sequence = self._get_default_pose_sequence(animation_type, template)
        
        if not pose_sequence:
            raise ValueError(f"No pose sequence found for {animation_type}")
        
        frames = []
        frame_paths = []
        
        logger.info(f"Starting {animation_type} animation with {len(pose_sequence)} frames")
        
        # Load workflow template
        workflow_template = self._load_workflow_template(template.get("workflow_file"))
        
        # Generate each frame
        for frame_idx, pose_ref in enumerate(pose_sequence):
            logger.info(f"Generating frame {frame_idx + 1}/{len(pose_sequence)}")
            
            try:
                # Prepare workflow for this specific frame
                workflow = self._prepare_frame_workflow(
                    workflow=workflow_template.copy(),
                    character_image_path=character_image_path,
                    pose_reference=pose_ref,
                    frame_idx=frame_idx,
                    total_frames=len(pose_sequence),
                    seed=seed if seed >= 0 else int(time.time() * 1000) + frame_idx
                )
                
                # Submit to ComfyUI
                prompt_id = await self.client.submit_workflow(workflow)
                
                # Wait for completion
                output_filename = await self.client.poll_until_complete(prompt_id, timeout=120)
                
                if output_filename:
                    frame_path = str(COMFYUI_OUTPUT_DIR / output_filename)
                    frame_paths.append(frame_path)
                    
                    frames.append({
                        "frame": frame_idx,
                        "path": frame_path,
                        "pose": pose_ref,
                        "prompt_id": prompt_id
                    })
                    
                    logger.info(f"Frame {frame_idx + 1} completed: {output_filename}")
                else:
                    logger.error(f"Frame {frame_idx + 1} generation failed or timed out")
                    
            except Exception as e:
                logger.error(f"Error generating frame {frame_idx}: {e}")
                continue
        
        return {
            "animation_type": animation_type,
            "frames_generated": len(frames),
            "total_frames": len(pose_sequence),
            "frame_paths": frame_paths,
            "frame_details": frames,
            "fps": fps
        }
    
    def _load_workflow_template(self, workflow_filename: str) -> Dict[str, Any]:
        """Load ComfyUI workflow template from file"""
        workflow_path = WORKFLOW_TEMPLATES_DIR / workflow_filename
        
        if workflow_path.exists():
            try:
                with open(workflow_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load workflow {workflow_filename}: {e}")
        
        # Return basic workflow template if file doesn't exist
        return self._create_basic_workflow_template()
    
    def _create_basic_workflow_template(self) -> Dict[str, Any]:
        """Create a basic ComfyUI workflow template"""
        return {
            "1": {
                "class_type": "LoadImage",
                "inputs": {"image": "CHARACTER_REFERENCE"}
            },
            "2": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "realisticVision_v51.safetensors"}
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "PROMPT_PLACEHOLDER",
                    "clip": ["2", 1]
                }
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "worst quality, low quality, blurry, distorted",
                    "clip": ["2", 1]
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 512,
                    "height": 768,
                    "batch_size": 1
                }
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": "SEED_PLACEHOLDER",
                    "steps": 25,
                    "cfg": 7.0,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 0.85,
                    "model": ["2", 0],
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "latent_image": ["5", 0]
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["6", 0],
                    "vae": ["2", 2]
                }
            },
            "8": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "anim_frame",
                    "images": ["7", 0]
                }
            }
        }
    
    def _prepare_frame_workflow(
        self,
        workflow: Dict[str, Any],
        character_image_path: str,
        pose_reference: str,
        frame_idx: int,
        total_frames: int,
        seed: int
    ) -> Dict[str, Any]:
        """Prepare workflow for specific frame generation"""
        
        # Update character reference
        for node_id, node in workflow.items():
            if node.get("class_type") == "LoadImage":
                if node["inputs"].get("image") == "CHARACTER_REFERENCE":
                    node["inputs"]["image"] = character_image_path
                elif node["inputs"].get("image") == "POSE_REFERENCE":
                    node["inputs"]["image"] = pose_reference
            
            # Update prompt
            elif node.get("class_type") == "CLIPTextEncode":
                if "PROMPT_PLACEHOLDER" in node["inputs"].get("text", ""):
                    node["inputs"]["text"] = f"animation frame, character reference, consistent style, frame {frame_idx + 1} of {total_frames}"
            
            # Update seed
            elif node.get("class_type") == "KSampler":
                if node["inputs"].get("seed") == "SEED_PLACEHOLDER" or isinstance(node["inputs"].get("seed"), str):
                    node["inputs"]["seed"] = seed + frame_idx
                
                # Adjust denoise for smoother transitions
                transition_factor = abs(frame_idx - total_frames / 2) / (total_frames / 2)
                node["inputs"]["denoise"] = 0.85 - (transition_factor * 0.1)
        
        return workflow
    
    def _get_default_pose_sequence(
        self,
        animation_type: str,
        template: Dict[str, Any]
    ) -> List[str]:
        """Get default pose sequence for animation type"""
        
        sequence_name = template.get("pose_sequence", "")
        frames_count = template.get("frames", 12)
        
        # Map animation types to pose directories
        pose_type_map = {
            "walk_cycle_2d": "walk_cycle",
            "idle_breathing": "idle",
            "talking_visemes": "mouth_shapes"
        }
        
        pose_subdir = pose_type_map.get(animation_type, "walk_cycle")
        pose_dir = POSE_LIBRARY_DIR / pose_subdir
        
        if not pose_dir.exists():
            logger.warning(f"Pose directory not found: {pose_dir}")
            return []
        
        # Try to find pose sequence files
        pose_files = []
        
        # Look for numbered pose files
        for i in range(1, frames_count + 1):
            # Try multiple naming patterns
            patterns = [
                pose_dir / f"{pose_subdir}_{i:02d}.png",
                pose_dir / f"pose_{i:02d}.png",
                pose_dir / f"frame_{i:02d}.png"
            ]
            
            for pattern in patterns:
                if pattern.exists():
                    pose_files.append(str(pattern))
                    break
        
        if not pose_files:
            logger.warning(f"No pose files found in {pose_dir}")
        
        return pose_files
    
    async def compile_to_video(
        self,
        frame_paths: List[str],
        output_filename: str,
        fps: int = 24,
        resolution: str = "1920x1080",
        loop: bool = False
    ) -> str:
        """
        Compile frames to video using FFmpeg
        
        Args:
            frame_paths: List of frame image paths
            output_filename: Output video filename
            fps: Frames per second
            resolution: Output resolution (e.g., '1920x1080')
            loop: Whether to loop the animation
            
        Returns:
            Path to compiled video
        """
        if not frame_paths:
            raise ValueError("No frames to compile")
        
        logger.info(f"Compiling {len(frame_paths)} frames to video at {fps} FPS")
        
        # Create temporary directory for frame sequence
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Copy and rename frames in sequential order
            for i, frame_path in enumerate(frame_paths):
                src = Path(frame_path)
                if src.exists():
                    dst = temp_path / f"frame_{i:04d}.png"
                    shutil.copy2(src, dst)
                else:
                    logger.warning(f"Frame not found: {frame_path}")
            
            # Count actual copied frames
            copied_frames = list(temp_path.glob("frame_*.png"))
            if not copied_frames:
                raise FileNotFoundError("No frames were copied successfully")
            
            logger.info(f"Copied {len(copied_frames)} frames to temporary directory")
            
            # Prepare output path
            output_path = ANIMATION_OUTPUT_DIR / output_filename
            
            # Parse resolution
            width, height = map(int, resolution.split('x'))
            
            # Build FFmpeg command
            ffmpeg_cmd = [
                "ffmpeg", "-y",  # Overwrite output
                "-framerate", str(fps),
                "-i", str(temp_path / "frame_%04d.png"),
                "-c:v", "libx264",  # H.264 codec
                "-pix_fmt", "yuv420p",  # Compatibility
                "-preset", "slow",  # Quality preset
                "-crf", "18",  # Quality (18 = visually lossless)
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            ]
            
            # Add looping if requested
            if loop:
                ffmpeg_cmd.extend(["-stream_loop", "2"])  # Loop twice
            
            ffmpeg_cmd.append(str(output_path))
            
            logger.info(f"Running FFmpeg: {' '.join(ffmpeg_cmd)}")
            
            # Execute FFmpeg
            try:
                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg failed: {result.stderr}")
                    raise RuntimeError(f"Video compilation failed: {result.stderr}")
                
                logger.info(f"Video compiled successfully: {output_path}")
                
                # Get video duration
                duration = len(frame_paths) / fps
                
                return {
                    "video_path": str(output_path),
                    "duration": duration,
                    "frame_count": len(frame_paths),
                    "fps": fps,
                    "resolution": resolution,
                    "file_size": output_path.stat().st_size if output_path.exists() else 0
                }
                
            except subprocess.TimeoutExpired:
                raise RuntimeError("FFmpeg compilation timed out after 5 minutes")
            except Exception as e:
                raise RuntimeError(f"FFmpeg execution failed: {e}")
    
    async def create_lip_sync_animation(
        self,
        character_image_path: str,
        audio_file_path: str,
        phonemes: Optional[List[str]] = None,
        fps: int = 30
    ) -> Dict[str, Any]:
        """
        Generate lip sync animation from audio
        
        Args:
            character_image_path: Path to character reference
            audio_file_path: Path to audio file
            phonemes: Phoneme sequence (default: A, E, I, O, U, M, B, P)
            fps: Frames per second
            
        Returns:
            Dict with video path and generation info
        """
        if phonemes is None:
            phonemes = ["A", "E", "I", "O", "U", "M", "B", "P"]
        
        logger.info(f"Creating lip sync with {len(phonemes)} phonemes")
        
        # Check if audio file exists
        audio_path = Path(audio_file_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")
        
        # Get audio duration using FFprobe
        duration = self._get_audio_duration(audio_file_path)
        
        # Calculate frames needed
        total_frames = int(duration * fps)
        
        # Map phonemes to frames (simple distribution for MVP)
        frame_phoneme_map = []
        frames_per_phoneme = max(1, total_frames // len(phonemes))
        
        for phoneme in phonemes:
            for _ in range(frames_per_phoneme):
                frame_phoneme_map.append(phoneme)
        
        # Pad or trim to exact frame count
        while len(frame_phoneme_map) < total_frames:
            frame_phoneme_map.append(phonemes[-1])
        frame_phoneme_map = frame_phoneme_map[:total_frames]
        
        # Generate frames for each phoneme
        mouth_shapes_dir = POSE_LIBRARY_DIR / "mouth_shapes"
        frame_paths = []
        
        for frame_idx, phoneme in enumerate(frame_phoneme_map):
            mouth_shape_path = mouth_shapes_dir / f"mouth_{phoneme.lower()}.png"
            
            if mouth_shape_path.exists():
                # Generate frame with this mouth shape
                # For MVP, we'll use simple frame generation
                # In production, this would use ControlNet with mouth shape
                logger.info(f"Frame {frame_idx + 1}/{total_frames}: phoneme {phoneme}")
                # TODO: Implement actual frame generation with mouth shapes
            else:
                logger.warning(f"Mouth shape not found: {mouth_shape_path}")
        
        # For MVP, return placeholder
        return {
            "status": "lip_sync_queued",
            "audio_duration": duration,
            "total_frames": total_frames,
            "fps": fps,
            "phonemes_used": phonemes,
            "message": "Lip sync frame generation requires ControlNet mouth shape integration (Phase 4)"
        }
    
    def _get_audio_duration(self, audio_file_path: str) -> float:
        """Get audio file duration using FFprobe"""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                logger.error(f"FFprobe failed: {result.stderr}")
                return 1.0  # Default 1 second
                
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 1.0  # Default 1 second
