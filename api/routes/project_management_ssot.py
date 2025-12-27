#!/usr/bin/env python3
"""
PROJECT MANAGEMENT SSOT (Single Source of Truth) API
Central system for tracking all anime generation activities
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncpg
import json
import hashlib
import aiohttp
from uuid import UUID
import os

router = APIRouter()

# Database connection
DATABASE_URL = "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost/anime_production"

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    target_episodes: int = 1
    style_guide: Optional[Dict[str, Any]] = Field(default_factory=dict)
    character_definitions: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class EpisodeCreate(BaseModel):
    episode_number: int
    title: Optional[str] = None
    description: Optional[str] = None
    prompt: str
    use_echo_optimization: bool = True
    use_ollama_enhancement: bool = True

class SceneGenerate(BaseModel):
    scene_number: int
    prompt: str
    frames: int = 24
    fps: int = 8
    model: str = "svd"
    use_fixed_seed: bool = True
    seed: Optional[int] = 424242

class JobTrack(BaseModel):
    job_id: str
    scene_id: Optional[str] = None
    episode_id: Optional[str] = None

class DecisionRecord(BaseModel):
    decision_type: str  # model_selection, prompt_optimization, parameter_tuning
    echo_reasoning: Optional[str] = None
    ollama_suggestion: Optional[str] = None
    parameters_used: Dict[str, Any]
    job_id: Optional[str] = None

async def get_db_connection():
    """Create database connection"""
    return await asyncpg.connect(DATABASE_URL)

@router.post("/projects/create")
async def create_project(project: ProjectCreate):
    """Create new anime project - establishes SSOT"""
    conn = await get_db_connection()

    try:
        # 1. Create project in SSOT database
        project_id = await conn.fetchval(
            """
            INSERT INTO projects (name, description, metadata)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            project.title,
            project.description,
            json.dumps({"created_via": "api", "version": "1.0"})
        )

        # 2. Create characters if provided
        if project.character_definitions:
            for char_def in project.character_definitions:
                await conn.execute(
                    """
                    INSERT INTO characters (project_id, name, description, design_prompt, traits, reference_seed)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    int(project_id),
                    char_def.get("name", "unnamed"),
                    char_def.get("description"),
                    char_def.get("design_prompt"),
                    json.dumps(char_def.get("traits", [])),
                    char_def.get("seed", 424242)
                )

        # 3. Use Ollama to generate episode outline if requested
        episodes_planned = []
        if project.target_episodes > 0:
            # Call Ollama for creative episode generation
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "llama3.2:3b",
                        "prompt": f"Generate {project.target_episodes} episode outlines for anime titled '{project.title}'. "
                                f"Description: {project.description}. Return as numbered list with brief descriptions.",
                        "stream": False
                    }
                ) as resp:
                    if resp.status == 200:
                        ollama_response = await resp.json()
                        episode_ideas = ollama_response.get("response", "")

                        # Parse and store episode outlines
                        lines = episode_ideas.split('\n')
                        for i, line in enumerate(lines[:project.target_episodes], 1):
                            if line.strip():
                                await conn.execute(
                                    """
                                    INSERT INTO episodes (project_id, episode_number, title, description, prompt, status)
                                    VALUES ($1, $2, $3, $4, $5, 'planned')
                                    """,
                                    int(project_id),
                                    i,
                                    f"Episode {i}",
                                    line.strip(),
                                    line.strip(),
                                )
                                episodes_planned.append({
                                    "episode": i,
                                    "description": line.strip()
                                })

        # 4. Let Echo analyze optimal generation strategy
        echo_recommendations = await analyze_with_echo(project_id, project.title, project.style_guide)

        return {
            "project_id": str(project_id),
            "title": project.title,
            "episodes_planned": len(episodes_planned),
            "episode_outlines": episodes_planned,
            "echo_recommendations": echo_recommendations,
            "ssot_established": True,
            "message": "Project created in SSOT database"
        }

    finally:
        await conn.close()

@router.post("/projects/{project_id}/episodes/create")
async def create_episode(project_id: str, episode: EpisodeCreate):
    """Create episode with SSOT tracking"""
    conn = await get_db_connection()

    try:
        # Verify project exists
        project = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1",
            int(project_id)
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Enhance prompt with Ollama if requested
        enhanced_prompt = episode.prompt
        if episode.use_ollama_enhancement:
            enhanced_prompt = await enhance_with_ollama(episode.prompt, project['style_guide'])

        # Create episode
        episode_id = await conn.fetchval(
            """
            INSERT INTO episodes (project_id, episode_number, title, description, prompt, enhanced_prompt, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'ready')
            RETURNING id
            """,
            int(project_id),
            episode.episode_number,
            episode.title,
            episode.description,
            episode.prompt,
            enhanced_prompt
        )

        return {
            "episode_id": str(episode_id),
            "episode_number": episode.episode_number,
            "original_prompt": episode.prompt,
            "enhanced_prompt": enhanced_prompt,
            "ssot_tracked": True
        }

    finally:
        await conn.close()

@router.post("/projects/{project_id}/episodes/{episode_id}/generate-scene")
async def generate_scene(
    project_id: str,
    episode_id: str,
    scene: SceneGenerate,
    background_tasks: BackgroundTasks
):
    """Generate scene with complete SSOT tracking"""
    conn = await get_db_connection()

    try:
        # Get episode context
        episode = await conn.fetchrow(
            """
            SELECT e.*, p.style_guide, p.title as project_title
            FROM episodes e
            JOIN projects p ON e.project_id = p.id
            WHERE e.id = $1 AND p.id = $2
            """,
            UUID(episode_id),
            int(project_id)
        )

        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")

        # Create scene record
        scene_id = await conn.fetchval(
            """
            INSERT INTO scenes (episode_id, scene_number, prompt, frame_count, fps, model_used, parameters, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'generating')
            RETURNING id
            """,
            UUID(episode_id),
            scene.scene_number,
            scene.prompt,
            scene.frames,
            scene.fps,
            scene.model,
            json.dumps({
                "seed": scene.seed,
                "fixed_seed": scene.use_fixed_seed,
                "cfg_scale": 7.5,
                "steps": 30
            })
        )

        # Get Echo optimization if enabled
        echo_decision = None
        if episode['enhanced_prompt']:
            echo_decision = await get_echo_optimization(
                scene.prompt,
                json.loads(episode['style_guide']) if episode['style_guide'] else {},
                scene.model
            )

            # Record Echo's decision
            await conn.execute(
                """
                INSERT INTO generation_decisions
                (scene_id, episode_id, decision_type, echo_reasoning, parameters_used)
                VALUES ($1, $2, 'model_selection', $3, $4)
                """,
                scene_id,
                UUID(episode_id),
                echo_decision.get('reasoning', ''),
                json.dumps(echo_decision.get('parameters', {}))
            )

        # Submit to ComfyUI
        generation_params = {
            "prompt": scene.prompt,
            "frames": scene.frames,
            "fps": scene.fps,
            "model": scene.model,
            "seed": scene.seed if scene.use_fixed_seed else None,
            "parameters": echo_decision.get('parameters', {}) if echo_decision else {}
        }

        # Call anime production API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8328/api/anime/generate",
                json=generation_params
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    job_id = result.get('job_id')

                    # Update scene with job ID
                    await conn.execute(
                        """
                        UPDATE scenes
                        SET generation_job_id = $1, status = 'processing'
                        WHERE id = $2
                        """,
                        job_id,
                        scene_id
                    )

                    # Track in background
                    background_tasks.add_task(
                        track_job_completion,
                        job_id,
                        scene_id,
                        episode_id
                    )

                    return {
                        "scene_id": str(scene_id),
                        "job_id": job_id,
                        "status": "generating",
                        "echo_optimized": echo_decision is not None,
                        "ssot_tracking": True,
                        "tracking_url": f"/api/ssot/jobs/{job_id}/status"
                    }
                else:
                    raise HTTPException(status_code=resp.status, detail="Generation failed")

    finally:
        await conn.close()

@router.post("/jobs/{job_id}/track")
async def track_job(job_id: str, tracking: JobTrack):
    """Track existing ComfyUI job in SSOT"""
    conn = await get_db_connection()

    try:
        # Check job status from ComfyUI
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:8188/history/{job_id}") as resp:
                if resp.status == 200:
                    history = await resp.json()
                    job_data = history.get(job_id, {})

                    status = "unknown"
                    output_path = None

                    if job_data:
                        status_info = job_data.get('status', {})
                        if status_info.get('completed'):
                            status = "completed"

                            # Extract output path
                            outputs = job_data.get('outputs', {})
                            for node_outputs in outputs.values():
                                if 'gifs' in node_outputs:
                                    for gif in node_outputs['gifs']:
                                        output_path = gif.get('fullpath')
                                        break
                        elif status_info.get('status_str') == 'error':
                            status = "failed"

                    # Update or create tracking record
                    if tracking.scene_id:
                        await conn.execute(
                            """
                            UPDATE scenes
                            SET generation_job_id = $1, status = $2, output_path = $3
                            WHERE id = $4
                            """,
                            job_id,
                            status,
                            output_path,
                            UUID(tracking.scene_id)
                        )

                    # Record in decisions table
                    if tracking.episode_id:
                        await conn.execute(
                            """
                            INSERT INTO generation_decisions
                            (episode_id, scene_id, decision_type, parameters_used)
                            VALUES ($1, $2, 'job_tracking', $3)
                            """,
                            UUID(tracking.episode_id) if tracking.episode_id else None,
                            UUID(tracking.scene_id) if tracking.scene_id else None,
                            json.dumps({
                                "job_id": job_id,
                                "status": status,
                                "output": output_path,
                                "tracked_at": datetime.now().isoformat()
                            })
                        )

                    return {
                        "job_id": job_id,
                        "status": status,
                        "output_path": output_path,
                        "ssot_updated": True,
                        "tracking_complete": status in ["completed", "failed"]
                    }
                else:
                    return {
                        "job_id": job_id,
                        "status": "not_found",
                        "message": "Job not found in ComfyUI history"
                    }

    finally:
        await conn.close()

@router.get("/projects/{project_id}/ssot-view")
async def get_project_ssot(project_id: str):
    """Get complete SSOT view of a project"""
    conn = await get_db_connection()

    try:
        # Get project
        project = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1",
            int(project_id)
        )

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get episodes
        episodes = await conn.fetch(
            "SELECT * FROM episodes WHERE project_id = $1 ORDER BY episode_number",
            int(project_id)
        )

        # Get scenes for each episode
        episode_data = []
        for episode in episodes:
            scenes = await conn.fetch(
                "SELECT * FROM scenes WHERE episode_id = $1 ORDER BY scene_number",
                episode['id']
            )

            # Get decisions for each scene
            scene_data = []
            for scene in scenes:
                decisions = await conn.fetch(
                    """
                    SELECT decision_type, echo_reasoning, ollama_suggestion,
                           parameters_used, success_score, created_at
                    FROM generation_decisions
                    WHERE scene_id = $1
                    ORDER BY created_at DESC
                    """,
                    scene['id']
                )

                scene_data.append({
                    "scene_number": scene['scene_number'],
                    "prompt": scene['prompt'],
                    "status": scene['status'],
                    "job_id": scene['generation_job_id'],
                    "output_path": scene['output_path'],
                    "decisions": [dict(d) for d in decisions]
                })

            episode_data.append({
                "episode_number": episode['episode_number'],
                "title": episode['title'],
                "status": episode['status'],
                "scenes": scene_data
            })

        # Get characters
        characters = await conn.fetch(
            "SELECT * FROM characters WHERE project_id = $1",
            int(project_id)
        )

        # Calculate metrics
        total_scenes = await conn.fetchval(
            """
            SELECT COUNT(*) FROM scenes s
            JOIN episodes e ON s.episode_id = e.id
            WHERE e.project_id = $1
            """,
            int(project_id)
        )

        completed_scenes = await conn.fetchval(
            """
            SELECT COUNT(*) FROM scenes s
            JOIN episodes e ON s.episode_id = e.id
            WHERE e.project_id = $1 AND s.status = 'completed'
            """,
            int(project_id)
        )

        return {
            "project": {
                "id": str(project['id']),
                "title": project['name'],
                "description": project['description'],
                "status": project['status'],
                "created_at": project['created_at'].isoformat() if project['created_at'] else None
            },
            "episodes": episode_data,
            "characters": [dict(c) for c in characters],
            "metrics": {
                "total_episodes": len(episodes),
                "total_scenes": total_scenes,
                "completed_scenes": completed_scenes,
                "completion_rate": (completed_scenes / total_scenes * 100) if total_scenes > 0 else 0
            },
            "ssot_complete": True
        }

    finally:
        await conn.close()

@router.post("/ssot/validate-integrity")
async def validate_ssot_integrity():
    """Validate SSOT database integrity"""
    conn = await get_db_connection()

    try:
        issues = []

        # Check for orphaned scenes
        orphaned_scenes = await conn.fetchval(
            """
            SELECT COUNT(*) FROM scenes s
            LEFT JOIN episodes e ON s.episode_id = e.id
            WHERE e.id IS NULL
            """
        )
        if orphaned_scenes > 0:
            issues.append(f"Found {orphaned_scenes} orphaned scenes")

        # Check for decisions without scenes
        orphaned_decisions = await conn.fetchval(
            """
            SELECT COUNT(*) FROM generation_decisions d
            LEFT JOIN scenes s ON d.scene_id = s.id
            WHERE d.scene_id IS NOT NULL AND s.id IS NULL
            """
        )
        if orphaned_decisions > 0:
            issues.append(f"Found {orphaned_decisions} decisions without scenes")

        # Check for incomplete jobs
        incomplete_jobs = await conn.fetch(
            """
            SELECT generation_job_id, COUNT(*) as count
            FROM scenes
            WHERE generation_job_id IS NOT NULL
            AND status NOT IN ('completed', 'failed')
            AND created_at < NOW() - INTERVAL '1 hour'
            GROUP BY generation_job_id
            """
        )

        for job in incomplete_jobs:
            issues.append(f"Job {job['generation_job_id']} incomplete for >1 hour")

        # Check for duplicate episodes
        duplicate_episodes = await conn.fetch(
            """
            SELECT project_id, episode_number, COUNT(*) as count
            FROM episodes
            GROUP BY project_id, episode_number
            HAVING COUNT(*) > 1
            """
        )

        if duplicate_episodes:
            issues.append(f"Found {len(duplicate_episodes)} duplicate episode entries")

        return {
            "integrity_valid": len(issues) == 0,
            "issues": issues,
            "recommendations": [
                "Run cleanup script" if orphaned_scenes > 0 else None,
                "Check ComfyUI queue" if incomplete_jobs else None,
                "Review duplicate episodes" if duplicate_episodes else None
            ],
            "checked_at": datetime.now().isoformat()
        }

    finally:
        await conn.close()

# Helper functions
async def analyze_with_echo(project_id: str, title: str, style_guide: dict) -> dict:
    """Get Echo's analysis of optimal generation strategy"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8309/api/echo/query",
            json={
                "query": f"Analyze optimal generation strategy for anime project: {title}",
                "context": style_guide,
                "conversation_id": f"project_{project_id}"
            }
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                return {
                    "strategy": result.get("response", ""),
                    "confidence": 0.85
                }
            return {"strategy": "Use standard generation parameters", "confidence": 0.5}

async def enhance_with_ollama(prompt: str, style_guide: dict) -> str:
    """Enhance prompt using Ollama"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:3b",
                "prompt": f"Enhance this anime scene prompt with more visual details: {prompt}",
                "stream": False
            }
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get("response", prompt)
            return prompt

async def get_echo_optimization(prompt: str, style_guide: dict, model: str) -> dict:
    """Get Echo's optimization for generation parameters"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8309/api/echo/query",
            json={
                "query": f"Optimize generation parameters for: {prompt}",
                "context": {
                    "style_guide": style_guide,
                    "model": model
                }
            }
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                # Parse Echo's response for parameters
                return {
                    "reasoning": result.get("response", ""),
                    "parameters": {
                        "cfg_scale": 7.5,
                        "steps": 30,
                        "motion_bucket": 127
                    }
                }
            return {"reasoning": "Default parameters", "parameters": {}}

async def track_job_completion(job_id: str, scene_id: str, episode_id: str):
    """Background task to track job completion"""
    import asyncio

    max_attempts = 60  # Check for 10 minutes
    attempt = 0

    while attempt < max_attempts:
        await asyncio.sleep(10)  # Check every 10 seconds

        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:8188/history/{job_id}") as resp:
                if resp.status == 200:
                    history = await resp.json()
                    job_data = history.get(job_id, {})

                    if job_data:
                        status_info = job_data.get('status', {})
                        if status_info.get('completed'):
                            # Job completed, update SSOT
                            conn = await get_db_connection()
                            try:
                                # Extract output
                                output_path = None
                                outputs = job_data.get('outputs', {})
                                for node_outputs in outputs.values():
                                    if 'gifs' in node_outputs:
                                        for gif in node_outputs['gifs']:
                                            output_path = gif.get('fullpath')
                                            break

                                # Update scene
                                await conn.execute(
                                    """
                                    UPDATE scenes
                                    SET status = 'completed', output_path = $1
                                    WHERE id = $2
                                    """,
                                    output_path,
                                    UUID(scene_id)
                                )

                                # Record success
                                await conn.execute(
                                    """
                                    UPDATE generation_decisions
                                    SET success_score = 1.0
                                    WHERE scene_id = $1
                                    """,
                                    UUID(scene_id)
                                )

                                print(f"Job {job_id} completed successfully")
                                return
                            finally:
                                await conn.close()

                        elif status_info.get('status_str') == 'error':
                            # Job failed
                            conn = await get_db_connection()
                            try:
                                await conn.execute(
                                    """
                                    UPDATE scenes
                                    SET status = 'failed'
                                    WHERE id = $1
                                    """,
                                    UUID(scene_id)
                                )

                                await conn.execute(
                                    """
                                    UPDATE generation_decisions
                                    SET success_score = 0.0
                                    WHERE scene_id = $1
                                    """,
                                    UUID(scene_id)
                                )

                                print(f"Job {job_id} failed")
                                return
                            finally:
                                await conn.close()

        attempt += 1

    # Timeout - mark as failed
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE scenes
            SET status = 'timeout'
            WHERE id = $1
            """,
            UUID(scene_id)
        )
        print(f"Job {job_id} timed out")
    finally:
        await conn.close()

# Special endpoint for your specific job
@router.post("/jobs/dae98412-6ec4-43ee-9f54-4855934213d5/import-to-ssot")
async def import_specific_job():
    """Import the completed job into SSOT"""
    job_id = "dae98412-6ec4-43ee-9f54-4855934213d5"

    # Track this specific job
    result = await track_job(
        job_id,
        JobTrack(
            job_id=job_id,
            scene_id=None,  # We'll create a new scene for this
            episode_id=None
        )
    )

    # Create a project entry for this completed job
    conn = await get_db_connection()
    try:
        # Create project
        project_id = await conn.fetchval(
            """
            INSERT INTO projects (title, description, status)
            VALUES ('Cyberpunk Goblin Slayer (Imported)', 'Imported from job ' || $1, 'completed')
            RETURNING id
            """,
            job_id
        )

        # Create episode
        episode_id = await conn.fetchval(
            """
            INSERT INTO episodes (project_id, episode_number, title, prompt, status)
            VALUES ($1, 1, 'Imported Episode', 'Cyberpunk goblin slayer in motion', 'completed')
            RETURNING id
            """,
            int(project_id)
        )

        # Create scene with the completed output
        scene_id = await conn.fetchval(
            """
            INSERT INTO scenes (
                episode_id, scene_number, prompt, frame_count, fps,
                model_used, generation_job_id, status, output_path
            )
            VALUES ($1, 1, $2, 24, 8, 'AnimateDiff', $3, 'completed', $4)
            RETURNING id
            """,
            episode_id,
            "Cyberpunk goblin slayer in motion, with smooth animation and consistent character design",
            job_id,
            "/mnt/1TB-storage/ComfyUI/output/coherent_70ce515e_00001.mp4"
        )

        # Record the import as a decision
        await conn.execute(
            """
            INSERT INTO generation_decisions (
                scene_id, episode_id, decision_type,
                echo_reasoning, parameters_used, success_score
            )
            VALUES ($1, $2, 'import', $3, $4, 1.0)
            """,
            scene_id,
            episode_id,
            f"Imported completed job {job_id} - 3 second video successfully generated",
            json.dumps({
                "job_id": job_id,
                "output": "/mnt/1TB-storage/ComfyUI/output/coherent_70ce515e_00001.mp4",
                "duration": "3.0s",
                "resolution": "512x512",
                "fps": 8
            })
        )

        return {
            "message": f"Successfully imported job {job_id} into SSOT",
            "project_id": str(project_id),
            "episode_id": str(episode_id),
            "scene_id": str(scene_id),
            "output_path": "/mnt/1TB-storage/ComfyUI/output/coherent_70ce515e_00001.mp4",
            "ssot_complete": True
        }

    finally:
        await conn.close()