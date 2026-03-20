"""Lightweight quality gate — auto-approve keyframes without Ollama GPU contention.

Replaces the heavy gemma3 vision review for keyframe auto-approval.
Uses file-size, aspect-ratio, and historical LoRA quality to decide:
  approved  — meets all criteria, skip human review
  review    — borderline, flag for human review
  rejected  — clearly bad (blank, corrupt, wrong dimensions)

Does NOT require GPU. Safe to call from the generation loop at full speed.
"""

import logging
from pathlib import Path

from .db import get_pool

logger = logging.getLogger(__name__)

# Defaults — overridden by project gen_loop_config
DEFAULT_AUTO_APPROVE_THRESHOLD = 0.75
DEFAULT_MIN_FILE_SIZE_KB = 50
DEFAULT_ASPECT_RATIO_TOLERANCE = 0.15


async def quality_gate(
    image_path: str,
    character_slug: str | None = None,
    lora_name: str | None = None,
    project_id: int | None = None,
    expected_width: int | None = None,
    expected_height: int | None = None,
    config: dict | None = None,
) -> dict:
    """Run lightweight quality checks on a generated keyframe.

    Returns:
        {
            "decision": "approved" | "review" | "rejected",
            "score": float (0-1),
            "reasons": [str],
            "auto_approved": bool,
        }
    """
    config = config or {}
    min_size_kb = config.get("min_file_size_kb", DEFAULT_MIN_FILE_SIZE_KB)
    ar_tolerance = config.get("aspect_ratio_tolerance", DEFAULT_ASPECT_RATIO_TOLERANCE)
    auto_threshold = config.get("auto_approve_threshold", DEFAULT_AUTO_APPROVE_THRESHOLD)

    path = Path(image_path)
    reasons = []
    score = 1.0

    # ── Check 1: File exists ──────────────────────────────────────────
    if not path.exists():
        return {"decision": "rejected", "score": 0.0, "reasons": ["file_not_found"], "auto_approved": False}

    # ── Check 2: File size (corrupt/blank detection) ──────────────────
    size_kb = path.stat().st_size / 1024
    if size_kb < min_size_kb:
        return {"decision": "rejected", "score": 0.1, "reasons": [f"file_too_small ({size_kb:.0f}KB < {min_size_kb}KB)"], "auto_approved": False}

    # ── Check 3: Aspect ratio ─────────────────────────────────────────
    if expected_width and expected_height:
        try:
            from PIL import Image
            with Image.open(path) as img:
                w, h = img.size
            expected_ar = expected_width / expected_height
            actual_ar = w / h
            ar_diff = abs(actual_ar - expected_ar) / expected_ar
            if ar_diff > ar_tolerance:
                score -= 0.3
                reasons.append(f"aspect_ratio_mismatch ({w}x{h} vs {expected_width}x{expected_height})")
        except Exception as e:
            score -= 0.2
            reasons.append(f"image_read_error ({e})")

    # ── Check 4: Historical LoRA quality ──────────────────────────────
    lora_score = await _get_historical_lora_quality(character_slug, lora_name, project_id)
    if lora_score is not None:
        if lora_score >= 0.8:
            # This LoRA+character combo historically produces good results
            score = min(score, 1.0)  # no penalty
        elif lora_score < 0.5:
            score -= 0.15
            reasons.append(f"lora_historically_poor ({lora_score:.2f})")

    # ── Check 5: CLIP similarity (optional, async, non-blocking) ──────
    clip_score = await _get_clip_similarity(image_path, character_slug, project_id)
    if clip_score is not None:
        if clip_score < 0.5:
            score -= 0.25
            reasons.append(f"low_clip_similarity ({clip_score:.2f})")
        elif clip_score >= 0.75:
            score += 0.05  # small bonus for high match

    score = max(0.0, min(1.0, score))

    # ── Decision ──────────────────────────────────────────────────────
    if score >= auto_threshold:
        decision = "approved"
    elif score >= auto_threshold - 0.25:
        decision = "review"
    else:
        decision = "rejected"

    return {
        "decision": decision,
        "score": round(score, 3),
        "reasons": reasons or ["passed_all_checks"],
        "auto_approved": decision == "approved",
    }


async def _get_historical_lora_quality(
    character_slug: str | None,
    lora_name: str | None,
    project_id: int | None,
) -> float | None:
    """Query average quality score for this LoRA+character combo from generation_history."""
    if not character_slug or not lora_name:
        return None
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT AVG(quality_score) as avg_score, COUNT(*) as cnt
                FROM generation_history
                WHERE character_slug = $1 AND lora_name = $2
                  AND quality_score IS NOT NULL
                  AND status IN ('approved', 'auto_approved')
            """, character_slug, lora_name)
            if row and row["cnt"] >= 3:
                return float(row["avg_score"])
    except Exception as e:
        logger.debug(f"Historical LoRA quality lookup failed: {e}")
    return None


async def _get_clip_similarity(
    image_path: str,
    character_slug: str | None,
    project_id: int | None,
) -> float | None:
    """Call Echo Brain's evaluate_generation for CLIP similarity score.

    Non-blocking: returns None on any failure rather than stalling the pipeline.
    """
    if not character_slug:
        return None
    try:
        import urllib.request
        import json

        payload = json.dumps({
            "method": "tools/call",
            "params": {
                "name": "evaluate_generation",
                "arguments": {
                    "image_path": image_path,
                    "character_slug": character_slug,
                },
            },
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8309/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        # Extract CLIP score from response
        content = result.get("result", {}).get("content", [])
        if content:
            text = content[0].get("text", "")
            data = json.loads(text) if text.startswith("{") else {}
            return data.get("clip_score") or data.get("similarity_score")
    except Exception as e:
        logger.debug(f"CLIP similarity check failed (non-fatal): {e}")
    return None
