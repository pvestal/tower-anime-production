"""Tests for packages.core.replenishment — autonomous image generation loop.

Tests the synchronous state-management functions and filesystem-based counters.
The async EventBus handler and generation logic are NOT tested here.
"""

import json

import pytest

from packages.core.replenishment import (
    enable,
    set_target,
    get_target,
    status,
    _count_approved,
    _count_pending,
    DEFAULT_TARGET,
    MAX_CONCURRENT,
    COOLDOWN_SECONDS,
    BATCH_SIZE,
)


@pytest.mark.unit
def test_enable_sets_and_unsets():
    """enable(True) sets _enabled, enable(False) unsets it."""
    import packages.core.replenishment as rep

    enable(True)
    assert rep._enabled is True

    enable(False)
    assert rep._enabled is False


@pytest.mark.unit
def test_set_target_per_character(monkeypatch):
    """set_target with character_slug sets a per-character override."""
    import packages.core.replenishment as rep

    # Clean state
    monkeypatch.setattr(rep, "_target_override", {})

    set_target(character_slug="luigi", target=30)
    assert rep._target_override["luigi"] == 30

    # get_target returns the override
    assert get_target("luigi") == 30


@pytest.mark.unit
def test_set_target_global_default(monkeypatch):
    """set_target without slug sets the global DEFAULT_TARGET."""
    import packages.core.replenishment as rep

    original = rep.DEFAULT_TARGET
    monkeypatch.setattr(rep, "_target_override", {})

    set_target(target=50)
    assert rep.DEFAULT_TARGET == 50

    # A character without an override gets the global default
    assert get_target("bowser") == 50

    # Restore
    rep.DEFAULT_TARGET = original


@pytest.mark.unit
def test_get_target_returns_override_or_default(monkeypatch):
    """get_target returns character override when set, global default otherwise."""
    import packages.core.replenishment as rep

    monkeypatch.setattr(rep, "_target_override", {"luigi": 25})
    monkeypatch.setattr(rep, "DEFAULT_TARGET", 20)

    assert get_target("luigi") == 25
    assert get_target("bowser") == 20


@pytest.mark.unit
def test_count_approved_reads_approval_status(tmp_path, monkeypatch):
    """_count_approved counts 'approved' entries from approval_status.json."""
    import packages.core.replenishment as rep

    monkeypatch.setattr(rep, "BASE_PATH", tmp_path)

    # Create character directory with approval_status.json
    char_dir = tmp_path / "luigi"
    char_dir.mkdir()
    approval_data = {
        "gen_001.png": "approved",
        "gen_002.png": "approved",
        "gen_003.png": "pending",
        "gen_004.png": "rejected",
        "gen_005.png": "approved",
    }
    (char_dir / "approval_status.json").write_text(json.dumps(approval_data))

    assert _count_approved("luigi") == 3


@pytest.mark.unit
def test_count_pending_reads_approval_status(tmp_path, monkeypatch):
    """_count_pending counts 'pending' entries from approval_status.json."""
    import packages.core.replenishment as rep

    monkeypatch.setattr(rep, "BASE_PATH", tmp_path)

    char_dir = tmp_path / "bowser"
    char_dir.mkdir()
    approval_data = {
        "gen_001.png": "approved",
        "gen_002.png": "pending",
        "gen_003.png": "pending",
    }
    (char_dir / "approval_status.json").write_text(json.dumps(approval_data))

    assert _count_pending("bowser") == 2


@pytest.mark.unit
async def test_status_returns_expected_keys(monkeypatch):
    """status() returns a dict with all expected configuration keys."""
    import packages.core.replenishment as rep

    # Clean state to avoid interference from other tests
    monkeypatch.setattr(rep, "_enabled", False)
    monkeypatch.setattr(rep, "_active_tasks", {})
    monkeypatch.setattr(rep, "_daily_counts", {})
    monkeypatch.setattr(rep, "_consecutive_rejects", {})
    monkeypatch.setattr(rep, "_last_generation", {})
    monkeypatch.setattr(rep, "_target_override", {})

    result = await status()

    expected_keys = {
        "enabled", "default_target", "max_concurrent", "cooldown_seconds",
        "max_daily_per_char", "max_consecutive_rejects", "batch_size",
        "active_generations", "daily_counts", "consecutive_rejects",
        "last_generation", "target_overrides",
    }
    assert expected_keys.issubset(set(result.keys()))
    assert result["enabled"] is False
    assert result["max_concurrent"] == MAX_CONCURRENT
    assert result["batch_size"] == BATCH_SIZE
