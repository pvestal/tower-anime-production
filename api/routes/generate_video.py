"""
Video generation endpoint with SVD workflow
"""

import json
import uuid
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

class VideoGenerationRequest(BaseModel):
    """Request model for video generation"""
    character: str = "Mei"
    prompt: str
    frames: int = 25
    fps: int = 8
    motion_bucket: int = 80
    augmentation: float = 0.02
    seed: Optional[int] = None

@router.post("/api/anime/generate/video")
async def generate_video(request: VideoGenerationRequest):
    """Generate video using SVD workflow"""

    try:
        client_id = f"video_{uuid.uuid4().hex[:8]}"
        seed = request.seed if request.seed else uuid.uuid4().int & 0xFFFFFFFF

        # Build SVD workflow
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "AOM3A1B.safetensors"
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{request.character}, {request.prompt}, masterpiece",
                    "clip": ["1", 1]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": "worst quality, low quality",
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": 512,
                    "height": 512,
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                    "seed": seed,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                }
            },
            "7": {
                "class_type": "ImageOnlyCheckpointLoader",
                "inputs": {
                    "ckpt_name": "svd_xt.safetensors"
                }
            },
            "8": {
                "class_type": "SVD_img2vid_Conditioning",
                "inputs": {
                    "clip_vision": ["7", 1],
                    "init_image": ["6", 0],
                    "vae": ["7", 2],
                    "width": 512,
                    "height": 512,
                    "video_frames": request.frames,
                    "motion_bucket_id": request.motion_bucket,
                    "fps": request.fps,
                    "augmentation_level": request.augmentation
                }
            },
            "9": {
                "class_type": "KSamplerAdvanced",
                "inputs": {
                    "model": ["7", 0],
                    "positive": ["8", 0],
                    "negative": ["8", 1],
                    "latent_image": ["8", 2],
                    "seed": seed,
                    "steps": 25,
                    "cfg": 2.5,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "add_noise": "enable",
                    "noise_seed": seed,
                    "start_at_step": 0,
                    "end_at_step": 25,
                    "return_with_leftover_noise": "disable"
                }
            },
            "10": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["9", 0],
                    "vae": ["7", 2]
                }
            },
            "11": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["10", 0],
                    "frame_rate": request.fps,
                    "loop_count": 0,
                    "filename_prefix": f"VIDEO_{request.character}_{datetime.now().strftime('%H%M%S')}",
                    "format": "video/h264-mp4",
                    "save_output": True,
                    "pingpong": False
                }
            }
        }

        # Submit to ComfyUI
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={
                    "prompt": workflow,
                    "client_id": client_id
                },
                timeout=10.0
            )

            if response.status_code != 200:
                error_detail = response.json() if response.text else "Unknown error"
                logger.error(f"ComfyUI rejected video workflow: {error_detail}")
                raise HTTPException(status_code=400, detail=f"ComfyUI error: {error_detail}")

            comfy_data = response.json()
            prompt_id = comfy_data.get("prompt_id")

        return {
            "success": True,
            "message": "Video generation submitted",
            "prompt_id": prompt_id,
            "client_id": client_id,
            "workflow_type": "SVD",
            "frames": request.frames,
            "fps": request.fps,
            "timestamp": datetime.utcnow().isoformat()
        }

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to ComfyUI: {e}")
        raise HTTPException(status_code=503, detail="ComfyUI service unavailable")
    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))