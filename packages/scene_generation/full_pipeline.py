"""Full production pipeline — end-to-end episode production from shots to published video.

Chains: shot generation → auto-approve → voice synthesis → music gen →
audio mixing → scene assembly → episode assembly → optional Jellyfin publish.

Usage:
    POST /api/scenes/produce-episode?project_id=24&episode_number=1
    POST /api/scenes/produce-episode?project_id=24&episode_number=1&publish=true
    POST /api/scenes/text-to-episode  — unified "text prompt → episode" endpoint
"""

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from packages.core.db import connect_direct
from packages.core.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Unified Text-to-Episode ──────────────────────────────────────────────

class TextToEpisodeRequest(BaseModel):
    project_id: int
    episode_number: int = Field(1, description="Episode number to create")
    title: str = Field(..., description="Episode title")
    synopsis: str | None = Field(None, description="Episode synopsis/story arc (uses project storyline if omitted)")
    publish: bool = False


@router.post("/scenes/text-to-episode")
async def text_to_episode(body: TextToEpisodeRequest, background_tasks: BackgroundTasks):
    """Unified text prompt → episode pipeline.

    Chains the full production flow in one call:
    1. Create episode record
    2. Generate scenes + shots from story via Ollama
    3. Generate keyframes for all shots
    4. Generate videos for all shots
    5. Assemble scenes → assemble episode
    6. Optionally publish to Jellyfin

    Returns immediately with episode_id; generation runs in background.
    Poll GET /api/system/orchestrator/pipeline/{project_id} for progress,
    or GET /api/episodes/{episode_id} for final status.
    """
    conn = await connect_direct()
    try:
        # Validate project exists
        project = await conn.fetchrow(
            "SELECT id, name, storyline FROM projects WHERE id = $1",
            body.project_id,
        )
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {body.project_id} not found")

        # Check episode doesn't already exist
        existing = await conn.fetchrow(
            "SELECT id FROM episodes WHERE project_id = $1 AND episode_number = $2",
            body.project_id, body.episode_number,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Episode {body.episode_number} already exists (id={existing['id']}). "
                       f"Use POST /api/scenes/produce-episode to regenerate it.",
            )

        # Check characters have design_prompts
        char_count = await conn.fetchval(
            "SELECT COUNT(*) FROM characters WHERE project_id = $1 AND design_prompt IS NOT NULL AND TRIM(design_prompt) != ''",
            body.project_id,
        )
        if char_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No characters with design_prompt found. Add characters before generating an episode.",
            )

        # Step 1: Create episode
        synopsis = body.synopsis or project["storyline"] or body.title
        episode_id = await conn.fetchval(
            "INSERT INTO episodes (project_id, episode_number, title, description, story_arc, status) "
            "VALUES ($1, $2, $3, $4, $5, 'generating') RETURNING id",
            body.project_id, body.episode_number, body.title, synopsis, synopsis,
        )
        logger.info(
            f"text-to-episode: created episode {body.episode_number} "
            f"'{body.title}' for project {project['name']} (id={episode_id})"
        )

    finally:
        await conn.close()

    # Run the full pipeline in background
    background_tasks.add_task(
        _run_text_to_episode_pipeline,
        body.project_id, body.episode_number, str(episode_id), body.publish,
    )

    return {
        "status": "generating",
        "episode_id": str(episode_id),
        "episode_number": body.episode_number,
        "title": body.title,
        "project": project["name"],
        "characters_available": char_count,
        "message": f"Episode pipeline started. Poll GET /api/episodes/{episode_id} for status.",
    }


async def _run_text_to_episode_pipeline(
    project_id: int, episode_number: int, episode_id: str, publish: bool
):
    """Background task: generate scenes from story → produce episode."""
    ep_uuid = uuid.UUID(episode_id)

    try:
        # Step 2: Generate scenes + shots from story via Ollama
        logger.info(f"text-to-episode: generating scenes from story for ep{episode_number}")
        from .story_to_scenes import generate_scenes_from_story
        from .scene_crud import _persist_scenes_and_shots

        scenes_data = await generate_scenes_from_story(project_id, episode_id=episode_id)

        if not scenes_data:
            await _update_episode_status(ep_uuid, "failed", "Ollama returned no scenes")
            return

        # Persist scenes + shots + link to episode
        saved = await _persist_scenes_and_shots(project_id, scenes_data, episode_id=episode_id)

        scene_count = len(saved) if saved else 0
        logger.info(f"text-to-episode: {scene_count} scenes created with shots")

        if scene_count == 0:
            await _update_episode_status(ep_uuid, "failed", "No scenes were created")
            return

        # Step 3-6: Use the existing produce_episode pipeline
        # It handles: keyframes → videos → voice → music → assembly → publish
        logger.info(f"text-to-episode: starting produce-episode pipeline")

        # Import produce_episode logic and call it directly
        # We can't call the endpoint, so we replicate the core logic
        from .builder import generate_scene
        from packages.episode_assembly.builder import (
            assemble_episode as _assemble_episode,
            get_video_duration,
            extract_thumbnail,
            EPISODE_OUTPUT_DIR,
        )

        conn = await connect_direct()
        try:
            # Get scenes for this episode
            scene_rows = await conn.fetch("""
                SELECT s.id, s.title, s.scene_number, s.generation_status,
                       s.final_video_path,
                       (SELECT COUNT(*) FROM shots WHERE scene_id = s.id) as shot_count
                FROM scenes s
                JOIN episode_scenes es ON es.scene_id = s.id
                WHERE es.episode_id = $1
                ORDER BY es.position
            """, ep_uuid)

            # Reset all shots to pending
            for sr in scene_rows:
                await conn.execute(
                    "UPDATE shots SET status = 'pending', error_message = NULL "
                    "WHERE scene_id = $1 AND status NOT IN ('completed', 'accepted_best')",
                    sr["id"],
                )
        finally:
            await conn.close()

        # Generate each scene (includes keyframes + videos + voice + music)
        for sr in scene_rows:
            scene_id = str(sr["id"])
            logger.info(
                f"text-to-episode: generating scene '{sr['title']}' "
                f"({sr['shot_count']} shots)"
            )
            try:
                await generate_scene(scene_id, auto_approve=True)
            except Exception as e:
                logger.error(f"text-to-episode: scene '{sr['title']}' failed: {e}")

        # Assemble episode from completed scene videos
        conn = await connect_direct()
        try:
            final_scenes = await conn.fetch("""
                SELECT s.id, s.title, s.final_video_path
                FROM scenes s
                JOIN episode_scenes es ON es.scene_id = s.id
                WHERE es.episode_id = $1
                ORDER BY es.position
            """, ep_uuid)

            video_paths = []
            transitions = []
            for sr in final_scenes:
                vp = sr["final_video_path"]
                if vp and Path(vp).exists():
                    video_paths.append(vp)
                    transitions.append("fadeblack")

            if not video_paths:
                await _update_episode_status(ep_uuid, "failed", "No scene videos completed")
                return

            episode_path = await _assemble_episode(episode_id, video_paths, transitions)

            # Apply episode-level music
            try:
                from packages.episode_assembly.router import _apply_episode_music
                episode = await conn.fetchrow("SELECT story_arc FROM episodes WHERE id = $1", ep_uuid)
                episode_path = await _apply_episode_music(
                    conn, ep_uuid, episode_path, episode["story_arc"] if episode else None,
                )
            except Exception as e:
                logger.warning(f"text-to-episode: episode music failed (non-fatal): {e}")

            duration = await get_video_duration(episode_path)
            thumb_path = str(EPISODE_OUTPUT_DIR / f"episode_{episode_id}_thumb.jpg")
            await extract_thumbnail(episode_path, thumb_path)

            await conn.execute("""
                UPDATE episodes SET status = 'assembled', final_video_path = $2,
                       actual_duration_seconds = $3, thumbnail_path = $4, updated_at = NOW()
                WHERE id = $1
            """, ep_uuid, episode_path, duration,
                thumb_path if Path(thumb_path).exists() else None)

            logger.info(
                f"text-to-episode: ep{episode_number} assembled — "
                f"{len(video_paths)} scenes, {duration:.1f}s"
            )

            # Publish to Jellyfin if requested
            if publish:
                try:
                    from packages.episode_assembly.publish import publish_episode as _publish
                    await _publish(
                        project_id=project_id,
                        episode_id=episode_id,
                        video_path=episode_path,
                        episode_number=episode_number,
                        title=await conn.fetchval("SELECT title FROM episodes WHERE id = $1", ep_uuid),
                    )
                    await conn.execute(
                        "UPDATE episodes SET status = 'published', updated_at = NOW() WHERE id = $1",
                        ep_uuid,
                    )
                    logger.info(f"text-to-episode: ep{episode_number} published to Jellyfin")
                except Exception as e:
                    logger.warning(f"text-to-episode: Jellyfin publish failed: {e}")

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"text-to-episode pipeline failed: {e}", exc_info=True)
        await _update_episode_status(ep_uuid, "failed", str(e))


async def _update_episode_status(episode_id: uuid.UUID, status: str, error: str = None):
    """Update episode status (helper for background task)."""
    conn = await connect_direct()
    try:
        if error:
            await conn.execute(
                "UPDATE episodes SET status = $2, description = COALESCE(description, '') || E'\\nError: ' || $3, updated_at = NOW() WHERE id = $1",
                episode_id, status, error,
            )
        else:
            await conn.execute(
                "UPDATE episodes SET status = $2, updated_at = NOW() WHERE id = $1",
                episode_id, status,
            )
    finally:
        await conn.close()


@router.post("/scenes/produce-episode")
async def produce_episode(
    project_id: int,
    episode_number: int,
    publish: bool = False,
):
    """End-to-end episode production pipeline.

    Orchestrates the full pipeline from shot generation to assembled episode:
    1. Verify episode exists and has scenes with shots
    2. Generate missing shots (auto-approve so downstream fires)
    3. Wait for all scenes to complete (voice + music + assembly happen inside)
    4. Assemble episode from completed scene videos
    5. Optionally publish to Jellyfin

    Auto-approve is enabled so the full downstream pipeline fires:
    - Voice synthesis (edge-tts / RVC / SoVITS / XTTS)
    - Music generation (ACE-Step from scene mood)
    - Audio mixing with ducking (dialogue + music)
    - Scene video assembly with crossfade transitions

    Args:
        project_id: Project ID
        episode_number: Episode number to produce
        publish: If True, publish to Jellyfin after assembly
    """
    conn = await connect_direct()
    try:
        # 1. Find the episode
        episode = await conn.fetchrow("""
            SELECT e.id, e.title, e.story_arc, e.status
            FROM episodes e
            WHERE e.project_id = $1 AND e.episode_number = $2
        """, project_id, episode_number)

        if not episode:
            raise HTTPException(
                status_code=404,
                detail=f"Episode {episode_number} not found for project {project_id}",
            )

        episode_id = episode["id"]

        # 2. Get all scenes for this episode, ordered by position
        scene_rows = await conn.fetch("""
            SELECT s.id, s.title, s.scene_number, s.generation_status,
                   s.final_video_path, s.mood,
                   es.position,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = s.id) as shot_count,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = s.id
                    AND status = 'completed') as completed_shots
            FROM scenes s
            JOIN episode_scenes es ON es.scene_id = s.id
            WHERE es.episode_id = $1
            ORDER BY es.position
        """, episode_id)

        if not scene_rows:
            raise HTTPException(
                status_code=400,
                detail=f"Episode {episode_number} has no scenes. "
                       f"Run POST /scenes/generate-from-story?project_id={project_id}&episode_id={episode_id} first.",
            )

        # Check for scenes without shots
        empty_scenes = [r for r in scene_rows if r["shot_count"] == 0]
        if empty_scenes:
            raise HTTPException(
                status_code=400,
                detail=f"{len(empty_scenes)} scene(s) have no shots. "
                       f"Run POST /scenes/generate-shots-all?project_id={project_id} first. "
                       f"Empty: {[r['title'] for r in empty_scenes]}",
            )

        # 3. Determine which scenes need generation
        needs_generation = [
            r for r in scene_rows
            if r["generation_status"] not in ("completed", "assembled")
            or not r["final_video_path"]
            or not Path(r["final_video_path"]).exists()
        ]

        already_done = [
            r for r in scene_rows
            if r["generation_status"] in ("completed", "assembled")
            and r["final_video_path"]
            and Path(r["final_video_path"]).exists()
        ]

    finally:
        await conn.close()

    # 4. Generate scenes that need it (auto-approve enabled)
    if needs_generation:
        logger.info(
            f"produce-episode: generating {len(needs_generation)} scenes "
            f"for ep{episode_number} ({len(already_done)} already done)"
        )

        from .builder import generate_scene, _scene_generation_lock

        for scene_row in needs_generation:
            scene_id = str(scene_row["id"])
            logger.info(
                f"produce-episode: generating scene '{scene_row['title']}' "
                f"({scene_row['shot_count']} shots)"
            )

            # Reset shots to pending for this scene
            conn = await connect_direct()
            try:
                await conn.execute(
                    "UPDATE shots SET status = 'pending', error_message = NULL "
                    "WHERE scene_id = $1 AND status NOT IN ('completed', 'accepted_best')",
                    scene_row["id"],
                )
                await conn.execute(
                    "UPDATE scenes SET completed_shots = 0, "
                    "current_generating_shot_id = NULL WHERE id = $1",
                    scene_row["id"],
                )
            finally:
                await conn.close()

            # Generate with auto_approve=True so voice/music/assembly fires
            await generate_scene(scene_id, auto_approve=True)

    # 5. Verify all scenes completed
    conn = await connect_direct()
    try:
        final_scenes = await conn.fetch("""
            SELECT s.id, s.title, s.generation_status, s.final_video_path
            FROM scenes s
            JOIN episode_scenes es ON es.scene_id = s.id
            WHERE es.episode_id = $1
            ORDER BY es.position
        """, episode_id)

        completed = [
            r for r in final_scenes
            if r["final_video_path"] and Path(r["final_video_path"]).exists()
        ]
        failed = [
            r for r in final_scenes
            if not r["final_video_path"] or not Path(r["final_video_path"]).exists()
        ]

        if not completed:
            return {
                "status": "failed",
                "message": "No scenes completed successfully",
                "failed_scenes": [r["title"] for r in failed],
            }

        # 6. Assemble episode
        video_paths = []
        transitions = []
        for sr in final_scenes:
            vp = sr["final_video_path"]
            if vp and Path(vp).exists():
                video_paths.append(vp)
                transitions.append("fadeblack")  # default transition
            else:
                logger.warning(f"produce-episode: skipping scene '{sr['title']}' (no video)")

        from packages.episode_assembly.builder import (
            assemble_episode as _assemble_episode,
            get_video_duration,
            extract_thumbnail,
            EPISODE_OUTPUT_DIR,
        )
        from packages.episode_assembly.router import _apply_episode_music

        episode_path = await _assemble_episode(
            str(episode_id), video_paths, transitions,
        )

        # Apply episode-level background music
        episode_path = await _apply_episode_music(
            conn, episode_id, episode_path, episode["story_arc"],
        )

        duration = await get_video_duration(episode_path)

        # Generate thumbnail
        thumb_path = str(EPISODE_OUTPUT_DIR / f"episode_{episode_id}_thumb.jpg")
        await extract_thumbnail(episode_path, thumb_path)

        # Update DB
        await conn.execute("""
            UPDATE episodes SET status = 'assembled', final_video_path = $2,
                   actual_duration_seconds = $3, thumbnail_path = $4, updated_at = NOW()
            WHERE id = $1
        """, episode_id, episode_path, duration,
            thumb_path if Path(thumb_path).exists() else None)

        logger.info(
            f"produce-episode: ep{episode_number} assembled — "
            f"{len(completed)} scenes, {duration:.1f}s, "
            f"{len(failed)} failed"
        )

        # 7. Optionally publish to Jellyfin
        publish_result = None
        if publish and episode_path:
            try:
                from packages.episode_assembly.publish import publish_episode as _publish
                publish_result = await _publish(
                    project_id=project_id,
                    episode_id=str(episode_id),
                    video_path=episode_path,
                    episode_number=episode_number,
                    title=episode["title"],
                )
                await conn.execute(
                    "UPDATE episodes SET status = 'published', updated_at = NOW() WHERE id = $1",
                    episode_id,
                )
                logger.info(f"produce-episode: ep{episode_number} published to Jellyfin")
            except Exception as e:
                logger.warning(f"produce-episode: Jellyfin publish failed (non-fatal): {e}")
                publish_result = {"error": str(e)}

        return {
            "status": "completed",
            "episode_id": str(episode_id),
            "episode_number": episode_number,
            "title": episode["title"],
            "video_path": episode_path,
            "duration_seconds": duration,
            "scenes_completed": len(completed),
            "scenes_failed": len(failed),
            "failed_scenes": [r["title"] for r in failed] if failed else [],
            "published": publish_result,
        }

    finally:
        await conn.close()
