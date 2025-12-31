#!/usr/bin/env python3
"""
Tower Anime Production FastAPI Application with SSOT Integration
Phase 2: Minimal working implementation
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import datetime
import asyncpg
import uvicorn
import sys
import os
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add paths for imports
sys.path.append('/opt/tower-anime-production')
sys.path.append('/opt/tower-anime-production/middleware')

# Import SSOT middleware
from ssot_fastapi import SSOTFastAPIMiddleware

# Import routers
from routes.status_endpoint import router as status_router
from routes.generate_production import router as production_router
from routes.generate_video import router as video_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("🚀 Starting Tower Anime Production API with SSOT tracking...")
    yield
    # Shutdown
    logger.info("👋 Shutting down Tower Anime Production API...")


# Create FastAPI app
app = FastAPI(
    title="Tower Anime Production API",
    description="Anime production workflow with comprehensive SSOT tracking",
    version="2.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(status_router)
app.include_router(production_router)
app.include_router(video_router)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add SSOT tracking middleware
app.add_middleware(SSOTFastAPIMiddleware)


# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'anime_production',
    'user': 'patrick',
    'password': os.getenv('DATABASE_PASSWORD', 'tower_echo_brain_secret_key_2025'),
}


async def get_db_connection():
    """Get database connection"""
    return await asyncpg.connect(**DB_CONFIG)


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Tower Anime Production API",
        "version": "2.0.0",
        "ssot_tracking": "enabled",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "generate": "/api/anime/generate",
            "metrics": "/api/anime/ssot/metrics",
            "tracking": "/api/anime/ssot/track/{request_id}"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (not tracked by SSOT)"""
    return {
        "status": "healthy",
        "service": "tower-anime-production",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "ssot_enabled": True
    }


# Generation endpoint is now in generate_production router


# Mount static files directory
app.mount("/static", StaticFiles(directory="/opt/tower-anime-production/static"), name="static")


@app.post("/api/anime/generate/image")
async def generate_image(request: Request):
    """Image generation endpoint"""
    try:
        data = await request.json()
        ssot_id = getattr(request.state, 'ssot_request_id', None)

        return {
            "success": True,
            "type": "image",
            "ssot_tracking_id": ssot_id,
            "prompt": data.get('prompt', ''),
            "parameters": data
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/anime/generate/video")
async def generate_video(request: Request):
    """Video generation endpoint"""
    try:
        data = await request.json()
        ssot_id = getattr(request.state, 'ssot_request_id', None)

        return {
            "success": True,
            "type": "video",
            "ssot_tracking_id": ssot_id,
            "prompt": data.get('prompt', ''),
            "parameters": data
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Frontend Required Endpoints ====================

@app.get("/api/anime/characters")
async def get_characters():
    """Get available characters"""
    return [
        {"id": "mei", "name": "Mei", "description": "Main character"},
        {"id": "zara", "name": "Zara", "description": "Supporting character"}
    ]

@app.get("/api/anime/styles")
async def get_styles():
    """Get available styles"""
    return [
        {"id": "anime", "name": "Anime", "description": "Standard anime style"},
        {"id": "realistic", "name": "Realistic", "description": "Photorealistic style"}
    ]

@app.get("/api/anime/models")
async def get_models():
    """Get available models"""
    return [
        {"id": "svd", "name": "SVD", "type": "video"},
        {"id": "img2img", "name": "Image to Image", "type": "image"}
    ]

@app.get("/api/anime/queue")
async def get_queue():
    """Get job queue"""
    return {
        "running": [],
        "pending": [],
        "completed": []
    }

@app.get("/api/anime/jobs")
async def get_jobs():
    """Get recent jobs"""
    return []

@app.get("/api/anime/projects")
async def get_projects():
    """Get projects"""
    return [
        {
            "id": "tokyo_debt_desire",
            "name": "Tokyo Debt Desire",
            "description": "Urban professional theme",
            "character": "Mei"
        }
    ]

@app.get("/api/anime/projects/")
async def get_projects_alt():
    """Get projects (alternate route)"""
    return await get_projects()

@app.get("/api/anime/generations")
async def get_generations():
    """Get generation history"""
    from pathlib import Path
    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
    files = list(output_dir.glob("MEI_*"))[:10]

    return [
        {
            "id": f.stem,
            "filename": f.name,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "type": "video" if f.suffix == ".mp4" else "image"
        }
        for f in files
    ]

@app.get("/api/anime/system/limits")
async def get_system_limits():
    """Get system limits"""
    return {
        "max_frames": 25,
        "max_resolution": 1024,
        "gpu_memory": 12288,
        "models_available": ["svd", "img2img"]
    }

@app.get("/api/anime/batch/optimal-settings/sfw")
async def get_optimal_settings():
    """Get optimal generation settings"""
    return {
        "resolution": "512x768",
        "steps": 20,
        "cfg_scale": 7.0,
        "sampler": "euler"
    }

@app.get("/api/anime/{character}/profile")
async def get_character_profile(character: str):
    """Get character profile"""
    if character == "zara":
        return {
            "name": "Zara",
            "description": "Supporting character",
            "traits": ["intelligent", "mysterious"]
        }
    return {"detail": "Character not found"}

# ==================== Production Pipeline Endpoints ====================

@app.post("/api/production/tokyo/generate")
async def generate_tokyo_pose(request: Request):
    """Generate Tokyo Debt Desire pose variation"""
    try:
        data = await request.json()
        pose = data.get('pose', 'frontal')

        import subprocess
        import uuid

        job_id = f"TOKYO-{uuid.uuid4().hex[:6].upper()}"

        # Run production pipeline
        cmd = [
            'python3',
            '/opt/tower-anime-production/workflows/production_pipeline_v2.py',
            '--pose', pose,
            '--job-id', job_id
        ]

        subprocess.Popen(cmd, cwd='/opt/tower-anime-production')

        return {
            "success": True,
            "job_id": job_id,
            "project": "tokyo_debt_desire",
            "pose": pose,
            "message": f"Generating {pose} pose for Tokyo project"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/production/status")
async def get_production_status():
    """Get production pipeline status"""
    from pathlib import Path

    output_dir = Path("/mnt/1TB-storage/ComfyUI/output")
    tokyo_outputs = list(output_dir.glob("MEI_Tokyo_*"))
    all_outputs = list(output_dir.glob("MEI_*"))

    return {
        "projects": {
            "tokyo_debt_desire": {
                "canonical": "/mnt/1TB-storage/ComfyUI/input/Mei_Tokyo_Debt_SVD_smooth_00001.png",
                "poses_generated": ["standing", "frontal", "professional", "professional_alt"],
                "output_count": len(tokyo_outputs)
            }
        },
        "statistics": {
            "total_outputs": len(all_outputs),
            "tokyo_outputs": len(tokyo_outputs),
            "last_updated": datetime.utcnow().isoformat()
        }
    }


# ==================== SSOT Monitoring Endpoints ====================

@app.get("/api/anime/ssot/metrics")
async def get_ssot_metrics():
    """Get SSOT tracking metrics"""
    try:
        conn = await get_db_connection()

        result = await conn.fetchrow('''
            SELECT
                COUNT(*) as total_requests,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN status = 'initiated' THEN 1 END) as in_progress,
                COALESCE(AVG(processing_time), 0) as avg_response_time,
                COALESCE(MAX(processing_time), 0) as max_response_time,
                COALESCE(MIN(processing_time), 0) as min_response_time,
                COUNT(DISTINCT endpoint) as unique_endpoints,
                MIN(timestamp) as tracking_since
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        ''')

        await conn.close()

        metrics = dict(result) if result else {}
        metrics['timestamp'] = datetime.utcnow().isoformat()

        return metrics

    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}")
        return {
            "error": str(e),
            "total_requests": 0,
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/anime/ssot/track/{request_id}")
async def get_tracking_data(request_id: str):
    """Get tracking data for specific request"""
    try:
        conn = await get_db_connection()

        result = await conn.fetchrow('''
            SELECT * FROM ssot_tracking
            WHERE request_id = $1
        ''', request_id)

        await conn.close()

        if result:
            data = dict(result)
            # Convert datetime objects to strings
            for key in ['timestamp', 'completed_at', 'created_at']:
                if key in data and data[key]:
                    data[key] = data[key].isoformat()
            return data
        else:
            raise HTTPException(status_code=404, detail="Request not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch tracking data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anime/ssot/live")
async def get_live_tracking():
    """Get live tracking data from last 5 minutes"""
    try:
        conn = await get_db_connection()

        results = await conn.fetch('''
            SELECT
                request_id,
                endpoint,
                method,
                status,
                processing_time,
                http_status,
                timestamp
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '5 minutes'
            ORDER BY timestamp DESC
            LIMIT 20
        ''')

        await conn.close()

        data = []
        for row in results:
            item = dict(row)
            if item.get('timestamp'):
                item['timestamp'] = item['timestamp'].isoformat()
            data.append(item)

        return {
            "live_requests": data,
            "count": len(data),
            "window": "last_5_minutes"
        }

    except Exception as e:
        logger.error(f"Failed to fetch live data: {e}")
        return {"error": str(e), "live_requests": []}


@app.get("/api/anime/ssot/health")
async def ssot_health():
    """Check SSOT system health"""
    try:
        conn = await get_db_connection()

        # Check tables exist
        tables = await conn.fetch('''
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('ssot_tracking', 'generation_workflow_decisions')
        ''')

        # Get recent activity
        recent = await conn.fetchval('''
            SELECT COUNT(*)
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '1 minute'
        ''')

        await conn.close()

        return {
            "status": "healthy" if len(tables) == 2 else "degraded",
            "tables_found": [t['table_name'] for t in tables],
            "recent_requests": recent or 0,
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "database": "disconnected",
            "timestamp": datetime.utcnow().isoformat()
        }


@app.post("/api/anime/test-ssot")
async def test_ssot(request: Request):
    """Test endpoint to verify SSOT tracking"""
    try:
        data = await request.json()
        ssot_id = getattr(request.state, 'ssot_request_id', None)

        return {
            "message": "SSOT test successful",
            "ssot_tracking_id": ssot_id,
            "received_data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8305,
        log_level="info",
        access_log=True,
        ws="none"  # Disable WebSocket support to avoid websockets.legacy error
    )