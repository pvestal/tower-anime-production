"""FastAPI endpoints for interactive visual novel (classic + director modes)."""
import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .engine import start_session, generate_scene
from .director import (
    start_director_session,
    handle_message,
    handle_choice as director_handle_choice,
    handle_edit,
    end_director_session,
)
from .image_gen import start_image_generation, get_image_status
from .models import StartSessionRequest, ChoiceRequest, MessageRequest, EditSceneRequest
from .session_store import store

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sessions")
async def create_session(req: StartSessionRequest):
    """Start a new interactive visual novel session."""
    try:
        session, opening_scene = await start_session(req.project_id, req.character_slugs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to start session")
        raise HTTPException(status_code=500, detail="Failed to start session — is Ollama running?")

    # Fire off image generation for the opening scene
    await start_image_generation(session, 0, opening_scene.image_prompt)

    return {
        "session_id": session.session_id,
        "scene": opening_scene.model_dump(),
        "image": get_image_status(session, 0),
    }


@router.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    return {"sessions": store.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session state."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.session_id,
        "project_id": session.project_id,
        "project_name": session.project_name,
        "scene_count": len(session.scenes),
        "current_scene_index": session.current_scene_index,
        "is_ended": session.is_ended,
        "relationships": session.relationships,
        "variables": session.variables,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """End and remove a session."""
    if store.delete(session_id):
        return {"message": "Session ended"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/scene")
async def get_current_scene(session_id: str):
    """Get the current scene."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.scenes:
        raise HTTPException(status_code=404, detail="No scenes yet")

    idx = session.current_scene_index
    return {
        "scene": session.scenes[idx],
        "image": get_image_status(session, idx),
    }


@router.post("/sessions/{session_id}/choose")
async def submit_choice(session_id: str, req: ChoiceRequest):
    """Submit a player choice and get the next scene."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_ended:
        raise HTTPException(status_code=400, detail="Session has ended")

    current = session.scenes[-1] if session.scenes else None
    if not current:
        raise HTTPException(status_code=400, detail="No current scene")

    choices = current.get("choices", [])
    if req.choice_index < 0 or req.choice_index >= len(choices):
        raise HTTPException(status_code=400, detail=f"Invalid choice index (0-{len(choices)-1})")

    choice_text = choices[req.choice_index]["text"]

    try:
        next_scene = await generate_scene(session, choice_text)
    except Exception:
        logger.exception("Failed to generate next scene")
        raise HTTPException(status_code=500, detail="Failed to generate scene")

    scene_idx = session.current_scene_index
    await start_image_generation(session, scene_idx, next_scene.image_prompt)

    return {
        "scene": next_scene.model_dump(),
        "image": get_image_status(session, scene_idx),
        "session_ended": session.is_ended,
    }


@router.get("/sessions/{session_id}/image/{scene_idx}")
async def image_status(session_id: str, scene_idx: int):
    """Get image generation status for a scene."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return get_image_status(session, scene_idx)


@router.get("/sessions/{session_id}/image/{scene_idx}/file")
async def serve_image(session_id: str, scene_idx: int):
    """Serve the generated image file."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    info = session.images.get(scene_idx)
    if not info or info.get("status") != "ready":
        raise HTTPException(status_code=404, detail="Image not ready")

    path = Path(info["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(path, media_type="image/png")


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str):
    """Get full scene history for a session."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "scenes": session.scenes,
        "relationships": session.relationships,
        "variables": session.variables,
        "is_ended": session.is_ended,
    }


# ─── Director Mode Endpoints ────────────────────────────────────────────


@router.post("/director/sessions")
async def create_director_session(req: StartSessionRequest):
    """Start a director-mode session with conversational AI."""
    try:
        session, greeting = await start_director_session(req.project_id, req.character_slugs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to start director session")
        raise HTTPException(status_code=500, detail="Failed to start session")

    return {
        "session_id": session.session_id,
        "greeting": greeting,
        "project_name": session.project_name,
        "characters": [
            {"name": c["name"], "slug": c["slug"], "role": c.get("role", "")}
            for c in session.characters
        ],
    }


@router.post("/director/sessions/{session_id}/message")
async def send_message(session_id: str, req: MessageRequest):
    """Send free-text message to the director."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_ended:
        raise HTTPException(status_code=400, detail="Session has ended")

    try:
        result = await handle_message(session, req.text)
    except Exception:
        logger.exception("Director message handling failed")
        raise HTTPException(status_code=500, detail="Failed to process message")

    response = {"result": result, "session_ended": session.is_ended}

    # If a scene was generated, include image status
    if result.get("type") == "scene":
        scene_idx = session.current_scene_index
        response["image"] = get_image_status(session, scene_idx)
        response["relationships"] = session.relationships

    return response


@router.post("/director/sessions/{session_id}/choose")
async def director_choose(session_id: str, req: ChoiceRequest):
    """Submit a structured choice in director mode."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_ended:
        raise HTTPException(status_code=400, detail="Session has ended")

    try:
        result = await director_handle_choice(session, req.choice_index)
    except Exception:
        logger.exception("Director choice handling failed")
        raise HTTPException(status_code=500, detail="Failed to process choice")

    response = {"result": result, "session_ended": session.is_ended}
    if result.get("type") == "scene":
        scene_idx = session.current_scene_index
        response["image"] = get_image_status(session, scene_idx)
        response["relationships"] = session.relationships
    return response


@router.patch("/director/sessions/{session_id}/edit")
async def edit_scene(session_id: str, req: EditSceneRequest):
    """Edit a scene field (narration, image_prompt) and optionally regenerate."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await handle_edit(session, req.scene_index, req.field, req.value)
    if result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    response = {"result": result}
    if result.get("regenerating_image"):
        response["image"] = get_image_status(session, req.scene_index)
    return response


@router.get("/director/sessions/{session_id}/events")
async def director_events(session_id: str):
    """SSE stream of real-time director events (thinking, image progress, etc)."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    # Register the queue on the session so director engine can push events
    if not hasattr(session, '_event_queues'):
        session._event_queues = []
    session._event_queues.append(queue)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = event.get("event", "status")
                    data = json.dumps(event.get("data", {}))
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if hasattr(session, '_event_queues'):
                try:
                    session._event_queues.remove(queue)
                except ValueError:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/director/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    """Get the full director conversation history."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.variables.get("_messages", [])
    if not isinstance(messages, list):
        messages = []

    return {
        "messages": messages,
        "scene_count": len(session.scenes),
        "relationships": session.relationships,
        "preferences": session.variables.get("_preferences", {}),
    }


@router.delete("/director/sessions/{session_id}")
async def end_director(session_id: str):
    """End a director session, storing summary in Echo Brain."""
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await end_director_session(session)
    store.delete(session_id)
    return {"message": "Session ended, summary saved"}
