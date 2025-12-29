#!/usr/bin/env python3
"""
SSOT Tracking Middleware for Tower Anime Production
Intercepts all generation requests and ensures SSOT tracking
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import asyncpg
import logging
from functools import wraps

logger = logging.getLogger(__name__)

class SSOTTracker:
    """Middleware to track all generation requests in SSOT database"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10
            )
            logger.info("SSOT Tracker initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SSOT Tracker: {e}")

    async def __call__(self, request: Request, call_next: Callable):
        """Main middleware handler"""
        start_time = time.time()

        # Generate tracking ID
        request_id = f"req_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        ssot_tracking_id = None

        # Check if this is a generation endpoint
        if self.should_track(request.url.path):
            try:
                # Extract request data
                tracking_data = {
                    'request_id': request_id,
                    'endpoint': str(request.url.path),
                    'method': request.method,
                    'user_id': request.headers.get('X-User-ID', 'system'),
                    'user_agent': request.headers.get('User-Agent', ''),
                    'ip_address': request.client.host if request.client else None,
                    'timestamp': datetime.utcnow().isoformat(),
                    'status': 'initiated'
                }

                # Get request body if POST/PUT
                body = None
                if request.method in ['POST', 'PUT']:
                    body_bytes = await request.body()
                    if body_bytes:
                        try:
                            body = json.loads(body_bytes)
                            tracking_data['parameters'] = body
                        except:
                            tracking_data['parameters'] = {'raw': body_bytes.decode('utf-8')[:1000]}

                        # Recreate request with body
                        async def receive():
                            return {"type": "http.request", "body": body_bytes}
                        request._receive = receive

                # Log to SSOT database
                ssot_tracking_id = await self.log_to_ssot(tracking_data)

                # Add tracking ID to request state
                request.state.ssot_tracking_id = ssot_tracking_id
                request.state.request_id = request_id

            except Exception as e:
                logger.error(f"SSOT tracking initiation failed: {e}")

        # Process the request
        response = await call_next(request)

        # Update SSOT with completion status
        if ssot_tracking_id and self.should_track(request.url.path):
            try:
                processing_time = int((time.time() - start_time) * 1000)  # milliseconds

                await self.update_ssot_status(
                    request_id=request_id,
                    status='completed',
                    processing_time=processing_time,
                    http_status=response.status_code
                )

                # Add tracking headers to response
                response.headers["X-SSOT-Tracking-ID"] = str(ssot_tracking_id)
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Processing-Time"] = str(processing_time)

            except Exception as e:
                logger.error(f"SSOT tracking completion failed: {e}")

        return response

    def should_track(self, path: str) -> bool:
        """Determine if this endpoint should be tracked"""
        tracking_patterns = [
            '/generate',
            '/api/anime/generate',
            '/api/projects',
            '/api/episodes',
            '/api/scenes',
            '/workflow',
            '/comfyui',
            '/echo',
            '/ollama'
        ]

        return any(pattern in path for pattern in tracking_patterns)

    async def log_to_ssot(self, tracking_data: Dict[str, Any]) -> Optional[int]:
        """Log request to SSOT database"""
        if not self.pool:
            return None

        try:
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
                    tracking_data['user_id'],
                    json.dumps(tracking_data.get('parameters', {})),
                    tracking_data['user_agent'],
                    tracking_data.get('ip_address'),
                    tracking_data['status'],
                    tracking_data['timestamp'],
                    json.dumps({})
                )

                logger.info(f"SSOT tracked: {tracking_data['request_id']} -> ID {result}")
                return result

        except Exception as e:
            logger.error(f"Failed to log to SSOT: {e}")
            # Fallback to file logging
            self.fallback_logging(tracking_data)
            return None

    async def update_ssot_status(self, request_id: str, status: str,
                                 processing_time: int, http_status: int):
        """Update SSOT record with completion status"""
        if not self.pool:
            return

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE ssot_tracking
                    SET status = $1,
                        completed_at = $2,
                        processing_time = $3,
                        http_status = $4
                    WHERE request_id = $5
                """,
                    status,
                    datetime.utcnow().isoformat(),
                    processing_time,
                    http_status,
                    request_id
                )

        except Exception as e:
            logger.error(f"Failed to update SSOT status: {e}")

    def fallback_logging(self, tracking_data: Dict[str, Any]):
        """Fallback file-based logging if database fails"""
        import os
        log_dir = "/opt/tower-anime-production/logs"
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, "ssot-fallback.log")
        with open(log_file, 'a') as f:
            f.write(f"{datetime.utcnow().isoformat()} | {json.dumps(tracking_data)}\n")

    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()


def track_generation_decision(func):
    """Decorator to track generation decisions for Echo/Ollama integration"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        request = kwargs.get('request') or (args[0] if args else None)

        # Create decision record
        decision_data = {
            'function': func.__name__,
            'timestamp': datetime.utcnow().isoformat(),
            'request_id': getattr(request.state, 'request_id', None) if request else None,
            'ssot_tracking_id': getattr(request.state, 'ssot_tracking_id', None) if request else None
        }

        try:
            # Execute the function
            result = await func(*args, **kwargs)

            # Record decision outcome
            decision_data['status'] = 'success'
            decision_data['processing_time'] = time.time() - start_time

            # If result contains Echo/Ollama decisions, track them
            if isinstance(result, dict):
                if 'echo_response' in result:
                    await track_echo_decision(decision_data['request_id'], result['echo_response'])
                if 'ollama_response' in result:
                    await track_ollama_decision(decision_data['request_id'], result['ollama_response'])

            return result

        except Exception as e:
            decision_data['status'] = 'failed'
            decision_data['error'] = str(e)
            logger.error(f"Generation decision failed: {e}")
            raise
        finally:
            # Log the decision
            await log_generation_decision(decision_data)

    return wrapper


async def track_echo_decision(request_id: str, echo_response: Dict[str, Any]):
    """Track Echo Brain decisions in generation_decisions table"""
    try:
        database_url = "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost/anime_production"
        conn = await asyncpg.connect(database_url)

        await conn.execute("""
            INSERT INTO generation_decisions (
                generation_id, decision_type, decision_data,
                confidence_score, timestamp
            ) VALUES (
                (SELECT id FROM project_generations WHERE job_id = $1 LIMIT 1),
                'echo_consultation',
                $2,
                $3,
                $4
            )
        """,
            request_id,
            json.dumps(echo_response),
            echo_response.get('confidence', 0.0),
            datetime.utcnow()
        )

        await conn.close()
        logger.info(f"Echo decision tracked for {request_id}")

    except Exception as e:
        logger.error(f"Failed to track Echo decision: {e}")


async def track_ollama_decision(request_id: str, ollama_response: Dict[str, Any]):
    """Track Ollama decisions in generation_decisions table"""
    try:
        database_url = "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost/anime_production"
        conn = await asyncpg.connect(database_url)

        await conn.execute("""
            INSERT INTO generation_decisions (
                generation_id, decision_type, decision_data,
                confidence_score, timestamp
            ) VALUES (
                (SELECT id FROM project_generations WHERE job_id = $1 LIMIT 1),
                'ollama_enhancement',
                $2,
                $3,
                $4
            )
        """,
            request_id,
            json.dumps(ollama_response),
            ollama_response.get('quality_score', 0.0),
            datetime.utcnow()
        )

        await conn.close()
        logger.info(f"Ollama decision tracked for {request_id}")

    except Exception as e:
        logger.error(f"Failed to track Ollama decision: {e}")


async def log_generation_decision(decision_data: Dict[str, Any]):
    """Log generation decision to database"""
    try:
        database_url = "postgresql://patrick:tower_echo_brain_secret_key_2025@localhost/anime_production"
        conn = await asyncpg.connect(database_url)

        await conn.execute("""
            INSERT INTO generation_workflow_decisions (
                request_id, function_name, status,
                processing_time, timestamp, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6)
        """,
            decision_data.get('request_id'),
            decision_data.get('function'),
            decision_data.get('status'),
            decision_data.get('processing_time'),
            decision_data.get('timestamp'),
            json.dumps(decision_data)
        )

        await conn.close()

    except Exception as e:
        logger.error(f"Failed to log generation decision: {e}")