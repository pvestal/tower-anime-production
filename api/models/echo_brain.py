"""
Echo Brain database models for Tower Anime Production API
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from api.core.database import Base


class EchoBrainSuggestion(Base):
    __tablename__ = "echo_brain_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    episode_id = Column(Integer)
    character_id = Column(Integer)
    scene_id = Column(Integer)
    request_type = Column(String(100))
    request_data = Column(JSONB)
    response_data = Column(JSONB)
    user_feedback = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)