"""
Scene database models for Tower Anime Production API
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from api.core.database import Base


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    episode_id = Column(Integer)
    name = Column(String, index=True)
    description = Column(Text)
    scene_type = Column(String)  # dialogue, action, transition, etc.
    duration = Column(Float)  # Scene duration in seconds
    scene_data = Column(JSONB)  # Store scene details, characters involved, etc.
    status = Column(String, default="planned")  # planned, in_progress, completed
    order_index = Column(Integer)  # Order within episode
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)