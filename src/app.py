#!/usr/bin/env python3
"""
Tower Anime Studio v3.2 — Modular FastAPI application.

Mounts all package routers under /api/lora to maintain URL compatibility.
Database credentials loaded from Vault (secret/anime/database).
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.core.auth import AuthMiddleware
from packages.core.db import init_pool, run_migrations
from packages.core.events import event_bus
from packages.core.gpu_router import get_system_status
import packages.core.learning as learning  # registers EventBus handlers on import
import packages.core.auto_correction as auto_correction  # registers EventBus handler on import
import packages.core.replenishment as replenishment  # registers EventBus handler on import
from packages.core.model_selector import recommend_params, detect_drift, character_quality_summary
from packages.lora_training.feedback import reconcile_training_jobs

from packages.story.router import router as story_router
from packages.visual_pipeline.router import router as visual_router
from packages.scene_generation.router import router as scene_router
from packages.lora_training.router import router as training_router
from packages.audio_composition.router import router as audio_router
from packages.echo_integration.router import router as echo_router
from packages.voice_pipeline.router import router as voice_router
from packages.episode_assembly.router import router as episode_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tower Anime Studio", version="3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

# Mount routers — all under /api/lora to maintain URL compatibility
app.include_router(story_router, prefix="/api/lora", tags=["story"])
app.include_router(visual_router, prefix="/api/lora", tags=["visual-pipeline"])
app.include_router(scene_router, prefix="/api/lora", tags=["scene-generation"])
app.include_router(training_router, prefix="/api/lora", tags=["lora-training"])
app.include_router(audio_router, prefix="/api/lora", tags=["audio-composition"])
app.include_router(echo_router, prefix="/api/lora", tags=["echo-integration"])
app.include_router(voice_router, prefix="/api/lora", tags=["voice-pipeline"])
app.include_router(episode_router, prefix="/api/lora", tags=["episode-assembly"])


@app.on_event("startup")
async def startup():
    await init_pool()
    await run_migrations()
    reconcile_training_jobs()
    logger.info("Tower Anime Studio v3.2 started — 8 packages mounted")


@app.get("/api/lora/health")
async def health():
    return {"status": "healthy", "service": "tower-anime-studio", "version": "3.2"}


@app.get("/api/lora/gpu/status")
async def gpu_status():
    """Full GPU dashboard — both GPUs + Ollama + ComfyUI."""
    return get_system_status()


@app.get("/api/lora/events/stats")
async def events_stats():
    """EventBus statistics — registered handlers, emit count, errors."""
    return event_bus.stats()


# --- Learning System Endpoints ---


@app.get("/api/lora/learning/stats")
async def get_learning_stats():
    """Overall learning system statistics for last 30 days."""
    return await learning.learning_stats()


@app.get("/api/lora/learning/suggest/{character_slug}")
async def get_suggestions(character_slug: str):
    """Suggest optimal generation parameters based on historical quality data."""
    params = await learning.suggest_params(character_slug)
    if not params:
        return {"character_slug": character_slug, "suggestions": None,
                "reason": f"Insufficient data (need {learning.MIN_SAMPLES}+ successful generations)"}
    return {"character_slug": character_slug, "suggestions": params}


@app.get("/api/lora/learning/rejections/{character_slug}")
async def get_rejection_patterns(character_slug: str):
    """Top rejection categories for a character."""
    patterns = await learning.rejection_patterns(character_slug)
    return {"character_slug": character_slug, "patterns": patterns}


@app.get("/api/lora/learning/checkpoints/{project_name}")
async def get_checkpoint_rankings(project_name: str):
    """Rank checkpoints by quality score for a project."""
    rankings = await learning.checkpoint_rankings(project_name)
    return {"project_name": project_name, "rankings": rankings}


@app.get("/api/lora/learning/trend")
async def get_quality_trend(character_slug: str = None, project_name: str = None, days: int = 7):
    """Quality score trend over recent days."""
    if not character_slug and not project_name:
        return {"error": "Provide character_slug or project_name"}
    trend = await learning.quality_trend(character_slug=character_slug, project_name=project_name, days=days)
    return {"character_slug": character_slug, "project_name": project_name, "days": days, "trend": trend}


# --- Model Selector & Drift Detection Endpoints ---


@app.get("/api/lora/recommend/{character_slug}")
async def get_recommendations(character_slug: str):
    """Recommend optimal params for a character based on learned patterns."""
    rec = await recommend_params(character_slug)
    return {"character_slug": character_slug, "recommendation": rec}


@app.get("/api/lora/drift")
async def get_drift(character_slug: str = None, project_name: str = None):
    """Detect quality drift — characters whose recent quality is declining."""
    if not character_slug and not project_name:
        # System-wide drift check
        pass
    alerts = await detect_drift(character_slug=character_slug, project_name=project_name)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/api/lora/quality/summary/{project_name}")
async def get_quality_summary(project_name: str):
    """Per-character quality summary for a project."""
    summary = await character_quality_summary(project_name)
    return {"project_name": project_name, "characters": summary}


# --- Auto-Correction & Quality Gates Endpoints ---


@app.get("/api/lora/correction/stats")
async def get_correction_stats():
    """Auto-correction success rate and statistics."""
    return await auto_correction.get_correction_stats()


@app.post("/api/lora/correction/toggle")
async def toggle_auto_correction(enabled: bool = True):
    """Enable or disable auto-correction on rejected images."""
    auto_correction.enable_auto_correction(enabled)
    return {"auto_correction_enabled": enabled}


@app.get("/api/lora/quality/gates")
async def get_quality_gates():
    """Get all configured quality gates with thresholds."""
    gates = await auto_correction.get_quality_gates()
    return {"gates": gates}


@app.put("/api/lora/quality/gates/{gate_name}")
async def update_gate(gate_name: str, threshold: float = None, is_active: bool = None):
    """Update a quality gate threshold or active status."""
    ok = await auto_correction.update_quality_gate(gate_name, threshold, is_active)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Failed to update quality gate")
    return {"gate_name": gate_name, "updated": True}


# --- Replenishment Loop Endpoints ---


@app.get("/api/lora/replenishment/status")
async def get_replenishment_status():
    """Get replenishment loop status — enabled, active tasks, daily counts."""
    return await replenishment.status()


@app.post("/api/lora/replenishment/toggle")
async def toggle_replenishment(enabled: bool = True):
    """Enable or disable the autonomous replenishment loop."""
    replenishment.enable(enabled)
    return {"replenishment_enabled": enabled}


@app.post("/api/lora/replenishment/target")
async def set_replenishment_target(target: int = 20, character_slug: str = None):
    """Set the target approved image count (global or per-character)."""
    replenishment.set_target(character_slug=character_slug, target=target)
    return {
        "target": target,
        "character_slug": character_slug,
        "scope": "character" if character_slug else "global",
    }


@app.get("/api/lora/replenishment/readiness")
async def get_character_readiness(project_name: str = None):
    """Get readiness status for all characters — approved vs target counts."""
    chars = await replenishment.character_readiness(project_name=project_name)
    ready = sum(1 for c in chars if c["ready"])
    return {
        "project_name": project_name,
        "characters": chars,
        "total": len(chars),
        "ready": ready,
        "deficit": len(chars) - ready,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8401)
