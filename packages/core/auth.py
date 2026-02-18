"""Authentication — JWT + local network bypass for external tester access."""

import ipaddress
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

AUTH_SERVICE_URL = "http://localhost:8088"

# Networks that bypass auth entirely
TRUSTED_NETWORKS = [
    ipaddress.ip_network("192.168.50.0/24"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def is_trusted_network(client_ip: str) -> bool:
    """Check if client IP is in a trusted local network."""
    try:
        addr = ipaddress.ip_address(client_ip)
        return any(addr in net for net in TRUSTED_NETWORKS)
    except ValueError:
        return False


@lru_cache()
def _get_jwt_secret() -> str:
    """Get JWT secret from Vault or environment."""
    try:
        import hvac
        vault = hvac.Client(url="http://127.0.0.1:8200")
        vault.token = os.getenv("VAULT_ROOT_TOKEN")
        secret = vault.secrets.kv.v2.read_secret_version(path="auth/jwt")
        return secret["data"]["data"]["secret_key"]
    except Exception:
        return os.getenv("JWT_SECRET_KEY", "tower_jwt_secret_2025")


def _verify_jwt_locally(token: str) -> dict | None:
    """Verify JWT token locally."""
    try:
        import jwt
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
        if payload.get("exp", 0) < time.time():
            return None
        return {
            "valid": True,
            "user": payload.get("user", "anonymous"),
            "email": payload.get("email"),
            "role": payload.get("role", "viewer"),
            "expires": payload.get("exp"),
        }
    except Exception:
        return None


async def _verify_with_auth_service(token: str) -> dict | None:
    """Verify token with the Tower auth service."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{AUTH_SERVICE_URL}/api/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        import json
        data = json.loads(resp.read())
        if data.get("valid"):
            return data
    except Exception as e:
        logger.debug(f"Auth service verification failed: {e}")
    return None


async def require_auth(request: Request) -> dict:
    """Require auth — but bypass for local network."""
    client_ip = request.client.host if request.client else "0.0.0.0"

    if is_trusted_network(client_ip):
        return {"user": "local", "role": "admin", "local": True}

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")

    token = auth_header[7:]  # Strip "Bearer "

    # Try auth service first, then local JWT
    user_data = await _verify_with_auth_service(token)
    if not user_data:
        user_data = _verify_jwt_locally(token)

    if not user_data or not user_data.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_data


async def optional_auth(request: Request) -> Optional[dict]:
    """Optional auth — returns user info if present, None otherwise."""
    try:
        return await require_auth(request)
    except HTTPException:
        return None


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(seconds=window_seconds)
        self.requests[key] = [t for t in self.requests[key] if t > cutoff]
        if len(self.requests[key]) >= max_requests:
            return False
        self.requests[key].append(now)
        return True


rate_limiter = RateLimiter()


class AuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware: local network bypass, JWT for external requests."""

    async def dispatch(self, request: Request, call_next):
        # Use X-Real-IP (set by nginx) for actual client IP behind reverse proxy
        client_ip = (
            request.headers.get("x-real-ip")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "0.0.0.0")
        )

        # Health and GPU status endpoints always open
        if request.url.path in ("/api/lora/health", "/api/lora/gpu/status"):
            return await call_next(request)

        # Local network — bypass auth
        if is_trusted_network(client_ip):
            request.state.user = {"user": "local", "role": "admin", "local": True}
            return await call_next(request)

        # External — require auth for API routes
        if request.url.path.startswith("/api/"):
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authorization required for external access"},
                )

            token = auth_header[7:]
            user_data = await _verify_with_auth_service(token)
            if not user_data:
                user_data = _verify_jwt_locally(token)

            if not user_data or not user_data.get("valid"):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                )

            request.state.user = user_data

            # Rate limit external users
            user_key = user_data.get("email", user_data.get("user", "anon"))
            if not rate_limiter.is_allowed(user_key, max_requests=60, window_seconds=60):
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded (60 req/min)"},
                )

        return await call_next(request)
