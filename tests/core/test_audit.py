"""Tests for packages.core.audit — fire-and-forget audit logging to DB.

All audit functions are async, use `await get_pool()`, and return row ID or None.
They catch all exceptions silently (fire-and-forget pattern).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from packages.core.audit import log_generation, log_rejection, log_approval, log_decision


@pytest.fixture
def _patch_audit_pool(mock_db_pool):
    """Patch get_pool where audit.py actually uses it."""
    with patch("packages.core.audit.get_pool", new_callable=AsyncMock, return_value=mock_db_pool):
        yield


@pytest.mark.unit
async def test_log_generation_returns_row_id(_patch_audit_pool, mock_conn):
    """log_generation returns the row ID when the INSERT succeeds."""
    mock_conn.fetchrow.return_value = {"id": 42}

    result = await log_generation(character_slug="luigi", project_name="Test Project")

    assert result == 42
    mock_conn.fetchrow.assert_called_once()
    # Verify the SQL contains INSERT INTO generation_history
    sql_arg = mock_conn.fetchrow.call_args[0][0]
    assert "INSERT INTO generation_history" in sql_arg


@pytest.mark.unit
async def test_log_generation_returns_none_on_db_error(_patch_audit_pool, mock_conn):
    """log_generation returns None when the DB raises an exception."""
    mock_conn.fetchrow.side_effect = RuntimeError("connection lost")

    result = await log_generation(character_slug="luigi", project_name="Test Project")

    assert result is None


@pytest.mark.unit
async def test_log_rejection_executes_insert(_patch_audit_pool, mock_conn):
    """log_rejection executes an INSERT with the correct parameters."""
    await log_rejection(
        character_slug="bowser",
        image_name="gen_bowser_001.png",
        categories=["wrong_appearance", "not_solo"],
        feedback_text="looks wrong",
        quality_score=0.35,
        project_name="Mario Galaxy",
        source="vision",
    )

    mock_conn.execute.assert_called_once()
    sql_arg = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO rejections" in sql_arg
    # Verify positional params include slug and categories
    call_args = mock_conn.execute.call_args[0]
    assert call_args[1] == "bowser"  # character_slug
    assert call_args[3] == "gen_bowser_001.png"  # image_name
    assert call_args[5] == ["wrong_appearance", "not_solo"]  # categories


@pytest.mark.unit
async def test_log_approval_serializes_vision_review(_patch_audit_pool, mock_conn):
    """log_approval serializes the vision_review dict as JSON before INSERT."""
    vision_review = {"character_match": 9, "solo": True, "clarity": 8}

    await log_approval(
        character_slug="luigi",
        image_name="gen_luigi_005.png",
        quality_score=0.88,
        auto_approved=True,
        vision_review=vision_review,
        project_name="Test Project",
    )

    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args[0]
    # The last positional param should be the JSON-serialized vision_review
    # Position: $1=slug, $2=project, $3=image, $4=gen_id, $5=quality, $6=auto, $7=vision_json
    json_arg = call_args[7]
    assert json_arg is not None
    parsed = json.loads(json_arg)
    assert parsed["character_match"] == 9
    assert parsed["solo"] is True


@pytest.mark.unit
async def test_log_decision_returns_row_id(_patch_audit_pool, mock_conn):
    """log_decision returns the row ID on successful INSERT."""
    mock_conn.fetchrow.return_value = {"id": 99}

    result = await log_decision(
        decision_type="auto_approve",
        character_slug="luigi",
        project_name="Test Project",
        input_context={"quality_score": 0.9},
        decision_made="approved",
        confidence_score=0.95,
        reasoning="High quality score above threshold",
    )

    assert result == 99
    mock_conn.fetchrow.assert_called_once()
    sql_arg = mock_conn.fetchrow.call_args[0][0]
    assert "INSERT INTO autonomy_decisions" in sql_arg


@pytest.mark.unit
async def test_log_decision_returns_none_on_error(_patch_audit_pool, mock_conn):
    """log_decision returns None when the DB raises an exception."""
    mock_conn.fetchrow.side_effect = ConnectionError("DB unreachable")

    result = await log_decision(
        decision_type="regeneration",
        character_slug="bowser",
        reasoning="Quality too low",
    )

    assert result is None
