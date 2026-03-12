"""Trailer Scorecard — measures LoRA effectiveness, motion quality, and pipeline
completeness from QC data on trailer shots.

Produces a pass/fail report per dimension with actionable recommendations.
The orchestrator's trailer_validation gate checks this scorecard before
allowing full production.
"""

import json
import logging
import uuid
import yaml
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from packages.core.db import connect_direct

logger = logging.getLogger(__name__)

LORA_CATALOG_PATH = Path("/opt/anime-studio/config/lora_catalog.yaml")
LORA_DIR = Path("/opt/ComfyUI/models/loras")

# Thresholds
CHARACTER_FIDELITY_THRESHOLD = 6.0   # /10
MOTION_EFFECTIVENESS_THRESHOLD = 5.5  # /10
MULTI_CHAR_THRESHOLD = 5.0           # /10
OVERALL_PASS_RATIO = 0.6             # 60% of dimensions must pass


@dataclass
class DimensionScore:
    name: str
    key: str
    passed: bool
    score: float | None  # 0-10 or None for binary
    details: str
    recommendation: str | None = None


@dataclass
class ShotScore:
    shot_id: str
    shot_number: int
    role: str
    status: str
    character_match: float | None
    motion_execution: float | None
    composition: float | None
    lighting: float | None
    temporal_consistency: float | None
    quality_score: float | None
    issues: list[str]
    lora_name: str | None
    image_lora: str | None
    motion_tier: str | None
    has_keyframe: bool
    has_video: bool


@dataclass
class TrailerScorecard:
    trailer_id: str
    project_id: int
    project_name: str
    scored_at: str
    dimensions: list[DimensionScore]
    overall_pass: bool
    pass_count: int
    fail_count: int
    skip_count: int
    recommendations: list[str]
    shot_scores: list[ShotScore]


def _load_lora_catalog() -> dict:
    if not LORA_CATALOG_PATH.exists():
        return {}
    with open(LORA_CATALOG_PATH) as f:
        return yaml.safe_load(f) or {}


def _qc_val(qc: dict | str | None, key: str) -> float | None:
    """Extract a QC category value, handling JSONB that may be a string."""
    if qc is None:
        return None
    if isinstance(qc, str):
        try:
            qc = json.loads(qc)
        except (json.JSONDecodeError, TypeError):
            return None
    val = qc.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _build_shot_scores(shots: list[dict]) -> list[ShotScore]:
    """Build per-shot score summaries from DB rows."""
    results = []
    for s in shots:
        qc = s.get("qc_category_averages")
        issues = s.get("qc_issues") or []
        results.append(ShotScore(
            shot_id=str(s["id"]),
            shot_number=s["shot_number"],
            role=s.get("trailer_role") or "unknown",
            status=s["status"],
            character_match=_qc_val(qc, "character_match"),
            motion_execution=_qc_val(qc, "motion_execution"),
            composition=_qc_val(qc, "composition"),
            lighting=_qc_val(qc, "lighting"),
            temporal_consistency=_qc_val(qc, "temporal_consistency"),
            quality_score=s.get("quality_score"),
            issues=list(issues),
            lora_name=s.get("lora_name"),
            image_lora=s.get("image_lora"),
            motion_tier=s.get("motion_tier"),
            has_keyframe=s.get("first_frame_path") is not None,
            has_video=s.get("output_video_path") is not None,
        ))
    return results


def _score_character_fidelity(shot_scores: list[ShotScore]) -> DimensionScore:
    """Score character LoRA fidelity from character_intro + interaction + climax shots."""
    relevant = [s for s in shot_scores if s.role in ("character_intro", "interaction", "climax")]
    scored = [s for s in relevant if s.character_match is not None]

    if not scored:
        return DimensionScore(
            name="Character LoRA Fidelity",
            key="character_fidelity",
            passed=False,
            score=None,
            details="No QC scores yet — shots need video generation + QC",
            recommendation="Generate videos and run QC on character shots",
        )

    avg = sum(s.character_match for s in scored) / len(scored)
    worst = min(scored, key=lambda s: s.character_match)
    passed = avg >= CHARACTER_FIDELITY_THRESHOLD

    rec = None
    if not passed:
        no_lora = [s for s in relevant if not s.image_lora]
        if no_lora:
            rec = f"No character LoRA on {len(no_lora)} shots — train or assign LoRAs"
        else:
            rec = f"Character match too low ({avg:.1f}/10). Retrain LoRA with better reference images"

    return DimensionScore(
        name="Character LoRA Fidelity",
        key="character_fidelity",
        passed=passed,
        score=round(avg, 1),
        details=f"Avg {avg:.1f}/10 across {len(scored)} shots. Worst: shot {worst.shot_number} ({worst.character_match:.1f})",
        recommendation=rec,
    )


def _score_motion_effectiveness(shot_scores: list[ShotScore]) -> DimensionScore:
    """Score motion LoRA effectiveness from action + climax shots."""
    relevant = [s for s in shot_scores if s.role in ("action", "climax") and s.lora_name]
    scored = [s for s in relevant if s.motion_execution is not None]

    if not relevant:
        return DimensionScore(
            name="Motion LoRA Effectiveness",
            key="motion_effectiveness",
            passed=False,
            score=None,
            details="No action shots with motion LoRAs — template may be misconfigured",
            recommendation="Ensure trailer has action shots with video LoRAs assigned",
        )

    if not scored:
        return DimensionScore(
            name="Motion LoRA Effectiveness",
            key="motion_effectiveness",
            passed=False,
            score=None,
            details=f"{len(relevant)} action shots pending QC",
            recommendation="Generate videos and run QC on action shots",
        )

    avg = sum(s.motion_execution for s in scored) / len(scored)
    passed = avg >= MOTION_EFFECTIVENESS_THRESHOLD

    # Per-LoRA breakdown
    by_lora = {}
    for s in scored:
        by_lora.setdefault(s.lora_name, []).append(s.motion_execution)
    breakdown = ", ".join(f"{k}: {sum(v)/len(v):.1f}" for k, v in by_lora.items())

    rec = None
    if not passed:
        worst_lora = min(by_lora, key=lambda k: sum(by_lora[k]) / len(by_lora[k]))
        rec = f"Swap or retrain '{worst_lora}' — motion score below threshold"

    return DimensionScore(
        name="Motion LoRA Effectiveness",
        key="motion_effectiveness",
        passed=passed,
        score=round(avg, 1),
        details=f"Avg {avg:.1f}/10. Per-LoRA: {breakdown}",
        recommendation=rec,
    )


def _score_content_lora_pairing(shot_scores: list[ShotScore], catalog: dict) -> DimensionScore:
    """Check that content LoRAs have valid HIGH/LOW pairs on disk."""
    pairs = catalog.get("video_lora_pairs", {})
    lora_shots = [s for s in shot_scores if s.lora_name]

    if not lora_shots:
        return DimensionScore(
            name="Content LoRA Pairing",
            key="content_pairing",
            passed=True,
            score=None,
            details="No content LoRAs used — skipped",
        )

    issues = []
    checked = set()
    for s in lora_shots:
        key = s.lora_name
        if key in checked:
            continue
        checked.add(key)

        pair = pairs.get(key, {})
        high = pair.get("high")
        low = pair.get("low")

        if not high:
            issues.append(f"{key}: no HIGH variant in catalog")
        elif not (LORA_DIR / high).exists():
            issues.append(f"{key}: HIGH file missing ({high})")

        if not low:
            issues.append(f"{key}: no LOW variant in catalog")
        elif not (LORA_DIR / low).exists():
            issues.append(f"{key}: LOW file missing ({low})")

    passed = len(issues) == 0
    return DimensionScore(
        name="Content LoRA Pairing",
        key="content_pairing",
        passed=passed,
        score=None,
        details=f"Checked {len(checked)} LoRAs. " + (f"{len(issues)} issues" if issues else "All pairs valid"),
        recommendation="; ".join(issues[:3]) if issues else None,
    )


def _score_motion_tier(shot_scores: list[ShotScore]) -> DimensionScore:
    """Evaluate which motion tier performs best from action shots."""
    scored = [s for s in shot_scores if s.motion_execution is not None and s.motion_tier]

    if not scored:
        return DimensionScore(
            name="Motion Tier Optimization",
            key="motion_tier",
            passed=True,
            score=None,
            details="Not enough data to evaluate tiers — skipped",
        )

    by_tier = {}
    for s in scored:
        by_tier.setdefault(s.motion_tier, []).append(s.motion_execution)

    tier_avgs = {t: sum(v) / len(v) for t, v in by_tier.items()}
    best_tier = max(tier_avgs, key=tier_avgs.get)
    best_avg = tier_avgs[best_tier]
    passed = best_avg >= MOTION_EFFECTIVENESS_THRESHOLD

    breakdown = ", ".join(f"{t}: {a:.1f}" for t, a in sorted(tier_avgs.items()))

    rec = None
    if not passed:
        rec = f"Best tier '{best_tier}' only scored {best_avg:.1f}/10 — try 'high' or 'extreme'"
    elif len(tier_avgs) == 1:
        rec = f"Only tested '{best_tier}' — regenerate some shots at different tiers to compare"

    return DimensionScore(
        name="Motion Tier Optimization",
        key="motion_tier",
        passed=passed,
        score=round(best_avg, 1),
        details=f"Best: {best_tier} ({best_avg:.1f}/10). {breakdown}",
        recommendation=rec,
    )


def _score_pipeline_completeness(shot_scores: list[ShotScore]) -> DimensionScore:
    """Check that all shots completed the full generation pipeline."""
    total = len(shot_scores)
    with_keyframe = sum(1 for s in shot_scores if s.has_keyframe)
    with_video = sum(1 for s in shot_scores if s.has_video)
    completed = sum(1 for s in shot_scores if s.status == "completed")

    all_done = completed == total and with_video == total
    passed = all_done

    failed_roles = [s.role for s in shot_scores if s.status != "completed"]
    details = f"{completed}/{total} completed, {with_keyframe}/{total} keyframes, {with_video}/{total} videos"

    rec = None
    if not all_done:
        missing_kf = [s for s in shot_scores if not s.has_keyframe]
        missing_vid = [s for s in shot_scores if s.has_keyframe and not s.has_video]
        if missing_kf:
            rec = f"Generate keyframes for shots: {', '.join(str(s.shot_number) for s in missing_kf)}"
        elif missing_vid:
            rec = f"Generate videos for shots: {', '.join(str(s.shot_number) for s in missing_vid)}"
        else:
            rec = f"Failed roles: {', '.join(failed_roles)}"

    return DimensionScore(
        name="Pipeline Completeness",
        key="pipeline_completeness",
        passed=passed,
        score=round(completed / total * 10, 1) if total else 0,
        details=details,
        recommendation=rec,
    )


def _score_multi_character(shot_scores: list[ShotScore]) -> DimensionScore:
    """Score multi-character coherence from interaction shots."""
    interaction = [s for s in shot_scores if s.role == "interaction"]

    if not interaction:
        return DimensionScore(
            name="Multi-Character Coherence",
            key="multi_character",
            passed=True,
            score=None,
            details="No interaction shots in trailer — skipped",
        )

    scored = [s for s in interaction if s.character_match is not None]
    if not scored:
        return DimensionScore(
            name="Multi-Character Coherence",
            key="multi_character",
            passed=False,
            score=None,
            details="Interaction shots pending QC",
            recommendation="Generate and QC interaction shots",
        )

    char_avg = sum(s.character_match for s in scored) / len(scored)
    comp_vals = [s.composition for s in scored if s.composition is not None]
    comp_avg = sum(comp_vals) / len(comp_vals) if comp_vals else None

    passed = char_avg >= MULTI_CHAR_THRESHOLD and (comp_avg is None or comp_avg >= MULTI_CHAR_THRESHOLD)
    score = round(char_avg, 1)

    details = f"Character match: {char_avg:.1f}/10"
    if comp_avg is not None:
        details += f", Composition: {comp_avg:.1f}/10"

    rec = None
    if not passed:
        rec = "Multi-character shots underperforming — try different character combinations or simpler compositions"

    return DimensionScore(
        name="Multi-Character Coherence",
        key="multi_character",
        passed=passed,
        score=score,
        details=details,
        recommendation=rec,
    )


def _score_overall_quality(shot_scores: list[ShotScore]) -> DimensionScore:
    """Overall quality from all completed shots."""
    scored = [s for s in shot_scores if s.quality_score is not None]

    if not scored:
        return DimensionScore(
            name="Overall Quality",
            key="overall_quality",
            passed=False,
            score=None,
            details="No quality scores yet",
            recommendation="Complete video generation and QC",
        )

    avg = sum(s.quality_score for s in scored) / len(scored)
    avg_10 = avg * 10  # normalize 0-1 to 0-10
    passed = avg >= 0.5  # 50% threshold

    worst = min(scored, key=lambda s: s.quality_score)

    return DimensionScore(
        name="Overall Quality",
        key="overall_quality",
        passed=passed,
        score=round(avg_10, 1),
        details=f"Avg {avg:.0%} across {len(scored)} shots. Worst: shot {worst.shot_number} ({worst.quality_score:.0%})",
        recommendation=f"Shot {worst.shot_number} dragging average — regenerate it" if not passed else None,
    )


async def score_trailer(trailer_id: str) -> dict:
    """Compute the full scorecard for a trailer and persist it.

    Returns the scorecard as a dict (JSON-serializable).
    """
    conn = await connect_direct()
    try:
        trailer = await conn.fetchrow(
            "SELECT * FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )
        if not trailer:
            raise ValueError(f"Trailer {trailer_id} not found")

        project = await conn.fetchrow(
            "SELECT id, name FROM projects WHERE id = $1", trailer["project_id"]
        )

        shots = await conn.fetch("""
            SELECT id, shot_number, shot_type, camera_angle, trailer_role,
                   generation_prompt, lora_name, image_lora, characters_present,
                   status, first_frame_path, output_video_path,
                   quality_score, qc_category_averages, qc_issues,
                   motion_tier, error_message
            FROM shots
            WHERE scene_id = $1
            ORDER BY shot_number
        """, trailer["scene_id"])

        shot_list = [dict(s) for s in shots]
        shot_scores = _build_shot_scores(shot_list)
        catalog = _load_lora_catalog()

        # Score each dimension
        dimensions = [
            _score_character_fidelity(shot_scores),
            _score_motion_effectiveness(shot_scores),
            _score_content_lora_pairing(shot_scores, catalog),
            _score_motion_tier(shot_scores),
            _score_pipeline_completeness(shot_scores),
            _score_multi_character(shot_scores),
            _score_overall_quality(shot_scores),
        ]

        # Collect recommendations
        recs = [d.recommendation for d in dimensions if d.recommendation]

        # Count pass/fail/skip
        pass_count = sum(1 for d in dimensions if d.passed)
        fail_count = sum(1 for d in dimensions if not d.passed and d.score is not None)
        skip_count = sum(1 for d in dimensions if not d.passed and d.score is None)

        scorable = pass_count + fail_count
        overall_pass = scorable > 0 and (pass_count / scorable) >= OVERALL_PASS_RATIO

        scorecard = TrailerScorecard(
            trailer_id=trailer_id,
            project_id=trailer["project_id"],
            project_name=project["name"] if project else "Unknown",
            scored_at=datetime.now(timezone.utc).isoformat(),
            dimensions=[asdict(d) for d in dimensions],
            overall_pass=overall_pass,
            pass_count=pass_count,
            fail_count=fail_count,
            skip_count=skip_count,
            recommendations=recs,
            shot_scores=[asdict(s) for s in shot_scores],
        )

        result = asdict(scorecard)

        # Persist to DB
        await conn.execute("""
            UPDATE trailers SET scorecard = $2::jsonb, updated_at = NOW()
            WHERE id = $1
        """, uuid.UUID(trailer_id), json.dumps(result))

        logger.info(
            f"Trailer {trailer_id} scored: {pass_count} pass, {fail_count} fail, "
            f"{skip_count} skip → {'PASS' if overall_pass else 'FAIL'}"
        )

        return result

    finally:
        await conn.close()


async def get_cached_scorecard(trailer_id: str) -> dict | None:
    """Return cached scorecard from DB, or None if not yet scored."""
    conn = await connect_direct()
    try:
        row = await conn.fetchval(
            "SELECT scorecard FROM trailers WHERE id = $1", uuid.UUID(trailer_id)
        )
        if row is None:
            return None
        if isinstance(row, str):
            return json.loads(row)
        return dict(row) if row else None
    finally:
        await conn.close()
