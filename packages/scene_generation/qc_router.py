"""QC Router — multi-dimensional video quality evaluation and routing decisions.

Evaluates generated video against expectations (identity, motion tier, pose,
temporal coherence) and routes to: pass, retry, refine, extend, or manual review.

Metrics framework based on per-dimension evaluation rather than single scalar.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class QCAction(Enum):
    PASS_FINAL = "pass_final"
    RETRY_SAME_CONFIG = "retry_same_config"
    RETRY_ADJUST_CONFIG = "retry_adjust_config"
    SEND_TO_REFINEMENT = "send_to_refinement"
    EXTEND_VIDEO = "extend_video"
    MANUAL_REVIEW = "manual_review"
    HARD_FAIL = "hard_fail"


class RetryReason(Enum):
    IDENTITY_LOW = "identity_low"
    MOTION_MISMATCH = "motion_mismatch"
    TEMPORAL_BAD = "temporal_bad"
    QUALITY_BAD = "quality_bad"
    POSE_MISMATCH = "pose_mismatch"
    MULTI_ISSUE = "multi_issue"


@dataclass
class QCExpectations:
    expected_engine: str                # "dasiwa", "wan22_14b", "ltx", "framepack"
    expected_motion_tier: str           # "low", "medium", "high", "extreme"
    expected_identity: str              # character slug, e.g. "soraya"
    expected_pose: str                  # "idle", "doggy", "cowgirl", "embrace", ...
    target_duration_sec: float = 5.0
    variant: Optional[str] = None       # "A" | "B"


@dataclass
class QCMeasurements:
    engine_used: str = ""
    duration_sec: float = 0.0
    global_quality: float = 0.0         # 0-1 scalar from vision QC
    identity_score: float = 0.0         # 0-1 face/embedding similarity
    pose_match_score: float = 1.0       # 0-1 classifier confidence
    motion_intensity_score: float = 0.0 # 0-1 normalized optical flow magnitude
    motion_smoothness_score: float = 1.0# 0-1, high = smooth
    temporal_flicker_score: float = 0.0 # 0-1, high = flickery (bad)
    num_artifact_frames: int = 0
    num_retries: int = 0
    max_retries: int = 3
    retry_reasons: list = field(default_factory=list)


# ── Thresholds ────────────────────────────────────────────────────────────

# Global quality
QUALITY_GOOD = 0.70
QUALITY_BORDERLINE = 0.55

# Identity — calibrated for illustrated/anime faces via ArcFace (photo-trained).
# Reference keyframes score 0.79-0.88 against averaged embedding.
# Video frames score 0.45-0.64 due to motion blur and angle changes.
IDENTITY_OK = 0.55
IDENTITY_BORDERLINE = 0.45

# Pose
POSE_OK = 0.85
POSE_BAD = 0.70

# Temporal
SMOOTHNESS_GOOD = 0.75
SMOOTHNESS_BORDERLINE = 0.60
FLICKER_GOOD = 0.25
FLICKER_BORDERLINE = 0.40

# Artifacts
ARTIFACT_OK = 2
ARTIFACT_BAD = 10

# Motion tier bands: (min, max) — score is 0-1 normalized optical flow
MOTION_TIER_BANDS = {
    "low":     (0.10, 0.30),
    "medium":  (0.30, 0.55),
    "high":    (0.55, 0.80),
    "extreme": (0.80, 1.00),
}
MOTION_TIER_MARGIN = 0.10


def is_motion_tier_consistent(expected: str, score: float) -> bool:
    """Check if motion intensity falls within expected tier band (with margin)."""
    band = MOTION_TIER_BANDS.get(expected)
    if not band:
        return True  # unknown tier, don't gate
    lo, hi = band
    return (lo - MOTION_TIER_MARGIN) <= score <= (hi + MOTION_TIER_MARGIN)


# ── Main Router ───────────────────────────────────────────────────────────

def decide_qc_action(
    expectations: QCExpectations,
    m: QCMeasurements,
) -> tuple[QCAction, list[RetryReason]]:
    """Decide what to do with a generated video based on multi-dimensional QC.

    Returns (action, [reasons]) where reasons explain why retry/refine was chosen.
    """
    reasons: list[RetryReason] = []

    # 0. Hard mismatches
    if m.engine_used and m.engine_used != expectations.expected_engine:
        logger.warning(f"QC: engine mismatch: used={m.engine_used}, expected={expectations.expected_engine}")
        return QCAction.HARD_FAIL, [RetryReason.QUALITY_BAD]

    if m.num_artifact_frames > ARTIFACT_BAD:
        return QCAction.MANUAL_REVIEW, [RetryReason.QUALITY_BAD]

    # 1. Identity and pose gates
    identity_ok = m.identity_score >= IDENTITY_OK
    identity_borderline = IDENTITY_BORDERLINE <= m.identity_score < IDENTITY_OK
    identity_bad = m.identity_score < IDENTITY_BORDERLINE

    pose_ok = m.pose_match_score >= POSE_OK
    pose_bad = m.pose_match_score < POSE_BAD

    # 2. Motion tier consistency
    tier_ok = is_motion_tier_consistent(expectations.expected_motion_tier, m.motion_intensity_score)

    # 3. Temporal coherence
    temporal_good = (m.motion_smoothness_score >= SMOOTHNESS_GOOD and
                     m.temporal_flicker_score <= FLICKER_GOOD)
    temporal_borderline = (
        (SMOOTHNESS_BORDERLINE <= m.motion_smoothness_score < SMOOTHNESS_GOOD) or
        (FLICKER_GOOD < m.temporal_flicker_score <= FLICKER_BORDERLINE)
    )
    temporal_bad = (m.motion_smoothness_score < SMOOTHNESS_BORDERLINE or
                    m.temporal_flicker_score > FLICKER_BORDERLINE)

    # 4. Global quality
    if m.global_quality >= QUALITY_GOOD:
        quality_level = "good"
    elif m.global_quality >= QUALITY_BORDERLINE:
        quality_level = "borderline"
    else:
        quality_level = "bad"

    # Build reason list
    if identity_bad:
        reasons.append(RetryReason.IDENTITY_LOW)
    if not tier_ok:
        reasons.append(RetryReason.MOTION_MISMATCH)
    if temporal_bad:
        reasons.append(RetryReason.TEMPORAL_BAD)
    if quality_level == "bad":
        reasons.append(RetryReason.QUALITY_BAD)
    if pose_bad:
        reasons.append(RetryReason.POSE_MISMATCH)

    # 5. Decision tree

    # Perfect: accept
    if (quality_level == "good" and identity_ok and pose_ok and
            tier_ok and temporal_good):
        if m.duration_sec + 0.25 >= expectations.target_duration_sec:
            return QCAction.PASS_FINAL, []
        else:
            return QCAction.EXTEND_VIDEO, []

    # Good visual, borderline identity/temporal → refine after at least 1 retry
    if (quality_level == "good" and identity_borderline and
            temporal_borderline and m.num_retries >= 1):
        return QCAction.SEND_TO_REFINEMENT, reasons

    # Borderline quality but otherwise aligned → refine
    if (quality_level == "borderline" and identity_ok and pose_ok and
            tier_ok and temporal_good):
        return QCAction.SEND_TO_REFINEMENT, reasons or [RetryReason.QUALITY_BAD]

    # Bad quality or obvious mismatch, retries left → retry with adjustments
    if quality_level == "bad" or not tier_ok or pose_bad:
        if len(reasons) > 2:
            reasons = [RetryReason.MULTI_ISSUE]
        if m.num_retries < m.max_retries:
            return QCAction.RETRY_ADJUST_CONFIG, reasons
        else:
            return QCAction.MANUAL_REVIEW, reasons

    # Identity bad (< 0.80) with retries left → retry with identity-preserving adjustments
    if identity_bad and m.num_retries < m.max_retries:
        return QCAction.RETRY_ADJUST_CONFIG, [RetryReason.IDENTITY_LOW]

    # Temporal issues only → retry same config (different seed may fix jitter)
    if temporal_bad:
        if m.num_retries < m.max_retries:
            return QCAction.RETRY_SAME_CONFIG, [RetryReason.TEMPORAL_BAD]
        else:
            return QCAction.SEND_TO_REFINEMENT, [RetryReason.TEMPORAL_BAD]

    # Identity borderline with retries left
    if identity_borderline and m.num_retries < m.max_retries:
        return QCAction.RETRY_ADJUST_CONFIG, [RetryReason.IDENTITY_LOW]

    # Identity bad, retries exhausted → refinement before manual review
    if identity_bad and m.num_retries >= m.max_retries:
        return QCAction.SEND_TO_REFINEMENT, [RetryReason.IDENTITY_LOW]

    # Fallback
    return QCAction.MANUAL_REVIEW, reasons or [RetryReason.MULTI_ISSUE]


# ── Retry-Adjust Config Presets ───────────────────────────────────────────

# Per engine, per tier, per retry-reason: what knobs to change.
# Values are DELTAS applied to current config (or absolute overrides where noted).

RETRY_ADJUSTMENTS = {
    "dasiwa": {
        # Reason: identity_low — reduce strength, add steps (closer to keyframe)
        RetryReason.IDENTITY_LOW: {
            "low":     {"steps_delta": +1, "strength_delta": -0.10, "cfg_delta": 0.0},
            "medium":  {"steps_delta": +2, "strength_delta": -0.10, "cfg_delta": 0.0},
            "high":    {"steps_delta": +2, "strength_delta": -0.10, "cfg_delta": 0.0},
            "extreme": {"steps_delta": +2, "strength_delta": -0.10, "cfg_delta": 0.0},
        },
        # Reason: motion_mismatch (too low) — increase strength
        RetryReason.MOTION_MISMATCH: {
            "low":     {"steps_delta": 0, "strength_delta": +0.10, "cfg_delta": 0.0},
            "medium":  {"steps_delta": 0, "strength_delta": +0.07, "cfg_delta": 0.0},
            "high":    {"steps_delta": 0, "strength_delta": +0.05, "cfg_delta": 0.0},
            "extreme": {"steps_delta": 0, "strength_delta": 0.0,   "cfg_delta": +0.3},
        },
        # Reason: temporal_bad — more steps, slightly lower CFG
        RetryReason.TEMPORAL_BAD: {
            "low":     {"steps_delta": +2, "strength_delta": 0.0, "cfg_delta": -0.1},
            "medium":  {"steps_delta": +2, "strength_delta": 0.0, "cfg_delta": -0.1},
            "high":    {"steps_delta": +2, "strength_delta": 0.0, "cfg_delta": -0.2},
            "extreme": {"steps_delta": +2, "strength_delta": 0.0, "cfg_delta": -0.5},
        },
        # Reason: quality_bad — combined: more steps + lower strength + lower CFG
        RetryReason.QUALITY_BAD: {
            "low":     {"steps_delta": +2, "strength_delta": -0.08, "cfg_delta": -0.1},
            "medium":  {"steps_delta": +2, "strength_delta": -0.08, "cfg_delta": -0.1},
            "high":    {"steps_delta": +2, "strength_delta": -0.08, "cfg_delta": -0.2},
            "extreme": {"steps_delta": +2, "strength_delta": -0.08, "cfg_delta": -0.3},
        },
        # Multi-issue: aggressive stabilization
        RetryReason.MULTI_ISSUE: {
            "low":     {"steps_delta": +2, "strength_delta": -0.10, "cfg_delta": -0.1},
            "medium":  {"steps_delta": +3, "strength_delta": -0.12, "cfg_delta": -0.1},
            "high":    {"steps_delta": +3, "strength_delta": -0.12, "cfg_delta": -0.2},
            "extreme": {"steps_delta": +3, "strength_delta": -0.12, "cfg_delta": -0.3},
        },
    },
    "wan22_14b": {
        RetryReason.IDENTITY_LOW: {
            "low":     {"steps_delta": +4, "strength_delta": -0.10, "cfg_delta": -0.5},
            "medium":  {"steps_delta": +4, "strength_delta": -0.10, "cfg_delta": -0.5},
            "high":    {"steps_delta": +4, "strength_delta": -0.10, "cfg_delta": -0.5},
            "extreme": {"steps_delta": +4, "strength_delta": -0.10, "cfg_delta": -0.5},
        },
        RetryReason.MOTION_MISMATCH: {
            "low":     {"steps_delta": 0, "strength_delta": +0.10, "cfg_delta": +0.5},
            "medium":  {"steps_delta": 0, "strength_delta": +0.08, "cfg_delta": +0.5},
            "high":    {"steps_delta": 0, "strength_delta": +0.06, "cfg_delta": +0.5},
            "extreme": {"steps_delta": 0, "strength_delta": 0.0,   "cfg_delta": +0.5},
        },
        RetryReason.TEMPORAL_BAD: {
            "low":     {"steps_delta": +4, "strength_delta": 0.0, "cfg_delta": -0.5},
            "medium":  {"steps_delta": +4, "strength_delta": 0.0, "cfg_delta": -0.5},
            "high":    {"steps_delta": +4, "strength_delta": 0.0, "cfg_delta": -0.5},
            "extreme": {"steps_delta": +4, "strength_delta": 0.0, "cfg_delta": -0.5},
        },
        RetryReason.QUALITY_BAD: {
            "low":     {"steps_delta": +4, "strength_delta": -0.08, "cfg_delta": -0.5},
            "medium":  {"steps_delta": +4, "strength_delta": -0.08, "cfg_delta": -0.5},
            "high":    {"steps_delta": +4, "strength_delta": -0.08, "cfg_delta": -0.5},
            "extreme": {"steps_delta": +4, "strength_delta": -0.08, "cfg_delta": -0.5},
        },
        RetryReason.MULTI_ISSUE: {
            "low":     {"steps_delta": +4, "strength_delta": -0.10, "cfg_delta": -0.5},
            "medium":  {"steps_delta": +6, "strength_delta": -0.12, "cfg_delta": -0.5},
            "high":    {"steps_delta": +6, "strength_delta": -0.12, "cfg_delta": -0.5},
            "extreme": {"steps_delta": +6, "strength_delta": -0.12, "cfg_delta": -0.5},
        },
    },
}


def get_retry_adjustments(
    engine: str,
    motion_tier: str,
    reasons: list[RetryReason],
    current_config: dict,
) -> dict:
    """Apply retry adjustments to current generation config.

    Args:
        engine: "dasiwa" or "wan22_14b"
        motion_tier: "low", "medium", "high", "extreme"
        reasons: list of RetryReason from decide_qc_action
        current_config: dict with keys like "steps", "strength", "cfg"

    Returns:
        Adjusted config dict with clamped values.
    """
    engine_presets = RETRY_ADJUSTMENTS.get(engine, RETRY_ADJUSTMENTS.get("dasiwa", {}))

    # Pick primary reason (first one, or MULTI_ISSUE)
    reason = reasons[0] if reasons else RetryReason.QUALITY_BAD
    if len(reasons) > 1:
        reason = RetryReason.MULTI_ISSUE

    tier_adjustments = engine_presets.get(reason, {}).get(motion_tier, {})
    if not tier_adjustments:
        logger.warning(f"QC retry: no adjustments for {engine}/{motion_tier}/{reason}")
        return current_config

    adjusted = dict(current_config)

    # Apply deltas with clamping
    if "steps" in adjusted:
        adjusted["steps"] = max(2, adjusted["steps"] + tier_adjustments.get("steps_delta", 0))
    if "strength" in adjusted or "denoise" in adjusted:
        key = "strength" if "strength" in adjusted else "denoise"
        adjusted[key] = max(0.3, min(1.0,
            adjusted[key] + tier_adjustments.get("strength_delta", 0)))
    if "cfg" in adjusted or "guidance_scale" in adjusted:
        key = "cfg" if "cfg" in adjusted else "guidance_scale"
        adjusted[key] = max(0.5, min(10.0,
            adjusted[key] + tier_adjustments.get("cfg_delta", 0)))

    logger.info(
        f"QC retry adjust ({engine}/{motion_tier}/{reason.value}): "
        f"steps={adjusted.get('steps')}, strength={adjusted.get('strength', adjusted.get('denoise')):.2f}, "
        f"cfg={adjusted.get('cfg', adjusted.get('guidance_scale'))}"
    )

    return adjusted


# ── Build from DB row ─────────────────────────────────────────────────────

def expectations_from_shot(shot: dict) -> QCExpectations:
    """Build QCExpectations from a shots DB row."""
    return QCExpectations(
        expected_engine=shot.get("expected_engine") or shot.get("video_engine") or "dasiwa",
        expected_motion_tier=shot.get("expected_motion_tier") or shot.get("motion_tier") or "medium",
        expected_identity=shot.get("expected_identity") or "",
        expected_pose=shot.get("expected_pose") or "",
        target_duration_sec=float(shot.get("duration_seconds") or 5),
        variant=shot.get("variant"),
    )


def measurements_from_shot(shot: dict) -> QCMeasurements:
    """Build QCMeasurements from a shots DB row + stored QC data.

    For metrics not yet computed (identity, motion, temporal), uses
    reasonable defaults that won't trigger false failures. As metric
    computation is wired in, these will be replaced with real values.
    """
    quality = float(shot.get("quality_score") or 0.0)

    return QCMeasurements(
        engine_used=shot.get("video_engine") or "",
        duration_sec=float(shot.get("duration_seconds") or 5),
        global_quality=quality,
        # Default to passing thresholds until real metrics are wired in
        identity_score=0.95 if quality >= 0.5 else 0.85,
        pose_match_score=0.90,
        motion_intensity_score=_estimate_motion_from_tier(
            shot.get("motion_tier") or "medium"),
        motion_smoothness_score=0.80 if quality >= 0.5 else 0.65,
        temporal_flicker_score=0.15 if quality >= 0.5 else 0.35,
        num_artifact_frames=0,
        num_retries=int(shot.get("retry_count") or 0),
        max_retries=3,
    )


def _estimate_motion_from_tier(tier: str) -> float:
    """Estimate motion intensity from tier name (placeholder until optical flow)."""
    return {
        "low": 0.20,
        "medium": 0.42,
        "high": 0.67,
        "extreme": 0.88,
    }.get(tier, 0.42)
