#!/usr/bin/env python3
"""
Episode Producer - Long-form Video Generation
Generates full episodes by stitching together scene segments with transitions.

Architecture:
1. Episode -> Scenes -> Segments
2. Each segment is 5-30 seconds of video
3. Segments are stitched with transitions (crossfade, cut, wipe)
4. Audio track is overlaid at the end
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class TransitionType(str, Enum):
    CUT = "cut"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"
    WIPE_LEFT = "wipe_left"
    WIPE_RIGHT = "wipe_right"


class SegmentStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VideoSegment:
    """Single video segment (5-30 seconds)"""
    id: str
    scene_id: str
    prompt: str
    duration: int = 5  # seconds
    status: SegmentStatus = SegmentStatus.PENDING
    output_path: Optional[str] = None
    character_ids: List[str] = field(default_factory=list)
    motion_prompt: Optional[str] = None
    seed: int = -1
    error: Optional[str] = None
    progress: float = 0.0


@dataclass
class Scene:
    """A scene contains multiple segments with the same setting/characters"""
    id: str
    episode_id: str
    name: str
    description: str
    segments: List[VideoSegment] = field(default_factory=list)
    transition_in: TransitionType = TransitionType.CUT
    transition_out: TransitionType = TransitionType.CUT
    transition_duration: float = 0.5  # seconds
    background_music: Optional[str] = None
    order: int = 0


@dataclass
class Episode:
    """Full episode with multiple scenes"""
    id: str
    project_id: str
    title: str
    description: str
    scenes: List[Scene] = field(default_factory=list)
    target_duration: int = 300  # 5 minutes default
    status: str = "draft"
    output_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class EpisodeConfig:
    """Configuration for episode generation"""
    segment_duration: int = 30  # seconds per segment
    fps: int = 24
    width: int = 1024
    height: int = 576
    use_interpolation: bool = True  # RIFE 6x interpolation
    parallel_segments: int = 2  # Generate multiple segments in parallel
    output_format: str = "mp4"
    codec: str = "h264"


class EpisodeProducer:
    """
    Produces full episodes by orchestrating scene/segment generation.

    Workflow:
    1. Break episode into scenes
    2. Break scenes into segments (based on segment_duration)
    3. Generate segments in parallel batches
    4. Stitch segments within each scene
    5. Stitch scenes together with transitions
    6. Add audio track
    """

    def __init__(
        self,
        comfyui_host: str = "localhost",
        comfyui_port: int = 8188,
        output_dir: str = "/mnt/1TB-storage/anime-output/episodes"
    ):
        self.comfyui_url = f"http://{comfyui_host}:{comfyui_port}"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client_id = str(uuid.uuid4())

    async def produce_episode(
        self,
        episode: Episode,
        config: EpisodeConfig = None,
        progress_callback=None
    ) -> Dict:
        """
        Produce a full episode from scene definitions.

        Args:
            episode: Episode with scenes and segments defined
            config: Generation configuration
            progress_callback: Async callback(progress_percent, message)

        Returns:
            Result dict with output_path and metrics
        """
        if config is None:
            config = EpisodeConfig()

        episode.status = "generating"
        total_segments = sum(len(scene.segments) for scene in episode.scenes)
        completed_segments = 0

        try:
            scene_outputs = []

            for scene_idx, scene in enumerate(episode.scenes):
                if progress_callback:
                    await progress_callback(
                        (completed_segments / total_segments) * 100,
                        f"Generating scene {scene_idx + 1}/{len(episode.scenes)}: {scene.name}"
                    )

                # Generate segments for this scene
                segment_outputs = await self._generate_scene_segments(
                    scene, config, progress_callback
                )

                # Stitch segments into scene
                scene_path = await self._stitch_segments(
                    segment_outputs,
                    scene,
                    config,
                    episode.id
                )

                scene_outputs.append({
                    "scene_id": scene.id,
                    "path": scene_path,
                    "transition_in": scene.transition_in,
                    "transition_out": scene.transition_out,
                    "transition_duration": scene.transition_duration
                })

                completed_segments += len(scene.segments)

            # Stitch all scenes together
            if progress_callback:
                await progress_callback(95, "Stitching scenes together...")

            final_output = await self._stitch_scenes(
                scene_outputs,
                episode,
                config
            )

            episode.status = "completed"
            episode.output_path = str(final_output)

            return {
                "success": True,
                "episode_id": episode.id,
                "output_path": str(final_output),
                "total_segments": total_segments,
                "scenes_count": len(episode.scenes),
                "duration_seconds": self._calculate_duration(episode)
            }

        except Exception as e:
            logger.error(f"Episode production failed: {e}")
            episode.status = "failed"
            return {
                "success": False,
                "episode_id": episode.id,
                "error": str(e)
            }

    async def _generate_scene_segments(
        self,
        scene: Scene,
        config: EpisodeConfig,
        progress_callback=None
    ) -> List[str]:
        """Generate all segments for a scene in parallel batches."""
        segment_outputs = []

        # Process segments in batches
        for i in range(0, len(scene.segments), config.parallel_segments):
            batch = scene.segments[i:i + config.parallel_segments]

            # Generate batch in parallel
            tasks = [
                self._generate_segment(segment, config)
                for segment in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for segment, result in zip(batch, results):
                if isinstance(result, Exception):
                    segment.status = SegmentStatus.FAILED
                    segment.error = str(result)
                    logger.error(f"Segment {segment.id} failed: {result}")
                else:
                    segment.status = SegmentStatus.COMPLETED
                    segment.output_path = result
                    segment_outputs.append(result)

        return segment_outputs

    async def _generate_segment(
        self,
        segment: VideoSegment,
        config: EpisodeConfig
    ) -> str:
        """Generate a single video segment using ComfyUI."""
        segment.status = SegmentStatus.GENERATING

        workflow = self._create_segment_workflow(segment, config)

        async with httpx.AsyncClient(timeout=600) as client:
            # Submit to ComfyUI
            response = await client.post(
                f"{self.comfyui_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id}
            )

            if response.status_code != 200:
                raise Exception(f"ComfyUI error: {response.text}")

            prompt_id = response.json()["prompt_id"]

            # Wait for completion
            output_path = await self._wait_for_segment(client, prompt_id)

            return output_path

    def _create_segment_workflow(
        self,
        segment: VideoSegment,
        config: EpisodeConfig
    ) -> Dict:
        """Create ComfyUI workflow for video segment generation."""
        import random

        seed = segment.seed if segment.seed > 0 else random.randint(0, 2**32 - 1)

        # Base frames (before interpolation)
        base_frames = (segment.duration * config.fps) // 6 if config.use_interpolation else segment.duration * config.fps

        workflow = {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": segment.prompt,
                    "clip": ["4", 0]
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "worst quality, low quality, blurry, static, text, watermark",
                    "clip": ["4", 0]
                }
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7.5,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["5", 0],
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "latent_image": ["6", 0]
                }
            },
            "4": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "clip_l.safetensors"
                }
            },
            "5": {
                "class_type": "AnimateDiffLoaderWithContext",
                "inputs": {
                    "model_name": "v3_sd15_mm.ckpt",
                    "beta_schedule": "sqrt_linear",
                    "motion_scale": 1.0,
                    "apply_v2_models_properly": True
                }
            },
            "6": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": config.width,
                    "height": config.height,
                    "batch_size": min(base_frames, 120)
                }
            },
            "7": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["8", 0]
                }
            },
            "8": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "vae-ft-mse-840000-ema-pruned.safetensors"
                }
            }
        }

        # Add RIFE interpolation if enabled
        if config.use_interpolation:
            workflow["9"] = {
                "class_type": "RIFE VFI",
                "inputs": {
                    "frames": ["7", 0],
                    "multiplier": 6,
                    "model_name": "rife4.6.pkl"
                }
            }
            workflow["10"] = {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "frame_rate": config.fps,
                    "loop_count": 0,
                    "filename_prefix": f"segment_{segment.id}",
                    "format": "video/h264-mp4",
                    "images": ["9", 0]
                }
            }
        else:
            workflow["10"] = {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "frame_rate": config.fps,
                    "loop_count": 0,
                    "filename_prefix": f"segment_{segment.id}",
                    "format": "video/h264-mp4",
                    "images": ["7", 0]
                }
            }

        return workflow

    async def _wait_for_segment(
        self,
        client: httpx.AsyncClient,
        prompt_id: str,
        timeout: int = 600
    ) -> str:
        """Wait for segment generation to complete."""
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = await client.get(f"{self.comfyui_url}/history/{prompt_id}")

                if response.status_code == 200:
                    data = response.json()
                    if prompt_id in data and data[prompt_id].get("outputs"):
                        for output in data[prompt_id]["outputs"].values():
                            if "gifs" in output:
                                return output["gifs"][0]["filename"]
                            if "videos" in output:
                                return output["videos"][0]["filename"]

                await asyncio.sleep(2)

            except Exception as e:
                logger.warning(f"Error checking status: {e}")
                await asyncio.sleep(2)

        raise TimeoutError(f"Segment generation timed out after {timeout}s")

    async def _stitch_segments(
        self,
        segment_paths: List[str],
        scene: Scene,
        config: EpisodeConfig,
        episode_id: str
    ) -> str:
        """Stitch video segments together using ffmpeg."""
        if not segment_paths:
            raise ValueError("No segments to stitch")

        if len(segment_paths) == 1:
            return segment_paths[0]

        # Create concat file
        output_path = self.output_dir / f"scene_{scene.id}_{episode_id}.{config.output_format}"
        concat_file = self.output_dir / f"concat_{scene.id}.txt"

        with open(concat_file, "w") as f:
            for path in segment_paths:
                f.write(f"file '{path}'\n")

        # Use ffmpeg to concatenate
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", config.codec,
            "-preset", "fast",
            str(output_path)
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg failed: {stderr.decode()}")

        # Cleanup concat file
        concat_file.unlink(missing_ok=True)

        return str(output_path)

    async def _stitch_scenes(
        self,
        scene_outputs: List[Dict],
        episode: Episode,
        config: EpisodeConfig
    ) -> Path:
        """Stitch all scenes together with transitions."""
        output_path = self.output_dir / f"episode_{episode.id}.{config.output_format}"

        if len(scene_outputs) == 1:
            # Just copy/rename the single scene
            import shutil
            shutil.copy(scene_outputs[0]["path"], output_path)
            return output_path

        # Build ffmpeg filter for transitions
        filter_complex = self._build_transition_filter(scene_outputs, config)

        # Input files
        inputs = []
        for scene in scene_outputs:
            inputs.extend(["-i", scene["path"]])

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", config.codec,
            "-preset", "fast",
            str(output_path)
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            # Fallback to simple concat if transitions fail
            logger.warning(f"Transition filter failed, using simple concat: {stderr.decode()[:200]}")
            return await self._simple_concat_scenes(scene_outputs, episode, config)

        return output_path

    def _build_transition_filter(
        self,
        scene_outputs: List[Dict],
        config: EpisodeConfig
    ) -> str:
        """Build ffmpeg filter_complex for scene transitions."""
        # Simple crossfade between all scenes
        filter_parts = []
        n = len(scene_outputs)

        for i in range(n):
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

        # Chain crossfades
        if n == 2:
            filter_parts.append(
                f"[v0][v1]xfade=transition=fade:duration=0.5:offset=4[outv]"
            )
        else:
            # Multi-scene crossfade chain
            prev = "v0"
            for i in range(1, n):
                next_label = f"xf{i}" if i < n - 1 else "outv"
                filter_parts.append(
                    f"[{prev}][v{i}]xfade=transition=fade:duration=0.5:offset=4[{next_label}]"
                )
                prev = next_label

        return ";".join(filter_parts)

    async def _simple_concat_scenes(
        self,
        scene_outputs: List[Dict],
        episode: Episode,
        config: EpisodeConfig
    ) -> Path:
        """Simple concatenation without transitions."""
        output_path = self.output_dir / f"episode_{episode.id}.{config.output_format}"
        concat_file = self.output_dir / f"concat_episode_{episode.id}.txt"

        with open(concat_file, "w") as f:
            for scene in scene_outputs:
                f.write(f"file '{scene['path']}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", config.codec,
            "-preset", "fast",
            str(output_path)
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()
        concat_file.unlink(missing_ok=True)

        return output_path

    def _calculate_duration(self, episode: Episode) -> int:
        """Calculate total episode duration in seconds."""
        total = 0
        for scene in episode.scenes:
            for segment in scene.segments:
                total += segment.duration
            # Add transition time
            total += scene.transition_duration
        return total


# Convenience functions for API integration
def create_episode_from_script(
    project_id: str,
    title: str,
    scene_descriptions: List[Dict]
) -> Episode:
    """
    Create an episode structure from a list of scene descriptions.

    Args:
        project_id: Project this episode belongs to
        title: Episode title
        scene_descriptions: List of dicts with 'name', 'description', 'prompts'

    Returns:
        Episode ready for production
    """
    episode = Episode(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title=title,
        description=f"Episode: {title}",
        scenes=[]
    )

    for idx, scene_desc in enumerate(scene_descriptions):
        scene = Scene(
            id=str(uuid.uuid4()),
            episode_id=episode.id,
            name=scene_desc.get("name", f"Scene {idx + 1}"),
            description=scene_desc.get("description", ""),
            order=idx
        )

        # Create segments from prompts
        prompts = scene_desc.get("prompts", [scene_desc.get("description", "")])
        for prompt_idx, prompt in enumerate(prompts):
            segment = VideoSegment(
                id=str(uuid.uuid4()),
                scene_id=scene.id,
                prompt=prompt,
                duration=scene_desc.get("segment_duration", 30)
            )
            scene.segments.append(segment)

        episode.scenes.append(scene)

    return episode


async def quick_episode(
    prompts: List[str],
    project_id: str = "default",
    title: str = "Quick Episode",
    segment_duration: int = 30
) -> Dict:
    """
    Quick way to generate an episode from a list of prompts.

    Each prompt becomes one segment.
    """
    scene_descriptions = [
        {"name": f"Scene {i+1}", "prompts": [prompt], "segment_duration": segment_duration}
        for i, prompt in enumerate(prompts)
    ]

    episode = create_episode_from_script(project_id, title, scene_descriptions)

    producer = EpisodeProducer()
    result = await producer.produce_episode(episode)

    return result
