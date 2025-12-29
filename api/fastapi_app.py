#!/usr/bin/env python3
"""
Tower Anime Production FastAPI Application with SSOT Integration
Phase 2: Minimal working implementation
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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


@app.post("/api/anime/generate")
async def generate_anime(request: Request):
    """Main generation endpoint - automatically tracked by SSOT"""
    try:
        data = await request.json()

        # Access SSOT tracking ID from request state
        ssot_id = getattr(request.state, 'ssot_request_id', None)

        # Simulate generation logic
        result = {
            "success": True,
            "message": "Generation request received and tracked",
            "ssot_tracking_id": ssot_id,
            "prompt": data.get('prompt', 'No prompt provided'),
            "timestamp": datetime.utcnow().isoformat()
        }

        # Log for verification
        logger.info(f"Generation request tracked: {ssot_id}")

        return result

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


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