"""Tests for GET /api/scenes/{scene_id}/shots/{shot_id}/built-prompt endpoint."""

import uuid

import pytest
from unittest.mock import AsyncMock, patch

_CRUD = "packages.scene_generation.scene_crud"

SCENE_UUID = str(uuid.uuid4())
SHOT_UUID = str(uuid.uuid4())


@pytest.mark.unit
async def test_get_built_prompt_returns_200(app_client):
    """Successful built-prompt preview returns prompt components."""
    mock_result = {
        "final_prompt": "photorealistic, city street, night, young man, walking forward",
        "final_negative": "low quality, blurry, watermark",
        "engine": "framepack",
        "prompt_length": 55,
        "style_anchor": "photorealistic, live action film, cinematic lighting",
        "scene_context": {
            "location": "city street",
            "time_of_day": "night",
            "mood": "tense",
            "description": "A dark alley encounter",
        },
        "character_appearances": [{"name": "Kai", "condensed": "young man, dark hair"}],
        "motion_prompt": "walking forward",
        "generation_prompt": None,
    }
    with patch(
        f"{_CRUD}.build_shot_prompt_preview",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        resp = await app_client.get(f"/api/scenes/{SCENE_UUID}/shots/{SHOT_UUID}/built-prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["final_prompt"] == mock_result["final_prompt"]
        assert data["engine"] == "framepack"
        assert data["scene_context"]["location"] == "city street"
        assert len(data["character_appearances"]) == 1


@pytest.mark.unit
async def test_get_built_prompt_404_on_missing(app_client):
    """Missing shot should return 404."""
    with patch(
        f"{_CRUD}.build_shot_prompt_preview",
        new_callable=AsyncMock,
        return_value={"error": "Shot not found"},
    ):
        resp = await app_client.get(f"/api/scenes/{SCENE_UUID}/shots/{SHOT_UUID}/built-prompt")
        assert resp.status_code == 404
