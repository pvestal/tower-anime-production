"""Tests for scene generation routes — CRUD, status, delete."""

import uuid
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, patch


SCENE_UUID = str(uuid.uuid4())
SCENE_UUID_OBJ = uuid.UUID(SCENE_UUID)


@pytest.mark.unit
async def test_list_scenes(app_client):
    mock_conn = AsyncMock()
    mock_row = {
        "id": SCENE_UUID_OBJ,
        "project_id": 1,
        "title": "Opening Scene",
        "description": "The beginning",
        "location": "City",
        "time_of_day": "night",
        "weather": "clear",
        "mood": "tense",
        "generation_status": "draft",
        "target_duration_seconds": 30,
        "actual_duration_seconds": None,
        "total_shots": 3,
        "completed_shots": 0,
        "final_video_path": None,
        "created_at": datetime(2026, 2, 18),
        "audio_track_id": None,
        "audio_track_name": None,
        "audio_track_artist": None,
        "audio_preview_url": None,
        "audio_fade_in": None,
        "audio_fade_out": None,
        "audio_start_offset": None,
    }
    mock_conn.fetch = AsyncMock(return_value=[mock_row])
    mock_conn.fetchval = AsyncMock(return_value=3)  # shot_count
    mock_conn.close = AsyncMock()
    with patch(
        "packages.scene_generation.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get("/api/scenes?project_id=1")
        assert resp.status_code == 200
        data = resp.json()
        assert "scenes" in data
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["title"] == "Opening Scene"
        assert data["scenes"][0]["total_shots"] == 3


@pytest.mark.unit
async def test_create_scene(app_client):
    new_id = uuid.uuid4()
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=0)  # max scene_number
    mock_conn.fetchrow = AsyncMock(return_value={
        "id": new_id,
        "created_at": datetime(2026, 2, 18),
    })
    mock_conn.close = AsyncMock()
    with patch(
        "packages.scene_generation.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.post("/api/scenes", json={
            "project_id": 1,
            "title": "Chase Scene",
            "description": "A high speed chase",
            "location": "Highway",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["scene_number"] == 1


@pytest.mark.unit
async def test_get_scene_status(app_client):
    mock_conn = AsyncMock()
    mock_scene = {
        "generation_status": "generating",
        "total_shots": 3,
        "completed_shots": 1,
        "current_generating_shot_id": None,
        "final_video_path": None,
        "actual_duration_seconds": None,
    }
    shot_id = uuid.uuid4()
    mock_shots = [{
        "id": shot_id,
        "shot_number": 1,
        "status": "completed",
        "output_video_path": "/opt/ComfyUI/output/test.mp4",
        "error_message": None,
        "comfyui_prompt_id": "abc-123",
        "generation_time_seconds": 120.5,
        "quality_score": 0.85,
        "motion_prompt": "walking forward",
    }]
    mock_conn.fetchrow = AsyncMock(return_value=mock_scene)
    mock_conn.fetch = AsyncMock(return_value=mock_shots)
    mock_conn.close = AsyncMock()
    with patch(
        "packages.scene_generation.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get(f"/api/scenes/{SCENE_UUID}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["generation_status"] == "generating"
        assert data["completed_shots"] == 1
        assert isinstance(data["shots"], list)
        assert data["shots"][0]["status"] == "completed"


@pytest.mark.unit
async def test_get_scene_status_not_found(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.close = AsyncMock()
    with patch(
        "packages.scene_generation.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get(f"/api/scenes/{SCENE_UUID}/status")
        assert resp.status_code == 404


@pytest.mark.unit
async def test_delete_scene(app_client):
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()
    with patch(
        "packages.scene_generation.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.delete(f"/api/scenes/{SCENE_UUID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Scene deleted"
        # Verify both shots and scene were deleted
        assert mock_conn.execute.call_count == 2
