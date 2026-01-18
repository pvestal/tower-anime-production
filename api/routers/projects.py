"""
Projects router for Tower Anime Production API
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List
from api.models.database import get_db, AnimeProject, ProductionJob
from api.models.schemas import AnimeProjectCreate, AnimeProjectResponse
from api.dependencies.auth import require_auth, require_admin

router = APIRouter(prefix="/api/anime/projects", tags=["projects"])

@router.get("", response_model=List[AnimeProjectResponse])
async def get_projects(current_user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """Get all anime projects"""
    projects = db.query(AnimeProject).all()
    return projects

@router.post("", response_model=AnimeProjectResponse)
async def create_project(
    project: AnimeProjectCreate,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create new anime project"""
    db_project = AnimeProject(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.patch("/{project_id}")
async def update_project(
    project_id: int,
    updates: dict,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update anime project"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for key, value in updates.items():
        if hasattr(project, key):
            setattr(project, key, value)

    db.commit()
    db.refresh(project)
    return project

@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete anime project"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
    return {"message": "Project deleted successfully"}

@router.put("/{project_id}")
async def replace_project(
    project_id: int,
    update_data: dict,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Replace anime project"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for key, value in update_data.items():
        if hasattr(project, key):
            setattr(project, key, value)

    db.commit()
    db.refresh(project)
    return project

@router.get("/{project_id}/history")
async def get_project_history(
    project_id: int,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get project history"""
    project = db.query(AnimeProject).filter(AnimeProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    jobs = db.query(ProductionJob).filter(ProductionJob.project_id == project_id).all()
    return {
        "history": [
            {
                "id": job.id,
                "type": job.job_type,
                "status": job.status,
                "created_at": job.created_at
            }
            for job in jobs
        ]
    }