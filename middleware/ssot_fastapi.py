#!/usr/bin/env python3
"""
FastAPI-compatible SSOT Middleware for Tower Anime Production
Phase 2: Proper implementation with Starlette middleware
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import uuid
import time
import json
import os
from datetime import datetime
import asyncpg
import logging

logger = logging.getLogger(__name__)


class SSOTFastAPIMiddleware(BaseHTTPMiddleware):
    """SSOT tracking middleware for FastAPI"""

    def __init__(self, app):
        super().__init__(app)
        self.db_url = f"postgresql://patrick:{os.getenv('DATABASE_PASSWORD', 'tower_echo_brain_secret_key_2025')}@localhost/anime_production"

    async def dispatch(self, request: Request, call_next):
        """Process each request and track in SSOT"""

        # Skip tracking for certain paths
        skip_paths = ['/health', '/docs', '/openapi.json', '/favicon.ico', '/redoc']
        if request.url.path in skip_paths:
            return await call_next(request)

        # Generate tracking ID and start timer
        request_id = f"req_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # Store in request state for access in endpoints
        request.state.ssot_request_id = request_id
        request.state.start_time = start_time

        # Prepare tracking data
        tracking_data = {
            'request_id': request_id,
            'endpoint': str(request.url.path),
            'method': request.method,
            'client_ip': request.client.host if request.client else None,
            'user_agent': request.headers.get('user-agent', ''),
            'timestamp': datetime.utcnow(),
            'status': 'initiated'
        }

        # Try to capture request body for POST/PUT/PATCH
        body_data = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                # Store the body to reuse it
                body = await request.body()
                if body:
                    try:
                        body_data = json.loads(body)
                        tracking_data['parameters'] = body_data
                    except:
                        tracking_data['parameters'] = {'raw': body.decode('utf-8')[:500]}

                    # Recreate the request body stream
                    async def receive():
                        return {"type": "http.request", "body": body}
                    request._receive = receive
            except Exception as e:
                logger.debug(f"Could not capture request body: {e}")

        # Log initial request to SSOT
        ssot_id = await self.log_to_ssot(tracking_data)

        try:
            # Process the actual request
            response = await call_next(request)

            # Calculate processing time
            processing_time = int((time.time() - start_time) * 1000)  # milliseconds

            # Add tracking headers
            response.headers['X-SSOT-Request-ID'] = request_id
            response.headers['X-Processing-Time'] = str(processing_time)
            if ssot_id:
                response.headers['X-SSOT-Tracking-ID'] = str(ssot_id)

            # Update SSOT with completion
            await self.update_ssot_completion(
                request_id,
                status='completed',
                http_status=response.status_code,
                processing_time=processing_time
            )

            return response

        except Exception as e:
            # Update SSOT with error
            processing_time = int((time.time() - start_time) * 1000)
            await self.update_ssot_completion(
                request_id,
                status='failed',
                error=str(e),
                processing_time=processing_time
            )

            # Re-raise the exception
            raise

    async def log_to_ssot(self, data):
        """Log request to SSOT database"""
        try:
            conn = await asyncpg.connect(self.db_url)

            result = await conn.fetchval('''
                INSERT INTO ssot_tracking (
                    request_id, endpoint, method, user_id,
                    parameters, user_agent, ip_address,
                    status, timestamp, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            ''',
                data['request_id'],
                data['endpoint'],
                data['method'],
                data.get('user_id', 'system'),
                json.dumps(data.get('parameters', {})) if data.get('parameters') else '{}',
                data.get('user_agent', ''),
                data.get('client_ip'),
                data['status'],
                data['timestamp'],
                json.dumps({'source': 'fastapi_middleware', 'version': '2.0'})
            )

            await conn.close()
            logger.info(f"SSOT tracked request {data['request_id']} -> ID {result}")
            return result

        except Exception as e:
            logger.error(f"SSOT logging failed: {e}")
            self.fallback_log(data)
            return None

    async def update_ssot_completion(self, request_id, status, http_status=None,
                                    processing_time=None, error=None):
        """Update SSOT record with completion data"""
        try:
            conn = await asyncpg.connect(self.db_url)

            await conn.execute('''
                UPDATE ssot_tracking
                SET status = $1,
                    completed_at = $2,
                    processing_time = $3,
                    http_status = $4,
                    response_data = $5
                WHERE request_id = $6
            ''',
                status,
                datetime.utcnow(),
                processing_time,
                http_status,
                json.dumps({'error': error}) if error else None,
                request_id
            )

            await conn.close()
            logger.debug(f"SSOT updated {request_id}: {status}")

        except Exception as e:
            logger.error(f"SSOT update failed: {e}")

    def fallback_log(self, data):
        """Fallback file logging if DB fails"""
        import os
        log_dir = "/opt/tower-anime-production/logs"
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, "ssot_fallback.log")
        with open(log_file, 'a') as f:
            f.write(f"{datetime.utcnow().isoformat()} | {json.dumps(data, default=str)}\n")