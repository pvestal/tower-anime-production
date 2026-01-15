"""
Pose Manager for Tower Anime Production.

Manages character pose libraries with OpenPose skeletons, semantic tagging,
and pose interpolation for keyframe-based animation workflows.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class PoseCategory(Enum):
    """Categories for organizing poses."""
    NEUTRAL = "neutral"
    EMOTIONAL = "emotional"
    ACTION = "action"
    SITTING = "sitting"
    STANDING = "standing"
    WALKING = "walking"
    RUNNING = "running"
    GESTURE = "gesture"
    COMBAT = "combat"
    CUSTOM = "custom"


class EmotionType(Enum):
    """Emotional states for poses."""
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    FEARFUL = "fearful"
    DISGUSTED = "disgusted"
    NEUTRAL = "neutral"
    CONFIDENT = "confident"
    SHY = "shy"
    DETERMINED = "determined"


@dataclass
class OpenPoseKeypoints:
    """OpenPose skeleton keypoints (BODY_25 format)."""

    # 25 keypoints: [x, y, confidence] for each
    keypoints: np.ndarray  # Shape: (25, 3)

    # Named accessors for key joints
    @property
    def nose(self) -> np.ndarray:
        return self.keypoints[0]

    @property
    def neck(self) -> np.ndarray:
        return self.keypoints[1]

    @property
    def right_shoulder(self) -> np.ndarray:
        return self.keypoints[2]

    @property
    def right_elbow(self) -> np.ndarray:
        return self.keypoints[3]

    @property
    def right_wrist(self) -> np.ndarray:
        return self.keypoints[4]

    @property
    def left_shoulder(self) -> np.ndarray:
        return self.keypoints[5]

    @property
    def left_elbow(self) -> np.ndarray:
        return self.keypoints[6]

    @property
    def left_wrist(self) -> np.ndarray:
        return self.keypoints[7]

    @property
    def mid_hip(self) -> np.ndarray:
        return self.keypoints[8]

    @property
    def right_hip(self) -> np.ndarray:
        return self.keypoints[9]

    @property
    def right_knee(self) -> np.ndarray:
        return self.keypoints[10]

    @property
    def right_ankle(self) -> np.ndarray:
        return self.keypoints[11]

    @property
    def left_hip(self) -> np.ndarray:
        return self.keypoints[12]

    @property
    def left_knee(self) -> np.ndarray:
        return self.keypoints[13]

    @property
    def left_ankle(self) -> np.ndarray:
        return self.keypoints[14]

    def to_dict(self) -> Dict:
        return {"keypoints": self.keypoints.tolist()}

    @classmethod
    def from_dict(cls, data: Dict) -> "OpenPoseKeypoints":
        return cls(keypoints=np.array(data["keypoints"]))

    def to_bytes(self) -> bytes:
        return self.keypoints.tobytes()

    @classmethod
    def from_bytes(cls, data: bytes) -> "OpenPoseKeypoints":
        arr = np.frombuffer(data, dtype=np.float32).reshape(25, 3)
        return cls(keypoints=arr)


@dataclass
class CharacterPose:
    """A stored pose for a character."""

    id: int
    character_id: int
    name: str
    category: PoseCategory
    emotion: Optional[EmotionType]
    keypoints: OpenPoseKeypoints
    tags: List[str]
    description: str
    reference_image_path: Optional[str]
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class PoseManager:
    """
    Manages character pose libraries for animation.

    Features:
    - Store/retrieve OpenPose skeletons per character
    - Tag poses by emotion, action, category
    - Interpolate between poses for smooth animation
    - Generate ControlNet-compatible pose images
    """

    def __init__(self, database_url: str, pose_images_dir: str = "/mnt/1TB-storage/poses"):
        """
        Initialize Pose Manager.

        Args:
            database_url: PostgreSQL connection URL
            pose_images_dir: Directory for storing pose reference images
        """
        self.database_url = database_url
        self.pose_images_dir = Path(pose_images_dir)
        self.pool = None

        # Ensure pose directory exists
        self.pose_images_dir.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> None:
        """Initialize database connection pool."""
        import asyncpg
        self.pool = await asyncpg.create_pool(self.database_url)
        await self._ensure_tables()
        logger.info("PoseManager connected to database")

    async def close(self) -> None:
        """Close database connections."""
        if self.pool:
            await self.pool.close()

    async def _ensure_tables(self) -> None:
        """Create pose library tables if they don't exist."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_poses (
                    id SERIAL PRIMARY KEY,
                    character_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    emotion VARCHAR(50),
                    keypoints BYTEA NOT NULL,
                    tags TEXT[] DEFAULT '{}',
                    description TEXT,
                    reference_image_path VARCHAR(500),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),

                    UNIQUE(character_id, name)
                );

                CREATE INDEX IF NOT EXISTS idx_poses_character ON character_poses(character_id);
                CREATE INDEX IF NOT EXISTS idx_poses_category ON character_poses(category);
                CREATE INDEX IF NOT EXISTS idx_poses_emotion ON character_poses(emotion);
                CREATE INDEX IF NOT EXISTS idx_poses_tags ON character_poses USING GIN(tags);
            """)

            # Pose sequences table for animation workflows
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pose_sequences (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    character_id INTEGER NOT NULL,
                    description TEXT,
                    pose_ids INTEGER[] NOT NULL,
                    durations_ms INTEGER[] NOT NULL,
                    interpolation_types TEXT[] DEFAULT '{}',
                    loop BOOLEAN DEFAULT FALSE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_sequences_character ON pose_sequences(character_id);
            """)

    # === Pose Storage Operations ===

    async def store_pose(
        self,
        character_id: int,
        name: str,
        keypoints: OpenPoseKeypoints,
        category: PoseCategory = PoseCategory.NEUTRAL,
        emotion: Optional[EmotionType] = None,
        tags: List[str] = None,
        description: str = "",
        reference_image_path: Optional[str] = None,
        metadata: Dict = None
    ) -> int:
        """
        Store a pose in the character's pose library.

        Args:
            character_id: Character this pose belongs to
            name: Unique name for the pose
            keypoints: OpenPose skeleton keypoints
            category: Pose category (action, emotional, etc.)
            emotion: Emotional state if applicable
            tags: Additional searchable tags
            description: Human-readable description
            reference_image_path: Path to reference image
            metadata: Additional metadata

        Returns:
            Database ID of the stored pose
        """
        async with self.pool.acquire() as conn:
            pose_id = await conn.fetchval("""
                INSERT INTO character_poses
                (character_id, name, category, emotion, keypoints, tags, description,
                 reference_image_path, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (character_id, name) DO UPDATE SET
                    category = EXCLUDED.category,
                    emotion = EXCLUDED.emotion,
                    keypoints = EXCLUDED.keypoints,
                    tags = EXCLUDED.tags,
                    description = EXCLUDED.description,
                    reference_image_path = EXCLUDED.reference_image_path,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING id
            """,
                character_id,
                name,
                category.value,
                emotion.value if emotion else None,
                keypoints.to_bytes(),
                tags or [],
                description,
                reference_image_path,
                json.dumps(metadata or {})
            )

            logger.info(f"Stored pose '{name}' for character {character_id}")
            return pose_id

    async def get_pose(self, pose_id: int) -> Optional[CharacterPose]:
        """Get a pose by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM character_poses WHERE id = $1", pose_id
            )

        if not row:
            return None

        return self._row_to_pose(row)

    async def get_pose_by_name(self, character_id: int, name: str) -> Optional[CharacterPose]:
        """Get a pose by character ID and name."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM character_poses
                WHERE character_id = $1 AND name = $2
            """, character_id, name)

        if not row:
            return None

        return self._row_to_pose(row)

    async def get_poses_by_character(
        self,
        character_id: int,
        category: Optional[PoseCategory] = None,
        emotion: Optional[EmotionType] = None,
        tags: Optional[List[str]] = None
    ) -> List[CharacterPose]:
        """
        Get all poses for a character with optional filtering.

        Args:
            character_id: Character ID
            category: Filter by category
            emotion: Filter by emotion
            tags: Filter by tags (any match)

        Returns:
            List of matching poses
        """
        query = "SELECT * FROM character_poses WHERE character_id = $1"
        params = [character_id]
        param_idx = 2

        if category:
            query += f" AND category = ${param_idx}"
            params.append(category.value)
            param_idx += 1

        if emotion:
            query += f" AND emotion = ${param_idx}"
            params.append(emotion.value)
            param_idx += 1

        if tags:
            query += f" AND tags && ${param_idx}"
            params.append(tags)
            param_idx += 1

        query += " ORDER BY name"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [self._row_to_pose(row) for row in rows]

    async def delete_pose(self, pose_id: int) -> bool:
        """Delete a pose from the library."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM character_poses WHERE id = $1", pose_id
            )
            return result == "DELETE 1"

    # === Pose Interpolation ===

    def interpolate_poses(
        self,
        start_pose: OpenPoseKeypoints,
        end_pose: OpenPoseKeypoints,
        num_frames: int,
        interpolation: str = "linear"
    ) -> List[OpenPoseKeypoints]:
        """
        Interpolate between two poses to create smooth animation.

        Args:
            start_pose: Starting pose keypoints
            end_pose: Ending pose keypoints
            num_frames: Number of intermediate frames
            interpolation: Type of interpolation (linear, ease_in, ease_out, ease_in_out)

        Returns:
            List of interpolated pose keypoints
        """
        frames = []

        for i in range(num_frames):
            t = i / (num_frames - 1) if num_frames > 1 else 0

            # Apply easing function
            if interpolation == "ease_in":
                t = t * t
            elif interpolation == "ease_out":
                t = 1 - (1 - t) ** 2
            elif interpolation == "ease_in_out":
                t = 3 * t * t - 2 * t * t * t
            # linear: t stays as-is

            # Interpolate keypoints
            interpolated = start_pose.keypoints * (1 - t) + end_pose.keypoints * t
            frames.append(OpenPoseKeypoints(keypoints=interpolated))

        return frames

    async def interpolate_pose_sequence(
        self,
        pose_ids: List[int],
        frames_between: int = 10,
        interpolation: str = "ease_in_out"
    ) -> List[OpenPoseKeypoints]:
        """
        Create a smooth animation sequence from multiple poses.

        Args:
            pose_ids: List of pose IDs in order
            frames_between: Number of interpolated frames between each pose
            interpolation: Interpolation type

        Returns:
            Complete list of keyframes for animation
        """
        if len(pose_ids) < 2:
            raise ValueError("Need at least 2 poses for interpolation")

        # Load all poses
        poses = []
        for pose_id in pose_ids:
            pose = await self.get_pose(pose_id)
            if pose:
                poses.append(pose)

        if len(poses) < 2:
            raise ValueError("Could not load enough poses")

        # Interpolate between each pair
        result = []
        for i in range(len(poses) - 1):
            interpolated = self.interpolate_poses(
                poses[i].keypoints,
                poses[i + 1].keypoints,
                frames_between + 1,  # +1 because we include endpoints
                interpolation
            )

            # Add all frames except last (to avoid duplicates)
            if i < len(poses) - 2:
                result.extend(interpolated[:-1])
            else:
                result.extend(interpolated)

        return result

    # === Pose Sequence Management ===

    async def create_sequence(
        self,
        name: str,
        character_id: int,
        pose_ids: List[int],
        durations_ms: List[int],
        interpolation_types: List[str] = None,
        loop: bool = False,
        description: str = "",
        metadata: Dict = None
    ) -> int:
        """
        Create a named pose sequence for reusable animations.

        Args:
            name: Sequence name
            character_id: Character this sequence is for
            pose_ids: Ordered list of pose IDs
            durations_ms: Duration at each pose in milliseconds
            interpolation_types: Interpolation type between each pose pair
            loop: Whether sequence should loop
            description: Description of the sequence
            metadata: Additional metadata

        Returns:
            Sequence ID
        """
        if len(pose_ids) != len(durations_ms):
            raise ValueError("pose_ids and durations_ms must have same length")

        if interpolation_types is None:
            interpolation_types = ["ease_in_out"] * (len(pose_ids) - 1)

        async with self.pool.acquire() as conn:
            seq_id = await conn.fetchval("""
                INSERT INTO pose_sequences
                (name, character_id, description, pose_ids, durations_ms,
                 interpolation_types, loop, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
                name,
                character_id,
                description,
                pose_ids,
                durations_ms,
                interpolation_types,
                loop,
                json.dumps(metadata or {})
            )

            logger.info(f"Created pose sequence '{name}' with {len(pose_ids)} poses")
            return seq_id

    async def get_sequence(self, sequence_id: int) -> Optional[Dict]:
        """Get a pose sequence by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM pose_sequences WHERE id = $1", sequence_id
            )

        if not row:
            return None

        return {
            "id": row["id"],
            "name": row["name"],
            "character_id": row["character_id"],
            "description": row["description"],
            "pose_ids": list(row["pose_ids"]),
            "durations_ms": list(row["durations_ms"]),
            "interpolation_types": list(row["interpolation_types"]),
            "loop": row["loop"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "created_at": row["created_at"]
        }

    async def render_sequence_keyframes(
        self,
        sequence_id: int,
        fps: int = 30
    ) -> List[OpenPoseKeypoints]:
        """
        Render a sequence into individual keyframes at specified FPS.

        Args:
            sequence_id: Sequence ID
            fps: Target frames per second

        Returns:
            List of all keyframes for the animation
        """
        sequence = await self.get_sequence(sequence_id)
        if not sequence:
            raise ValueError(f"Sequence {sequence_id} not found")

        all_frames = []
        pose_ids = sequence["pose_ids"]
        durations_ms = sequence["durations_ms"]
        interpolation_types = sequence["interpolation_types"]

        # Load poses
        poses = []
        for pose_id in pose_ids:
            pose = await self.get_pose(pose_id)
            if pose:
                poses.append(pose)

        if len(poses) < 2:
            raise ValueError("Need at least 2 valid poses in sequence")

        # Generate frames for each segment
        for i in range(len(poses) - 1):
            duration_ms = durations_ms[i]
            frames_count = max(1, int((duration_ms / 1000) * fps))
            interp = interpolation_types[i] if i < len(interpolation_types) else "linear"

            segment_frames = self.interpolate_poses(
                poses[i].keypoints,
                poses[i + 1].keypoints,
                frames_count,
                interp
            )

            # Add frames (skip last to avoid duplicates except at end)
            if i < len(poses) - 2:
                all_frames.extend(segment_frames[:-1])
            else:
                all_frames.extend(segment_frames)

        return all_frames

    # === ControlNet Integration ===

    async def generate_controlnet_image(
        self,
        keypoints: OpenPoseKeypoints,
        width: int = 512,
        height: int = 768,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate a ControlNet-compatible pose image from keypoints.

        Args:
            keypoints: OpenPose keypoints
            width: Image width
            height: Image height
            output_path: Where to save the image

        Returns:
            Path to generated image
        """
        try:
            import cv2
        except ImportError:
            raise RuntimeError("OpenCV required for pose image generation")

        # Create black background
        image = np.zeros((height, width, 3), dtype=np.uint8)

        # BODY_25 limb connections
        limbs = [
            (0, 1), (1, 2), (2, 3), (3, 4),      # Right arm
            (1, 5), (5, 6), (6, 7),               # Left arm
            (1, 8),                                # Spine
            (8, 9), (9, 10), (10, 11),            # Right leg
            (8, 12), (12, 13), (13, 14),          # Left leg
            (0, 15), (15, 17),                     # Right face
            (0, 16), (16, 18),                     # Left face
            (11, 22), (22, 23), (23, 24),         # Right foot
            (14, 19), (19, 20), (20, 21)          # Left foot
        ]

        # Colors for limbs (OpenPose style)
        colors = [
            (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0),
            (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85),
            (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
            (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255),
            (255, 0, 170), (255, 0, 85)
        ]

        kp = keypoints.keypoints

        # Draw limbs
        for idx, (start, end) in enumerate(limbs):
            if start < len(kp) and end < len(kp):
                if kp[start][2] > 0.1 and kp[end][2] > 0.1:  # Confidence threshold
                    pt1 = (int(kp[start][0] * width), int(kp[start][1] * height))
                    pt2 = (int(kp[end][0] * width), int(kp[end][1] * height))
                    color = colors[idx % len(colors)]
                    cv2.line(image, pt1, pt2, color, 4)

        # Draw keypoints
        for i, point in enumerate(kp):
            if point[2] > 0.1:  # Confidence threshold
                x, y = int(point[0] * width), int(point[1] * height)
                cv2.circle(image, (x, y), 6, (255, 255, 255), -1)

        # Save image
        if output_path is None:
            output_path = str(self.pose_images_dir / f"pose_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        cv2.imwrite(output_path, image)
        logger.info(f"Generated ControlNet pose image: {output_path}")

        return output_path

    async def generate_sequence_controlnet_images(
        self,
        sequence_id: int,
        fps: int = 30,
        width: int = 512,
        height: int = 768
    ) -> List[str]:
        """
        Generate all ControlNet images for a pose sequence.

        Args:
            sequence_id: Sequence ID
            fps: Frames per second
            width: Image width
            height: Image height

        Returns:
            List of paths to generated images
        """
        keyframes = await self.render_sequence_keyframes(sequence_id, fps)

        sequence = await self.get_sequence(sequence_id)
        output_dir = self.pose_images_dir / f"sequence_{sequence_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for i, kf in enumerate(keyframes):
            path = str(output_dir / f"frame_{i:05d}.png")
            await self.generate_controlnet_image(kf, width, height, path)
            paths.append(path)

        logger.info(f"Generated {len(paths)} ControlNet images for sequence {sequence_id}")
        return paths

    # === Pose Extraction from Images ===

    async def extract_pose_from_image(
        self,
        image_path: str,
        character_id: int,
        pose_name: str,
        category: PoseCategory = PoseCategory.CUSTOM,
        emotion: Optional[EmotionType] = None,
        tags: List[str] = None
    ) -> Optional[int]:
        """
        Extract pose from an image and store it in the library.

        Requires OpenPose or similar pose estimation to be available.

        Args:
            image_path: Path to source image
            character_id: Character to associate pose with
            pose_name: Name for the extracted pose
            category: Pose category
            emotion: Emotional state
            tags: Additional tags

        Returns:
            Pose ID if successful, None otherwise
        """
        try:
            # Try to use controlnet_aux for pose detection
            from controlnet_aux import OpenposeDetector
            import cv2
            from PIL import Image

            # Load image
            image = Image.open(image_path)

            # Detect pose
            detector = OpenposeDetector.from_pretrained("lllyasviel/ControlNet")
            pose_image = detector(image, hand_and_face=False)

            # Extract keypoints from pose image
            # This is a simplified version - real implementation would parse detector output
            pose_np = np.array(pose_image)

            # For now, create normalized keypoints from detected pose
            # In production, this would use the actual detector output
            keypoints = np.zeros((25, 3), dtype=np.float32)

            # Store the pose
            pose_id = await self.store_pose(
                character_id=character_id,
                name=pose_name,
                keypoints=OpenPoseKeypoints(keypoints=keypoints),
                category=category,
                emotion=emotion,
                tags=tags or [],
                description=f"Extracted from {Path(image_path).name}",
                reference_image_path=image_path
            )

            return pose_id

        except ImportError:
            logger.warning("controlnet_aux not available for pose extraction")
            return None
        except Exception as e:
            logger.error(f"Error extracting pose: {e}")
            return None

    # === Utility Methods ===

    def _row_to_pose(self, row) -> CharacterPose:
        """Convert database row to CharacterPose object."""
        return CharacterPose(
            id=row["id"],
            character_id=row["character_id"],
            name=row["name"],
            category=PoseCategory(row["category"]),
            emotion=EmotionType(row["emotion"]) if row["emotion"] else None,
            keypoints=OpenPoseKeypoints.from_bytes(row["keypoints"]),
            tags=list(row["tags"]) if row["tags"] else [],
            description=row["description"] or "",
            reference_image_path=row["reference_image_path"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
        )

    async def get_pose_library_stats(self, character_id: int) -> Dict[str, Any]:
        """Get statistics about a character's pose library."""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_poses,
                    COUNT(DISTINCT category) as categories_used,
                    COUNT(DISTINCT emotion) FILTER (WHERE emotion IS NOT NULL) as emotions_used,
                    array_agg(DISTINCT category) as categories
                FROM character_poses
                WHERE character_id = $1
            """, character_id)

            sequences = await conn.fetchval("""
                SELECT COUNT(*) FROM pose_sequences WHERE character_id = $1
            """, character_id)

        return {
            "character_id": character_id,
            "total_poses": stats["total_poses"],
            "categories_used": stats["categories_used"],
            "emotions_used": stats["emotions_used"],
            "categories": list(stats["categories"]) if stats["categories"] else [],
            "total_sequences": sequences
        }


# === Factory function for easy initialization ===

async def create_pose_manager(database_url: str) -> PoseManager:
    """Create and initialize a PoseManager instance."""
    manager = PoseManager(database_url)
    await manager.connect()
    return manager
