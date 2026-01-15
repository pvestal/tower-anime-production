"""
Keyframe Animator for Tower Anime Production.

Integrates pose management with FramePack scene generation for
pose-to-pose animation workflows.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from services.animation.pose_manager import (
    PoseManager,
    PoseCategory,
    EmotionType,
    OpenPoseKeypoints,
    CharacterPose,
)
from services.animation.shot_assembler import (
    ShotAssembler,
    TransitionType,
    TransitionSpec,
)

logger = logging.getLogger(__name__)


class MotionCurve(Enum):
    """Motion interpolation curves."""
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    BOUNCE = "bounce"
    ELASTIC = "elastic"


@dataclass
class Keyframe:
    """A keyframe in the animation timeline."""
    time_ms: int
    pose_id: Optional[int] = None
    pose: Optional[OpenPoseKeypoints] = None
    motion_curve: MotionCurve = MotionCurve.EASE_IN_OUT
    hold_frames: int = 0  # Frames to hold this pose before transitioning
    prompt_override: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnimationClip:
    """A complete animation clip definition."""
    id: int
    name: str
    character_id: int
    keyframes: List[Keyframe]
    duration_ms: int
    fps: int = 30
    width: int = 1280
    height: int = 720
    base_prompt: str = ""
    negative_prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """Result of keyframe animation generation."""
    clip_id: int
    output_path: str
    duration_ms: int
    frames_generated: int
    quality_score: float
    success: bool
    error: Optional[str] = None


class KeyframeAnimator:
    """
    Creates pose-to-pose animations using keyframes.

    Integrates:
    - PoseManager for keyframe poses
    - FramePack/ComfyUI for video generation
    - ShotAssembler for final output
    """

    def __init__(
        self,
        database_url: str,
        comfyui_url: str = "http://localhost:8188",
        output_dir: str = "/mnt/1TB-storage/ComfyUI/output/keyframe_anim",
        pose_images_dir: str = "/mnt/1TB-storage/poses"
    ):
        """
        Initialize Keyframe Animator.

        Args:
            database_url: PostgreSQL connection URL
            comfyui_url: ComfyUI server URL
            output_dir: Directory for output videos
            pose_images_dir: Directory for pose images
        """
        self.database_url = database_url
        self.comfyui_url = comfyui_url
        self.output_dir = Path(output_dir)
        self.pose_images_dir = Path(pose_images_dir)

        self.pose_manager: Optional[PoseManager] = None
        self.shot_assembler: Optional[ShotAssembler] = None
        self.pool = None

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> None:
        """Initialize all connections."""
        import asyncpg
        self.pool = await asyncpg.create_pool(self.database_url)

        self.pose_manager = PoseManager(self.database_url, str(self.pose_images_dir))
        await self.pose_manager.connect()

        self.shot_assembler = ShotAssembler(self.database_url, str(self.output_dir))
        await self.shot_assembler.connect()

        await self._ensure_tables()
        logger.info("KeyframeAnimator connected")

    async def close(self) -> None:
        """Close all connections."""
        if self.pose_manager:
            await self.pose_manager.close()
        if self.shot_assembler:
            await self.shot_assembler.close()
        if self.pool:
            await self.pool.close()

    async def _ensure_tables(self) -> None:
        """Create animation clip tables."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS animation_clips (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    character_id INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    fps INTEGER DEFAULT 30,
                    width INTEGER DEFAULT 1280,
                    height INTEGER DEFAULT 720,
                    base_prompt TEXT,
                    negative_prompt TEXT,
                    status VARCHAR(50) DEFAULT 'draft',
                    output_path VARCHAR(500),
                    quality_score FLOAT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS clip_keyframes (
                    id SERIAL PRIMARY KEY,
                    clip_id INTEGER REFERENCES animation_clips(id) ON DELETE CASCADE,
                    time_ms INTEGER NOT NULL,
                    pose_id INTEGER,
                    pose_data BYTEA,
                    motion_curve VARCHAR(50) DEFAULT 'ease_in_out',
                    hold_frames INTEGER DEFAULT 0,
                    prompt_override TEXT,
                    metadata JSONB DEFAULT '{}',

                    UNIQUE(clip_id, time_ms)
                );

                CREATE TABLE IF NOT EXISTS clip_segments (
                    id SERIAL PRIMARY KEY,
                    clip_id INTEGER REFERENCES animation_clips(id) ON DELETE CASCADE,
                    segment_order INTEGER NOT NULL,
                    start_keyframe_id INTEGER,
                    end_keyframe_id INTEGER,
                    video_path VARCHAR(500),
                    status VARCHAR(50) DEFAULT 'pending',
                    comfyui_prompt_id VARCHAR(100),
                    quality_score FLOAT,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_clip_keyframes_clip ON clip_keyframes(clip_id);
                CREATE INDEX IF NOT EXISTS idx_clip_segments_clip ON clip_segments(clip_id);
            """)

    # === Animation Clip Management ===

    async def create_clip(
        self,
        name: str,
        character_id: int,
        duration_ms: int,
        fps: int = 30,
        width: int = 1280,
        height: int = 720,
        base_prompt: str = "",
        negative_prompt: str = "low quality, blurry, distorted",
        metadata: Dict = None
    ) -> int:
        """
        Create a new animation clip.

        Args:
            name: Clip name
            character_id: Character to animate
            duration_ms: Total duration in milliseconds
            fps: Frames per second
            width: Video width
            height: Video height
            base_prompt: Base prompt for generation
            negative_prompt: Negative prompt
            metadata: Additional metadata

        Returns:
            Clip ID
        """
        async with self.pool.acquire() as conn:
            clip_id = await conn.fetchval("""
                INSERT INTO animation_clips
                (name, character_id, duration_ms, fps, width, height,
                 base_prompt, negative_prompt, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """,
                name,
                character_id,
                duration_ms,
                fps,
                width,
                height,
                base_prompt,
                negative_prompt,
                json.dumps(metadata or {})
            )

        logger.info(f"Created animation clip '{name}' with ID {clip_id}")
        return clip_id

    async def add_keyframe(
        self,
        clip_id: int,
        time_ms: int,
        pose_id: Optional[int] = None,
        pose: Optional[OpenPoseKeypoints] = None,
        motion_curve: MotionCurve = MotionCurve.EASE_IN_OUT,
        hold_frames: int = 0,
        prompt_override: Optional[str] = None,
        metadata: Dict = None
    ) -> int:
        """
        Add a keyframe to an animation clip.

        Args:
            clip_id: Clip ID
            time_ms: Time position in milliseconds
            pose_id: Reference to stored pose (mutually exclusive with pose)
            pose: Direct pose data (mutually exclusive with pose_id)
            motion_curve: Interpolation curve to next keyframe
            hold_frames: Frames to hold before transitioning
            prompt_override: Override prompt for this keyframe
            metadata: Additional metadata

        Returns:
            Keyframe ID
        """
        pose_data = pose.to_bytes() if pose else None

        async with self.pool.acquire() as conn:
            keyframe_id = await conn.fetchval("""
                INSERT INTO clip_keyframes
                (clip_id, time_ms, pose_id, pose_data, motion_curve, hold_frames,
                 prompt_override, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (clip_id, time_ms) DO UPDATE SET
                    pose_id = EXCLUDED.pose_id,
                    pose_data = EXCLUDED.pose_data,
                    motion_curve = EXCLUDED.motion_curve,
                    hold_frames = EXCLUDED.hold_frames,
                    prompt_override = EXCLUDED.prompt_override,
                    metadata = EXCLUDED.metadata
                RETURNING id
            """,
                clip_id,
                time_ms,
                pose_id,
                pose_data,
                motion_curve.value,
                hold_frames,
                prompt_override,
                json.dumps(metadata or {})
            )

        logger.info(f"Added keyframe at {time_ms}ms to clip {clip_id}")
        return keyframe_id

    async def add_keyframes_from_sequence(
        self,
        clip_id: int,
        sequence_id: int,
        start_time_ms: int = 0
    ) -> List[int]:
        """
        Add keyframes from a pose sequence.

        Args:
            clip_id: Clip ID
            sequence_id: Pose sequence ID
            start_time_ms: Starting time offset

        Returns:
            List of keyframe IDs
        """
        sequence = await self.pose_manager.get_sequence(sequence_id)
        if not sequence:
            raise ValueError(f"Sequence {sequence_id} not found")

        keyframe_ids = []
        current_time = start_time_ms

        for i, (pose_id, duration_ms) in enumerate(zip(
            sequence["pose_ids"],
            sequence["durations_ms"]
        )):
            # Get interpolation type
            interp = "ease_in_out"
            if i < len(sequence["interpolation_types"]):
                interp = sequence["interpolation_types"][i]

            kf_id = await self.add_keyframe(
                clip_id=clip_id,
                time_ms=current_time,
                pose_id=pose_id,
                motion_curve=MotionCurve(interp)
            )
            keyframe_ids.append(kf_id)
            current_time += duration_ms

        return keyframe_ids

    # === Animation Generation ===

    async def generate_animation(
        self,
        clip_id: int,
        use_framepack: bool = True
    ) -> GenerationResult:
        """
        Generate the full animation from keyframes.

        This is the main entry point for animation generation.

        Args:
            clip_id: Animation clip ID
            use_framepack: Use FramePack for video generation

        Returns:
            GenerationResult with output path and stats
        """
        try:
            # Get clip info
            clip = await self._get_clip(clip_id)
            if not clip:
                raise ValueError(f"Clip {clip_id} not found")

            # Get keyframes
            keyframes = await self._get_clip_keyframes(clip_id)
            if len(keyframes) < 2:
                raise ValueError("Need at least 2 keyframes")

            # Update status
            await self._update_clip_status(clip_id, "processing")

            # Generate segments between keyframes
            segment_paths = []

            for i in range(len(keyframes) - 1):
                start_kf = keyframes[i]
                end_kf = keyframes[i + 1]

                segment_path = await self._generate_segment(
                    clip=clip,
                    start_keyframe=start_kf,
                    end_keyframe=end_kf,
                    segment_index=i,
                    use_framepack=use_framepack
                )

                if segment_path:
                    segment_paths.append(segment_path)

            if not segment_paths:
                raise ValueError("No segments generated")

            # Assemble segments
            output_filename = f"clip_{clip_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            output_path = self.output_dir / output_filename

            assembly_result = await self.shot_assembler.assemble_shots_simple(
                video_paths=segment_paths,
                output_filename=output_filename,
                transition=TransitionType.CUT
            )

            if not assembly_result.success:
                raise ValueError(f"Assembly failed: {assembly_result.error}")

            # Update clip with result
            await self._update_clip_completed(
                clip_id,
                str(output_path),
                assembly_result.duration_ms
            )

            return GenerationResult(
                clip_id=clip_id,
                output_path=str(output_path),
                duration_ms=assembly_result.duration_ms,
                frames_generated=int(assembly_result.duration_ms / 1000 * clip["fps"]),
                quality_score=0.85,  # TODO: Actual quality assessment
                success=True
            )

        except Exception as e:
            logger.error(f"Animation generation failed: {e}")
            await self._update_clip_status(clip_id, "failed")
            return GenerationResult(
                clip_id=clip_id,
                output_path="",
                duration_ms=0,
                frames_generated=0,
                quality_score=0,
                success=False,
                error=str(e)
            )

    async def _generate_segment(
        self,
        clip: Dict,
        start_keyframe: Dict,
        end_keyframe: Dict,
        segment_index: int,
        use_framepack: bool
    ) -> Optional[str]:
        """Generate a single segment between two keyframes."""
        import httpx
        import time

        try:
            # Get poses for keyframes
            start_pose = await self._get_keyframe_pose(start_keyframe)
            end_pose = await self._get_keyframe_pose(end_keyframe)

            if not start_pose or not end_pose:
                logger.warning("Could not get poses for keyframes")
                # Fall back to prompt-only generation

            # Generate ControlNet pose images
            start_pose_image = None
            end_pose_image = None

            if start_pose:
                start_pose_image = await self.pose_manager.generate_controlnet_image(
                    start_pose,
                    clip["width"],
                    clip["height"]
                )

            if end_pose:
                end_pose_image = await self.pose_manager.generate_controlnet_image(
                    end_pose,
                    clip["width"],
                    clip["height"]
                )

            # Calculate segment duration
            duration_ms = end_keyframe["time_ms"] - start_keyframe["time_ms"]
            num_frames = int((duration_ms / 1000) * clip["fps"])

            # Build prompt
            prompt = start_keyframe.get("prompt_override") or clip["base_prompt"]

            # Build workflow
            if use_framepack:
                workflow = self._build_framepack_workflow(
                    clip=clip,
                    prompt=prompt,
                    num_frames=num_frames,
                    start_pose_image=start_pose_image,
                    end_pose_image=end_pose_image,
                    segment_index=segment_index
                )
            else:
                workflow = self._build_animatediff_workflow(
                    clip=clip,
                    prompt=prompt,
                    num_frames=num_frames,
                    start_pose_image=start_pose_image,
                    segment_index=segment_index
                )

            # Submit to ComfyUI
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": workflow}
                )

                if response.status_code != 200:
                    logger.error(f"ComfyUI error: {response.status_code}")
                    return None

                result = response.json()
                prompt_id = result.get("prompt_id")

            # Wait for completion
            output_path = await self._wait_for_comfyui(prompt_id, timeout=300)
            return output_path

        except Exception as e:
            logger.error(f"Segment generation error: {e}")
            return None

    def _build_framepack_workflow(
        self,
        clip: Dict,
        prompt: str,
        num_frames: int,
        start_pose_image: Optional[str],
        end_pose_image: Optional[str],
        segment_index: int
    ) -> Dict:
        """Build FramePack workflow for segment generation."""
        import time
        seed = int(time.time() * 1000) % (2**32)

        workflow = {
            # Load FramePack model
            "1": {
                "class_type": "FramePackHYModelLoader",
                "inputs": {
                    "model": "diffusion_models/FramePackI2V_HY_fp8_e4m3fn.safetensors",
                    "precision": "fp8_e4m3fn"
                }
            },
            # VAE
            "2": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "hunyuan_video_vae_bf16.safetensors"}
            },
            # CLIP
            "3": {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": "clip_l.safetensors",
                    "clip_name2": "llava_llama3_fp16.safetensors",
                    "type": "hunyuan_video"
                }
            },
            # Positive prompt
            "5": {
                "class_type": "HYVideoCLIPTextEncode",
                "inputs": {
                    "clip": ["3", 0],
                    "prompt": prompt
                }
            },
            # Negative prompt
            "6": {
                "class_type": "HYVideoCLIPTextEncode",
                "inputs": {
                    "clip": ["3", 0],
                    "prompt": clip.get("negative_prompt", "low quality, blurry")
                }
            },
            # Sampler
            "10": {
                "class_type": "FramePackSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7.0,
                    "denoise": 1.0,
                    "num_frames": num_frames,
                    "width": clip["width"],
                    "height": clip["height"]
                }
            },
            # Decode
            "11": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["10", 0],
                    "vae": ["2", 0]
                }
            },
            # Save video
            "12": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["11", 0],
                    "frame_rate": clip["fps"],
                    "loop_count": 0,
                    "filename_prefix": f"keyframe_anim/clip_{clip['id']}_seg_{segment_index}",
                    "format": "video/h264-mp4",
                    "save_output": True
                }
            }
        }

        # Add ControlNet conditioning if pose images available
        if start_pose_image:
            workflow["20"] = {
                "class_type": "LoadImage",
                "inputs": {"image": start_pose_image}
            }
            workflow["21"] = {
                "class_type": "ControlNetLoader",
                "inputs": {"control_net_name": "control_v11p_sd15_openpose.pth"}
            }
            workflow["22"] = {
                "class_type": "ControlNetApply",
                "inputs": {
                    "conditioning": ["5", 0],
                    "control_net": ["21", 0],
                    "image": ["20", 0],
                    "strength": 0.8
                }
            }
            # Update sampler to use ControlNet conditioning
            workflow["10"]["inputs"]["positive"] = ["22", 0]

        return workflow

    def _build_animatediff_workflow(
        self,
        clip: Dict,
        prompt: str,
        num_frames: int,
        start_pose_image: Optional[str],
        segment_index: int
    ) -> Dict:
        """Build AnimateDiff workflow as fallback."""
        import time
        seed = int(time.time() * 1000) % (2**32)

        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "counterfeitV30_v30.safetensors"}
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": clip.get("negative_prompt", "low quality, blurry"),
                    "clip": ["4", 1]
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": clip["width"],
                    "height": clip["height"],
                    "batch_size": num_frames
                }
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["8", 0],
                    "frame_rate": clip["fps"],
                    "filename_prefix": f"keyframe_anim/clip_{clip['id']}_seg_{segment_index}",
                    "format": "video/h264-mp4"
                }
            }
        }

        return workflow

    async def _wait_for_comfyui(self, prompt_id: str, timeout: int = 300) -> Optional[str]:
        """Wait for ComfyUI generation to complete."""
        import httpx
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")

                    if response.status_code == 200:
                        history = response.json()

                        if prompt_id in history:
                            outputs = history[prompt_id].get("outputs", {})

                            for node_id, output in outputs.items():
                                if "gifs" in output:
                                    filename = output["gifs"][0]["filename"]
                                    subfolder = output["gifs"][0].get("subfolder", "")
                                    return str(self.output_dir.parent / subfolder / filename)

                                if "videos" in output:
                                    filename = output["videos"][0]["filename"]
                                    return str(self.output_dir / filename)

            except Exception as e:
                logger.warning(f"Error checking ComfyUI status: {e}")

            await asyncio.sleep(5)

        logger.error(f"Timeout waiting for ComfyUI prompt {prompt_id}")
        return None

    async def _get_keyframe_pose(self, keyframe: Dict) -> Optional[OpenPoseKeypoints]:
        """Get pose data for a keyframe."""
        if keyframe.get("pose_data"):
            return OpenPoseKeypoints.from_bytes(keyframe["pose_data"])

        if keyframe.get("pose_id"):
            pose = await self.pose_manager.get_pose(keyframe["pose_id"])
            if pose:
                return pose.keypoints

        return None

    # === Database Helpers ===

    async def _get_clip(self, clip_id: int) -> Optional[Dict]:
        """Get clip information."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM animation_clips WHERE id = $1", clip_id
            )

        if not row:
            return None

        return {
            "id": row["id"],
            "name": row["name"],
            "character_id": row["character_id"],
            "duration_ms": row["duration_ms"],
            "fps": row["fps"],
            "width": row["width"],
            "height": row["height"],
            "base_prompt": row["base_prompt"],
            "negative_prompt": row["negative_prompt"],
            "status": row["status"],
            "output_path": row["output_path"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
        }

    async def _get_clip_keyframes(self, clip_id: int) -> List[Dict]:
        """Get all keyframes for a clip."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM clip_keyframes
                WHERE clip_id = $1
                ORDER BY time_ms
            """, clip_id)

        return [
            {
                "id": row["id"],
                "time_ms": row["time_ms"],
                "pose_id": row["pose_id"],
                "pose_data": row["pose_data"],
                "motion_curve": row["motion_curve"],
                "hold_frames": row["hold_frames"],
                "prompt_override": row["prompt_override"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
            }
            for row in rows
        ]

    async def _update_clip_status(self, clip_id: int, status: str) -> None:
        """Update clip status."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE animation_clips SET status = $2, updated_at = NOW()
                WHERE id = $1
            """, clip_id, status)

    async def _update_clip_completed(
        self, clip_id: int, output_path: str, duration_ms: int
    ) -> None:
        """Mark clip as completed."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE animation_clips
                SET status = 'completed', output_path = $2, duration_ms = $3, updated_at = NOW()
                WHERE id = $1
            """, clip_id, output_path, duration_ms)


# === Factory function ===

async def create_keyframe_animator(database_url: str) -> KeyframeAnimator:
    """Create and initialize a KeyframeAnimator instance."""
    animator = KeyframeAnimator(database_url)
    await animator.connect()
    return animator
