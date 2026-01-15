"""
Animation services for Tower Anime Production.

This module provides pose management, shot assembly, and keyframe animation tools.
"""

from services.animation.pose_manager import (
    PoseManager,
    PoseCategory,
    EmotionType,
    OpenPoseKeypoints,
    CharacterPose,
    create_pose_manager,
)

from services.animation.shot_assembler import (
    ShotAssembler,
    TransitionType,
    AudioTrackType,
    Shot,
    AudioTrack,
    TransitionSpec,
    AssemblyResult,
    create_shot_assembler,
)

__all__ = [
    # Pose Manager
    "PoseManager",
    "PoseCategory",
    "EmotionType",
    "OpenPoseKeypoints",
    "CharacterPose",
    "create_pose_manager",
    # Shot Assembler
    "ShotAssembler",
    "TransitionType",
    "AudioTrackType",
    "Shot",
    "AudioTrack",
    "TransitionSpec",
    "AssemblyResult",
    "create_shot_assembler",
]
