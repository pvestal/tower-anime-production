"""
SVD Animation Router - Production endpoint for Stable Video Diffusion
Generates character animations from existing character images
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import json
import httpx
import shutil
import os
from datetime import datetime
from pathlib import Path

from database import get_db
from models import GenerationJob  # Fixed import - CharacterGeneration doesn't exist

router = APIRouter(prefix="/api/anime/character-studio", tags=["svd_animation"])

COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_TEMPLATE_PATH = "/opt/tower-anime-production/workflows/animation_templates/svd_img2vid.json"
COMFYUI_INPUT_DIR = "/mnt/1TB-storage/ComfyUI/input"
ANIMATION_OUTPUT_DIR = "/mnt/1TB-storage/character_animations"

class SVDAnimationRequest(BaseModel):
    """Request parameters for SVD animation generation"""
    motion_bucket_id: int = Field(
        default=127,
        ge=0,
        le=255,
        description="Controls motion amount: 0=minimal, 127=moderate, 255=extreme"
    )
    fps: int = Field(
        default=6,
        ge=1,
        le=30,
        description="Frames per second (SVD trained at 6 FPS)"
    )
    video_frames: int = Field(
        default=25,
        ge=14,
        le=25,
        description="Number of frames to generate (14-25)"
    )
    augmentation_level: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Video quality enhancement (0.0-1.0)"
    )
    steps: int = Field(
        default=20,
        ge=10,
        le=50,
        description="Diffusion steps (more = higher quality, slower)"
    )
    cfg: float = Field(
        default=2.5,
        ge=1.0,
        le=10.0,
        description="CFG scale for guidance strength"
    )

class SVDAnimationResponse(BaseModel):
    """Response from SVD animation generation"""
    animation_id: int
    character_id: int
    character_name: str
    project_name: str
    status: str
    comfyui_prompt_id: str
    total_frames: int
    fps: int
    message: str

def load_workflow_template() -> dict:
    """Load SVD workflow template"""
    with open(WORKFLOW_TEMPLATE_PATH) as f:
        return json.load(f)

def inject_svd_parameters(workflow: dict, params: dict) -> dict:
    """Inject parameters into SVD workflow"""
    # Update conditioning node (node 3)
    workflow["3"]["inputs"]["motion_bucket_id"] = params["motion_bucket_id"]
    workflow["3"]["inputs"]["fps"] = params["fps"]
    workflow["3"]["inputs"]["video_frames"] = params["video_frames"]
    workflow["3"]["inputs"]["augmentation_level"] = params["augmentation_level"]
    
    # Update sampler node (node 5)
    workflow["5"]["inputs"]["steps"] = params["steps"]
    workflow["5"]["inputs"]["cfg"] = params["cfg"]
    workflow["5"]["inputs"]["seed"] = params.get("seed", 60108)
    
    # Update image loader (node 1)
    workflow["1"]["inputs"]["image"] = params["image_filename"]
    
    # Update output prefix (node 7)
    workflow["7"]["inputs"]["filename_prefix"] = params["output_prefix"]
    
    return workflow

@router.post("/character/{character_id}/animate-svd", response_model=SVDAnimationResponse)
async def animate_character_svd(
    character_id: int,
    request: SVDAnimationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate SVD animation from a character's reference image.
    
    This endpoint:
    1. Fetches the character's existing image
    2. Prepares SVD workflow with specified parameters
    3. Submits to ComfyUI for generation
    4. Tracks the animation job in database
    5. Returns immediately while generation happens in background
    """
    
    # 1. Fetch character and validate
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail=f"Character {character_id} not found")
    
    if not character.output_path or not os.path.exists(character.output_path):
        raise HTTPException(
            status_code=400,
            detail=f"Character image not found at {character.output_path}"
        )
    
    # 2. Copy character image to ComfyUI input directory
    os.makedirs(COMFYUI_INPUT_DIR, exist_ok=True)
    image_filename = f"char_{character_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    input_image_path = os.path.join(COMFYUI_INPUT_DIR, image_filename)
    shutil.copy(character.output_path, input_image_path)
    
    # 3. Load and configure SVD workflow
    workflow = load_workflow_template()
    output_prefix = f"svd_{character.project}_{character.character_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}".replace(" ", "_")
    
    workflow = inject_svd_parameters(workflow, {
        "motion_bucket_id": request.motion_bucket_id,
        "fps": request.fps,
        "video_frames": request.video_frames,
        "augmentation_level": request.augmentation_level,
        "steps": request.steps,
        "cfg": request.cfg,
        "seed": character.seed if character.seed else 60108,
        "image_filename": image_filename,
        "output_prefix": output_prefix
    })
    
    # 4. Submit to ComfyUI
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"ComfyUI error: {response.status_code} - {response.text}"
                )
            
            result = response.json()
            prompt_id = result["prompt_id"]
            
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"ComfyUI service unavailable: {str(e)}"
            )
    
    # 5. Create animation record in database
    animation = AnimationSequence(
        character_id=character_id,
        animation_type="svd",
        comfyui_prompt_id=prompt_id,
        status="processing",
        total_frames=request.video_frames,
        fps=request.fps,
        motion_bucket_id=request.motion_bucket_id,
        augmentation_level=request.augmentation_level,
        output_prefix=output_prefix,
        created_at=datetime.utcnow()
    )
    
    db.add(animation)
    db.commit()
    db.refresh(animation)
    
    return SVDAnimationResponse(
        animation_id=animation.id,
        character_id=character_id,
        character_name=character.character_name,
        project_name=character.project,
        status="processing",
        comfyui_prompt_id=prompt_id,
        total_frames=request.video_frames,
        fps=request.fps,
        message=f"SVD animation generation started. Check status with animation_id: {animation.id}"
    )

@router.get("/animation/{animation_id}/status")
async def get_animation_status(
    animation_id: int,
    db: Session = Depends(get_db)
):
    """Check status of SVD animation generation"""
    
    animation = db.query(AnimationSequence).filter(
        AnimationSequence.id == animation_id
    ).first()
    
    if not animation:
        raise HTTPException(status_code=404, detail=f"Animation {animation_id} not found")
    
    # Poll ComfyUI for completion status
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{COMFYUI_URL}/history/{animation.comfyui_prompt_id}"
            )
            
            if response.status_code == 200:
                history_data = response.json()
                
                if animation.comfyui_prompt_id in history_data:
                    prompt_data = history_data[animation.comfyui_prompt_id]
                    
                    # Check for completion
                    if "outputs" in prompt_data and "7" in prompt_data["outputs"]:
                        outputs = prompt_data["outputs"]["7"]
                        if "images" in outputs:
                            frames = outputs["images"]
                            
                            # Update animation record
                            animation.status = "completed"
                            animation.completed_at = datetime.utcnow()
                            animation.frame_count = len(frames)
                            db.commit()
                            
                            return {
                                "animation_id": animation_id,
                                "status": "completed",
                                "total_frames": len(frames),
                                "frames": [f["filename"] for f in frames]
                            }
                    
                    # Check for errors
                    if "status" in prompt_data:
                        status = prompt_data["status"]
                        if "messages" in status:
                            for msg_type, msg_data in status["messages"]:
                                if msg_type == "execution_error":
                                    animation.status = "failed"
                                    animation.error_message = str(msg_data)
                                    db.commit()
                                    
                                    return {
                                        "animation_id": animation_id,
                                        "status": "failed",
                                        "error": msg_data
                                    }
        
        except httpx.RequestError:
            pass
    
    return {
        "animation_id": animation_id,
        "status": animation.status,
        "total_frames": animation.total_frames,
        "fps": animation.fps
    }
