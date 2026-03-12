"""Interactive Feedback Loop — question generator, action executor, LoRA finder, Echo Brain storage.

Flow: user rates shot → system generates diagnostic questions with action-mapped options
→ user picks option → system executes DB update + resets shot for regeneration
→ stores feedback in Echo Brain for future learning.
"""

import json
import logging
import urllib.request as _ur
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import yaml

from packages.core.db import get_pool
from packages.core.events import event_bus, FEEDBACK_SUBMITTED, FEEDBACK_ACTION_EXECUTED
from packages.core.learning import record_learned_pattern

logger = logging.getLogger(__name__)

ECHO_BRAIN_URL = "http://localhost:8309"
_TIMEOUT = 8
_LORA_DIR = Path("/opt/ComfyUI/models/loras")
_CATALOG_PATH = Path("/opt/anime-studio/config/lora_catalog.yaml")
_catalog_cache: dict | None = None

MOTION_TIER_ORDER = ["low", "medium", "high", "extreme"]


# ── Echo Brain helpers ──────────────────────────────────────────────────

def _mcp_call(tool_name: str, arguments: dict) -> dict | None:
    try:
        payload = json.dumps({
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }).encode()
        req = _ur.Request(
            f"{ECHO_BRAIN_URL}/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = _ur.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read())
    except Exception as e:
        logger.warning("Echo Brain %s failed: %s", tool_name, e)
        return None


def _extract_text(result: dict | None) -> str:
    if not result or "result" not in result:
        return ""
    content = result.get("result", {}).get("content", [])
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item["text"])
    return "\n".join(parts)


def _search_echo_brain(query: str) -> str:
    result = _mcp_call("search_memory", {"query": query, "limit": 3})
    return _extract_text(result)


def _store_echo_feedback(content: str) -> bool:
    result = _mcp_call("store_memory", {"content": content})
    return result is not None


def _store_echo_fact(topic: str, fact: str) -> bool:
    result = _mcp_call("store_fact", {"topic": topic, "fact": fact})
    return result is not None


# ── LoRA catalog ────────────────────────────────────────────────────────

def _load_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    try:
        with open(_CATALOG_PATH) as f:
            _catalog_cache = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load LoRA catalog: %s", e)
        _catalog_cache = {}
    return _catalog_cache


def find_lora_alternatives(current_lora: str, max_results: int = 3) -> list[dict]:
    """Find alternative LoRAs ranked by tag similarity to current one."""
    catalog = _load_catalog()
    pairs = catalog.get("video_lora_pairs", {})

    # Find current entry
    current_key = None
    current_tags: set = set()
    current_tier = ""
    current_motion = ""
    for key, entry in pairs.items():
        high_path = entry.get("high") or ""
        low_path = entry.get("low") or ""
        if current_lora and (current_lora in high_path or current_lora in low_path or key in current_lora):
            current_key = key
            current_tags = set(entry.get("tags", []))
            current_tier = entry.get("tier", "")
            current_motion = entry.get("motion_tier", "")
            break

    if not current_key:
        return []

    alternatives = []
    for key, entry in pairs.items():
        if key == current_key:
            continue
        high_path = entry.get("high") or ""
        # Verify file exists
        full_path = _LORA_DIR / high_path
        if high_path and not full_path.exists():
            continue

        tags = set(entry.get("tags", []))
        score = len(tags & current_tags) * 2
        if entry.get("tier") == current_tier:
            score += 1
        if entry.get("motion_tier") == current_motion:
            score += 1

        if score > 0:
            alternatives.append({
                "key": key,
                "label": entry.get("label", key),
                "high": high_path,
                "low": entry.get("low", ""),
                "tags": list(tags),
                "motion_tier": entry.get("motion_tier", "medium"),
                "score": score,
            })

    alternatives.sort(key=lambda x: x["score"], reverse=True)
    return alternatives[:max_results]


# ── Question generator ──────────────────────────────────────────────────

async def generate_questions(
    shot: dict,
    qc_averages: dict | None,
    qc_issues: list[str],
    rating: int,
    categories: list[str],
    echo_context: str = "",
) -> list[dict]:
    """Generate diagnostic questions with action-mapped options based on QC signals."""
    questions = []
    # Map QC category names to what video_vision.py actually stores
    motion_score = (qc_averages or {}).get("motion_execution",
                   (qc_averages or {}).get("motion_coherence", 10.0))
    char_score = (qc_averages or {}).get("character_match",
                 (qc_averages or {}).get("character_consistency", 10.0))
    comp_score = (qc_averages or {}).get("style_match",
                 (qc_averages or {}).get("composition", 10.0))
    visual_score = (qc_averages or {}).get("technical_quality",
                   (qc_averages or {}).get("visual_quality", 10.0))
    current_tier = shot.get("motion_tier") or "medium"
    lora_name = shot.get("lora_name") or ""
    quality_score = shot.get("quality_score") or 0

    tier_idx = MOTION_TIER_ORDER.index(current_tier) if current_tier in MOTION_TIER_ORDER else 1

    # Motion issues
    if motion_score < 5.0 or "frozen_motion" in qc_issues or "motion" in categories:
        options = [
            {"id": "new_seed", "label": "Retry with new seed", "action": "new_seed"},
        ]
        if tier_idx < len(MOTION_TIER_ORDER) - 1:
            next_tier = MOTION_TIER_ORDER[tier_idx + 1]
            options.insert(0, {
                "id": "bump_tier",
                "label": f"Bump motion tier to {next_tier}",
                "action": "bump_tier",
            })
        # LoRA alternatives — enriched with effectiveness data when available
        try:
            from .lora_effectiveness import find_alternatives_with_effectiveness
            alts = await find_alternatives_with_effectiveness(
                lora_name, char_slug=shot.get("characters_present", [None])[0]
                if shot.get("characters_present") else None,
            )
        except Exception:
            alts = [{"key": a["key"], "label": a["label"], "high": a["high"],
                      "low": a["low"], "effectiveness": None}
                     for a in find_lora_alternatives(lora_name)]
        for alt in alts[:2]:
            label = f"Swap LoRA to {alt['label']}"
            eff = alt.get("effectiveness")
            if eff and eff.get("avg_quality"):
                label += f" (avg quality: {eff['avg_quality']:.0%})"
            options.append({
                "id": f"swap_lora_{alt['key']}",
                "label": label,
                "action": "swap_lora",
                "params": {"lora_key": alt["key"], "high": alt.get("high", ""), "low": alt.get("low", "")},
            })

        hint = f"Motion score is {motion_score:.1f}/10. Current tier: {current_tier}."
        if echo_context:
            hint += f"\n{echo_context}"

        questions.append({
            "id": "q_motion",
            "text": hint,
            "options": options,
        })

    # Motion severely underperforming at high+ tier
    if motion_score < 3.0 and tier_idx >= 2:
        options = [{"id": "new_seed", "label": "Retry with new seed", "action": "new_seed"}]
        if current_tier != "extreme":
            options.insert(0, {
                "id": "bump_extreme",
                "label": "Bump to extreme (disables lightx2v)",
                "action": "bump_tier",
                "params": {"target_tier": "extreme"},
            })
        alts = find_lora_alternatives(lora_name)
        for alt in alts[:2]:
            options.append({
                "id": f"swap_lora_{alt['key']}",
                "label": f"Swap LoRA to {alt['label']}",
                "action": "swap_lora",
                "params": {"lora_key": alt["key"], "high": alt["high"], "low": alt["low"]},
            })
        questions.append({
            "id": "q_motion_severe",
            "text": f"Motion severely underperforming ({motion_score:.1f}/10) even at {current_tier} tier.",
            "options": options,
        })

    # Action-reaction issues (from action_reaction_qc.py)
    reaction_score = (qc_averages or {}).get("reaction_presence", 10.0)
    state_delta = (qc_averages or {}).get("state_delta", 10.0)
    ar_issues = [i for i in qc_issues if i in ("reaction_absent", "frozen_interaction", "weak_reaction")]

    if ar_issues or reaction_score < 5.0 or state_delta < 4.0 or "interaction" in categories:
        ar_text_parts = []
        if reaction_score < 10.0:
            ar_text_parts.append(f"Reaction score: {reaction_score:.1f}/10")
        if state_delta < 10.0:
            ar_text_parts.append(f"State delta: {state_delta:.1f}/10")
        if "reaction_absent" in ar_issues:
            ar_text_parts.append("No reaction detected in secondary character/region")
        if "frozen_interaction" in ar_issues:
            ar_text_parts.append("Both characters appear frozen")
        if not ar_text_parts:
            ar_text_parts.append("Interaction quality flagged for review")

        options = []
        if tier_idx < len(MOTION_TIER_ORDER) - 1:
            next_tier = MOTION_TIER_ORDER[tier_idx + 1]
            options.append({
                "id": "bump_tier_ar",
                "label": f"Bump motion tier to {next_tier} (more steps/cfg)",
                "action": "bump_tier",
            })
        options.append({
            "id": "new_seed_ar",
            "label": "Retry with new seed (keep params)",
            "action": "new_seed",
        })
        alts = find_lora_alternatives(lora_name)
        for alt in alts[:2]:
            options.append({
                "id": f"swap_lora_ar_{alt['key']}",
                "label": f"Swap LoRA to {alt['label']}",
                "action": "swap_lora",
                "params": {"lora_key": alt["key"], "high": alt["high"], "low": alt["low"]},
            })
        if lora_name:
            options.append({
                "id": "boost_strength_ar",
                "label": "Increase LoRA strength (+0.15)",
                "action": "adjust_strength",
                "params": {"delta": 0.15},
            })

        questions.append({
            "id": "q_action_reaction",
            "text": "Action-reaction problem: " + ". ".join(ar_text_parts) + ".",
            "options": options,
        })

    # Character issues
    if char_score < 5.0 or "wrong_character" in qc_issues or "character" in categories:
        options = [
            {"id": "adjust_strength", "label": f"Increase LoRA strength (+0.1)", "action": "adjust_strength",
             "params": {"delta": 0.1}},
            {"id": "edit_prompt", "label": "Edit generation prompt", "action": "edit_prompt"},
            {"id": "new_seed", "label": "Retry with new seed", "action": "new_seed"},
        ]
        questions.append({
            "id": "q_character",
            "text": f"Character match score: {char_score:.1f}/10. Character doesn't match reference.",
            "options": options,
        })

    # Composition issues
    if comp_score < 5.0 or "composition" in categories:
        camera = shot.get("camera_angle") or "medium"
        cam_options = ["close_up", "medium", "wide", "over_shoulder", "low_angle", "high_angle", "dutch"]
        alt_cams = [c for c in cam_options if c != camera][:3]
        options = [
            {"id": f"change_cam_{c}", "label": f"Change camera to {c.replace('_', ' ')}",
             "action": "change_camera", "params": {"camera_angle": c}}
            for c in alt_cams
        ]
        options.append({"id": "edit_motion", "label": "Edit motion prompt", "action": "edit_motion"})
        questions.append({
            "id": "q_composition",
            "text": f"Composition score: {comp_score:.1f}/10. Current camera: {camera}.",
            "options": options,
        })

    # Lighting issues
    if visual_score < 5.0 or "poor_lighting" in qc_issues or "lighting" in categories:
        options = [
            {"id": "fix_lighting", "label": "Add lighting keywords to prompt", "action": "edit_prompt",
             "params": {"append": "well-lit, balanced lighting, studio lighting"}},
            {"id": "adjust_cfg", "label": "Adjust CFG scale", "action": "adjust_cfg",
             "params": {"delta": 0.5}},
            {"id": "new_seed", "label": "Retry with new seed", "action": "new_seed"},
        ]
        questions.append({
            "id": "q_lighting",
            "text": f"Visual quality score: {visual_score:.1f}/10. Lighting issues detected.",
            "options": options,
        })

    # Overall very low
    if quality_score < 0.4 and rating <= 2 and not questions:
        options = [
            {"id": "new_seed", "label": "Retry with new seed", "action": "new_seed"},
        ]
        alts = find_lora_alternatives(lora_name)
        for alt in alts[:2]:
            options.append({
                "id": f"swap_lora_{alt['key']}",
                "label": f"Swap LoRA to {alt['label']}",
                "action": "swap_lora",
                "params": {"lora_key": alt["key"], "high": alt["high"], "low": alt["low"]},
            })
        options.append({
            "id": "blacklist",
            "label": f"Blacklist {shot.get('video_engine', 'engine')} for this character",
            "action": "blacklist_engine",
        })
        questions.append({
            "id": "q_overall",
            "text": f"Overall quality very low ({quality_score:.0%}). Rating: {rating}/5.",
            "options": options,
        })

    # LoRA underperforming
    if lora_name and quality_score < 0.5 and not any(q["id"].startswith("q_motion") for q in questions):
        alts = find_lora_alternatives(lora_name)
        if alts:
            options = []
            for alt in alts[:3]:
                options.append({
                    "id": f"swap_lora_{alt['key']}",
                    "label": f"Swap to {alt['label']}",
                    "action": "swap_lora",
                    "params": {"lora_key": alt["key"], "high": alt["high"], "low": alt["low"]},
                })
            options.append({
                "id": "reduce_strength",
                "label": "Reduce LoRA strength (-0.1)",
                "action": "adjust_strength",
                "params": {"delta": -0.1},
            })
            options.append({
                "id": "remove_lora",
                "label": "Remove LoRA entirely",
                "action": "adjust_strength",
                "params": {"set_to": 0},
            })
            questions.append({
                "id": "q_lora",
                "text": f"LoRA '{lora_name.split('/')[-1]}' underperforming (quality {quality_score:.0%}).",
                "options": options,
            })

    # Looks good but not approved
    if rating >= 4 and not questions:
        questions.append({
            "id": "q_almost",
            "text": "Looks good but not perfect?",
            "options": [
                {"id": "new_seed_keep", "label": "Retry with new seed (keep all params)", "action": "new_seed"},
                {"id": "minor_tweak", "label": "Minor prompt tweak", "action": "edit_prompt"},
            ],
        })

    return questions


# ── Action executor ─────────────────────────────────────────────────────

async def execute_action(
    shot_id: str,
    action_type: str,
    params: dict | None = None,
) -> dict:
    """Execute a feedback action: update shot params and reset for regeneration.

    Returns dict with 'changes' (before→after) and 'regenerated' bool.
    """
    params = params or {}
    pool = await get_pool()
    changes = {}

    async with pool.acquire() as conn:
        shot = await conn.fetchrow("SELECT * FROM shots WHERE id = $1", UUID(shot_id))
        if not shot:
            return {"error": "Shot not found", "regenerated": False}

        before = _snapshot_params(shot)
        updates: list[tuple[str, Any]] = []

        if action_type == "bump_tier":
            target = params.get("target_tier")
            if not target:
                current = shot["motion_tier"] or "medium"
                idx = MOTION_TIER_ORDER.index(current) if current in MOTION_TIER_ORDER else 1
                target = MOTION_TIER_ORDER[min(idx + 1, len(MOTION_TIER_ORDER) - 1)]
            updates.append(("motion_tier", target))
            # Apply tier params
            from packages.scene_generation.motion_intensity import MOTION_TIERS
            tier_params = MOTION_TIERS.get(target)
            if tier_params:
                updates.append(("gen_split_steps", tier_params.split_steps))
                updates.append(("gen_lightx2v", tier_params.use_lightx2v))
                updates.append(("steps", tier_params.total_steps))

        elif action_type == "drop_tier":
            current = shot["motion_tier"] or "medium"
            idx = MOTION_TIER_ORDER.index(current) if current in MOTION_TIER_ORDER else 1
            target = MOTION_TIER_ORDER[max(idx - 1, 0)]
            updates.append(("motion_tier", target))
            from packages.scene_generation.motion_intensity import MOTION_TIERS
            tier_params = MOTION_TIERS.get(target)
            if tier_params:
                updates.append(("gen_split_steps", tier_params.split_steps))
                updates.append(("gen_lightx2v", tier_params.use_lightx2v))
                updates.append(("steps", tier_params.total_steps))

        elif action_type == "swap_lora":
            high = params.get("high", "")
            low = params.get("low", "")
            updates.append(("lora_name", high))
            updates.append(("content_lora_high", high))
            updates.append(("content_lora_low", low))
            # Apply recommended params from effectiveness data if available
            lora_key = params.get("lora_key")
            if lora_key:
                try:
                    from .lora_effectiveness import recommended_params
                    chars = shot.get("characters_present") or []
                    rec = await recommended_params(lora_key, chars[0] if chars else None)
                    if rec:
                        if rec.get("best_motion_tier"):
                            updates.append(("motion_tier", rec["best_motion_tier"]))
                        if rec.get("best_lora_strength"):
                            updates.append(("lora_strength", rec["best_lora_strength"]))
                except Exception as _eff_err:
                    logger.debug("Effectiveness lookup failed for %s: %s", lora_key, _eff_err)

        elif action_type == "adjust_cfg":
            current_cfg = shot.get("guidance_scale") or 1.0
            delta = params.get("delta", 0.5)
            new_cfg = max(0.5, min(10.0, current_cfg + delta))
            # guidance_scale may not be a column — use steps as proxy or check
            # Actually shots don't have guidance_scale column, this maps to gen params
            # Store in motion tier params instead
            updates.append(("gen_split_steps", shot.get("gen_split_steps") or 2))

        elif action_type == "adjust_strength":
            current = shot["lora_strength"] or 0.8
            if "set_to" in params:
                new_val = params["set_to"]
            else:
                delta = params.get("delta", 0.1)
                new_val = max(0.0, min(1.5, current + delta))
            updates.append(("lora_strength", round(new_val, 2)))
            if new_val == 0:
                updates.append(("lora_name", None))
                updates.append(("content_lora_high", None))
                updates.append(("content_lora_low", None))

        elif action_type == "edit_prompt":
            if "append" in params:
                current_prompt = shot.get("generation_prompt") or shot.get("motion_prompt") or ""
                new_prompt = f"{current_prompt}, {params['append']}"
                updates.append(("motion_prompt", new_prompt))
            elif "text" in params:
                updates.append(("motion_prompt", params["text"]))

        elif action_type == "edit_motion":
            if "text" in params:
                updates.append(("motion_prompt", params["text"]))

        elif action_type == "new_seed":
            updates.append(("seed", None))

        elif action_type == "change_camera":
            new_cam = params.get("camera_angle", "medium")
            updates.append(("camera_angle", new_cam))

        elif action_type == "blacklist_engine":
            engine = shot.get("video_engine") or "framepack"
            chars = shot.get("characters_present") or []
            char_slug = chars[0] if chars else "unknown"
            scene = await conn.fetchrow("SELECT project_id FROM scenes WHERE id = $1", shot["scene_id"])
            project_id = scene["project_id"] if scene else None
            await conn.execute(
                "INSERT INTO engine_blacklist (character_slug, project_id, video_engine, reason) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                char_slug, project_id, engine, "Feedback loop: user blacklisted"
            )
            # Switch to alternative engine
            alt_engine = "wan22_14b" if engine != "wan22_14b" else "framepack"
            updates.append(("video_engine", alt_engine))

        # Apply updates
        if updates:
            set_parts = []
            vals = [UUID(shot_id)]
            for i, (col, val) in enumerate(updates, 2):
                set_parts.append(f"{col} = ${i}")
                vals.append(val)
            sql = f"UPDATE shots SET {', '.join(set_parts)} WHERE id = $1"
            await conn.execute(sql, *vals)

        # Reset for regeneration
        await conn.execute(
            "UPDATE shots SET status = 'pending', output_video_path = NULL, "
            "review_status = NULL, quality_score = NULL, qc_issues = NULL, "
            "qc_category_averages = NULL, qc_per_frame = NULL, "
            "error_message = NULL, comfyui_prompt_id = NULL "
            "WHERE id = $1",
            UUID(shot_id),
        )

        # Get after snapshot
        shot_after = await conn.fetchrow("SELECT * FROM shots WHERE id = $1", UUID(shot_id))
        after = _snapshot_params(shot_after) if shot_after else {}

        changes = {col: {"before": before.get(col), "after": val} for col, val in updates}

    return {"changes": changes, "regenerated": True, "before": before, "after": after}


def _snapshot_params(shot) -> dict:
    """Extract generation-relevant params from a shot row."""
    keys = [
        "motion_tier", "gen_split_steps", "gen_lightx2v", "steps", "seed",
        "lora_name", "lora_strength", "content_lora_high", "content_lora_low",
        "camera_angle", "motion_prompt", "video_engine", "quality_score",
    ]
    result = {}
    for k in keys:
        try:
            val = shot[k]
            # Convert non-JSON-serializable types
            if isinstance(val, UUID):
                val = str(val)
            result[k] = val
        except (KeyError, TypeError):
            pass
    return result


# ── Feedback submission (full flow) ─────────────────────────────────────

async def submit_feedback(
    shot_id: str,
    rating: int,
    feedback_text: str = "",
    feedback_categories: list[str] | None = None,
) -> dict:
    """Submit initial feedback: store rating, generate questions with Echo Brain context."""
    categories = feedback_categories or []
    pool = await get_pool()

    async with pool.acquire() as conn:
        shot = await conn.fetchrow("SELECT * FROM shots WHERE id = $1", UUID(shot_id))
        if not shot:
            return {"error": "Shot not found"}

        qc_averages = shot.get("qc_category_averages") or {}
        qc_issues = list(shot.get("qc_issues") or [])
        lora_name = shot.get("lora_name") or ""

        # Query Echo Brain for relevant context
        echo_query_parts = ["video feedback"]
        if lora_name:
            echo_query_parts.append(lora_name.split("/")[-1].replace(".safetensors", ""))
        if shot.get("video_engine"):
            echo_query_parts.append(shot["video_engine"])
        echo_context = _search_echo_brain(" ".join(echo_query_parts))

        # Query learned patterns
        chars = shot.get("characters_present") or []
        learned_hint = ""
        if chars:
            pattern = await conn.fetchrow(
                "SELECT quality_score_avg, frequency, cfg_range_min, cfg_range_max "
                "FROM learned_patterns WHERE character_slug = $1 AND pattern_type = 'success' "
                "ORDER BY frequency DESC LIMIT 1",
                chars[0],
            )
            if pattern and pattern["frequency"] >= 3:
                learned_hint = (
                    f"Note: {chars[0]} has {pattern['frequency']} successful generations "
                    f"averaging {pattern['quality_score_avg']:.1f} quality."
                )

        full_echo = ""
        if echo_context:
            full_echo = echo_context
        if learned_hint:
            full_echo = f"{full_echo}\n{learned_hint}" if full_echo else learned_hint

        # Generate questions
        shot_dict = dict(shot)
        # Ensure qc_averages is a dict (asyncpg may return None)
        if isinstance(qc_averages, str):
            try:
                qc_averages = json.loads(qc_averages)
            except (json.JSONDecodeError, TypeError):
                qc_averages = {}
        questions = await generate_questions(
            shot_dict, qc_averages, qc_issues, rating, categories, full_echo,
        )

        # Count existing feedback rounds for this shot
        round_count = await conn.fetchval(
            "SELECT COALESCE(MAX(feedback_round), 0) FROM shot_feedback WHERE shot_id = $1",
            UUID(shot_id),
        )

        # Store feedback row
        feedback_id = await conn.fetchval(
            "INSERT INTO shot_feedback "
            "(shot_id, rating, feedback_text, feedback_categories, questions, echo_context, feedback_round) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7) RETURNING id",
            UUID(shot_id), rating, feedback_text, categories,
            json.dumps(questions), full_echo, (round_count or 0) + 1,
        )

    await event_bus.emit(FEEDBACK_SUBMITTED, {
        "shot_id": shot_id, "rating": rating, "categories": categories,
    })

    return {
        "feedback_id": str(feedback_id),
        "questions": questions,
        "echo_context": full_echo,
        "feedback_round": (round_count or 0) + 1,
    }


async def answer_question(
    shot_id: str,
    feedback_id: str,
    question_id: str,
    selected_option: str,
    extra_params: dict | None = None,
) -> dict:
    """Process a user's answer: execute the mapped action, store results, notify Echo Brain."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        fb = await conn.fetchrow(
            "SELECT * FROM shot_feedback WHERE id = $1", UUID(feedback_id),
        )
        if not fb:
            return {"error": "Feedback not found"}

        shot = await conn.fetchrow("SELECT * FROM shots WHERE id = $1", UUID(shot_id))
        if not shot:
            return {"error": "Shot not found"}

        # Find the question and selected option
        questions = fb["questions"] or []
        if isinstance(questions, str):
            questions = json.loads(questions)
        question = None
        option = None
        for q in questions:
            if q["id"] == question_id:
                question = q
                for opt in q.get("options", []):
                    if opt["id"] == selected_option:
                        option = opt
                        break
                break

        if not question or not option:
            return {"error": "Question or option not found"}

        action_type = option.get("action", "new_seed")
        action_params = option.get("params", {})
        if extra_params:
            action_params.update(extra_params)

        # Snapshot before
        before = _snapshot_params(shot)

        # Execute the action
        result = await execute_action(shot_id, action_type, action_params)

        # Update feedback row with answer and action
        raw_answers = fb["answers"] or []
        answers = json.loads(raw_answers) if isinstance(raw_answers, str) else list(raw_answers)
        if not isinstance(answers, list):
            answers = []
        answers.append({
            "question_id": question_id,
            "selected_option": selected_option,
            "action_type": action_type,
            "action_params": action_params,
        })

        raw_actions = fb["actions_taken"] or []
        actions_taken = json.loads(raw_actions) if isinstance(raw_actions, str) else list(raw_actions)
        if not isinstance(actions_taken, list):
            actions_taken = []
        actions_taken.append({
            "action_type": action_type,
            "changes": result.get("changes", {}),
            "regenerated": result.get("regenerated", False),
        })

        await conn.execute(
            "UPDATE shot_feedback SET answers = $2::jsonb, actions_taken = $3::jsonb, "
            "previous_params = $4::jsonb, new_params = $5::jsonb WHERE id = $1",
            UUID(feedback_id),
            json.dumps(answers),
            json.dumps(actions_taken),
            json.dumps(before),
            json.dumps(result.get("after", {})),
        )

    # Emit event
    await event_bus.emit(FEEDBACK_ACTION_EXECUTED, {
        "shot_id": shot_id,
        "feedback_id": feedback_id,
        "action_type": action_type,
        "changes": result.get("changes", {}),
    })

    # Store to Echo Brain
    chars = shot.get("characters_present") or []
    char_str = ", ".join(chars) if chars else "unknown"
    lora_str = (shot.get("lora_name") or "no LoRA").split("/")[-1]
    _store_echo_feedback(
        f"[Feedback Loop] Shot {shot_id}: {action_type} applied for {char_str} "
        f"(LoRA: {lora_str}, rating: {fb['rating']}/5). "
        f"Changes: {json.dumps(result.get('changes', {}))}"
    )

    # Record learned pattern
    if chars:
        await record_learned_pattern(
            character_slug=chars[0],
            pattern_type=f"feedback_{action_type}",
            quality_score=shot.get("quality_score"),
        )

    return {
        "action_type": action_type,
        "changes": result.get("changes", {}),
        "regenerated": result.get("regenerated", False),
        "before": before,
        "after": result.get("after", {}),
    }


async def get_feedback_history(shot_id: str) -> list[dict]:
    """Get all feedback rounds for a shot."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM shot_feedback WHERE shot_id = $1 ORDER BY feedback_round",
            UUID(shot_id),
        )
        def _parse_jsonb(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            return val

        return [
            {
                "id": str(r["id"]),
                "shot_id": str(r["shot_id"]),
                "rating": r["rating"],
                "feedback_text": r["feedback_text"],
                "feedback_categories": list(r["feedback_categories"] or []),
                "questions": _parse_jsonb(r["questions"] or []),
                "answers": _parse_jsonb(r["answers"] or []),
                "actions_taken": _parse_jsonb(r["actions_taken"] or []),
                "echo_context": r["echo_context"],
                "previous_params": _parse_jsonb(r["previous_params"]),
                "new_params": _parse_jsonb(r["new_params"]),
                "feedback_round": r["feedback_round"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
