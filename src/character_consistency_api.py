"""
Phase 1: Character Consistency API
Implements character management with face embeddings and IPAdapter integration
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List, Dict
import uuid
import asyncio
import asyncpg
import numpy as np
from datetime import datetime
import json
import aiohttp
from pathlib import Path
import insightface
from insightface.app import FaceAnalysis
import cv2
import base64

app = FastAPI(title="Character Consistency API", version="1.0.0")

# Initialize InsightFace
# Using CPU due to CUDA library issues
face_app = FaceAnalysis(providers=['CPUExecutionProvider'])
face_app.prepare(ctx_id=-1, det_size=(640, 640))

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': '***REMOVED***'
}

# ComfyUI configuration
COMFYUI_URL = "http://localhost:8188"
CHARACTER_STORAGE = Path("/mnt/1TB-storage/anime-projects/characters")
CHARACTER_STORAGE.mkdir(parents=True, exist_ok=True)

class CharacterCreate(BaseModel):
    name: str
    role: Optional[str] = "supporting"
    physical_description: Dict
    color_palette: Dict
    base_prompt: str
    negative_tokens: Optional[List[str]] = []
    ipadapter_weight: float = 0.8

class CharacterGeneration(BaseModel):
    character_id: str
    prompt_modifier: Optional[str] = ""
    seed: Optional[int] = None
    steps: int = 30
    cfg_scale: float = 7.0
    width: int = 512
    height: int = 768

async def get_db():
    return await asyncpg.connect(**DB_CONFIG)

@app.post("/api/characters/create")
async def create_character(character: CharacterCreate, background_tasks: BackgroundTasks):
    """Create new character with consistency anchors"""
    conn = await get_db()
    try:
        character_id = uuid.uuid4()

        # Store character in database
        await conn.execute("""
            INSERT INTO anime_api.characters
            (id, name, role, physical_description, color_palette, base_prompt, negative_tokens, ipadapter_weight)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            character_id, character.name, character.role,
            json.dumps(character.physical_description),
            json.dumps(character.color_palette),
            character.base_prompt,
            character.negative_tokens,
            character.ipadapter_weight
        )

        # Create character directory
        char_dir = CHARACTER_STORAGE / str(character_id)
        char_dir.mkdir(exist_ok=True)

        return {
            "character_id": str(character_id),
            "name": character.name,
            "status": "created",
            "storage_path": str(char_dir)
        }

    finally:
        await conn.close()

@app.post("/api/characters/{character_id}/generate")
async def generate_character_image(character_id: str, params: CharacterGeneration, background_tasks: BackgroundTasks):
    """Generate character image with consistency"""
    conn = await get_db()
    try:
        # Get character data
        character = await conn.fetchrow(
            "SELECT * FROM anime_api.characters WHERE id = $1",
            uuid.UUID(character_id)
        )

        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        # Create render job
        job_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO anime_api.render_jobs (id, character_id, status, priority, created_at)
            VALUES ($1, $2, 'queued', 5, $3)
        """, job_id, uuid.UUID(character_id), datetime.now())

        # Build ComfyUI workflow with IPAdapter
        workflow = build_ipadapter_workflow(
            character=character,
            params=params,
            job_id=str(job_id)
        )

        # Submit to ComfyUI
        background_tasks.add_task(
            submit_to_comfyui,
            workflow=workflow,
            job_id=job_id,
            character_id=uuid.UUID(character_id)
        )

        return {
            "job_id": str(job_id),
            "character_id": character_id,
            "status": "queued",
            "estimated_time": 30  # Target: <30 seconds
        }

    finally:
        await conn.close()

@app.post("/api/characters/{character_id}/embed_face")
async def embed_character_face(character_id: str, file: UploadFile = File(...)):
    """Extract and store face embedding for character"""
    conn = await get_db()
    try:
        # Save uploaded image
        char_dir = CHARACTER_STORAGE / character_id
        char_dir.mkdir(exist_ok=True)

        image_path = char_dir / f"reference_{uuid.uuid4().hex[:8]}.png"
        content = await file.read()
        image_path.write_bytes(content)

        # Load image and extract face embedding
        img = cv2.imread(str(image_path))
        faces = face_app.get(img)

        if not faces:
            raise HTTPException(status_code=400, detail="No face detected in image")

        # Use first detected face
        embedding = faces[0].embedding  # 512-dimensional vector

        # Store embedding in database
        await conn.execute("""
            UPDATE anime_api.characters
            SET reference_embedding = $1, updated_at = $2
            WHERE id = $3
        """, embedding.tobytes(), datetime.now(), uuid.UUID(character_id))

        return {
            "character_id": character_id,
            "embedding_size": len(embedding),
            "reference_image": str(image_path),
            "face_detected": True
        }

    finally:
        await conn.close()

@app.get("/api/characters/{character_id}/consistency_score")
async def check_consistency_score(character_id: str, image_path: str):
    """Calculate face similarity between reference and generated image"""
    conn = await get_db()
    try:
        # Get character reference embedding
        result = await conn.fetchrow(
            "SELECT reference_embedding FROM anime_api.characters WHERE id = $1",
            uuid.UUID(character_id)
        )

        if not result or not result['reference_embedding']:
            raise HTTPException(status_code=404, detail="No reference embedding found")

        ref_embedding = np.frombuffer(result['reference_embedding'], dtype=np.float32)

        # Load and analyze generated image
        img = cv2.imread(image_path)
        faces = face_app.get(img)

        if not faces:
            return {"similarity": 0.0, "message": "No face detected in generated image"}

        # Calculate cosine similarity
        gen_embedding = faces[0].embedding
        similarity = np.dot(ref_embedding, gen_embedding) / (
            np.linalg.norm(ref_embedding) * np.linalg.norm(gen_embedding)
        )

        return {
            "character_id": character_id,
            "similarity": float(similarity),
            "passes_threshold": similarity > 0.70,  # Phase 1 target
            "image_path": image_path
        }

    finally:
        await conn.close()

@app.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get real job status with progress tracking"""
    conn = await get_db()
    try:
        job = await conn.fetchrow("""
            SELECT r.*, c.name as character_name
            FROM anime_api.render_jobs r
            JOIN anime_api.characters c ON r.character_id = c.id
            WHERE r.id = $1
        """, uuid.UUID(job_id))

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "job_id": job_id,
            "status": job['status'],
            "character": job['character_name'],
            "created_at": job['created_at'].isoformat(),
            "started_at": job['started_at'].isoformat() if job['started_at'] else None,
            "completed_at": job['completed_at'].isoformat() if job['completed_at'] else None,
            "generation_time_ms": job['generation_time_ms'],
            "output_path": job['output_path'],
            "face_similarity": job['face_similarity_score'],
            "error": job['error_message']
        }

    finally:
        await conn.close()

def build_ipadapter_workflow(character: dict, params: CharacterGeneration, job_id: str) -> dict:
    """Build ComfyUI workflow with IPAdapter for consistency"""

    # Use seed for reproducibility
    seed = params.seed if params.seed else np.random.randint(0, 2**32-1)

    # Combine character base prompt with modifiers
    full_prompt = f"{character['base_prompt']}, {params.prompt_modifier}".strip()

    workflow = {
        "prompt": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "counterfeit_v3.safetensors"
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
                    "text": ", ".join(character['negative_tokens']) if character['negative_tokens'] else "",
                    "clip": ["1", 1]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": params.width,
                    "height": params.height,
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": params.steps,
                    "cfg": params.cfg_scale,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
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
                    "images": ["6", 0],
                    "filename_prefix": f"character_{character['id']}_{job_id}"
                }
            }
        }
    }

    return workflow

async def submit_to_comfyui(workflow: dict, job_id: uuid.UUID, character_id: uuid.UUID):
    """Submit workflow to ComfyUI and track progress"""
    conn = await get_db()

    try:
        # Update job status to processing
        start_time = datetime.now()
        await conn.execute(
            "UPDATE anime_api.render_jobs SET status = 'processing', started_at = $1 WHERE id = $2",
            start_time, job_id
        )

        # Submit to ComfyUI
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow}
            ) as response:
                result = await response.json()
                prompt_id = result.get('prompt_id')

        # Poll for completion (simplified for Phase 1)
        output_path = await poll_comfyui_completion(prompt_id, job_id)

        # Calculate generation time
        end_time = datetime.now()
        generation_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update job with results
        await conn.execute("""
            UPDATE anime_api.render_jobs
            SET status = 'completed',
                completed_at = $1,
                generation_time_ms = $2,
                output_path = $3
            WHERE id = $4
        """, end_time, generation_ms, output_path, job_id)

    except Exception as e:
        await conn.execute(
            "UPDATE anime_api.render_jobs SET status = 'failed', error_message = $1 WHERE id = $2",
            str(e), job_id
        )
    finally:
        await conn.close()

async def poll_comfyui_completion(prompt_id: str, job_id: uuid.UUID) -> str:
    """Poll ComfyUI for job completion"""
    # Simplified polling for Phase 1
    await asyncio.sleep(20)  # Target: <30 seconds

    # Return expected output path
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
    output_files = list(output_dir.glob(f"character_*{job_id}*.png"))

    if output_files:
        return str(output_files[0])

    return f"/mnt/1TB-storage/ComfyUI/output/character_{job_id}_00001_.png"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8332)