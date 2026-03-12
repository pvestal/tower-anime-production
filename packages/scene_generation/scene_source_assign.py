"""Source image/video assignment — auto-assign best sources to shots."""

import json
import logging
from pathlib import Path

from packages.core.config import BASE_PATH
from packages.core.audit import log_decision
from .scene_prompt import resolve_slug
from .image_recommender import recommend_for_scene

logger = logging.getLogger(__name__)


async def ensure_source_videos(conn, scene_id: str, shots: list) -> int:
    """Auto-assign best source video clips to solo shots from character_clips table.

    Mirrors ensure_source_images but assigns video clips for V2V style transfer.
    Only assigns to solo character shots that don't already have a source_video_path
    and weren't manually assigned. Returns the number of shots auto-assigned.
    """
    null_shots = [
        s for s in shots
        if not s.get("source_video_path")
        and not s.get("source_video_auto_assigned")
        and len(s.get("characters_present") or []) == 1
    ]
    if not null_shots:
        return 0

    assigned = 0
    for shot in null_shots:
        chars = shot.get("characters_present") or []
        slug = chars[0] if chars else None
        if not slug:
            continue

        try:
            clip_row = await conn.fetchrow(
                "SELECT clip_path FROM character_clips "
                "WHERE character_slug = $1 ORDER BY similarity DESC NULLS LAST LIMIT 1",
                slug,
            )
            if clip_row and clip_row["clip_path"] and Path(clip_row["clip_path"]).exists():
                await conn.execute(
                    "UPDATE shots SET source_video_path = $2, source_video_auto_assigned = TRUE WHERE id = $1",
                    shot["id"], clip_row["clip_path"],
                )
                assigned += 1
                logger.info(
                    f"Shot {shot['id']}: auto-assigned source video clip for '{slug}' "
                    f"({clip_row['clip_path']})"
                )
        except Exception as e:
            logger.debug(f"Source video lookup for {slug}: {e}")

    return assigned


async def ensure_source_images(conn, scene_id: str, shots: list) -> int:
    """Auto-assign best source images to solo-character shots with NULL source_image_path.

    Uses the image recommender to score and rank approved images per character.
    Assigns images to ALL solo character shots (1 character) regardless of current
    engine — the engine selector runs AFTER this and will pick FramePack when a
    source image is available. Multi-char shots (>1 character) are handled separately
    by generate_composite_source() in Step 1.5 of the generation pipeline.

    Returns the number of shots that were auto-assigned.
    """
    null_shots = [
        s for s in shots
        if not s["source_image_path"]
        and len(s.get("characters_present") or []) == 1
    ]
    if not null_shots:
        return 0

    # Priority 0: Check continuity frames from previously completed shots
    # These are the last frames from prior scenes — best for visual consistency
    assigned_from_continuity = 0
    scene_row = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", scene_id)
    _project_id = scene_row["project_id"] if scene_row else None
    if _project_id:
        remaining_null = []
        for shot in null_shots:
            chars = shot.get("characters_present") or []
            slug = chars[0] if chars else None
            if not slug:
                remaining_null.append(shot)
                continue
            try:
                cont_row = await conn.fetchrow(
                    "SELECT frame_path FROM character_continuity_frames "
                    "WHERE project_id = $1 AND character_slug = $2 AND scene_id != $3",
                    _project_id, slug, scene_id,
                )
                if cont_row and cont_row["frame_path"] and Path(cont_row["frame_path"]).exists():
                    await conn.execute(
                        "UPDATE shots SET source_image_path = $2, source_image_auto_assigned = TRUE WHERE id = $1",
                        shot["id"], cont_row["frame_path"],
                    )
                    assigned_from_continuity += 1
                    logger.info(
                        f"Shot {shot['id']}: continuity frame for '{slug}' from prior scene"
                    )
                    continue
            except Exception as _e:
                logger.debug(f"Continuity frame lookup for {slug}: {_e}")
            remaining_null.append(shot)
        null_shots = remaining_null
        if not null_shots:
            return assigned_from_continuity

    # Build approved image map from approval_status.json
    all_slugs: set[str] = set()
    for shot in null_shots:
        chars = shot.get("characters_present")
        if chars and isinstance(chars, list):
            all_slugs.update(chars)

    if not all_slugs:
        logger.warning(f"Scene {scene_id}: shots need source images but no characters_present set")
        return assigned_from_continuity

    approved: dict[str, list[str]] = {}
    for slug in all_slugs:
        dir_slug = resolve_slug(slug)
        approval_file = BASE_PATH / dir_slug / "approval_status.json"
        images_dir = BASE_PATH / dir_slug / "images"
        if not images_dir.exists():
            logger.debug(f"No dataset dir for slug '{slug}' (resolved: '{dir_slug}')")
            continue
        if approval_file.exists():
            try:
                with open(approval_file) as f:
                    statuses = json.load(f)
                imgs = [
                    name for name, st in statuses.items()
                    if (st == "approved" or (isinstance(st, dict) and st.get("status") == "approved"))
                    and (images_dir / name).exists()
                ]
                if imgs:
                    # Store under BOTH short and dir slug so lookups work either way
                    approved[slug] = sorted(imgs)
                    approved[dir_slug] = approved[slug]
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read approval_status.json for {dir_slug}: {e}")

    if not approved:
        # Mark all null shots as failed — no images available
        for shot in null_shots:
            await conn.execute(
                "UPDATE shots SET status = 'failed', "
                "error_message = 'No approved images available for auto-assignment' "
                "WHERE id = $1", shot["id"],
            )
        logger.error(f"Scene {scene_id}: no approved images for any character — {len(null_shots)} shots failed")
        return 0

    # Batch-fetch video effectiveness scores (one query per character, not per image)
    video_scores: dict[str, dict[str, float]] = {}
    for slug in all_slugs:
        dir_slug = resolve_slug(slug)
        try:
            # Try both short and resolved slug in effectiveness table
            rows = await conn.fetch(
                "SELECT image_name, AVG(video_quality_score) as avg_score "
                "FROM source_image_effectiveness "
                "WHERE character_slug IN ($1, $2) AND video_quality_score IS NOT NULL "
                "GROUP BY image_name",
                slug, dir_slug,
            )
            if rows:
                video_scores[slug] = {r["image_name"]: float(r["avg_score"]) for r in rows}
                video_scores[dir_slug] = video_scores[slug]
        except Exception as e:
            logger.debug(f"Video effectiveness lookup for {slug}: {e}")

    # Build shot dicts for recommender (include motion_prompt for description matching)
    shot_list = [{
        "id": str(s["id"]),
        "shot_number": s["shot_number"],
        "shot_type": s["shot_type"],
        "camera_angle": s["camera_angle"],
        "characters_present": s["characters_present"] or [],
        "source_image_path": s["source_image_path"],
        "motion_prompt": s.get("motion_prompt"),
    } for s in shots]  # Pass ALL shots for diversity tracking

    # Fetch narrative state and image tags for state-aware selection (NSM Phase 1b)
    character_states = None
    character_image_tags = None
    try:
        state_rows = await conn.fetch(
            "SELECT character_slug, clothing, hair_state, emotional_state, "
            "body_state, energy_level FROM character_scene_state WHERE scene_id = $1",
            scene_id,
        )
        if state_rows:
            character_states = {
                r["character_slug"]: dict(r) for r in state_rows
            }
            # Fetch image tags for all characters that have states
            character_image_tags = {}
            for slug in character_states:
                tag_rows = await conn.fetch(
                    "SELECT image_name, clothing, hair_state, expression, "
                    "body_state, pose FROM image_visual_tags "
                    "WHERE character_slug = $1",
                    slug,
                )
                if tag_rows:
                    character_image_tags[slug] = {
                        r["image_name"]: dict(r) for r in tag_rows
                    }
    except Exception as e:
        logger.debug(f"NSM state lookup for scene {scene_id}: {e}")

    recommendations = recommend_for_scene(
        BASE_PATH, shot_list, approved, top_n=1, video_scores=video_scores,
        character_states=character_states,
        character_image_tags=character_image_tags,
    )

    assigned_count = 0
    for rec in recommendations:
        shot_id = rec["shot_id"]
        # Only assign to shots that actually need it
        if rec["current_source"]:
            continue
        top_recs = rec.get("recommendations", [])
        if not top_recs:
            # No recommendation available for this shot's character
            await conn.execute(
                "UPDATE shots SET status = 'failed', "
                "error_message = 'No approved images for character(s) in this shot' "
                "WHERE id = $1", shot_id,
            )
            continue

        best = top_recs[0]
        dir_slug = resolve_slug(best['slug'])
        image_path = f"{dir_slug}/images/{best['image_name']}"

        await conn.execute(
            "UPDATE shots SET source_image_path = $2, source_image_auto_assigned = TRUE WHERE id = $1",
            shot_id, image_path,
        )
        assigned_count += 1

        await log_decision(
            decision_type="source_image_auto_assign",
            input_context={
                "shot_id": str(shot_id),
                "scene_id": str(scene_id),
                "character_slug": best["slug"],
                "image_name": best["image_name"],
                "score": best["score"],
                "reason": best["reason"],
            },
            decision_made="auto_assigned",
            confidence_score=best["score"],
            reasoning=f"Auto-assigned {best['image_name']} (score={best['score']:.3f}, {best['reason']})",
        )
        logger.info(
            f"Shot {shot_id}: auto-assigned {image_path} "
            f"(score={best['score']:.3f}, {best['reason']})"
        )

    total_assigned = assigned_count + assigned_from_continuity
    if total_assigned:
        logger.info(
            f"Scene {scene_id}: auto-assigned source images for {total_assigned} shots "
            f"({assigned_from_continuity} from continuity, {assigned_count} from approved pool)"
        )

    return total_assigned


async def _get_continuity_frame(conn, project_id: int, character_slug: str, current_scene_id) -> str | None:
    """Look up the most recent generated frame for this character from a prior scene.

    Returns the frame path if it exists and the file is on disk, else None.
    Only returns frames from OTHER scenes (not the current one) to avoid
    self-referencing within the same scene's shot loop.
    """
    row = await conn.fetchrow("""
        SELECT frame_path FROM character_continuity_frames
        WHERE project_id = $1 AND character_slug = $2 AND scene_id != $3
    """, project_id, character_slug, current_scene_id)
    if row and row["frame_path"] and Path(row["frame_path"]).exists():
        return row["frame_path"]
    return None


async def _save_continuity_frame(
    conn, project_id: int, character_slug: str,
    scene_id, shot_id, frame_path: str,
    scene_number: int | None = None, shot_number: int | None = None,
):
    """Save/update the most recent frame for a character in this project.

    Uses UPSERT — one row per (project_id, character_slug), always the latest.
    """
    await conn.execute("""
        INSERT INTO character_continuity_frames
            (project_id, character_slug, scene_id, shot_id, frame_path,
             scene_number, shot_number, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        ON CONFLICT (project_id, character_slug) DO UPDATE SET
            scene_id = EXCLUDED.scene_id,
            shot_id = EXCLUDED.shot_id,
            frame_path = EXCLUDED.frame_path,
            scene_number = EXCLUDED.scene_number,
            shot_number = EXCLUDED.shot_number,
            created_at = now()
    """, project_id, character_slug, scene_id, shot_id, frame_path,
         scene_number, shot_number)
