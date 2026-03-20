"""Production Orchestrator — FastAPI endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import orchestrator
from . import generation_loop

router = APIRouter()


class ToggleRequest(BaseModel):
    enabled: bool = True


class InitializeRequest(BaseModel):
    project_id: int
    training_target: int | None = None


class OverrideRequest(BaseModel):
    entity_type: str  # "character" or "project"
    entity_id: str
    phase: str
    action: str  # "skip", "reset", "complete"


class TrainingTargetRequest(BaseModel):
    target: int


class PriorityRequest(BaseModel):
    project_id: int
    priority: int  # higher = processed first, 0 = default


@router.get("/orchestrator/status")
async def get_status():
    """Global orchestrator on/off + config."""
    return {
        "enabled": orchestrator.is_enabled(),
        "training_target": orchestrator._training_target,
        "tick_interval": orchestrator._tick_interval,
    }


@router.get("/orchestrator/health")
async def orchestrator_health():
    """Watchdog health: last success time, queue depth, active tasks."""
    return await orchestrator.get_orchestrator_health()


@router.post("/orchestrator/toggle")
async def toggle(req: ToggleRequest):
    """Enable or disable the orchestrator."""
    await orchestrator.enable(req.enabled)
    return {"enabled": orchestrator.is_enabled()}


@router.post("/orchestrator/initialize")
async def initialize(req: InitializeRequest):
    """Bootstrap pipeline entries for a project."""
    try:
        result = await orchestrator.initialize_project(
            req.project_id, req.training_target
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orchestrator/pipeline/{project_id}")
async def pipeline_status(project_id: int):
    """Full structured pipeline status for dashboard."""
    return await orchestrator.get_pipeline_status(project_id)


@router.get("/orchestrator/summary/{project_id}")
async def pipeline_summary(project_id: int):
    """Human-readable summary for Echo Brain context."""
    text = await orchestrator.get_pipeline_summary(project_id)
    return {"project_id": project_id, "summary": text}


@router.post("/orchestrator/tick")
async def manual_tick():
    """Trigger a single evaluation pass."""
    result = await orchestrator.tick()
    return result


@router.post("/orchestrator/override")
async def override(req: OverrideRequest):
    """Force a phase status (skip, reset, complete)."""
    try:
        result = await orchestrator.override_phase(
            req.entity_type, req.entity_id, req.phase, req.action
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orchestrator/training-target")
async def set_training_target(req: TrainingTargetRequest):
    """Set the approved image threshold for training_data phase."""
    orchestrator.set_training_target(req.target)
    return {"training_target": orchestrator._training_target}


@router.post("/orchestrator/priority")
async def set_priority(req: PriorityRequest):
    """Set project priority. Higher number = processed first. 0 = default."""
    return await orchestrator.set_project_priority(req.project_id, req.priority)


@router.get("/orchestrator/priorities")
async def get_priorities():
    """Get all project priorities with pending phase counts."""
    priorities = await orchestrator.get_project_priorities()
    return {"projects": priorities}


# ── Generation Loop Endpoints ─────────────────────────────────────────


class GenLoopEnableRequest(BaseModel):
    enabled: bool = True


class GenLoopStartRequest(BaseModel):
    project_id: int
    config: dict | None = None


class GenLoopConfigRequest(BaseModel):
    project_id: int
    auto_approve_threshold: float | None = None
    burst_enabled: bool | None = None
    burst_budget_cap: float | None = None
    burst_queue_threshold: int | None = None
    target_keyframes_per_lora: int | None = None
    max_concurrent_videos: int | None = None
    tick_interval_seconds: int | None = None
    video_enabled: bool | None = None
    assembly_enabled: bool | None = None
    dry_run: bool | None = None
    keyframe_batch_size: int | None = None


@router.post("/generation-loop/enable")
async def enable_gen_loop(req: GenLoopEnableRequest):
    """Enable or disable the generation loop system. Must be called before starting any loops."""
    return await generation_loop.enable(req.enabled)


@router.post("/generation-loop/start")
async def start_gen_loop(req: GenLoopStartRequest):
    """Start a continuous generation loop for a project. Requires enable() first."""
    return await generation_loop.start_loop(req.project_id, req.config)


@router.post("/generation-loop/stop")
async def stop_gen_loop(req: GenLoopStartRequest):
    """Stop a generation loop for a project."""
    return await generation_loop.stop_loop(req.project_id)


@router.get("/generation-loop/status")
async def gen_loop_status(project_id: int | None = None):
    """Get status of generation loops."""
    return await generation_loop.get_status(project_id)


@router.put("/generation-loop/config")
async def update_gen_loop_config(req: GenLoopConfigRequest):
    """Update generation loop config for a running loop (or save to DB for next start)."""
    loop = generation_loop.get_loop(req.project_id)

    # Build config update from non-None fields
    updates = {k: v for k, v in req.model_dump().items() if v is not None and k != "project_id"}

    if loop and loop._running:
        loop.config.update(updates)
        return {"status": "updated", "project_id": req.project_id, "config": loop.config}

    # Save to DB for next start
    from .db import connect_direct
    import json
    conn = await connect_direct()
    try:
        existing = await conn.fetchval(
            "SELECT gen_loop_config FROM projects WHERE id = $1", req.project_id,
        )
        current = json.loads(existing) if existing else {}
        current.update(updates)
        await conn.execute(
            "UPDATE projects SET gen_loop_config = $2 WHERE id = $1",
            req.project_id, json.dumps(current),
        )
        return {"status": "saved", "project_id": req.project_id, "config": current}
    finally:
        await conn.close()
