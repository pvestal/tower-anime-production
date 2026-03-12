"""Trailer generator — builds representative shot lists for style validation.

Creates a virtual scene with 8 template-driven shots that exercise:
  - Project checkpoint model (establishing shots)
  - Character LoRAs (character intro shots)
  - Video motion LoRAs (action/interaction shots)
  - Audio pipeline (dialogue + SFX on assembled trailer)

The trailer's shots live in the normal `shots` table via a linked scene,
so all existing generation code (keyframe_blitz, generate_scene, assembly)
works without modification.
"""

import logging
import random
import uuid
import yaml
from pathlib import Path

from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

LORA_CATALOG_PATH = Path("/opt/anime-studio/config/lora_catalog.yaml")

# Shot template: each entry defines a role and how to build it
# Every shot features characters — no empty establishing shots.
# The whole point is testing character LoRAs and motion LoRAs.
TRAILER_TEMPLATE = [
    {
        "role": "character_intro",
        "shot_type": "medium",
        "camera_angle": "eye-level",
        "duration": 5.0,
        "needs_characters": True,
        "char_index": 0,
        "description": "Lead character introduction — medium portrait",
    },
    {
        "role": "character_intro",
        "shot_type": "close-up",
        "camera_angle": "eye-level",
        "duration": 5.0,
        "needs_characters": True,
        "char_index": 0,
        "description": "Lead character close-up — detail quality test",
    },
    {
        "role": "character_intro",
        "shot_type": "medium",
        "camera_angle": "low-angle",
        "duration": 5.0,
        "needs_characters": True,
        "char_index": 1,
        "description": "Second character introduction",
    },
    {
        "role": "interaction",
        "shot_type": "medium",
        "camera_angle": "eye-level",
        "duration": 5.0,
        "needs_characters": True,
        "char_count": 2,
        "description": "Two characters together — multi-char coherence",
    },
    {
        "role": "action",
        "shot_type": "action",
        "camera_angle": "eye-level",
        "duration": 5.0,
        "needs_characters": True,
        "use_motion_lora": True,
        "motion_lora_index": 0,
        "description": "Action — first video motion LoRA",
    },
    {
        "role": "action",
        "shot_type": "action",
        "camera_angle": "low-angle",
        "duration": 5.0,
        "needs_characters": True,
        "use_motion_lora": True,
        "motion_lora_index": 1,
        "description": "Action — second video motion LoRA",
    },
    {
        "role": "action",
        "shot_type": "action",
        "camera_angle": "eye-level",
        "duration": 5.0,
        "needs_characters": True,
        "use_motion_lora": True,
        "motion_lora_index": 2,
        "description": "Action — third video motion LoRA",
    },
    {
        "role": "climax",
        "shot_type": "close-up",
        "camera_angle": "eye-level",
        "duration": 5.0,
        "needs_characters": True,
        "char_index": 0,
        "use_motion_lora": True,
        "motion_lora_index": 0,
        "description": "Climax — best character + best motion LoRA",
    },
]


def _load_lora_catalog() -> dict:
    """Load LoRA catalog from YAML."""
    if not LORA_CATALOG_PATH.exists():
        return {}
    with open(LORA_CATALOG_PATH) as f:
        return yaml.safe_load(f) or {}


def _pick_motion_loras(content_rating: str, catalog: dict, count: int = 2) -> list[dict]:
    """Pick diverse video motion LoRA pairs from catalog, prioritizing the project's content tier.

    For XXX projects: pick ONLY from explicit/furry_explicit tiers.
    The whole point of the trailer is testing these LoRAs.
    """
    pairs = catalog.get("video_lora_pairs", {})

    # For XXX content, ONLY pick explicit LoRAs — that's what we're testing
    if content_rating == "XXX":
        priority_tiers = {"explicit", "furry_explicit"}
    elif content_rating == "R":
        priority_tiers = {"mature", "explicit"}
    else:
        priority_tiers = {"universal", "wholesome"}

    eligible = []
    for key, pair in pairs.items():
        tier = pair.get("tier", "universal")
        if tier in priority_tiers:
            high = pair.get("high") or ""
            high_path = Path(f"/opt/ComfyUI/models/loras/{high}")
            if high and high_path.exists():
                eligible.append({"key": key, **pair})

    if not eligible:
        return []

    # Pick diverse pairs (different tag groups)
    selected = []
    used_tags = set()
    random.shuffle(eligible)

    for pair in eligible:
        tags = set(pair.get("tags", []))
        if not tags & used_tags or len(selected) == 0:
            selected.append(pair)
            used_tags |= tags
            if len(selected) >= count:
                break

    # Fill remaining slots if we didn't get enough diversity
    if len(selected) < count:
        for pair in eligible:
            if pair not in selected:
                selected.append(pair)
                if len(selected) >= count:
                    break

    return selected[:count]


async def _pick_characters(conn, project_id: int, count: int = 2) -> list[dict]:
    """Pick characters to feature in trailer, preferring those with LoRAs."""
    chars = await conn.fetch("""
        SELECT id, name, lora_path, lora_trigger, design_prompt, role,
               REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') as slug
        FROM characters
        WHERE project_id = $1 AND design_prompt IS NOT NULL AND design_prompt != ''
        ORDER BY
            CASE WHEN lora_path IS NOT NULL AND lora_path != '' THEN 0 ELSE 1 END,
            CASE WHEN role = 'lead' THEN 0 ELSE 1 END,
            id
    """, project_id)

    return [dict(c) for c in chars[:count]]


async def _get_world_context(conn, project_id: int) -> dict:
    """Get world settings for environment shot prompts."""
    row = await conn.fetchrow("""
        SELECT style_preamble, art_style, aesthetic, color_palette,
               world_location, time_period, negative_prompt_guidance
        FROM world_settings
        WHERE project_id = $1
    """, project_id)
    return dict(row) if row else {}


async def _get_project_info(conn, project_id: int) -> dict:
    """Get project details including checkpoint and style."""
    row = await conn.fetchrow("""
        SELECT p.name, p.content_rating, p.premise, p.genre,
               gs.checkpoint_model, gs.positive_prompt_template, gs.negative_prompt_template,
               gs.width, gs.height
        FROM projects p
        LEFT JOIN generation_styles gs ON p.default_style = gs.style_name
        WHERE p.id = $1
    """, project_id)
    return dict(row) if row else {}


def _build_prompt(
    template_entry: dict,
    project: dict,
    world: dict,
    characters: list[dict],
    motion_loras: list[dict],
) -> tuple[str, str, list[str], str | None, str | None]:
    """Build generation prompt, negative, characters_present, lora_name, and image_lora for a shot.

    Returns (prompt, negative, characters_present_slugs, video_lora_name, image_lora).
    Characters_present uses slugs (not names) so the keyframe pipeline can look them up.
    """
    style_preamble = world.get("style_preamble", "") or ""
    art_style = world.get("art_style", "") or ""
    neg_world = world.get("negative_prompt_guidance", "") or ""
    neg_project = project.get("negative_prompt_template", "") or ""
    negative = f"{neg_world}, {neg_project}".strip(", ") if neg_world or neg_project else "low quality, blurry, watermark"
    role = template_entry["role"]
    video_lora = None
    image_lora = None
    chars_present = []  # slugs

    # Style prefix — if no world settings, use a sensible default from genre
    genre = project.get("genre", "") or ""
    if not style_preamble and not art_style:
        style_preamble = f"{genre} style" if genre else "high quality, detailed"

    if role == "establishing":
        location = ""
        if world.get("world_location"):
            loc = world["world_location"]
            if isinstance(loc, dict):
                location = loc.get("name", "") or loc.get("description", "")
            else:
                location = str(loc)
        if not location:
            # Use project premise for atmosphere
            premise = project.get("premise", "") or ""
            location = premise[:200] if premise else genre
        prompt = f"{style_preamble}, {art_style}, {location}, cinematic establishing shot, wide angle, atmospheric, no people".strip(", ")

    elif role == "character_intro":
        idx = template_entry.get("char_index", 0)
        char = characters[idx % len(characters)] if characters else None
        if char:
            trigger = char.get("lora_trigger", "") or ""
            design = char.get("design_prompt", "") or ""
            slug = char.get("slug", char["name"].lower().replace(" ", "_"))
            chars_present = [slug]
            # Set image_lora for keyframe generation
            if char.get("lora_path"):
                image_lora = char["lora_path"]
            shot_type = template_entry.get("shot_type", "medium")
            framing = "portrait, upper body" if shot_type == "medium" else "face close-up, detailed features"
            prompt = f"{style_preamble}, {trigger}, {design}, {framing}, looking at viewer".strip(", ")
        else:
            prompt = f"{style_preamble}, {art_style}, character portrait, looking at viewer".strip(", ")

    elif role == "interaction":
        char_count = template_entry.get("char_count", 2)
        featured = characters[:char_count] if characters else []
        parts = []
        for c in featured:
            slug = c.get("slug", c["name"].lower().replace(" ", "_"))
            chars_present.append(slug)
            trigger = c.get("lora_trigger", "") or ""
            design = c.get("design_prompt", "") or ""
            parts.append(f"{trigger} {design}".strip())
            if not image_lora and c.get("lora_path"):
                image_lora = c["lora_path"]
        char_desc = ", ".join(parts) if parts else "two characters"
        prompt = f"{style_preamble}, {char_desc}, together, eye contact, dramatic lighting".strip(", ")

    elif role in ("action", "climax"):
        idx = template_entry.get("char_index", 0)
        char = characters[idx % len(characters)] if characters else None
        char_desc = ""
        if char:
            trigger = char.get("lora_trigger", "") or ""
            design = char.get("design_prompt", "") or ""
            slug = char.get("slug", char["name"].lower().replace(" ", "_"))
            chars_present = [slug]
            char_desc = f"{trigger} {design}".strip()
            if char.get("lora_path"):
                image_lora = char["lora_path"]

        # Video motion LoRA for video generation (not keyframes)
        if template_entry.get("use_motion_lora") and motion_loras:
            lora_idx = template_entry.get("motion_lora_index", 0)
            lora = motion_loras[lora_idx % len(motion_loras)]
            video_lora = lora.get("key", "")
            tags = ", ".join(lora.get("tags", []))
            prompt = f"{style_preamble}, {char_desc}, {tags}".strip(", ")
        else:
            prompt = f"{style_preamble}, {char_desc}, action, dynamic movement".strip(", ")

    else:
        prompt = f"{style_preamble}, {art_style}".strip(", ")

    # Clean up double commas/spaces
    prompt = ", ".join(p.strip() for p in prompt.split(",") if p.strip())

    return prompt, negative, chars_present, video_lora, image_lora


async def create_trailer(project_id: int, title: str | None = None) -> dict:
    """Create a trailer with auto-generated shots from template.

    Creates:
    1. A trailers record
    2. A virtual scene linked to the project
    3. 8 shots based on the trailer template

    Returns trailer details including all shot IDs.
    """
    conn = await connect_direct()
    try:
        # Get project info
        project = await _get_project_info(conn, project_id)
        if not project or not project.get("name"):
            raise ValueError(f"Project {project_id} not found")

        # Get version number
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM trailers WHERE project_id = $1", project_id
        )
        version = (existing or 0) + 1

        trailer_title = title or f"{project['name']} - Trailer v{version}"

        # Pick characters and motion LoRAs
        characters = await _pick_characters(conn, project_id, count=3)
        world = await _get_world_context(conn, project_id)
        catalog = _load_lora_catalog()
        content_rating = project.get("content_rating", "R")
        motion_loras = _pick_motion_loras(content_rating, catalog, count=3)

        # Create the virtual scene
        scene_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO scenes (id, project_id, title, description, scene_number, generation_status)
            VALUES ($1, $2, $3, $4,
                    COALESCE((SELECT MAX(scene_number) FROM scenes WHERE project_id = $2), 0) + 1,
                    'pending')
        """, scene_id, project_id, f"[Trailer v{version}]", f"Style validation trailer for {project['name']}")

        # Create trailer record
        trailer_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO trailers (id, project_id, title, version, status, scene_id,
                                  checkpoint_model, video_loras_tested, character_loras_tested)
            VALUES ($1, $2, $3, $4, 'draft', $5, $6, $7::jsonb, $8::jsonb)
        """, trailer_id, project_id, trailer_title, version, scene_id,
            project.get("checkpoint_model", ""),
            _json_dumps([{"key": l.get("key"), "label": l.get("label")} for l in motion_loras]),
            _json_dumps([{"name": c["name"], "lora": c.get("lora_path")} for c in characters]),
        )

        # Build and insert shots
        shots = []
        for i, tmpl in enumerate(TRAILER_TEMPLATE):
            # Skip character shots if no characters available
            if tmpl.get("needs_characters") and not characters:
                continue

            prompt, negative, chars_present, video_lora, image_lora = _build_prompt(
                tmpl, project, world, characters, motion_loras
            )

            shot_id = uuid.uuid4()
            await conn.execute("""
                INSERT INTO shots (id, scene_id, shot_number, shot_type, camera_angle,
                                   duration_seconds, generation_prompt, generation_negative,
                                   characters_present, lora_name, image_lora, trailer_role,
                                   video_engine, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'wan22_14b', 'pending')
            """, shot_id, scene_id, i + 1, tmpl["shot_type"], tmpl["camera_angle"],
                tmpl["duration"], prompt, negative, chars_present or [],
                video_lora, image_lora, tmpl["role"])

            shots.append({
                "shot_id": str(shot_id),
                "shot_number": i + 1,
                "role": tmpl["role"],
                "shot_type": tmpl["shot_type"],
                "video_lora": video_lora,
                "image_lora": image_lora,
                "characters": chars_present,
                "prompt": prompt,
            })

        logger.info(
            f"Trailer created: {trailer_title} ({len(shots)} shots, "
            f"{len(characters)} chars, {len(motion_loras)} motion LoRAs)"
        )

        return {
            "trailer_id": str(trailer_id),
            "title": trailer_title,
            "version": version,
            "scene_id": str(scene_id),
            "project": project["name"],
            "checkpoint": project.get("checkpoint_model", ""),
            "content_rating": content_rating,
            "characters_featured": [c["name"] for c in characters],
            "motion_loras_tested": [l.get("key") for l in motion_loras],
            "shots": shots,
        }

    finally:
        await conn.close()


async def get_trailer(trailer_id: str) -> dict | None:
    """Get trailer details with all shot info."""
    conn = await connect_direct()
    try:
        trailer = await conn.fetchrow(
            "SELECT * FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )
        if not trailer:
            return None

        t = dict(trailer)
        shots = await conn.fetch("""
            SELECT id, shot_number, shot_type, camera_angle, trailer_role,
                   generation_prompt, lora_name, characters_present, status,
                   source_image_path, output_video_path, quality_score,
                   duration_seconds, error_message
            FROM shots
            WHERE scene_id = $1
            ORDER BY shot_number
        """, t["scene_id"])

        t["shots"] = [dict(s) for s in shots]
        # Stringify UUIDs
        for key in ("id", "scene_id"):
            if t.get(key):
                t[key] = str(t[key])
        for s in t["shots"]:
            if s.get("id"):
                s["id"] = str(s["id"])

        return t
    finally:
        await conn.close()


async def list_trailers(project_id: int) -> list[dict]:
    """List all trailers for a project."""
    conn = await connect_direct()
    try:
        rows = await conn.fetch("""
            SELECT t.id, t.title, t.version, t.status, t.final_video_path,
                   t.checkpoint_model, t.video_loras_tested, t.character_loras_tested,
                   t.created_at, t.actual_duration_seconds,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = t.scene_id) as shot_count,
                   (SELECT COUNT(*) FROM shots WHERE scene_id = t.scene_id
                    AND status = 'completed') as completed_shots
            FROM trailers t
            WHERE t.project_id = $1
            ORDER BY t.version DESC
        """, project_id)
        result = []
        for r in rows:
            d = dict(r)
            d["id"] = str(d["id"])
            result.append(d)
        return result
    finally:
        await conn.close()


async def update_trailer_shot(trailer_id: str, shot_id: str, updates: dict) -> dict:
    """Update a trailer shot's prompt, LoRA, or other generation params.

    Resets the shot to pending so it can be regenerated.
    """
    conn = await connect_direct()
    try:
        # Verify shot belongs to this trailer
        trailer = await conn.fetchrow(
            "SELECT scene_id FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )
        if not trailer:
            raise ValueError(f"Trailer {trailer_id} not found")

        shot = await conn.fetchrow(
            "SELECT id FROM shots WHERE id = $1 AND scene_id = $2",
            uuid.UUID(shot_id), trailer["scene_id"]
        )
        if not shot:
            raise ValueError(f"Shot {shot_id} not in trailer {trailer_id}")

        # Apply updates
        allowed = {"generation_prompt", "generation_negative", "lora_name",
                    "shot_type", "camera_angle", "characters_present"}
        set_parts = []
        params = [uuid.UUID(shot_id)]
        idx = 2
        for key, val in updates.items():
            if key in allowed:
                set_parts.append(f"{key} = ${idx}")
                params.append(val)
                idx += 1

        if set_parts:
            # Reset to pending for regeneration
            set_parts.append("status = 'pending'")
            set_parts.append("source_image_path = NULL")
            set_parts.append("output_video_path = NULL")
            set_parts.append("error_message = NULL")
            set_parts.append("comfyui_prompt_id = NULL")

            sql = f"UPDATE shots SET {', '.join(set_parts)} WHERE id = $1"
            await conn.execute(sql, *params)

        return {"shot_id": shot_id, "updated": list(updates.keys()), "status": "pending"}
    finally:
        await conn.close()


async def approve_trailer(trailer_id: str, notes: str = "") -> dict:
    """Mark a trailer as approved — signals style is validated for full production."""
    conn = await connect_direct()
    try:
        await conn.execute("""
            UPDATE trailers SET status = 'approved', review_notes = $2, approved_at = NOW(), updated_at = NOW()
            WHERE id = $1
        """, uuid.UUID(trailer_id), notes)

        trailer = await conn.fetchrow(
            "SELECT project_id, title FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )

        logger.info(f"Trailer approved: {trailer['title']} (project {trailer['project_id']})")

        return {
            "trailer_id": trailer_id,
            "status": "approved",
            "project_id": trailer["project_id"],
        }
    finally:
        await conn.close()


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, default=str)
