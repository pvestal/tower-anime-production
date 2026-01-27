#!/usr/bin/env python3
"""
Anime Director Router - Integration with Echo Brain AI Director
Provides intelligent scene planning, prompt refinement, and learning endpoints
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json
import asyncio
import sys
import os

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now import from services
from api.services.echo_anime_client import echo_anime_client, EchoAnimeClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/director", tags=["AI Director"])


# ============= Dependency Injection =============

async def get_echo_client():
    """Dependency to get Echo Brain anime client"""
    return echo_anime_client


# ============= API Endpoints =============

@router.get("/health")
async def check_director_health(
    client: EchoAnimeClient = Depends(get_echo_client)
):
    """Check health of AI Director integration"""
    health = await client.check_health()
    return {
        "echo_brain": health,
        "integration": "operational",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/scene/plan")
async def plan_scene_with_ai(
    request: Dict[str, Any],
    client: EchoAnimeClient = Depends(get_echo_client)
):
    """
    AI-assisted scene planning
    Breaks down a scene description into cinematic shots
    """
    try:
        session_id = request.get("session_id", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        scene_description = request.get("description", "")
        characters = request.get("characters", [])
        duration = request.get("duration", 10)
        style = request.get("style", "anime")

        if not scene_description:
            raise HTTPException(status_code=400, detail="Scene description is required")

        # Get AI scene planning
        scene_plan = await client.plan_scene(
            session_id=session_id,
            scene_description=scene_description,
            characters=characters,
            style_references=[style],
            duration=duration
        )

        # Add metadata
        scene_plan["session_id"] = session_id
        scene_plan["timestamp"] = datetime.utcnow().isoformat()
        scene_plan["ai_generated"] = True

        return {
            "success": True,
            "scene_plan": scene_plan,
            "message": "Scene planning completed successfully"
        }

    except Exception as e:
        logger.error(f"Scene planning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt/enhance")
async def enhance_prompt_with_ai(
    request: Dict[str, Any],
    client: EchoAnimeClient = Depends(get_echo_client)
):
    """
    Enhance generation prompts using AI Director
    Adds cinematic details, style keywords, and consistency hints
    """
    try:
        session_id = request.get("session_id", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        raw_prompt = request.get("prompt", "")
        character = request.get("character")
        emotion = request.get("emotion", "neutral")
        camera_angle = request.get("camera_angle", "medium")
        context_tags = request.get("tags", [])

        if not raw_prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        # Get AI prompt refinement
        refined = await client.refine_prompt(
            session_id=session_id,
            raw_prompt=raw_prompt,
            character_name=character,
            emotion=emotion,
            camera_angle=camera_angle,
            context_tags=context_tags
        )

        return {
            "success": True,
            "original_prompt": raw_prompt,
            "enhanced_prompt": refined.get("enhanced_prompt", raw_prompt),
            "negative_prompt": refined.get("negative_prompt", ""),
            "style_keywords": refined.get("style_keywords", []),
            "cinematic_terms": refined.get("cinematic_terms", []),
            "character_hints": refined.get("character_consistency_hints", []),
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Prompt enhancement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback/submit")
async def submit_generation_feedback(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    client: EchoAnimeClient = Depends(get_echo_client)
):
    """
    Submit feedback about generated content for AI learning
    Helps improve future generations
    """
    try:
        session_id = request.get("session_id")
        generation_id = request.get("generation_id")
        prompt_used = request.get("prompt")
        quality_scores = request.get("quality_scores", {})
        user_feedback = request.get("user_feedback")
        context_tags = request.get("tags", [])

        if not all([session_id, generation_id, prompt_used]):
            raise HTTPException(
                status_code=400,
                detail="session_id, generation_id, and prompt are required"
            )

        # Submit feedback to Echo Brain
        feedback_response = await client.submit_feedback(
            session_id=session_id,
            generation_id=generation_id,
            prompt_used=prompt_used,
            quality_scores=quality_scores,
            user_feedback=user_feedback,
            context_tags=context_tags
        )

        # Log learning insights
        logger.info(f"Feedback submitted for generation {generation_id}: {feedback_response}")

        return {
            "success": True,
            "generation_id": generation_id,
            "learned_elements": feedback_response.get("learned_elements", []),
            "confidence_scores": feedback_response.get("updated_confidence_scores", {}),
            "recommendations": feedback_response.get("recommendations_for_next", []),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/integrate")
async def integrate_with_comfyui_workflow(
    request: Dict[str, Any],
    client: EchoAnimeClient = Depends(get_echo_client)
):
    """
    Generate a complete ComfyUI workflow with AI-enhanced prompts
    Integrates scene planning with generation pipeline
    """
    try:
        session_id = request.get("session_id", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        scene_description = request.get("scene", "")
        characters = request.get("characters", [])
        workflow_type = request.get("workflow_type", "standard")

        if not scene_description:
            raise HTTPException(status_code=400, detail="Scene description is required")

        # Step 1: Plan the scene
        scene_plan = await client.plan_scene(
            session_id=session_id,
            scene_description=scene_description,
            characters=characters
        )

        # Step 2: Generate enhanced prompts for each shot
        enhanced_shots = []
        for shot in scene_plan.get("shot_list", []):
            # Build prompt from shot description
            base_prompt = f"{shot['description']}, {shot['suggested_camera_angle']} shot"

            # Get character emotions
            emotions = shot.get("character_emotions", {})
            if emotions:
                emotion_text = ", ".join([f"{char} feeling {emotion}" for char, emotion in emotions.items()])
                base_prompt += f", {emotion_text}"

            # Enhance the prompt
            refined = await client.refine_prompt(
                session_id=session_id,
                raw_prompt=base_prompt,
                camera_angle=shot["suggested_camera_angle"]
            )

            enhanced_shots.append({
                "shot_number": shot["shot_number"],
                "duration": shot["duration_seconds"],
                "prompt": refined.get("enhanced_prompt", base_prompt),
                "negative_prompt": refined.get("negative_prompt", ""),
                "camera_angle": shot["suggested_camera_angle"],
                "style_keywords": refined.get("style_keywords", [])
            })

        # Step 3: Build workflow configuration
        workflow_config = {
            "session_id": session_id,
            "workflow_type": workflow_type,
            "scene_plan": scene_plan,
            "shots": enhanced_shots,
            "overall_mood": scene_plan.get("overall_mood", "neutral"),
            "lighting": scene_plan.get("lighting_suggestions", "standard"),
            "comfyui_settings": {
                "checkpoint": "counterfeit_v3",  # Default anime model
                "sampler": "DPM++ 2M Karras",
                "steps": 20,
                "cfg_scale": 7.5,
                "width": 1024,
                "height": 576  # 16:9 aspect ratio
            }
        }

        return {
            "success": True,
            "workflow": workflow_config,
            "shot_count": len(enhanced_shots),
            "total_duration": sum(shot["duration"] for shot in enhanced_shots),
            "message": "Workflow integrated with AI Director successfully"
        }

    except Exception as e:
        logger.error(f"Workflow integration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    limit: int = 10
):
    """
    Get history of AI Director interactions for a session
    Useful for reviewing creative decisions
    """
    try:
        # This would query the database for session history
        # For now, return a placeholder
        return {
            "session_id": session_id,
            "interactions": [],
            "total_scenes_planned": 0,
            "total_prompts_refined": 0,
            "average_quality_score": 0.0,
            "message": "Session history endpoint - database integration pending"
        }

    except Exception as e:
        logger.error(f"Failed to get session history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/process")
async def batch_process_scenes(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    client: EchoAnimeClient = Depends(get_echo_client)
):
    """
    Process multiple scenes in batch with AI Director
    Efficient for episode or project-wide generation
    """
    try:
        session_id = request.get("session_id", f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        scenes = request.get("scenes", [])

        if not scenes:
            raise HTTPException(status_code=400, detail="At least one scene is required")

        processed_scenes = []

        # Process each scene
        for idx, scene in enumerate(scenes):
            try:
                # Plan the scene
                scene_plan = await client.plan_scene(
                    session_id=session_id,
                    scene_description=scene.get("description", ""),
                    characters=scene.get("characters", []),
                    duration=scene.get("duration", 10)
                )

                processed_scenes.append({
                    "scene_index": idx,
                    "original": scene,
                    "ai_plan": scene_plan,
                    "status": "success"
                })

            except Exception as scene_error:
                logger.warning(f"Failed to process scene {idx}: {scene_error}")
                processed_scenes.append({
                    "scene_index": idx,
                    "original": scene,
                    "error": str(scene_error),
                    "status": "failed"
                })

        # Calculate statistics
        success_count = sum(1 for s in processed_scenes if s["status"] == "success")

        return {
            "success": True,
            "session_id": session_id,
            "total_scenes": len(scenes),
            "processed_successfully": success_count,
            "failed": len(scenes) - success_count,
            "scenes": processed_scenes,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))