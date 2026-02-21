"""Tests for story package routes — projects, characters, checkpoints."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
async def test_get_projects(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"id": 1, "name": "Test Project", "default_style": "test_style", "char_count": 3},
    ])
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.get("/api/story/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "Test Project"
        assert data["projects"][0]["character_count"] == 3


@pytest.mark.unit
async def test_create_project(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(side_effect=[None, 42])
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.post("/api/story/projects", json={
            "name": "New Project",
            "description": "A test project",
            "genre": "sci-fi",
            "checkpoint_model": "test_model.safetensors",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == 42
        assert "style_name" in data
        assert "New Project" in data["message"]


@pytest.mark.unit
async def test_get_characters(app_client):
    mock_char_map = {
        "luigi": {
            "name": "Luigi",
            "project_name": "Mario Galaxy",
            "design_prompt": "tall man in green",
            "default_style": "mario_style",
            "checkpoint_model": "test.safetensors",
            "cfg_scale": 8.5,
            "steps": 40,
            "resolution": "512x768",
        },
    }
    with patch(
        "packages.story.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value=mock_char_map,
    ), patch(
        "packages.story.router.BASE_PATH",
        new=MagicMock(),
    ) as mock_base:
        # Make the images directory appear to not exist so we skip filesystem calls
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_base.__truediv__ = MagicMock(return_value=mock_path)
        mock_path.__truediv__ = MagicMock(return_value=mock_path)

        resp = await app_client.get("/api/story/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert "characters" in data
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "Luigi"
        assert data["characters"][0]["slug"] == "luigi"


@pytest.mark.unit
async def test_create_character(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[
        {"id": 1},  # project lookup
        None,        # existing character check (none found)
    ])
    mock_conn.fetchval = AsyncMock(return_value=99)
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ), patch(
        "packages.story.router.BASE_PATH",
        new=MagicMock(),
    ) as mock_base, patch(
        "packages.story.router.invalidate_char_cache",
    ):
        # Mock the filesystem path operations
        mock_char_path = MagicMock()
        mock_images = MagicMock()
        mock_char_path.__truediv__ = MagicMock(side_effect=lambda x: mock_images if x == "images" else MagicMock())
        mock_base.__truediv__ = MagicMock(return_value=mock_char_path)

        mock_approval_file = MagicMock()
        mock_approval_file.exists.return_value = False

        def div_side_effect(x):
            if x == "images":
                return mock_images
            if x == "approval_status.json":
                return mock_approval_file
            return MagicMock()
        mock_char_path.__truediv__ = MagicMock(side_effect=div_side_effect)

        resp = await app_client.post("/api/story/characters", json={
            "name": "Toad",
            "project_name": "Mario Galaxy",
            "design_prompt": "small mushroom character",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "toad"
        assert data["id"] == 99


@pytest.mark.unit
async def test_create_character_project_not_found(app_client):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.close = AsyncMock()
    with patch(
        "packages.story.router.connect_direct",
        new_callable=AsyncMock,
        return_value=mock_conn,
    ):
        resp = await app_client.post("/api/story/characters", json={
            "name": "Ghost",
            "project_name": "Nonexistent Project",
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


@pytest.mark.unit
async def test_get_checkpoints(app_client):
    mock_file1 = MagicMock()
    mock_file1.name = "model_v1.safetensors"
    mock_file1.suffix = ".safetensors"
    mock_file1.is_file.return_value = True
    mock_stat = MagicMock()
    mock_stat.st_size = 2 * 1048576  # 2 MB
    mock_file1.stat.return_value = mock_stat

    mock_dir = MagicMock()
    mock_dir.exists.return_value = True
    mock_dir.iterdir.return_value = [mock_file1]

    with patch("packages.story.router.CHECKPOINTS_DIR", mock_dir):
        resp = await app_client.get("/api/story/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert "checkpoints" in data
        assert len(data["checkpoints"]) == 1
        assert data["checkpoints"][0]["filename"] == "model_v1.safetensors"
        assert data["checkpoints"][0]["size_mb"] == 2.0
