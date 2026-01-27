"""
Project management endpoints for Tower Anime Production API
Handles anime project CRUD operations
"""

import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.core.database import get_db
from api.core.security import require_auth, require_admin, require_user_or_admin, guest_or_auth
from api.models import AnimeProject
from api.schemas.requests import AnimeProjectCreate
from api.schemas.responses import AnimeProjectResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/anime/projects", response_model=List[AnimeProjectResponse])
async def get_projects(
    current_user: dict = Depends(guest_or_auth),
    db: Session = Depends(get_db)
):
    """Get all anime projects (Guest access allowed)"""
    projects = db.query(AnimeProject).all()
    return projects


@router.post("/api/anime/projects", response_model=AnimeProjectResponse)
async def create_project(
    project: AnimeProjectCreate,
    current_user: dict = Depends(require_user_or_admin),
    db: Session = Depends(get_db)
):
    """Create new anime project (Requires authentication)"""
    db_project = AnimeProject(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    logger.info(f"Created new project: {db_project.name} (ID: {db_project.id})")
    return db_project


@router.get("/api/anime/projects/{project_id}", response_model=AnimeProjectResponse)
async def get_project(
    project_id: int,
    current_user: dict = Depends(guest_or_auth),
    db: Session = Depends(get_db)
):
    """Get specific project by ID"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/api/anime/projects/{project_id}")
async def update_project_patch(
    project_id: int,
    updates: dict,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update anime project (PATCH method)"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update only provided fields
    for key, value in updates.items():
        if hasattr(project, key):
            setattr(project, key, value)

    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)

    logger.info(f"Updated project {project_id}: {list(updates.keys())}")
    return project


@router.delete("/api/anime/projects/{project_id}")
async def delete_project(
    project_id: int,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete anime project (Admin only)"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_name = project.name
    db.delete(project)
    db.commit()

    logger.info(f"Deleted project: {project_name} (ID: {project_id})")
    return {"message": "Project deleted successfully"}