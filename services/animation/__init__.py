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

from services.animation.keyframe_animator import (
    KeyframeAnimator,
    MotionCurve,
    Keyframe,
    AnimationClip,
    GenerationResult,
    create_keyframe_animator,
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
    # Keyframe Animator
    "KeyframeAnimator",
    "MotionCurve",
    "Keyframe",
    "AnimationClip",
    "GenerationResult",
    "create_keyframe_animator",
]
