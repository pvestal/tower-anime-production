"""
Response schemas for Tower Anime Production API
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class AnimeProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    project_metadata: Optional[dict] = None

    class Config:
        from_attributes = True


class ProductionJobResponse(BaseModel):
    id: int
    project_id: int
    job_type: str
    status: str
    output_path: Optional[str] = None
    quality_score: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CharacterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    project_id: int
    lora_available: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SceneResponse(BaseModel):
    id: int
    project_id: int
    episode_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    scene_type: str
    duration: Optional[float] = None
    status: str
    order_index: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EpisodeResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    episode_number: int
    duration: Optional[float] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class GenerationStatusResponse(BaseModel):
    request_id: str
    status: str
    progress: Optional[float] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None