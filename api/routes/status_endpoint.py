"""
Comprehensive status endpoint for Tower Anime Production System
Includes SSOT audit history and QC results
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import asyncpg
from typing import Dict, Any, List
import os

router = APIRouter()

async def get_db_connection():
    """Get database connection."""
    return await asyncpg.connect(
        host="localhost",
        database="anime_production",
        user="patrick",
        password="tower_echo_brain_secret_key_2025"
    )

@router.get("/api/anime/status")
async def get_comprehensive_status() -> Dict[str, Any]:
    """
    Get comprehensive system status including:
    - Production statistics
    - QC history
    - SSOT audit trail
    - Active jobs
    - System health
    """
    conn = await get_db_connection()

    try:
        # Get production statistics
        total_projects = await conn.fetchval("SELECT COUNT(*) FROM projects")
        total_characters = await conn.fetchval("SELECT COUNT(*) FROM characters")
        total_generations = await conn.fetchval("SELECT COUNT(*) FROM generation_history")
        total_qc_checks = await conn.fetchval("SELECT COUNT(*) FROM quality_verifications")

        # Get latest QC results
        latest_qc = await conn.fetch("""
            SELECT test_name, similarity_score, created_at
            FROM quality_verifications
            ORDER BY created_at DESC
            LIMIT 5
        """)

        # Get SSOT audit statistics
        ssot_stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_requests,
                COUNT(DISTINCT endpoint) as unique_endpoints,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(processing_time) as avg_processing_ms
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)

        # Get recent SSOT activity
        recent_ssot = await conn.fetch("""
            SELECT endpoint, method, status, timestamp
            FROM ssot_tracking
            ORDER BY timestamp DESC
            LIMIT 10
        """)

        # Get active generation jobs
        active_jobs = await conn.fetch("""
            SELECT id::text, status, created_at
            FROM generation_jobs
            WHERE status IN ('pending', 'processing', 'running')
            ORDER BY created_at DESC
            LIMIT 5
        """)

        # Get model availability
        models = await conn.fetch("""
            SELECT model_name as name, model_type as type, status
            FROM ai_models
            WHERE status = 'active'
        """)

        # Check ComfyUI status
        import aiohttp
        comfyui_status = "unknown"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8188/system_stats", timeout=2) as resp:
                    if resp.status == 200:
                        comfyui_status = "online"
                    else:
                        comfyui_status = "error"
        except:
            comfyui_status = "offline"

        # Build response
        response = {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "statistics": {
                "total_projects": total_projects,
                "total_characters": total_characters,
                "total_generations": total_generations,
                "total_qc_checks": total_qc_checks
            },
            "quality_control": {
                "recent_checks": [
                    {
                        "test": rec["test_name"],
                        "score": float(rec["similarity_score"]) if rec["similarity_score"] else 0,
                        "timestamp": rec["created_at"].isoformat() if rec["created_at"] else None
                    }
                    for rec in latest_qc
                ],
                "average_score": await conn.fetchval("""
                    SELECT AVG(similarity_score)
                    FROM quality_verifications
                    WHERE similarity_score IS NOT NULL
                """) or 0
            },
            "ssot_audit": {
                "last_24h": {
                    "total_requests": ssot_stats["total_requests"] if ssot_stats else 0,
                    "unique_endpoints": ssot_stats["unique_endpoints"] if ssot_stats else 0,
                    "unique_users": ssot_stats["unique_users"] if ssot_stats else 0,
                    "avg_processing_ms": float(ssot_stats["avg_processing_ms"]) if ssot_stats and ssot_stats["avg_processing_ms"] else 0
                },
                "recent_activity": [
                    {
                        "endpoint": rec["endpoint"],
                        "method": rec["method"],
                        "status": rec["status"],
                        "timestamp": rec["timestamp"].isoformat() if rec["timestamp"] else None
                    }
                    for rec in recent_ssot
                ]
            },
            "active_jobs": [
                {
                    "id": rec["id"],
                    "status": rec["status"],
                    "created_at": rec["created_at"].isoformat() if rec["created_at"] else None
                }
                for rec in active_jobs
            ],
            "models": {
                "available": [
                    {
                        "name": rec["name"],
                        "type": rec["type"]
                    }
                    for rec in models
                ],
                "count": len(models)
            },
            "services": {
                "api": "online",
                "database": "online",
                "comfyui": comfyui_status,
                "frontend": "online"
            }
        }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")
    finally:
        await conn.close()

@router.get("/api/anime/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "tower-anime-production"
    }