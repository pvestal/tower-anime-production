"""Share link public endpoints — project viewing and commenting for external reviewers."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from .db import connect_direct
from .ratings import can_access

logger = logging.getLogger(__name__)
router = APIRouter()


class ReviewComment(BaseModel):
    comment_text: str
    asset_type: Optional[str] = "general"
    asset_id: Optional[str] = None


@router.get("/studio/shared/{token}")
async def get_shared_project(token: str, request: Request):
    """Get project data for a share link (read-only)."""
    conn = await connect_direct()
    try:
        sl = await conn.fetchrow("""
            SELECT sl.*, p.name, p.description, p.genre, p.premise, p.content_rating,
                   p.default_style
            FROM share_links sl
            JOIN projects p ON sl.project_id = p.id
            WHERE sl.token = $1 AND sl.is_active = TRUE AND sl.expires_at > NOW()
        """, token)
        if not sl:
            raise HTTPException(status_code=404, detail="Share link not found or expired")

        # Check content rating against share link's max_rating
        if not can_access(sl["max_rating"], sl["content_rating"] or "R"):
            raise HTTPException(status_code=403, detail="Content exceeds share link rating limit")

        project_id = sl["project_id"]

        # Get approved images for this project's characters
        char_rows = await conn.fetch("""
            SELECT c.id, c.name, c.slug
            FROM characters c WHERE c.project_id = $1
        """, project_id)

        # Get episodes
        episode_rows = await conn.fetch("""
            SELECT id, episode_number, title, description, status,
                   final_video_path, thumbnail_path, actual_duration_seconds
            FROM episodes
            WHERE project_id = $1 AND status IN ('assembled', 'published')
            ORDER BY episode_number
        """, project_id)

        # Get existing comments
        comment_rows = await conn.fetch("""
            SELECT rc.id, rc.reviewer_name, rc.comment_text, rc.asset_type,
                   rc.asset_id, rc.created_at
            FROM review_comments rc
            WHERE rc.share_link_id = $1
            ORDER BY rc.created_at DESC
        """, sl["id"])

        return {
            "project": {
                "name": sl["name"],
                "description": sl["description"],
                "genre": sl["genre"],
                "premise": sl["premise"],
            },
            "share_label": sl["label"],
            "characters": [
                {"id": c["id"], "name": c["name"], "slug": c["slug"]}
                for c in char_rows
            ],
            "episodes": [
                {
                    "id": str(e["id"]),
                    "episode_number": e["episode_number"],
                    "title": e["title"],
                    "description": e["description"],
                    "status": e["status"],
                    "has_video": bool(e["final_video_path"]),
                    "duration_seconds": e["actual_duration_seconds"],
                }
                for e in episode_rows
            ],
            "comments": [
                {
                    "id": c["id"],
                    "reviewer_name": c["reviewer_name"] or "Anonymous",
                    "comment_text": c["comment_text"],
                    "asset_type": c["asset_type"],
                    "asset_id": c["asset_id"],
                    "created_at": c["created_at"].isoformat() if c["created_at"] else None,
                }
                for c in comment_rows
            ],
        }
    finally:
        await conn.close()


@router.post("/studio/shared/{token}/comments")
async def add_comment(token: str, body: ReviewComment, request: Request):
    """Add a reviewer comment to a shared project."""
    user = getattr(request.state, "user", None)

    conn = await connect_direct()
    try:
        sl = await conn.fetchrow("""
            SELECT id, project_id FROM share_links
            WHERE token = $1 AND is_active = TRUE AND expires_at > NOW()
        """, token)
        if not sl:
            raise HTTPException(status_code=404, detail="Share link not found or expired")

        reviewer_name = None
        user_id = None
        if user:
            reviewer_name = user.get("user") or user.get("email")
            user_id = user.get("studio_user_id")

        await conn.execute("""
            INSERT INTO review_comments (share_link_id, project_id, user_id,
                                          reviewer_name, comment_text, asset_type, asset_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, sl["id"], sl["project_id"], user_id,
            reviewer_name, body.comment_text, body.asset_type, body.asset_id)

        return {"message": "Comment added"}
    finally:
        await conn.close()
