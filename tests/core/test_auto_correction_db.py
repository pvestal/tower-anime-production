"""Tests for async functions in packages.core.auto_correction — DB-dependent logic.

Tests apply_corrections (daily limit check, strategy application),
check_quality_gates (gate evaluation), and constants.
"""

import copy
from unittest.mock import AsyncMock, patch

import pytest

from packages.core.auto_correction import (
    apply_corrections,
    check_quality_gates,
    get_correction_stats,
    MAX_CORRECTIONS_PER_DAY,
)

# A minimal ComfyUI workflow dict with KSampler and CLIPTextEncode nodes.
# Used as input to apply_corrections.
SAMPLE_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 12345,
            "steps": 25,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "masterpiece, best quality, Illumination 3D CGI, tall thin man in green cap",
        },
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "worst quality, low quality, blurry, deformed",
        },
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": 512,
            "height": 768,
            "batch_size": 1,
        },
    },
}


@pytest.fixture
def _patch_correction_pool(mock_db_pool):
    """Patch get_pool where auto_correction.py actually uses it."""
    with patch("packages.core.auto_correction.get_pool", new_callable=AsyncMock, return_value=mock_db_pool):
        # Also patch audit.get_pool since apply_corrections calls log_decision internally
        with patch("packages.core.audit.get_pool", new_callable=AsyncMock, return_value=mock_db_pool):
            yield


@pytest.mark.unit
async def test_apply_corrections_returns_corrected_workflow(_patch_correction_pool, mock_conn):
    """apply_corrections returns a modified workflow when categories match fix strategies."""
    # Daily limit not reached
    mock_conn.fetchval.return_value = 0
    # log_decision fetchrow (from audit module)
    mock_conn.fetchrow.return_value = {"id": 1}

    workflow = copy.deepcopy(SAMPLE_WORKFLOW)
    result = await apply_corrections(
        workflow=workflow,
        categories=["bad_quality"],
        character_slug="luigi",
        quality_score=0.3,
    )

    assert result is not None
    # fix_quality should have increased steps and/or CFG
    sampler_node = result["3"]
    # euler should be upgraded to dpmpp_2m
    assert sampler_node["inputs"]["sampler_name"] == "dpmpp_2m"
    assert sampler_node["inputs"]["scheduler"] == "karras"
    # Steps should be increased (from 25, capped at 50)
    assert sampler_node["inputs"]["steps"] > 25
    # CFG should be nudged up (from 7.0)
    assert sampler_node["inputs"]["cfg"] > 7.0
    # Original workflow should be untouched
    assert workflow["3"]["inputs"]["sampler_name"] == "euler"


@pytest.mark.unit
async def test_apply_corrections_returns_none_when_daily_limit_reached(_patch_correction_pool, mock_conn):
    """apply_corrections returns None when daily correction limit is reached."""
    mock_conn.fetchval.return_value = MAX_CORRECTIONS_PER_DAY

    workflow = copy.deepcopy(SAMPLE_WORKFLOW)
    result = await apply_corrections(
        workflow=workflow,
        categories=["bad_quality"],
        character_slug="luigi",
        quality_score=0.3,
    )

    assert result is None


@pytest.mark.unit
async def test_apply_corrections_returns_none_when_no_strategies_match(_patch_correction_pool, mock_conn):
    """apply_corrections returns None when categories don't map to any fix strategies."""
    mock_conn.fetchval.return_value = 0

    workflow = copy.deepcopy(SAMPLE_WORKFLOW)
    result = await apply_corrections(
        workflow=workflow,
        categories=["unknown_category_xyz"],
        character_slug="luigi",
        quality_score=0.6,  # Above 0.4, so fix_quality won't auto-add
    )

    assert result is None


@pytest.mark.unit
async def test_check_quality_gates_passes_above_thresholds(_patch_correction_pool, mock_conn):
    """check_quality_gates passes when score is above all gate thresholds."""
    mock_conn.fetch.return_value = [
        {"gate_name": "auto_reject_threshold", "gate_type": "auto_reject", "threshold_value": 0.4},
        {"gate_name": "scene_shot_minimum", "gate_type": "overall_consistency", "threshold_value": 0.4},
    ]

    result = await check_quality_gates(quality_score=0.85, solo=True)

    assert result["passed"] is True
    assert len(result["gates"]) == 2
    assert all(g["passed"] for g in result["gates"])


@pytest.mark.unit
async def test_check_quality_gates_fails_below_reject_threshold(_patch_correction_pool, mock_conn):
    """check_quality_gates fails when score is below auto_reject threshold."""
    mock_conn.fetch.return_value = [
        {"gate_name": "auto_reject_threshold", "gate_type": "auto_reject", "threshold_value": 0.4},
        {"gate_name": "auto_approve_threshold", "gate_type": "auto_approve", "threshold_value": 0.8},
    ]

    result = await check_quality_gates(quality_score=0.3, solo=True)

    assert result["passed"] is False
    # The auto_reject gate should fail (0.3 < 0.4)
    reject_gate = next(g for g in result["gates"] if g["name"] == "auto_reject_threshold")
    assert reject_gate["passed"] is False
    # The auto_approve gate should also fail (0.3 < 0.8)
    approve_gate = next(g for g in result["gates"] if g["name"] == "auto_approve_threshold")
    assert approve_gate["passed"] is False
