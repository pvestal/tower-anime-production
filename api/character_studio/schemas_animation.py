"""
character_studio/schemas_animation.py
Phase 3: Animation Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class AnimationType(str, Enum):
    """Animation type enumeration"""
    WALK_CYCLE_2D = "walk_cycle_2d"
    IDLE_BREATHING = "idle_breathing"
    TALKING_VISEMES = "talking_visemes"
    CUSTOM_SEQUENCE = "custom_sequence"


class AnimationRequest(BaseModel):
    """Request for generating animation sequence"""
    character_id: int = Field(..., description="Character ID from database")
    animation_type: AnimationType = Field(..., description="Type of animation to generate")
    pose_sequence: Optional[List[str]] = Field(
        None,
        description="Custom pose sequence (list of pose image paths)"
    )
    fps: int = Field(24, ge=1, le=60, description="Frames per second")
    resolution: str = Field("1920x1080", description="Output video resolution")
    loop: bool = Field(True, description="Whether to loop the animation")
    seed: int = Field(-1, description="Random seed (-1 for random)")
    
    class Config:
        schema_extra = {
            "example": {
                "character_id": 36,
                "animation_type": "walk_cycle_2d",
                "fps": 24,
                "resolution": "1920x1080",
                "loop": True,
                "seed": 42000
            }
        }


class AnimationResponse(BaseModel):
    """Response from animation generation"""
    animation_id: int
    character_id: int
    character_name: Optional[str]
    animation_type: str
    frame_count: int
    video_path: Optional[str]
    status: str
    estimated_completion: str
    created_at: str
    
    class Config:
        schema_extra = {
            "example": {
                "animation_id": 1,
                "character_id": 36,
                "character_name": "Rina Suzuki",
                "animation_type": "walk_cycle_2d",
                "frame_count": 12,
                "video_path": "/mnt/1TB-storage/animations/tokyo_debt_desire_rina_suzuki_walk_cycle_20251218.mp4",
                "status": "completed",
                "estimated_completion": "N/A",
                "created_at": "2025-12-18T20:00:00"
            }
        }


class LipSyncRequest(BaseModel):
    """Request for lip sync generation"""
    character_id: int = Field(..., description="Character ID")
    audio_file_path: str = Field(..., description="Path to audio file (.wav, .mp3)")
    phonemes: Optional[List[str]] = Field(
        None,
        description="Phoneme sequence (A, E, I, O, U, M, B, P)"
    )
    fps: int = Field(30, ge=12, le=60, description="Frames per second for lip sync")
    
    class Config:
        schema_extra = {
            "example": {
                "character_id": 36,
                "audio_file_path": "/mnt/1TB-storage/audio/dialogue_01.wav",
                "phonemes": ["A", "E", "I", "O", "U", "M", "B", "P"],
                "fps": 30
            }
        }


class LipSyncResponse(BaseModel):
    """Response from lip sync generation"""
    character_id: int
    character_name: Optional[str]
    video_path: str
    audio_duration: float
    frames_generated: int
    phonemes_used: List[str]
    status: str


class PoseSequenceRequest(BaseModel):
    """Request to create a pose sequence"""
    sequence_name: str = Field(..., description="Name of the pose sequence")
    animation_type: str = Field(..., description="Type of animation this is for")
    poses: List[str] = Field(..., description="List of pose image paths in order")
    fps: int = Field(24, ge=1, le=60, description="Default FPS for this sequence")
    loop: bool = Field(True, description="Whether this sequence should loop")
    
    class Config:
        schema_extra = {
            "example": {
                "sequence_name": "custom_walk_12f",
                "animation_type": "walk_cycle_2d",
                "poses": [
                    "/mnt/1TB-storage/poses/custom/walk_01.png",
                    "/mnt/1TB-storage/poses/custom/walk_02.png",
                    "/mnt/1TB-storage/poses/custom/walk_03.png"
                ],
                "fps": 24,
                "loop": True
            }
        }


class PoseSequenceResponse(BaseModel):
    """Response from pose sequence creation"""
    sequence_id: str
    sequence_name: str
    animation_type: str
    poses_count: int
    file_path: str
    fps: int


class AnimationTemplateInfo(BaseModel):
    """Information about an animation template"""
    template_id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field("", description="Template description")
    frame_count: int = Field(12, description="Default number of frames")
    fps: int = Field(24, description="Default frames per second")
    controlnet_type: str = Field("openpose", description="ControlNet type (openpose/depth/canny)")
    workflow_file: str = Field(..., description="Workflow JSON filename")
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "walk_cycle_2d",
                "name": "2D Walk Cycle",
                "description": "Basic walk cycle animation with OpenPose ControlNet",
                "frame_count": 12,
                "fps": 24,
                "controlnet_type": "openpose",
                "workflow_file": "walk_cycle_2d.json"
            }
        }
