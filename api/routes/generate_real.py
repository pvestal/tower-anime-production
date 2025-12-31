"""
Real generation endpoint that actually submits to ComfyUI
"""

import json
import uuid
import httpx
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime
import logging
import asyncpg

router = APIRouter()
logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

import os

async def get_project_models(project_name: str):
    """Get the correct models from SSOT database"""
    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "anime_production"),
        user=os.getenv("DB_USER", "patrick"),
        password=os.getenv("DB_PASSWORD", "tower_echo_brain_secret_key_2025")
    )

    try:
        # Get profile for this project
        profile = await conn.fetchrow("""
            SELECT gp.*,
                   cm.model_path as checkpoint_path,
                   lm.model_path as lora_path
            FROM generation_profiles gp
            LEFT JOIN ai_models cm ON gp.checkpoint_id = cm.id
            LEFT JOIN ai_models lm ON gp.lora_id = lm.id
            WHERE gp.name LIKE $1 OR gp.is_default = true
            ORDER BY (gp.name LIKE $1) DESC
            LIMIT 1
        """, f"%{project_name}%")

        if profile:
            return {
                "checkpoint": profile["checkpoint_path"] or "AOM3A1B.safetensors",
                "lora": profile["lora_path"] or "mei_working_v1.safetensors",
                "lora_strength": profile["lora_strength"] or 0.8,
                "negative_prompt": profile["negative_prompt"],
                "style_prompt": profile["style_prompt"],
                "width": profile["width"],
                "height": profile["height"],
                "steps": profile["steps"],
                "cfg_scale": profile["cfg_scale"]
            }
    finally:
        await conn.close()

    # Fallback defaults
    return {
        "checkpoint": "AOM3A1B.safetensors",
        "lora": "mei_working_v1.safetensors",
        "lora_strength": 0.8,
        "negative_prompt": "worst quality, low quality",
        "style_prompt": "",
        "width": 512,
        "height": 768,
        "steps": 20,
        "cfg_scale": 7.0
    }

@router.post("/api/anime/generate/real")
async def generate_real(request: Request):
    """Actually generate content using ComfyUI"""
    try:
        data = await request.json()
        project = data.get("project", "default")

        # Get models from SSOT
        models = await get_project_models(project)

        # Generate unique client ID
        client_id = f"anime_{uuid.uuid4().hex[:8]}"

        # Build prompt with style additions
        base_prompt = data.get("prompt", "anime girl, masterpiece")
        if models["style_prompt"]:
            full_prompt = f"{base_prompt}, {models['style_prompt']}"
        else:
            full_prompt = base_prompt

        # Create workflow with SSOT models
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": models["checkpoint"]
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
                    "text": models["negative_prompt"],
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": models["width"],
                    "height": models["height"],
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
                    "seed": data.get("seed", 123456),
                    "steps": models["steps"],
                    "cfg": models["cfg_scale"],
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
                    "filename_prefix": f"REAL_TEST_{datetime.now().strftime('%H%M%S')}",
                    "images": ["6", 0]
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
                }
            )

            if response.status_code == 200:
                result = response.json()
                prompt_id = result.get("prompt_id")

                return {
                    "success": True,
                    "message": "Generation submitted to ComfyUI",
                    "prompt_id": prompt_id,
                    "client_id": client_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                error_detail = response.json() if response.text else "Unknown error"
                logger.error(f"ComfyUI rejected workflow: {error_detail}")
                return {
                    "success": False,
                    "message": "ComfyUI rejected the workflow",
                    "error": error_detail
                }

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))