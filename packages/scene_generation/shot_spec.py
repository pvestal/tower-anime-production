"""Shot Spec Enrichment — AI-driven pose/camera/emotion generation per shot.

Before video generation, this module enriches each shot with:
- A specific pose_type (from a vocabulary of body positions)
- must_differ_from UUIDs (recent shots with same character to avoid repetition)
- Enhanced generation_prompt with pose-aware, emotion-aware language
- Enhanced generation_negative with anti-sameness terms

Uses Ollama (gemma3:12b) for contextual shot spec generation.
"""

import json
import logging
from typing import Any

import asyncpg
import httpx

from packages.core.config import OLLAMA_URL

logger = logging.getLogger(__name__)

# Pose vocabulary — keyed by shot type, each list ordered by preference
POSE_VOCABULARY: dict[str, list[str]] = {
    "close-up": [
        "head tilt left", "head tilt right", "chin on hand", "looking over shoulder",
        "leaning forward", "eyes closed", "hand on cheek", "profile view",
    ],
    "medium": [
        "standing contrapposto", "arms crossed", "sitting relaxed", "leaning against wall",
        "hands in pockets", "one hand on hip", "three-quarter turn", "gesturing mid-speech",
    ],
    "wide": [
        "walking forward", "standing with arms spread", "crouching", "sitting on ground",
        "back turned half-profile", "mid-stride", "standing at threshold", "kneeling",
    ],
    "establishing": [
        "silhouette in doorway", "standing center frame", "walking away from camera",
        "small figure in landscape", "looking out window", "at desk from behind",
    ],
    "action": [
        "running full stride", "mid-jump", "crouching defensive", "throwing punch",
        "dodging", "reaching for something", "falling backwards", "bracing for impact",
    ],
    "extreme_close": [
        "eyes only", "lips and chin", "hand close-up", "tears forming",
        "clenched fist", "profile silhouette",
    ],
}

# Camera angles with their narrative connotations
CAMERA_ANGLES = [
    "eye-level", "low-angle", "high-angle", "dutch-angle",
    "over-the-shoulder", "bird's-eye", "worm's-eye",
]

# Emotional beat → camera/lighting suggestions
EMOTION_CAMERA_MAP: dict[str, dict[str, str]] = {
    "tension": {"camera": "dutch-angle", "lighting": "harsh side lighting"},
    "intimacy": {"camera": "close eye-level", "lighting": "warm soft lighting"},
    "power": {"camera": "low-angle", "lighting": "dramatic backlight"},
    "vulnerability": {"camera": "high-angle", "lighting": "cold diffused lighting"},
    "comedy": {"camera": "eye-level wide", "lighting": "bright even lighting"},
    "revelation": {"camera": "push-in close-up", "lighting": "spotlight emerging from shadow"},
    "isolation": {"camera": "extreme wide", "lighting": "muted desaturated"},
    "confrontation": {"camera": "over-the-shoulder", "lighting": "split lighting"},
}


async def enrich_shot_spec(
    conn: asyncpg.Connection,
    shot_row: dict[str, Any],
    scene_context: dict[str, Any],
    prev_shots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Enrich a shot with AI-generated pose, camera, and emotion-aware prompts.

    Args:
        conn: DB connection (for writing back enriched fields)
        shot_row: Full shot row from DB
        scene_context: Scene mood/location/time_of_day
        prev_shots: Previous N shots in this scene (for variety enforcement)

    Returns:
        Dict with enriched fields: pose_type, must_differ_from, generation_prompt, generation_negative
    """
    shot_id = shot_row["id"]
    shot_type = shot_row.get("shot_type") or "medium"
    camera_angle = shot_row.get("camera_angle") or "eye-level"
    emotional_beat = shot_row.get("emotional_beat") or ""
    viewer_feel = shot_row.get("viewer_should_feel") or ""
    current_prompt = shot_row.get("generation_prompt") or ""
    current_negative = shot_row.get("generation_negative") or ""
    characters = shot_row.get("characters_present") or []

    # Build must_differ_from: recent shots with overlapping characters
    must_differ_from = []
    recent_poses_used = []
    for ps in prev_shots:
        ps_chars = ps.get("characters_present") or []
        if any(c in ps_chars for c in characters):
            if ps.get("id"):
                must_differ_from.append(ps["id"])
            if ps.get("pose_type"):
                recent_poses_used.append(ps["pose_type"])

    # Get available poses for this shot type, excluding recently used
    available_poses = POSE_VOCABULARY.get(shot_type, POSE_VOCABULARY["medium"])
    filtered_poses = [p for p in available_poses if p not in recent_poses_used]
    if not filtered_poses:
        filtered_poses = available_poses  # Reset if all exhausted

    # Get emotion-based camera/lighting suggestion
    emotion_suggest = {}
    if emotional_beat:
        for key, val in EMOTION_CAMERA_MAP.items():
            if key in emotional_beat.lower():
                emotion_suggest = val
                break

    # Build Ollama prompt for shot spec enrichment
    ollama_prompt = _build_enrichment_prompt(
        shot_type=shot_type,
        camera_angle=camera_angle,
        emotional_beat=emotional_beat,
        viewer_feel=viewer_feel,
        scene_mood=scene_context.get("mood", ""),
        scene_location=scene_context.get("location", ""),
        characters=characters,
        current_prompt=current_prompt,
        available_poses=filtered_poses,
        recent_poses=recent_poses_used,
        emotion_suggest=emotion_suggest,
    )

    # Call Ollama for enrichment
    enriched = await _call_ollama_enrichment(ollama_prompt)

    # Fallback: if Ollama fails, pick first available pose
    pose_type = enriched.get("pose_type") or (filtered_poses[0] if filtered_poses else "standing contrapposto")
    enhanced_prompt = enriched.get("enhanced_prompt") or current_prompt
    enhanced_negative = enriched.get("enhanced_negative") or current_negative

    # Add anti-sameness terms to negative if must_differ_from is populated
    if must_differ_from and recent_poses_used:
        anti_terms = ", ".join(f"no {p}" for p in recent_poses_used[:3])
        if anti_terms not in enhanced_negative:
            enhanced_negative = f"{enhanced_negative}, {anti_terms}, no stiff straight standing pose".strip(", ")

    # Write enriched fields back to DB
    await conn.execute("""
        UPDATE shots SET
            pose_type = $2,
            pose_vocabulary = $3,
            must_differ_from = $4,
            generation_prompt = $5,
            generation_negative = $6
        WHERE id = $1
    """, shot_id, pose_type, filtered_poses, must_differ_from,
        enhanced_prompt, enhanced_negative)

    logger.info(f"Shot {shot_id}: enriched pose={pose_type}, must_differ_from={len(must_differ_from)} shots")

    return {
        "pose_type": pose_type,
        "must_differ_from": must_differ_from,
        "generation_prompt": enhanced_prompt,
        "generation_negative": enhanced_negative,
    }


def _build_enrichment_prompt(
    shot_type: str,
    camera_angle: str,
    emotional_beat: str,
    viewer_feel: str,
    scene_mood: str,
    scene_location: str,
    characters: list[str],
    current_prompt: str,
    available_poses: list[str],
    recent_poses: list[str],
    emotion_suggest: dict[str, str],
) -> str:
    """Build the Ollama prompt for shot spec enrichment."""
    chars_str = ", ".join(characters) if characters else "unknown character"
    poses_str = ", ".join(available_poses)
    recent_str = ", ".join(recent_poses) if recent_poses else "none"
    emotion_camera = emotion_suggest.get("camera", "")
    emotion_lighting = emotion_suggest.get("lighting", "")

    return f"""You are a cinematography director for anime production. Enrich this shot specification.

SCENE CONTEXT:
- Location: {scene_location}
- Mood: {scene_mood}
- Characters: {chars_str}

SHOT DETAILS:
- Type: {shot_type}
- Camera angle: {camera_angle}
- Emotional beat: {emotional_beat}
- Viewer should feel: {viewer_feel}
- Current prompt: {current_prompt}

POSE VARIETY:
- Available poses: {poses_str}
- Recently used (AVOID THESE): {recent_str}
{f'- Suggested camera for emotion: {emotion_camera}' if emotion_camera else ''}
{f'- Suggested lighting: {emotion_lighting}' if emotion_lighting else ''}

INSTRUCTIONS:
1. Pick ONE pose_type from the available poses that best fits the emotional beat and shot type.
2. Write an enhanced_prompt that adds the pose, body language, and emotion-specific visual cues to the current prompt. Keep the existing content, just enrich it.
3. Write enhanced_negative with terms to avoid (including recently used poses and generic stiff poses).

Respond ONLY with valid JSON:
{{"pose_type": "chosen pose", "enhanced_prompt": "enriched prompt text", "enhanced_negative": "negative prompt text"}}"""


async def _call_ollama_enrichment(prompt: str) -> dict[str, Any]:
    """Call Ollama gemma3:12b for shot spec enrichment. Returns parsed JSON or empty dict."""
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": "gemma3:12b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 512,
                    },
                },
            )
            if resp.status_code != 200:
                logger.warning(f"Ollama enrichment failed: HTTP {resp.status_code}")
                return {}

            response_text = resp.json().get("response", "")
            # Extract JSON from response (may have markdown fences)
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Ollama enrichment: invalid JSON response: {e}")
        return {}
    except httpx.TimeoutException:
        logger.warning("Ollama enrichment: timed out (90s)")
        return {}
    except Exception as e:
        logger.warning(f"Ollama enrichment failed: {type(e).__name__}: {e}")
        return {}


async def get_scene_context(conn: asyncpg.Connection, scene_id) -> dict[str, Any]:
    """Fetch scene context for shot enrichment."""
    row = await conn.fetchrow("""
        SELECT mood, location, time_of_day, weather, title
        FROM scenes WHERE id = $1
    """, scene_id)
    if not row:
        return {}
    return dict(row)


async def get_recent_shots(conn: asyncpg.Connection, scene_id, limit: int = 5) -> list[dict]:
    """Fetch recent completed/generating shots in a scene for variety comparison."""
    rows = await conn.fetch("""
        SELECT id, shot_number, shot_type, camera_angle, pose_type,
               characters_present, generation_prompt
        FROM shots
        WHERE scene_id = $1 AND status IN ('completed', 'generating')
        ORDER BY shot_number DESC
        LIMIT $2
    """, scene_id, limit)
    return [dict(r) for r in rows]
