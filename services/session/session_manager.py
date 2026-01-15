"""
Session Manager for AI Director System.

Manages creative sessions that bridge the frontend director interface,
anime production pipeline, and Echo Brain conversational AI.

Features:
- Session lifecycle management (create, resume, pause, complete)
- Context caching for fast state loading
- Echo Brain conversation integration
- Director suggestions tracking
- Learning feedback collection
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


class SessionMode(Enum):
    """Current mode of the creative session."""
    PLANNING = "planning"
    DIRECTING = "directing"
    REVIEWING = "reviewing"
    GENERATING = "generating"


class SessionStatus(Enum):
    """Session lifecycle status."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    EXPIRED = "expired"


class SuggestionType(Enum):
    """Types of AI director suggestions."""
    POSE = "pose"
    CAMERA = "camera"
    LIGHTING = "lighting"
    PROMPT = "prompt"
    SEQUENCE = "sequence"
    STYLE = "style"
    TRANSITION = "transition"


class SuggestionStatus(Enum):
    """Status of director suggestions."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"


@dataclass
class CreativeSession:
    """Represents a creative session for the AI Director."""
    id: int
    session_uuid: str
    user_id: Optional[int]
    project_id: int

    # Echo Brain Integration
    echo_conversation_id: Optional[str] = None
    echo_session_state: Optional[Dict[str, Any]] = None

    # Creative State
    current_scene_id: Optional[int] = None
    current_mode: SessionMode = SessionMode.PLANNING
    current_character_ids: List[int] = field(default_factory=list)

    # Context Cache
    cached_context: Dict[str, Any] = field(default_factory=dict)

    # AI Memory
    director_notes: List[Dict[str, Any]] = field(default_factory=list)
    style_decisions: Dict[str, Any] = field(default_factory=dict)
    narrative_arc: Optional[str] = None
    prompt_history: List[Dict[str, Any]] = field(default_factory=list)

    # Activity
    interaction_count: int = 0
    last_interaction_type: Optional[str] = None
    generation_count: int = 0
    successful_generations: int = 0

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_interaction_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Status
    status: SessionStatus = SessionStatus.ACTIVE


@dataclass
class ContextSnapshot:
    """A snapshot of context changes."""
    id: int
    session_id: int
    context_key: str
    old_value: Optional[Any]
    new_value: Any
    change_source: str  # user, ai_suggestion, generation_result, system, auto
    change_reason: Optional[str]
    generation_id: Optional[int]
    created_at: datetime


@dataclass
class DirectorSuggestion:
    """An AI-generated suggestion for the director."""
    id: int
    session_id: int
    suggestion_type: SuggestionType
    suggestion_data: Dict[str, Any]
    explanation: Optional[str]
    confidence_score: Optional[float]
    model_used: Optional[str]
    status: SuggestionStatus
    user_response_at: Optional[datetime]
    user_modification: Optional[Dict[str, Any]]
    context_snapshot: Optional[Dict[str, Any]]
    created_at: datetime
    expires_at: datetime


class SessionManager:
    """
    Manages creative sessions for the AI Director system.

    Provides session lifecycle management, context caching,
    Echo Brain integration, and learning feedback collection.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._session_cache: Dict[str, CreativeSession] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._cache_timestamps: Dict[str, datetime] = {}

    # =========================================================================
    # SESSION LIFECYCLE
    # =========================================================================

    async def create_session(
        self,
        project_id: int,
        user_id: Optional[int] = None,
        echo_conversation_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> CreativeSession:
        """
        Create a new creative session.

        Args:
            project_id: The project this session belongs to
            user_id: Optional user ID
            echo_conversation_id: Optional Echo Brain conversation ID
            initial_context: Optional initial context data

        Returns:
            The created CreativeSession
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO creative_sessions (
                    project_id, user_id, echo_conversation_id,
                    cached_context, status
                )
                VALUES ($1, $2, $3, $4, 'active')
                RETURNING *
                """,
                project_id,
                user_id,
                echo_conversation_id,
                json.dumps(initial_context or {})
            )

            session = self._row_to_session(row)
            self._cache_session(session)

            logger.info(f"Created session {session.session_uuid} for project {project_id}")
            return session

    async def get_session(self, session_uuid: str) -> Optional[CreativeSession]:
        """
        Get a session by UUID.

        Args:
            session_uuid: The session UUID

        Returns:
            The session or None if not found
        """
        # Check cache first
        cached = self._get_cached_session(session_uuid)
        if cached:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM creative_sessions WHERE session_uuid = $1",
                uuid.UUID(session_uuid)
            )

            if not row:
                return None

            session = self._row_to_session(row)
            self._cache_session(session)
            return session

    async def get_or_create_session(
        self,
        project_id: int,
        user_id: Optional[int] = None
    ) -> CreativeSession:
        """
        Get an existing active session or create a new one.

        Args:
            project_id: The project ID
            user_id: Optional user ID

        Returns:
            An active session for the project
        """
        async with self.pool.acquire() as conn:
            # Use the database function
            row = await conn.fetchrow(
                "SELECT * FROM get_or_create_session($1, $2)",
                project_id,
                user_id
            )

            session = self._row_to_session(row)
            self._cache_session(session)
            return session

    async def get_session_with_context(self, session_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get session with all related context data.

        Args:
            session_uuid: The session UUID

        Returns:
            Full session context including snapshots, suggestions, and feedback
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT get_session_with_context($1)",
                uuid.UUID(session_uuid)
            )

            if result:
                return json.loads(result)
            return None

    async def update_session_mode(
        self,
        session_uuid: str,
        mode: SessionMode,
        reason: Optional[str] = None
    ) -> bool:
        """
        Update the session's current mode.

        Args:
            session_uuid: The session UUID
            mode: The new mode
            reason: Optional reason for the change

        Returns:
            True if updated successfully
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET current_mode = $1, last_interaction_type = 'mode_change'
                WHERE session_uuid = $2 AND status = 'active'
                """,
                mode.value,
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                # Record the change
                await self._record_context_change(
                    conn, session_uuid, "current_mode",
                    None, mode.value, "system", reason
                )
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def update_session_scene(
        self,
        session_uuid: str,
        scene_id: int,
        scene_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update the session's current scene.

        Args:
            session_uuid: The session UUID
            scene_id: The new scene ID
            scene_context: Optional context data for the scene

        Returns:
            True if updated successfully
        """
        async with self.pool.acquire() as conn:
            # Get current scene for snapshot
            old_scene = await conn.fetchval(
                "SELECT current_scene_id FROM creative_sessions WHERE session_uuid = $1",
                uuid.UUID(session_uuid)
            )

            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET current_scene_id = $1,
                    cached_context = cached_context || $2,
                    last_interaction_type = 'scene_change'
                WHERE session_uuid = $3 AND status = 'active'
                """,
                scene_id,
                json.dumps(scene_context or {}),
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                await self._record_context_change(
                    conn, session_uuid, "current_scene_id",
                    old_scene, scene_id, "user", None
                )
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def update_session_characters(
        self,
        session_uuid: str,
        character_ids: List[int]
    ) -> bool:
        """
        Update the characters in focus for the session.

        Args:
            session_uuid: The session UUID
            character_ids: List of character IDs to focus on

        Returns:
            True if updated successfully
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET current_character_ids = $1,
                    last_interaction_type = 'character_change'
                WHERE session_uuid = $2 AND status = 'active'
                """,
                character_ids,
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def pause_session(self, session_uuid: str) -> bool:
        """Pause an active session."""
        return await self._update_session_status(session_uuid, SessionStatus.PAUSED)

    async def resume_session(self, session_uuid: str) -> bool:
        """Resume a paused session."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET status = 'active',
                    expires_at = CURRENT_TIMESTAMP + INTERVAL '24 hours'
                WHERE session_uuid = $1 AND status = 'paused'
                """,
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def complete_session(self, session_uuid: str) -> bool:
        """Mark a session as completed."""
        return await self._update_session_status(session_uuid, SessionStatus.COMPLETED)

    async def archive_session(self, session_uuid: str) -> bool:
        """Archive a session."""
        return await self._update_session_status(session_uuid, SessionStatus.ARCHIVED)

    async def _update_session_status(
        self,
        session_uuid: str,
        status: SessionStatus
    ) -> bool:
        """Update session status."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET status = $1
                WHERE session_uuid = $2
                """,
                status.value,
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    # =========================================================================
    # CONTEXT MANAGEMENT
    # =========================================================================

    async def update_context(
        self,
        session_uuid: str,
        context_updates: Dict[str, Any],
        source: str = "user",
        reason: Optional[str] = None,
        generation_id: Optional[int] = None
    ) -> bool:
        """
        Update session context with change tracking.

        Args:
            session_uuid: The session UUID
            context_updates: Dictionary of context updates
            source: Source of the change (user, ai_suggestion, generation_result, system, auto)
            reason: Optional reason for the change
            generation_id: Optional linked generation ID

        Returns:
            True if updated successfully
        """
        async with self.pool.acquire() as conn:
            # Get current context
            current = await conn.fetchval(
                "SELECT cached_context FROM creative_sessions WHERE session_uuid = $1",
                uuid.UUID(session_uuid)
            )

            if current is None:
                return False

            current_context = json.loads(current) if current else {}

            # Record each change
            for key, new_value in context_updates.items():
                old_value = current_context.get(key)
                if old_value != new_value:
                    await self._record_context_change(
                        conn, session_uuid, key,
                        old_value, new_value, source, reason, generation_id
                    )

            # Merge updates
            current_context.update(context_updates)

            # Update session
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET cached_context = $1,
                    last_interaction_type = 'context_update'
                WHERE session_uuid = $2 AND status = 'active'
                """,
                json.dumps(current_context),
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def get_context(self, session_uuid: str) -> Optional[Dict[str, Any]]:
        """Get the cached context for a session."""
        session = await self.get_session(session_uuid)
        if session:
            return session.cached_context
        return None

    async def get_context_history(
        self,
        session_uuid: str,
        context_key: Optional[str] = None,
        limit: int = 50
    ) -> List[ContextSnapshot]:
        """
        Get context change history.

        Args:
            session_uuid: The session UUID
            context_key: Optional filter by context key
            limit: Maximum number of records

        Returns:
            List of context snapshots
        """
        async with self.pool.acquire() as conn:
            session = await self.get_session(session_uuid)
            if not session:
                return []

            if context_key:
                rows = await conn.fetch(
                    """
                    SELECT * FROM session_context_snapshots
                    WHERE session_id = $1 AND context_key = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    session.id, context_key, limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM session_context_snapshots
                    WHERE session_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    session.id, limit
                )

            return [self._row_to_snapshot(row) for row in rows]

    async def _record_context_change(
        self,
        conn: asyncpg.Connection,
        session_uuid: str,
        context_key: str,
        old_value: Any,
        new_value: Any,
        source: str,
        reason: Optional[str],
        generation_id: Optional[int] = None
    ):
        """Record a context change in the snapshots table."""
        session_id = await conn.fetchval(
            "SELECT id FROM creative_sessions WHERE session_uuid = $1",
            uuid.UUID(session_uuid)
        )

        if session_id:
            await conn.execute(
                """
                INSERT INTO session_context_snapshots (
                    session_id, context_key, old_value, new_value,
                    change_source, change_reason, generation_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                session_id,
                context_key,
                json.dumps(old_value) if old_value is not None else None,
                json.dumps(new_value),
                source,
                reason,
                generation_id
            )

    # =========================================================================
    # DIRECTOR SUGGESTIONS
    # =========================================================================

    async def create_suggestion(
        self,
        session_uuid: str,
        suggestion_type: SuggestionType,
        suggestion_data: Dict[str, Any],
        explanation: Optional[str] = None,
        confidence_score: Optional[float] = None,
        model_used: Optional[str] = None
    ) -> Optional[int]:
        """
        Create a new director suggestion.

        Args:
            session_uuid: The session UUID
            suggestion_type: Type of suggestion
            suggestion_data: The suggestion content
            explanation: Human-readable explanation
            confidence_score: AI confidence (0-1)
            model_used: Name of the model that generated this

        Returns:
            The suggestion ID or None if failed
        """
        session = await self.get_session(session_uuid)
        if not session:
            return None

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO director_suggestions (
                    session_id, suggestion_type, suggestion_data,
                    explanation, confidence_score, model_used,
                    context_snapshot
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                session.id,
                suggestion_type.value,
                json.dumps(suggestion_data),
                explanation,
                confidence_score,
                model_used,
                json.dumps(session.cached_context)
            )

            return row["id"] if row else None

    async def get_pending_suggestions(
        self,
        session_uuid: str,
        suggestion_type: Optional[SuggestionType] = None
    ) -> List[DirectorSuggestion]:
        """Get all pending suggestions for a session."""
        session = await self.get_session(session_uuid)
        if not session:
            return []

        async with self.pool.acquire() as conn:
            if suggestion_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM director_suggestions
                    WHERE session_id = $1
                    AND status = 'pending'
                    AND suggestion_type = $2
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY confidence_score DESC NULLS LAST
                    """,
                    session.id, suggestion_type.value
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM director_suggestions
                    WHERE session_id = $1
                    AND status = 'pending'
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY confidence_score DESC NULLS LAST
                    """,
                    session.id
                )

            return [self._row_to_suggestion(row) for row in rows]

    async def respond_to_suggestion(
        self,
        suggestion_id: int,
        accepted: bool,
        modification: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Record user response to a suggestion.

        Args:
            suggestion_id: The suggestion ID
            accepted: Whether the user accepted it
            modification: Optional modifications made

        Returns:
            True if updated successfully
        """
        status = "accepted" if accepted else "rejected"
        if modification:
            status = "modified"

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE director_suggestions
                SET status = $1,
                    user_response_at = CURRENT_TIMESTAMP,
                    user_modification = $2
                WHERE id = $3 AND status = 'pending'
                """,
                status,
                json.dumps(modification) if modification else None,
                suggestion_id
            )

            return "UPDATE 1" in result

    # =========================================================================
    # LEARNING FEEDBACK
    # =========================================================================

    async def record_generation_feedback(
        self,
        session_uuid: str,
        generation_id: int,
        prompt_used: str,
        enhanced_prompt: Optional[str],
        negative_prompt: Optional[str],
        generation_params: Dict[str, Any],
        quality_scores: Dict[str, float],
        character_ids: Optional[List[int]] = None,
        pose_ids: Optional[List[int]] = None,
        context_tags: Optional[List[str]] = None,
        style_tags: Optional[List[str]] = None
    ) -> Optional[int]:
        """
        Record feedback for a generation for the learning loop.

        Args:
            session_uuid: The session UUID
            generation_id: ID of the production job
            prompt_used: The original prompt
            enhanced_prompt: AI-enhanced version
            negative_prompt: Negative prompt used
            generation_params: All generation parameters
            quality_scores: Quality metrics from analyzer
            character_ids: Characters involved
            pose_ids: Poses used
            context_tags: Context tags for pattern matching
            style_tags: Style tags

        Returns:
            The feedback ID or None if failed
        """
        session = await self.get_session(session_uuid)
        if not session:
            return None

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO learning_feedback (
                    session_id, generation_id, prompt_used,
                    enhanced_prompt, negative_prompt,
                    generation_params, quality_scores,
                    character_ids, pose_ids,
                    context_tags, style_tags
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
                """,
                session.id,
                generation_id,
                prompt_used,
                enhanced_prompt,
                negative_prompt,
                json.dumps(generation_params),
                json.dumps(quality_scores),
                character_ids,
                pose_ids,
                context_tags,
                style_tags
            )

            # Update session generation counts
            await conn.execute(
                """
                UPDATE creative_sessions
                SET generation_count = generation_count + 1,
                    successful_generations = successful_generations +
                        CASE WHEN $1 >= 0.5 THEN 1 ELSE 0 END
                WHERE session_uuid = $2
                """,
                quality_scores.get("overall", 0),
                uuid.UUID(session_uuid)
            )

            self._invalidate_cache(session_uuid)
            return row["id"] if row else None

    async def add_user_feedback(
        self,
        feedback_id: int,
        rating: int,
        comments: Optional[str] = None,
        accepted: bool = True
    ) -> bool:
        """
        Add user feedback to a generation record.

        Args:
            feedback_id: The feedback record ID
            rating: User rating (1-5)
            comments: Optional user comments
            accepted: Whether user accepted the result

        Returns:
            True if updated successfully
        """
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE learning_feedback
                SET user_rating = $1,
                    user_comments = $2,
                    user_accepted = $3
                WHERE id = $4
                """,
                rating, comments, accepted, feedback_id
            )

            return "UPDATE 1" in result

    async def analyze_feedback(
        self,
        feedback_id: int,
        ai_analysis: Dict[str, Any],
        learned_patterns: List[str],
        confidence_adjustments: Dict[str, float],
        improvement_suggestions: List[str]
    ) -> bool:
        """
        Record AI analysis of generation feedback.

        Args:
            feedback_id: The feedback record ID
            ai_analysis: What worked/didn't work
            learned_patterns: Patterns extracted for future use
            confidence_adjustments: How this affects future suggestions
            improvement_suggestions: Suggestions for improvement

        Returns:
            True if updated successfully
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE learning_feedback
                SET ai_analysis = $1,
                    learned_patterns = $2,
                    confidence_adjustments = $3,
                    improvement_suggestions = $4,
                    analyzed_at = CURRENT_TIMESTAMP
                WHERE id = $5
                """,
                json.dumps(ai_analysis),
                learned_patterns,
                json.dumps(confidence_adjustments),
                improvement_suggestions,
                feedback_id
            )

            return "UPDATE 1" in result

    # =========================================================================
    # ECHO BRAIN INTEGRATION
    # =========================================================================

    async def link_echo_conversation(
        self,
        session_uuid: str,
        echo_conversation_id: str
    ) -> bool:
        """Link an Echo Brain conversation to a session."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET echo_conversation_id = $1
                WHERE session_uuid = $2 AND status = 'active'
                """,
                echo_conversation_id,
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def save_echo_state(
        self,
        session_uuid: str,
        echo_state: Dict[str, Any]
    ) -> bool:
        """Save Echo Brain session state."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET echo_session_state = $1
                WHERE session_uuid = $2
                """,
                json.dumps(echo_state),
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def get_echo_state(self, session_uuid: str) -> Optional[Dict[str, Any]]:
        """Get saved Echo Brain session state."""
        session = await self.get_session(session_uuid)
        if session:
            return session.echo_session_state
        return None

    # =========================================================================
    # DIRECTOR NOTES & MEMORY
    # =========================================================================

    async def add_director_note(
        self,
        session_uuid: str,
        note: str,
        note_type: str = "observation",
        related_generation_id: Optional[int] = None
    ) -> bool:
        """
        Add a director note to the session.

        Args:
            session_uuid: The session UUID
            note: The note content
            note_type: Type of note (observation, decision, reminder, etc.)
            related_generation_id: Optional linked generation

        Returns:
            True if added successfully
        """
        async with self.pool.acquire() as conn:
            # Get current notes
            current = await conn.fetchval(
                "SELECT director_notes FROM creative_sessions WHERE session_uuid = $1",
                uuid.UUID(session_uuid)
            )

            if current is None:
                return False

            notes = json.loads(current) if current else []
            notes.append({
                "note": note,
                "type": note_type,
                "generation_id": related_generation_id,
                "timestamp": datetime.utcnow().isoformat()
            })

            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET director_notes = $1
                WHERE session_uuid = $2
                """,
                json.dumps(notes),
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def update_style_decisions(
        self,
        session_uuid: str,
        style_updates: Dict[str, Any]
    ) -> bool:
        """Update style decisions for the session."""
        async with self.pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT style_decisions FROM creative_sessions WHERE session_uuid = $1",
                uuid.UUID(session_uuid)
            )

            if current is None:
                return False

            decisions = json.loads(current) if current else {}
            decisions.update(style_updates)

            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET style_decisions = $1
                WHERE session_uuid = $2
                """,
                json.dumps(decisions),
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    async def add_prompt_to_history(
        self,
        session_uuid: str,
        prompt: str,
        enhanced_prompt: Optional[str],
        generation_id: int,
        quality_score: Optional[float] = None
    ) -> bool:
        """Add a prompt to the session's history for learning."""
        async with self.pool.acquire() as conn:
            current = await conn.fetchval(
                "SELECT prompt_history FROM creative_sessions WHERE session_uuid = $1",
                uuid.UUID(session_uuid)
            )

            if current is None:
                return False

            history = json.loads(current) if current else []
            history.append({
                "prompt": prompt,
                "enhanced": enhanced_prompt,
                "generation_id": generation_id,
                "quality_score": quality_score,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Keep last 50 prompts
            if len(history) > 50:
                history = history[-50:]

            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET prompt_history = $1
                WHERE session_uuid = $2
                """,
                json.dumps(history),
                uuid.UUID(session_uuid)
            )

            if "UPDATE 1" in result:
                self._invalidate_cache(session_uuid)
                return True
            return False

    # =========================================================================
    # PATTERN RETRIEVAL
    # =========================================================================

    async def get_best_patterns(
        self,
        context_tags: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get the best prompt patterns for the current context.

        Args:
            context_tags: Optional context tags to filter by
            limit: Maximum patterns to return

        Returns:
            List of pattern dictionaries
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM get_best_patterns_for_context($1, $2)",
                context_tags or [],
                limit
            )

            return [dict(row) for row in rows]

    async def refresh_pattern_analysis(self) -> bool:
        """Refresh the materialized view for pattern analysis."""
        async with self.pool.acquire() as conn:
            await conn.execute("SELECT refresh_learning_patterns()")
            return True

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def expire_old_sessions(self, dry_run: bool = False) -> int:
        """
        Mark expired sessions.

        Args:
            dry_run: If True, just count without updating

        Returns:
            Number of sessions expired
        """
        async with self.pool.acquire() as conn:
            if dry_run:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM creative_sessions
                    WHERE status = 'active' AND expires_at < CURRENT_TIMESTAMP
                    """
                )
                return count or 0

            result = await conn.execute(
                """
                UPDATE creative_sessions
                SET status = 'expired'
                WHERE status = 'active' AND expires_at < CURRENT_TIMESTAMP
                """
            )

            # Parse the count from result
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                logger.info(f"Expired {count} sessions")
            return count

    # =========================================================================
    # CACHING HELPERS
    # =========================================================================

    def _cache_session(self, session: CreativeSession):
        """Add session to cache."""
        self._session_cache[session.session_uuid] = session
        self._cache_timestamps[session.session_uuid] = datetime.utcnow()

    def _get_cached_session(self, session_uuid: str) -> Optional[CreativeSession]:
        """Get session from cache if valid."""
        if session_uuid not in self._session_cache:
            return None

        timestamp = self._cache_timestamps.get(session_uuid)
        if timestamp and datetime.utcnow() - timestamp < self._cache_ttl:
            return self._session_cache[session_uuid]

        # Cache expired
        self._invalidate_cache(session_uuid)
        return None

    def _invalidate_cache(self, session_uuid: str):
        """Remove session from cache."""
        self._session_cache.pop(session_uuid, None)
        self._cache_timestamps.pop(session_uuid, None)

    # =========================================================================
    # ROW CONVERTERS
    # =========================================================================

    def _row_to_session(self, row: asyncpg.Record) -> CreativeSession:
        """Convert a database row to a CreativeSession."""
        return CreativeSession(
            id=row["id"],
            session_uuid=str(row["session_uuid"]),
            user_id=row["user_id"],
            project_id=row["project_id"],
            echo_conversation_id=row.get("echo_conversation_id"),
            echo_session_state=json.loads(row["echo_session_state"]) if row.get("echo_session_state") else None,
            current_scene_id=row.get("current_scene_id"),
            current_mode=SessionMode(row["current_mode"]) if row.get("current_mode") else SessionMode.PLANNING,
            current_character_ids=list(row["current_character_ids"]) if row.get("current_character_ids") else [],
            cached_context=json.loads(row["cached_context"]) if row.get("cached_context") else {},
            director_notes=json.loads(row["director_notes"]) if row.get("director_notes") else [],
            style_decisions=json.loads(row["style_decisions"]) if row.get("style_decisions") else {},
            narrative_arc=row.get("narrative_arc"),
            prompt_history=json.loads(row["prompt_history"]) if row.get("prompt_history") else [],
            interaction_count=row.get("interaction_count", 0),
            last_interaction_type=row.get("last_interaction_type"),
            generation_count=row.get("generation_count", 0),
            successful_generations=row.get("successful_generations", 0),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            last_interaction_at=row.get("last_interaction_at"),
            expires_at=row.get("expires_at"),
            status=SessionStatus(row["status"]) if row.get("status") else SessionStatus.ACTIVE
        )

    def _row_to_snapshot(self, row: asyncpg.Record) -> ContextSnapshot:
        """Convert a database row to a ContextSnapshot."""
        return ContextSnapshot(
            id=row["id"],
            session_id=row["session_id"],
            context_key=row["context_key"],
            old_value=json.loads(row["old_value"]) if row.get("old_value") else None,
            new_value=json.loads(row["new_value"]),
            change_source=row["change_source"],
            change_reason=row.get("change_reason"),
            generation_id=row.get("generation_id"),
            created_at=row["created_at"]
        )

    def _row_to_suggestion(self, row: asyncpg.Record) -> DirectorSuggestion:
        """Convert a database row to a DirectorSuggestion."""
        return DirectorSuggestion(
            id=row["id"],
            session_id=row["session_id"],
            suggestion_type=SuggestionType(row["suggestion_type"]),
            suggestion_data=json.loads(row["suggestion_data"]),
            explanation=row.get("explanation"),
            confidence_score=row.get("confidence_score"),
            model_used=row.get("model_used"),
            status=SuggestionStatus(row["status"]),
            user_response_at=row.get("user_response_at"),
            user_modification=json.loads(row["user_modification"]) if row.get("user_modification") else None,
            context_snapshot=json.loads(row["context_snapshot"]) if row.get("context_snapshot") else None,
            created_at=row["created_at"],
            expires_at=row["expires_at"]
        )


async def create_session_manager(database_url: str) -> SessionManager:
    """
    Factory function to create a SessionManager instance.

    Args:
        database_url: PostgreSQL connection string

    Returns:
        Initialized SessionManager
    """
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    return SessionManager(pool)
