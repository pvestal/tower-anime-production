"""Tests for routes defined directly in src/app.py — health, events, learning, replenishment, correction."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.unit
async def test_health(app_client):
    resp = await app_client.get("/api/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "tower-anime-studio"
    assert data["version"] == "3.3"


@pytest.mark.unit
async def test_events_stats(app_client):
    resp = await app_client.get("/api/system/events/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "registered_events" in data
    assert "total_handlers" in data
    assert "total_emits" in data
    assert "total_errors" in data


@pytest.mark.unit
async def test_learning_stats(app_client):
    mock_result = {
        "generation_history": {"total": 100, "with_quality": 80},
        "rejections": {"total": 15},
        "approvals": {"total": 65},
        "learned_patterns": {"total": 5},
    }
    with patch(
        "packages.core.learning.learning_stats",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        resp = await app_client.get("/api/system/learning/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "generation_history" in data
        assert data["generation_history"]["total"] == 100


@pytest.mark.unit
async def test_learning_suggest(app_client):
    mock_params = {
        "median_cfg": 8.5,
        "median_steps": 40,
        "best_sampler": "dpmpp_2m",
        "avg_quality": 0.85,
    }
    with patch(
        "packages.core.learning.suggest_params",
        new_callable=AsyncMock,
        return_value=mock_params,
    ):
        resp = await app_client.get("/api/system/learning/suggest/luigi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_slug"] == "luigi"
        assert data["suggestions"] is not None
        assert data["suggestions"]["median_cfg"] == 8.5


@pytest.mark.unit
async def test_learning_suggest_insufficient_data(app_client):
    with patch(
        "packages.core.learning.suggest_params",
        new_callable=AsyncMock,
        return_value={},
    ):
        resp = await app_client.get("/api/system/learning/suggest/unknown_char")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] is None
        assert "Insufficient data" in data["reason"]


@pytest.mark.unit
async def test_learning_rejections(app_client):
    mock_patterns = [
        {"category": "not_solo", "count": 5},
        {"category": "bad_quality", "count": 3},
    ]
    with patch(
        "packages.core.learning.rejection_patterns",
        new_callable=AsyncMock,
        return_value=mock_patterns,
    ):
        resp = await app_client.get("/api/system/learning/rejections/luigi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_slug"] == "luigi"
        assert isinstance(data["patterns"], list)
        assert len(data["patterns"]) == 2


@pytest.mark.unit
async def test_learning_trend(app_client):
    mock_trend = [
        {"date": "2026-02-17", "avg_quality": 0.82, "count": 5},
        {"date": "2026-02-18", "avg_quality": 0.85, "count": 3},
    ]
    with patch(
        "packages.core.learning.quality_trend",
        new_callable=AsyncMock,
        return_value=mock_trend,
    ):
        resp = await app_client.get("/api/system/learning/trend?character_slug=luigi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_slug"] == "luigi"
        assert isinstance(data["trend"], list)
        assert data["days"] == 7


@pytest.mark.unit
async def test_learning_trend_missing_params(app_client):
    resp = await app_client.get("/api/system/learning/trend")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data


@pytest.mark.unit
async def test_replenishment_status(app_client):
    mock_status = {
        "enabled": False,
        "active_tasks": 0,
        "daily_counts": {},
        "target": 20,
    }
    with patch(
        "packages.core.replenishment.status",
        new_callable=AsyncMock,
        return_value=mock_status,
    ):
        resp = await app_client.get("/api/system/replenishment/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert data["enabled"] is False


@pytest.mark.unit
async def test_correction_stats(app_client):
    mock_stats = {
        "total_corrections": 10,
        "success_rate": 0.7,
        "enabled": False,
    }
    with patch(
        "packages.core.auto_correction.get_correction_stats",
        new_callable=AsyncMock,
        return_value=mock_stats,
    ):
        resp = await app_client.get("/api/system/correction/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_corrections" in data
        assert data["total_corrections"] == 10
