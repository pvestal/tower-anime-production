#!/usr/bin/env python3
"""
Tower Scene Description Generator Agent
Autonomous Scene Creation System for Professional Anime Production

Port: 8332
Purpose: Professional scene description generation with Echo Brain integration
Features: Visual composition, cinematography, atmosphere, timing orchestration
Revenue: Optimized for autonomous passive income generation
"""

import os
import sys
import asyncio
import logging
import uvicorn
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncpg
import redis
import json

# Scene Description Core Components
from engines.visual_composition_engine import VisualCompositionEngine
from engines.cinematography_engine import CinematographyEngine
from engines.atmosphere_engine import AtmosphereEngine
from engines.timing_engine import TimingOrchestrator
from engines.revenue_engine import RevenueOptimizer
from agents.autonomous_scene_creator import AutonomousSceneCreator
from integrations.echo_brain import EchoBrainIntegration as EchoBrainClient
from integrations.anime_production import AnimeProductionIntegration as AnimeProductionClient
from integrations.story_bible import StoryBibleIntegration as StoryBibleClient
from integrations.script_writer import ScriptWriterIntegration as ScriptWriterClient
from utils.database import DatabaseManager
from utils.logger import setup_logger
from models.scene_models import *

# Initialize FastAPI application
app = FastAPI(
    title="Tower Scene Description Generator Agent",
    description="Autonomous Scene Creation System for Professional Anime Production",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global components
db_manager = None
redis_client = None
visual_engine = None
cinematography_engine = None
atmosphere_engine = None
timing_orchestrator = None
revenue_optimizer = None
autonomous_creator = None
echo_integration = None
anime_integration = None
story_bible_integration = None
script_writer_integration = None

logger = setup_logger(__name__)

# Database connection
async def get_db():
    global db_manager
    if not db_manager:
        db_manager = DatabaseManager()
        await db_manager.initialize()
    return db_manager

# Redis connection
async def get_redis():
    global redis_client
    if not redis_client:
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    return redis_client

@app.on_event("startup")
async def startup_event():
    """Initialize all components on startup"""
    global visual_engine, cinematography_engine, atmosphere_engine, timing_orchestrator
    global revenue_optimizer, autonomous_creator, echo_integration, anime_integration
    global story_bible_integration, script_writer_integration

    logger.info("Starting Tower Scene Description Generator Agent...")

    # Initialize engines (these work without database)
    visual_engine = VisualCompositionEngine()
    cinematography_engine = CinematographyEngine()
    atmosphere_engine = AtmosphereEngine()
    timing_orchestrator = TimingOrchestrator()
    revenue_optimizer = RevenueOptimizer()

    # Initialize autonomous systems
    autonomous_creator = AutonomousSceneCreator(
        visual_engine=visual_engine,
        cinematography_engine=cinematography_engine,
        atmosphere_engine=atmosphere_engine,
        timing_orchestrator=timing_orchestrator
    )

    # Initialize integrations
    echo_integration = EchoBrainClient(base_url="http://localhost:8309")
    anime_integration = AnimeProductionClient(base_url="http://localhost:8328")
    story_bible_integration = StoryBibleClient(base_url="http://localhost:8324")
    script_writer_integration = ScriptWriterClient(base_url="http://localhost:8331")

    # Try to initialize database and redis, but don't fail if unavailable
    try:
        await get_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.warning(f"Database unavailable, running in fallback mode: {e}")

    try:
        await get_redis()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(f"Redis unavailable, caching disabled: {e}")

    logger.info("Tower Scene Description Generator Agent initialized successfully")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "tower-scene-description",
        "port": 8332,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/api/scene-description/status")
async def get_service_status():
    """Get comprehensive service status"""
    db = await get_db()
    redis = await get_redis()

    # Database status
    try:
        await db.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Redis status
    try:
        redis.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"

    # Component status
    return {
        "service": "tower-scene-description",
        "status": "operational",
        "components": {
            "database": db_status,
            "redis": redis_status,
            "visual_engine": "active" if visual_engine else "inactive",
            "cinematography_engine": "active" if cinematography_engine else "inactive",
            "atmosphere_engine": "active" if atmosphere_engine else "inactive",
            "timing_orchestrator": "active" if timing_orchestrator else "inactive",
            "autonomous_creator": "active" if autonomous_creator else "inactive"
        },
        "integrations": {
            "echo_brain": "active" if echo_integration else "inactive",
            "anime_production": "active" if anime_integration else "inactive",
            "story_bible": "active" if story_bible_integration else "inactive",
            "script_writer": "active" if script_writer_integration else "inactive"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

# Scene CRUD Operations
@app.post("/api/scene-description/scenes")
async def create_scene(scene_data: CreateSceneRequest):
    """Create a new scene description"""
    try:
        # Generate comprehensive scene description
        scene_description = await autonomous_creator.generate_scene_description(
            script_id=scene_data.script_id,
            scene_number=scene_data.scene_number,
            location=scene_data.location,
            time_of_day=scene_data.time_of_day,
            characters=scene_data.characters,
            action_summary=scene_data.action_summary,
            mood=scene_data.mood,
            style_preferences=scene_data.style_preferences
        )

        # Try to store in database if available
        scene_id = 1  # Default ID
        try:
            db = await get_db()
            scene_id = await db.execute("""
                INSERT INTO scenes (
                    script_id, scene_number, title, location, time_of_day,
                    characters, action_summary, mood, visual_description,
                    cinematography_notes, atmosphere_description, timing_notes,
                    technical_specifications, created_by, revenue_potential
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING id
            """,
                scene_data.script_id,
                scene_data.scene_number,
                scene_description["title"],
                scene_data.location,
                scene_data.time_of_day,
                json.dumps(scene_data.characters),
                scene_data.action_summary,
                scene_data.mood,
                scene_description["visual_description"],
                scene_description["cinematography_notes"],
                scene_description["atmosphere_description"],
                scene_description["timing_notes"],
                json.dumps(scene_description["technical_specifications"]),
                scene_data.created_by,
                scene_description["revenue_potential"]
            )
        except Exception as db_error:
            logger.warning(f"Database storage failed, returning scene without persistence: {db_error}")

        # Try to log to Echo Brain for learning
        try:
            await echo_integration.log_scene_creation(scene_id, scene_description)
        except Exception as echo_error:
            logger.warning(f"Echo Brain logging failed: {echo_error}")

        return {
            "id": scene_id,
            **scene_description,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "database_stored": scene_id != 1
        }

    except Exception as e:
        logger.error(f"Scene creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scene creation failed: {str(e)}")

@app.get("/api/scene-description/scenes/{scene_id}", response_model=SceneResponse)
async def get_scene(scene_id: int):
    """Get scene description by ID"""
    try:
        db = await get_db()

        scene = await db.fetchrow("""
            SELECT * FROM scenes WHERE id = $1
        """, scene_id)

        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        return SceneResponse(**dict(scene))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scene retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scene retrieval failed: {str(e)}")

@app.get("/api/scene-description/scripts/{script_id}/scenes", response_model=List[SceneResponse])
async def get_script_scenes(script_id: int, limit: int = 50, offset: int = 0):
    """Get all scenes for a script"""
    try:
        db = await get_db()

        scenes = await db.fetch("""
            SELECT * FROM scenes
            WHERE script_id = $1
            ORDER BY scene_number ASC
            LIMIT $2 OFFSET $3
        """, script_id, limit, offset)

        return [SceneResponse(**dict(scene)) for scene in scenes]

    except Exception as e:
        logger.error(f"Script scenes retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Script scenes retrieval failed: {str(e)}")

@app.put("/api/scene-description/scenes/{scene_id}", response_model=SceneResponse)
async def update_scene(scene_id: int, scene_data: UpdateSceneRequest):
    """Update scene description"""
    try:
        db = await get_db()

        # Regenerate description if content changed
        if scene_data.regenerate_description:
            scene_description = await autonomous_creator.regenerate_scene_description(
                scene_id=scene_id,
                updates=scene_data.dict(exclude_unset=True)
            )
        else:
            scene_description = {}

        # Update database
        await db.execute("""
            UPDATE scenes SET
                title = COALESCE($2, title),
                location = COALESCE($3, location),
                time_of_day = COALESCE($4, time_of_day),
                characters = COALESCE($5, characters),
                action_summary = COALESCE($6, action_summary),
                mood = COALESCE($7, mood),
                visual_description = COALESCE($8, visual_description),
                cinematography_notes = COALESCE($9, cinematography_notes),
                atmosphere_description = COALESCE($10, atmosphere_description),
                timing_notes = COALESCE($11, timing_notes),
                technical_specifications = COALESCE($12, technical_specifications),
                updated_at = NOW()
            WHERE id = $1
        """,
            scene_id,
            scene_data.title,
            scene_data.location,
            scene_data.time_of_day,
            json.dumps(scene_data.characters) if scene_data.characters else None,
            scene_data.action_summary,
            scene_data.mood,
            scene_description.get("visual_description"),
            scene_description.get("cinematography_notes"),
            scene_description.get("atmosphere_description"),
            scene_description.get("timing_notes"),
            json.dumps(scene_description.get("technical_specifications")) if scene_description.get("technical_specifications") else None
        )

        # Return updated scene
        return await get_scene(scene_id)

    except Exception as e:
        logger.error(f"Scene update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scene update failed: {str(e)}")

@app.delete("/api/scene-description/scenes/{scene_id}")
async def delete_scene(scene_id: int):
    """Delete scene description"""
    try:
        db = await get_db()

        result = await db.execute("""
            DELETE FROM scenes WHERE id = $1
        """, scene_id)

        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Scene not found")

        return {"message": "Scene deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scene deletion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scene deletion failed: {str(e)}")

# Advanced Scene Generation Endpoints
@app.post("/api/scene-description/generate/batch")
async def generate_batch_scenes(request: BatchSceneRequest):
    """Generate multiple scenes from script"""
    try:
        scenes = await autonomous_creator.generate_batch_scenes(
            script_id=request.script_id,
            scene_count=request.scene_count,
            style_preferences=request.style_preferences,
            revenue_optimization=request.revenue_optimization
        )

        return {
            "generated_scenes": len(scenes),
            "scenes": scenes,
            "batch_id": request.script_id,
            "generation_time": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Batch scene generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch generation failed: {str(e)}")

@app.post("/api/scene-description/export/anime")
async def export_to_anime_production(request: ExportAnimeRequest):
    """Export scene descriptions to anime production system"""
    try:
        export_result = await anime_integration.export_scene_descriptions(
            scene_ids=request.scene_ids,
            project_id=request.project_id,
            export_options=request.export_options
        )

        return {
            "success": True,
            "anime_project_id": export_result["project_id"],
            "export_summary": export_result["summary"],
            "generation_queue_id": export_result.get("queue_id")
        }

    except Exception as e:
        logger.error(f"Anime export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Anime export failed: {str(e)}")

@app.post("/api/scene-description/autonomous/optimize")
async def autonomous_revenue_optimization():
    """Trigger autonomous revenue optimization"""
    try:
        optimization_result = await revenue_optimizer.optimize_existing_scenes()

        return {
            "optimization_complete": True,
            "scenes_optimized": optimization_result["count"],
            "revenue_increase": optimization_result["revenue_increase"],
            "optimization_summary": optimization_result["summary"]
        }

    except Exception as e:
        logger.error(f"Revenue optimization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")

# Echo Brain Integration Endpoints
@app.post("/api/scene-description/echo/collaborate")
async def collaborate_with_echo(request: EchoCollaborationRequest):
    """Collaborate with Echo Brain for advanced scene generation"""
    try:
        collaboration_result = await echo_integration.collaborative_scene_creation(
            prompt=request.prompt,
            context=request.context,
            creative_parameters=request.creative_parameters
        )

        return collaboration_result

    except Exception as e:
        logger.error(f"Echo collaboration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Echo collaboration failed: {str(e)}")

# Analytics and Metrics
@app.get("/api/scene-description/analytics/performance")
async def get_performance_analytics():
    """Get scene generation performance analytics"""
    try:
        db = await get_db()

        analytics = await db.fetchrow("""
            SELECT
                COUNT(*) as total_scenes,
                AVG(revenue_potential) as avg_revenue_potential,
                COUNT(DISTINCT script_id) as unique_scripts,
                AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_generation_time
            FROM scenes
            WHERE created_at >= NOW() - INTERVAL '30 days'
        """)

        return {
            "period": "30_days",
            "metrics": dict(analytics),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Analytics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting Tower Scene Description Generator Agent on port 8332...")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8332,
        reload=False,
        log_level="info"
    )