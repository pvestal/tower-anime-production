"""
Pydantic schemas for Tower Anime Production API
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

# Request/Response Models
class AnimeProjectCreate(BaseModel):
    name: str
    description: str
    style: str = "anime"
    characters: List[Dict[str, Any]] = []

class AnimeProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    style: str
    characters: List[Dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime

class AnimeGenerationRequest(BaseModel):
    prompt: str
    character: str = "original"
    style: str = "anime"
    duration: int = 30
    generation_type: str = "image"

class PersonalCreativeRequest(BaseModel):
    mood: str = "neutral"
    personal_context: Optional[str] = None

class CharacterGenerateRequest(BaseModel):
    action: str = "portrait"  # portrait, walking, talking, action, dancing
    generation_type: str = "image"
    location: str = "tokyo street"
    prompt: Optional[str] = None

class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress: float
    created_at: datetime
    completed_at: Optional[datetime] = None
    result_path: Optional[str] = None
    error_message: Optional[str] = None