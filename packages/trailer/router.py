"""Trailer API — create, generate, review, and assemble style-validation trailers.

Endpoints:
    POST   /api/trailers/create          — Create trailer with auto-generated shots
    GET    /api/trailers?project_id=N     — List trailers for a project
    GET    /api/trailers/{id}             — Get trailer details with shots
    POST   /api/trailers/{id}/generate-keyframes  — Fast keyframe preview
    POST   /api/trailers/{id}/generate-videos     — Full video generation
    POST   /api/trailers/{id}/assemble    — Stitch shots into trailer video
    PATCH  /api/trailers/{id}/shots/{sid} — Update shot prompt/LoRA/params
    POST   /api/trailers/{id}/approve     — Approve trailer (unlocks full production)
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from packages.core.db import connect_direct

from .generator import create_trailer, get_trailer, list_trailers, update_trailer_shot, approve_trailer
from .assembler import assemble_trailer
from .trailer_scorecard import score_trailer, get_cached_scorecard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trailers", tags=["trailers"])


class TrailerCreateRequest(BaseModel):
    project_id: int
    title: str | None = None


class ShotUpdateRequest(BaseModel):
    generation_prompt: str | None = None
    generation_negative: str | None = None
    lora_name: str | None = None
    shot_type: str | None = None
    camera_angle: str | None = None


class ApproveRequest(BaseModel):
    notes: str = ""


class ShotActionRequest(BaseModel):
    action: str  # bump_tier, swap_lora, regenerate, new_seed
    value: str | None = None  # e.g. new lora name, tier name


class GenerateVideosRequest(BaseModel):
    shot_ids: list[str] | None = Field(None, description="Specific shot IDs to generate. Omit for all.")


# ── Create ──────────────────────────────────────────────────────────────

@router.post("/create")
async def create_trailer_endpoint(body: TrailerCreateRequest):
    """Create a new trailer with auto-generated shots from template.

    Picks characters (preferring those with LoRAs), selects diverse motion
    LoRAs from the catalog based on content rating, and builds 8 shots.
    """
    try:
        result = await create_trailer(body.project_id, body.title)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Trailer creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── List / Get ──────────────────────────────────────────────────────────

@router.get("")
async def list_trailers_endpoint(project_id: int):
    """List all trailers for a project."""
    return await list_trailers(project_id)


@router.get("/{trailer_id}")
async def get_trailer_endpoint(trailer_id: str):
    """Get trailer details including all shots and their status."""
    result = await get_trailer(trailer_id)
    if not result:
        raise HTTPException(status_code=404, detail="Trailer not found")
    return result


# ── Generate Keyframes ──────────────────────────────────────────────────

@router.post("/{trailer_id}/generate-keyframes")
async def generate_keyframes_endpoint(trailer_id: str, background_tasks: BackgroundTasks):
    """Generate keyframe images for all trailer shots (~18s per shot).

    Uses the existing keyframe_blitz pipeline. Review keyframes before
    committing to full video generation.
    """
    trailer = await get_trailer(trailer_id)
    if not trailer:
        raise HTTPException(status_code=404, detail="Trailer not found")

    scene_id = trailer["scene_id"]

    # Run keyframe blitz in background
    background_tasks.add_task(_run_keyframe_blitz, scene_id, trailer_id)

    return {
        "trailer_id": trailer_id,
        "scene_id": scene_id,
        "status": "generating_keyframes",
        "message": f"Generating keyframes for {len(trailer['shots'])} shots. "
                   f"Check GET /api/trailers/{trailer_id} for progress.",
    }


async def _run_keyframe_blitz(scene_id: str, trailer_id: str):
    """Background task: run keyframe blitz on trailer's scene."""
    try:
        from packages.scene_generation.scene_keyframe import keyframe_blitz
        conn = await connect_direct()
        try:
            result = await keyframe_blitz(conn, scene_id)
        finally:
            await conn.close()
        logger.info(f"Trailer {trailer_id} keyframe blitz: {result}")

        # Update trailer status
        conn = await connect_direct()
        try:
            await conn.execute("""
                UPDATE trailers SET status = 'keyframes_ready', updated_at = NOW()
                WHERE id = $1 AND status = 'draft'
            """, uuid.UUID(trailer_id))
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Trailer {trailer_id} keyframe blitz failed: {e}")


# ── Generate Videos ─────────────────────────────────────────────────────

@router.post("/{trailer_id}/generate-videos")
async def generate_videos_endpoint(
    trailer_id: str,
    body: GenerateVideosRequest = GenerateVideosRequest(),
    background_tasks: BackgroundTasks = None,
):
    """Generate videos for trailer shots.

    If shot_ids is provided, only those shots are regenerated.
    Otherwise, generates all pending/failed shots.
    """
    trailer = await get_trailer(trailer_id)
    if not trailer:
        raise HTTPException(status_code=404, detail="Trailer not found")

    scene_id = trailer["scene_id"]

    # If specific shots requested, reset them to pending
    if body.shot_ids:
        conn = await connect_direct()
        try:
            for sid in body.shot_ids:
                await conn.execute("""
                    UPDATE shots SET status = 'pending', error_message = NULL, comfyui_prompt_id = NULL
                    WHERE id = $1 AND scene_id = $2
                """, uuid.UUID(sid), uuid.UUID(scene_id))
        finally:
            await conn.close()

    # Run scene generation in background
    background_tasks.add_task(_run_video_generation, scene_id, trailer_id)

    return {
        "trailer_id": trailer_id,
        "scene_id": scene_id,
        "status": "generating_videos",
        "shot_ids": body.shot_ids,
        "message": f"Generating videos for trailer. "
                   f"Check GET /api/trailers/{trailer_id} for progress.",
    }


async def _run_video_generation(scene_id: str, trailer_id: str):
    """Background task: generate all pending shots in trailer's scene."""
    try:
        # Force trailer shots to use WAN 2.2 14B (not FramePack default)
        # and clear any auto-assigned movie clip sources
        conn = await connect_direct()
        try:
            await conn.execute("""
                UPDATE shots
                SET source_video_path = NULL,
                    source_video_auto_assigned = FALSE,
                    video_engine = 'wan22_14b'
                WHERE scene_id = $1 AND status = 'pending'
            """, uuid.UUID(scene_id))
        finally:
            await conn.close()

        from packages.scene_generation.builder import generate_scene
        await generate_scene(scene_id, auto_approve=True)

        # Update trailer status
        conn = await connect_direct()
        try:
            completed = await conn.fetchval("""
                SELECT COUNT(*) FROM shots
                WHERE scene_id = $1 AND status = 'completed'
            """, uuid.UUID(scene_id))
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM shots WHERE scene_id = $1",
                uuid.UUID(scene_id),
            )

            if completed == total:
                new_status = "videos_ready"
            elif completed > 0:
                new_status = "videos_partial"
            else:
                new_status = "videos_failed"

            await conn.execute("""
                UPDATE trailers SET status = $2, updated_at = NOW()
                WHERE id = $1
            """, uuid.UUID(trailer_id), new_status)

            logger.info(f"Trailer {trailer_id} video gen: {completed}/{total} completed → {new_status}")
        finally:
            await conn.close()

        # Auto-score the trailer so scorecard is ready for review
        try:
            await score_trailer(trailer_id)
            logger.info(f"Trailer {trailer_id} auto-scored after video generation")
        except Exception as score_err:
            logger.warning(f"Trailer {trailer_id} auto-score failed: {score_err}")

    except Exception as e:
        logger.error(f"Trailer {trailer_id} video generation failed: {e}")


# ── Assemble ────────────────────────────────────────────────────────────

@router.post("/{trailer_id}/assemble")
async def assemble_trailer_endpoint(trailer_id: str):
    """Assemble completed trailer shots into a single video.

    Uses quick-cut dissolve transitions (0.15s) for an energetic feel.
    Returns the output video path and duration.
    """
    try:
        result = await assemble_trailer(trailer_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Trailer assembly failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Update Shot ─────────────────────────────────────────────────────────

@router.patch("/{trailer_id}/shots/{shot_id}")
async def update_shot_endpoint(trailer_id: str, shot_id: str, body: ShotUpdateRequest):
    """Update a trailer shot's generation parameters.

    Resets the shot to pending so it can be regenerated with new settings.
    Use this to swap LoRAs, adjust prompts, or change shot type.
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        result = await update_trailer_shot(trailer_id, shot_id, updates)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Approve ─────────────────────────────────────────────────────────────

@router.post("/{trailer_id}/approve")
async def approve_trailer_endpoint(trailer_id: str, body: ApproveRequest = ApproveRequest()):
    """Approve a trailer — signals that project style is validated.

    This unlocks full production in the orchestrator's trailer_validation phase.
    """
    try:
        result = await approve_trailer(trailer_id, body.notes)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Scorecard ──────────────────────────────────────────────────────────

@router.get("/{trailer_id}/scorecard")
async def get_scorecard_endpoint(trailer_id: str, refresh: bool = False):
    """Get trailer scorecard. Computes on first call, returns cached after.

    Pass ?refresh=true to force recomputation.
    """
    if not refresh:
        cached = await get_cached_scorecard(trailer_id)
        if cached:
            return cached

    try:
        return await score_trailer(trailer_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Scorecard computation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trailer_id}/scorecard/refresh")
async def refresh_scorecard_endpoint(trailer_id: str):
    """Force recompute the trailer scorecard."""
    try:
        return await score_trailer(trailer_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Shot Actions ───────────────────────────────────────────────────────

@router.post("/{trailer_id}/shots/{shot_id}/action")
async def shot_action_endpoint(trailer_id: str, shot_id: str, body: ShotActionRequest):
    """Execute a scorecard recommendation action on a trailer shot.

    Actions: bump_tier, drop_tier, swap_lora, new_seed, regenerate
    """
    conn = await connect_direct()
    try:
        # Verify shot belongs to trailer
        trailer = await conn.fetchrow(
            "SELECT scene_id FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )
        if not trailer:
            raise HTTPException(status_code=404, detail="Trailer not found")

        shot = await conn.fetchrow(
            "SELECT * FROM shots WHERE id = $1 AND scene_id = $2",
            uuid.UUID(shot_id), trailer["scene_id"]
        )
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not in trailer")

        action = body.action
        changes = {}

        if action == "bump_tier":
            tiers = ["low", "medium", "high", "extreme"]
            current = shot.get("motion_tier") or "medium"
            idx = tiers.index(current) if current in tiers else 1
            new_tier = tiers[min(idx + 1, len(tiers) - 1)]
            changes["motion_tier"] = new_tier

        elif action == "drop_tier":
            tiers = ["low", "medium", "high", "extreme"]
            current = shot.get("motion_tier") or "medium"
            idx = tiers.index(current) if current in tiers else 1
            new_tier = tiers[max(idx - 1, 0)]
            changes["motion_tier"] = new_tier

        elif action == "swap_lora":
            if not body.value:
                raise HTTPException(status_code=400, detail="Provide lora name in 'value'")
            changes["lora_name"] = body.value

        elif action == "new_seed":
            changes["seed"] = None

        elif action == "regenerate":
            pass  # just reset below

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        # Build SET clause
        set_parts = [
            "status = 'pending'",
            "output_video_path = NULL",
            "quality_score = NULL",
            "qc_category_averages = NULL",
            "qc_issues = NULL",
            "comfyui_prompt_id = NULL",
            "error_message = NULL",
        ]
        params = [uuid.UUID(shot_id)]
        idx = 2
        for col, val in changes.items():
            set_parts.append(f"{col} = ${idx}")
            params.append(val)
            idx += 1

        await conn.execute(
            f"UPDATE shots SET {', '.join(set_parts)} WHERE id = $1",
            *params
        )

        return {
            "shot_id": shot_id,
            "action": action,
            "changes": changes,
            "status": "pending",
        }
    finally:
        await conn.close()
