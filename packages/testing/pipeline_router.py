"""Pipeline test API endpoints — validate config, run keyframe tests, full pipeline tests."""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class ValidateRequest(BaseModel):
    project_id: int


class KeyframeTestRequest(BaseModel):
    project_id: int
    character_slugs: Optional[list[str]] = None
    shot_types: Optional[list[str]] = None
    dry_run: bool = False


class PipelineTestRequest(BaseModel):
    project_id: int
    character_slugs: Optional[list[str]] = None
    include_video: bool = True


@router.post("/validate-config")
async def validate_config(req: ValidateRequest):
    """Pre-flight config validation — checks characters, LoRAs, checkpoints, ComfyUI health."""
    from .pipeline_test import validate_project_config
    return await validate_project_config(req.project_id)


@router.post("/keyframe-test")
async def keyframe_test(req: KeyframeTestRequest):
    """Generate test keyframes using production code paths."""
    from .pipeline_test import run_keyframe_test
    return await run_keyframe_test(
        req.project_id,
        character_slugs=req.character_slugs,
        shot_types=req.shot_types,
        dry_run=req.dry_run,
    )


@router.post("/pipeline-test")
async def pipeline_test(req: PipelineTestRequest):
    """Full keyframe-to-video pipeline test using production code."""
    from .pipeline_test import run_pipeline_test
    return await run_pipeline_test(
        req.project_id,
        character_slugs=req.character_slugs,
        include_video=req.include_video,
    )


@router.get("/pipeline-test/{batch_id}")
async def get_pipeline_results(batch_id: str):
    """Get results for a pipeline test batch from prompt_tests table."""
    from packages.core.db import connect_direct
    conn = await connect_direct()
    try:
        rows = await conn.fetch(
            "SELECT * FROM prompt_tests WHERE batch_id = $1 ORDER BY id", batch_id
        )
        if not rows:
            return {"batch_id": batch_id, "tests": [], "message": "No results found"}
        return {"batch_id": batch_id, "tests": [dict(r) for r in rows]}
    finally:
        await conn.close()
