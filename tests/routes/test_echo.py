"""Tests for echo integration routes — status, chat, enhance-prompt."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_urlopen_response(data: dict):
    """Create a mock urllib response object that returns JSON data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@pytest.mark.unit
async def test_echo_status_connected(app_client):
    health_data = {"status": "ok", "version": "2.0", "vectors": 54000}
    mock_resp = _make_urlopen_response(health_data)
    with patch("packages.echo_integration.router._ur.urlopen", return_value=mock_resp):
        resp = await app_client.get("/api/echo/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["echo_brain"]["status"] == "ok"


@pytest.mark.unit
async def test_echo_status_offline(app_client):
    with patch(
        "packages.echo_integration.router._ur.urlopen",
        side_effect=Exception("Connection refused"),
    ):
        resp = await app_client.get("/api/echo/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "offline"
        assert "error" in data


@pytest.mark.unit
async def test_echo_chat_success(app_client):
    mcp_response = {
        "result": {
            "content": [
                {"type": "text", "text": "Luigi is a tall character in green overalls."},
                {"type": "text", "text": "He appears in the Mario franchise."},
            ]
        }
    }
    mock_resp = _make_urlopen_response(mcp_response)
    with patch(
        "packages.echo_integration.router._ur.urlopen",
        return_value=mock_resp,
    ), patch(
        "packages.echo_integration.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        resp = await app_client.post("/api/echo/chat", json={
            "message": "Tell me about Luigi",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "Luigi" in data["response"]


@pytest.mark.unit
async def test_echo_chat_with_character_context(app_client):
    mock_char_map = {
        "luigi": {
            "name": "Luigi",
            "project_name": "Mario Galaxy",
            "design_prompt": "tall man in green",
        },
    }
    mcp_response = {
        "result": {
            "content": [
                {"type": "text", "text": "Found memories about Luigi."},
            ]
        }
    }
    mock_resp = _make_urlopen_response(mcp_response)
    with patch(
        "packages.echo_integration.router._ur.urlopen",
        return_value=mock_resp,
    ), patch(
        "packages.echo_integration.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value=mock_char_map,
    ):
        resp = await app_client.post("/api/echo/chat", json={
            "message": "How should I generate Luigi?",
            "character_slug": "luigi",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["context_used"] is True
        assert data["character_context"] is not None
        assert "Luigi" in data["character_context"]


@pytest.mark.unit
async def test_echo_chat_unavailable(app_client):
    with patch(
        "packages.echo_integration.router._ur.urlopen",
        side_effect=Exception("Connection refused"),
    ), patch(
        "packages.echo_integration.router.get_char_project_map",
        new_callable=AsyncMock,
        return_value={},
    ):
        resp = await app_client.post("/api/echo/chat", json={
            "message": "Hello",
        })
        assert resp.status_code == 502
        assert "unavailable" in resp.json()["detail"].lower()
