#!/usr/bin/env python3
"""
SSOT Service for centralized tracking and decision logging
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncpg
import redis
import os

logger = logging.getLogger(__name__)


class SSOTService:
    """Service for managing SSOT tracking and decision logging"""

    def __init__(self):
        self.database_url = f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', 'tower_echo_brain_secret_key_2025')}@localhost/anime_production"
        self.pool: Optional[asyncpg.Pool] = None
        self.redis_client = None
        self.initialize_redis()

    def initialize_redis(self):
        """Initialize Redis connection for caching"""
        try:
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True,
                db=1  # Use DB 1 for SSOT
            )
            self.redis_client.ping()
            logger.info("Redis initialized for SSOT caching")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Proceeding without cache.")
            self.redis_client = None

    async def initialize_pool(self):
        """Initialize database connection pool"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=20
            )

    async def log_request(self, tracking_data: Dict[str, Any]) -> int:
        """Log a request to SSOT tracking table"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                INSERT INTO ssot_tracking (
                    request_id, endpoint, method, user_id,
                    parameters, user_agent, ip_address,
                    status, timestamp, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """,
                tracking_data['request_id'],
                tracking_data['endpoint'],
                tracking_data['method'],
                tracking_data.get('user_id', 'system'),
                json.dumps(tracking_data.get('parameters', {})),
                tracking_data.get('user_agent', ''),
                tracking_data.get('ip_address'),
                tracking_data.get('status', 'initiated'),
                datetime.utcnow(),
                json.dumps(tracking_data.get('metadata', {}))
            )

        # Cache in Redis for quick access
        if self.redis_client:
            cache_key = f"ssot:request:{tracking_data['request_id']}"
            tracking_data['ssot_id'] = result
            self.redis_client.setex(
                cache_key,
                3600,  # 1 hour TTL
                json.dumps(tracking_data, default=str)
            )

        return result

    async def update_request_status(
        self,
        request_id: str,
        status: str,
        processing_time: Optional[int] = None,
        http_status: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None
    ):
        """Update the status of a tracked request"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE ssot_tracking
                SET status = $1,
                    completed_at = $2,
                    processing_time = $3,
                    http_status = $4,
                    response_data = $5
                WHERE request_id = $6
            """,
                status,
                datetime.utcnow(),
                processing_time,
                http_status,
                json.dumps(response_data) if response_data else None,
                request_id
            )

        # Update cache
        if self.redis_client:
            cache_key = f"ssot:request:{request_id}"
            cached = self.redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                data.update({
                    'status': status,
                    'completed_at': datetime.utcnow().isoformat(),
                    'processing_time': processing_time,
                    'http_status': http_status
                })
                self.redis_client.setex(cache_key, 3600, json.dumps(data, default=str))

    async def log_generation_decision(
        self,
        generation_id: int,
        decision_type: str,
        decision_data: Dict[str, Any],
        confidence_score: float = 0.0
    ) -> int:
        """Log a generation decision to the generation_decisions table"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                INSERT INTO generation_decisions (
                    generation_id, decision_type, decision_data,
                    confidence_score, timestamp
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """,
                generation_id,
                decision_type,
                json.dumps(decision_data),
                confidence_score,
                datetime.utcnow()
            )

        logger.info(f"Logged {decision_type} decision for generation {generation_id}")
        return result

    async def get_tracking_data(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get tracking data for a request"""
        # Check cache first
        if self.redis_client:
            cache_key = f"ssot:request:{request_id}"
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

        # Fallback to database
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT * FROM ssot_tracking
                WHERE request_id = $1
            """, request_id)

            if result:
                return dict(result)

        return None

    async def get_generation_decisions(self, generation_id: int) -> List[Dict[str, Any]]:
        """Get all decisions for a generation"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT * FROM generation_decisions
                WHERE generation_id = $1
                ORDER BY timestamp DESC
            """, generation_id)

            return [dict(row) for row in results]

    async def get_metrics(self, time_range: str = '24 hours') -> Dict[str, Any]:
        """Get SSOT metrics for dashboard"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            # Overall metrics
            metrics = await conn.fetchrow(f"""
                SELECT
                    COUNT(*) as total_requests,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                    COUNT(CASE WHEN status = 'initiated' THEN 1 END) as in_progress,
                    AVG(processing_time) as avg_response_time,
                    MAX(processing_time) as max_response_time,
                    MIN(processing_time) as min_response_time
                FROM ssot_tracking
                WHERE timestamp > NOW() - INTERVAL '{time_range}'
            """)

            # Endpoint breakdown
            endpoints = await conn.fetch(f"""
                SELECT
                    endpoint,
                    method,
                    COUNT(*) as request_count,
                    AVG(processing_time) as avg_time,
                    COUNT(CASE WHEN http_status >= 400 THEN 1 END) as errors
                FROM ssot_tracking
                WHERE timestamp > NOW() - INTERVAL '{time_range}'
                GROUP BY endpoint, method
                ORDER BY request_count DESC
                LIMIT 20
            """)

            # Decision tracking
            decisions = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_decisions,
                    COUNT(CASE WHEN decision_type = 'echo_consultation' THEN 1 END) as echo_decisions,
                    COUNT(CASE WHEN decision_type = 'ollama_enhancement' THEN 1 END) as ollama_decisions,
                    AVG(confidence_score) as avg_confidence
                FROM generation_decisions
                WHERE timestamp > NOW() - INTERVAL '24 hours'
            """)

            return {
                'overall': dict(metrics) if metrics else {},
                'endpoints': [dict(row) for row in endpoints],
                'decisions': dict(decisions) if decisions else {}
            }

    async def get_endpoint_performance(self, endpoint: str) -> Dict[str, Any]:
        """Get performance metrics for specific endpoint"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            # Hourly breakdown
            hourly = await conn.fetch("""
                SELECT
                    date_trunc('hour', timestamp) as hour,
                    COUNT(*) as requests,
                    AVG(processing_time) as avg_time,
                    MAX(processing_time) as max_time
                FROM ssot_tracking
                WHERE endpoint = $1
                    AND timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY hour
                ORDER BY hour DESC
            """, endpoint)

            # Status distribution
            status_dist = await conn.fetch("""
                SELECT
                    http_status,
                    COUNT(*) as count
                FROM ssot_tracking
                WHERE endpoint = $1
                    AND timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY http_status
                ORDER BY count DESC
            """, endpoint)

            return {
                'hourly': [dict(row) for row in hourly],
                'status_distribution': [dict(row) for row in status_dist]
            }

    async def cleanup_old_records(self, days_to_keep: int = 30):
        """Clean up old tracking records"""
        await self.initialize_pool()

        async with self.pool.acquire() as conn:
            deleted = await conn.fetchval("""
                DELETE FROM ssot_tracking
                WHERE timestamp < NOW() - INTERVAL '%s days'
                RETURNING COUNT(*)
            """, days_to_keep)

            logger.info(f"Cleaned up {deleted} old SSOT records")
            return deleted

    async def close(self):
        """Close all connections"""
        if self.pool:
            await self.pool.close()

        if self.redis_client:
            self.redis_client.close()


# Singleton instance
ssot_service = SSOTService()


async def get_ssot_service() -> SSOTService:
    """Get singleton SSOT service instance"""
    return ssot_service