"""Authentication — multi-user with JWT, local profiles, and share links.

Auth paths:
  A) JWT cookie/header present → verify + look up studio_users
  B) Local network + studio_profile cookie → profile picker flow
  C) Local network + no cookies → fallback to admin (backward compat)
  D) Share link token → project-scoped reviewer access
"""

import ipaddress
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .ratings import allowed_ratings

logger = logging.getLogger(__name__)

AUTH_SERVICE_URL = "http://localhost:8088"

TRUSTED_NETWORKS = [
    ipaddress.ip_network("192.168.50.0/24"),
    ipaddress.ip_network("127.0.0.0/8"),
]

# Paths that never require auth
PUBLIC_PATHS = frozenset([
    "/api/system/health",
    "/api/system/gpu/status",
    "/api/studio/auth/profiles",
    "/api/studio/auth/local/select",
    "/api/studio/auth/local/verify-pin",
])


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
            "auth_user_id": payload.get("sub") or payload.get("user_id"),
            "role": payload.get("role", "viewer"),
            "expires": payload.get("exp"),
            "avatar_url": payload.get("picture"),
            "display_name": payload.get("name") or payload.get("user", "anonymous"),
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


async def _get_or_create_studio_user(jwt_data: dict) -> dict | None:
    """Look up or auto-provision a studio_user from JWT claims."""
    from .db import connect_direct
    auth_user_id = jwt_data.get("auth_user_id")
    if not auth_user_id:
        return None

    try:
        conn = await connect_direct()
        row = await conn.fetchrow(
            "SELECT * FROM studio_users WHERE auth_user_id = $1", str(auth_user_id)
        )
        if row:
            # Update last_login
            await conn.execute(
                "UPDATE studio_users SET last_login = NOW() WHERE id = $1", row["id"]
            )
            await conn.close()
            return dict(row)

        # Auto-provision new user (default: viewer, PG, easy, not onboarded)
        row = await conn.fetchrow("""
            INSERT INTO studio_users (auth_user_id, display_name, email, avatar_url,
                                       role, max_rating, ui_mode, onboarded, last_login)
            VALUES ($1, $2, $3, $4, 'viewer', 'PG', 'easy', FALSE, NOW())
            RETURNING *
        """, str(auth_user_id),
            jwt_data.get("display_name", jwt_data.get("email", "User")),
            jwt_data.get("email"),
            jwt_data.get("avatar_url"),
        )
        await conn.close()
        logger.info(f"Auto-provisioned studio_user for {jwt_data.get('email')}")
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"studio_user lookup failed: {e}")
        return None


async def _get_studio_user_by_id(user_id: int) -> dict | None:
    """Look up a studio_user by ID (for profile cookie flow)."""
    from .db import connect_direct
    try:
        conn = await connect_direct()
        row = await conn.fetchrow("SELECT * FROM studio_users WHERE id = $1", user_id)
        if row:
            await conn.execute(
                "UPDATE studio_users SET last_login = NOW() WHERE id = $1", user_id
            )
        await conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"studio_user lookup by id failed: {e}")
        return None


async def _get_admin_user() -> dict:
    """Get the Patrick admin profile as fallback."""
    from .db import connect_direct
    try:
        conn = await connect_direct()
        row = await conn.fetchrow(
            "SELECT * FROM studio_users WHERE role = 'admin' ORDER BY id LIMIT 1"
        )
        await conn.close()
        if row:
            return dict(row)
    except Exception as e:
        logger.warning(f"Admin user lookup failed: {e}")

    # Hard fallback if DB isn't ready yet
    return {
        "id": 1, "display_name": "Patrick", "role": "admin",
        "max_rating": "XXX", "ui_mode": "advanced", "onboarded": True,
    }


async def _validate_share_token(token: str) -> dict | None:
    """Validate a share link token, return share link data if valid."""
    from .db import connect_direct
    try:
        conn = await connect_direct()
        row = await conn.fetchrow("""
            SELECT sl.*, p.name as project_name, p.content_rating
            FROM share_links sl
            JOIN projects p ON sl.project_id = p.id
            WHERE sl.token = $1 AND sl.is_active = TRUE AND sl.expires_at > NOW()
        """, token)
        await conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"Share token validation failed: {e}")
        return None


def _build_user_state(studio_user: dict, share_link: dict | None = None) -> dict:
    """Build the request.state.user dict from a studio_user record."""
    result = {
        "studio_user_id": studio_user.get("id"),
        "user": studio_user.get("display_name", "User"),
        "email": studio_user.get("email"),
        "avatar_url": studio_user.get("avatar_url"),
        "role": studio_user.get("role", "viewer"),
        "max_rating": studio_user.get("max_rating", "PG"),
        "ui_mode": studio_user.get("ui_mode", "easy"),
        "onboarded": studio_user.get("onboarded", False),
        "local": studio_user.get("auth_user_id") is None,
    }
    if share_link:
        result["share_link"] = share_link
        result["share_project_id"] = share_link["project_id"]
        # Clamp rating to share link's max
        from .ratings import RATING_ORDER
        link_ceiling = RATING_ORDER.get(share_link.get("max_rating", "PG-13"), 2)
        user_ceiling = RATING_ORDER.get(result["max_rating"], 1)
        if link_ceiling < user_ceiling:
            result["max_rating"] = share_link["max_rating"]
    return result


async def get_user_projects(request: Request) -> list[int]:
    """Get list of project IDs the current user can access.

    Filters by:
    1. Content rating (user's max_rating)
    2. Explicit user_project_access rows (if any exist, intersect)
    3. Share link (single project only)

    Use as FastAPI dependency: allowed = Depends(get_user_projects)
    """
    user = getattr(request.state, "user", None)
    if not user:
        return []

    # Share link users: single project only
    if user.get("share_project_id"):
        return [user["share_project_id"]]

    from .db import connect_direct
    max_rating = user.get("max_rating", "PG")
    ratings = allowed_ratings(max_rating)
    studio_user_id = user.get("studio_user_id")

    try:
        conn = await connect_direct()

        # Get all projects within rating ceiling
        rows = await conn.fetch(
            "SELECT id FROM projects WHERE content_rating = ANY($1)",
            ratings,
        )
        rating_project_ids = {r["id"] for r in rows}

        # Check for explicit access rows
        if studio_user_id:
            access_rows = await conn.fetch(
                "SELECT project_id FROM user_project_access WHERE user_id = $1",
                studio_user_id,
            )
            if access_rows:
                explicit_ids = {r["project_id"] for r in access_rows}
                rating_project_ids &= explicit_ids

        await conn.close()
        return sorted(rating_project_ids)
    except Exception as e:
        logger.warning(f"get_user_projects failed: {e}")
        return []


async def require_auth(request: Request) -> dict:
    """Require auth — returns user info. Raises 401 if not authenticated."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def require_admin(request: Request) -> dict:
    """Require admin role."""
    user = await require_auth(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def optional_auth(request: Request) -> Optional[dict]:
    """Optional auth — returns user info if present, None otherwise."""
    return getattr(request.state, "user", None)


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


def _get_client_ip(request: Request) -> str:
    """Extract real client IP from proxy headers or connection."""
    return (
        request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "0.0.0.0")
    )


def _extract_token(request: Request) -> str | None:
    """Extract JWT from cookie or Authorization header."""
    # Cookie first (browser sessions)
    token = request.cookies.get("tower_token")
    if token:
        return token
    # Bearer header (API clients)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware: multi-user auth with JWT, profiles, and share links."""

    async def dispatch(self, request: Request, call_next):
        client_ip = _get_client_ip(request)
        path = request.url.path

        # Public paths — always open
        if path in PUBLIC_PATHS:
            request.state.user = {"user": "anonymous", "role": "viewer", "max_rating": "G"}
            return await call_next(request)

        # Static file serving — no auth needed
        if not path.startswith("/api/"):
            return await call_next(request)

        # ── Path A: JWT token present (any network) ──
        token = _extract_token(request)
        if token:
            user_data = await _verify_with_auth_service(token)
            if not user_data:
                user_data = _verify_jwt_locally(token)

            if user_data and user_data.get("valid"):
                studio_user = await _get_or_create_studio_user(user_data)
                if studio_user:
                    # Check for share token alongside JWT
                    share_token = (
                        request.query_params.get("share_token")
                        or request.headers.get("x-share-token")
                    )
                    share_link = None
                    if share_token:
                        share_link = await _validate_share_token(share_token)
                    request.state.user = _build_user_state(studio_user, share_link)
                    return await call_next(request)
                else:
                    # JWT valid but no studio_user — use JWT data directly
                    request.state.user = {
                        "user": user_data.get("user", "anonymous"),
                        "email": user_data.get("email"),
                        "role": user_data.get("role", "viewer"),
                        "max_rating": "PG",
                        "ui_mode": "easy",
                        "onboarded": False,
                        "local": False,
                    }
                    return await call_next(request)

        # ── Path D: Share link token (no JWT) ──
        share_token = (
            request.query_params.get("share_token")
            or request.headers.get("x-share-token")
        )
        if share_token and not is_trusted_network(client_ip):
            # External share link access requires Google login (JWT)
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "Google login required to view shared projects", "login_required": True},
            )

        # ── Local network paths ──
        if is_trusted_network(client_ip):
            # Path B: Profile cookie present
            profile_cookie = request.cookies.get("studio_profile")
            if profile_cookie:
                try:
                    profile_id = int(profile_cookie)
                    studio_user = await _get_studio_user_by_id(profile_id)
                    if studio_user:
                        # Check share token on local network too
                        if share_token:
                            share_link = await _validate_share_token(share_token)
                            request.state.user = _build_user_state(studio_user, share_link)
                        else:
                            request.state.user = _build_user_state(studio_user)
                        return await call_next(request)
                except (ValueError, TypeError):
                    pass

            # Path C: No JWT, no profile cookie → admin fallback
            admin_user = await _get_admin_user()
            request.state.user = _build_user_state(admin_user)
            return await call_next(request)

        # ── External, no valid auth ──
        if path.startswith("/api/"):
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "Authorization required for external access"},
            )

        return await call_next(request)
