"""Feedback Loop API — endpoints for interactive video review feedback + LoRA effectiveness.

POST /api/feedback/review   — submit rating + categories, get diagnostic questions
POST /api/feedback/answer   — pick an option, execute corrective action
GET  /api/feedback/history/{shot_id} — get all feedback rounds for a shot
POST /api/feedback/effectiveness/refresh — re-aggregate LoRA effectiveness from QC data
GET  /api/feedback/effectiveness/character/{slug} — best LoRAs for a character
GET  /api/feedback/effectiveness/top — top LoRAs overall
GET  /api/feedback/effectiveness/lora/{lora_key} — cross-project summary for a LoRA
GET  /api/feedback/effectiveness/params/{lora_key} — recommended params for a LoRA
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .feedback_loop import submit_feedback, answer_question, get_feedback_history
from .lora_effectiveness import (
    refresh_effectiveness,
    best_loras_for_character,
    best_loras_overall,
    recommended_params,
    lora_effectiveness_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


class ReviewRequest(BaseModel):
    shot_id: str
    rating: int = Field(ge=1, le=5)
    feedback_text: str = ""
    feedback_categories: list[str] = Field(default_factory=list)


class AnswerRequest(BaseModel):
    shot_id: str
    feedback_id: str
    question_id: str
    selected_option: str
    extra_params: Optional[dict] = None


@router.post("/review")
async def review_endpoint(req: ReviewRequest):
    """Submit feedback for a shot — returns diagnostic questions."""
    result = await submit_feedback(
        shot_id=req.shot_id,
        rating=req.rating,
        feedback_text=req.feedback_text,
        feedback_categories=req.feedback_categories,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/answer")
async def answer_endpoint(req: AnswerRequest):
    """Answer a diagnostic question — executes corrective action and queues regeneration."""
    result = await answer_question(
        shot_id=req.shot_id,
        feedback_id=req.feedback_id,
        question_id=req.question_id,
        selected_option=req.selected_option,
        extra_params=req.extra_params,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/history/{shot_id}")
async def history_endpoint(shot_id: str):
    """Get all feedback rounds for a shot."""
    history = await get_feedback_history(shot_id)
    return {"shot_id": shot_id, "rounds": history, "total": len(history)}


# ── LoRA Effectiveness endpoints ──────────────────────────────────────


@router.post("/effectiveness/refresh")
async def refresh_effectiveness_endpoint(project_id: Optional[int] = None):
    """Re-aggregate LoRA effectiveness from QC data across all projects."""
    count = await refresh_effectiveness(project_id)
    return {"upserted": count}


@router.get("/effectiveness/character/{slug}")
async def effectiveness_for_character(
    slug: str,
    content_rating: Optional[str] = None,
    project_id: Optional[int] = None,
    limit: int = Query(default=5, le=20),
):
    """Best-performing LoRAs for a specific character, ranked by avg quality."""
    results = await best_loras_for_character(
        character_slug=slug,
        content_rating=content_rating,
        project_id=project_id,
        limit=limit,
    )
    return {"character": slug, "results": results, "total": len(results)}


@router.get("/effectiveness/top")
async def top_loras_endpoint(
    content_rating: Optional[str] = None,
    min_samples: int = Query(default=3, ge=1),
    limit: int = Query(default=10, le=50),
):
    """Top LoRAs across all characters and projects."""
    results = await best_loras_overall(
        content_rating=content_rating,
        min_samples=min_samples,
        limit=limit,
    )
    return {"results": results, "total": len(results)}


@router.get("/effectiveness/lora/{lora_key}")
async def lora_summary_endpoint(lora_key: str):
    """Full cross-project summary for a single LoRA key."""
    summary = await lora_effectiveness_summary(lora_key)
    return summary


@router.get("/effectiveness/params/{lora_key}")
async def lora_params_endpoint(
    lora_key: str,
    character_slug: Optional[str] = None,
):
    """Get recommended generation params for a LoRA based on historical performance."""
    params = await recommended_params(lora_key, character_slug)
    if not params:
        return {"lora_key": lora_key, "recommendation": None, "message": "No effectiveness data yet"}
    return {"lora_key": lora_key, "recommendation": params}
