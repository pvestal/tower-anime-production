"""
Shot Assembler for Tower Anime Production.

Handles scene assembly from individual shots, including transitions,
background persistence, and audio synchronization.
"""

import asyncio
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class TransitionType(Enum):
    """Types of transitions between shots."""
    CUT = "cut"                    # Instant cut (no transition)
    FADE = "fade"                  # Fade to black then to next shot
    CROSSFADE = "crossfade"        # Dissolve from one shot to next
    WIPE_LEFT = "wipe_left"        # Wipe transition from right to left
    WIPE_RIGHT = "wipe_right"      # Wipe transition from left to right
    WIPE_UP = "wipe_up"            # Wipe transition from bottom to top
    WIPE_DOWN = "wipe_down"        # Wipe transition from top to bottom
    ZOOM_IN = "zoom_in"            # Zoom into next shot
    ZOOM_OUT = "zoom_out"          # Zoom out to next shot
    SLIDE_LEFT = "slide_left"      # Slide next shot in from right
    SLIDE_RIGHT = "slide_right"    # Slide next shot in from left


class AudioTrackType(Enum):
    """Types of audio tracks."""
    DIALOGUE = "dialogue"
    MUSIC = "music"
    SFX = "sfx"
    AMBIENT = "ambient"
    VOICEOVER = "voiceover"


@dataclass
class Shot:
    """A single shot in the assembly."""
    id: int
    video_path: str
    duration_ms: int
    start_time_ms: int = 0
    end_time_ms: Optional[int] = None
    scene_id: Optional[int] = None
    character_ids: List[int] = field(default_factory=list)
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioTrack:
    """An audio track to sync with video."""
    id: int
    audio_path: str
    track_type: AudioTrackType
    start_time_ms: int
    duration_ms: Optional[int] = None
    volume: float = 1.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransitionSpec:
    """Specification for a transition between shots."""
    transition_type: TransitionType
    duration_ms: int = 500
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssemblyResult:
    """Result of scene assembly."""
    output_path: str
    duration_ms: int
    shots_count: int
    transitions_count: int
    audio_tracks_count: int
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ShotAssembler:
    """
    Assembles shots into complete scenes with transitions and audio.

    Features:
    - Shot stitching with configurable transitions
    - Background persistence across shots in a scene
    - Multi-track audio synchronization
    - Timeline-based assembly with ffmpeg
    """

    def __init__(
        self,
        database_url: str,
        output_dir: str = "/mnt/1TB-storage/ComfyUI/output/assembled",
        temp_dir: str = "/tmp/shot_assembly"
    ):
        """
        Initialize Shot Assembler.

        Args:
            database_url: PostgreSQL connection URL
            output_dir: Directory for assembled output
            temp_dir: Directory for temporary files during assembly
        """
        self.database_url = database_url
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.pool = None

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> None:
        """Initialize database connection pool."""
        import asyncpg
        self.pool = await asyncpg.create_pool(self.database_url)
        await self._ensure_tables()
        logger.info("ShotAssembler connected to database")

    async def close(self) -> None:
        """Close database connections."""
        if self.pool:
            await self.pool.close()

    async def _ensure_tables(self) -> None:
        """Create assembly tables if they don't exist."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS shot_assemblies (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    scene_id INTEGER,
                    episode_id INTEGER,
                    project_id INTEGER,
                    output_path VARCHAR(500),
                    duration_ms INTEGER,
                    status VARCHAR(50) DEFAULT 'pending',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS assembly_shots (
                    id SERIAL PRIMARY KEY,
                    assembly_id INTEGER REFERENCES shot_assemblies(id) ON DELETE CASCADE,
                    shot_order INTEGER NOT NULL,
                    video_path VARCHAR(500) NOT NULL,
                    start_time_ms INTEGER DEFAULT 0,
                    end_time_ms INTEGER,
                    duration_ms INTEGER NOT NULL,
                    transition_type VARCHAR(50) DEFAULT 'cut',
                    transition_duration_ms INTEGER DEFAULT 0,
                    transition_params JSONB DEFAULT '{}',
                    metadata JSONB DEFAULT '{}',

                    UNIQUE(assembly_id, shot_order)
                );

                CREATE TABLE IF NOT EXISTS assembly_audio_tracks (
                    id SERIAL PRIMARY KEY,
                    assembly_id INTEGER REFERENCES shot_assemblies(id) ON DELETE CASCADE,
                    track_type VARCHAR(50) NOT NULL,
                    audio_path VARCHAR(500) NOT NULL,
                    start_time_ms INTEGER NOT NULL,
                    duration_ms INTEGER,
                    volume FLOAT DEFAULT 1.0,
                    fade_in_ms INTEGER DEFAULT 0,
                    fade_out_ms INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS scene_backgrounds (
                    id SERIAL PRIMARY KEY,
                    scene_id INTEGER NOT NULL,
                    background_image_path VARCHAR(500) NOT NULL,
                    depth_map_path VARCHAR(500),
                    parallax_enabled BOOLEAN DEFAULT FALSE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),

                    UNIQUE(scene_id)
                );

                CREATE INDEX IF NOT EXISTS idx_assembly_shots_assembly ON assembly_shots(assembly_id);
                CREATE INDEX IF NOT EXISTS idx_assembly_audio_assembly ON assembly_audio_tracks(assembly_id);
            """)

    # === Assembly Creation ===

    async def create_assembly(
        self,
        name: str,
        scene_id: Optional[int] = None,
        episode_id: Optional[int] = None,
        project_id: Optional[int] = None
    ) -> int:
        """
        Create a new shot assembly.

        Args:
            name: Assembly name
            scene_id: Associated scene ID
            episode_id: Associated episode ID
            project_id: Associated project ID

        Returns:
            Assembly ID
        """
        async with self.pool.acquire() as conn:
            assembly_id = await conn.fetchval("""
                INSERT INTO shot_assemblies (name, scene_id, episode_id, project_id, status)
                VALUES ($1, $2, $3, $4, 'pending')
                RETURNING id
            """, name, scene_id, episode_id, project_id)

        logger.info(f"Created assembly '{name}' with ID {assembly_id}")
        return assembly_id

    async def add_shot(
        self,
        assembly_id: int,
        video_path: str,
        duration_ms: int,
        shot_order: Optional[int] = None,
        start_time_ms: int = 0,
        end_time_ms: Optional[int] = None,
        transition: Optional[TransitionSpec] = None,
        metadata: Dict = None
    ) -> int:
        """
        Add a shot to the assembly.

        Args:
            assembly_id: Assembly ID
            video_path: Path to shot video
            duration_ms: Shot duration in milliseconds
            shot_order: Order in sequence (auto-assigned if None)
            start_time_ms: Start offset within source video
            end_time_ms: End offset within source video
            transition: Transition to next shot
            metadata: Additional metadata

        Returns:
            Shot ID
        """
        async with self.pool.acquire() as conn:
            # Auto-assign order if not specified
            if shot_order is None:
                max_order = await conn.fetchval("""
                    SELECT COALESCE(MAX(shot_order), -1) FROM assembly_shots
                    WHERE assembly_id = $1
                """, assembly_id)
                shot_order = max_order + 1

            transition_type = transition.transition_type.value if transition else "cut"
            transition_duration = transition.duration_ms if transition else 0
            transition_params = transition.parameters if transition else {}

            shot_id = await conn.fetchval("""
                INSERT INTO assembly_shots
                (assembly_id, shot_order, video_path, start_time_ms, end_time_ms,
                 duration_ms, transition_type, transition_duration_ms, transition_params, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (assembly_id, shot_order) DO UPDATE SET
                    video_path = EXCLUDED.video_path,
                    start_time_ms = EXCLUDED.start_time_ms,
                    end_time_ms = EXCLUDED.end_time_ms,
                    duration_ms = EXCLUDED.duration_ms,
                    transition_type = EXCLUDED.transition_type,
                    transition_duration_ms = EXCLUDED.transition_duration_ms,
                    transition_params = EXCLUDED.transition_params,
                    metadata = EXCLUDED.metadata
                RETURNING id
            """,
                assembly_id,
                shot_order,
                video_path,
                start_time_ms,
                end_time_ms,
                duration_ms,
                transition_type,
                transition_duration,
                json.dumps(transition_params),
                json.dumps(metadata or {})
            )

        logger.info(f"Added shot {shot_order} to assembly {assembly_id}")
        return shot_id

    async def add_audio_track(
        self,
        assembly_id: int,
        audio_path: str,
        track_type: AudioTrackType,
        start_time_ms: int,
        duration_ms: Optional[int] = None,
        volume: float = 1.0,
        fade_in_ms: int = 0,
        fade_out_ms: int = 0,
        metadata: Dict = None
    ) -> int:
        """
        Add an audio track to the assembly.

        Args:
            assembly_id: Assembly ID
            audio_path: Path to audio file
            track_type: Type of audio track
            start_time_ms: When audio starts in timeline
            duration_ms: Audio duration (uses full file if None)
            volume: Volume multiplier (0.0 to 1.0+)
            fade_in_ms: Fade in duration
            fade_out_ms: Fade out duration
            metadata: Additional metadata

        Returns:
            Audio track ID
        """
        async with self.pool.acquire() as conn:
            track_id = await conn.fetchval("""
                INSERT INTO assembly_audio_tracks
                (assembly_id, track_type, audio_path, start_time_ms, duration_ms,
                 volume, fade_in_ms, fade_out_ms, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """,
                assembly_id,
                track_type.value,
                audio_path,
                start_time_ms,
                duration_ms,
                volume,
                fade_in_ms,
                fade_out_ms,
                json.dumps(metadata or {})
            )

        logger.info(f"Added {track_type.value} audio track to assembly {assembly_id}")
        return track_id

    # === Background Management ===

    async def set_scene_background(
        self,
        scene_id: int,
        background_image_path: str,
        depth_map_path: Optional[str] = None,
        parallax_enabled: bool = False,
        metadata: Dict = None
    ) -> None:
        """
        Set persistent background for a scene.

        This background can be composited behind all shots in the scene.

        Args:
            scene_id: Scene ID
            background_image_path: Path to background image
            depth_map_path: Optional depth map for parallax effects
            parallax_enabled: Enable parallax scrolling
            metadata: Additional metadata
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scene_backgrounds
                (scene_id, background_image_path, depth_map_path, parallax_enabled, metadata)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (scene_id) DO UPDATE SET
                    background_image_path = EXCLUDED.background_image_path,
                    depth_map_path = EXCLUDED.depth_map_path,
                    parallax_enabled = EXCLUDED.parallax_enabled,
                    metadata = EXCLUDED.metadata
            """,
                scene_id,
                background_image_path,
                depth_map_path,
                parallax_enabled,
                json.dumps(metadata or {})
            )

        logger.info(f"Set background for scene {scene_id}")

    async def get_scene_background(self, scene_id: int) -> Optional[Dict]:
        """Get background info for a scene."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM scene_backgrounds WHERE scene_id = $1
            """, scene_id)

        if not row:
            return None

        return {
            "scene_id": row["scene_id"],
            "background_image_path": row["background_image_path"],
            "depth_map_path": row["depth_map_path"],
            "parallax_enabled": row["parallax_enabled"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
        }

    # === Assembly Execution ===

    async def assemble(
        self,
        assembly_id: int,
        output_filename: Optional[str] = None,
        include_background: bool = True,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        fps: int = 30,
        resolution: Tuple[int, int] = (1920, 1080)
    ) -> AssemblyResult:
        """
        Execute the assembly and produce final video.

        Args:
            assembly_id: Assembly ID to process
            output_filename: Output filename (auto-generated if None)
            include_background: Include scene background if available
            video_codec: Video codec for output
            audio_codec: Audio codec for output
            fps: Output frame rate
            resolution: Output resolution (width, height)

        Returns:
            AssemblyResult with output path and status
        """
        try:
            # Get assembly info
            async with self.pool.acquire() as conn:
                assembly = await conn.fetchrow(
                    "SELECT * FROM shot_assemblies WHERE id = $1", assembly_id
                )
                if not assembly:
                    raise ValueError(f"Assembly {assembly_id} not found")

                # Get shots
                shots = await conn.fetch("""
                    SELECT * FROM assembly_shots
                    WHERE assembly_id = $1
                    ORDER BY shot_order
                """, assembly_id)

                # Get audio tracks
                audio_tracks = await conn.fetch("""
                    SELECT * FROM assembly_audio_tracks
                    WHERE assembly_id = $1
                """, assembly_id)

            if not shots:
                raise ValueError("No shots in assembly")

            # Update status
            await self._update_assembly_status(assembly_id, "processing")

            # Generate output filename
            if output_filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"assembly_{assembly_id}_{timestamp}.mp4"

            output_path = self.output_dir / output_filename

            # Build and execute ffmpeg command
            result = await self._execute_assembly(
                assembly_id=assembly_id,
                shots=shots,
                audio_tracks=audio_tracks,
                output_path=str(output_path),
                scene_id=assembly["scene_id"],
                include_background=include_background,
                video_codec=video_codec,
                audio_codec=audio_codec,
                fps=fps,
                resolution=resolution
            )

            # Update assembly record
            if result.success:
                await self._update_assembly_completed(
                    assembly_id, str(output_path), result.duration_ms
                )
            else:
                await self._update_assembly_status(assembly_id, "failed")

            return result

        except Exception as e:
            logger.error(f"Assembly failed: {e}")
            await self._update_assembly_status(assembly_id, "failed")
            return AssemblyResult(
                output_path="",
                duration_ms=0,
                shots_count=0,
                transitions_count=0,
                audio_tracks_count=0,
                success=False,
                error=str(e)
            )

    async def _execute_assembly(
        self,
        assembly_id: int,
        shots: List,
        audio_tracks: List,
        output_path: str,
        scene_id: Optional[int],
        include_background: bool,
        video_codec: str,
        audio_codec: str,
        fps: int,
        resolution: Tuple[int, int]
    ) -> AssemblyResult:
        """Execute the actual assembly using ffmpeg."""

        width, height = resolution
        filter_complex_parts = []
        inputs = []
        input_idx = 0

        # Get background if needed
        background = None
        if include_background and scene_id:
            background = await self.get_scene_background(scene_id)

        # Add background as first input if available
        if background:
            inputs.extend(["-loop", "1", "-i", background["background_image_path"]])
            bg_idx = input_idx
            input_idx += 1
        else:
            bg_idx = None

        # Add shot inputs
        shot_indices = []
        for shot in shots:
            inputs.extend(["-i", shot["video_path"]])
            shot_indices.append(input_idx)
            input_idx += 1

        # Add audio inputs
        audio_indices = []
        for track in audio_tracks:
            inputs.extend(["-i", track["audio_path"]])
            audio_indices.append(input_idx)
            input_idx += 1

        # Build filter complex for video
        video_filters = []
        current_stream = None
        transitions_count = 0

        for i, (shot, shot_idx) in enumerate(zip(shots, shot_indices)):
            # Scale and trim shot
            trim_start = shot["start_time_ms"] / 1000
            duration = shot["duration_ms"] / 1000

            scale_filter = f"[{shot_idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,trim=start={trim_start}:duration={duration},setpts=PTS-STARTPTS[v{i}]"
            video_filters.append(scale_filter)

            if current_stream is None:
                current_stream = f"v{i}"
            else:
                # Apply transition
                transition_type = shot["transition_type"]
                transition_duration = shot["transition_duration_ms"] / 1000

                if transition_type == "cut" or transition_duration == 0:
                    # Simple concat
                    video_filters.append(
                        f"[{current_stream}][v{i}]concat=n=2:v=1:a=0[vout{i}]"
                    )
                elif transition_type == "crossfade":
                    # Crossfade transition
                    video_filters.append(
                        f"[{current_stream}][v{i}]xfade=transition=fade:duration={transition_duration}:offset={duration - transition_duration}[vout{i}]"
                    )
                    transitions_count += 1
                elif transition_type == "fade":
                    # Fade through black
                    video_filters.append(
                        f"[{current_stream}]fade=t=out:st={duration - transition_duration}:d={transition_duration}[fade_out{i}]"
                    )
                    video_filters.append(
                        f"[v{i}]fade=t=in:st=0:d={transition_duration}[fade_in{i}]"
                    )
                    video_filters.append(
                        f"[fade_out{i}][fade_in{i}]concat=n=2:v=1:a=0[vout{i}]"
                    )
                    transitions_count += 1
                elif transition_type.startswith("wipe"):
                    # Wipe transitions
                    wipe_dir = transition_type.split("_")[1]
                    wipe_map = {"left": "wipeleft", "right": "wiperight", "up": "wipeup", "down": "wipedown"}
                    xfade_type = wipe_map.get(wipe_dir, "fade")
                    video_filters.append(
                        f"[{current_stream}][v{i}]xfade=transition={xfade_type}:duration={transition_duration}:offset={duration - transition_duration}[vout{i}]"
                    )
                    transitions_count += 1
                else:
                    # Default to concat
                    video_filters.append(
                        f"[{current_stream}][v{i}]concat=n=2:v=1:a=0[vout{i}]"
                    )

                current_stream = f"vout{i}"

        # Build audio mix filter
        audio_filters = []
        if audio_tracks:
            # Process each audio track
            audio_streams = []
            for j, (track, track_idx) in enumerate(zip(audio_tracks, audio_indices)):
                volume = track["volume"]
                start_ms = track["start_time_ms"]
                fade_in = track["fade_in_ms"] / 1000
                fade_out = track["fade_out_ms"] / 1000
                delay_ms = start_ms

                # Build audio filter chain
                a_filter = f"[{track_idx}:a]"

                if volume != 1.0:
                    a_filter = f"[{track_idx}:a]volume={volume}"

                if fade_in > 0:
                    a_filter += f",afade=t=in:st=0:d={fade_in}"

                if fade_out > 0 and track["duration_ms"]:
                    fade_start = (track["duration_ms"] / 1000) - fade_out
                    a_filter += f",afade=t=out:st={fade_start}:d={fade_out}"

                if delay_ms > 0:
                    a_filter += f",adelay={delay_ms}|{delay_ms}"

                a_filter += f"[a{j}]"
                audio_filters.append(a_filter)
                audio_streams.append(f"[a{j}]")

            # Mix all audio streams
            if len(audio_streams) > 1:
                audio_filters.append(
                    f"{''.join(audio_streams)}amix=inputs={len(audio_streams)}:duration=longest[aout]"
                )
                final_audio = "[aout]"
            else:
                final_audio = audio_streams[0]
        else:
            final_audio = None

        # Combine all filters
        all_filters = video_filters + audio_filters
        filter_complex = ";".join(all_filters)

        # Build ffmpeg command
        cmd = ["ffmpeg", "-y"]
        cmd.extend(inputs)

        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex])

        # Map outputs
        cmd.extend(["-map", f"[{current_stream}]"])
        if final_audio:
            cmd.extend(["-map", final_audio])

        # Output settings
        cmd.extend([
            "-c:v", video_codec,
            "-preset", "medium",
            "-crf", "23",
            "-r", str(fps)
        ])

        if final_audio:
            cmd.extend(["-c:a", audio_codec, "-b:a", "192k"])

        cmd.append(output_path)

        logger.info(f"Executing assembly: {' '.join(cmd[:20])}...")

        # Execute ffmpeg
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return AssemblyResult(
                    output_path="",
                    duration_ms=0,
                    shots_count=len(shots),
                    transitions_count=transitions_count,
                    audio_tracks_count=len(audio_tracks),
                    success=False,
                    error=result.stderr[:500]
                )

            # Calculate total duration
            total_duration_ms = sum(shot["duration_ms"] for shot in shots)
            # Subtract transition overlap
            total_duration_ms -= sum(
                shot["transition_duration_ms"]
                for shot in shots[1:]
                if shot["transition_type"] != "cut"
            )

            return AssemblyResult(
                output_path=output_path,
                duration_ms=total_duration_ms,
                shots_count=len(shots),
                transitions_count=transitions_count,
                audio_tracks_count=len(audio_tracks),
                success=True
            )

        except subprocess.TimeoutExpired:
            return AssemblyResult(
                output_path="",
                duration_ms=0,
                shots_count=len(shots),
                transitions_count=transitions_count,
                audio_tracks_count=len(audio_tracks),
                success=False,
                error="Assembly timed out"
            )

    # === Convenience Methods ===

    async def assemble_shots_simple(
        self,
        video_paths: List[str],
        output_filename: str,
        transition: TransitionType = TransitionType.CUT,
        transition_duration_ms: int = 500
    ) -> AssemblyResult:
        """
        Simple assembly of video files with uniform transitions.

        Args:
            video_paths: List of video file paths in order
            output_filename: Output filename
            transition: Transition type between all shots
            transition_duration_ms: Duration of each transition

        Returns:
            AssemblyResult
        """
        # Create temporary assembly
        assembly_id = await self.create_assembly(f"simple_assembly_{datetime.now().timestamp()}")

        # Add all shots
        for i, path in enumerate(video_paths):
            # Get video duration
            duration_ms = await self._get_video_duration_ms(path)

            trans = TransitionSpec(
                transition_type=transition,
                duration_ms=transition_duration_ms if i > 0 else 0
            )

            await self.add_shot(
                assembly_id=assembly_id,
                video_path=path,
                duration_ms=duration_ms,
                shot_order=i,
                transition=trans
            )

        # Execute assembly
        return await self.assemble(assembly_id, output_filename)

    async def _get_video_duration_ms(self, video_path: str) -> int:
        """Get video duration in milliseconds using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            duration_sec = float(result.stdout.strip())
            return int(duration_sec * 1000)
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return 0

    # === Database Helpers ===

    async def _update_assembly_status(self, assembly_id: int, status: str) -> None:
        """Update assembly status."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE shot_assemblies SET status = $2 WHERE id = $1
            """, assembly_id, status)

    async def _update_assembly_completed(
        self, assembly_id: int, output_path: str, duration_ms: int
    ) -> None:
        """Mark assembly as completed."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE shot_assemblies
                SET status = 'completed', output_path = $2, duration_ms = $3, completed_at = NOW()
                WHERE id = $1
            """, assembly_id, output_path, duration_ms)

    async def get_assembly(self, assembly_id: int) -> Optional[Dict]:
        """Get assembly information."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM shot_assemblies WHERE id = $1", assembly_id
            )

        if not row:
            return None

        return {
            "id": row["id"],
            "name": row["name"],
            "scene_id": row["scene_id"],
            "episode_id": row["episode_id"],
            "project_id": row["project_id"],
            "output_path": row["output_path"],
            "duration_ms": row["duration_ms"],
            "status": row["status"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "created_at": row["created_at"],
            "completed_at": row["completed_at"]
        }

    async def get_assembly_shots(self, assembly_id: int) -> List[Dict]:
        """Get all shots in an assembly."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM assembly_shots
                WHERE assembly_id = $1
                ORDER BY shot_order
            """, assembly_id)

        return [
            {
                "id": row["id"],
                "shot_order": row["shot_order"],
                "video_path": row["video_path"],
                "start_time_ms": row["start_time_ms"],
                "end_time_ms": row["end_time_ms"],
                "duration_ms": row["duration_ms"],
                "transition_type": row["transition_type"],
                "transition_duration_ms": row["transition_duration_ms"],
                "transition_params": json.loads(row["transition_params"]) if row["transition_params"] else {},
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
            }
            for row in rows
        ]


# === Factory function ===

async def create_shot_assembler(database_url: str) -> ShotAssembler:
    """Create and initialize a ShotAssembler instance."""
    assembler = ShotAssembler(database_url)
    await assembler.connect()
    return assembler
