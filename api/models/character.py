"""
Character database models for Tower Anime Production API
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from api.core.database import Base


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    project_id = Column(Integer)
    character_data = Column(JSONB)  # Store character traits, appearance, etc.
    lora_available = Column(Boolean, default=False)
    lora_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)