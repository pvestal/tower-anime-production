#!/usr/bin/env python3
"""
Tower Anime Production Service - Main API with SSOT Integration
Phase 2: SSOT Middleware Implementation
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
import uvicorn

# Add paths for imports
sys.path.append('/opt/tower-anime-production')
sys.path.append('/opt/tower-anime-production/middleware')
sys.path.append('/opt/tower-anime-production/services')
sys.path.append('/opt/tower-anime-production/services/ssot')
sys.path.append('/opt/tower-anime-production/dashboard')
sys.path.append('/opt/tower-anime-production/dashboard/ssot')

# Import SSOT middleware and monitoring
from ssot_tracker import SSOTTracker
from ssot_monitor import router as ssot_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Tower Anime Production API with SSOT",
    description="Anime production service with comprehensive SSOT tracking",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Initialize SSOT tracker
DATABASE_URL = f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', 'tower_echo_brain_secret_key_2025')}@localhost/anime_production"
ssot_tracker = SSOTTracker(DATABASE_URL)

# Add SSOT middleware
@app.middleware("http")
async def ssot_middleware(request: Request, call_next):
    """SSOT tracking middleware"""
    return await ssot_tracker(request, call_next)

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await ssot_tracker.initialize()
    logger.info("✅ SSOT tracking initialized")
    logger.info("✅ Tower Anime Production API started on port 8305")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await ssot_tracker.close()
    logger.info("SSOT tracking shut down")

# Include SSOT monitoring dashboard
app.include_router(ssot_router, prefix="/api/anime")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "service": "Tower Anime Production API",
        "ssot_enabled": True,
        "timestamp": datetime.utcnow().isoformat()
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Tower Anime Production API",
        "version": "2.0.0",
        "ssot_tracking": "enabled",
        "dashboard": "/api/anime/ssot/metrics"
    }

# Generation endpoints (these will be tracked by SSOT)
class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = ""
    model: Optional[str] = "default"
    parameters: Optional[Dict[str, Any]] = {}

@app.post("/api/anime/generate")
async def generate(request: GenerationRequest):
    """Main generation endpoint - tracked by SSOT"""
    try:
        # This is a placeholder - actual generation logic would go here
        logger.info(f"Generation request: {request.prompt[:50]}...")

        return {
            "status": "success",
            "message": "Generation request received",
            "prompt": request.prompt,
            "tracking_enabled": True
        }
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/anime/generate/image")
async def generate_image(request: GenerationRequest):
    """Image generation endpoint - tracked by SSOT"""
    return {
        "status": "success",
        "type": "image",
        "prompt": request.prompt
    }

@app.post("/api/anime/generate/video")
async def generate_video(request: GenerationRequest):
    """Video generation endpoint - tracked by SSOT"""
    return {
        "status": "success",
        "type": "video",
        "prompt": request.prompt
    }

# Projects endpoints
@app.get("/api/anime/projects")
async def list_projects():
    """List all projects"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        projects = await conn.fetch("SELECT id, name, description, status FROM projects LIMIT 10")
        await conn.close()

        return {
            "projects": [dict(p) for p in projects],
            "count": len(projects)
        }
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
        return {"projects": [], "error": str(e)}

# Test endpoint for SSOT verification
@app.post("/api/anime/test-ssot")
async def test_ssot(data: dict):
    """Test endpoint to verify SSOT tracking"""
    return {
        "message": "SSOT test successful",
        "received": data,
        "timestamp": datetime.utcnow().isoformat()
    }

# Statistics endpoint
@app.get("/api/anime/stats")
async def get_stats():
    """Get production statistics"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Get counts
        project_count = await conn.fetchval("SELECT COUNT(*) FROM projects")
        generation_count = await conn.fetchval("SELECT COUNT(*) FROM project_generations")
        tracking_count = await conn.fetchval("SELECT COUNT(*) FROM ssot_tracking WHERE timestamp > NOW() - INTERVAL '24 hours'")

        await conn.close()

        return {
            "projects": project_count,
            "generations": generation_count,
            "tracked_requests_24h": tracking_count
        }
    except Exception as e:
        return {
            "error": str(e),
            "projects": 0,
            "generations": 0,
            "tracked_requests_24h": 0
        }

if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8305,
        log_level="info"
    )