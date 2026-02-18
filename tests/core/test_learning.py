"""Tests for packages.core.learning — SQL-based pattern analysis.

Functions query generation_history, rejections, approvals, and learned_patterns
tables via the shared asyncpg pool. All are async and fail gracefully.
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from packages.core.learning import (
    suggest_params,
    rejection_patterns,
    checkpoint_rankings,
    quality_trend,
    learning_stats,
    record_learned_pattern,
    MIN_SAMPLES,
    SUCCESS_THRESHOLD,
)


@pytest.fixture
def _patch_learning_pool(mock_db_pool):
    """Patch get_pool where learning.py actually uses it."""
    with patch("packages.core.learning.get_pool", new_callable=AsyncMock, return_value=mock_db_pool):
        yield


@pytest.mark.unit
async def test_suggest_params_returns_empty_when_insufficient_data(_patch_learning_pool, mock_conn):
    """suggest_params returns {} when sample_count < MIN_SAMPLES."""
    mock_conn.fetchrow.return_value = {
        "sample_count": MIN_SAMPLES - 1,
        "median_cfg": 8.0,
        "median_steps": 30,
        "median_width": 512,
        "median_height": 768,
        "avg_quality": 0.75,
    }

    result = await suggest_params("luigi")

    assert result == {}


@pytest.mark.unit
async def test_suggest_params_returns_suggestions_with_enough_data(_patch_learning_pool, mock_conn):
    """suggest_params returns full suggestions when enough data is available."""
    mock_conn.fetchrow.side_effect = [
        # First call: main params query
        {
            "sample_count": 10,
            "median_cfg": 8.5,
            "median_steps": 40,
            "median_width": 512,
            "median_height": 768,
            "avg_quality": 0.85,
        },
        # Second call: best sampler query
        {
            "sampler": "dpmpp_2m",
            "avg_q": 0.88,
            "n": 5,
        },
    ]

    result = await suggest_params("luigi")

    assert result["sample_count"] == 10
    assert result["cfg_scale"] == 8.5
    assert result["steps"] == 40
    assert result["width"] == 512
    assert result["height"] == 768
    assert result["avg_quality"] == 0.85
    assert result["sampler"] == "dpmpp_2m"
    assert result["sampler_avg_quality"] == 0.88


@pytest.mark.unit
async def test_rejection_patterns_returns_list(_patch_learning_pool, mock_conn):
    """rejection_patterns returns list of dicts from DB rows."""
    mock_conn.fetch.return_value = [
        {"category": "wrong_appearance", "count": 5, "latest_at": datetime(2026, 2, 15, 12, 0)},
        {"category": "not_solo", "count": 3, "latest_at": datetime(2026, 2, 14, 10, 0)},
    ]

    result = await rejection_patterns("bowser")

    assert len(result) == 2
    assert result[0]["category"] == "wrong_appearance"
    assert result[0]["count"] == 5
    assert result[0]["latest_at"] == "2026-02-15T12:00:00"
    assert result[1]["category"] == "not_solo"


@pytest.mark.unit
async def test_rejection_patterns_returns_empty_on_error(_patch_learning_pool, mock_conn):
    """rejection_patterns returns empty list when DB raises an exception."""
    mock_conn.fetch.side_effect = RuntimeError("query failed")

    result = await rejection_patterns("bowser")

    assert result == []


@pytest.mark.unit
async def test_checkpoint_rankings_returns_sorted_list(_patch_learning_pool, mock_conn):
    """checkpoint_rankings returns sorted list with approval rates."""
    mock_conn.fetch.return_value = [
        {
            "checkpoint_model": "realcartoonPixar_v12.safetensors",
            "avg_quality": 0.87,
            "total": 50,
            "approved": 40,
            "rejected": 10,
        },
        {
            "checkpoint_model": "realistic_vision_v51.safetensors",
            "avg_quality": 0.72,
            "total": 30,
            "approved": 18,
            "rejected": 12,
        },
    ]

    result = await checkpoint_rankings("Super Mario Galaxy Anime Adventure")

    assert len(result) == 2
    assert result[0]["checkpoint"] == "realcartoonPixar_v12.safetensors"
    assert result[0]["approval_rate"] == 0.80
    assert result[1]["approval_rate"] == 0.60


@pytest.mark.unit
async def test_quality_trend_with_character_slug(_patch_learning_pool, mock_conn):
    """quality_trend returns daily data when called with character_slug."""
    mock_conn.fetch.return_value = [
        {
            "gen_date": date(2026, 2, 14),
            "avg_quality": 0.82,
            "total": 10,
            "approved": 7,
            "rejected": 3,
        },
        {
            "gen_date": date(2026, 2, 15),
            "avg_quality": 0.88,
            "total": 8,
            "approved": 6,
            "rejected": 2,
        },
    ]

    result = await quality_trend(character_slug="luigi", days=7)

    assert len(result) == 2
    assert result[0]["date"] == "2026-02-14"
    assert result[0]["avg_quality"] == 0.82
    assert result[1]["date"] == "2026-02-15"
    mock_conn.fetch.assert_called_once()


@pytest.mark.unit
async def test_learning_stats_aggregates_tables(_patch_learning_pool, mock_conn):
    """learning_stats aggregates data from generation_history, rejections, learned_patterns, and autonomy_decisions."""
    mock_conn.fetchrow.side_effect = [
        # generation_history stats
        {
            "total_generations": 100,
            "reviewed": 80,
            "avg_quality": 0.78,
            "approved": 50,
            "rejected": 30,
            "characters_tracked": 5,
            "checkpoints_used": 2,
        },
        # rejections stats
        {
            "total_rejections": 30,
            "characters_rejected": 4,
        },
        # learned_patterns count
        {
            "total_patterns": 12,
        },
        # autonomy_decisions stats
        {
            "total_decisions": 65,
            "auto_approves": 40,
            "auto_rejects": 20,
            "regenerations": 5,
        },
    ]

    result = await learning_stats()

    assert result["generation_history"]["total"] == 100
    assert result["generation_history"]["avg_quality"] == 0.78
    assert result["rejections"]["total"] == 30
    assert result["learned_patterns"] == 12
    assert result["autonomy_decisions"]["total"] == 65
    assert result["period"] == "last_30_days"


@pytest.mark.unit
async def test_record_learned_pattern_inserts_new(_patch_learning_pool, mock_conn):
    """record_learned_pattern inserts a new row when no existing pattern found."""
    # fetchrow returns None = no existing pattern
    mock_conn.fetchrow.return_value = None

    await record_learned_pattern(
        character_slug="luigi",
        pattern_type="success",
        project_name="Test Project",
        checkpoint_model="realcartoonPixar_v12.safetensors",
        quality_score=0.88,
        cfg_scale=8.5,
        steps=40,
    )

    # Should have called fetchrow (check existing) then execute (insert)
    mock_conn.fetchrow.assert_called_once()
    mock_conn.execute.assert_called_once()
    sql_arg = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO learned_patterns" in sql_arg


@pytest.mark.unit
async def test_record_learned_pattern_updates_existing(_patch_learning_pool, mock_conn):
    """record_learned_pattern updates running average when a pattern already exists."""
    # fetchrow returns existing pattern
    mock_conn.fetchrow.return_value = {
        "id": 7,
        "quality_score_avg": 0.80,
        "frequency": 4,
        "cfg_range_min": 7.0,
        "cfg_range_max": 9.0,
        "steps_range_min": 30,
        "steps_range_max": 45,
    }

    await record_learned_pattern(
        character_slug="luigi",
        pattern_type="success",
        quality_score=0.90,
        cfg_scale=8.5,
        steps=40,
    )

    mock_conn.execute.assert_called_once()
    sql_arg = mock_conn.execute.call_args[0][0]
    assert "UPDATE learned_patterns" in sql_arg
    # Verify the ID is passed as first positional arg
    call_args = mock_conn.execute.call_args[0]
    assert call_args[1] == 7  # existing row ID
    # Running average: (0.80 * 4 + 0.90) / 5 = 0.82
    assert call_args[2] == 0.82  # new_avg
