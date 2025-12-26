"""
character_studio/router.py
FastAPI router for Character Studio endpoints
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path

from database import get_db
from .schemas import (
    CharacterGenerateRequest,
    CharacterGenerateResponse,
    CharacterListResponse,
    CharacterListItem,
    CharacterDetailResponse
)
from .service import CharacterGenerationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anime/character")

# Instantiate service
service = CharacterGenerationService()


@router.post("/generate", response_model=CharacterGenerateResponse)
async def generate_character(
    request: CharacterGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a character image with optional ControlNet pose control

    This endpoint:
    1. Builds a ComfyUI workflow
    2. Submits to ComfyUI for generation
    3. Waits for completion
    4. Moves output to organized directory
    5. Saves metadata to database
    """
    try:
        return await service.generate_character(request, db)
    except Exception as e:
        logger.error(f"Character generation endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=CharacterListResponse)
async def list_characters(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    project: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    List generated characters with pagination

    Query params:
    - skip: Offset for pagination
    - limit: Number of results
    - project: Filter by project name (optional)
    """
    try:
        characters, total = await service.list_characters(db, skip, limit, project)

        return CharacterListResponse(
            characters=[CharacterListItem.from_orm(c) for c in characters],
            total=total,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error(f"List characters error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{character_id}", response_model=CharacterDetailResponse)
async def get_character_detail(
    character_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a character generation"""
    try:
        character = await service.get_character_by_id(character_id, db)

        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        return CharacterDetailResponse.from_orm(character)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get character detail error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{character_id}/image")
async def get_character_image(
    character_id: int,
    db: Session = Depends(get_db)
):
    """Serve the generated character image file"""
    try:
        character = await service.get_character_by_id(character_id, db)

        if not character:
            raise HTTPException(status_code=404, detail="Character not found")

        image_path = Path(character.output_path)

        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")

        return FileResponse(image_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get character image error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
