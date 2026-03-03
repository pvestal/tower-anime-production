"""Tests for engine_selector.py — motion detection and engine selection.

All disk dependencies (LoRA files, video_models.yaml, Wan 14B readiness)
are patched out so tests run without GPU or model files.
"""

import pytest
from unittest.mock import patch, MagicMock

from packages.scene_generation.engine_selector import (
    detect_motion_preset,
    select_engine,
    EngineSelection,
)

_ES = "packages.scene_generation.engine_selector"
_WAN = "packages.scene_generation.wan_video"


# ---------------------------------------------------------------------------
# TestDetectMotionPreset — 5 tests
# ---------------------------------------------------------------------------

class TestDetectMotionPreset:
    """detect_motion_preset(motion_prompt, shot_type) → preset name or None."""

    def test_walk_keyword(self):
        assert detect_motion_preset("character walking down the street") == "walking"

    def test_fight_keyword(self):
        assert detect_motion_preset("punch and dodge in combat") == "fight_scene"

    def test_establishing_from_shot_type(self):
        """No keyword match but establishing shot_type → 'establishing'."""
        assert detect_motion_preset("a wide view of the city", "establishing") == "establishing"

    def test_no_match_returns_none(self):
        """Prompt with no motion keywords and non-establishing type → None."""
        assert detect_motion_preset("a gentle breeze on the hillside", "medium") is None

    def test_case_insensitive(self):
        assert detect_motion_preset("SPRINT across the rooftop") == "running"


# ---------------------------------------------------------------------------
# TestSelectEngine — 7 tests
# ---------------------------------------------------------------------------

class TestSelectEngine:
    """select_engine() with disk deps patched out."""

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    @patch(f"{_WAN}.check_wan22_14b_ready", return_value=(False, ""))
    def test_multi_char_picks_wan(self, _ready, _preset, _lora):
        """Multi-character shot without 14B ready → wan."""
        result = select_engine(
            shot_type="medium",
            characters_present=["alice", "bob"],
            has_source_image=True,
        )
        assert result.engine == "wan"
        assert "multi-character" in result.reason

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    @patch(f"{_WAN}.check_wan22_14b_ready", return_value=(True, "/models/14b"))
    def test_multi_char_with_14b_picks_wan22_14b(self, _ready, _preset, _lora):
        """Multi-character with 14B ready + source image → wan22_14b."""
        result = select_engine(
            shot_type="medium",
            characters_present=["alice", "bob"],
            has_source_image=True,
        )
        assert result.engine == "wan22_14b"
        assert "multi-character" in result.reason

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    def test_establishing_picks_wan(self, _preset, _lora):
        """Establishing shot → wan (T2V for environments)."""
        result = select_engine(
            shot_type="establishing",
            characters_present=[],
            has_source_image=False,
        )
        assert result.engine == "wan"
        assert "establishing" in result.reason

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    @patch(f"{_WAN}.check_wan22_14b_ready", return_value=(False, ""))
    def test_solo_with_source_picks_framepack(self, _ready, _preset, _lora):
        """Solo shot with source image, no 14B → framepack."""
        result = select_engine(
            shot_type="medium",
            characters_present=["alice"],
            has_source_image=True,
        )
        assert result.engine == "framepack"

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    def test_reference_v2v_with_source_video(self, _preset, _lora):
        """Shot with source video → reference_v2v."""
        result = select_engine(
            shot_type="medium",
            characters_present=["alice"],
            has_source_image=True,
            has_source_video=True,
        )
        assert result.engine == "reference_v2v"

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    @patch(f"{_WAN}.check_wan22_14b_ready", return_value=(False, ""))
    def test_project_wan_lora_overrides(self, _ready, _preset, _lora):
        """project_wan_lora routes all shots to wan22."""
        result = select_engine(
            shot_type="medium",
            characters_present=["alice"],
            has_source_image=True,
            project_wan_lora="rosa_wan22_v1.safetensors",
        )
        assert result.engine == "wan22"
        assert "project Wan LoRA" in result.reason

    @patch(f"{_ES}._pick_best_lora", return_value=(None, None, None))
    @patch(f"{_ES}.detect_motion_preset", return_value=None)
    @patch(f"{_WAN}.check_wan22_14b_ready", return_value=(False, ""))
    def test_blacklist_skips_engine(self, _ready, _preset, _lora):
        """Blacklisted engine should be skipped for next candidate."""
        result = select_engine(
            shot_type="medium",
            characters_present=["alice"],
            has_source_image=True,
            blacklisted_engines=["framepack"],
        )
        # framepack would be selected for solo+source, but blacklisted
        assert result.engine != "framepack"
