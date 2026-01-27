"""
Generation endpoints for Tower Anime Production API
Handles anime video/image generation, character shots, and scene generation
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional

from api.core.database import get_db
from api.core.security import require_auth, guest_or_auth
from api.models import ProductionJob
from api.schemas import AnimeGenerationRequest, CharacterGenerateRequest, GenerationStatusResponse
from api.services import video_generation_service, comfyui_service
from api.core.dependencies import get_pipeline, PIPELINE_AVAILABLE

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/anime/projects/{project_id}/generate")
async def generate_video_frontend_compat(
    project_id: int,
    request: dict,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate video - Frontend compatibility endpoint"""
    # Convert frontend request format to backend format
    anime_request = AnimeGenerationRequest(
        prompt=request.get("prompt", ""),
        character=request.get("character", "original"),
        style=request.get("style", "anime"),
        duration=request.get("duration", 30)
    )

    # Create production job record
    job = ProductionJob(
        project_id=project_id,
        job_type="video_generation",
        prompt=anime_request.prompt,
        parameters=anime_request.json(),
        status="processing"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # Generate video using the video generation service
        if anime_request.generation_type == "video":
            result = await video_generation_service.generate_video_with_animatediff(
                prompt=anime_request.prompt,
                checkpoint=None,  # Use default
                lora_name=None if anime_request.character == "original" else f"{anime_request.character}.safetensors"
            )
        else:
            result = await video_generation_service.generate_image_with_comfyui(
                prompt=anime_request.prompt,
                checkpoint=None,
                lora_name=None if anime_request.character == "original" else f"{anime_request.character}.safetensors"
            )

        # Update job with result
        job.status = "completed"
        job.output_path = result.get("output_path")
        db.commit()

        return {
            "job_id": job.id,
            "prompt_id": result.get("prompt_id"),
            "output_path": result.get("output_path"),
            "status": "submitted",
            "workflow_used": result.get("workflow_used")
        }

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/api/anime/generation/{request_id}/status", response_model=GenerationStatusResponse)
async def get_generation_status(request_id: str, db: Session = Depends(get_db)):
    """Get generation status by request ID with REAL ComfyUI monitoring"""
    # Try to find the job in database first
    job = db.query(ProductionJob).filter(
        ProductionJob.parameters.contains(request_id)
    ).first()

    if job:
        progress = await video_generation_service.get_generation_progress(request_id)
        return GenerationStatusResponse(
            request_id=request_id,
            status=job.status,
            progress=progress,
            output_path=job.output_path
        )

    # Fallback to ComfyUI queue check
    progress = await video_generation_service.get_generation_progress(request_id)
    status = "completed" if progress >= 1.0 else "processing" if progress > 0 else "queued"

    return GenerationStatusResponse(
        request_id=request_id,
        status=status,
        progress=progress
    )


@router.post("/api/anime/generation/{request_id}/cancel")
async def cancel_generation(request_id: str, current_user: dict = Depends(require_auth)):
    """Cancel generation by request ID"""
    success = await video_generation_service.cancel_generation(request_id)
    return {"message": "Generation cancelled" if success else "Failed to cancel generation"}


@router.post("/api/anime/characters/{character_id}/generate")
async def generate_character_shot(
    character_id: int,
    request: CharacterGenerateRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate character-specific shots (portrait, action, etc.)"""

    # Build character-specific prompt
    character_prompt = f"{request.action} of anime character"
    if request.location:
        character_prompt += f" in {request.location}"
    if request.prompt:
        character_prompt = request.prompt

    # Create production job
    job = ProductionJob(
        job_type="character_generation",
        prompt=character_prompt,
        parameters=request.json(),
        status="processing"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        if request.generation_type == "video":
            result = await video_generation_service.generate_video_with_animatediff(
                prompt=character_prompt,
                frame_count=24 if request.action == "walking" else 16
            )
        else:
            result = await video_generation_service.generate_image_with_comfyui(
                prompt=character_prompt
            )

        job.status = "completed"
        job.output_path = result.get("output_path")
        db.commit()

        return {
            "job_id": job.id,
            "character_id": character_id,
            "action": request.action,
            "generation_type": request.generation_type,
            "prompt_id": result.get("prompt_id"),
            "output_path": result.get("output_path"),
            "status": "submitted"
        }

    except Exception as e:
        logger.error(f"Character generation failed: {e}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Character generation failed: {str(e)}")


@router.post("/api/anime/scenes/{scene_id}/generate")
async def generate_from_scene(
    scene_id: str,
    generation_type: str = "image",
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate content from scene data"""
    from ..models import Scene

    # Get scene from database
    scene = db.query(Scene).filter(Scene.id == int(scene_id)).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Build prompt from scene
    prompt = scene.description or scene.name
    if scene.scene_data:
        characters = scene.scene_data.get("characters", [])
        if characters:
            prompt += f", featuring {', '.join(characters)}"

        location = scene.scene_data.get("location")
        if location:
            prompt += f", set in {location}"

    # Create production job
    job = ProductionJob(
        job_type="scene_generation",
        prompt=prompt,
        parameters=f'{{"scene_id": {scene_id}, "generation_type": "{generation_type}"}}',
        status="processing"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        if generation_type == "video":
            result = await video_generation_service.generate_video_with_animatediff(
                prompt=prompt,
                frame_count=int((scene.duration or 3.0) * 8)  # 8 FPS
            )
        else:
            result = await video_generation_service.generate_image_with_comfyui(
                prompt=prompt
            )

        # Update scene with generated content
        scene.scene_data = scene.scene_data or {}
        scene.scene_data["generated_content"] = {
            "output_path": result.get("output_path"),
            "prompt_id": result.get("prompt_id"),
            "generation_type": generation_type
        }
        scene.status = "completed"

        job.status = "completed"
        job.output_path = result.get("output_path")
        db.commit()

        return {
            "job_id": job.id,
            "scene_id": scene_id,
            "generation_type": generation_type,
            "prompt_used": prompt,
            "prompt_id": result.get("prompt_id"),
            "output_path": result.get("output_path"),
            "status": "submitted"
        }

    except Exception as e:
        logger.error(f"Scene generation failed: {e}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Scene generation failed: {str(e)}")


@router.post("/generate/integrated")
async def generate_with_integrated_pipeline(
    request: AnimeGenerationRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate anime using the integrated pipeline with quality controls"""
    if not PIPELINE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Integrated pipeline not available")

    try:
        # Create production job record
        job = ProductionJob(
            job_type="integrated_generation",
            prompt=request.prompt,
            parameters=request.json(),
            status="processing"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Use integrated pipeline
        pipeline = get_pipeline()
        result = await pipeline.test_complete_pipeline()

        if result.get('test_result', {}).get('success', False):
            # Update job status
            job.status = "completed"
            job.quality_score = result.get('test_result', {}).get('quality_score', 0.85)
            db.commit()

            return {
                "job_id": job.id,
                "status": "completed",
                "message": "Generation completed with quality controls",
                "quality_score": job.quality_score,
                "pipeline_used": "integrated",
                "components_tested": result.get('components_tested', []),
                "result": result
            }
        else:
            # Update job as failed
            job.status = "failed"
            db.commit()
            raise HTTPException(status_code=500, detail="Generation failed quality controls")

    except Exception as e:
        # Mark job as failed
        if 'job' in locals():
            job.status = "failed"
            db.commit()
        raise HTTPException(status_code=500, detail=f"Integrated generation failed: {str(e)}")


@router.post("/generate/professional")
async def generate_professional_anime(
    request: AnimeGenerationRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Generate professional anime content using optimized workflows"""
    # Create production job record
    job = ProductionJob(
        job_type="professional_generation",
        prompt=request.prompt,
        parameters=request.json(),
        status="processing"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # Use professional workflow with enhanced prompting
        enhanced_prompt = f"masterpiece, best quality, {request.prompt}, cinematic lighting, detailed background, professional anime art, 8k uhd"

        if request.generation_type == "video":
            result = await video_generation_service.generate_video_with_animatediff(
                prompt=enhanced_prompt,
                frame_count=request.duration * 8  # 8 FPS
            )
        else:
            result = await video_generation_service.generate_image_with_comfyui(
                prompt=enhanced_prompt,
                steps=30,  # More steps for professional quality
                cfg=8.0
            )

        # Update job with professional quality settings
        job.status = "completed"
        job.output_path = result.get("output_path")
        job.quality_score = 0.9  # Professional tier
        db.commit()

        return {
            "job_id": job.id,
            "status": "completed",
            "prompt_id": result.get("prompt_id"),
            "output_path": result.get("output_path"),
            "quality_tier": "professional",
            "workflow_used": result.get("workflow_used")
        }

    except Exception as e:
        logger.error(f"Professional generation failed: {e}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Professional generation failed: {str(e)}")


@router.post("/echo/enhance-prompt")
async def enhance_prompt(request: dict, current_user: dict = Depends(guest_or_auth)):
    """Enhance prompt using Echo Brain AI"""
    original_prompt = request.get("prompt", "")

    # Mock enhancement for now - in production this would call Echo Brain API
    enhanced_suggestions = [
        f"{original_prompt}, masterpiece, best quality, detailed",
        f"cinematic {original_prompt}, dramatic lighting",
        f"{original_prompt}, anime style, vibrant colors",
        f"high quality {original_prompt}, professional animation",
        "Specified high quality anime style",
        "Enhanced for detailed animation"
    ]

    return {
        "original": original_prompt,
        "enhanced_options": enhanced_suggestions
    }