"""
Database Models for Animation Orchestration System
SQLAlchemy models for PostgreSQL integration
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel

Base = declarative_base()


class GenerationJob(Base):
    """Generation job model for tracking orchestration jobs"""
    __tablename__ = 'generation_jobs'

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), nullable=True)
    character_id = Column(String(64), nullable=True)
    generation_type = Column(String(50), nullable=False)
    status = Column(String(20), default='queued')
    progress = Column(Float, default=0.0)
    parameters = Column(JSONB)
    result = Column(JSONB)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'character_id': self.character_id,
            'generation_type': self.generation_type,
            'status': self.status,
            'progress': self.progress,
            'parameters': self.parameters,
            'result': self.result,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class ProjectCharacter(Base):
    """Character profile model"""
    __tablename__ = 'character_profiles'

    character_id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    reference_images = Column(ARRAY(Text))
    embedding_ids = Column(ARRAY(Text))
    visual_traits = Column(JSONB)
    style_preferences = Column(ARRAY(String))
    generation_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_metadata = Column('metadata', JSONB)
    last_generated_image = Column(String(512))
    last_generated_video = Column(String(512))

    def to_dict(self):
        return {
            'character_id': self.character_id,
            'name': self.name,
            'description': self.description,
            'reference_images': self.reference_images or [],
            'embedding_ids': self.embedding_ids or [],
            'visual_traits': self.visual_traits or {},
            'style_preferences': self.style_preferences or [],
            'generation_count': self.generation_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.extra_metadata or {},
            'last_generated_image': self.last_generated_image,
            'last_generated_video': self.last_generated_video
        }


class AnimationProject(Base):
    """Animation project model"""
    __tablename__ = 'animation_projects'

    project_id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    characters = Column(JSONB)
    scenes = Column(JSONB)
    assets = Column(ARRAY(Text))
    status = Column(String(20), default='active')
    extra_metadata = Column('metadata', JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'project_id': self.project_id,
            'name': self.name,
            'description': self.description,
            'characters': self.characters or {},
            'scenes': self.scenes or {},
            'assets': self.assets or [],
            'status': self.status,
            'metadata': self.extra_metadata or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UnifiedEmbedding(Base):
    """Unified embedding model"""
    __tablename__ = 'unified_embeddings'

    embedding_id = Column(String(64), primary_key=True)
    embedding_type = Column(String(50), nullable=False)
    source_type = Column(String(50), nullable=False)
    source_data = Column(Text)
    source_hash = Column(String(64), nullable=False)
    extra_metadata = Column('metadata', JSONB)
    vector_dimension = Column(Integer)
    collection_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'embedding_id': self.embedding_id,
            'embedding_type': self.embedding_type,
            'source_type': self.source_type,
            'source_data': self.source_data,
            'source_hash': self.source_hash,
            'metadata': self.extra_metadata or {},
            'vector_dimension': self.vector_dimension,
            'collection_name': self.collection_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AssetRegistry(Base):
    """Asset registry model"""
    __tablename__ = 'asset_registry'

    asset_id = Column(String(64), primary_key=True)
    asset_type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    thumbnail_path = Column(Text)
    embedding_id = Column(String(64))
    project_id = Column(String(64))
    character_id = Column(String(64))
    tags = Column(ARRAY(Text))
    extra_metadata = Column('metadata', JSONB)
    file_size = Column(Integer)
    file_hash = Column(String(64))
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'asset_id': self.asset_id,
            'asset_type': self.asset_type,
            'name': self.name,
            'file_path': self.file_path,
            'thumbnail_path': self.thumbnail_path,
            'embedding_id': self.embedding_id,
            'project_id': self.project_id,
            'character_id': self.character_id,
            'tags': self.tags or [],
            'metadata': self.extra_metadata or {},
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'usage_count': self.usage_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# Pydantic models for API validation
class GenerationJobCreate(BaseModel):
    project_id: Optional[str] = None
    character_id: Optional[str] = None
    generation_type: str
    parameters: Dict[str, Any]


class GenerationJobUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class CharacterProfileCreate(BaseModel):
    name: str
    description: str
    reference_images: List[str] = []
    style_preferences: List[str] = []
    metadata: Dict[str, Any] = {}


class CharacterProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    reference_images: Optional[List[str]] = None
    style_preferences: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None