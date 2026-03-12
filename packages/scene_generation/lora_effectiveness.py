"""Cross-project LoRA effectiveness tracking.

Aggregates QC scores from shots across all projects into lora_effectiveness rows.
Provides query functions for: best LoRA for a character, best params for a LoRA,
cross-project rankings, and effectiveness-aware alternative suggestions.

Usage:
    # Refresh all aggregates (run periodically or after QC batch)
    await refresh_effectiveness()

    # Query best LoRAs for a character
    results = await best_loras_for_character("mira", content_rating="G")

    # Get recommended params for a LoRA
    params = await recommended_params("assertive_cowgirl")
"""

import json
import logging
from typing import Optional

from packages.core.db import get_pool

logger = logging.getLogger(__name__)


# ── Aggregation ────────────────────────────────────────────────────────

async def refresh_effectiveness(project_id: int | None = None):
    """Aggregate QC scores from shots into lora_effectiveness rows.

    Groups by lora_key (extracted from lora_name filename) × character_slug × project.
    Computes averages, approval rates, best-performing params, and issue histograms.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Build WHERE clause
        where = "WHERE s.lora_name IS NOT NULL AND s.quality_score IS NOT NULL"
        params = []
        if project_id:
            where += " AND sc.project_id = $1"
            params.append(project_id)

        rows = await conn.fetch(f"""
            WITH shot_data AS (
                SELECT
                    s.lora_name,
                    -- Extract lora key from filename: wan22_nsfw/assertive_cowgirl_HIGH.safetensors → assertive_cowgirl
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            SPLIT_PART(s.lora_name, '/', -1),
                            '_(HIGH|LOW)\\.safetensors$', '', 'i'
                        ),
                        '\\.safetensors$', '', 'i'
                    ) AS lora_key,
                    CASE WHEN s.characters_present IS NOT NULL AND array_length(s.characters_present, 1) > 0
                         THEN s.characters_present[1] ELSE NULL END AS char_slug,
                    sc.project_id,
                    p.name AS project_name,
                    p.content_rating,
                    s.quality_score,
                    s.review_status,
                    s.motion_tier,
                    s.lora_strength,
                    s.guidance_scale,
                    s.steps,
                    s.qc_category_averages,
                    s.qc_issues
                FROM shots s
                JOIN scenes sc ON s.scene_id = sc.id
                JOIN projects p ON sc.project_id = p.id
                {where}
            )
            SELECT
                lora_key,
                lora_name,
                char_slug,
                project_id,
                project_name,
                content_rating,
                COUNT(*) AS sample_count,
                AVG(quality_score) AS avg_quality,
                COUNT(*) FILTER (WHERE review_status = 'approved')::FLOAT
                    / NULLIF(COUNT(*) FILTER (WHERE review_status IS NOT NULL), 0) AS approval_rate,
                -- Best params = from highest-scoring shot
                (ARRAY_AGG(motion_tier ORDER BY quality_score DESC NULLS LAST))[1] AS best_motion_tier,
                (ARRAY_AGG(lora_strength ORDER BY quality_score DESC NULLS LAST))[1] AS best_lora_strength,
                (ARRAY_AGG(guidance_scale ORDER BY quality_score DESC NULLS LAST))[1] AS best_cfg,
                (ARRAY_AGG(steps ORDER BY quality_score DESC NULLS LAST))[1] AS best_steps,
                -- Collect all qc_category_averages and qc_issues for post-processing
                ARRAY_AGG(qc_category_averages::text) AS all_qc_avgs,
                ARRAY_AGG(array_to_json(COALESCE(qc_issues, ARRAY[]::text[]))::text) AS all_qc_issues
            FROM shot_data
            GROUP BY lora_key, lora_name, char_slug, project_id, project_name, content_rating
        """, *params)

        upserted = 0
        for row in rows:
            # Compute average category scores from JSONB arrays
            avg_motion = _avg_from_jsonb_array(row["all_qc_avgs"], "motion_execution")
            avg_char = _avg_from_jsonb_array(row["all_qc_avgs"], "character_match")
            avg_reaction = _avg_from_jsonb_array(row["all_qc_avgs"], "reaction_presence")
            avg_state_delta = _avg_from_jsonb_array(row["all_qc_avgs"], "state_delta")

            # Build issue histogram
            issues_hist = _build_issue_histogram(row["all_qc_issues"])

            # Upsert
            await conn.execute("""
                INSERT INTO lora_effectiveness (
                    lora_key, lora_name, character_slug, project_id, project_name,
                    content_rating, sample_count, avg_quality, avg_motion_execution,
                    avg_character_match, avg_reaction_score, avg_state_delta,
                    approval_rate, best_motion_tier, best_lora_strength, best_cfg,
                    best_steps, issues_histogram, last_updated
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18::jsonb, NOW()
                )
                ON CONFLICT (lora_key, COALESCE(character_slug, ''), COALESCE(project_id, 0))
                DO UPDATE SET
                    lora_name = EXCLUDED.lora_name,
                    project_name = EXCLUDED.project_name,
                    content_rating = EXCLUDED.content_rating,
                    sample_count = EXCLUDED.sample_count,
                    avg_quality = EXCLUDED.avg_quality,
                    avg_motion_execution = EXCLUDED.avg_motion_execution,
                    avg_character_match = EXCLUDED.avg_character_match,
                    avg_reaction_score = EXCLUDED.avg_reaction_score,
                    avg_state_delta = EXCLUDED.avg_state_delta,
                    approval_rate = EXCLUDED.approval_rate,
                    best_motion_tier = EXCLUDED.best_motion_tier,
                    best_lora_strength = EXCLUDED.best_lora_strength,
                    best_cfg = EXCLUDED.best_cfg,
                    best_steps = EXCLUDED.best_steps,
                    issues_histogram = EXCLUDED.issues_histogram,
                    last_updated = NOW()
            """,
                row["lora_key"], row["lora_name"], row["char_slug"],
                row["project_id"], row["project_name"], row["content_rating"],
                row["sample_count"], row["avg_quality"],
                avg_motion, avg_char, avg_reaction, avg_state_delta,
                row["approval_rate"],
                row["best_motion_tier"], row["best_lora_strength"],
                row["best_cfg"], row["best_steps"],
                json.dumps(issues_hist),
            )
            upserted += 1

        logger.info("LoRA effectiveness: upserted %d rows", upserted)
        return upserted


def _avg_from_jsonb_array(jsonb_array, key: str) -> float | None:
    """Extract average of a key from an array of JSONB objects (some may be None or strings)."""
    values = []
    for item in (jsonb_array or []):
        if item is None:
            continue
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(item, dict):
            val = item.get(key)
            if val is not None:
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    pass
    return sum(values) / len(values) if values else None


def _build_issue_histogram(issues_array) -> dict:
    """Count issue occurrences across shots."""
    hist: dict[str, int] = {}
    for issues in (issues_array or []):
        if issues is None:
            continue
        if isinstance(issues, str):
            try:
                issues = json.loads(issues)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(issues, list):
            for issue in issues:
                if isinstance(issue, str):
                    hist[issue] = hist.get(issue, 0) + 1
    return hist


# ── Query functions ────────────────────────────────────────────────────

async def best_loras_for_character(
    character_slug: str,
    content_rating: str | None = None,
    project_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Find best-performing LoRAs for a character across projects.

    Returns ranked by avg_quality DESC, with sample_count as tiebreaker.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        where_parts = ["character_slug = $1", "sample_count >= 2"]
        params: list = [character_slug]
        idx = 2

        if content_rating:
            where_parts.append(f"content_rating = ${idx}")
            params.append(content_rating)
            idx += 1

        if project_id:
            where_parts.append(f"project_id = ${idx}")
            params.append(project_id)
            idx += 1

        where_parts.append(f"${idx}")
        params.append(limit)

        rows = await conn.fetch(f"""
            SELECT lora_key, lora_name, project_name, content_rating,
                   sample_count, avg_quality, avg_motion_execution,
                   avg_character_match, avg_reaction_score,
                   approval_rate, best_motion_tier, best_lora_strength,
                   best_cfg, best_steps, issues_histogram
            FROM lora_effectiveness
            WHERE {' AND '.join(where_parts[:-1])}
            ORDER BY avg_quality DESC NULLS LAST, sample_count DESC
            LIMIT ${idx}
        """, *params)

        return [_row_to_dict(r) for r in rows]


async def best_loras_overall(
    content_rating: str | None = None,
    min_samples: int = 3,
    limit: int = 10,
) -> list[dict]:
    """Top LoRAs across all characters and projects."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        where_parts = [f"sample_count >= $1"]
        params: list = [min_samples]
        idx = 2

        if content_rating:
            where_parts.append(f"content_rating = ${idx}")
            params.append(content_rating)
            idx += 1

        params.append(limit)

        rows = await conn.fetch(f"""
            SELECT lora_key, lora_name, character_slug, project_name,
                   content_rating, sample_count, avg_quality,
                   avg_motion_execution, avg_character_match,
                   approval_rate, best_motion_tier, best_lora_strength,
                   issues_histogram
            FROM lora_effectiveness
            WHERE {' AND '.join(where_parts)}
            ORDER BY avg_quality DESC NULLS LAST, sample_count DESC
            LIMIT ${idx}
        """, *params)

        return [_row_to_dict(r) for r in rows]


async def recommended_params(
    lora_key: str,
    character_slug: str | None = None,
) -> dict | None:
    """Get recommended generation params for a LoRA, optionally per-character.

    Returns best_motion_tier, best_lora_strength, best_cfg, best_steps
    from the highest-quality row matching the LoRA key.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Try character-specific first, then global
        if character_slug:
            row = await conn.fetchrow(
                "SELECT best_motion_tier, best_lora_strength, best_cfg, best_steps, "
                "avg_quality, sample_count "
                "FROM lora_effectiveness "
                "WHERE lora_key = $1 AND character_slug = $2 AND sample_count >= 2 "
                "ORDER BY avg_quality DESC NULLS LAST LIMIT 1",
                lora_key, character_slug,
            )
            if row:
                return _row_to_dict(row)

        row = await conn.fetchrow(
            "SELECT best_motion_tier, best_lora_strength, best_cfg, best_steps, "
            "avg_quality, sample_count "
            "FROM lora_effectiveness "
            "WHERE lora_key = $1 AND sample_count >= 2 "
            "ORDER BY avg_quality DESC NULLS LAST LIMIT 1",
            lora_key,
        )
        return _row_to_dict(row) if row else None


async def lora_effectiveness_summary(lora_key: str) -> dict:
    """Full cross-project summary for a single LoRA key."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM lora_effectiveness WHERE lora_key = $1 "
            "ORDER BY avg_quality DESC NULLS LAST",
            lora_key,
        )
        if not rows:
            return {"lora_key": lora_key, "entries": [], "total_samples": 0}

        entries = [_row_to_dict(r) for r in rows]
        total_samples = sum(e.get("sample_count", 0) for e in entries)
        avg_quality = (
            sum(e["avg_quality"] * e["sample_count"] for e in entries if e.get("avg_quality"))
            / total_samples
        ) if total_samples > 0 else None

        return {
            "lora_key": lora_key,
            "entries": entries,
            "total_samples": total_samples,
            "weighted_avg_quality": round(avg_quality, 3) if avg_quality else None,
            "projects": list({e["project_name"] for e in entries if e.get("project_name")}),
            "characters": list({e["character_slug"] for e in entries if e.get("character_slug")}),
        }


async def find_alternatives_with_effectiveness(
    current_lora_key: str,
    character_slug: str | None = None,
    content_rating: str | None = None,
    limit: int = 3,
) -> list[dict]:
    """Find alternative LoRAs ranked by actual effectiveness data.

    Supplements catalog tag-matching with real QC performance data.
    Falls back to catalog-only matching if no effectiveness data exists.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get current LoRA's tags from catalog for tag-matching
        from .feedback_loop import find_lora_alternatives, _load_catalog
        catalog_alts = find_lora_alternatives(current_lora_key, max_results=10)

        if not catalog_alts:
            return []

        # Enrich with effectiveness data
        enriched = []
        for alt in catalog_alts:
            alt_key = alt["key"]
            # Query effectiveness for this alternative
            where_parts = ["lora_key = $1"]
            params: list = [alt_key]
            idx = 2

            if character_slug:
                where_parts.append(f"(character_slug = ${idx} OR character_slug IS NULL)")
                params.append(character_slug)
                idx += 1

            if content_rating:
                where_parts.append(f"(content_rating = ${idx} OR content_rating IS NULL)")
                params.append(content_rating)
                idx += 1

            eff_row = await conn.fetchrow(f"""
                SELECT avg_quality, avg_motion_execution, avg_character_match,
                       approval_rate, sample_count, best_motion_tier, best_lora_strength
                FROM lora_effectiveness
                WHERE {' AND '.join(where_parts)}
                ORDER BY
                    CASE WHEN character_slug = $1 THEN 0 ELSE 1 END,
                    avg_quality DESC NULLS LAST
                LIMIT 1
            """, *params)

            entry = dict(alt)
            if eff_row:
                entry["effectiveness"] = {
                    "avg_quality": eff_row["avg_quality"],
                    "avg_motion": eff_row["avg_motion_execution"],
                    "avg_character": eff_row["avg_character_match"],
                    "approval_rate": eff_row["approval_rate"],
                    "sample_count": eff_row["sample_count"],
                    "recommended_tier": eff_row["best_motion_tier"],
                    "recommended_strength": eff_row["best_lora_strength"],
                }
                # Boost score with effectiveness data
                if eff_row["avg_quality"] is not None:
                    entry["score"] += int(eff_row["avg_quality"] * 2)
                if eff_row["approval_rate"] is not None and eff_row["approval_rate"] > 0.5:
                    entry["score"] += 3
            else:
                entry["effectiveness"] = None

            enriched.append(entry)

        # Re-sort by combined score
        enriched.sort(key=lambda x: x["score"], reverse=True)
        return enriched[:limit]


def _row_to_dict(row) -> dict:
    """Convert asyncpg Record to dict, parsing JSONB strings."""
    if row is None:
        return {}
    d = dict(row)
    for key in ("issues_histogram",):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
