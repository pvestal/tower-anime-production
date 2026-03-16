"""Action-Reaction QC — optical flow analysis + frame-pair vision scoring.

Measures whether both characters/regions exhibit expected motion in generated videos.
Two independent scoring methods:

Level 1: Frame-pair vision comparison via gemma3:12b
  - Sends early + late frame pair with counter_motion context
  - Scores: action_initiation, reaction_presence, state_delta

Level 2: Optical flow region analysis via OpenCV (CPU-only, hard numbers)
  - Dense optical flow between consecutive frames
  - Splits frame into regions, measures flow magnitude per region
  - Scores: flow_magnitude_primary, flow_magnitude_secondary, motion_correlation
"""

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

import yaml

from packages.core.config import OLLAMA_URL, VISION_MODEL

logger = logging.getLogger(__name__)

_interaction_cache: dict | None = None


# ── LoRA Interaction Metadata ──────────────────────────────────────────

def get_interaction_metadata(lora_name: str) -> dict | None:
    """Look up layout, roles, actor/reactor motion from lora_catalog.yaml.

    Returns dict with:
        layout: "halves" | "top_bottom" | "whole"
        roles: {actor: "top"|"bottom"|"left"|"right", reactor: ...}
        actor_motion: str — expected action description
        reactor_motion: str — expected reaction description
        counter_motion: str — original counter_motion string
    Or None if the LoRA has no interaction metadata.
    """
    global _interaction_cache
    if _interaction_cache is None:
        from .catalog_loader import load_catalog
        _interaction_cache = load_catalog()

    pairs = _interaction_cache.get("video_lora_pairs", {})
    if not lora_name:
        return None

    # Normalize: strip path and extension for matching
    norm = lora_name.split("/")[-1].replace(".safetensors", "").lower()

    # Two-pass matching: exact filename match first, then fuzzy key match
    # This ensures wan22_assertive_cowgirl matches assertive_cowgirl, not cowgirl
    best_match = None
    best_score = 0

    for key, entry in pairs.items():
        if not entry:
            continue
        if not (entry.get("layout") or entry.get("counter_motion")):
            continue

        high = (entry.get("high") or "").lower()
        low = (entry.get("low") or "").lower()

        # Exact filename match in high/low paths (highest priority)
        if norm in high or norm in low:
            score = 100
        # Exact key match
        elif key == norm:
            score = 90
        # Key is substring of normalized name (e.g. "cowgirl" in "assertive_cowgirl")
        elif key in norm:
            score = len(key)  # longer key = more specific match
        else:
            continue

        if score > best_score:
            best_score = score
            best_match = {
                "layout": entry.get("layout", "halves"),
                "roles": entry.get("roles", {}),
                "actor_motion": entry.get("actor_motion", ""),
                "reactor_motion": entry.get("reactor_motion", entry.get("counter_motion", "")),
                "counter_motion": entry.get("counter_motion", ""),
                "label": entry.get("label", key),
                "lora_key": key,
            }

    return best_match


def invalidate_interaction_cache():
    """Clear cached catalog (call after YAML updates)."""
    global _interaction_cache
    _interaction_cache = None


# ── Level 2: Optical Flow (hard numbers, no model needed) ──────────────

def compute_optical_flow(
    frame_a_path: str,
    frame_b_path: str,
    layout: str = "halves",
) -> dict:
    """Compute dense optical flow between two frames and score motion per region.

    Args:
        frame_a_path: Early frame (start of clip)
        frame_b_path: Late frame (end of clip)
        layout: How to split regions.
            "halves" — left/right split (side-by-side characters)
            "top_bottom" — top/bottom split (stacked characters)
            "whole" — no split, just measure total flow

    Returns dict with:
        flow_magnitude_primary: float — avg pixel displacement in primary region
        flow_magnitude_secondary: float — avg pixel displacement in secondary region
        motion_correlation: float — correlation of flow vectors between regions (-1 to 1)
        both_regions_active: bool — both regions have significant motion
        total_flow: float — whole-frame average flow magnitude
        flow_ratio: float — ratio of secondary/primary (0 = only primary moves, 1 = equal)
    """
    try:
        a = cv2.imread(frame_a_path, cv2.IMREAD_GRAYSCALE)
        b = cv2.imread(frame_b_path, cv2.IMREAD_GRAYSCALE)

        if a is None or b is None:
            logger.warning("Optical flow: could not read frames")
            return _empty_flow_result()

        # Resize to consistent dimensions for speed (flow is resolution-sensitive)
        target_h, target_w = 360, 640
        a = cv2.resize(a, (target_w, target_h))
        b = cv2.resize(b, (target_w, target_h))

        flow = cv2.calcOpticalFlowFarneback(
            a, b, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
        )

        h, w = flow.shape[:2]
        magnitude = np.linalg.norm(flow, axis=2)
        total_flow = float(np.mean(magnitude))

        # Split into regions
        if layout == "top_bottom":
            primary_flow = flow[:h // 2]
            secondary_flow = flow[h // 2:]
            primary_mag = magnitude[:h // 2]
            secondary_mag = magnitude[h // 2:]
        elif layout == "halves":
            primary_flow = flow[:, :w // 2]
            secondary_flow = flow[:, w // 2:]
            primary_mag = magnitude[:, :w // 2]
            secondary_mag = magnitude[:, w // 2:]
        else:
            # Whole frame — no split
            return {
                "flow_magnitude_primary": total_flow,
                "flow_magnitude_secondary": total_flow,
                "motion_correlation": 1.0,
                "both_regions_active": total_flow > 0.5,
                "total_flow": total_flow,
                "flow_ratio": 1.0,
            }

        mag_primary = float(np.mean(primary_mag))
        mag_secondary = float(np.mean(secondary_mag))

        # Correlation of horizontal flow vectors between regions
        # (action-reaction: expect positive correlation for impact-style motion)
        try:
            # Flatten and sample to keep computation fast
            p_x = primary_flow[:, :, 0].flatten()
            s_x = secondary_flow[:, :, 0].flatten()
            # Match lengths (regions might differ slightly)
            min_len = min(len(p_x), len(s_x))
            if min_len > 1000:
                # Subsample for speed
                idx = np.random.default_rng(42).choice(min_len, 1000, replace=False)
                p_x = p_x[idx]
                s_x = s_x[idx]
            else:
                p_x = p_x[:min_len]
                s_x = s_x[:min_len]
            correlation = float(np.corrcoef(p_x, s_x)[0, 1])
            if np.isnan(correlation):
                correlation = 0.0
        except Exception:
            correlation = 0.0

        # Both regions active if above threshold
        motion_threshold = 0.5
        both_active = mag_primary > motion_threshold and mag_secondary > motion_threshold

        # Ratio: how much secondary moves relative to primary
        flow_ratio = mag_secondary / mag_primary if mag_primary > 0.01 else 0.0

        return {
            "flow_magnitude_primary": round(mag_primary, 3),
            "flow_magnitude_secondary": round(mag_secondary, 3),
            "motion_correlation": round(correlation, 3),
            "both_regions_active": both_active,
            "total_flow": round(total_flow, 3),
            "flow_ratio": round(min(flow_ratio, 5.0), 3),
        }

    except Exception as e:
        logger.warning(f"Optical flow computation failed: {e}")
        return _empty_flow_result()


def _empty_flow_result() -> dict:
    return {
        "flow_magnitude_primary": 0.0,
        "flow_magnitude_secondary": 0.0,
        "motion_correlation": 0.0,
        "both_regions_active": False,
        "total_flow": 0.0,
        "flow_ratio": 0.0,
    }


def extract_flow_frames(video_path: str, count: int = 6) -> list[str]:
    """Extract evenly-spaced frames for optical flow analysis.

    More frames than the 3 used for vision QC — flow needs denser sampling
    to catch temporal patterns. Returns paths to extracted PNGs.
    """
    import subprocess

    video = Path(video_path)
    if not video.exists():
        return []

    # Get duration
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 3.0
    except Exception:
        duration = 3.0

    # Extract frames at evenly-spaced timestamps
    timestamps = [duration * i / (count + 1) for i in range(1, count + 1)]
    base = video_path.rsplit(".", 1)[0]
    frame_paths = []

    for i, ts in enumerate(timestamps):
        out_path = f"{base}_flow_frame_{i}.png"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                 "-vframes", "1", "-q:v", "2", out_path],
                capture_output=True, timeout=10,
            )
            if Path(out_path).exists():
                frame_paths.append(out_path)
        except Exception:
            pass

    return frame_paths


def score_action_reaction_flow(video_path: str, layout: str = "halves") -> dict:
    """Full optical flow scoring pipeline for a video.

    Extracts multiple frame pairs and averages flow metrics across them.
    Returns aggregated scores suitable for storing in qc_category_averages.
    """
    frame_paths = extract_flow_frames(video_path, count=6)
    if len(frame_paths) < 2:
        return _empty_flow_result()

    # Compute flow between consecutive frame pairs
    pair_results = []
    for i in range(len(frame_paths) - 1):
        result = compute_optical_flow(frame_paths[i], frame_paths[i + 1], layout)
        pair_results.append(result)

    # Also compute flow between first and last frame (full action arc)
    arc_result = compute_optical_flow(frame_paths[0], frame_paths[-1], layout)

    # Cleanup extracted frames
    for fp in frame_paths:
        try:
            Path(fp).unlink(missing_ok=True)
        except Exception:
            pass

    if not pair_results:
        return _empty_flow_result()

    # Aggregate: average across pairs for sustained motion, arc for total change
    avg_primary = sum(r["flow_magnitude_primary"] for r in pair_results) / len(pair_results)
    avg_secondary = sum(r["flow_magnitude_secondary"] for r in pair_results) / len(pair_results)
    avg_correlation = sum(r["motion_correlation"] for r in pair_results) / len(pair_results)
    avg_total = sum(r["total_flow"] for r in pair_results) / len(pair_results)
    pairs_both_active = sum(1 for r in pair_results if r["both_regions_active"])
    flow_ratio = avg_secondary / avg_primary if avg_primary > 0.01 else 0.0

    # Convert to 1-10 scores for consistency with vision QC
    # flow magnitude: 0 = frozen, 2+ = strong motion → map to 1-10
    def flow_to_score(mag: float) -> float:
        return round(max(1.0, min(10.0, mag * 4.0 + 1.0)), 1)

    # Correlation: -1 to 1 → 1-10 (higher correlation = better action-reaction)
    def corr_to_score(corr: float) -> float:
        return round(max(1.0, min(10.0, (corr + 1) * 4.5 + 1)), 1)

    return {
        "flow_magnitude_primary": round(avg_primary, 3),
        "flow_magnitude_secondary": round(avg_secondary, 3),
        "motion_correlation": round(avg_correlation, 3),
        "both_regions_active": pairs_both_active > len(pair_results) * 0.5,
        "total_flow": round(avg_total, 3),
        "flow_ratio": round(min(flow_ratio, 5.0), 3),
        # Arc-level: did state change across full clip?
        "arc_flow_primary": arc_result["flow_magnitude_primary"],
        "arc_flow_secondary": arc_result["flow_magnitude_secondary"],
        # Scores on 1-10 scale
        "action_flow_score": flow_to_score(avg_primary),
        "reaction_flow_score": flow_to_score(avg_secondary),
        "correlation_score": corr_to_score(avg_correlation),
        "pairs_both_active": pairs_both_active,
        "pairs_total": len(pair_results),
    }


# ── Level 1: Frame-Pair Vision Scoring ─────────────────────────────────

async def score_action_reaction_vision(
    frame_early_path: str,
    frame_late_path: str,
    motion_prompt: str,
    counter_motion: str,
    character_slug: str | None = None,
) -> dict:
    """Send frame pair to gemma3:12b for action-reaction assessment.

    Args:
        frame_early_path: Frame from start of clip
        frame_late_path: Frame from end of clip
        motion_prompt: What the video was supposed to show
        counter_motion: Expected reaction from lora_catalog.yaml

    Returns dict with action_initiation, reaction_presence, state_delta (1-10).
    """
    import urllib.request

    try:
        with open(frame_early_path, "rb") as f:
            early_b64 = base64.b64encode(f.read()).decode()
        with open(frame_late_path, "rb") as f:
            late_b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        logger.warning(f"Frame-pair vision: could not read frames: {e}")
        return _empty_vision_result()

    char_context = f" The character involved is '{character_slug}'." if character_slug else ""

    prompt = (
        f"You are comparing two frames from the SAME video clip.\n"
        f"Image 1: EARLY frame (start of action)\n"
        f"Image 2: LATE frame (after action completes)\n\n"
        f"The intended action: \"{motion_prompt}\"\n"
        f"The expected reaction/counter-motion: \"{counter_motion}\"\n"
        f"{char_context}\n\n"
        f"Score each 1-10. Be STRICT — 7+ means clearly visible, 5 means ambiguous, 3 means absent:\n"
        f"- action_initiation: Does Image 1 show the action beginning or the setup for it? "
        f"(1=no action visible, 10=action clearly starting)\n"
        f"- reaction_presence: Does Image 2 show the expected reaction/counter-motion? "
        f"(1=no reaction at all, 10=reaction clearly visible)\n"
        f"- state_delta: Has something PHYSICALLY CHANGED between the two frames? "
        f"Compare body positions, expressions, spatial relationships. "
        f"(1=frames are identical/frozen, 10=clear physical change matching the described motion)\n"
        f"- temporal_coherence: Do these two frames look like they belong to the same "
        f"continuous motion sequence? (1=completely unrelated, 10=natural progression)\n\n"
        f"Reply in EXACTLY this JSON format, nothing else:\n"
        f'{{"action_initiation": N, "reaction_presence": N, "state_delta": N, '
        f'"temporal_coherence": N}}'
    )

    payload = json.dumps({
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [early_b64, late_b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=90)
        result = json.loads(resp.read())
        text = result.get("response", "").strip()

        # Extract JSON
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)

        scores = {}
        for key in ("action_initiation", "reaction_presence", "state_delta", "temporal_coherence"):
            val = parsed.get(key, 5)
            scores[key] = max(1, min(10, int(val)))

        return scores

    except Exception as e:
        logger.warning(f"Frame-pair vision scoring failed: {e}")
        return _empty_vision_result()


def _empty_vision_result() -> dict:
    return {
        "action_initiation": 5,
        "reaction_presence": 5,
        "state_delta": 5,
        "temporal_coherence": 5,
    }


# ── Combined Scoring ───────────────────────────────────────────────────

async def score_action_reaction(
    video_path: str,
    qc_frame_paths: list[str],
    motion_prompt: str,
    counter_motion: str | None,
    character_slug: str | None = None,
    lora_name: str | None = None,
) -> dict | None:
    """Run both Level 1 (vision) and Level 2 (optical flow) action-reaction scoring.

    Pulls layout and role metadata from lora_catalog.yaml to know HOW to split
    the frame (top/bottom vs left/right) and WHAT motion to expect per region.

    Only runs when counter_motion is defined (indicates multi-entity interaction).
    Returns combined scores or None if not applicable.
    """
    if not counter_motion:
        return None

    # Pull interaction metadata from catalog
    metadata = get_interaction_metadata(lora_name or "") if lora_name else None
    layout = (metadata or {}).get("layout", "halves")
    actor_motion = (metadata or {}).get("actor_motion", motion_prompt)
    reactor_motion = (metadata or {}).get("reactor_motion", counter_motion)
    roles = (metadata or {}).get("roles", {})

    result = {"metadata": {
        "layout": layout,
        "roles": roles,
        "actor_motion": actor_motion,
        "reactor_motion": reactor_motion,
    }}

    # Level 2: Optical flow (CPU, fast, hard numbers) — uses layout from catalog
    try:
        flow_scores = score_action_reaction_flow(video_path, layout)
        result["optical_flow"] = flow_scores
    except Exception as e:
        logger.warning(f"Action-reaction optical flow failed: {e}")
        result["optical_flow"] = _empty_flow_result()

    # Level 1: Vision frame-pair comparison (uses gemma3:12b on AMD)
    # Pass both actor_motion and reactor_motion for more precise scoring
    if len(qc_frame_paths) >= 2:
        try:
            vision_scores = await score_action_reaction_vision(
                frame_early_path=qc_frame_paths[0],
                frame_late_path=qc_frame_paths[-1],
                motion_prompt=actor_motion,
                counter_motion=reactor_motion,
                character_slug=character_slug,
            )
            result["vision_pair"] = vision_scores
        except Exception as e:
            logger.warning(f"Action-reaction vision scoring failed: {e}")
            result["vision_pair"] = _empty_vision_result()
    else:
        result["vision_pair"] = _empty_vision_result()

    # Composite score: weighted average of both methods
    flow = result["optical_flow"]
    vision = result["vision_pair"]

    # Hard gate: if optical flow says both regions are frozen, override vision
    if not flow["both_regions_active"] and flow["total_flow"] < 0.3:
        state_delta_override = min(vision["state_delta"], 3)
    else:
        state_delta_override = vision["state_delta"]

    # Map flow regions to actor/reactor based on roles
    actor_role = roles.get("actor", "left")
    if actor_role in ("top", "left"):
        actor_flow = flow["flow_magnitude_primary"]
        reactor_flow = flow["flow_magnitude_secondary"]
    else:
        actor_flow = flow["flow_magnitude_secondary"]
        reactor_flow = flow["flow_magnitude_primary"]

    def flow_to_score(mag: float) -> float:
        return round(max(1.0, min(10.0, mag * 4.0 + 1.0)), 1)

    result["composite"] = {
        "action_score": round((vision["action_initiation"] + flow_to_score(actor_flow)) / 2, 1),
        "reaction_score": round((vision["reaction_presence"] + flow_to_score(reactor_flow)) / 2, 1),
        "state_delta": round((state_delta_override + flow["correlation_score"]) / 2, 1),
        "both_active": flow["both_regions_active"],
        "actor_flow": round(actor_flow, 3),
        "reactor_flow": round(reactor_flow, 3),
    }

    return result
