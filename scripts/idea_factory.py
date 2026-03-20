#!/usr/bin/env python3
"""Idea Factory v3 — cross-project creative intelligence engine.

INTELLIGENCE LAYERS:
  1. Narrative Pressure   — External creative seeds (archetypes, art movements, genre tropes)
  2. Temporal Drift       — Anti-repeat: tracks combo hashes, weights against already-explored space
  3. Character Relations  — Dramatic pairings from config, affinity/tension scoring
  4. Feedback Learning    — Approved ideas up-weight future selection, rejected combos down-weight

STRATEGIES (8):
  character_keyframe, scene_remix, world_crossover, checkpoint_shootout,
  motion_preview, style_transfer, storyline_moment, shot_gap_fill

Usage:
    python scripts/idea_factory.py [--interval 150] [--dry-run] [--strategy all|...]
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from packages.core.config import BASE_PATH, COMFYUI_URL
from packages.core.db import get_pool, connect_direct
from packages.core.generation import generate_batch
from packages.core.audit import log_decision
from packages.lora_training.feedback import get_feedback_negatives, register_pending_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [idea-factory] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("idea_factory")

# ── Constants ──
DEFAULT_INTERVAL = 150
COMFYUI_QUEUE_URL = f"{COMFYUI_URL}/queue"
BACKOFF_BUSY = 30
BACKOFF_ERROR = 60
MAX_CONSECUTIVE_ERRORS = 10
VISION_REVIEW_TIMEOUT = 600

# ── Strategy base weights (modified by feedback learning) ──
STRATEGY_WEIGHTS = {
    "character_keyframe": 25,
    "scene_remix": 20,
    "world_crossover": 15,
    "checkpoint_shootout": 5,
    "motion_preview": 10,
    "style_transfer": 15,
    "storyline_moment": 5,
    "shot_gap_fill": 5,
}

# ── State ──
_consecutive_errors = 0
_generation_count = 0
_strategy_counts: dict[str, int] = {}
_characters_seen: dict[str, int] = {}
_last_review_results: dict[str, dict] = {}

# ── Caches ──
_cache_ttl = 300
_cache: dict[str, tuple[float, any]] = {}


def load_templates() -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / "idea_templates.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def check_comfyui_busy() -> bool:
    """Check if ALL available GPUs are busy. Returns False if any GPU is free."""
    try:
        from packages.core.dual_gpu import get_best_gpu_for_task, _get_queue_depth
        best_url = get_best_gpu_for_task("keyframe")
        return _get_queue_depth(best_url) > 0
    except ImportError:
        pass
    # Fallback: check nvidia only
    try:
        req = urllib.request.Request(COMFYUI_QUEUE_URL)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        running = len(data.get("queue_running", []))
        pending = len(data.get("queue_pending", []))
        return running > 0 or pending > 0
    except Exception:
        return True


# ═══════════════════════════════════════════════════════════════
# LAYER 1: NARRATIVE PRESSURE — inject external creative seeds
# ═══════════════════════════════════════════════════════════════

def select_narrative_seed(templates: dict) -> dict | None:
    """Pick a narrative seed to bias this tick's generation.

    50% chance of applying a seed. When active, it biases mood/setting
    and adds thematic context to the prompt.
    """
    seeds = templates.get("narrative_seeds", {})
    if not seeds:
        return None

    # 50% chance of narrative pressure per tick
    if random.random() > 0.5:
        return None

    # Weighted selection across seed categories
    # archetypes and incongruity are more creatively interesting → higher weight
    category_weights = {
        "archetypes": 30,
        "genre_tropes": 20,
        "art_movements": 20,
        "seasonal": 15,
        "incongruity": 15,
    }

    available = [(cat, seeds[cat]) for cat in category_weights if cat in seeds and seeds[cat]]
    if not available:
        return None

    cats, pools = zip(*available)
    weights = [category_weights.get(c, 10) for c in cats]
    chosen_cat = random.choices(cats, weights=weights, k=1)[0]
    chosen_pool = seeds[chosen_cat]
    item = random.choice(chosen_pool)

    if chosen_cat == "archetypes":
        return {
            "category": "archetype",
            "name": item.get("theme", ""),
            "prompt_fragment": item.get("mood", ""),
            "bias_mood": item.get("bias_mood"),
        }
    elif chosen_cat == "incongruity":
        return {
            "category": "incongruity",
            "name": item.get("note", "emotional clash"),
            "prompt_fragment": f"{item.get('mood_clash', '')}, {item.get('setting_clash', '')}",
            "bias_mood": None,
        }
    elif chosen_cat == "art_movements":
        return {
            "category": "art_movement",
            "name": item.split(",")[0] if "," in item else item[:30],
            "prompt_fragment": item,
            "bias_mood": None,
        }
    else:
        # genre_tropes and seasonal are plain strings
        return {
            "category": chosen_cat,
            "name": item[:40],
            "prompt_fragment": item,
            "bias_mood": None,
        }


# ═══════════════════════════════════════════════════════════════
# LAYER 2: TEMPORAL DRIFT — explore, don't repeat
# ═══════════════════════════════════════════════════════════════

# In-memory set of combo hashes seen this session
_session_combos: set[str] = set()
# DB-loaded combo counts (refreshed periodically)
_historical_combos: dict[str, int] = {}
_historical_loaded_at: float = 0


def compute_combo_hash(strategy: str, char_slug: str, extra: str = "") -> str:
    """Deterministic hash for a strategy+character+context combo."""
    raw = f"{strategy}:{char_slug}:{extra}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


async def _connect_public():
    """Connect with search_path=public to avoid ag_catalog interference."""
    from packages.core.config import DB_CONFIG
    import asyncpg
    return await asyncpg.connect(
        host=DB_CONFIG.get("host", "localhost"),
        database=DB_CONFIG.get("database", "anime_production"),
        user=DB_CONFIG.get("user", "patrick"),
        password=DB_CONFIG.get("password"),
        server_settings={"search_path": "public"},
    )


async def load_historical_combos():
    """Load combo frequency from idea_factory_log (every 10 min)."""
    global _historical_combos, _historical_loaded_at
    if time.time() - _historical_loaded_at < 600:
        return
    try:
        conn = await _connect_public()
        rows = await conn.fetch("""
            SELECT combo_hash, COUNT(*) as cnt,
                   AVG(CASE WHEN approved = TRUE THEN 1.0 WHEN approved = FALSE THEN 0.0 END) as approval_rate
            FROM idea_factory_log
            GROUP BY combo_hash
        """)
        await conn.close()
        _historical_combos = {r["combo_hash"]: r["cnt"] for r in rows}
        _historical_loaded_at = time.time()
        logger.info(f"Loaded {len(_historical_combos)} historical combos")
    except Exception as e:
        logger.warning(f"Failed to load historical combos: {e}")


def temporal_drift_penalty(combo_hash: str) -> float:
    """Return a penalty (0.0 to 0.9) for already-explored combos.

    Session repeats → heavy penalty (0.7-0.9)
    Historical repeats → moderate penalty scaled by count
    Novel combos → no penalty (0.0)
    """
    if combo_hash in _session_combos:
        return 0.8  # Already tried this session

    hist_count = _historical_combos.get(combo_hash, 0)
    if hist_count == 0:
        return 0.0  # Novel — full weight
    elif hist_count <= 3:
        return 0.2
    elif hist_count <= 10:
        return 0.4
    else:
        return 0.6  # Well-explored — heavily penalize


# ═══════════════════════════════════════════════════════════════
# LAYER 3: CHARACTER RELATIONSHIPS — dramatic pairings
# ═══════════════════════════════════════════════════════════════

def get_relationship_pairings(templates: dict) -> list[dict]:
    """Flatten all character relationship axes into a pairing list."""
    rels = templates.get("character_relationships", {})
    pairings = []
    for axis_name, axis_pairs in rels.items():
        if not isinstance(axis_pairs, list):
            continue
        for p in axis_pairs:
            pairings.append({
                "pair": p.get("pair", []),
                "type": p.get("type", "affinity"),
                "weight": p.get("weight", 1),
                "note": p.get("note", ""),
                "axis": axis_name,
            })
    return pairings


def pick_dramatic_pairing(
    char_slug: str, characters: list[dict], templates: dict
) -> dict | None:
    """Given a primary character, find a dramatically interesting partner.

    Returns the partner character dict or None.
    Uses config relationships when available, falls back to cross-project random.
    """
    pairings = get_relationship_pairings(templates)
    char_slugs = {c["slug"]: c for c in characters}

    # Find pairings involving this character
    relevant = []
    for p in pairings:
        pair = p["pair"]
        if len(pair) != 2:
            continue
        if char_slug in pair:
            other = pair[1] if pair[0] == char_slug else pair[0]
            if other in char_slugs:
                relevant.append((char_slugs[other], p["weight"], p))

    if relevant:
        # Weighted selection among configured pairings
        chars, weights, pairing_info = zip(*relevant)
        chosen_idx = random.choices(range(len(chars)), weights=weights, k=1)[0]
        partner = chars[chosen_idx]
        info = pairing_info[chosen_idx]
        logger.info(
            f"Dramatic pairing: {char_slug} + {partner['slug']} "
            f"({info['type']}, {info['axis']}: {info['note']})"
        )
        return partner

    return None  # No configured pairing — strategies handle their own fallback


# ═══════════════════════════════════════════════════════════════
# LAYER 4: FEEDBACK LEARNING — approved combos up-weight
# ═══════════════════════════════════════════════════════════════

_feedback_scores: dict[str, float] = {}  # strategy → learned weight modifier
_feedback_loaded_at: float = 0


async def load_feedback_scores():
    """Learn which strategies produce approved results."""
    global _feedback_scores, _feedback_loaded_at
    if time.time() - _feedback_loaded_at < 600:
        return
    try:
        conn = await _connect_public()
        rows = await conn.fetch("""
            SELECT strategy,
                   COUNT(*) as total,
                   SUM(CASE WHEN approved = TRUE THEN 1 ELSE 0 END) as approved_count,
                   SUM(CASE WHEN approved = FALSE THEN 1 ELSE 0 END) as rejected_count
            FROM idea_factory_log
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY strategy
        """)
        await conn.close()

        _feedback_scores = {}
        for r in rows:
            total = r["total"]
            if total < 5:
                continue  # Not enough data
            approval_rate = r["approved_count"] / total if total > 0 else 0.5
            # Convert to weight modifier: 0.5 rate = 1.0x, 0.8 rate = 1.6x, 0.2 rate = 0.6x
            _feedback_scores[r["strategy"]] = 0.4 + (approval_rate * 1.2)

        _feedback_loaded_at = time.time()
        if _feedback_scores:
            scores_str = ", ".join(f"{k}={v:.2f}" for k, v in _feedback_scores.items())
            logger.info(f"Feedback modifiers: {scores_str}")
    except Exception as e:
        logger.warning(f"Failed to load feedback scores: {e}")


async def log_idea(idea: dict, gen_history_id: int | None):
    """Record idea to idea_factory_log for temporal drift + feedback learning."""
    try:
        conn = await _connect_public()
        await conn.execute("""
            INSERT INTO idea_factory_log
                (strategy, character_slug, second_character_slug,
                 source_project, target_project, narrative_seed,
                 checkpoint_override, combo_hash, generation_history_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
            idea.get("strategy"),
            idea.get("character", {}).get("slug"),
            idea.get("second_character_slug"),
            idea.get("source_project"),
            idea.get("target_project"),
            idea.get("narrative_seed_name"),
            idea.get("checkpoint_override"),
            idea.get("combo_hash", ""),
            gen_history_id,
        )
        await conn.close()
    except Exception as e:
        logger.warning(f"Failed to log idea: {e}")


async def sync_idea_approvals():
    """Backfill approved/rejected status from generation_history into idea_factory_log.

    Run periodically to close the feedback loop.
    """
    try:
        conn = await _connect_public()
        await conn.execute("""
            UPDATE idea_factory_log ifl
            SET approved = CASE
                    WHEN gh.status = 'approved' THEN TRUE
                    WHEN gh.status = 'rejected' THEN FALSE
                    ELSE NULL
                END,
                quality_score = gh.quality_score
            FROM generation_history gh
            WHERE ifl.generation_history_id = gh.id
              AND ifl.approved IS NULL
              AND gh.status IN ('approved', 'rejected')
        """)
        await conn.close()
    except Exception as e:
        logger.debug(f"Sync approvals: {e}")


# ═══════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════

async def _cached(key: str, loader):
    now = time.time()
    if key in _cache and (now - _cache[key][0]) < _cache_ttl:
        return _cache[key][1]
    result = await loader()
    _cache[key] = (now, result)
    return result


async def get_eligible_characters() -> list[dict]:
    async def _load():
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT
                    c.id, c.name,
                    REGEXP_REPLACE(LOWER(REPLACE(c.name, ' ', '_')), '[^a-z0-9_-]', '', 'g') AS slug,
                    c.design_prompt, c.lora_path, c.lora_trigger, c.appearance_data,
                    p.id AS project_id, p.name AS project_name, p.content_rating,
                    gs.checkpoint_model, gs.cfg_scale, gs.steps,
                    gs.sampler, gs.scheduler, gs.width, gs.height,
                    gs.positive_prompt_template, gs.negative_prompt_template
                FROM characters c
                JOIN projects p ON c.project_id = p.id
                LEFT JOIN generation_styles gs ON gs.style_name = (
                    SELECT style_name FROM generation_styles
                    WHERE style_name = LOWER(REPLACE(p.name, ' ', '_'))
                    LIMIT 1
                )
                WHERE c.lora_path IS NOT NULL AND c.lora_path != ''
                  AND p.status != 'paused'
                ORDER BY p.id, c.name
            """)
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    return await _cached("characters", _load)


async def get_all_scenes() -> list[dict]:
    async def _load():
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT s.id, s.title, s.description, s.location, s.time_of_day,
                       s.weather, s.mood, p.name AS project_name, p.id AS project_id
                FROM scenes s JOIN projects p ON s.project_id = p.id
                WHERE p.status != 'paused' AND s.description IS NOT NULL AND LENGTH(s.description) > 30
            """)
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    return await _cached("scenes", _load)


async def get_world_settings() -> list[dict]:
    async def _load():
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT w.project_id, w.style_preamble, w.art_style, w.aesthetic,
                       w.color_palette, w.cinematography, w.world_location, w.time_period,
                       w.negative_prompt_guidance, p.name AS project_name
                FROM world_settings w JOIN projects p ON w.project_id = p.id
                WHERE p.status != 'paused'
            """)
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    return await _cached("worlds", _load)


async def get_generation_styles() -> list[dict]:
    async def _load():
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT style_name, checkpoint_model, cfg_scale, steps,
                       sampler, scheduler, width, height,
                       positive_prompt_template, negative_prompt_template
                FROM generation_styles
            """)
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    return await _cached("styles", _load)


async def get_pending_shots() -> list[dict]:
    async def _load():
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT sh.id, sh.generation_prompt, sh.motion_prompt, sh.shot_type,
                       sh.camera_angle, sh.characters_present, sh.video_engine, sh.lora_name, sh.status,
                       s.location, s.mood, s.time_of_day,
                       p.name AS project_name, p.id AS project_id
                FROM shots sh JOIN scenes s ON sh.scene_id = s.id JOIN projects p ON s.project_id = p.id
                WHERE sh.generation_prompt IS NOT NULL AND LENGTH(sh.generation_prompt) > 20
                  AND sh.status IN ('pending', 'failed') AND sh.source_image_path IS NULL
                  AND p.status != 'paused'
                LIMIT 100
            """)
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    return await _cached("pending_shots", _load)


async def get_storylines() -> list[dict]:
    async def _load():
        conn = await connect_direct()
        try:
            rows = await conn.fetch("""
                SELECT sl.project_id, sl.title, sl.theme, sl.genre, sl.tone,
                       sl.humor_style, sl.themes, p.name AS project_name
                FROM storylines sl JOIN projects p ON sl.project_id = p.id
                WHERE p.status != 'paused'
            """)
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    return await _cached("storylines", _load)


# ═══════════════════════════════════════════════════════════════
# IDEA STRATEGIES
# ═══════════════════════════════════════════════════════════════

async def get_character_learning_score(slug: str) -> float:
    approval_file = BASE_PATH / slug / "approval_status.json"
    approved = pending = 0
    if approval_file.exists():
        try:
            statuses = json.loads(approval_file.read_text())
            for v in statuses.values():
                if v == "approved" or (isinstance(v, dict) and v.get("status") == "approved"):
                    approved += 1
                elif v == "pending":
                    pending += 1
        except (json.JSONDecodeError, IOError):
            pass

    score = max(0, 100 - approved) / 100.0
    score -= min(pending * 0.1, 0.5)

    feedback_file = BASE_PATH / slug / "feedback.json"
    if feedback_file.exists():
        try:
            fb = json.loads(feedback_file.read_text())
            if fb.get("rejection_count", 0) > 0:
                score += min(fb["rejection_count"] * 0.02, 0.3)
        except (json.JSONDecodeError, IOError):
            pass

    score -= min(_characters_seen.get(slug, 0) * 0.05, 0.4)
    return max(0.0, score)


def pick_character(characters: list[dict], scores: dict[str, float]) -> dict | None:
    if not characters:
        return None
    weights = [max(scores.get(c["slug"], 0.5), 0.05) for c in characters]
    return random.choices(characters, weights=weights, k=1)[0]


def should_try_alt_checkpoint(templates: dict) -> str | None:
    exp = templates.get("checkpoint_experiments", {})
    if not exp.get("enabled", False):
        return None
    if random.random() > exp.get("probability", 0.15):
        return None
    alts = exp.get("alternatives", [])
    return random.choice(alts) if alts else None


async def strategy_character_keyframe(templates: dict, seed: dict | None) -> dict | None:
    characters = await get_eligible_characters()
    if not characters:
        return None

    scores = {}
    for c in characters:
        scores[c["slug"]] = await get_character_learning_score(c["slug"])
    char = pick_character(characters, scores)
    if not char:
        return None

    # Build prompt — inject narrative seed if present
    composition = random.choice(templates["compositions"])
    lighting = random.choice(templates["lighting"])

    if seed and seed.get("prompt_fragment"):
        mood_part = seed["prompt_fragment"]
    else:
        mood_part = random.choice(templates["moods"])

    setting = random.choice(templates["settings"])
    idea_prompt = f"{composition}, {lighting}, {mood_part}, {setting}"

    checkpoint_override = should_try_alt_checkpoint(templates)
    if checkpoint_override and checkpoint_override == char.get("checkpoint_model"):
        checkpoint_override = None

    combo = compute_combo_hash("character_keyframe", char["slug"],
                                seed["name"] if seed else "")

    return {
        "strategy": "character_keyframe",
        "character": char,
        "custom_pose": idea_prompt,
        "checkpoint_override": checkpoint_override,
        "combo_hash": combo,
        "narrative_seed_name": seed["name"] if seed else None,
        "description": f"{char['slug']} — {composition}" + (f" [{seed['name']}]" if seed else ""),
    }


async def strategy_scene_remix(templates: dict, seed: dict | None) -> dict | None:
    characters = await get_eligible_characters()
    scenes = await get_all_scenes()
    if not characters or not scenes:
        return None

    scene = random.choice(scenes)

    # Use character relationships if available
    other_chars = [c for c in characters if c["project_id"] != scene["project_id"]]
    if not other_chars:
        other_chars = characters
    char = random.choice(other_chars)

    # Try dramatic pairing to pick a better character
    partner = pick_dramatic_pairing(char["slug"], other_chars, templates)
    if partner:
        char = partner  # Use the dramatically interesting partner instead

    parts = []
    if scene.get("location"):
        parts.append(scene["location"])
    if scene.get("time_of_day"):
        parts.append(scene["time_of_day"])
    if scene.get("mood"):
        parts.append(scene["mood"])
    if seed and seed.get("prompt_fragment"):
        parts.append(seed["prompt_fragment"])
    if not parts:
        parts.append(scene.get("description", "")[:100])

    composition = random.choice(templates["compositions"])
    lighting = random.choice(templates["lighting"])
    scene_prompt = ", ".join(parts)

    combo = compute_combo_hash("scene_remix", char["slug"], scene["title"])

    return {
        "strategy": "scene_remix",
        "character": char,
        "custom_pose": f"{composition}, {scene_prompt}, {lighting}",
        "checkpoint_override": None,
        "combo_hash": combo,
        "source_project": scene["project_name"],
        "target_project": char["project_name"],
        "narrative_seed_name": seed["name"] if seed else None,
        "description": f"{char['slug']} in '{scene['title']}' from {scene['project_name']}"
                       + (f" [{seed['name']}]" if seed else ""),
    }


async def strategy_world_crossover(templates: dict, seed: dict | None) -> dict | None:
    characters = await get_eligible_characters()
    worlds = await get_world_settings()
    if not characters or not worlds:
        return None

    world = random.choice(worlds)
    other_chars = [c for c in characters if c["project_id"] != world["project_id"]]
    if not other_chars:
        other_chars = characters
    char = random.choice(other_chars)

    parts = []
    if world.get("art_style"):
        parts.append(world["art_style"])
    if world.get("aesthetic"):
        parts.append(world["aesthetic"])

    palette = world.get("color_palette")
    if palette:
        if isinstance(palette, str):
            try:
                palette = json.loads(palette)
            except (json.JSONDecodeError, TypeError):
                palette = None
        if isinstance(palette, dict):
            colors = []
            for v in palette.values():
                if isinstance(v, str):
                    colors.append(v)
                elif isinstance(v, list):
                    colors.extend(v[:2])
            if colors:
                parts.append(", ".join(colors[:3]))

    location = world.get("world_location")
    if location:
        if isinstance(location, str):
            try:
                location = json.loads(location)
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(location, dict):
            setting = location.get("setting") or location.get("primary", "")
            if setting:
                parts.append(setting)
        elif isinstance(location, str):
            parts.append(location[:80])

    # Inject narrative seed (especially art movements work great here)
    if seed and seed.get("prompt_fragment"):
        parts.append(seed["prompt_fragment"])

    if not parts:
        return None

    composition = random.choice(templates["compositions"])
    combo = compute_combo_hash("world_crossover", char["slug"], world["project_name"])

    return {
        "strategy": "world_crossover",
        "character": char,
        "custom_pose": f"{composition}, {', '.join(parts[:5])}",
        "checkpoint_override": None,
        "combo_hash": combo,
        "source_project": world["project_name"],
        "target_project": char["project_name"],
        "narrative_seed_name": seed["name"] if seed else None,
        "description": f"{char['slug']} in {world['project_name']} world"
                       + (f" [{seed['name']}]" if seed else ""),
    }


async def strategy_checkpoint_shootout(templates: dict, seed: dict | None) -> dict | None:
    characters = await get_eligible_characters()
    styles = await get_generation_styles()
    if not characters or not styles:
        return None

    char = random.choice(characters)
    alt_styles = [s for s in styles if s["checkpoint_model"] and s["checkpoint_model"] != char.get("checkpoint_model")]
    if not alt_styles:
        return None
    alt = random.choice(alt_styles)

    composition = random.choice(templates["compositions"])
    lighting = random.choice(templates["lighting"])
    combo = compute_combo_hash("checkpoint_shootout", char["slug"], alt["checkpoint_model"])

    return {
        "strategy": "checkpoint_shootout",
        "character": char,
        "custom_pose": f"{composition}, {lighting}",
        "checkpoint_override": alt["checkpoint_model"],
        "combo_hash": combo,
        "narrative_seed_name": None,
        "description": f"{char['slug']} shootout: {alt['checkpoint_model'][:30]}",
    }


async def strategy_motion_preview(templates: dict, seed: dict | None) -> dict | None:
    shots = await get_pending_shots()
    characters = await get_eligible_characters()
    if not shots or not characters:
        return None

    shot = random.choice(shots)
    char = None
    if shot.get("characters_present"):
        for c in characters:
            if c["slug"] in shot["characters_present"]:
                char = c
                break
    if not char:
        project_chars = [c for c in characters if c["project_id"] == shot["project_id"]]
        char = random.choice(project_chars) if project_chars else None
    if not char:
        return None

    gen_prompt = shot.get("generation_prompt", "")[:300]
    combo = compute_combo_hash("motion_preview", char["slug"], str(shot["id"])[:8])

    return {
        "strategy": "motion_preview",
        "character": char,
        "custom_pose": gen_prompt,
        "checkpoint_override": None,
        "prompt_override": gen_prompt,
        "combo_hash": combo,
        "narrative_seed_name": None,
        "description": f"Motion preview: {char['slug']} in {shot['project_name']}",
    }


async def strategy_style_transfer(templates: dict, seed: dict | None) -> dict | None:
    characters = await get_eligible_characters()
    worlds = await get_world_settings()
    if not characters or not worlds:
        return None

    styled_worlds = [w for w in worlds if w.get("style_preamble") and len(w["style_preamble"]) > 10]
    if not styled_worlds:
        return None

    world = random.choice(styled_worlds)
    other_chars = [c for c in characters if c["project_id"] != world["project_id"]]
    if not other_chars:
        other_chars = characters
    char = random.choice(other_chars)

    composition = random.choice(templates["compositions"])
    mood = seed["prompt_fragment"] if seed else random.choice(templates["moods"])
    combo = compute_combo_hash("style_transfer", char["slug"], world["project_name"])

    return {
        "strategy": "style_transfer",
        "character": char,
        "custom_pose": f"{world['style_preamble']}, {composition}, {mood}",
        "checkpoint_override": None,
        "combo_hash": combo,
        "source_project": world["project_name"],
        "target_project": char["project_name"],
        "narrative_seed_name": seed["name"] if seed else None,
        "description": f"{char['slug']} with {world['project_name']} style"
                       + (f" [{seed['name']}]" if seed else ""),
    }


async def strategy_storyline_moment(templates: dict, seed: dict | None) -> dict | None:
    characters = await get_eligible_characters()
    storylines = await get_storylines()
    if not characters or not storylines:
        return None

    story = random.choice(storylines)
    char = random.choice(characters)

    parts = []
    if story.get("theme"):
        parts.append(story["theme"])
    if story.get("tone"):
        parts.append(story["tone"])
    if story.get("themes") and isinstance(story["themes"], list):
        parts.extend(random.sample(story["themes"], min(2, len(story["themes"]))))
    if seed and seed.get("prompt_fragment"):
        parts.append(seed["prompt_fragment"])
    if not parts:
        return None

    composition = random.choice(templates["compositions"])
    lighting = random.choice(templates["lighting"])
    combo = compute_combo_hash("storyline_moment", char["slug"], story.get("title", ""))

    return {
        "strategy": "storyline_moment",
        "character": char,
        "custom_pose": f"{composition}, {lighting}, {', '.join(parts[:4])}",
        "checkpoint_override": None,
        "combo_hash": combo,
        "source_project": story["project_name"],
        "target_project": char["project_name"],
        "narrative_seed_name": seed["name"] if seed else None,
        "description": f"{char['slug']} in '{story.get('title', '?')}' mood"
                       + (f" [{seed['name']}]" if seed else ""),
    }


async def strategy_shot_gap_fill(templates: dict, seed: dict | None) -> dict | None:
    shots = await get_pending_shots()
    characters = await get_eligible_characters()
    if not shots or not characters:
        return None

    failed = [s for s in shots if s["status"] == "failed"]
    shot = random.choice(failed) if failed else random.choice(shots)

    char = None
    if shot.get("characters_present"):
        for c in characters:
            if c["slug"] in shot["characters_present"]:
                char = c
                break
    if not char:
        project_chars = [c for c in characters if c["project_id"] == shot["project_id"]]
        char = random.choice(project_chars) if project_chars else None
    if not char:
        return None

    gen_prompt = shot.get("generation_prompt", "")
    if not gen_prompt:
        return None

    combo = compute_combo_hash("shot_gap_fill", char["slug"], str(shot["id"])[:8])

    return {
        "strategy": "shot_gap_fill",
        "character": char,
        "custom_pose": gen_prompt[:300],
        "prompt_override": gen_prompt,
        "checkpoint_override": None,
        "combo_hash": combo,
        "narrative_seed_name": None,
        "description": f"Gap fill: {char['slug']} in {shot['project_name']} ({shot['status']})",
    }


# ═══════════════════════════════════════════════════════════════
# STRATEGY DISPATCHER (with all 4 intelligence layers)
# ═══════════════════════════════════════════════════════════════

STRATEGIES = {
    "character_keyframe": strategy_character_keyframe,
    "scene_remix": strategy_scene_remix,
    "world_crossover": strategy_world_crossover,
    "checkpoint_shootout": strategy_checkpoint_shootout,
    "motion_preview": strategy_motion_preview,
    "style_transfer": strategy_style_transfer,
    "storyline_moment": strategy_storyline_moment,
    "shot_gap_fill": strategy_shot_gap_fill,
}


def pick_strategy(allowed: str = "all") -> str:
    """Weighted random strategy selection, modified by feedback learning."""
    if allowed != "all" and allowed in STRATEGIES:
        return allowed

    names = list(STRATEGY_WEIGHTS.keys())
    # Apply feedback modifiers
    weights = [
        STRATEGY_WEIGHTS[n] * _feedback_scores.get(n, 1.0)
        for n in names
    ]
    return random.choices(names, weights=weights, k=1)[0]


async def generate_idea_with_intelligence(
    templates: dict, allowed_strategy: str = "all"
) -> dict | None:
    """Full pipeline: narrative seed → strategy → temporal drift check → execute.

    Retries up to 3 times if temporal drift rejects the combo.
    """
    # Layer 1: Select narrative seed
    seed = select_narrative_seed(templates)
    if seed:
        logger.info(f"Narrative seed: [{seed['category']}] {seed['name']}")

    for attempt in range(3):
        # Pick strategy (Layer 4: feedback-weighted)
        strategy_name = pick_strategy(allowed_strategy)
        func = STRATEGIES.get(strategy_name)
        if not func:
            continue

        # Execute strategy (Layer 3: relationships used inside strategies)
        try:
            idea = await func(templates, seed)
        except Exception as e:
            logger.error(f"Strategy {strategy_name} error: {e}", exc_info=True)
            continue

        if not idea:
            continue

        # Layer 2: Temporal drift check
        combo_hash = idea.get("combo_hash", "")
        penalty = temporal_drift_penalty(combo_hash)
        if penalty > 0.5 and attempt < 2:
            logger.debug(f"Temporal drift rejecting {strategy_name} combo (penalty={penalty:.1f}), retrying")
            continue  # Try a different strategy

        idea["temporal_penalty"] = penalty
        return idea

    return None


# ═══════════════════════════════════════════════════════════════
# VISION REVIEW + GENERATION
# ═══════════════════════════════════════════════════════════════

async def trigger_vision_review(slug: str, project_name: str) -> dict:
    try:
        from packages.visual_pipeline.visual_review import vision_review, _vision_tasks
        from packages.core.models import VisionReviewRequest

        request = VisionReviewRequest(
            character_slug=slug, max_images=5,
            auto_reject_threshold=0.3, auto_approve_threshold=0.85,
            regenerate=False, update_captions=True,
        )
        result = await vision_review(request)
        task_id = result.get("task_id")
        if not task_id:
            return {"approved": 0, "rejected": 0, "reviewed": 0}

        waited = 0
        while waited < VISION_REVIEW_TIMEOUT:
            task_info = _vision_tasks.get(task_id, {})
            if task_info.get("status") != "running":
                break
            await asyncio.sleep(3)
            waited += 3

        task_info = _vision_tasks.get(task_id, {})
        return {
            "approved": task_info.get("auto_approved", 0),
            "rejected": task_info.get("auto_rejected", 0),
            "reviewed": task_info.get("reviewed", 0),
        }
    except Exception as e:
        if "409" in str(e) or "already running" in str(e).lower():
            logger.info(f"Vision review busy, skipping {slug}")
        else:
            logger.error(f"Vision review failed for {slug}: {e}")
        return {"approved": 0, "rejected": 0, "reviewed": 0}


async def generate_idea(idea: dict, dry_run: bool = False) -> dict:
    global _generation_count

    char = idea["character"]
    slug = char["slug"]
    strategy = idea["strategy"]

    seed_tag = f" [{idea['narrative_seed_name']}]" if idea.get("narrative_seed_name") else ""
    drift_tag = f" (drift={idea.get('temporal_penalty', 0):.1f})" if idea.get("temporal_penalty", 0) > 0 else ""

    if dry_run:
        logger.info(f"[DRY RUN] [{strategy}]{seed_tag}{drift_tag} {idea['description']}")
        logger.info(f"  prompt: {idea.get('custom_pose', idea.get('prompt_override', ''))[:120]}")
        return {"status": "dry_run", "slug": slug, "strategy": strategy}

    logger.info(f"[{strategy}]{seed_tag}{drift_tag} {idea['description']}")

    prompt_override = idea.get("prompt_override")
    custom_poses = [idea["custom_pose"]] if not prompt_override else None

    # Smart GPU routing: use whichever GPU is least busy
    _idea_gpu_url = None
    try:
        from packages.core.dual_gpu import get_best_gpu_for_task
        _idea_gpu_url = get_best_gpu_for_task("keyframe")
    except ImportError:
        pass

    results = await generate_batch(
        character_slug=slug, count=1,
        prompt_override=prompt_override,
        pose_variation=False,
        include_feedback_negatives=True,
        include_learned_negatives=True,
        fire_events=True,
        checkpoint_override=idea.get("checkpoint_override"),
        custom_poses=custom_poses,
        source="idea_factory",
        comfyui_url=_idea_gpu_url,
    )

    _generation_count += 1
    _characters_seen[slug] = _characters_seen.get(slug, 0) + 1
    _strategy_counts[strategy] = _strategy_counts.get(strategy, 0) + 1
    _session_combos.add(idea.get("combo_hash", ""))

    if not results or results[0].get("status") != "completed":
        return {"status": "failed", "slug": slug, "strategy": strategy}

    gen_id = results[0].get("gen_id")

    # Log to idea_factory_log for temporal drift + feedback learning
    await log_idea(idea, gen_id)

    await log_decision(
        decision_type="idea_factory",
        character_slug=slug,
        project_name=char["project_name"],
        input_context={
            "strategy": strategy,
            "description": idea["description"],
            "narrative_seed": idea.get("narrative_seed_name"),
            "combo_hash": idea.get("combo_hash"),
            "temporal_penalty": idea.get("temporal_penalty", 0),
        },
        decision_made=f"idea_{strategy}",
        confidence_score=0.8,
        reasoning=idea["description"],
    )

    return {
        "status": "completed", "slug": slug, "strategy": strategy,
        "project_name": char["project_name"],
        "prompt_id": results[0].get("prompt_id"),
        "images": results[0].get("images", []),
    }


# ═══════════════════════════════════════════════════════════════
# DAEMON LOOP
# ═══════════════════════════════════════════════════════════════

async def run_daemon(interval: int, dry_run: bool = False, allowed_strategy: str = "all"):
    global _consecutive_errors

    logger.info("=" * 60)
    logger.info("Idea Factory v3 — Creative Intelligence Engine")
    logger.info(f"  Interval: {interval}s | Dry run: {dry_run}")
    logger.info(f"  Strategy: {allowed_strategy}")
    logger.info(f"  Layers: narrative_pressure, temporal_drift, character_relations, feedback_learning")
    logger.info("=" * 60)

    templates = load_templates()
    seeds = templates.get("narrative_seeds", {})
    seed_counts = {k: len(v) for k, v in seeds.items() if isinstance(v, list)}
    logger.info(f"Narrative seeds: {seed_counts}")
    rels = get_relationship_pairings(templates)
    logger.info(f"Character relationships: {len(rels)} configured pairings")

    await get_pool()

    # Initial load of intelligence layers
    await load_historical_combos()
    await load_feedback_scores()

    tick = 0
    while True:
        try:
            # Dual-GPU guard: if 3060 is in video mode, don't submit keyframes
            try:
                from packages.core.dual_gpu import is_dual_video_enabled, get_3060_mode, GpuMode
                if is_dual_video_enabled() and get_3060_mode() != GpuMode.KEYFRAME:
                    logger.info(f"3060 in {get_3060_mode().value} mode (dual-GPU video), backing off...")
                    await asyncio.sleep(BACKOFF_BUSY)
                    continue
            except ImportError:
                pass

            if check_comfyui_busy():
                logger.info("ComfyUI busy, backing off...")
                await asyncio.sleep(BACKOFF_BUSY)
                continue

            # Refresh intelligence layers periodically
            if tick % 4 == 0:  # Every ~10 minutes
                await load_historical_combos()
                await load_feedback_scores()
                await sync_idea_approvals()
                # Reload templates (live config changes)
                templates = load_templates()

            idea = await generate_idea_with_intelligence(templates, allowed_strategy)

            if not idea:
                logger.debug("No idea generated this tick")
                await asyncio.sleep(10)
                continue

            result = await generate_idea(idea, dry_run=dry_run)

            if result.get("status") == "completed":
                _consecutive_errors = 0
                slug = result["slug"]
                review = await trigger_vision_review(slug, result.get("project_name", ""))
                _last_review_results[slug] = review

                logger.info(
                    f"#{_generation_count} [{result['strategy']}] {slug}: "
                    f"{len(result.get('images', []))} img, "
                    f"{review.get('approved', 0)}A/{review.get('rejected', 0)}R"
                )
            elif result.get("status") != "dry_run":
                _consecutive_errors += 1
                if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"{MAX_CONSECUTIVE_ERRORS} errors, extended pause")
                    await asyncio.sleep(BACKOFF_ERROR * 5)
                    _consecutive_errors = 0

            tick += 1
            await asyncio.sleep(interval)

        except KeyboardInterrupt:
            break
        except Exception as e:
            _consecutive_errors += 1
            logger.error(f"Tick error: {e}", exc_info=True)
            if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                await asyncio.sleep(BACKOFF_ERROR * 5)
                _consecutive_errors = 0
            else:
                await asyncio.sleep(BACKOFF_ERROR)


def print_status():
    logger.info("Session stats:")
    logger.info(f"  Total: {_generation_count} | Combos explored: {len(_session_combos)}")
    logger.info(f"  Strategies:")
    for s, c in sorted(_strategy_counts.items(), key=lambda x: -x[1]):
        fb = _feedback_scores.get(s, 1.0)
        logger.info(f"    {s}: {c}x (feedback modifier: {fb:.2f})")
    logger.info(f"  Characters ({len(_characters_seen)}):")
    for slug, count in sorted(_characters_seen.items(), key=lambda x: -x[1])[:15]:
        r = _last_review_results.get(slug, {})
        logger.info(f"    {slug}: {count}x, {r.get('approved', '?')}A/{r.get('rejected', '?')}R")


def main():
    parser = argparse.ArgumentParser(description="Idea Factory v3 — Creative Intelligence Engine")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strategy", default="all",
                        choices=["all"] + list(STRATEGIES.keys()))
    args = parser.parse_args()

    try:
        asyncio.run(run_daemon(interval=args.interval, dry_run=args.dry_run,
                               allowed_strategy=args.strategy))
    except KeyboardInterrupt:
        pass
    finally:
        print_status()


if __name__ == "__main__":
    main()
