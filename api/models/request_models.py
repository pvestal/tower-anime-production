"""Request and Response models for the API"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    negative_prompt: Optional[str] = None
    model: Optional[str] = "animagine-xl-3.1.safetensors"
    project_id: Optional[str] = None
    width: int = Field(default=832, ge=256, le=2048)
    height: int = Field(default=1216, ge=256, le=2048)
    steps: int = Field(default=15, ge=1, le=100)
    cfg_scale: float = Field(default=7.0, ge=1.0, le=20.0)
    seed: Optional[int] = None
    batch_size: int = Field(default=1, ge=1, le=4)

    @field_validator('prompt')
    def validate_prompt(cls, v):
        if not v or not v.strip():
            raise ValueError('Prompt cannot be empty')
        return v.strip()


class MusicVideoRequest(BaseModel):
    video_prompt: str = Field(..., min_length=1, max_length=1000)
    music_genre: str = Field(default="electronic")
    video_duration: int = Field(default=30, ge=5, le=300)
    style: str = Field(default="anime")
    bpm: Optional[int] = Field(None, ge=60, le=200)

    @field_validator('video_prompt')
    def validate_video_prompt(cls, v):
        if not v or not v.strip():
            raise ValueError('Video prompt cannot be empty')
        return v.strip()


class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    intent: Optional[Dict] = None
    suggestions: Optional[List[str]] = None
    job_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class CreateEpisodeRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    episode_number: int = Field(..., ge=1)
    project_id: str
    script_content: Optional[str] = None
    duration_seconds: int = Field(default=300, ge=30, le=3600)