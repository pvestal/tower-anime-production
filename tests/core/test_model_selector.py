"""Tests for packages.core.model_selector — checkpoint/param recommendation.

Recommend_params combines project-level SSOT with learned patterns.
Detect_drift compares rolling quality averages to historical averages.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.core.model_selector import (
    recommend_params,
    detect_drift,
    character_quality_summary,
    MIN_CONFIDENCE_SAMPLES,
    QUALITY_FLOOR,
    DRIFT_ALERT_THRESHOLD,
)


@pytest.fixture
def _patch_selector_pool(mock_db_pool):
    """Patch get_pool where model_selector.py actually uses it."""
    with patch("packages.core.model_selector.get_pool", new_callable=AsyncMock, return_value=mock_db_pool):
        yield


@pytest.mark.unit
def test_min_confidence_samples_is_five():
    """MIN_CONFIDENCE_SAMPLES is 5."""
    assert MIN_CONFIDENCE_SAMPLES == 5


@pytest.mark.unit
def test_quality_floor_is_065():
    """QUALITY_FLOOR is 0.65."""
    assert QUALITY_FLOOR == 0.65


@pytest.mark.unit
async def test_recommend_params_confidence_none_insufficient_data(_patch_selector_pool, mock_conn):
    """recommend_params returns confidence='none' when sample_count < MIN_CONFIDENCE_SAMPLES."""
    # param_row with too few samples
    mock_conn.fetchrow.return_value = {
        "sample_count": 3,
        "avg_quality": 0.7,
        "median_cfg": 8.0,
        "median_steps": 30,
        "best_sampler": "dpmpp_2m",
        "best_scheduler": "karras",
    }
    # _get_learned_negatives fetch returns empty
    mock_conn.fetch.return_value = []

    with patch("packages.lora_training.feedback.REJECTION_NEGATIVE_MAP", {}):
        result = await recommend_params("luigi")

    assert result["confidence"] == "none"
    assert result["sample_count"] == 3
    assert result["learned_negatives"] == ""


@pytest.mark.unit
async def test_recommend_params_full_recommendations(_patch_selector_pool, mock_conn):
    """recommend_params returns full recommendations with confidence level when data is sufficient."""
    mock_conn.fetchrow.side_effect = [
        # First call: param_row with enough samples
        {
            "sample_count": 15,
            "avg_quality": 0.85,
            "median_cfg": 8.5,
            "median_steps": 40,
            "best_sampler": "dpmpp_2m",
            "best_scheduler": "karras",
        },
        # Second call: best checkpoint (called when project_name given)
        {
            "checkpoint_model": "realcartoonPixar_v12.safetensors",
            "avg_q": 0.88,
            "n": 10,
        },
    ]
    # _get_learned_negatives fetch returns empty
    mock_conn.fetch.return_value = []

    with patch("packages.lora_training.feedback.REJECTION_NEGATIVE_MAP", {}):
        result = await recommend_params("luigi", project_name="Test Project")

    assert result["confidence"] == "medium"  # 15 samples: 10 <= n < 25 => medium
    assert result["sample_count"] == 15
    assert result["avg_quality"] == 0.85
    assert result["cfg_scale"] == 8.5
    assert result["steps"] == 40
    assert result["sampler"] == "dpmpp_2m"
    assert result["scheduler"] == "karras"
    assert result["checkpoint"]["model"] == "realcartoonPixar_v12.safetensors"
    assert result["learned_negatives"] == ""


@pytest.mark.unit
async def test_recommend_params_includes_learned_negatives(_patch_selector_pool, mock_conn):
    """recommend_params includes learned_negatives from rejection patterns with freq >= 2."""
    mock_conn.fetchrow.side_effect = [
        # param_row
        {
            "sample_count": 8,
            "avg_quality": 0.78,
            "median_cfg": 8.0,
            "median_steps": 35,
            "best_sampler": "dpmpp_2m",
            "best_scheduler": "karras",
        },
        # No project_name passed, so no checkpoint query
    ]
    # _get_learned_negatives: fetch returns rejection categories
    mock_conn.fetch.return_value = [
        {"category": "wrong_appearance", "freq": 3},
        {"category": "not_solo", "freq": 2},
        {"category": "wrong_pose", "freq": 1},  # freq < 2, should be excluded
    ]

    mock_map = {
        "wrong_appearance": "wrong colors, inaccurate character design, wrong outfit",
        "not_solo": "multiple characters, crowd, group shot",
        "wrong_pose": "awkward pose, unnatural position",
    }
    with patch("packages.lora_training.feedback.REJECTION_NEGATIVE_MAP", mock_map):
        result = await recommend_params("bowser")

    assert result["confidence"] == "low"  # 8 samples: 5 <= n < 10 => low
    negatives = result["learned_negatives"]
    assert "wrong colors, inaccurate character design, wrong outfit" in negatives
    assert "multiple characters, crowd, group shot" in negatives
    # wrong_pose (freq=1) should NOT be included
    assert "awkward pose" not in negatives


@pytest.mark.unit
async def test_detect_drift_returns_empty_when_no_drift(_patch_selector_pool, mock_conn):
    """detect_drift returns empty list when no characters are drifting."""
    mock_conn.fetch.return_value = []

    result = await detect_drift(project_name="Test Project")

    assert result == []


@pytest.mark.unit
async def test_detect_drift_returns_alerts_for_declining_characters(_patch_selector_pool, mock_conn):
    """detect_drift returns alerts for characters with declining quality."""
    mock_conn.fetch.return_value = [
        {
            "character_slug": "bowser",
            "recent_avg": 0.50,
            "overall_avg": 0.75,
            "recent_count": 10,
            "total_count": 40,
        },
    ]

    result = await detect_drift(project_name="Test Project")

    assert len(result) == 1
    assert result[0]["character_slug"] == "bowser"
    assert result[0]["recent_avg"] == 0.50
    assert result[0]["overall_avg"] == 0.75
    assert result[0]["drift"] == -0.25
    assert result[0]["alert"] is True  # 0.50 < DRIFT_ALERT_THRESHOLD (0.55)


@pytest.mark.unit
async def test_character_quality_summary_returns_per_character_data(_patch_selector_pool, mock_conn):
    """character_quality_summary returns per-character aggregated data."""
    mock_conn.fetch.return_value = [
        {
            "character_slug": "luigi",
            "total": 20,
            "approved": 15,
            "rejected": 5,
            "avg_quality": 0.85,
            "best_quality": 0.95,
            "worst_quality": 0.60,
            "last_generated": None,
        },
        {
            "character_slug": "bowser",
            "total": 10,
            "approved": 4,
            "rejected": 6,
            "avg_quality": 0.65,
            "best_quality": 0.80,
            "worst_quality": 0.40,
            "last_generated": None,
        },
    ]

    result = await character_quality_summary("Super Mario Galaxy Anime Adventure")

    assert len(result) == 2
    assert result[0]["character_slug"] == "luigi"
    assert result[0]["approval_rate"] == 0.75
    assert result[0]["avg_quality"] == 0.85
    assert result[1]["character_slug"] == "bowser"
    assert result[1]["approval_rate"] == 0.40
