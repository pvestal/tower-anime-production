"""
Production job database models for Tower Anime Production API
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from datetime import datetime
from api.core.database import Base


class ProductionJob(Base):
    __tablename__ = "production_jobs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    job_type = Column(String)  # generation, quality_check, personal_analysis
    prompt = Column(Text)
    parameters = Column(Text)  # JSON parameters
    status = Column(String, default="pending")
    output_path = Column(String)
    quality_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)