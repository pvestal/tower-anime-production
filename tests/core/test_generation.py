"""Tests for packages.core.generation — the critical generation pipeline.

Covers:
- _copy_to_dataset: file copying, captions, metadata sidecars
- _poll_until_complete: ComfyUI polling with timeout and error handling
- generate_batch: full pipeline with DB lookup, prompt building, ComfyUI
  submission, polling, dataset copy, and event firing
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from packages.core.generation import (
    _copy_to_dataset,
    _poll_until_complete,
    generate_batch,
    build_character_negatives,
)


# ---------------------------------------------------------------------------
# _copy_to_dataset tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCopyToDataset:
    """Tests for _copy_to_dataset — copies files from ComfyUI output to dataset dir."""

    def test_happy_path_creates_image_caption_and_meta(self, tmp_path, monkeypatch):
        """Copies the image, writes a .txt caption and .meta.json sidecar."""
        # Set up fake ComfyUI output dir with a source image
        comfyui_out = tmp_path / "comfyui_output"
        comfyui_out.mkdir()
        src_file = comfyui_out / "output_001.png"
        src_file.write_bytes(b"\x89PNG fake image data")

        # Point BASE_PATH and COMFYUI_OUTPUT_DIR to tmp dirs
        dataset_base = tmp_path / "datasets"
        dataset_base.mkdir()
        monkeypatch.setattr("packages.core.generation.BASE_PATH", dataset_base)
        monkeypatch.setattr("packages.core.generation.COMFYUI_OUTPUT_DIR", comfyui_out)

        result = _copy_to_dataset(
            character_slug="luigi",
            filenames=["output_001.png"],
            design_prompt="tall thin man in green cap",
            job_params={"seed": 42, "checkpoint_model": "test.safetensors"},
            project_name="Test Project",
            character_name="Luigi",
            pose="standing pose, front view",
        )

        assert len(result) == 1
        copied_name = result[0]
        assert copied_name.startswith("gen_luigi_")
        assert copied_name.endswith(".png")

        images_dir = dataset_base / "luigi" / "images"
        assert (images_dir / copied_name).exists()

        # Caption .txt written
        txt_path = images_dir / copied_name.replace(".png", ".txt")
        assert txt_path.exists()
        assert txt_path.read_text() == "tall thin man in green cap"

        # Metadata .meta.json written
        meta_path = images_dir / copied_name.replace(".png", ".meta.json")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["seed"] == 42
        assert meta["design_prompt"] == "tall thin man in green cap"
        assert meta["pose"] == "standing pose, front view"
        assert meta["project_name"] == "Test Project"
        assert meta["character_name"] == "Luigi"
        assert meta["source"] == "generate_batch"

        # Source file should be cleaned up
        assert not src_file.exists()

    def test_empty_filenames_returns_empty(self, tmp_path, monkeypatch):
        """Empty filenames list returns empty list without creating files."""
        dataset_base = tmp_path / "datasets"
        dataset_base.mkdir()
        monkeypatch.setattr("packages.core.generation.BASE_PATH", dataset_base)

        result = _copy_to_dataset(
            character_slug="luigi",
            filenames=[],
            design_prompt="test prompt",
            job_params={},
        )

        assert result == []

    def test_source_file_missing_skips(self, tmp_path, monkeypatch):
        """When source file doesn't exist in ComfyUI output, skip it."""
        comfyui_out = tmp_path / "comfyui_output"
        comfyui_out.mkdir()
        # Do NOT create the source file

        dataset_base = tmp_path / "datasets"
        dataset_base.mkdir()
        monkeypatch.setattr("packages.core.generation.BASE_PATH", dataset_base)
        monkeypatch.setattr("packages.core.generation.COMFYUI_OUTPUT_DIR", comfyui_out)

        result = _copy_to_dataset(
            character_slug="luigi",
            filenames=["nonexistent.png"],
            design_prompt="test prompt",
            job_params={},
        )

        assert result == []

    def test_multiple_files_copies_all(self, tmp_path, monkeypatch):
        """Multiple filenames are each copied with unique names."""
        comfyui_out = tmp_path / "comfyui_output"
        comfyui_out.mkdir()
        for i in range(3):
            (comfyui_out / f"output_{i:03d}.png").write_bytes(b"\x89PNG data")

        dataset_base = tmp_path / "datasets"
        dataset_base.mkdir()
        monkeypatch.setattr("packages.core.generation.BASE_PATH", dataset_base)
        monkeypatch.setattr("packages.core.generation.COMFYUI_OUTPUT_DIR", comfyui_out)

        result = _copy_to_dataset(
            character_slug="luigi",
            filenames=["output_000.png", "output_001.png", "output_002.png"],
            design_prompt="test",
            job_params={},
        )

        assert len(result) == 3
        # All filenames should be unique
        assert len(set(result)) == 3


# ---------------------------------------------------------------------------
# _poll_until_complete tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPollUntilComplete:
    """Tests for _poll_until_complete — polls ComfyUI until job finishes."""

    async def test_returns_filenames_on_completed(self):
        """Returns list of filenames when ComfyUI reports completed status."""
        mock_progress = {
            "status": "completed",
            "progress": 1.0,
            "images": ["output_001.png", "output_002.png"],
        }
        with patch(
            "packages.core.generation.get_comfyui_progress",
            return_value=mock_progress,
        ):
            result = await _poll_until_complete("prompt-123", timeout=10, interval=0.01)

        assert result == ["output_001.png", "output_002.png"]

    async def test_returns_none_on_timeout(self):
        """Returns None when the job never completes within timeout."""
        mock_progress = {"status": "running", "progress": 0.5}
        with patch(
            "packages.core.generation.get_comfyui_progress",
            return_value=mock_progress,
        ):
            result = await _poll_until_complete("prompt-123", timeout=0.05, interval=0.01)

        assert result is None

    async def test_returns_none_on_error_status(self):
        """Returns None when ComfyUI reports error status."""
        mock_progress = {"status": "error", "progress": 0.0, "error": "CUDA OOM"}
        with patch(
            "packages.core.generation.get_comfyui_progress",
            return_value=mock_progress,
        ):
            result = await _poll_until_complete("prompt-123", timeout=10, interval=0.01)

        assert result is None

    async def test_polls_until_status_changes(self):
        """Keeps polling while status is pending/running, returns on completed."""
        progress_sequence = [
            {"status": "pending", "progress": 0.1},
            {"status": "running", "progress": 0.5},
            {"status": "completed", "progress": 1.0, "images": ["out.png"]},
        ]
        mock_fn = MagicMock(side_effect=progress_sequence)
        with patch("packages.core.generation.get_comfyui_progress", mock_fn):
            result = await _poll_until_complete("prompt-123", timeout=10, interval=0.01)

        assert result == ["out.png"]
        assert mock_fn.call_count == 3


# ---------------------------------------------------------------------------
# generate_batch tests
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _make_generate_batch_patches(
    sample_char_map,
    submit_return="prompt-123",
    submit_side_effect=None,
    poll_return=_SENTINEL,
    copy_return=_SENTINEL,
    recommend_return=_SENTINEL,
    feedback_return="",
    log_gen_return=1,
):
    """Helper to build the standard set of patches for generate_batch tests.

    Returns a dict of patch context managers keyed by short name.
    """
    if poll_return is _SENTINEL:
        poll_return = ["output_001.png"]
    if copy_return is _SENTINEL:
        copy_return = ["gen_luigi_test.png"]
    if recommend_return is _SENTINEL:
        recommend_return = {"learned_negatives": "", "confidence": "none"}

    patches = {
        "char_map": patch(
            "packages.core.generation.get_char_project_map",
            new_callable=AsyncMock,
            return_value=sample_char_map,
        ),
        "submit": patch(
            "packages.core.generation.submit_comfyui_workflow",
            side_effect=submit_side_effect,
            return_value=submit_return,
        ),
        "poll": patch(
            "packages.core.generation._poll_until_complete",
            new_callable=AsyncMock,
            return_value=poll_return,
        ),
        "copy": patch(
            "packages.core.generation._copy_to_dataset",
            return_value=copy_return,
        ),
        "register": patch(
            "packages.core.generation.register_pending_image",
        ),
        "log_gen": patch(
            "packages.core.generation.log_generation",
            new_callable=AsyncMock,
            return_value=log_gen_return,
        ),
        "recommend": patch(
            "packages.core.generation.recommend_params",
            new_callable=AsyncMock,
            return_value=recommend_return,
        ),
        "feedback": patch(
            "packages.core.generation.get_feedback_negatives",
            return_value=feedback_return,
        ),
        "event_bus": patch("packages.core.generation.event_bus"),
        "build_workflow": patch(
            "packages.core.generation.build_comfyui_workflow",
            return_value={"3": {"inputs": {"seed": 12345}}},
        ),
    }
    return patches


@pytest.mark.unit
class TestGenerateBatch:
    """Tests for generate_batch — the main generation entry point."""

    async def test_happy_path_single_image(self, sample_char_map):
        """count=1 returns list with 1 result dict, status=completed."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert results[0]["images"] == ["gen_luigi_test.png"]
        assert results[0]["prompt_id"] == "prompt-123"

    async def test_character_not_found_raises_value_error(self, sample_char_map):
        """Raises ValueError when character_slug is not in the char map."""
        with patch(
            "packages.core.generation.get_char_project_map",
            new_callable=AsyncMock,
            return_value=sample_char_map,
        ):
            with pytest.raises(ValueError, match="not found"):
                await generate_batch(character_slug="nonexistent")

    async def test_no_checkpoint_raises_value_error(self, sample_char_map):
        """Raises ValueError when the character has no checkpoint_model configured."""
        char_map_no_checkpoint = {
            "luigi": {**sample_char_map["luigi"], "checkpoint_model": None},
        }
        with patch(
            "packages.core.generation.get_char_project_map",
            new_callable=AsyncMock,
            return_value=char_map_no_checkpoint,
        ):
            with pytest.raises(ValueError, match="No checkpoint"):
                await generate_batch(character_slug="luigi")

    async def test_comfyui_submit_failure_returns_empty(self, sample_char_map):
        """When ComfyUI submission raises, that job is skipped; returns empty."""
        p = _make_generate_batch_patches(
            sample_char_map,
            submit_side_effect=ConnectionError("ComfyUI down"),
        )
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        assert results == []

    async def test_seed_override_is_passed_through(self, sample_char_map):
        """When seed is provided, it appears in the result dict."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"] as mock_build:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi", count=1, seed=99999
            )

        # build_comfyui_workflow should have been called with seed=99999
        assert mock_build.called
        _, kwargs = mock_build.call_args
        assert kwargs["seed"] == 99999

    async def test_prompt_override_uses_custom_prompt(self, sample_char_map):
        """With prompt_override, the override is used as design_prompt."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"] as mock_build:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi",
                count=1,
                prompt_override="custom override prompt",
            )

        assert len(results) == 1
        # The workflow's design_prompt should contain the override
        _, kwargs = mock_build.call_args
        assert "custom override prompt" in kwargs["design_prompt"]
        # When prompt_override is set, style_preamble and positive_template
        # should NOT be prepended
        assert "Illumination Studios style" not in kwargs["design_prompt"]

    async def test_fire_events_false_does_not_emit(self, sample_char_map):
        """With fire_events=False, event_bus.emit is never called."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi", count=1, fire_events=False
            )

        assert len(results) == 1
        mock_bus.emit.assert_not_called()

    async def test_fire_events_true_emits_generation_submitted(self, sample_char_map):
        """With fire_events=True (default), emits GENERATION_SUBMITTED."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi", count=1, fire_events=True
            )

        assert len(results) == 1
        mock_bus.emit.assert_called_once()
        emit_args = mock_bus.emit.call_args
        # First arg is the event name constant
        event_data = emit_args[0][1]
        assert event_data["character_slug"] == "luigi"
        assert event_data["prompt_id"] == "prompt-123"

    async def test_pose_variation_true_has_nonempty_pose(self, sample_char_map):
        """With pose_variation=True, each job's pose field is non-empty."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi", count=1, pose_variation=True
            )

        assert len(results) == 1
        assert results[0]["pose"] != ""

    async def test_pose_variation_false_has_empty_pose(self, sample_char_map):
        """With pose_variation=False, pose field is empty string."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi", count=1, pose_variation=False
            )

        assert len(results) == 1
        assert results[0]["pose"] == ""

    async def test_include_feedback_negatives_true_calls_get_feedback(
        self, sample_char_map
    ):
        """With include_feedback_negatives=True, get_feedback_negatives is called."""
        p = _make_generate_batch_patches(
            sample_char_map, feedback_return="bad hands, extra fingers"
        )
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], \
             p["feedback"] as mock_feedback, \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi",
                count=1,
                include_feedback_negatives=True,
            )

        mock_feedback.assert_called_once_with("luigi")
        # The feedback negatives should appear in the negative_prompt
        assert "bad hands, extra fingers" in results[0]["negative_prompt"]

    async def test_include_feedback_negatives_false_skips(self, sample_char_map):
        """With include_feedback_negatives=False, get_feedback_negatives is not called."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], \
             p["feedback"] as mock_feedback, \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi",
                count=1,
                include_feedback_negatives=False,
            )

        mock_feedback.assert_not_called()

    async def test_include_learned_negatives_true_calls_recommend(
        self, sample_char_map
    ):
        """With include_learned_negatives=True, recommend_params is called."""
        p = _make_generate_batch_patches(
            sample_char_map,
            recommend_return={
                "learned_negatives": "blurry eyes, wrong colors",
                "confidence": "medium",
            },
        )
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], \
             p["recommend"] as mock_recommend, p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi",
                count=1,
                include_learned_negatives=True,
            )

        mock_recommend.assert_called_once()
        # Learned negatives should be in the negative prompt
        assert "blurry eyes, wrong colors" in results[0]["negative_prompt"]

    async def test_include_learned_negatives_false_skips_recommend(
        self, sample_char_map
    ):
        """With include_learned_negatives=False, recommend_params is not called."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], \
             p["recommend"] as mock_recommend, p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi",
                count=1,
                include_learned_negatives=False,
            )

        mock_recommend.assert_not_called()

    async def test_poll_timeout_returns_timeout_status(self, sample_char_map):
        """When polling returns None (timeout), result has status='timeout'."""
        p = _make_generate_batch_patches(sample_char_map, poll_return=None)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        assert len(results) == 1
        assert results[0]["status"] == "timeout"
        assert results[0]["images"] == []

    async def test_count_3_submits_3_jobs(self, sample_char_map):
        """count=3 submits 3 jobs and returns 3 results."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"] as mock_submit, p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=3)

        assert len(results) == 3
        # submit_comfyui_workflow should have been called 3 times
        assert mock_submit.call_count == 3
        for r in results:
            assert r["status"] == "completed"

    async def test_register_pending_called_for_each_copied_image(
        self, sample_char_map
    ):
        """register_pending_image is called once per copied image file."""
        p = _make_generate_batch_patches(
            sample_char_map,
            copy_return=["gen_luigi_001.png", "gen_luigi_002.png"],
        )
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"] as mock_register, p["log_gen"], p["recommend"], \
             p["feedback"], p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        assert mock_register.call_count == 2
        mock_register.assert_any_call("luigi", "gen_luigi_001.png")
        mock_register.assert_any_call("luigi", "gen_luigi_002.png")

    async def test_log_generation_called_with_correct_params(self, sample_char_map):
        """log_generation is called with the character slug and project name."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"] as mock_log, p["recommend"], \
             p["feedback"], p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        mock_log.assert_called_once()
        _, kwargs = mock_log.call_args
        assert kwargs["character_slug"] == "luigi"
        assert kwargs["project_name"] == "Super Mario Galaxy Anime Adventure"
        assert kwargs["checkpoint_model"] == "realcartoonPixar_v12.safetensors"
        assert kwargs["comfyui_prompt_id"] == "prompt-123"

    async def test_bowser_character_negatives_in_negative_prompt(
        self, sample_char_map
    ):
        """Bowser's appearance_data with 'NOT human' adds character negatives."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="bowser", count=1)

        assert len(results) == 1
        neg = results[0]["negative_prompt"]
        # Bowser's species is "dragon-turtle (NOT human)" + common_errors has "depicted as child"
        assert "human" in neg
        assert "human face" in neg
        assert "child" in neg

    async def test_recommend_params_exception_is_swallowed(self, sample_char_map):
        """If recommend_params raises, generation continues without learned negatives."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()
            with patch(
                "packages.core.generation.recommend_params",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB connection failed"),
            ):
                results = await generate_batch(
                    character_slug="luigi",
                    count=1,
                    include_learned_negatives=True,
                )

        # Should still complete despite recommend_params failure
        assert len(results) == 1
        assert results[0]["status"] == "completed"

    async def test_seed_increments_for_each_job_in_batch(self, sample_char_map):
        """When seed is provided and count>1, each job gets seed+i."""
        p = _make_generate_batch_patches(sample_char_map)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"] as mock_build:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(
                character_slug="luigi", count=3, seed=1000
            )

        assert mock_build.call_count == 3
        seeds_used = [c[1]["seed"] for c in mock_build.call_args_list]
        assert seeds_used == [1000, 1001, 1002]

    async def test_gen_id_stored_in_result(self, sample_char_map):
        """The generation history ID from log_generation appears in result."""
        p = _make_generate_batch_patches(sample_char_map, log_gen_return=42)
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        assert results[0]["gen_id"] == 42

    async def test_all_submissions_fail_returns_empty_list(self, sample_char_map):
        """When all ComfyUI submissions fail, returns empty list."""
        p = _make_generate_batch_patches(
            sample_char_map,
            submit_side_effect=ConnectionError("ComfyUI unreachable"),
        )
        with p["char_map"], p["submit"], p["poll"], p["copy"], \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=3)

        assert results == []

    async def test_copy_to_dataset_called_with_correct_args(self, sample_char_map):
        """_copy_to_dataset receives the character slug and filenames from poll."""
        p = _make_generate_batch_patches(
            sample_char_map,
            poll_return=["comfyui_output_001.png"],
        )
        with p["char_map"], p["submit"], p["poll"], \
             p["copy"] as mock_copy, \
             p["register"], p["log_gen"], p["recommend"], p["feedback"], \
             p["event_bus"] as mock_bus, p["build_workflow"]:
            mock_bus.emit = AsyncMock()

            results = await generate_batch(character_slug="luigi", count=1)

        mock_copy.assert_called_once()
        _, kwargs = mock_copy.call_args
        assert kwargs["character_slug"] == "luigi"
        assert kwargs["filenames"] == ["comfyui_output_001.png"]
        assert kwargs["project_name"] == "Super Mario Galaxy Anime Adventure"
        assert kwargs["character_name"] == "Luigi"
