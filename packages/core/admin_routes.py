"""Admin endpoints — user management, share links, reviewer comments."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .auth import require_admin
from .db import connect_direct

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Models ──────────────────────────────────────────────────────

class CreateUser(BaseModel):
    display_name: str
    role: str = "viewer"
    max_rating: str = "PG"
    ui_mode: str = "easy"
    pin: Optional[str] = None


class UpdateUser(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    max_rating: Optional[str] = None
    ui_mode: Optional[str] = None
    pin: Optional[str] = None  # Set to "" to clear PIN


class CreateShareLink(BaseModel):
    project_id: int
    label: Optional[str] = None
    max_rating: str = "PG-13"
    expires_days: int = 7


# ── User Management ────────────────────────────────────────────

@router.get("/studio/admin/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all studio users."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT id, auth_user_id, display_name, email, avatar_url, role,
                   max_rating, ui_mode, onboarded, (pin_hash IS NOT NULL) as has_pin,
                   created_at, last_login
            FROM studio_users ORDER BY id
        """)
        return {
            "users": [
                {
                    "id": r["id"],
                    "auth_user_id": r["auth_user_id"],
                    "display_name": r["display_name"],
                    "email": r["email"],
                    "avatar_url": r["avatar_url"],
                    "role": r["role"],
                    "max_rating": r["max_rating"],
                    "ui_mode": r["ui_mode"],
                    "onboarded": r["onboarded"],
                    "has_pin": r["has_pin"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "last_login": r["last_login"].isoformat() if r["last_login"] else None,
                }
                for r in rows
            ]
        }
    finally:
        await conn.close()


@router.post("/studio/admin/users")
async def create_user(body: CreateUser, admin: dict = Depends(require_admin)):
    """Create a new local profile."""
    conn = await connect_direct()
    try:
        pin_hash = None
        if body.pin:
            import bcrypt
            pin_hash = bcrypt.hashpw(body.pin.encode(), bcrypt.gensalt()).decode()

        row = await conn.fetchrow("""
            INSERT INTO studio_users (display_name, role, max_rating, ui_mode, pin_hash)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """, body.display_name, body.role, body.max_rating, body.ui_mode, pin_hash)
        return {"id": row["id"], "message": f"User '{body.display_name}' created"}
    finally:
        await conn.close()


@router.patch("/studio/admin/users/{user_id}")
async def update_user(user_id: int, body: UpdateUser, admin: dict = Depends(require_admin)):
    """Update a studio user."""
    conn = await connect_direct()
    try:
        if not await conn.fetchval("SELECT id FROM studio_users WHERE id = $1", user_id):
            raise HTTPException(status_code=404, detail="User not found")

        updates, params, idx = [], [], 1
        for field in ("display_name", "role", "max_rating", "ui_mode"):
            val = getattr(body, field)
            if val is not None:
                updates.append(f"{field} = ${idx}")
                params.append(val)
                idx += 1

        # Handle PIN
        if body.pin is not None:
            if body.pin == "":
                updates.append(f"pin_hash = ${idx}")
                params.append(None)
                idx += 1
            else:
                import bcrypt
                pin_hash = bcrypt.hashpw(body.pin.encode(), bcrypt.gensalt()).decode()
                updates.append(f"pin_hash = ${idx}")
                params.append(pin_hash)
                idx += 1

        if not updates:
            return {"message": "No fields to update"}

        params.append(user_id)
        await conn.execute(
            f"UPDATE studio_users SET {', '.join(updates)} WHERE id = ${idx}", *params
        )
        return {"message": f"User {user_id} updated"}
    finally:
        await conn.close()


@router.delete("/studio/admin/users/{user_id}")
async def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    """Delete a studio user."""
    conn = await connect_direct()
    try:
        # Don't allow deleting yourself
        if admin.get("studio_user_id") == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        deleted = await conn.fetchval(
            "DELETE FROM studio_users WHERE id = $1 RETURNING id", user_id
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": f"User {user_id} deleted"}
    finally:
        await conn.close()


# ── Share Links ─────────────────────────────────────────────────

@router.post("/studio/admin/share-links")
async def create_share_link(body: CreateShareLink, admin: dict = Depends(require_admin)):
    """Create a share link for a project."""
    conn = await connect_direct()
    try:
        # Verify project exists
        project = await conn.fetchrow("SELECT id, name FROM projects WHERE id = $1", body.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        token = secrets.token_urlsafe(48)
        expires_at = datetime.now() + timedelta(days=body.expires_days)

        row = await conn.fetchrow("""
            INSERT INTO share_links (token, project_id, created_by, label, max_rating, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, token
        """, token, body.project_id, admin.get("studio_user_id", 1),
            body.label or f"Share: {project['name']}", body.max_rating, expires_at)

        return {
            "id": row["id"],
            "token": row["token"],
            "url": f"/anime-studio/shared/{row['token']}",
            "expires_at": expires_at.isoformat(),
            "project_name": project["name"],
        }
    finally:
        await conn.close()


@router.get("/studio/admin/share-links")
async def list_share_links(admin: dict = Depends(require_admin)):
    """List all share links."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT sl.*, p.name as project_name,
                   su.display_name as created_by_name,
                   (SELECT COUNT(*) FROM review_comments rc WHERE rc.share_link_id = sl.id) as comment_count
            FROM share_links sl
            JOIN projects p ON sl.project_id = p.id
            LEFT JOIN studio_users su ON sl.created_by = su.id
            ORDER BY sl.created_at DESC
        """)
        return {
            "share_links": [
                {
                    "id": r["id"],
                    "token": r["token"],
                    "project_id": r["project_id"],
                    "project_name": r["project_name"],
                    "label": r["label"],
                    "max_rating": r["max_rating"],
                    "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                    "is_active": r["is_active"],
                    "created_by_name": r["created_by_name"],
                    "comment_count": r["comment_count"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "expired": r["expires_at"] < datetime.now() if r["expires_at"] else False,
                }
                for r in rows
            ]
        }
    finally:
        await conn.close()


@router.delete("/studio/admin/share-links/{token}")
async def revoke_share_link(token: str, admin: dict = Depends(require_admin)):
    """Revoke a share link."""
    conn = await connect_direct()
    try:
        updated = await conn.fetchval(
            "UPDATE share_links SET is_active = FALSE WHERE token = $1 RETURNING id", token
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Share link not found")
        return {"message": "Share link revoked"}
    finally:
        await conn.close()


# ── Reviewer Comments ───────────────────────────────────────────

@router.get("/studio/admin/comments")
async def list_comments(
    project_id: int = None,
    admin: dict = Depends(require_admin),
):
    """List reviewer comments, optionally filtered by project."""
    conn = await connect_direct()
    try:
        if project_id:
            rows = await conn.fetch("""
                SELECT rc.*, p.name as project_name, su.display_name as user_display_name
                FROM review_comments rc
                JOIN projects p ON rc.project_id = p.id
                LEFT JOIN studio_users su ON rc.user_id = su.id
                WHERE rc.project_id = $1
                ORDER BY rc.created_at DESC
            """, project_id)
        else:
            rows = await conn.fetch("""
                SELECT rc.*, p.name as project_name, su.display_name as user_display_name
                FROM review_comments rc
                JOIN projects p ON rc.project_id = p.id
                LEFT JOIN studio_users su ON rc.user_id = su.id
                ORDER BY rc.created_at DESC
                LIMIT 100
            """)
        return {
            "comments": [
                {
                    "id": r["id"],
                    "project_id": r["project_id"],
                    "project_name": r["project_name"],
                    "reviewer_name": r["reviewer_name"] or r["user_display_name"] or "Anonymous",
                    "comment_text": r["comment_text"],
                    "asset_type": r["asset_type"],
                    "asset_id": r["asset_id"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ]
        }
    finally:
        await conn.close()
