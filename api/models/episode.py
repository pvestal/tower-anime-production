"""
Episode database models for Tower Anime Production API
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from api.core.database import Base


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    name = Column(String, index=True)
    description = Column(Text)
    episode_number = Column(Integer)
    duration = Column(Float)  # Total episode duration in seconds
    status = Column(String, default="planned")  # planned, in_progress, completed
    episode_data = Column(JSONB)  # Store episode metadata, scene order, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)