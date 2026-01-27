"""
Real database endpoints for anime production
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

DATABASE_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': 'RP78eIrW7cI2jYvL5akt1yurE'
}

def get_db_connection():
    """Get database connection to anime_production"""
    return psycopg2.connect(**DATABASE_CONFIG)

async def get_all_projects() -> List[Dict]:
    """Get all projects from database"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, name, description, status, created_at,
               metadata->>'genre' as genre,
               metadata->>'target_audience' as target_audience
        FROM projects
        ORDER BY created_at DESC
    """)

    projects = cur.fetchall()
    conn.close()

    return {"projects": [dict(p) for p in projects]}

async def get_all_characters() -> List[Dict]:
    """Get all characters from database"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT c.id, c.name, c.description, c.lora_trigger, c.lora_path,
               p.name as project_name
        FROM characters c
        LEFT JOIN projects p ON c.project_id = p.id
        ORDER BY c.name
    """)

    characters = cur.fetchall()
    conn.close()

    return {"characters": [dict(c) for c in characters]}

async def get_all_episodes() -> List[Dict]:
    """Get all episodes from database"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT e.id, e.episode_number, e.title, e.description, e.status,
               p.name as project_name, p.id as project_id
        FROM episodes e
        JOIN projects p ON e.project_id = p.id
        ORDER BY p.name, e.episode_number
    """)

    episodes = cur.fetchall()
    conn.close()

    return {"episodes": [dict(e) for e in episodes]}

async def get_project_episodes(project_id: int) -> List[Dict]:
    """Get episodes for a specific project"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT e.id, e.episode_number, e.title, e.description, e.status,
               COUNT(s.id) as scene_count
        FROM episodes e
        LEFT JOIN scenes s ON s.episode_id = e.id
        WHERE e.project_id = %s
        GROUP BY e.id
        ORDER BY e.episode_number
    """, (project_id,))

    episodes = cur.fetchall()
    conn.close()

    return {"episodes": [dict(e) for e in episodes]}

async def get_episode_scenes(episode_id: str) -> List[Dict]:
    """Get scenes for a specific episode"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT s.id, s.scene_number, s.title, s.description,
               s.visual_description, s.prompt, s.parameters,
               array_agg(c.name) as characters
        FROM scenes s
        LEFT JOIN LATERAL unnest(s.characters_present) AS char_id ON true
        LEFT JOIN characters c ON c.id = char_id
        WHERE s.episode_id = %s::uuid
        GROUP BY s.id
        ORDER BY s.scene_number
    """, (episode_id,))

    scenes = cur.fetchall()
    conn.close()

    return {"scenes": [dict(s) for s in scenes]}

async def get_all_scenes(limit: int = 100) -> List[Dict]:
    """Get all scenes with limit"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT s.id, s.scene_number, s.title, s.description,
               e.title as episode_title, e.episode_number,
               p.name as project_name
        FROM scenes s
        JOIN episodes e ON s.episode_id = e.id
        JOIN projects p ON e.project_id = p.id
        ORDER BY p.name, e.episode_number, s.scene_number
        LIMIT %s
    """, (limit,))

    scenes = cur.fetchall()
    conn.close()

    return [dict(s) for s in scenes]

async def get_scene_details(scene_id: str) -> Optional[Dict]:
    """Get detailed scene information with characters"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT s.*,
               e.title as episode_title, e.episode_number,
               p.name as project_name,
               array_agg(
                   json_build_object(
                       'id', c.id,
                       'name', c.name,
                       'lora_trigger', c.lora_trigger,
                       'lora_path', c.lora_path
                   )
               ) FILTER (WHERE c.id IS NOT NULL) as characters
        FROM scenes s
        JOIN episodes e ON s.episode_id = e.id
        JOIN projects p ON e.project_id = p.id
        LEFT JOIN LATERAL unnest(s.characters_present) AS char_id ON true
        LEFT JOIN characters c ON c.id = char_id
        WHERE s.id = %s::uuid
        GROUP BY s.id, e.title, e.episode_number, p.name
    """, (scene_id,))

    scene = cur.fetchone()
    conn.close()

    return dict(scene) if scene else None