"""
Database models for Tower Anime Production API
"""
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

# Database Setup
DATABASE_PASSWORD = os.getenv('DATABASE_PASSWORD')
if not DATABASE_PASSWORD:
    raise ValueError("DATABASE_PASSWORD environment variable is required")
DATABASE_URL = f"postgresql://patrick:{DATABASE_PASSWORD}@localhost/anime_production"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class AnimeProject(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    style = Column(String, default="anime")
    characters = Column(JSONB, default=list)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProductionJob(Base):
    __tablename__ = "production_jobs"

    id = Column(String, primary_key=True)
    project_id = Column(Integer)
    job_type = Column(String)
    prompt = Column(Text)
    parameters = Column(JSONB)
    status = Column(String, default="pending")
    progress = Column(Float, default=0.0)
    result_path = Column(String)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

# Database dependency
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()