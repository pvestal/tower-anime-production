"""Unit tests for packages.lora_training.feedback — maybe_refine_prompt_via_echo_brain."""

import json
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestMaybeRefinePromptViaEchoBrain:

    @pytest.fixture(autouse=True)
    def _patch_base_path(self, tmp_path, monkeypatch):
        """Redirect BASE_PATH to a tmp directory for every test."""
        monkeypatch.setattr("packages.lora_training.feedback.BASE_PATH", tmp_path)
        self.base = tmp_path

    def _write_feedback(self, slug: str, data: dict):
        """Helper to write a feedback.json for a character."""
        char_dir = self.base / slug
        char_dir.mkdir(parents=True, exist_ok=True)
        (char_dir / "feedback.json").write_text(json.dumps(data))

    def _make_feedback_data(
        self, n_rejections: int = 5, last_suggestion_at: int = 0
    ) -> dict:
        """Build a feedback payload with n structured rejections."""
        return {
            "rejections": [
                {
                    "categories": ["wrong_appearance"],
                    "feedback": "wrong_appearance|bad colors",
                    "image": f"img_{i}.png",
                    "timestamp": "2026-01-01",
                }
                for i in range(n_rejections)
            ],
            "rejection_count": n_rejections,
            "negative_additions": ["wrong colors"],
            "last_echo_brain_suggestion_at_count": last_suggestion_at,
        }

    # --- Tests ---

    def test_returns_none_when_feedback_missing(self):
        from packages.lora_training.feedback import maybe_refine_prompt_via_echo_brain

        result = maybe_refine_prompt_via_echo_brain("nonexistent_char")
        assert result is None

    def test_returns_none_when_fewer_than_3_structured(self):
        from packages.lora_training.feedback import maybe_refine_prompt_via_echo_brain

        self._write_feedback("toad", self._make_feedback_data(n_rejections=2))
        result = maybe_refine_prompt_via_echo_brain("toad")
        assert result is None

    def test_returns_none_when_suggestion_already_recent(self):
        from packages.lora_training.feedback import maybe_refine_prompt_via_echo_brain

        # last_suggestion_at_count=3, rejection_count=5 -> diff is 2, threshold is 5
        self._write_feedback(
            "toad", self._make_feedback_data(n_rejections=5, last_suggestion_at=3)
        )
        result = maybe_refine_prompt_via_echo_brain("toad")
        assert result is None

    def test_returns_echo_context_on_success(self, monkeypatch):
        from packages.lora_training.feedback import maybe_refine_prompt_via_echo_brain

        self._write_feedback("toad", self._make_feedback_data(n_rejections=5))

        echo_response = json.dumps({
            "result": {
                "content": [
                    {"type": "text", "text": "Toad is a mushroom-headed humanoid with a spotted cap."}
                ]
            }
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = echo_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "urllib.request.urlopen", lambda *args, **kwargs: mock_resp
        )

        result = maybe_refine_prompt_via_echo_brain("toad")
        assert result is not None
        assert "mushroom-headed" in result

    def test_returns_none_when_urllib_fails(self, monkeypatch):
        from packages.lora_training.feedback import maybe_refine_prompt_via_echo_brain

        self._write_feedback("toad", self._make_feedback_data(n_rejections=5))

        def _raise(*args, **kwargs):
            raise ConnectionError("Echo Brain unreachable")

        monkeypatch.setattr("urllib.request.urlopen", _raise)

        result = maybe_refine_prompt_via_echo_brain("toad")
        assert result is None
