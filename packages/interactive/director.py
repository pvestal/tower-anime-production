"""Director engine — conversational AI layer over the visual novel engine.

Instead of just generating scenes from fixed choices, the director:
- Asks the user questions (tone, preferences, focus)
- Accepts free-text input alongside structured choices
- Streams status events via an async queue
- Integrates Echo Brain for memory/preferences
- Allows editing scenes and regenerating images
"""

import asyncio
import json
import logging
import time

import httpx

from packages.core.config import OLLAMA_URL

from .echo_brain import (
    search_user_preferences,
    recall_session_context,
    store_preference,
    store_decision,
    store_session_summary,
)
from .engine import load_project_context, generate_scene, OLLAMA_MODEL
from .image_gen import start_image_generation
from .models import SceneData
from .session_store import SessionState, store

logger = logging.getLogger(__name__)

# Event types for SSE
EVT_THINKING = "thinking"
EVT_DIRECTOR_MESSAGE = "director_message"
EVT_SCENE_READY = "scene_ready"
EVT_IMAGE_STATUS = "image_status"
EVT_ECHO_BRAIN = "echo_brain"
EVT_PREFERENCE_SAVED = "preference_saved"
EVT_ERROR = "error"

DIRECTOR_SYSTEM_PROMPT = """\
You are the AI Director for an interactive visual novel. You guide the player \
through story creation and gameplay with a warm, engaging personality.

Your role has TWO modes:

MODE 1 — CONVERSATION (when no active scene or between scenes):
Respond naturally. Ask questions about preferences, react to the player's input, \
suggest story directions. Output JSON:
{
  "type": "conversation",
  "message": "Your response to the player",
  "suggestions": ["option 1", "option 2", "option 3"],
  "detected_preferences": [{"key": "tone", "value": "dark"}, ...],
  "ready_to_generate": false
}

Set ready_to_generate=true when you have enough context to create the next scene.

MODE 2 — SCENE GENERATION (when ready_to_generate was true):
Generate a full visual novel scene. Output JSON:
{
  "type": "scene",
  "narration": "Second-person present tense (2-4 sentences)",
  "image_prompt": "Detailed anime scene for Stable Diffusion (no character names)",
  "dialogue": [{"character": "Name", "text": "words", "emotion": "neutral"}],
  "choices": [{"text": "What player does", "tone": "bold|cautious|romantic|dramatic|humorous|neutral"}],
  "story_effects": [{"type": "relationship|variable|flag", "target": "name", "value": "..."}],
  "director_note": "Brief note about what's happening narratively",
  "is_ending": false,
  "ending_type": null
}

RULES:
- When the player sends free text, interpret it as story direction or a response
- If the player edits something, acknowledge and adapt
- Track tone preferences: if they consistently pick bold choices, lean into that
- 2-4 choices per scene, meaningful branching
- image_prompt: describe appearance not names, optimize for Stable Diffusion
- Pacing: scenes 1-5 setup, 6-15 rising, 15-22 climax, 22-30 resolution
- End naturally between scene 20-30
"""


async def start_director_session(
    project_id: int,
    character_slugs: list[str] | None = None,
    event_queue: asyncio.Queue | None = None,
) -> tuple[SessionState, dict]:
    """Start a director session — loads context, recalls Echo Brain, sends greeting."""
    _emit(event_queue, EVT_THINKING, {"step": "Loading project..."})

    ctx = await load_project_context(project_id, character_slugs)

    session = store.create(
        project_id=project_id,
        project_name=ctx["project_name"],
        character_slugs=ctx["character_slugs"],
        characters=ctx["characters"],
        world_context=ctx["world_context"],
        checkpoint_model=ctx["checkpoint_model"],
        generation_params=ctx["generation_params"],
    )
    for c in ctx["characters"]:
        session.relationships[c["name"]] = 0

    # Initialize director state on the session
    session.variables["_director_mode"] = True
    session.variables["_messages"] = []  # Director conversation history
    session.variables["_preferences"] = {}

    # Recall from Echo Brain
    _emit(event_queue, EVT_ECHO_BRAIN, {"step": "Searching memories..."})
    preferences = ""
    past_context = ""
    try:
        preferences = await asyncio.to_thread(
            search_user_preferences, ctx["project_name"]
        )
        char_names = [c["name"] for c in ctx["characters"]]
        past_context = await asyncio.to_thread(
            recall_session_context, ctx["project_name"], char_names
        )
    except Exception as e:
        logger.warning("Echo Brain recall failed: %s", e)
    if preferences or past_context:
        _emit(event_queue, EVT_ECHO_BRAIN, {
            "step": "Found memories",
            "has_preferences": bool(preferences),
            "has_past_sessions": bool(past_context),
        })

    # Generate director greeting
    _emit(event_queue, EVT_THINKING, {"step": "Director is preparing..."})

    char_block = ", ".join(
        f"{c['name']} ({c.get('role', 'character')})" for c in ctx["characters"]
    )
    memory_block = ""
    if preferences:
        memory_block += f"\n\nPLAYER PREFERENCES FROM MEMORY:\n{preferences[:500]}"
    if past_context:
        memory_block += f"\n\nPAST SESSION CONTEXT:\n{past_context[:500]}"

    greeting_prompt = (
        f"The player just started a new session for the project '{ctx['project_name']}'.\n"
        f"WORLD: {ctx['world_context']}\n"
        f"CHARACTERS: {char_block}\n"
        f"{memory_block}\n\n"
        "Greet them warmly. Introduce the world briefly. Ask what kind of experience "
        "they want (tone, focus, any characters they're interested in). "
        "If you found past preferences, reference them naturally. "
        "Output MODE 1 (conversation) JSON."
    )

    response = await _call_director(greeting_prompt)
    msg = _parse_director_response(response)

    # Store as first message
    _append_message(session, "director", msg)

    _emit(event_queue, EVT_DIRECTOR_MESSAGE, msg)
    return session, msg


async def handle_message(
    session: SessionState,
    text: str,
    event_queue: asyncio.Queue | None = None,
) -> dict:
    """Handle free-text user input — could be conversation, choice, or direction."""
    target = (event_queue, session)
    _emit(target, EVT_THINKING, {"step": "Processing your input..."})

    _append_message(session, "user", {"message": text})

    # Build context for director
    conversation_history = _get_conversation_summary(session)
    scene_count = len(session.scenes)

    # Detect if user is picking from suggestions
    last_director_msg = _get_last_director_message(session)
    suggestions = last_director_msg.get("suggestions", []) if last_director_msg else []

    # Check if the director was ready to generate
    was_ready = last_director_msg.get("ready_to_generate", False) if last_director_msg else False

    prompt = _build_message_prompt(
        session=session,
        user_text=text,
        conversation_history=conversation_history,
        scene_count=scene_count,
        was_ready=was_ready,
    )

    _emit(target, EVT_THINKING, {"step": "Director is thinking..."})
    response = await _call_director(prompt)
    result = _parse_director_response(response)

    # Handle preferences
    for pref in result.get("detected_preferences", []):
        key, val = pref.get("key", ""), pref.get("value", "")
        if key and val:
            session.variables.setdefault("_preferences", {})
            if isinstance(session.variables["_preferences"], dict):
                session.variables["_preferences"][key] = val
            _emit(target, EVT_PREFERENCE_SAVED, {"key": key, "value": val})
            asyncio.create_task(_store_preference_bg(
                f"Prefers {key}={val}", session.project_name
            ))

    if result.get("type") == "scene":
        _emit(target, EVT_THINKING, {"step": "Building scene..."})
        scene = _director_response_to_scene(result, len(session.scenes))

        for effect in scene.story_effects:
            if effect.type == "relationship" and effect.target in session.relationships:
                try:
                    session.relationships[effect.target] += int(effect.value)
                except (ValueError, TypeError):
                    pass
            elif effect.type in ("variable", "flag"):
                session.variables[effect.target] = effect.value

        scene_record = scene.model_dump()
        scene_record["director_note"] = result.get("director_note", "")
        session.scenes.append(scene_record)

        if scene.is_ending:
            session.is_ended = True

        session.touch()

        scene_idx = session.current_scene_index
        _emit(target, EVT_IMAGE_STATUS, {"scene_index": scene_idx, "status": "pending"})
        await start_image_generation(session, scene_idx, scene.image_prompt)

        if text and scene_count > 0:
            asyncio.create_task(_store_decision_bg(
                session.project_name, scene_count + 1, text
            ))

        scene_data = scene.model_dump()
        scene_data["director_note"] = result.get("director_note", "")
        msg = {
            "type": "scene",
            "scene": scene_data,
            "director_note": result.get("director_note", ""),
        }
        _append_message(session, "director", msg)
        _emit(target, EVT_SCENE_READY, scene_data)
        return msg

    # Conversation response
    _append_message(session, "director", result)
    _emit(target, EVT_DIRECTOR_MESSAGE, result)

    # If ready_to_generate, auto-generate the scene
    if result.get("ready_to_generate"):
        return await _auto_generate_scene(session, (event_queue, session))

    return result


async def handle_choice(
    session: SessionState,
    choice_index: int,
    event_queue: asyncio.Queue | None = None,
) -> dict:
    """Handle a structured choice selection — wraps as a message."""
    current = session.scenes[-1] if session.scenes else None
    if not current:
        return await handle_message(session, "Let's begin the story", event_queue)

    choices = current.get("choices", [])
    if choice_index < 0 or choice_index >= len(choices):
        return {"type": "error", "message": "Invalid choice"}

    choice_text = choices[choice_index]["text"]
    return await handle_message(session, choice_text, event_queue)


async def handle_edit(
    session: SessionState,
    scene_index: int,
    field: str,
    new_value: str,
    event_queue: asyncio.Queue | None = None,
) -> dict:
    """Handle user editing a scene field (narration, image_prompt, etc)."""
    if scene_index < 0 or scene_index >= len(session.scenes):
        return {"type": "error", "message": "Invalid scene index"}

    scene = session.scenes[scene_index]
    old_value = scene.get(field, "")
    if field not in ("narration", "image_prompt", "dialogue"):
        return {"type": "error", "message": f"Cannot edit field: {field}"}

    scene[field] = new_value
    target = (event_queue, session)
    _emit(target, EVT_THINKING, {"step": f"Updated {field}"})

    # If image_prompt was edited, regenerate the image
    if field == "image_prompt":
        _emit(target, EVT_IMAGE_STATUS, {"scene_index": scene_index, "status": "pending"})
        await start_image_generation(session, scene_index, new_value)

    # Tell the director about the edit
    _append_message(session, "user", {
        "message": f"[Edited scene {scene_index + 1} {field}]",
        "edit": {"field": field, "old": old_value[:100], "new": new_value[:100]},
    })

    return {
        "type": "edit_confirmed",
        "scene_index": scene_index,
        "field": field,
        "regenerating_image": field == "image_prompt",
    }


async def end_director_session(session: SessionState):
    """Store session summary in Echo Brain when session ends."""
    key_decisions = []
    for s in session.scenes:
        if chosen := s.get("chosen_text"):
            key_decisions.append(chosen)
        # Also grab free-text inputs
        messages = session.variables.get("_messages", [])
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                msg_text = m.get("content", {})
                if isinstance(msg_text, dict):
                    msg_text = msg_text.get("message", "")
                if isinstance(msg_text, str) and len(msg_text) > 10:
                    key_decisions.append(msg_text[:80])

    try:
        await asyncio.to_thread(
            store_session_summary,
            session.project_name,
            len(session.scenes),
            session.scenes[-1].get("ending_type") if session.scenes else None,
            session.relationships,
            key_decisions[:10],
        )
    except Exception as e:
        logger.warning("Failed to store session summary: %s", e)


# --- Internal helpers ---


async def _auto_generate_scene(
    session: SessionState,
    event_queue: asyncio.Queue | None,
) -> dict:
    """When director says ready_to_generate, produce a scene."""
    _emit(event_queue, EVT_THINKING, {"step": "Generating scene..."})

    # Gather preferences for the scene prompt
    prefs = session.variables.get("_preferences", {})
    pref_block = ", ".join(f"{k}={v}" for k, v in prefs.items()) if isinstance(prefs, dict) and prefs else ""

    scene_number = len(session.scenes) + 1
    conversation_summary = _get_conversation_summary(session)

    prompt = (
        f"WORLD: {session.world_context}\n\n"
        f"CHARACTERS:\n"
    )
    for c in session.characters:
        prompt += f"- {c['name']}: {c.get('personality', '')}. "
        if c.get("appearance_summary"):
            prompt += f"Appearance: {c['appearance_summary']}"
        prompt += "\n"

    if session.story_summary:
        prompt += f"\nSTORY SO FAR:\n{session.story_summary}\n"

    if pref_block:
        prompt += f"\nPLAYER PREFERENCES: {pref_block}\n"

    prompt += f"\nCONVERSATION WITH PLAYER:\n{conversation_summary}\n"

    rels = session.relationships
    if rels:
        prompt += "\nRelationships: " + ", ".join(f"{k}: {v:+d}" for k, v in rels.items())

    vars_clean = {k: v for k, v in session.variables.items() if not k.startswith("_")}
    if vars_clean:
        prompt += "\nStory variables: " + ", ".join(f"{k}={v}" for k, v in vars_clean.items())

    prompt += (
        f"\n\nThis is scene {scene_number} of ~30. "
        "The player is ready. Generate MODE 2 (scene) JSON. "
        "Incorporate their preferences and conversation into the scene."
    )

    response = await _call_director(prompt)
    result = _parse_director_response(response)

    if result.get("type") != "scene":
        # Director didn't produce a scene — wrap as conversation
        _append_message(session, "director", result)
        _emit(event_queue, EVT_DIRECTOR_MESSAGE, result)
        return result

    # Process scene
    scene = _director_response_to_scene(result, len(session.scenes))
    for effect in scene.story_effects:
        if effect.type == "relationship" and effect.target in session.relationships:
            try:
                session.relationships[effect.target] += int(effect.value)
            except (ValueError, TypeError):
                pass
        elif effect.type in ("variable", "flag"):
            session.variables[effect.target] = effect.value

    scene_record = scene.model_dump()
    scene_record["director_note"] = result.get("director_note", "")
    session.scenes.append(scene_record)

    if scene.is_ending:
        session.is_ended = True

    session.touch()

    scene_idx = session.current_scene_index
    _emit(event_queue, EVT_IMAGE_STATUS, {"scene_index": scene_idx, "status": "pending"})
    await start_image_generation(session, scene_idx, scene.image_prompt)

    scene_data = scene.model_dump()
    scene_data["director_note"] = result.get("director_note", "")
    msg = {
        "type": "scene",
        "scene": scene_data,
        "director_note": result.get("director_note", ""),
    }
    _append_message(session, "director", msg)
    _emit(event_queue, EVT_SCENE_READY, scene_data)
    return msg


def _build_message_prompt(
    session: SessionState,
    user_text: str,
    conversation_history: str,
    scene_count: int,
    was_ready: bool,
) -> str:
    """Build the prompt for handling a user message."""
    prompt = f"WORLD: {session.world_context}\n\n"
    prompt += "CHARACTERS:\n"
    for c in session.characters:
        prompt += f"- {c['name']}: {c.get('personality', '')}. "
        if c.get("description"):
            prompt += f"{c['description']} "
        if c.get("appearance_summary"):
            prompt += f"Appearance: {c['appearance_summary']}"
        prompt += "\n"

    if session.story_summary:
        prompt += f"\nSTORY SO FAR (scenes played):\n{session.story_summary}\n"

    prefs = session.variables.get("_preferences", {})
    if isinstance(prefs, dict) and prefs:
        prompt += "\nKNOWN PREFERENCES: " + ", ".join(f"{k}={v}" for k, v in prefs.items()) + "\n"

    prompt += f"\nCONVERSATION:\n{conversation_history}\n"
    prompt += f"\nPLAYER SAYS: \"{user_text}\"\n"
    prompt += f"\nScenes completed: {scene_count}\n"

    if was_ready:
        prompt += (
            "\nYou previously indicated ready_to_generate=true. "
            "If the player's response confirms they're ready, generate a MODE 2 (scene). "
            "If they want to adjust something first, respond in MODE 1 (conversation)."
        )
    elif scene_count == 0:
        prompt += (
            "\nNo scenes yet. Continue conversation to understand what the player wants. "
            "When you have enough, set ready_to_generate=true. Output MODE 1 or MODE 2 JSON."
        )
    else:
        prompt += (
            "\nThe player is responding during gameplay. This could be a choice, "
            "a story direction, or a conversation. Interpret naturally and either "
            "continue the conversation (MODE 1) or generate the next scene (MODE 2)."
        )

    return prompt


async def _call_director(user_prompt: str) -> dict:
    """Call Ollama with the director system prompt."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "num_predict": 4096,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data.get("message", {}).get("content", "{}")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("Director returned invalid JSON: %s", content[:500])
        return {
            "type": "conversation",
            "message": "Let me think about that for a moment... What would you like to do?",
            "suggestions": ["Continue the story", "Tell me about the world", "Surprise me"],
            "detected_preferences": [],
            "ready_to_generate": False,
        }


def _parse_director_response(raw: dict) -> dict:
    """Normalize director response into a consistent format."""
    resp_type = raw.get("type", "conversation")
    if resp_type == "scene":
        return {
            "type": "scene",
            "narration": raw.get("narration", "The scene unfolds..."),
            "image_prompt": raw.get("image_prompt", "anime scene, detailed background"),
            "dialogue": raw.get("dialogue", []),
            "choices": raw.get("choices", [
                {"text": "Continue forward", "tone": "neutral"},
                {"text": "Take a different path", "tone": "cautious"},
            ]),
            "story_effects": raw.get("story_effects", []),
            "director_note": raw.get("director_note", ""),
            "is_ending": raw.get("is_ending", False),
            "ending_type": raw.get("ending_type"),
            "ready_to_generate": False,
        }
    return {
        "type": "conversation",
        "message": raw.get("message", "What would you like to do?"),
        "suggestions": raw.get("suggestions", []),
        "detected_preferences": raw.get("detected_preferences", []),
        "ready_to_generate": raw.get("ready_to_generate", False),
    }


def _director_response_to_scene(result: dict, scene_index: int) -> SceneData:
    """Convert a director MODE 2 response into a SceneData object."""
    from .engine import _parse_scene_response
    return _parse_scene_response(result, scene_index)


def _append_message(session: SessionState, role: str, content: dict):
    """Append a message to the session's conversation log."""
    messages = session.variables.get("_messages", [])
    if not isinstance(messages, list):
        messages = []
    messages.append({
        "role": role,
        "content": content,
        "timestamp": time.time(),
    })
    # Keep last 30 messages to avoid bloat
    if len(messages) > 30:
        messages = messages[-30:]
    session.variables["_messages"] = messages


def _get_conversation_summary(session: SessionState) -> str:
    """Build a condensed conversation summary for the AI prompt."""
    messages = session.variables.get("_messages", [])
    if not isinstance(messages, list):
        return ""
    lines = []
    for m in messages[-10:]:
        role = m.get("role", "?")
        content = m.get("content", {})
        if role == "user":
            text = content.get("message", str(content)) if isinstance(content, dict) else str(content)
            lines.append(f"Player: {text[:200]}")
        elif role == "director":
            if isinstance(content, dict):
                if content.get("type") == "scene":
                    note = content.get("director_note", "")
                    lines.append(f"[Scene generated{': ' + note if note else ''}]")
                else:
                    lines.append(f"Director: {content.get('message', '')[:200]}")
            else:
                lines.append(f"Director: {str(content)[:200]}")
    return "\n".join(lines)


def _get_last_director_message(session: SessionState) -> dict | None:
    """Get the most recent director message."""
    messages = session.variables.get("_messages", [])
    if not isinstance(messages, list):
        return None
    for m in reversed(messages):
        if m.get("role") == "director":
            return m.get("content", {})
    return None


def _emit(target, event_type: str, data: dict):
    """Emit event to queue(s). target can be Queue, SessionState, tuple of both, or None."""
    targets = target if isinstance(target, tuple) else (target,)
    for t in targets:
        if t is None:
            continue
        if isinstance(t, asyncio.Queue):
            try:
                t.put_nowait({"event": event_type, "data": data})
            except asyncio.QueueFull:
                pass
        elif isinstance(t, SessionState):
            for q in getattr(t, '_event_queues', []):
                try:
                    q.put_nowait({"event": event_type, "data": data})
                except asyncio.QueueFull:
                    pass


async def _store_preference_bg(preference: str, project_name: str):
    """Background task to store preference in Echo Brain."""
    try:
        await asyncio.to_thread(store_preference, preference, project_name)
    except Exception as e:
        logger.debug("Failed to store preference: %s", e)


async def _store_decision_bg(project_name: str, scene_number: int, decision: str):
    """Background task to store decision in Echo Brain."""
    try:
        await asyncio.to_thread(store_decision, project_name, scene_number, decision)
    except Exception as e:
        logger.debug("Failed to store decision: %s", e)
