"""
Additional Episode Management API Endpoints
To be imported into main.py
"""

from fastapi import HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

COMFYUI_URL = "http://localhost:8188"

async def add_episode_endpoints(app, get_db):
    """Add episode management endpoints to the FastAPI app"""

    @app.get("/api/anime/jobs/{job_id}/status")
    async def get_job_status_detailed(job_id: str, db: Session = Depends(get_db)):
        """Get detailed job status for polling"""
        # Check if it's a ComfyUI job ID (has dashes)
        if "-" in str(job_id):
            # This is a ComfyUI job - check its status
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{COMFYUI_URL}/history/{job_id}") as response:
                        if response.status == 200:
                            history = await response.json()
                            if job_id in history:
                                outputs = history[job_id].get('outputs', {})
                                if outputs:
                                    return {"status": "completed", "outputs": outputs}
                                else:
                                    # Check if it's still in queue
                                    async with session.get(f"{COMFYUI_URL}/queue") as queue_response:
                                        if queue_response.status == 200:
                                            queue_data = await queue_response.json()
                                            queue_running = queue_data.get('queue_running', [])
                                            queue_pending = queue_data.get('queue_pending', [])

                                            for item in queue_running:
                                                if item[0] == job_id:
                                                    return {"status": "generating"}

                                            for item in queue_pending:
                                                if item[0] == job_id:
                                                    return {"status": "queued"}

                                    return {"status": "generating"}
            except Exception as e:
                logger.error(f"Error checking ComfyUI job {job_id}: {e}")

            return {"status": "unknown"}

        # Otherwise check database for numeric job IDs
        try:
            job_id_int = int(job_id)
            job = db.query(ProductionJob).filter(ProductionJob.id == job_id_int).first()
            if not job:
                return {"status": "not_found"}

            return {
                "status": job.status,
                "output_path": job.output_path
            }
        except ValueError:
            return {"status": "invalid_id"}

    @app.get("/api/anime/scenes")
    async def get_all_scenes(db: Session = Depends(get_db)):
        """Get all scenes across all projects"""

        query = text("""
            SELECT
                s.id,
                s.episode_id,
                s.project_id,
                s.scene_number,
                s.title,
                s.description,
                s.visual_description,
                s.prompt,
                s.frame_count,
                s.fps,
                s.status,
                s.created_at
            FROM scenes s
            ORDER BY s.episode_id, s.scene_number
        """)

        result = db.execute(query)
        scenes = []
        for row in result:
            scene_dict = dict(row)
            scenes.append(scene_dict)

        return scenes

    @app.post("/api/anime/scenes/{scene_id}/generate")
    async def generate_scene(scene_id: int, db: Session = Depends(get_db)):
        """Generate video for a specific scene"""

        # Import here to avoid circular import
        from .main import generate_with_fixed_animatediff_workflow

        # Get scene details
        query = text("""
            SELECT
                s.*,
                p.name as project_name,
                e.title as episode_title
            FROM scenes s
            LEFT JOIN projects p ON s.project_id = p.id
            LEFT JOIN episodes e ON s.episode_id = e.id
            WHERE s.id = :scene_id
            LIMIT 1
        """)

        result = db.execute(query, {"scene_id": scene_id}).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Scene not found")

        scene = dict(result)

        # Generate using the scene's prompt
        prompt = scene.get('prompt') or scene.get('description', '')

        # Get appropriate LoRA based on project
        lora_name = None
        if scene.get('project_id') == 24:  # Tokyo Debt Desire
            # Check which character this scene features
            if "mei" in prompt.lower() or "kobayashi" in prompt.lower():
                lora_name = "mei_working_v1.safetensors"

        # Generate the video
        try:
            generation_result = await generate_with_fixed_animatediff_workflow(
                prompt=prompt,
                generation_type="video",
                lora_name=lora_name
            )

            # Update scene status
            update_query = text("""
                UPDATE scenes
                SET status = 'generating'
                WHERE id = :scene_id
            """)

            db.execute(update_query, {"scene_id": scene_id})
            db.commit()

            # Store job in production_jobs
            from .models import ProductionJob
            job = ProductionJob(
                project_id=scene['project_id'],
                job_type="scene_generation",
                prompt=prompt,
                parameters=json.dumps({
                    "scene_id": scene_id,
                    "frame_count": scene.get('frame_count', 24),
                    "fps": scene.get('fps', 24)
                }),
                status="processing",
                output_path=generation_result.get('output_path')
            )
            db.add(job)
            db.commit()

            return {
                "job_id": generation_result.get('prompt_id'),
                "scene_id": scene_id,
                "status": "generating"
            }

        except Exception as e:
            logger.error(f"Failed to generate scene {scene_id}: {e}")

            # Update scene status to failed
            update_query = text("""
                UPDATE scenes
                SET status = 'failed'
                WHERE id = :scene_id
            """)
            db.execute(update_query, {"scene_id": scene_id})
            db.commit()

            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/anime/scenes/reorder")
    async def reorder_scenes(request: dict, db: Session = Depends(get_db)):
        """Reorder scenes within an episode"""

        scenes = request.get('scenes', [])

        for scene in scenes:
            update_query = text("""
                UPDATE scenes
                SET scene_number = :scene_number
                WHERE id = :scene_id
            """)

            db.execute(update_query, {
                "scene_id": scene['id'],
                "scene_number": scene['scene_number']
            })

        db.commit()
        return {"message": "Scenes reordered successfully"}

    @app.post("/api/anime/episodes/{episode_id}/generate-all")
    async def generate_all_episode_scenes(episode_id: int, db: Session = Depends(get_db)):
        """Generate all scenes in an episode"""

        # Get all scenes for this episode
        query = text("""
            SELECT id, scene_number, prompt, description
            FROM scenes
            WHERE episode_id = :episode_id
            AND status != 'completed'
            ORDER BY scene_number
        """)

        result = db.execute(query, {"episode_id": episode_id})
        scenes = [dict(row) for row in result]

        if not scenes:
            return {
                "episode_id": episode_id,
                "message": "No scenes to generate or all scenes already completed",
                "scenes_queued": 0
            }

        job_ids = []
        for scene in scenes:
            try:
                # Generate each scene
                result = await generate_scene(scene['id'], db)
                job_ids.append(result['job_id'])

                # Add small delay between submissions to avoid overwhelming ComfyUI
                import asyncio
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Failed to queue scene {scene['id']}: {e}")

        return {
            "episode_id": episode_id,
            "scenes_queued": len(job_ids),
            "job_ids": job_ids,
            "message": f"Queued {len(job_ids)} scenes for generation"
        }

    @app.get("/api/anime/episodes/{project_id}/scenes")
    async def get_episode_scenes(project_id: int, db: Session = Depends(get_db)):
        """Get all scenes for episodes in a project"""

        query = text("""
            SELECT
                s.id,
                s.episode_id,
                s.scene_number,
                s.title,
                s.description,
                s.prompt,
                s.status,
                s.frame_count,
                s.fps,
                e.episode_number,
                e.title as episode_title
            FROM scenes s
            JOIN episodes e ON s.episode_id = e.id
            WHERE e.project_id = :project_id
            ORDER BY e.episode_number, s.scene_number
        """)

        result = db.execute(query, {"project_id": project_id})
        scenes = []
        for row in result:
            scenes.append(dict(row))

        return {"scenes": scenes}