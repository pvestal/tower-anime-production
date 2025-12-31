"""
API endpoints for Scene Director orchestrator v2
Enterprise-grade anime production with semantic registry
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import asyncio
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from orchestrator.v2.scene_director import SceneDirector
from services.database import get_db_connection
from services.comfyui_client import ComfyUIClient
from services.echo_brain_client import EchoBrainClient

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])

# Initialize clients
comfyui_client = ComfyUIClient()
echo_client = EchoBrainClient()


# Pydantic models
class GenerationRequest(BaseModel):
    """Request model for scene generation"""
    character_id: int
    action_id: int
    style_angle_id: int
    duration_seconds: int
    workflow_tier: Optional[str] = None
    project_id: Optional[int] = None
    episode_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = {}


class RapidRegenerateRequest(BaseModel):
    """Request model for rapid regeneration"""
    cache_key: str
    modifications: Dict[str, Any]


class QualityUpdateRequest(BaseModel):
    """Request model for quality score update"""
    quality_score: float
    user_rating: Optional[int] = None


# Global job tracking (in production, use Redis or similar)
active_jobs = {}


@router.post("/generate")
async def generate_scene(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_connection)
):
    """
    Submit a new scene generation job
    """
    try:
        # Initialize Scene Director
        director = SceneDirector(db, comfyui_client, echo_client)

        # Get character, action, and style details
        character = await db.fetch_one(
            "SELECT * FROM characters WHERE id = %s",
            (request.character_id,)
        )
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        action = await db.fetch_one(
            "SELECT * FROM semantic_actions WHERE id = %s",
            (request.action_id,)
        )
        if not action:
            raise HTTPException(status_code=404, detail="Action not found")

        style = await db.fetch_one(
            "SELECT * FROM style_angle_library WHERE id = %s",
            (request.style_angle_id,)
        )
        if not style:
            raise HTTPException(status_code=404, detail="Style not found")

        # Plan the scene
        payload = await director.plan_scene(
            character_name=character['name'],
            action_tag=action['action_tag'],
            style_name=style['name'],
            duration_sec=request.duration_seconds,
            project_id=request.project_id,
            episode_id=request.episode_id
        )

        # Apply any custom options
        if request.options:
            payload.update(request.options)

        # Execute generation
        result = await director.execute_generation(payload)

        # Track job
        active_jobs[result['job_id']] = {
            'status': 'submitted',
            'payload': payload,
            'created_at': datetime.now(),
            'result': result
        }

        # Start background monitoring
        background_tasks.add_task(
            monitor_job,
            result['job_id'],
            director
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status of a generation job
    """
    if job_id not in active_jobs:
        # Try to fetch from ComfyUI directly
        try:
            status = await comfyui_client.get_job_status(job_id)
            return status
        except:
            raise HTTPException(status_code=404, detail="Job not found")

    job = active_jobs[job_id]

    # Calculate progress based on time elapsed
    elapsed = (datetime.now() - job['created_at']).total_seconds()
    estimated = job['result'].get('estimated_duration', 60)
    progress = min(int((elapsed / estimated) * 100), 99)

    return {
        'status': job['status'],
        'progress': progress if job['status'] != 'completed' else 100,
        'eta': max(0, int(estimated - elapsed)),
        'cache_key': job['result'].get('cache_key'),
        'output_url': job.get('output_url'),
        'error': job.get('error')
    }


@router.post("/rapid-regenerate")
async def rapid_regenerate(
    request: RapidRegenerateRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_connection)
):
    """
    Rapidly regenerate from cached result with modifications
    """
    try:
        director = SceneDirector(db, comfyui_client, echo_client)

        result = await director.rapid_regenerate(
            cache_key=request.cache_key,
            modifications=request.modifications
        )

        # Track job
        active_jobs[result['job_id']] = {
            'status': 'regenerating',
            'created_at': datetime.now(),
            'result': result
        }

        # Start background monitoring
        background_tasks.add_task(
            monitor_job,
            result['job_id'],
            director
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")


@router.get("/cache")
async def get_cached_generations(
    character_id: int,
    limit: int = 10,
    db=Depends(get_db_connection)
):
    """
    Get cached generations for a character
    """
    query = """
        SELECT gc.*, sa.action_tag, sal.name as style_name
        FROM generation_cache gc
        LEFT JOIN semantic_actions sa ON gc.action_id = sa.id
        LEFT JOIN style_angle_library sal ON gc.style_angle_id = sal.id
        WHERE gc.character_id = %s
        ORDER BY gc.quality_score DESC, gc.created_at DESC
        LIMIT %s
    """

    results = await db.fetch_all(query, (character_id, limit))

    return [dict(r) for r in results]


@router.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancel a running generation job
    """
    try:
        # Cancel in ComfyUI
        await comfyui_client.cancel_job(job_id)

        # Update local tracking
        if job_id in active_jobs:
            active_jobs[job_id]['status'] = 'cancelled'

        return {"message": "Job cancelled successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@router.patch("/cache/{cache_id}/quality")
async def update_quality_score(
    cache_id: str,
    request: QualityUpdateRequest,
    db=Depends(get_db_connection)
):
    """
    Update quality score for a cached generation
    """
    query = """
        UPDATE generation_cache
        SET quality_score = %s, user_rating = %s
        WHERE id = %s
    """

    await db.execute(
        query,
        (request.quality_score, request.user_rating, cache_id)
    )

    return {"message": "Quality score updated"}


# SSOT endpoints for semantic registry
@router.get("/ssot/semantic-actions")
async def get_semantic_actions(
    category: Optional[str] = None,
    db=Depends(get_db_connection)
):
    """
    Get all semantic actions, optionally filtered by category
    """
    if category:
        query = "SELECT * FROM semantic_actions WHERE category = %s ORDER BY intensity_level"
        results = await db.fetch_all(query, (category,))
    else:
        query = "SELECT * FROM semantic_actions ORDER BY category, intensity_level"
        results = await db.fetch_all(query)

    return [dict(r) for r in results]


@router.get("/ssot/styles")
async def get_styles(db=Depends(get_db_connection)):
    """
    Get all available styles
    """
    query = "SELECT * FROM style_angle_library ORDER BY name"
    results = await db.fetch_all(query)

    return [dict(r) for r in results]


@router.get("/ssot/characters")
async def get_characters(
    project_id: Optional[int] = None,
    db=Depends(get_db_connection)
):
    """
    Get all characters, optionally filtered by project
    """
    if project_id:
        query = """
            SELECT c.*, cgs.lora_path, cgs.trigger_words, cgs.optimal_weight
            FROM characters c
            LEFT JOIN character_generation_settings cgs ON c.id = cgs.character_id
            WHERE c.project_id = %s
            ORDER BY c.name
        """
        results = await db.fetch_all(query, (project_id,))
    else:
        query = """
            SELECT c.*, cgs.lora_path, cgs.trigger_words, cgs.optimal_weight
            FROM characters c
            LEFT JOIN character_generation_settings cgs ON c.id = cgs.character_id
            ORDER BY c.name
        """
        results = await db.fetch_all(query)

    return [dict(r) for r in results]


@router.get("/ssot/actions/{action_id}/compatible-styles")
async def get_compatible_styles(action_id: int, db=Depends(get_db_connection)):
    """
    Get styles compatible with a specific action
    """
    # First get the action category
    action = await db.fetch_one(
        "SELECT category FROM semantic_actions WHERE id = %s",
        (action_id,)
    )

    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    # Get compatible styles
    query = """
        SELECT * FROM style_angle_library
        WHERE %s = ANY(compatible_categories)
        ORDER BY name
    """
    results = await db.fetch_all(query, (action['category'],))

    return [dict(r) for r in results]


@router.post("/ssot/production-scenes")
async def create_production_scene(
    scene: Dict[str, Any],
    db=Depends(get_db_connection)
):
    """
    Create a new production scene entry
    """
    query = """
        INSERT INTO production_scenes (
            project_id, episode_id, scene_number,
            semantic_action_id, style_angle_id,
            duration_seconds, character_ids, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    result = await db.fetch_one(
        query,
        (
            scene.get('project_id'),
            scene.get('episode_id'),
            scene.get('scene_number'),
            scene.get('semantic_action_id'),
            scene.get('style_angle_id'),
            scene.get('duration_seconds'),
            scene.get('character_ids', []),
            scene.get('notes')
        )
    )

    return {"id": result['id'], "message": "Production scene created"}


# Background task for monitoring jobs
async def monitor_job(job_id: str, director: SceneDirector):
    """
    Monitor a generation job until completion
    """
    max_attempts = 120  # 10 minutes max
    attempt = 0

    while attempt < max_attempts:
        await asyncio.sleep(5)  # Check every 5 seconds

        try:
            status = await comfyui_client.get_job_status(job_id)

            if job_id in active_jobs:
                active_jobs[job_id]['status'] = status['status']

                if status['status'] == 'completed':
                    active_jobs[job_id]['output_url'] = status.get('output_url')
                    # Cache the successful generation
                    if 'payload' in active_jobs[job_id]:
                        await director.cache.store_generation(
                            active_jobs[job_id]['payload'],
                            status.get('output', {})
                        )
                    break
                elif status['status'] == 'failed':
                    active_jobs[job_id]['error'] = status.get('error', 'Unknown error')
                    break
        except Exception as e:
            print(f"Error monitoring job {job_id}: {e}")

        attempt += 1

    # Clean up old job after some time
    await asyncio.sleep(300)  # Keep for 5 minutes after completion
    if job_id in active_jobs:
        del active_jobs[job_id]