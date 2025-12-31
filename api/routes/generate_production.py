"""
Production-ready generation endpoint with real ComfyUI integration
"""

import json
import uuid
import httpx
import asyncpg
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any
import logging
from .style_validator import validate_project_style

router = APIRouter()
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"
import os

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "anime_production"),
    "user": os.getenv("DB_USER", "patrick"),
    "password": os.getenv("DB_PASSWORD", "tower_echo_brain_secret_key_2025")
}

class GenerationRequest(BaseModel):
    """Request model for generation endpoint"""
    project: str = "Tokyo Debt Desire"
    character: Optional[str] = None
    prompt: str
    type: str = "image"  # image or video
    seed: Optional[int] = None
    lora_model: Optional[str] = None
    width: int = 512
    height: int = 768
    steps: int = 20
    cfg_scale: float = 7.0

async def get_models_from_ssot(project: str) -> Dict[str, Any]:
    """Get correct models from SSOT based on project"""
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        # Match project to profile
        profile = await conn.fetchrow("""
            SELECT gp.*,
                   cm.model_path as checkpoint,
                   lm.model_path as lora
            FROM generation_profiles gp
            LEFT JOIN ai_models cm ON gp.checkpoint_id = cm.id
            LEFT JOIN ai_models lm ON gp.lora_id = lm.id
            WHERE gp.name LIKE $1 OR gp.is_default = true
            ORDER BY (gp.name LIKE $1) DESC
            LIMIT 1
        """, f"%{project.lower()}%")

        if profile:
            return dict(profile)
    finally:
        await conn.close()

    # Fallback
    return {
        "checkpoint": "AOM3A1B.safetensors",
        "lora": None,
        "lora_strength": 0.8
    }

async def build_workflow_from_request(request: GenerationRequest) -> Dict[str, Any]:
    """Build ComfyUI workflow from request parameters"""

    # Use random seed if not provided
    seed = request.seed if request.seed else uuid.uuid4().int & 0xFFFFFFFF

    # Get models from SSOT
    models = await get_models_from_ssot(request.project)
    checkpoint = models["checkpoint"]
    lora = models.get("lora") or request.lora_model

    # Validate style compliance
    try:
        validate_project_style(request.project, checkpoint, lora)
    except ValueError as e:
        logger.error(f"Style validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    # Build prompt with character if specified
    full_prompt = request.prompt
    if request.character:
        full_prompt = f"{request.character}, {request.prompt}"

    # Add style prompt if exists
    if models.get("style_prompt"):
        full_prompt = f"{full_prompt}, {models['style_prompt']}"

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": checkpoint
            }
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": full_prompt,
                "clip": ["1", 1]
            }
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": models.get("negative_prompt", "worst quality, low quality, blurry"),
                "clip": ["1", 1]
            }
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": request.width,
                "height": request.height,
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
                "steps": request.steps,
                "cfg": request.cfg_scale,
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
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": f"{request.character or 'anime'}_{datetime.now().strftime('%H%M%S')}",
                "images": ["6", 0]
            }
        }
    }

    # Add LoRA if specified
    if lora:
        workflow["8"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora,
                "strength_model": models.get("lora_strength", 0.8),
                "strength_clip": models.get("lora_strength", 0.8),
                "model": ["1", 0],
                "clip": ["1", 1]
            }
        }
        # Update sampler to use LoRA model
        workflow["5"]["inputs"]["model"] = ["8", 0]
        workflow["2"]["inputs"]["clip"] = ["8", 1]
        workflow["3"]["inputs"]["clip"] = ["8", 1]

    return workflow

async def store_job_in_db(request: GenerationRequest, prompt_id: str, client_id: str) -> str:
    """Store generation job in database for tracking"""

    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        # Generate job ID
        job_id = str(uuid.uuid4())

        # Get project ID
        project_row = await conn.fetchrow(
            "SELECT id FROM projects WHERE name = $1",
            request.project
        )

        # Store in generation_jobs table
        await conn.execute("""
            INSERT INTO generation_jobs (
                id, project_name, job_type, status,
                comfyui_prompt_id, input_data, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
            uuid.UUID(job_id),
            request.project,
            request.type,
            "pending",
            prompt_id,
            json.dumps(request.dict()),
            datetime.utcnow()
        )

        logger.info(f"Stored job {job_id} with ComfyUI prompt {prompt_id}")
        return job_id

    except Exception as e:
        logger.error(f"Failed to store job in DB: {e}")
        return None
    finally:
        await conn.close()

@router.post("/api/anime/generate")
async def generate_content(request: GenerationRequest):
    """
    REAL generation endpoint with ComfyUI integration and job tracking
    """
    try:
        # Generate client ID for this session
        client_id = f"anime_{uuid.uuid4().hex[:8]}"

        # Build workflow from request
        workflow_json = await build_workflow_from_request(request)

        # Submit to ComfyUI
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={
                    "prompt": workflow_json,
                    "client_id": client_id
                },
                timeout=10.0
            )

            if response.status_code != 200:
                error_detail = response.json() if response.text else "Unknown error"
                logger.error(f"ComfyUI rejected workflow: {error_detail}")
                raise HTTPException(status_code=400, detail=f"ComfyUI error: {error_detail}")

            comfy_data = response.json()
            prompt_id = comfy_data.get("prompt_id")

        # Store job in database
        job_id = await store_job_in_db(request, prompt_id, client_id)

        if not job_id:
            logger.warning(f"Job submitted to ComfyUI but not tracked in DB: {prompt_id}")

        # Return trackable response
        return {
            "success": True,
            "message": "Generation job submitted",
            "job_id": job_id,
            "prompt_id": prompt_id,
            "client_id": client_id,
            "queue_status_url": f"/api/anime/jobs/{job_id}/status" if job_id else None,
            "timestamp": datetime.utcnow().isoformat()
        }

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to ComfyUI: {e}")
        raise HTTPException(status_code=503, detail="ComfyUI service unavailable")
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/anime/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get status of a generation job"""

    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        # Get job from database
        job = await conn.fetchrow("""
            SELECT id, project_name, job_type, status, comfyui_prompt_id,
                   output_data, error_message, created_at, updated_at
            FROM generation_jobs
            WHERE id = $1
        """, uuid.UUID(job_id))

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check ComfyUI queue for live status if pending/processing
        if job["status"] in ["pending", "processing"]:
            async with httpx.AsyncClient() as client:
                try:
                    # Check queue
                    queue_response = await client.get(f"{COMFYUI_URL}/queue")
                    queue_data = queue_response.json()

                    # Check if job is in queue
                    prompt_id = job["comfyui_prompt_id"]
                    is_running = any(
                        item[1] == prompt_id
                        for item in queue_data.get("queue_running", [])
                    )
                    is_pending = any(
                        item[1] == prompt_id
                        for item in queue_data.get("queue_pending", [])
                    )

                    # Update status based on queue
                    if is_running:
                        current_status = "processing"
                        await conn.execute("""
                            UPDATE generation_jobs
                            SET status = 'processing', updated_at = $1
                            WHERE id = $2 AND status = 'pending'
                        """, datetime.utcnow(), uuid.UUID(job_id))
                    elif is_pending:
                        current_status = "pending"
                    else:
                        # Not in queue, check history
                        history_response = await client.get(
                            f"{COMFYUI_URL}/history/{prompt_id}"
                        )
                        if history_response.status_code == 200:
                            history_data = history_response.json()
                            if prompt_id in history_data:
                                current_status = "completed"
                                # Get output info
                                outputs = history_data[prompt_id].get("outputs", {})
                                await conn.execute("""
                                    UPDATE generation_jobs
                                    SET status = 'completed',
                                        output_data = $1,
                                        updated_at = $2
                                    WHERE id = $3
                                """, json.dumps(outputs), datetime.utcnow(), uuid.UUID(job_id))
                        else:
                            current_status = job["status"]

                except Exception as e:
                    logger.error(f"Failed to check ComfyUI status: {e}")
                    current_status = job["status"]
        else:
            current_status = job["status"]

        return {
            "job_id": job_id,
            "project": job["project_name"],
            "type": job["job_type"],
            "status": current_status,
            "comfyui_prompt_id": job["comfyui_prompt_id"],
            "output": job["output_data"],
            "error": job["error_message"],
            "created_at": job["created_at"].isoformat() if job["created_at"] else None,
            "updated_at": job["updated_at"].isoformat() if job["updated_at"] else None
        }

    finally:
        await conn.close()

# Deprecation endpoint
@router.post("/api/anime/generate/real")
async def deprecated_endpoint():
    """Deprecated - use /api/anime/generate instead"""
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Please use POST /api/anime/generate instead."
    )