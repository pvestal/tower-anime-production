"""Unit tests for feedback loop helpers in packages.lora_training.feedback.

Tests record_rejection, get_feedback_negatives, REJECTION_NEGATIVE_MAP,
register_pending_image, and register_image_status.

All filesystem tests use monkeypatch to redirect BASE_PATH to tmp_path.
"""

import json

import pytest

from packages.lora_training.feedback import (
    record_rejection,
    get_feedback_negatives,
    REJECTION_NEGATIVE_MAP,
    register_pending_image,
    register_image_status,
)


@pytest.fixture
def feedback_fs(tmp_path, monkeypatch):
    """Redirect BASE_PATH to tmp_path and create a character directory."""
    monkeypatch.setattr("packages.lora_training.feedback.BASE_PATH", tmp_path)
    char_dir = tmp_path / "test_char"
    char_dir.mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# REJECTION_NEGATIVE_MAP structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rejection_negative_map_has_six_entries():
    """REJECTION_NEGATIVE_MAP should have exactly 6 standard categories."""
    expected = {
        "wrong_appearance", "wrong_style", "bad_quality",
        "not_solo", "wrong_pose", "wrong_expression",
    }
    assert set(REJECTION_NEGATIVE_MAP.keys()) == expected
    assert len(REJECTION_NEGATIVE_MAP) == 6


# ---------------------------------------------------------------------------
# record_rejection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_record_rejection_creates_feedback_json(feedback_fs):
    """record_rejection creates feedback.json with structured rejection data."""
    record_rejection("test_char", "img_001.png", "wrong_appearance")
    fb_path = feedback_fs / "test_char" / "feedback.json"
    assert fb_path.exists()
    data = json.loads(fb_path.read_text())
    assert data["rejection_count"] == 1
    assert len(data["rejections"]) == 1
    entry = data["rejections"][0]
    assert entry["image"] == "img_001.png"
    assert entry["feedback"] == "wrong_appearance"
    assert "wrong_appearance" in entry["categories"]


@pytest.mark.unit
def test_record_rejection_pipe_separated_categories(feedback_fs):
    """record_rejection parses pipe-separated feedback into structured categories."""
    record_rejection("test_char", "img_002.png", "wrong_appearance|bad_quality|face looks weird")
    fb_path = feedback_fs / "test_char" / "feedback.json"
    data = json.loads(fb_path.read_text())
    entry = data["rejections"][0]
    assert "wrong_appearance" in entry["categories"]
    assert "bad_quality" in entry["categories"]
    # Free text "face looks weird" is not a recognized category
    assert "face looks weird" not in entry["categories"]


@pytest.mark.unit
def test_record_rejection_appends_to_existing(feedback_fs):
    """record_rejection appends to an existing feedback.json without losing prior entries."""
    record_rejection("test_char", "img_001.png", "wrong_appearance")
    record_rejection("test_char", "img_002.png", "bad_quality")
    fb_path = feedback_fs / "test_char" / "feedback.json"
    data = json.loads(fb_path.read_text())
    assert data["rejection_count"] == 2
    assert len(data["rejections"]) == 2
    assert data["rejections"][0]["image"] == "img_001.png"
    assert data["rejections"][1]["image"] == "img_002.png"


# ---------------------------------------------------------------------------
# get_feedback_negatives
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_feedback_negatives_returns_terms(feedback_fs):
    """get_feedback_negatives returns comma-separated negative prompt terms from feedback.json."""
    record_rejection("test_char", "img_001.png", "wrong_appearance")
    result = get_feedback_negatives("test_char")
    assert result != ""
    # wrong_appearance maps to "wrong colors, inaccurate character design, wrong outfit"
    assert "wrong colors" in result


@pytest.mark.unit
def test_get_feedback_negatives_empty_when_no_file(feedback_fs):
    """get_feedback_negatives returns empty string when no feedback.json exists."""
    result = get_feedback_negatives("nonexistent_char")
    assert result == ""


# ---------------------------------------------------------------------------
# register_pending_image
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_register_pending_image_creates_status(feedback_fs):
    """register_pending_image creates approval_status.json with 'pending' status."""
    register_pending_image("test_char", "gen_test_001.png")
    status_path = feedback_fs / "test_char" / "approval_status.json"
    assert status_path.exists()
    data = json.loads(status_path.read_text())
    assert data["gen_test_001.png"] == "pending"


# ---------------------------------------------------------------------------
# register_image_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_register_image_status_approved(feedback_fs):
    """register_image_status with 'approved' correctly updates the status file."""
    # First register as pending
    register_pending_image("test_char", "gen_test_002.png")
    # Then approve
    register_image_status("test_char", "gen_test_002.png", "approved")
    status_path = feedback_fs / "test_char" / "approval_status.json"
    data = json.loads(status_path.read_text())
    assert data["gen_test_002.png"] == "approved"
