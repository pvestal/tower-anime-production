"""
Project database models for Tower Anime Production API
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from api.core.database import Base


class AnimeProject(Base):
    __tablename__ = "projects"  # Fixed to use correct table name

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    status = Column(String, default="active")
    project_metadata = Column("metadata", JSONB)  # Map to metadata column
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)