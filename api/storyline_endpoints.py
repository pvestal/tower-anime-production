"""Storyline Management API Endpoints"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import asyncpg
from datetime import datetime
import json
import uuid

router = APIRouter()

class StorylineCreate(BaseModel):
    project_id: int
    title: str
    summary: str
    genre: str = "Anime Adventure"
    theme: str = ""
    target_audience: str = "All Ages"
    status: str = "active"
    episodes: List[str] = []
    style_guidelines: Optional[Dict] = None

class StorylineUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    episodes: Optional[List[str]] = None
    status: Optional[str] = None

async def get_db_connection():
    return await asyncpg.connect(
        host="localhost",
        database="anime_production",
        user="patrick",
        password="RP78eIrW7cI2jYvL5akt1yurE"
    )

@router.get("/api/anime/storylines")
async def get_storylines(project_id: Optional[int] = None):
    """Get storylines for a project or all storylines"""
    conn = await get_db_connection()
    try:
        if project_id:
            query = """
                SELECT id, project_id, title, summary, episodes,
                       style_guidelines, theme, genre, target_audience, status
                FROM storylines
                WHERE project_id = $1
                ORDER BY created_at DESC
            """
            rows = await conn.fetch(query, project_id)
        else:
            query = """
                SELECT id, project_id, title, summary, episodes,
                       style_guidelines, theme, genre, target_audience, status
                FROM storylines
                ORDER BY created_at DESC
            """
            rows = await conn.fetch(query)

        storylines = []
        for row in rows:
            storylines.append({
                "id": row['id'],
                "project_id": row['project_id'],
                "title": row['title'],
                "summary": row['summary'],
                "episodes": row['episodes'] or [],
                "style_guidelines": row['style_guidelines'] or {},
                "theme": row['theme'],
                "genre": row['genre'],
                "target_audience": row['target_audience'],
                "status": row['status']
            })

        return {"storylines": storylines}
    finally:
        await conn.close()

@router.post("/api/anime/storylines")
async def create_storyline(storyline: StorylineCreate):
    """Create a new storyline"""
    conn = await get_db_connection()
    try:
        # Ensure table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS storylines (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                title TEXT NOT NULL,
                summary TEXT,
                episodes TEXT[],
                style_guidelines JSONB,
                theme TEXT,
                genre TEXT,
                target_audience TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Insert storyline
        storyline_id = await conn.fetchval("""
            INSERT INTO storylines (
                project_id, title, summary, episodes, style_guidelines,
                theme, genre, target_audience, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, storyline.project_id, storyline.title, storyline.summary,
            storyline.episodes, json.dumps(storyline.style_guidelines or {}),
            storyline.theme, storyline.genre, storyline.target_audience,
            storyline.status)

        return {
            "id": storyline_id,
            "status": "created",
            "message": f"Storyline '{storyline.title}' created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.put("/api/anime/storylines/{storyline_id}")
async def update_storyline(storyline_id: int, update: StorylineUpdate):
    """Update a storyline"""
    conn = await get_db_connection()
    try:
        # Build dynamic update query
        update_fields = []
        values = []
        param_count = 1

        if update.title is not None:
            update_fields.append(f"title = ${param_count}")
            values.append(update.title)
            param_count += 1

        if update.summary is not None:
            update_fields.append(f"summary = ${param_count}")
            values.append(update.summary)
            param_count += 1

        if update.episodes is not None:
            update_fields.append(f"episodes = ${param_count}")
            values.append(update.episodes)
            param_count += 1

        if update.status is not None:
            update_fields.append(f"status = ${param_count}")
            values.append(update.status)
            param_count += 1

        if not update_fields:
            return {"status": "no_changes"}

        # Add storyline_id to values
        values.append(storyline_id)

        query = f"""
            UPDATE storylines
            SET {', '.join(update_fields)}
            WHERE id = ${param_count}
        """

        await conn.execute(query, *values)
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.get("/api/anime/characters")
async def get_characters(project_id: Optional[int] = None):
    """Get characters for a project"""
    conn = await get_db_connection()
    try:
        if project_id:
            query = """
                SELECT id, name, design_prompt, personality, role,
                       lora_trigger, lora_path, appearance_data
                FROM characters
                WHERE project_id = $1
                ORDER BY name
            """
            rows = await conn.fetch(query, project_id)
        else:
            query = """
                SELECT id, name, design_prompt, personality, role,
                       lora_trigger, lora_path, appearance_data
                FROM characters
                ORDER BY name
                LIMIT 20
            """
            rows = await conn.fetch(query)

        characters = []
        for row in rows:
            characters.append({
                "id": row['id'],
                "name": row['name'],
                "design_prompt": row['design_prompt'],
                "personality": row['personality'],
                "role": row['role'],
                "lora_trigger": row['lora_trigger'],
                "lora_path": row['lora_path'],
                "appearance_data": row['appearance_data']
            })

        return {"characters": characters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.get("/api/anime/approvals/{project_id}/{character}")
async def get_character_approvals(project_id: int, character: str):
    """Get approval counts for a character"""
    conn = await get_db_connection()
    try:
        result = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE approved = true) as approved_count,
                COUNT(*) FILTER (WHERE approved = false) as rejected_count,
                COUNT(*) FILTER (WHERE approved IS NULL) as pending_count
            FROM character_approvals
            WHERE project_id = $1 AND character_name = $2
        """, project_id, character)

        return {
            "approved_count": result['approved_count'] or 0,
            "rejected_count": result['rejected_count'] or 0,
            "pending_count": result['pending_count'] or 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.get("/api/anime/episodes/{episode_id}")
async def get_episode(episode_id: str):
    """Get a single episode by ID"""
    conn = await get_db_connection()
    try:
        # Handle both UUID and integer IDs
        try:
            episode_uuid = uuid.UUID(episode_id)
            query = """
                SELECT id, title, description, project_id, status, episode_number
                FROM episodes
                WHERE id = $1
            """
            row = await conn.fetchrow(query, episode_uuid)
        except ValueError:
            # Not a UUID, try as integer
            query = """
                SELECT id, title, description, project_id, status, episode_number
                FROM episodes
                WHERE id::text = $1
            """
            row = await conn.fetchrow(query, str(episode_id))

        if not row:
            raise HTTPException(status_code=404, detail="Episode not found")

        # Get scene count
        scene_count = await conn.fetchval("""
            SELECT COUNT(*) FROM episode_scenes WHERE episode_id = $1
        """, row['id'])

        return {
            "id": str(row['id']),
            "title": row['title'],
            "description": row['description'],
            "project_id": row['project_id'],
            "status": row['status'],
            "episode_number": row['episode_number'],
            "scene_count": scene_count
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.post("/api/anime/episodes")
async def create_episode(episode: dict):
    """Create a new episode"""
    conn = await get_db_connection()
    try:
        episode_id = await conn.fetchval("""
            INSERT INTO episodes (project_id, title, description, status, episode_number)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """, episode.get('project_id'), episode.get('title'),
            episode.get('description'), episode.get('status', 'planning'),
            episode.get('episode_number', 1))

        return {
            "id": str(episode_id),
            "status": "created",
            "message": f"Episode '{episode.get('title')}' created"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.post("/api/anime/lora/train")
async def start_lora_training(request: dict):
    """Start LoRA training for a character"""
    import subprocess
    import asyncio

    project_id = request.get('project_id')
    character_name = request.get('character_name')
    base_model = request.get('base_model', 'realisticVision_v51.safetensors')

    # Check if quality gate is met
    conn = await get_db_connection()
    try:
        approved_count = await conn.fetchval("""
            SELECT COUNT(*) FROM character_approvals
            WHERE project_id = $1 AND character_name = $2 AND approved = true
        """, project_id, character_name)

        # Get quality gate requirement
        project_name = await conn.fetchval("""
            SELECT name FROM projects WHERE id = $1
        """, project_id)

        # Check against quality gates (hardcoded for now)
        quality_gates = {
            'Super Mario Galaxy Anime Adventure': 15,
            'Tokyo Debt Desire': 12,
            'Cyberpunk Goblin Slayer': 10
        }

        required = quality_gates.get(project_name, 10)
        if approved_count < required:
            raise HTTPException(
                status_code=400,
                detail=f"Quality gate not met. Need {required} approved images, have {approved_count}"
            )

        # Start training process
        training_id = f"lora_{character_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Launch training in background
        dataset_path = f"/mnt/1TB-storage/lora_datasets/{character_name}/images"
        cmd = [
            "/opt/tower-lora-studio/venv/bin/python",
            "/opt/tower-lora-studio/train_character.py",
            "--character_name", character_name,
            "--dataset_path", dataset_path,
            "--project_id", str(project_id),
            "--training_steps", "1500",
            "--output_name", training_id
        ]

        # Start process in background
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        return {
            "training_id": training_id,
            "status": "started",
            "message": f"LoRA training started for {character_name}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

@router.post("/api/anime/generate/character")
async def generate_character_images(request: dict):
    """Generate images for a character"""
    # This would integrate with ComfyUI or your image generation pipeline
    project_id = request.get('project_id')
    character_name = request.get('character_name')
    count = request.get('count', 20)
    style = request.get('style')
    model = request.get('model')

    generation_id = f"gen_{character_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # In production, this would trigger actual generation
    # For now, return a mock response
    return {
        "generation_id": generation_id,
        "status": "queued",
        "message": f"Generating {count} images for {character_name}",
        "style": style,
        "model": model
    }