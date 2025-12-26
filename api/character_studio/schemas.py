"""
character_studio/schemas.py
Pydantic models for Character Studio API requests and responses
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class LoRAConfig(BaseModel):
    """LoRA model configuration"""
    name: str = Field(..., description="LoRA filename (e.g., 'arcane_offset.safetensors')")
    strength_model: float = Field(default=1.0, ge=0.0, le=2.0, description="Model strength")
    strength_clip: float = Field(default=1.0, ge=0.0, le=2.0, description="CLIP strength")


class CharacterGenerateRequest(BaseModel):
    """Request to generate a character image"""

    # Character identity
    character_name: Optional[str] = Field(
        None,
        description="Character name for organization",
        max_length=100
    )
    scene: Optional[str] = Field(
        None,
        description="Scene/location (e.g., 'apartment_morning', 'office_desk')",
        max_length=100
    )
    action: Optional[str] = Field(
        None,
        description="Character action (e.g., 'yoga_practice', 'drinking_coffee')",
        max_length=100
    )
    project: str = Field(
        default="default",
        description="Project name for organizing characters",
        max_length=100
    )
    scene: Optional[str] = Field(
        None,
        description="Scene/location (e.g., 'apartment_morning', 'office_desk')",
        max_length=100
    )
    action: Optional[str] = Field(
        None,
        description="Character action (e.g., 'yoga_practice', 'drinking_coffee')",
        max_length=100
    )

    # Prompts
    prompt: str = Field(
        ...,
        description="Detailed character description",
        min_length=10,
        max_length=1000
    )
    negative_prompt: str = Field(
        default="bad quality, blurry, lowres, deformed, worst quality",
        description="What to avoid in generation",
        max_length=500
    )

    # Model settings
    checkpoint: str = Field(
        default="AOM3A1B.safetensors",
        description="Stable Diffusion checkpoint to use"
    )
    width: int = Field(default=512, ge=256, le=1024)
    height: int = Field(default=768, ge=256, le=1024)
    steps: int = Field(default=20, ge=10, le=50, description="Sampling steps")
    cfg_scale: float = Field(default=7.0, ge=1.0, le=20.0, description="CFG scale")
    seed: int = Field(default=-1, description="Seed for reproducibility (-1 = random)")

    # LoRA settings
    loras: List[LoRAConfig] = Field(default_factory=list, description="LoRA models to apply")

    # Sampler settings
    sampler: str = Field(default="euler", description="Sampler name (euler, dpmpp_2m_karras, etc.)")
    scheduler: str = Field(default="normal", description="Scheduler (normal, karras, exponential)")

    # ControlNet settings
    use_controlnet: bool = Field(default=False, description="Enable ControlNet pose control")
    controlnet_model: str = Field(
        default="control_v11p_sd15_openpose",
        description="ControlNet model name"
    )
    pose_reference: Optional[str] = Field(
        None,
        description="Path to pose reference image (relative to ComfyUI/input)"
    )

    # Metadata
    tags: List[str] = Field(default_factory=list, description="Tags for organization")

    @field_validator('checkpoint')
    @classmethod
    def validate_checkpoint(cls, v):
        """Ensure checkpoint has correct extension"""
        if not (v.endswith('.safetensors') or v.endswith('.ckpt')):
            return f"{v}.safetensors"
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "character_name": "Akari",
                "project": "winter_tale",
                "prompt": "anime girl, long silver hair, blue eyes, school uniform, detailed face, high quality",
                "negative_prompt": "bad quality, blurry, deformed",
                "checkpoint": "AOM3A1B.safetensors",
                "width": 512,
                "height": 768,
                "steps": 20,
                "cfg_scale": 7.0,
                "seed": 42,
                "use_controlnet": True,
                "pose_reference": "pose_templates/standing_front.png",
                "tags": ["protagonist", "design_v1"]
            }
        }


class CharacterGenerateResponse(BaseModel):
    """Response from character generation"""

    job_id: str
    character_name: Optional[str]
    project: str
    status: str  # "completed", "failed"
    output_path: Optional[str] = None
    comfyui_prompt_id: Optional[str] = None
    error: Optional[str] = None
    seed: Optional[int] = None
    created_at: str
    completed_at: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "character_name": "Akari",
                "project": "winter_tale",
                "status": "completed",
                "output_path": "/mnt/1TB-storage/character_assets/winter_tale/Akari_20251218_043015.png",
                "comfyui_prompt_id": "abc123-def456",
                "seed": 42,
                "created_at": "2025-12-18T04:30:15.123456",
                "completed_at": "2025-12-18T04:30:45.789012"
            }
        }


class CharacterListItem(BaseModel):
    """Character in list view"""

    id: int
    character_name: Optional[str]
    project: str
    prompt: str
    output_path: str
    created_at: datetime
    status: str

    class Config:
        from_attributes = True  # For SQLAlchemy models


class CharacterListResponse(BaseModel):
    """Response for list endpoint"""

    characters: List[CharacterListItem]
    total: int
    skip: int
    limit: int


class CharacterDetailResponse(BaseModel):
    """Detailed character information"""

    id: int
    job_id: str
    character_name: Optional[str]
    project: str

    # Prompts
    prompt: str
    negative_prompt: Optional[str]

    # Generation settings
    checkpoint: Optional[str]
    width: Optional[int]
    height: Optional[int]
    steps: Optional[int]
    cfg_scale: Optional[float]
    seed: Optional[int]

    # ControlNet
    use_controlnet: bool
    controlnet_model: Optional[str]
    pose_reference: Optional[str]

    # Output
    output_path: str
    comfyui_prompt_id: Optional[str]

    # Status
    status: str
    error_message: Optional[str]

    # Timestamps
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
