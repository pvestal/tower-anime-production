"""EventBus — simple in-process async event emitter for cross-package coordination.

No external dependencies. Follows Echo Brain's autonomous/core.py pattern.

Usage:
    from packages.core.events import event_bus

    # Register handler (at module import or startup)
    @event_bus.on("image.rejected")
    async def handle_rejection(data):
        await learning_system.analyze_failure(data)

    # Emit event (at decision point)
    await event_bus.emit("image.rejected", {
        "character_slug": slug,
        "image_name": img_path.name,
        "quality_score": quality_score,
        "categories": categories,
    })
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Event type constants
IMAGE_GENERATED = "image.generated"
IMAGE_APPROVED = "image.approved"
IMAGE_REJECTED = "image.rejected"
GENERATION_SUBMITTED = "generation.submitted"
GENERATION_COMPLETED = "generation.completed"
FEEDBACK_RECORDED = "feedback.recorded"
REGENERATION_QUEUED = "regeneration.queued"
ECHO_BRAIN_CONSULTED = "echo_brain.consulted"
SHOT_GENERATED = "shot.generated"
SHOT_REJECTED = "shot.rejected"
FEEDBACK_SUBMITTED = "feedback.submitted"
FEEDBACK_ACTION_EXECUTED = "feedback.action_executed"

# Production orchestrator events
TRAINING_STARTED = "training.started"
TRAINING_COMPLETE = "training.complete"
SCENE_PLANNING_COMPLETE = "scene_planning.complete"
SCENE_READY = "scene.ready"
EPISODE_ASSEMBLED = "episode.assembled"
EPISODE_PUBLISHED = "episode.published"
PIPELINE_PHASE_ADVANCED = "pipeline.phase_advanced"

# Voice pipeline events
VOICE_SEGMENT_APPROVED = "voice.segment.approved"
VOICE_SEGMENT_REJECTED = "voice.segment.rejected"
VOICE_TRAINING_SUBMITTED = "voice.training.submitted"
VOICE_TRAINING_COMPLETED = "voice.training.completed"
VOICE_SYNTHESIS_COMPLETED = "voice.synthesis.completed"

# Narrative State Machine events
STATE_INITIALIZED = "state.initialized"
STATE_UPDATED = "state.updated"
STATE_PROPAGATED = "state.propagated"
SCENE_UPDATED = "scene.updated"
SHOT_UPDATED = "shot.updated"
EPISODE_UPDATED = "episode.updated"
REGENERATION_NEEDED = "regeneration.needed"


class EventBus:
    """Async event emitter. Handlers run concurrently via asyncio.gather."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._emit_count: int = 0
        self._error_count: int = 0

    def on(self, event: str):
        """Decorator to register an async handler for an event type."""
        def decorator(fn: Callable[..., Coroutine]):
            self._handlers[event].append(fn)
            logger.debug(f"EventBus: registered {fn.__name__} for '{event}'")
            return fn
        return decorator

    def subscribe(self, event: str, handler: Callable):
        """Imperative handler registration (alternative to decorator)."""
        self._handlers[event].append(handler)

    async def emit(self, event: str, data: dict[str, Any] | None = None):
        """Emit an event to all registered handlers. Errors logged, not raised."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        self._emit_count += 1
        data = data or {}
        data.setdefault("_event", event)
        data.setdefault("_timestamp", datetime.now().isoformat())

        results = await asyncio.gather(
            *(self._safe_call(h, data) for h in handlers),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._error_count += 1
                logger.error(
                    f"EventBus handler {handlers[i].__name__} failed on '{event}': {result}"
                )

    async def _safe_call(self, handler: Callable, data: dict):
        """Call handler, converting sync functions to async if needed."""
        result = handler(data)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def stats(self) -> dict:
        """Return bus statistics."""
        return {
            "registered_events": list(self._handlers.keys()),
            "total_handlers": sum(len(h) for h in self._handlers.values()),
            "total_emits": self._emit_count,
            "total_errors": self._error_count,
        }


# Module-level singleton
event_bus = EventBus()


def register_graph_sync_handlers():
    """Register graph sync handlers on the EventBus. Called once at startup."""
    from .graph_sync import (
        on_image_approved,
        on_image_rejected,
        on_generation_submitted,
        on_regeneration_queued,
        on_shot_generated,
    )
    event_bus.subscribe(IMAGE_APPROVED, on_image_approved)
    event_bus.subscribe(IMAGE_REJECTED, on_image_rejected)
    event_bus.subscribe(GENERATION_SUBMITTED, on_generation_submitted)
    event_bus.subscribe(REGENERATION_QUEUED, on_regeneration_queued)
    event_bus.subscribe(SHOT_GENERATED, on_shot_generated)
    logger.info("EventBus: graph sync handlers registered")


def register_sfx_handlers():
    """Register unified audio handler on SHOT_GENERATED. Called once at startup.

    Handles both foley SFX AND per-shot voice dialogue synthesis.
    """

    async def _auto_apply_audio(data: dict):
        """Auto-assign foley SFX + voice dialogue to a completed shot."""
        shot_id = data.get("shot_id")
        video_path = data.get("video_path")
        if not shot_id or not video_path:
            return

        try:
            from packages.scene_generation.sfx_mapper import (
                match_lora_to_sfx, match_lora_to_voice_lines,
                overlay_sfx_on_video, mix_voice_and_sfx,
                detect_pairing,
            )
            from packages.core.db import connect_direct

            conn = await connect_direct()
            try:
                row = await conn.fetchrow(
                    "SELECT s.lora_name, s.dialogue_text, s.dialogue_character_slug, "
                    "s.characters_present, sc.project_id "
                    "FROM shots s JOIN scenes sc ON s.scene_id = sc.id "
                    "WHERE s.id = $1", shot_id
                )
                if not row:
                    return

                lora_name = row["lora_name"]
                existing_dialogue = row["dialogue_text"]
                chars_present = row["characters_present"] or []
                project_id = row["project_id"]

                # Get project genre for anthro detection
                proj_row = await conn.fetchrow(
                    "SELECT genre, content_rating FROM projects WHERE id = $1", project_id
                )
                project_genre = proj_row["genre"] if proj_row else None

                # Build character gender map from DB
                char_genders = {}
                if chars_present:
                    char_rows = await conn.fetch(
                        "SELECT name, design_prompt FROM characters "
                        "WHERE name = ANY($1::text[])", chars_present
                    )
                    for cr in char_rows:
                        dp = (cr["design_prompt"] or "").lower()
                        gender = "male" if ("1boy" in dp or "male" in dp) else "female"
                        char_genders[cr["name"]] = gender

                # Detect pairing type (mm, ff, anthro, or None)
                pairing = detect_pairing(char_genders, project_genre)

                # --- Foley SFX ---
                sfx_clips = match_lora_to_sfx(lora_name, pairing=pairing)

                # --- Voice dialogue ---
                voice_wav = None
                voice_line = None
                voice_slug = None

                # Use existing dialogue_text if set, otherwise auto-generate from LoRA
                if existing_dialogue:
                    voice_line = existing_dialogue
                    voice_slug = row["dialogue_character_slug"]
                else:
                    voice_results = match_lora_to_voice_lines(
                        lora_name, char_genders, pairing=pairing
                    )
                    if voice_results:
                        # Pick the first character's line (usually female lead)
                        pick = voice_results[0]
                        voice_line = pick["line"]
                        voice_slug = pick["character_slug"]
                        # Save auto-generated dialogue to shot
                        await conn.execute(
                            "UPDATE shots SET dialogue_text = $2, dialogue_character_slug = $3 "
                            "WHERE id = $1", shot_id, voice_line, voice_slug
                        )

                # Synthesize voice if we have a line
                if voice_line and voice_slug:
                    try:
                        from packages.voice_pipeline.synthesis import synthesize_dialogue
                        result = await synthesize_dialogue(
                            character_slug=voice_slug,
                            text=voice_line,
                        )
                        if result.get("output_path"):
                            voice_wav = result["output_path"]
                            logger.info(
                                f"Shot {shot_id}: voice synthesized for {voice_slug}: "
                                f"{voice_line[:50]!r} ({result.get('engine_used')})"
                            )
                    except Exception as ve:
                        logger.warning(f"Shot {shot_id}: voice synthesis failed: {ve}")

                # --- Mix audio layers ---
                if voice_wav and sfx_clips:
                    output = mix_voice_and_sfx(video_path, voice_wav, sfx_clips)
                elif voice_wav:
                    # Voice only, no foley
                    from packages.scene_generation.sfx_mapper import mix_voice_and_sfx
                    output = mix_voice_and_sfx(video_path, voice_wav, [])
                elif sfx_clips:
                    output = overlay_sfx_on_video(video_path, sfx_clips)
                else:
                    return

                if output:
                    # Store mixed audio path + individual voice path
                    update_sql = "UPDATE shots SET sfx_audio_path = $2"
                    params = [shot_id, output]
                    if voice_wav:
                        update_sql += ", voice_audio_path = $3"
                        params.append(voice_wav)
                    update_sql += " WHERE id = $1"
                    await conn.execute(update_sql, *params)
                    parts = []
                    if sfx_clips:
                        parts.append(f"{len(sfx_clips)} foley")
                    if voice_wav:
                        parts.append("voice")
                    logger.info(f"Shot {shot_id}: audio applied ({', '.join(parts)}) → {output}")
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"Shot audio auto-apply failed for {shot_id}: {e}")

    event_bus.subscribe(SHOT_GENERATED, _auto_apply_audio)
    logger.info("EventBus: unified audio handler registered (foley + voice)")
