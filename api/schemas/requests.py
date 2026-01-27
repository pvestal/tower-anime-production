"""
Request schemas for Tower Anime Production API
"""

from typing import Optional
from pydantic import BaseModel


class AnimeProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class AnimeProjectCreate(AnimeProjectBase):
    pass


class AnimeGenerationRequest(BaseModel):
    prompt: str
    character: str = "original"
    scene_type: str = "dialogue"
    duration: int = 3
    style: str = "anime"


class PersonalCreativeRequest(BaseModel):
    mood: str = "neutral"
    personal_context: Optional[str] = None
    style_preferences: Optional[str] = None
    biometric_data: Optional[dict] = None


class CharacterGenerateRequest(BaseModel):
    action: str = "portrait"  # portrait, walking, talking, action, dancing
    generation_type: str = "image"
    location: str = "tokyo street"
    prompt: Optional[str] = None


class SceneGenerateRequest(BaseModel):
    scene_type: str = "dialogue"
    duration: float = 3.0
    characters: Optional[list] = None
    location: Optional[str] = None
    prompt: Optional[str] = None


class EpisodeGenerateRequest(BaseModel):
    episode_number: int
    scenes: list
    style: str = "anime"
    duration: Optional[float] = None