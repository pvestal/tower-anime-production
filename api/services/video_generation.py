"""
Video generation service for Tower Anime Production API
Handles AnimateDiff, RIFE, SVD workflows for anime video production
"""

import os
import time
import random
import logging
import asyncio
import aiohttp
import psycopg2
from typing import Optional, Dict, Any
from fastapi import HTTPException

from ..core.config import get_database_password, get_database_host, SystemConfig

logger = logging.getLogger(__name__)

# Configuration - Use domain-aware configuration
from ..core.config import COMFYUI_URL as DEFAULT_COMFYUI_URL
COMFYUI_URL = os.getenv('COMFYUI_URL', DEFAULT_COMFYUI_URL)


class VideoGenerationService:
    """Service for anime video generation using ComfyUI workflows"""

    def __init__(self):
        self.comfyui_url = COMFYUI_URL

    async def submit_comfyui_workflow(self, workflow_data: dict) -> Optional[str]:
        """Submit workflow to ComfyUI and return job ID"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.comfyui_url}/prompt", json=workflow_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("prompt_id")
                    else:
                        logger.error(f"ComfyUI submission failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"ComfyUI connection failed: {e}")
            return None

    async def generate_video_with_animatediff(
        self,
        prompt: str,
        checkpoint: Optional[str] = None,
        lora_name: Optional[str] = None,
        frame_count: int = 16,
        width: int = 512,
        height: int = 768
    ) -> Dict[str, Any]:
        """
        Generate anime video using AnimateDiff workflow from database SSOT
        """
        # Use database defaults if not specified
        if checkpoint is None:
            checkpoint = SystemConfig.get('default_checkpoint', 'realisticVision_v51.safetensors')

        # Load workflow from database SSOT
        try:
            conn = psycopg2.connect(
                host=get_database_host(),
                database='tower_consolidated',
                user='patrick',
                password=get_database_password()
            )

            with conn.cursor() as cur:
                # Get workflow from database - use the RIFE workflow for better quality
                cur.execute("""
                    SELECT workflow_template, frame_count
                    FROM video_workflow_templates
                    WHERE name = 'anime_30sec_rife_workflow'
                """)
                row = cur.fetchone()

                if not row:
                    raise ValueError("Workflow not found in database SSOT")

                workflow = row[0]  # JSONB returns dict directly
                frame_count = row[1]
                logger.info(f"Loaded workflow from database with {frame_count} frames")

            conn.close()

            # Update the prompts dynamically
            for node_id, node in workflow.items():
                if isinstance(node, dict):
                    # Update positive prompt - REPLACE the entire text, not append
                    if node.get("class_type") == "CLIPTextEncode" and "Positive" in str(node.get("_meta", {}).get("title", "")):
                        old_prompt = workflow[node_id]["inputs"]["text"]
                        # Complete replacement to avoid any leftover character names
                        workflow[node_id]["inputs"]["text"] = f"{prompt}, masterpiece, best quality"
                        logger.info(f"Updated prompt from '{old_prompt}' to '{workflow[node_id]['inputs']['text']}'")

                    # Update checkpoint if different
                    if node.get("class_type") == "CheckpointLoaderSimple":
                        workflow[node_id]["inputs"]["ckpt_name"] = checkpoint

                    # Update LoRA if specified (for video workflows that have LoraLoader)
                    if node.get("class_type") == "LoraLoader" and lora_name:
                        workflow[node_id]["inputs"]["lora_name"] = lora_name
                        logger.info(f"Updated LoRA to '{lora_name}'")
                    elif node.get("class_type") == "LoraLoader" and not lora_name:
                        # Remove LoRA node if no LoRA specified
                        logger.info("No LoRA specified, using base model only")

            # Generate unique filename - find the VHS_VideoCombine node
            timestamp = int(time.time())
            for node_id, node in workflow.items():
                if isinstance(node, dict) and node.get("class_type") == "VHS_VideoCombine":
                    workflow[node_id]["inputs"]["filename_prefix"] = f"anime_video_{timestamp}"
                    logger.info(f"Updated video output node {node_id} with timestamp {timestamp}")
                    break

            async with aiohttp.ClientSession() as session:
                # Submit to ComfyUI
                async with session.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow}) as response:
                    if response.status == 200:
                        result = await response.json()
                        output_path = f"/mnt/1TB-storage/ComfyUI/output/anime_video_{timestamp}_00001_.mp4"
                        return {
                            "prompt_id": result.get("prompt_id"),
                            "output_path": output_path,
                            "workflow_used": "FIXED_anime_video_workflow"
                        }
                    else:
                        error_text = await response.text()
                        raise HTTPException(status_code=500, detail=f"ComfyUI error: {response.status}")

        except Exception as e:
            logger.error(f"AnimateDiff workflow error: {e}")
            raise HTTPException(status_code=500, detail=f"AnimateDiff generation failed: {str(e)}")

    async def generate_image_with_comfyui(
        self,
        prompt: str,
        checkpoint: Optional[str] = None,
        lora_name: Optional[str] = None,
        width: int = 512,
        height: int = 768,
        steps: int = 20,
        cfg: float = 7.5
    ) -> Dict[str, Any]:
        """
        Generate single image using ComfyUI text2img workflow
        """
        if checkpoint is None:
            checkpoint = SystemConfig.get('default_checkpoint', 'realisticVision_v51.safetensors')

        workflow = {
            "3": {
                "inputs": {
                    "seed": random.randint(0, 1000000),
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {
                "inputs": {"ckpt_name": checkpoint},
                "class_type": "CheckpointLoaderSimple"
            },
            "5": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "text": f"{prompt}, masterpiece, best quality",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "7": {
                "inputs": {
                    "text": "nsfw, nude, naked, worst quality, low quality, blurry",
                    "clip": ["4", 1]
                },
                "class_type": "CLIPTextEncode"
            },
            "8": {
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                },
                "class_type": "VAEDecode"
            },
            "9": {
                "inputs": {
                    "filename_prefix": f"anime_image_{int(time.time())}",
                    "images": ["8", 0]
                },
                "class_type": "SaveImage"
            }
        }

        # Add LoRA if specified
        if lora_name:
            workflow["10"] = {
                "inputs": {
                    "lora_name": lora_name,
                    "strength_model": 0.8,
                    "strength_clip": 0.8,
                    "model": ["4", 0],
                    "clip": ["4", 1]
                },
                "class_type": "LoraLoader"
            }
            # Update references to use LoRA output
            workflow["3"]["inputs"]["model"] = ["10", 0]
            workflow["6"]["inputs"]["clip"] = ["10", 1]
            workflow["7"]["inputs"]["clip"] = ["10", 1]

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow}) as response:
                if response.status == 200:
                    result = await response.json()
                    timestamp = int(time.time())
                    return {
                        "prompt_id": result.get("prompt_id"),
                        "output_path": f"/mnt/1TB-storage/ComfyUI/output/anime_image_{timestamp}_00001.png",
                        "workflow_used": "simple_text2img"
                    }
                else:
                    raise HTTPException(status_code=500, detail=f"ComfyUI error: {response.status}")

    async def get_generation_progress(self, request_id: str) -> float:
        """Get real progress from ComfyUI queue system"""
        try:
            async with aiohttp.ClientSession() as session:
                # Check ComfyUI queue
                async with session.get(f"{self.comfyui_url}/queue") as response:
                    if response.status == 200:
                        queue_data = await response.json()

                        # Check if request_id is in running jobs
                        running = queue_data.get("queue_running", [])
                        pending = queue_data.get("queue_pending", [])

                        for job in running:
                            if request_id in str(job):
                                return 0.5  # Currently processing

                        for job in pending:
                            if request_id in str(job):
                                return 0.1  # Queued

                        # Check history for completion
                        async with session.get(f"{self.comfyui_url}/history") as hist_response:
                            if hist_response.status == 200:
                                history = await hist_response.json()
                                if request_id in history:
                                    return 1.0  # Completed

                        return 0.0  # Not found

        except Exception as e:
            logger.error(f"Error getting ComfyUI progress: {e}")
            return 0.0

    async def cancel_generation(self, request_id: str) -> bool:
        """Cancel a running generation"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.comfyui_url}/interrupt") as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error canceling generation: {e}")
            return False


async def generate_video_with_music_sync(generation_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate video synchronized with music timing and BPM"""
    try:
        service = video_generation_service

        # Extract music sync parameters
        project_id = generation_config["project_id"]
        bpm = generation_config["bpm"]
        frames_per_beat = generation_config["frames_per_beat"]
        fps = generation_config.get("fps", 24)
        sync_mode = generation_config.get("sync_mode", "auto")

        # Calculate timing parameters for music synchronization
        beats_per_second = bpm / 60

        # Generate scene prompt based on project
        # This would normally fetch from the database
        scene_prompt = f"anime scene, space adventure, {sync_mode} synchronized animation, dynamic movement"

        # Modify AnimateDiff parameters for music sync
        # Key insight: frame count should align with musical phrases
        if sync_mode == "beat_sync":
            # Sync to every beat
            frame_count = int(frames_per_beat * 8)  # 8 beats = 2 musical bars
        elif sync_mode == "auto":
            # Sync to musical phrases (typically 4 beats)
            frame_count = int(frames_per_beat * 4)
        else:
            # Manual mode - use standard 5 second duration
            frame_count = fps * 5

        # Ensure frame count is reasonable for AnimateDiff
        frame_count = max(24, min(frame_count, 120))

        # Calculate context overlap for smooth music sync
        context_overlap = max(4, int(frames_per_beat / 2))

        # Enhanced prompt for music synchronization
        enhanced_prompt = f"{scene_prompt}, rhythmic motion at {bpm} BPM, synchronized animation"

        # Generate the video with music-aware parameters
        job_id = await service.generate_video_with_animatediff(
            prompt=enhanced_prompt,
            frame_count=frame_count,
            context_overlap=context_overlap,
            fps=fps,
            # Additional parameters for better music sync
            guidance_scale=7.5,  # More controlled generation
            motion_scale=1.2,    # Enhanced motion for beat sync
        )

        if job_id:
            # Store music sync metadata in database
            try:
                # This would update the generation record with music sync info
                logger.info(f"Music-synced video generation started: {job_id}")
                logger.info(f"BPM: {bpm}, Frames per beat: {frames_per_beat}, Total frames: {frame_count}")

                return {
                    "job_id": job_id,
                    "status": "started",
                    "music_sync_config": {
                        "bpm": bpm,
                        "frames_per_beat": frames_per_beat,
                        "frame_count": frame_count,
                        "fps": fps,
                        "sync_mode": sync_mode
                    }
                }
            except Exception as db_error:
                logger.warning(f"Failed to store music sync metadata: {db_error}")
                # Still return success since generation started
                return {"job_id": job_id, "status": "started"}
        else:
            raise HTTPException(status_code=500, detail="Failed to start music-synced generation")

    except Exception as e:
        logger.error(f"Music sync generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Global service instance
video_generation_service = VideoGenerationService()