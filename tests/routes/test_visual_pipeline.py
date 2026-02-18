"""Tests for visual pipeline routes — generate, status, gallery, vision review."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
async def test_generate_character_not_found(app_client):
    with patch(
        "packages.visual_pipeline.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        resp = await app_client.post(
            "/api/lora/generate/nonexistent",
            json={"generation_type": "image"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


@pytest.mark.unit
async def test_generate_no_checkpoint(app_client):
    mock_char_map = {
        "luigi": {
            "name": "Luigi",
            "checkpoint_model": None,
            "design_prompt": "tall man",
            "project_name": "Test",
        },
    }
    with patch(
        "packages.visual_pipeline.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value=mock_char_map,
    ):
        resp = await app_client.post(
            "/api/lora/generate/luigi",
            json={"generation_type": "image"},
        )
        assert resp.status_code == 400
        assert "checkpoint" in resp.json()["detail"].lower()


@pytest.mark.unit
async def test_generate_success(app_client):
    mock_char_map = {
        "luigi": {
            "name": "Luigi",
            "checkpoint_model": "test.safetensors",
            "design_prompt": "tall man in green",
            "project_name": "Mario Galaxy",
            "sampler": "DPM++ 2M Karras",
            "scheduler": "karras",
            "cfg_scale": 8.5,
            "steps": 40,
            "width": 512,
            "height": 768,
            "style_preamble": None,
        },
    }
    mock_workflow = {
        "3": {"inputs": {"seed": 12345}},
    }
    with patch(
        "packages.visual_pipeline.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value=mock_char_map,
    ), patch(
        "packages.visual_pipeline.router.recommend_params",
        new_callable=AsyncMock,
        return_value={"learned_negatives": ""},
    ), patch(
        "packages.visual_pipeline.router.build_comfyui_workflow",
        return_value=mock_workflow,
    ), patch(
        "packages.visual_pipeline.router.submit_comfyui_workflow",
        return_value="prompt-abc-123",
    ), patch(
        "packages.visual_pipeline.router.log_generation",
        new_callable=AsyncMock,
        return_value=1,
    ), patch(
        "packages.visual_pipeline.router.event_bus",
    ) as mock_bus:
        mock_bus.emit = AsyncMock()
        resp = await app_client.post(
            "/api/lora/generate/luigi",
            json={"generation_type": "image"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt_id"] == "prompt-abc-123"
        assert data["character"] == "luigi"
        assert data["checkpoint"] == "test.safetensors"
        assert data["seed"] == 12345


@pytest.mark.unit
async def test_get_generation_status(app_client):
    mock_progress = {
        "status": "generating",
        "progress": 0.5,
        "current_node": "KSampler",
    }
    with patch(
        "packages.visual_pipeline.router.get_comfyui_progress",
        return_value=mock_progress,
    ):
        resp = await app_client.get("/api/lora/generate/test-prompt-id/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "generating"
        assert data["progress"] == 0.5


@pytest.mark.unit
async def test_gallery_empty(app_client):
    with patch(
        "packages.visual_pipeline.router.COMFYUI_OUTPUT_DIR",
        new=MagicMock(),
    ) as mock_dir:
        mock_dir.exists.return_value = False
        resp = await app_client.get("/api/lora/gallery")
        assert resp.status_code == 200
        data = resp.json()
        assert data["images"] == []


@pytest.mark.unit
async def test_vision_review_missing_params(app_client):
    resp = await app_client.post(
        "/api/lora/approval/vision-review",
        json={},
    )
    assert resp.status_code == 400
    assert "character_slug or project_name" in resp.json()["detail"]


@pytest.mark.unit
async def test_vision_review_character_not_found(app_client):
    with patch(
        "packages.visual_pipeline.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        resp = await app_client.post(
            "/api/lora/approval/vision-review",
            json={"character_slug": "nonexistent"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]
