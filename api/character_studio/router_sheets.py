"""
character_studio/router_sheets.py
API routes for character sheet generation (turnarounds, expressions, poses)
Phase 2: Character Consistency & Expressions
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from database import get_db
# from models import CharacterGeneration  # Model not available yet
from .character_sheets import CharacterSheetGenerator
from .schemas import CharacterGenerateRequest

router = APIRouter(prefix="/api/anime/character-sheets", tags=["character-sheets"])


class TurnaroundRequest(BaseModel):
    """Request to generate character turnaround sheet"""
    angles: Optional[List[str]] = Field(None, description="Specific angles (default: all 8)")


class ExpressionRequest(BaseModel):
    """Request to generate character expressions"""
    expressions: Optional[List[str]] = Field(None, description="Specific expressions (default: 5 basic)")


class PoseRequest(BaseModel):
    """Request to generate character poses"""
    poses: Optional[List[str]] = Field(None, description="Specific poses (default: 4 basic)")


class CharacterSheetResponse(BaseModel):
    """Response from character sheet generation"""
    character_id: int
    sheet_type: str  # turnaround, expression, pose
    results: List[dict]
    total_generated: int
    errors: List[str]


@router.post("/{character_id}/turnaround", response_model=CharacterSheetResponse)
async def generate_turnaround_sheet(
    character_id: int,
    request: TurnaroundRequest = TurnaroundRequest(),
    db: Session = Depends(get_db)
):
    """
    Generate 8-view turnaround sheet for character
    
    Creates multiple views of the character from different angles
    for animation reference purposes.
    
    Default angles: front, front_3quarter, side, back_3quarter, back, etc.
    """
    # Get base character
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Build base request from character record
    base_request = CharacterGenerateRequest(
        character_name=character.character_name,
        project=character.project,
        prompt=character.prompt,
        negative_prompt=character.negative_prompt,
        checkpoint=character.checkpoint,
        width=character.width or 512,
        height=character.height or 768,
        steps=character.steps or 28,
        cfg_scale=character.cfg_scale or 7.0,
        seed=character.seed or -1,
        sampler=character.sampler_name or "dpmpp_2m",
        scheduler=character.scheduler or "karras"
    )
    
    # Generate turnaround
    generator = CharacterSheetGenerator()
    results = await generator.generate_turnaround(
        character_id=character_id,
        base_request=base_request,
        db=db,
        angles=request.angles
    )
    
    # Collect errors
    errors = [r.get("error") for r in results if "error" in r]
    successful = [r for r in results if "error" not in r]
    
    return CharacterSheetResponse(
        character_id=character_id,
        sheet_type="turnaround",
        results=results,
        total_generated=len(successful),
        errors=errors
    )


@router.post("/{character_id}/expressions", response_model=CharacterSheetResponse)
async def generate_expression_sheet(
    character_id: int,
    request: ExpressionRequest = ExpressionRequest(),
    db: Session = Depends(get_db)
):
    """
    Generate facial expression sheet for character
    
    Creates multiple facial expressions for animation:
    neutral, happy, sad, angry, surprised, etc.
    """
    # Get base character
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Build base request from character record
    base_request = CharacterGenerateRequest(
        character_name=character.character_name,
        project=character.project,
        prompt=character.prompt,
        negative_prompt=character.negative_prompt,
        checkpoint=character.checkpoint,
        width=512,  # Smaller for expression close-ups
        height=768,
        steps=character.steps or 28,
        cfg_scale=character.cfg_scale or 7.0,
        seed=character.seed or -1,
        sampler=character.sampler_name or "dpmpp_2m",
        scheduler=character.scheduler or "karras"
    )
    
    # Generate expressions
    generator = CharacterSheetGenerator()
    results = await generator.generate_expressions(
        character_id=character_id,
        base_request=base_request,
        db=db,
        expressions=request.expressions
    )
    
    # Collect errors
    errors = [r.get("error") for r in results if "error" in r]
    successful = [r for r in results if "error" not in r]
    
    return CharacterSheetResponse(
        character_id=character_id,
        sheet_type="expression",
        results=results,
        total_generated=len(successful),
        errors=errors
    )


@router.post("/{character_id}/poses", response_model=CharacterSheetResponse)
async def generate_pose_sheet(
    character_id: int,
    request: PoseRequest = PoseRequest(),
    db: Session = Depends(get_db)
):
    """
    Generate pose reference sheet for character
    
    Creates character in different poses:
    standing, sitting, walking, running, etc.
    """
    # Get base character
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Build base request from character record
    base_request = CharacterGenerateRequest(
        character_name=character.character_name,
        project=character.project,
        prompt=character.prompt,
        negative_prompt=character.negative_prompt,
        checkpoint=character.checkpoint,
        width=character.width or 512,
        height=character.height or 768,
        steps=character.steps or 28,
        cfg_scale=character.cfg_scale or 7.0,
        seed=character.seed or -1,
        sampler=character.sampler_name or "dpmpp_2m",
        scheduler=character.scheduler or "karras"
    )
    
    # Generate poses
    generator = CharacterSheetGenerator()
    results = await generator.generate_pose_sheet(
        character_id=character_id,
        base_request=base_request,
        db=db,
        poses=request.poses
    )
    
    # Collect errors
    errors = [r.get("error") for r in results if "error" in r]
    successful = [r for r in results if "error" not in r]
    
    return CharacterSheetResponse(
        character_id=character_id,
        sheet_type="pose",
        results=results,
        total_generated=len(successful),
        errors=errors
    )


@router.get("/{character_id}/sheets")
async def list_character_sheets(
    character_id: int,
    db: Session = Depends(get_db)
):
    """
    List all generated sheets for a character
    
    Returns turnarounds, expressions, and poses
    """
    from models import CharacterTurnaround, CharacterExpression
    
    character = db.query(CharacterGeneration).filter(
        CharacterGeneration.id == character_id
    ).first()
    
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    turnarounds = db.query(CharacterTurnaround).filter(
        CharacterTurnaround.character_id == character_id
    ).all()
    
    expressions = db.query(CharacterExpression).filter(
        CharacterExpression.character_id == character_id
    ).all()
    
    return {
        "character_id": character_id,
        "character_name": character.character_name,
        "project": character.project,
        "turnarounds": [
            {
                "angle": t.angle,
                "image_path": t.image_path,
                "seed": t.seed,
                "created_at": t.created_at.isoformat()
            }
            for t in turnarounds
        ],
        "expressions": [
            {
                "expression": e.expression,
                "image_path": e.image_path,
                "seed": e.seed,
                "created_at": e.created_at.isoformat()
            }
            for e in expressions
        ]
    }
