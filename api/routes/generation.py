"""Generation routes for image and video creation"""

import uuid
import time
import logging
import os
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from typing import Optional

class GenerateRequest(BaseModel):
    prompt: str
    type: str = "image"
    model: str = "AOM3A1B"
    negative_prompt: str = ""
    seed: Optional[int] = None
    width: int = 512
    height: int = 768
    steps: int = 20
    cfg_scale: float = 7.0
    batch_size: int = 1
    project_id: Optional[str] = None
    duration: Optional[int] = 2  # For video generation

class MusicVideoRequest(BaseModel):
    prompt: str
    music_url: Optional[str] = None
    duration: int = 2
from services.gpu_service import ensure_vram_available
from services.comfyui_service import submit_to_comfyui
from job_tracker_fixed import job_tracker
from auth_middleware import optional_auth

logger = logging.getLogger(__name__)
router = APIRouter()

# Track active generation
active_generation = None


@router.post("/api/anime/generate")
async def generate_image(
    request: GenerateRequest,
    user=Depends(optional_auth)
):
    """Generate anime images with optional authentication"""
    global active_generation

    # Check if another generation is in progress
    if active_generation:
        raise HTTPException(
            status_code=429,
            detail=f"Generation already in progress: {active_generation}"
        )

    # Check VRAM availability
    if not ensure_vram_available(4000):
        raise HTTPException(
            status_code=503,
            detail="Insufficient GPU memory available"
        )

    job_id = str(uuid.uuid4())
    active_generation = job_id

    try:
        # Create job in database
        job_data = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "model": request.model,
            "width": request.width,
            "height": request.height,
            "steps": request.steps,
            "cfg_scale": request.cfg_scale,
            "seed": request.seed,
            "batch_size": request.batch_size,
            "project_id": request.project_id
        }

        # Create job using the correct method for video jobs
        if request.type == "video":
            job_tracker.create_video_job(job_data)
        else:
            # For images, use simple tracking
            job_tracker.update_job(job_id, {"status": "processing", **job_data})

        # Submit to ComfyUI with proper job type
        if request.type == "video":
            # Use proper video workflow
            result = await submit_to_comfyui(
                prompt=request.prompt,
                job_id=job_id,
                job_type="video"
            )
        else:
            # Use image workflow
            result = await submit_to_comfyui(
                prompt=request.prompt,
                job_id=job_id,
                job_type="image"
            )
        success = result.get("success", False)

        if success:
            prompt_id = result.get("prompt_id")

            # Wait for completion (max 180 seconds for video)
            import asyncio
            import httpx

            for i in range(180):
                await asyncio.sleep(1)
                async with httpx.AsyncClient() as client:
                    history_resp = await client.get(f"http://localhost:8188/history/{prompt_id}")
                    if history_resp.status_code == 200:
                        history = history_resp.json()
                        if prompt_id in history:
                            job_history = history[prompt_id]
                            if job_history.get("outputs"):
                                # Find the output image
                                for node_id, node_output in job_history["outputs"].items():
                                    # Check for image output
                                    if "images" in node_output:
                                        images = node_output["images"]
                                        if images:
                                            # For video, convert frames to MP4
                                            if request.type == "video":
                                                prefix = result.get("prefix")
                                                if prefix:
                                                    from services.video_converter import convert_frames_to_video
                                                    video_path = convert_frames_to_video(prefix, 8)
                                                    if video_path:
                                                        return {
                                                            "job_id": job_id,
                                                            "status": "completed",
                                                            "output_path": video_path,
                                                            "filename": os.path.basename(video_path),
                                                            "type": "video",
                                                            "format": "mp4",
                                                            "frames": len(images),
                                                            "prompt": request.prompt,
                                                            "generation_time": f"{i+1} seconds"
                                                        }

                                            # For image, return as is
                                            filename = images[0]["filename"]
                                            output_path = f"/home/patrick/ComfyUI/output/{filename}"
                                            return {
                                                "job_id": job_id,
                                                "status": "completed",
                                                "output_path": output_path,
                                                "filename": filename,
                                                "type": request.type,
                                                "prompt": request.prompt,
                                                "generation_time": f"{i+1} seconds"
                                            }

            # Timeout after 30 seconds
            return {
                "job_id": job_id,
                "status": "timeout",
                "message": "Generation taking longer than expected",
                "prompt_id": prompt_id
            }
        else:
            job_tracker.update_job(job_id, {"status": "failed"})
            raise HTTPException(
                status_code=500,
                detail="Failed to start generation"
            )

    finally:
        active_generation = None


@router.post("/api/anime/generate/video")
async def generate_video(
    prompt: str,
    duration: int = 2,
    user=Depends(optional_auth)
):
    """Generate anime video from prompt"""

    # Check VRAM (video needs more)
    if not ensure_vram_available(6000):
        raise HTTPException(
            status_code=503,
            detail="Insufficient GPU memory for video generation"
        )

    job_id = str(uuid.uuid4())

    try:
        # Create job
        job_data = {
            "type": "video",
            "prompt": prompt,
            "duration": duration,
            "frames": duration * 8  # 8 fps
        }

        # Create job using the correct method for video jobs
        if request.type == "video":
            job_tracker.create_video_job(job_data)
        else:
            # For images, use simple tracking
            job_tracker.update_job(job_id, {"status": "processing", **job_data})

        # TODO: Implement actual video generation workflow
        # For now, return job created response

        return {
            "job_id": job_id,
            "status": "processing",
            "type": "video",
            "duration": duration,
            "message": "Video generation started",
            "created_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        job_tracker.update_job_status(job_id, "failed")
        raise HTTPException(
            status_code=500,
            detail=f"Video generation failed: {str(e)}"
        )


@router.post("/api/anime/generate-with-music")
async def generate_with_music(
    request: MusicVideoRequest,
    user=Depends(optional_auth)
):
    """Generate video with synchronized music"""

    job_id = str(uuid.uuid4())

    try:
        # Create job
        job_data = {
            "type": "music_video",
            "video_prompt": request.video_prompt,
            "music_genre": request.music_genre,
            "duration": request.video_duration,
            "style": request.style,
            "bpm": request.bpm
        }

        job_tracker.create_job(job_id, job_data)

        return {
            "job_id": job_id,
            "status": "processing",
            "type": "music_video",
            "message": "Music video generation started",
            "created_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Music video generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Music video generation failed: {str(e)}"
        )