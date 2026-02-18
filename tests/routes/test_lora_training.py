"""Tests for LoRA training routes — pending approvals, approve, feedback, dataset."""

import json
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
async def test_get_pending_approvals_empty(app_client):
    mock_base = MagicMock()
    mock_base.exists.return_value = False
    with patch("packages.lora_training.router.BASE_PATH", mock_base):
        resp = await app_client.get("/api/lora/approval/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_images"] == []


@pytest.mark.unit
async def test_get_pending_approvals_with_images(app_client, mock_filesystem):
    mock_char_map = {
        "luigi": {
            "name": "Luigi",
            "project_name": "Mario Galaxy",
            "design_prompt": "tall man in green",
            "checkpoint_model": "test.safetensors",
            "default_style": "mario_style",
        },
    }
    with patch(
        "packages.lora_training.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value=mock_char_map,
    ), patch(
        "packages.lora_training.router.BASE_PATH",
        mock_filesystem,
    ):
        resp = await app_client.get("/api/lora/approval/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["pending_images"], list)
        assert len(data["pending_images"]) == 1
        img = data["pending_images"][0]
        assert img["character_slug"] == "luigi"
        assert img["name"] == "gen_luigi_test_001.png"
        assert img["status"] == "pending"
        assert img["project_name"] == "Mario Galaxy"


@pytest.mark.unit
async def test_approve_image(app_client, mock_filesystem):
    with patch("packages.lora_training.router.BASE_PATH", mock_filesystem), \
         patch("packages.lora_training.router.record_rejection"), \
         patch("packages.lora_training.router.queue_regeneration"):
        resp = await app_client.post("/api/lora/approval/approve", json={
            "character_name": "Luigi",
            "character_slug": "luigi",
            "image_name": "gen_luigi_test_001.png",
            "approved": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "approved" in data["message"]
        assert data["regeneration_queued"] is False

        # Verify the approval_status.json was updated
        status_file = mock_filesystem / "luigi" / "approval_status.json"
        statuses = json.loads(status_file.read_text())
        assert statuses["gen_luigi_test_001.png"] == "approved"


@pytest.mark.unit
async def test_reject_image_queues_regeneration(app_client, mock_filesystem):
    with patch("packages.lora_training.router.BASE_PATH", mock_filesystem), \
         patch("packages.lora_training.router.record_rejection") as mock_record, \
         patch("packages.lora_training.router.queue_regeneration") as mock_regen:
        resp = await app_client.post("/api/lora/approval/approve", json={
            "character_name": "Luigi",
            "character_slug": "luigi",
            "image_name": "gen_luigi_test_001.png",
            "approved": False,
            "feedback": "bad_quality|too blurry",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "rejected" in data["message"]
        assert data["regeneration_queued"] is True
        mock_record.assert_called_once()
        mock_regen.assert_called_once_with("luigi")


@pytest.mark.unit
async def test_get_feedback(app_client, mock_filesystem):
    with patch(
        "packages.lora_training.training_router.BASE_PATH",
        mock_filesystem,
    ):
        resp = await app_client.get("/api/lora/feedback/luigi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character"] == "luigi"
        assert "rejection_count" in data
        assert data["rejection_count"] == 0


@pytest.mark.unit
async def test_get_feedback_no_file(app_client, tmp_path):
    with patch(
        "packages.lora_training.training_router.BASE_PATH",
        tmp_path,
    ):
        resp = await app_client.get("/api/lora/feedback/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character"] == "nonexistent"
        assert data["rejection_count"] == 0
        assert data["rejections"] == []


@pytest.mark.unit
async def test_get_dataset_info(app_client, mock_filesystem):
    with patch("packages.lora_training.router.BASE_PATH", mock_filesystem):
        resp = await app_client.get("/api/lora/dataset/luigi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character"] == "luigi"
        assert isinstance(data["images"], list)
        assert len(data["images"]) == 1
        assert data["images"][0]["name"] == "gen_luigi_test_001.png"
        assert data["images"][0]["status"] == "pending"


@pytest.mark.unit
async def test_get_dataset_info_missing_character(app_client, tmp_path):
    with patch("packages.lora_training.router.BASE_PATH", tmp_path):
        resp = await app_client.get("/api/lora/dataset/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["images"] == []
