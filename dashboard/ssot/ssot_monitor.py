#!/usr/bin/env python3
"""
SSOT Monitoring Dashboard API Endpoints
Provides real-time tracking and analytics for SSOT integration
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncpg
import json
import os

router = APIRouter(prefix="/ssot", tags=["SSOT Monitoring"])

# Database connection
DATABASE_URL = f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', 'tower_echo_brain_secret_key_2025')}@localhost/anime_production"


@router.get("/metrics")
async def get_ssot_metrics(time_range: str = Query("24 hours", description="Time range for metrics")):
    """Get overall SSOT tracking metrics"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Overall metrics
        metrics = await conn.fetchrow(f"""
            SELECT
                COUNT(*) as total_requests,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN status = 'initiated' THEN 1 END) as in_progress,
                AVG(processing_time) as avg_response_time,
                MAX(processing_time) as max_response_time,
                MIN(processing_time) as min_response_time,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT endpoint) as unique_endpoints
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '{time_range}'
        """)

        # Decision tracking metrics
        decisions = await conn.fetchrow(f"""
            SELECT
                COUNT(*) as total_decisions,
                COUNT(DISTINCT scene_id) as unique_scenes,
                COUNT(DISTINCT episode_id) as unique_episodes,
                AVG(success_score) as avg_success_score
            FROM generation_decisions
            WHERE created_at > NOW() - INTERVAL '{time_range}'
        """)

        # Error rate calculation
        error_rate = await conn.fetchval(f"""
            SELECT
                CASE
                    WHEN COUNT(*) > 0 THEN
                        COUNT(CASE WHEN http_status >= 400 THEN 1 END)::FLOAT / COUNT(*) * 100
                    ELSE 0
                END as error_rate
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '{time_range}'
        """)

        await conn.close()

        return {
            "time_range": time_range,
            "overall_metrics": dict(metrics) if metrics else {},
            "decision_metrics": dict(decisions) if decisions else {},
            "error_rate": round(error_rate, 2) if error_rate else 0,
            "tracking_enabled": True
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {str(e)}")


@router.get("/endpoint-breakdown")
async def get_endpoint_breakdown(
    time_range: str = Query("1 hour", description="Time range for breakdown"),
    limit: int = Query(20, description="Maximum number of endpoints to return")
):
    """Get performance breakdown by endpoint"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        breakdown = await conn.fetch(f"""
            SELECT
                endpoint,
                method,
                COUNT(*) as request_count,
                AVG(processing_time) as avg_time,
                MAX(processing_time) as max_time,
                MIN(processing_time) as min_time,
                COUNT(CASE WHEN http_status >= 400 THEN 1 END) as errors,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '{time_range}'
            GROUP BY endpoint, method
            ORDER BY request_count DESC
            LIMIT {limit}
        """)

        await conn.close()

        return {
            "time_range": time_range,
            "endpoints": [dict(row) for row in breakdown],
            "total_endpoints": len(breakdown)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch endpoint breakdown: {str(e)}")


@router.get("/track/{request_id}")
async def get_tracking_data(request_id: str):
    """Get detailed tracking data for a specific request"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Get tracking record
        tracking = await conn.fetchrow("""
            SELECT * FROM ssot_tracking
            WHERE request_id = $1
        """, request_id)

        if not tracking:
            await conn.close()
            raise HTTPException(status_code=404, detail="Request not found")

        # Get associated workflow decisions
        decisions = await conn.fetch("""
            SELECT * FROM generation_workflow_decisions
            WHERE request_id = $1
            ORDER BY timestamp
        """, request_id)

        await conn.close()

        return {
            "tracking": dict(tracking),
            "workflow_decisions": [dict(row) for row in decisions],
            "decision_count": len(decisions)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tracking data: {str(e)}")


@router.get("/performance/{endpoint:path}")
async def get_endpoint_performance(
    endpoint: str,
    time_range: str = Query("24 hours", description="Time range for analysis")
):
    """Get detailed performance metrics for a specific endpoint"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Hourly breakdown
        hourly = await conn.fetch(f"""
            SELECT
                date_trunc('hour', timestamp) as hour,
                COUNT(*) as requests,
                AVG(processing_time) as avg_time,
                MAX(processing_time) as max_time,
                MIN(processing_time) as min_time,
                COUNT(CASE WHEN http_status >= 400 THEN 1 END) as errors
            FROM ssot_tracking
            WHERE endpoint = $1
                AND timestamp > NOW() - INTERVAL '{time_range}'
            GROUP BY hour
            ORDER BY hour DESC
        """, f"/{endpoint}")

        # Status distribution
        status_dist = await conn.fetch(f"""
            SELECT
                http_status,
                COUNT(*) as count
            FROM ssot_tracking
            WHERE endpoint = $1
                AND timestamp > NOW() - INTERVAL '{time_range}'
                AND http_status IS NOT NULL
            GROUP BY http_status
            ORDER BY count DESC
        """, f"/{endpoint}")

        # Percentiles
        percentiles = await conn.fetchrow(f"""
            SELECT
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY processing_time) as p50,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY processing_time) as p75,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY processing_time) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY processing_time) as p99
            FROM ssot_tracking
            WHERE endpoint = $1
                AND timestamp > NOW() - INTERVAL '{time_range}'
                AND processing_time IS NOT NULL
        """, f"/{endpoint}")

        await conn.close()

        return {
            "endpoint": f"/{endpoint}",
            "time_range": time_range,
            "hourly_metrics": [dict(row) for row in hourly],
            "status_distribution": [dict(row) for row in status_dist],
            "percentiles": dict(percentiles) if percentiles else {}
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch endpoint performance: {str(e)}")


@router.get("/live-feed")
async def get_live_feed(limit: int = Query(50, description="Number of recent requests")):
    """Get live feed of recent requests"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        recent = await conn.fetch("""
            SELECT
                request_id,
                endpoint,
                method,
                user_id,
                status,
                processing_time,
                http_status,
                timestamp,
                completed_at
            FROM ssot_tracking
            ORDER BY timestamp DESC
            LIMIT $1
        """, limit)

        await conn.close()

        return {
            "requests": [dict(row) for row in recent],
            "count": len(recent),
            "latest_timestamp": recent[0]['timestamp'] if recent else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch live feed: {str(e)}")


@router.get("/decision-analytics")
async def get_decision_analytics(time_range: str = Query("7 days", description="Time range")):
    """Get analytics on generation decisions"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Decision type breakdown
        decision_types = await conn.fetch(f"""
            SELECT
                decision_type,
                COUNT(*) as count,
                AVG(success_score) as avg_score
            FROM generation_decisions
            WHERE created_at > NOW() - INTERVAL '{time_range}'
            GROUP BY decision_type
            ORDER BY count DESC
        """)

        # Hourly decision volume
        hourly_volume = await conn.fetch(f"""
            SELECT
                date_trunc('hour', created_at) as hour,
                COUNT(*) as decision_count
            FROM generation_decisions
            WHERE created_at > NOW() - INTERVAL '{time_range}'
            GROUP BY hour
            ORDER BY hour DESC
            LIMIT 24
        """)

        # Success score distribution
        score_dist = await conn.fetch(f"""
            SELECT
                CASE
                    WHEN success_score < 0.3 THEN 'Low (< 0.3)'
                    WHEN success_score < 0.6 THEN 'Medium (0.3-0.6)'
                    WHEN success_score < 0.8 THEN 'High (0.6-0.8)'
                    ELSE 'Very High (> 0.8)'
                END as score_range,
                COUNT(*) as count
            FROM generation_decisions
            WHERE created_at > NOW() - INTERVAL '{time_range}'
                AND success_score IS NOT NULL
            GROUP BY score_range
            ORDER BY
                CASE score_range
                    WHEN 'Low (< 0.3)' THEN 1
                    WHEN 'Medium (0.3-0.6)' THEN 2
                    WHEN 'High (0.6-0.8)' THEN 3
                    ELSE 4
                END
        """)

        await conn.close()

        return {
            "time_range": time_range,
            "decision_types": [dict(row) for row in decision_types],
            "hourly_volume": [dict(row) for row in hourly_volume],
            "score_distribution": [dict(row) for row in score_dist]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch decision analytics: {str(e)}")


@router.get("/health")
async def get_ssot_health():
    """Check SSOT tracking system health"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Check if tables exist
        tables_check = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
                AND table_name IN ('ssot_tracking', 'generation_workflow_decisions', 'generation_decisions')
        """)

        # Get recent activity
        recent_activity = await conn.fetchval("""
            SELECT COUNT(*)
            FROM ssot_tracking
            WHERE timestamp > NOW() - INTERVAL '1 minute'
        """)

        # Check for stuck requests
        stuck_requests = await conn.fetchval("""
            SELECT COUNT(*)
            FROM ssot_tracking
            WHERE status = 'initiated'
                AND timestamp < NOW() - INTERVAL '5 minutes'
        """)

        await conn.close()

        tables_present = [row['table_name'] for row in tables_check]

        return {
            "status": "healthy" if len(tables_present) == 3 else "degraded",
            "tables_present": tables_present,
            "recent_activity": recent_activity,
            "stuck_requests": stuck_requests,
            "database_connected": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_connected": False,
            "timestamp": datetime.utcnow().isoformat()
        }