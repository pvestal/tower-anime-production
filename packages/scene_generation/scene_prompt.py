"""Prompt engineering helpers — tag classification, genre profiles, slug resolution."""

import logging
from pathlib import Path

from packages.core.config import BASE_PATH
from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Genre-aware video prompt profiles
# ---------------------------------------------------------------------------
# Tag categories — superset of classification keywords across all genres.
# Used by both FramePack (reorder) and Wan (condense) paths.
TAG_CATEGORIES: dict[str, set[str]] = {
    "identity": {"male", "man", "woman", "female", "young", "old", "japanese",
                 "boy", "girl", "adult", "teen", "child", "elderly"},
    "face": {"expression", "smirk", "smile", "frown", "eyes", "eye", "face",
             "scar", "menacing", "nervous", "confident", "worried", "aggressive",
             "gentle", "stern", "gaze", "look", "glasses", "eyepatch", "mask",
             "beard", "mustache"},
    "hair": {"hair", "bald", "ponytail", "braid", "bangs", "twintail",
             "short hair", "long hair", "mohawk"},
    "skin": {"tan", "pale", "skin", "dark skin", "fair", "rough", "smooth",
             "tattoo", "freckle"},
    "body": {"body", "build", "muscular", "slim", "athletic", "toned",
             "shoulder", "chest", "pec", "waist", "abs", "thigh", "leg",
             "butt", "hip", "tall", "short", "lean", "broad", "narrow",
             "flat male chest", "wide", "underfed", "stocky", "petite"},
    "anatomy": {"penis", "testicle", "vagina", "breast", "nipple", "areola",
                "cock", "b-cup", "c-cup", "d-cup", "perky", "nude", "naked",
                "genitals"},
    "equipment": {"sword", "shield", "armor", "helmet", "weapon", "gun",
                  "blade", "staff", "bow", "axe", "spear", "dagger", "gauntlet",
                  "scabbard", "holster"},
    "clothing": {"clothing", "dress", "shirt", "pants", "skirt", "jacket",
                 "coat", "boots", "gloves", "cape", "cloak", "hat", "uniform",
                 "suit", "scarf", "belt", "collar", "bikini", "underwear",
                 "overalls", "vest"},
    "cybernetics": {"cybernetic", "augment", "prosthetic", "implant", "visor",
                    "neon", "circuit", "chrome", "mechanical arm", "bionic"},
    "proportions": {"proportions", "chibi", "stylized", "exaggerated",
                    "realistic proportions", "cartoonish", "round", "plump"},
    "style": {"3d render", "cel-shaded", "pixel", "watercolor", "painterly",
              "illumination", "pixar", "disney", "ghibli"},
}

# Each genre profile specifies how to condense/reorder design_prompt tags.
GENRE_VIDEO_PROFILES: dict[str, dict] = {
    "explicit": {
        "keep_categories": {"identity", "hair", "skin", "body", "anatomy"},
        "reorder_priority": ["identity", "face", "hair", "skin", "body", "anatomy"],
        "negative_additions": "malformed genitals, distorted genitals, malformed penis",
        "include_scene_desc": True,
    },
    "cyberpunk": {
        "keep_categories": {"identity", "hair", "skin", "body", "face",
                            "equipment", "clothing", "cybernetics"},
        "reorder_priority": ["identity", "face", "hair", "equipment",
                             "cybernetics", "clothing", "body", "skin"],
        "negative_additions": "modern casual, peaceful, bright cheerful",
        "include_scene_desc": True,
    },
    "action": {
        "keep_categories": {"identity", "hair", "skin", "body", "face",
                            "equipment", "clothing"},
        "reorder_priority": ["identity", "face", "hair", "equipment",
                             "clothing", "body", "skin"],
        "negative_additions": "peaceful, static, boring",
        "include_scene_desc": True,
    },
    "3d_animation": {
        "keep_categories": {"identity", "hair", "face", "clothing",
                            "proportions", "style"},
        "reorder_priority": ["style", "identity", "face", "hair",
                             "clothing", "proportions"],
        "negative_additions": "photorealistic, anime, 2d, flat shading",
        "include_scene_desc": True,
    },
    "anime": {
        "keep_categories": {"identity", "hair", "face", "skin", "body",
                            "clothing"},
        "reorder_priority": ["identity", "face", "hair", "clothing",
                             "body", "skin"],
        "negative_additions": "photorealistic, 3d render, live action",
        "include_scene_desc": True,
    },
    "default": {
        "keep_categories": {"identity", "hair", "face", "skin", "body",
                            "clothing", "equipment"},
        "reorder_priority": ["identity", "face", "hair", "clothing",
                             "equipment", "body", "skin"],
        "negative_additions": "",
        "include_scene_desc": True,
    },
}


def _get_genre_profile(genre: str | None, content_rating: str | None) -> dict:
    """Resolve project genre + content_rating → video profile dict."""
    # Explicit content rating overrides genre completely
    if content_rating:
        cr = content_rating.lower()
        if any(kw in cr for kw in ("xxx", "adult", "nsfw", "hentai")):
            return GENRE_VIDEO_PROFILES["explicit"]

    if not genre:
        return GENRE_VIDEO_PROFILES["default"]

    g = genre.lower().strip()
    # Direct match
    if g in GENRE_VIDEO_PROFILES:
        return GENRE_VIDEO_PROFILES[g]
    # Keyword-based fallback
    if any(kw in g for kw in ("cyber", "sci-fi", "scifi", "dystop")):
        return GENRE_VIDEO_PROFILES["cyberpunk"]
    if any(kw in g for kw in ("action", "shonen", "battle", "fight", "martial")):
        return GENRE_VIDEO_PROFILES["action"]
    if any(kw in g for kw in ("3d", "pixar", "cg", "illumination", "cartoon")):
        return GENRE_VIDEO_PROFILES["3d_animation"]
    if any(kw in g for kw in ("anime", "manga", "slice of life", "romance")):
        return GENRE_VIDEO_PROFILES["anime"]
    return GENRE_VIDEO_PROFILES["default"]


def _classify_tag(tag_lower: str) -> str:
    """Classify a single prompt tag into a TAG_CATEGORIES bucket."""
    for cat, keywords in TAG_CATEGORIES.items():
        if any(kw in tag_lower for kw in keywords):
            return cat
    return "other"


def _condense_for_video(design_prompt: str, genre_profile: dict,
                        engine: str) -> str:
    """Replace both _video_safe_appearance and _condensed_appearance.

    FramePack: reorder tags by genre priority (keeps all meaningful tags).
    Wan: aggressive condense — only keep tags matching genre keep_categories.
    """
    strip_tags = {"solo", "1boy", "1girl", "full body", "score_9", "score_8_up"}
    parts = [p.strip() for p in design_prompt.split(",") if p.strip()]
    parts = [p for p in parts if p.lower().strip() not in strip_tags]

    if engine in ("framepack", "framepack_f1"):
        # Reorder by genre priority, keep all categorised tags
        priority = genre_profile.get("reorder_priority",
                                     GENRE_VIDEO_PROFILES["default"]["reorder_priority"])
        buckets: dict[str, list[str]] = {cat: [] for cat in priority}
        buckets["other"] = []
        for p in parts:
            cat = _classify_tag(p.lower().strip())
            if cat in buckets:
                buckets[cat].append(p)
            else:
                buckets["other"].append(p)
        ordered = []
        for cat in priority:
            ordered.extend(buckets.get(cat, []))
        ordered.extend(buckets["other"])
        return ", ".join(ordered) if ordered else design_prompt
    else:
        # Wan T2V: aggressive condense — only keep_categories tags
        keep_cats = genre_profile.get("keep_categories",
                                      GENRE_VIDEO_PROFILES["default"]["keep_categories"])
        # Flatten all keywords from kept categories
        keep_keywords: set[str] = set()
        for cat in keep_cats:
            if cat in TAG_CATEGORIES:
                keep_keywords.update(TAG_CATEGORIES[cat])
        kept = []
        for p in parts:
            low = p.lower().strip()
            if any(kw in low for kw in keep_keywords):
                kept.append(p)
        return ", ".join(kept) if kept else design_prompt


def _build_video_negative(style_anchor: str, genre_profile: dict,
                          nsm_negative: str = "") -> str:
    """Build negative prompt from base + style exclusions + genre additions."""
    parts = ["low quality, blurry, watermark, deformed face, distorted face, "
             "bad hands, extra limbs"]
    # Style-aware exclusions
    if style_anchor:
        if "photorealistic" in style_anchor:
            parts.append("anime, cartoon, illustration, drawing, painted, "
                         "cel-shaded, 3d render")
        elif "anime" in style_anchor:
            parts.append("photorealistic, photograph, live action, real person")
        elif "Pixar" in style_anchor:
            parts.append("anime, photorealistic, photograph, live action, 2d, flat")
    # Genre-specific additions
    genre_neg = genre_profile.get("negative_additions", "")
    if genre_neg:
        parts.append(genre_neg)
    # NSM state additions
    if nsm_negative:
        parts.append(nsm_negative)
    return ", ".join(parts)


async def build_shot_prompt_preview(scene_id: str, shot_id: str) -> dict:
    """Build the final prompt that would be sent to ComfyUI, without generating.

    Returns dict with: final_prompt, final_negative, engine, style_anchor,
    character_appearances, scene_context, and component breakdown.
    """
    conn = await connect_direct()
    try:
        scene_uuid = __import__("uuid").UUID(scene_id)
        shot_uuid = __import__("uuid").UUID(shot_id)

        shot_row = await conn.fetchrow(
            "SELECT * FROM shots WHERE id = $1 AND scene_id = $2", shot_uuid, scene_uuid
        )
        if not shot_row:
            return {"error": "Shot not found"}

        scene_row = await conn.fetchrow(
            "SELECT project_id, description, location, time_of_day, mood FROM scenes WHERE id = $1",
            scene_uuid,
        )
        if not scene_row:
            return {"error": "Scene not found"}

        project_id = scene_row["project_id"]
        scene_desc = scene_row["description"] or ""
        scene_location = scene_row["location"] or ""
        scene_mood = scene_row["mood"] or ""
        scene_time = scene_row["time_of_day"] or ""

        # Get project genre profile
        proj_row = await conn.fetchrow(
            "SELECT genre, content_rating FROM projects WHERE id = $1", project_id
        )
        genre_profile = _get_genre_profile(
            proj_row["genre"] if proj_row else None,
            proj_row["content_rating"] if proj_row else None,
        )

        # Get style anchor
        style_anchor = ""
        try:
            style_row = await conn.fetchrow(
                "SELECT gs.checkpoint_model FROM projects p "
                "JOIN generation_styles gs ON p.default_style = gs.style_name "
                "WHERE p.id = $1", project_id,
            )
            if style_row:
                ckpt = (style_row["checkpoint_model"] or "").lower()
                if "illustrious" in ckpt or "noob" in ckpt:
                    style_anchor = "anime style, detailed animation, cinematic"
                elif "cyberrealistic" in ckpt:
                    style_anchor = "photorealistic, live action film, cinematic lighting"
                elif "nova_animal" in ckpt or "pony" in ckpt:
                    style_anchor = "anime style, detailed illustration, cinematic"
        except Exception:
            pass

        shot_dict = dict(shot_row)
        chars = shot_dict.get("characters_present") or []
        character_slug = chars[0] if len(chars) == 1 else None
        shot_engine = shot_dict.get("video_engine") or "framepack"
        motion_prompt = shot_dict["motion_prompt"] or shot_dict.get("generation_prompt") or ""

        # Helper: look up character
        async def _find_char(slug):
            return await conn.fetchrow(
                "SELECT name, design_prompt FROM characters "
                "WHERE project_id = $2 AND ("
                "  REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') = $1 "
                "  OR REGEXP_REPLACE(LOWER(REPLACE(name, ' ', '_')), '[^a-z0-9_-]', '', 'g') LIKE $1 || '_%'"
                ")", slug, project_id,
            )

        # Build prompt per engine — mirrors generate_scene logic
        current_prompt = motion_prompt
        char_appearances = []

        if character_slug and shot_engine in ("framepack", "framepack_f1"):
            try:
                char_row = await _find_char(character_slug)
                if char_row and char_row["design_prompt"]:
                    appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                    char_appearances.append({"name": char_row["name"], "condensed": appearance})
                    fp_parts = []
                    if style_anchor:
                        fp_parts.append(style_anchor)
                    if scene_location:
                        setting = scene_location
                        if scene_time:
                            setting += f", {scene_time}"
                        fp_parts.append(setting)
                    if scene_desc:
                        fp_parts.append(scene_desc)
                    fp_parts.append(appearance)
                    if motion_prompt and motion_prompt.lower() != "static":
                        fp_parts.append(motion_prompt)
                    fp_parts.append("consistent character appearance, maintain all physical features")
                    if scene_mood:
                        fp_parts.append(f"{scene_mood} mood")
                    current_prompt = ", ".join(fp_parts)
            except Exception:
                pass
        elif shot_engine in ("wan22", "wan22_14b") and chars:
            try:
                char_descriptions = []
                for cslug in chars:
                    char_row = await _find_char(cslug)
                    if char_row and char_row["design_prompt"]:
                        appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                        char_descriptions.append(f"{char_row['name']} ({appearance})")
                        char_appearances.append({"name": char_row["name"], "condensed": appearance})
                prompt_parts = []
                if char_descriptions:
                    prompt_parts.append("; ".join(char_descriptions))
                if motion_prompt and motion_prompt.lower() != "static":
                    prompt_parts.append(motion_prompt)
                if scene_desc and genre_profile.get("include_scene_desc", True):
                    prompt_parts.append(scene_desc[:200])
                if scene_location:
                    setting = scene_location
                    if scene_time:
                        setting += f", {scene_time}"
                    prompt_parts.append(setting)
                if style_anchor:
                    prompt_parts.append(style_anchor)
                if scene_mood:
                    prompt_parts.append(f"{scene_mood} mood")
                current_prompt = ". ".join(prompt_parts)
            except Exception:
                pass
        elif shot_engine == "wan" and chars:
            try:
                char_descriptions = []
                for cslug in chars:
                    char_row = await _find_char(cslug)
                    if char_row and char_row["design_prompt"]:
                        appearance = _condense_for_video(char_row["design_prompt"], genre_profile, shot_engine)
                        char_descriptions.append(f"{char_row['name']} ({appearance})")
                        char_appearances.append({"name": char_row["name"], "condensed": appearance})
                prompt_parts = []
                if motion_prompt and motion_prompt.lower() != "static":
                    prompt_parts.append(motion_prompt)
                if char_descriptions:
                    prompt_parts.append("; ".join(char_descriptions))
                if scene_desc and genre_profile.get("include_scene_desc", True):
                    prompt_parts.append(scene_desc[:120])
                if scene_location:
                    setting = scene_location
                    if scene_time:
                        setting += f", {scene_time}"
                    prompt_parts.append(setting)
                if style_anchor:
                    prompt_parts.append(style_anchor)
                current_prompt = ". ".join(prompt_parts)
            except Exception:
                pass

        current_negative = _build_video_negative(style_anchor, genre_profile)

        return {
            "final_prompt": current_prompt,
            "final_negative": current_negative,
            "engine": shot_engine,
            "prompt_length": len(current_prompt),
            "style_anchor": style_anchor or None,
            "scene_context": {
                "location": scene_location or None,
                "time_of_day": scene_time or None,
                "mood": scene_mood or None,
                "description": scene_desc[:200] if scene_desc else None,
            },
            "character_appearances": char_appearances,
            "motion_prompt": shot_dict["motion_prompt"] or None,
            "generation_prompt": shot_dict["generation_prompt"] or None,
        }
    finally:
        await conn.close()


# --- Slug resolver: maps short slugs (rina) to dataset dir slugs (rina_suzuki) ---
_slug_cache: dict[str, str] = {}


def resolve_slug(short_slug: str) -> str:
    """Resolve a possibly-short character slug to the actual dataset directory name.

    Tries exact match first, then prefix match (short_slug + '_*').
    Caches results for the lifetime of the process.
    """
    if short_slug in _slug_cache:
        return _slug_cache[short_slug]
    # Exact match
    if (BASE_PATH / short_slug).is_dir():
        _slug_cache[short_slug] = short_slug
        return short_slug
    # Prefix match: rina -> rina_suzuki
    candidates = sorted(BASE_PATH.glob(f"{short_slug}_*"))
    dirs = [c for c in candidates if c.is_dir()]
    if dirs:
        resolved = dirs[0].name
        _slug_cache[short_slug] = resolved
        return resolved
    # No match — return as-is
    _slug_cache[short_slug] = short_slug
    return short_slug
