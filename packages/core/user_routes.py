"""User-facing auth endpoints — profile, preferences, local profile picker."""

import logging
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Optional

from .db import connect_direct

logger = logging.getLogger(__name__)
router = APIRouter()


class PreferencesUpdate(BaseModel):
    ui_mode: Optional[str] = None
    onboarded: Optional[bool] = None
    display_name: Optional[str] = None
    preferences: Optional[dict] = None


class PinVerify(BaseModel):
    user_id: int
    pin: str


# ── Current user ────────────────────────────────────────────────

@router.get("/studio/auth/me")
async def get_me(request: Request):
    """Get current user profile."""
    user = getattr(request.state, "user", None)
    if not user or not user.get("studio_user_id"):
        return {
            "authenticated": False,
            "user": user or {"role": "viewer", "max_rating": "PG"},
        }

    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT id, display_name, email, avatar_url, role, max_rating, "
            "ui_mode, onboarded, preferences, created_at, last_login "
            "FROM studio_users WHERE id = $1",
            user["studio_user_id"],
        )
        if not row:
            return {"authenticated": False, "user": user}
        return {
            "authenticated": True,
            "user": {
                "id": row["id"],
                "display_name": row["display_name"],
                "email": row["email"],
                "avatar_url": row["avatar_url"],
                "role": row["role"],
                "max_rating": row["max_rating"],
                "ui_mode": row["ui_mode"],
                "onboarded": row["onboarded"],
                "preferences": row["preferences"] or {},
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "last_login": row["last_login"].isoformat() if row["last_login"] else None,
            },
        }
    finally:
        await conn.close()


@router.patch("/studio/auth/me/preferences")
async def update_preferences(request: Request, body: PreferencesUpdate):
    """Update current user's preferences (ui_mode, onboarded, etc.)."""
    user = getattr(request.state, "user", None)
    if not user or not user.get("studio_user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = await connect_direct()
    try:
        updates, params, idx = [], [], 1
        for field in ("ui_mode", "onboarded", "display_name"):
            val = getattr(body, field)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1
        if body.preferences is not None:
            updates.append(f"preferences = ${idx}::jsonb")
            import json
            params.append(json.dumps(body.preferences))
            idx += 1
        if not updates:
            return {"message": "No fields to update"}
        params.append(user["studio_user_id"])
        await conn.execute(
            f"UPDATE studio_users SET {', '.join(updates)} WHERE id = ${idx}",
            *params,
        )
        return {"message": "Preferences updated"}
    finally:
        await conn.close()


# ── Local profile picker ────────────────────────────────────────

@router.get("/studio/auth/profiles")
async def list_profiles():
    """List local profiles for the profile picker (no auth required)."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT id, display_name, avatar_url, role, max_rating, ui_mode,
                   (pin_hash IS NOT NULL) as has_pin
            FROM studio_users
            WHERE auth_user_id IS NULL
            ORDER BY id
        """)
        return {
            "profiles": [
                {
                    "id": r["id"],
                    "display_name": r["display_name"],
                    "avatar_url": r["avatar_url"],
                    "role": r["role"],
                    "max_rating": r["max_rating"],
                    "ui_mode": r["ui_mode"],
                    "has_pin": r["has_pin"],
                }
                for r in rows
            ]
        }
    finally:
        await conn.close()


@router.post("/studio/auth/local/select")
async def select_profile(request: Request, response: Response, user_id: int = 0):
    """Select a local profile (sets studio_profile cookie)."""
    if user_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT id, pin_hash, display_name FROM studio_users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found")

        # If PIN is set, don't select directly — require PIN verification
        if row["pin_hash"]:
            return {"requires_pin": True, "user_id": row["id"], "display_name": row["display_name"]}

        # No PIN — set cookie and return
        await conn.execute("UPDATE studio_users SET last_login = NOW() WHERE id = $1", user_id)
        response.set_cookie(
            "studio_profile", str(user_id),
            max_age=86400 * 30,  # 30 days
            httponly=True,
            samesite="lax",
        )
        return {"selected": True, "display_name": row["display_name"]}
    finally:
        await conn.close()


@router.post("/studio/auth/local/verify-pin")
async def verify_pin(response: Response, body: PinVerify):
    """Verify PIN for a protected local profile."""
    conn = await connect_direct()
    try:
        row = await conn.fetchrow(
            "SELECT id, pin_hash, display_name FROM studio_users WHERE id = $1",
            body.user_id,
        )
        if not row or not row["pin_hash"]:
            raise HTTPException(status_code=400, detail="Profile has no PIN")

        import bcrypt
        if not bcrypt.checkpw(body.pin.encode(), row["pin_hash"].encode()):
            raise HTTPException(status_code=401, detail="Incorrect PIN")

        await conn.execute("UPDATE studio_users SET last_login = NOW() WHERE id = $1", body.user_id)
        response.set_cookie(
            "studio_profile", str(body.user_id),
            max_age=86400 * 30,
            httponly=True,
            samesite="lax",
        )
        return {"verified": True, "display_name": row["display_name"]}
    finally:
        await conn.close()


@router.post("/studio/auth/logout")
async def logout(response: Response):
    """Clear auth cookies."""
    response.delete_cookie("studio_profile")
    response.delete_cookie("tower_token")
    return {"message": "Logged out"}
