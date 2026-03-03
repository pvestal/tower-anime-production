"""Tests for builder.py prompt-construction helpers.

Covers _get_genre_profile, _condense_for_video, and _build_video_negative
without touching the database or ComfyUI.
"""

import pytest

from packages.scene_generation.builder import (
    GENRE_VIDEO_PROFILES,
    _get_genre_profile,
    _condense_for_video,
    _build_video_negative,
)


# ---------------------------------------------------------------------------
# TestGetGenreProfile — 8 tests
# ---------------------------------------------------------------------------

class TestGetGenreProfile:
    """_get_genre_profile(genre, content_rating) → profile dict."""

    def test_explicit_content_rating_overrides_genre(self):
        """NSFW content rating should always return explicit profile."""
        result = _get_genre_profile("romance", "NSFW")
        assert result is GENRE_VIDEO_PROFILES["explicit"]

    def test_explicit_xxx_rating(self):
        result = _get_genre_profile("comedy", "xxx rated")
        assert result is GENRE_VIDEO_PROFILES["explicit"]

    def test_explicit_hentai_rating(self):
        result = _get_genre_profile("anime", "hentai")
        assert result is GENRE_VIDEO_PROFILES["explicit"]

    def test_exact_genre_match(self):
        """Direct key lookup: 'cyberpunk' → cyberpunk profile."""
        result = _get_genre_profile("cyberpunk", None)
        assert result is GENRE_VIDEO_PROFILES["cyberpunk"]

    def test_cyberpunk_keyword_fallback(self):
        """'sci-fi dystopian' should match cyberpunk via keywords."""
        result = _get_genre_profile("sci-fi dystopian", None)
        assert result is GENRE_VIDEO_PROFILES["cyberpunk"]

    def test_action_keyword_fallback(self):
        """'shonen battle anime' should match action."""
        result = _get_genre_profile("shonen battle anime", None)
        assert result is GENRE_VIDEO_PROFILES["action"]

    def test_3d_keyword_fallback(self):
        """'Pixar adventure' should match 3d_animation."""
        result = _get_genre_profile("Pixar adventure", None)
        assert result is GENRE_VIDEO_PROFILES["3d_animation"]

    def test_none_genre_returns_default(self):
        """None genre with no content rating → default profile."""
        result = _get_genre_profile(None, None)
        assert result is GENRE_VIDEO_PROFILES["default"]


# ---------------------------------------------------------------------------
# TestCondenseForVideo — 5 tests
# ---------------------------------------------------------------------------

class TestCondenseForVideo:
    """_condense_for_video(design_prompt, genre_profile, engine)."""

    def test_framepack_reorders_by_priority(self):
        """FramePack should reorder tags by genre priority buckets."""
        prompt = "red jacket, young woman, short hair, confident expression"
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _condense_for_video(prompt, profile, "framepack")
        parts = [p.strip() for p in result.split(",")]
        # identity tags ('young woman') should come before clothing ('red jacket')
        assert parts.index("young woman") < parts.index("red jacket")

    def test_strips_solo_and_1girl(self):
        """'solo' and '1girl' boilerplate tags should be removed."""
        prompt = "solo, 1girl, blue hair, smiling"
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _condense_for_video(prompt, profile, "framepack")
        assert "solo" not in result.lower().split(", ")
        assert "1girl" not in result.lower().split(", ")
        assert "blue hair" in result
        assert "smiling" in result

    def test_wan_aggressive_condense(self):
        """Wan engine should only keep tags matching genre keep_categories."""
        prompt = "young man, sword, dark hair, spaceship interior, neon visor"
        profile = GENRE_VIDEO_PROFILES["cyberpunk"]
        result = _condense_for_video(prompt, profile, "wan")
        # cyberpunk keeps: identity, hair, skin, body, face, equipment, clothing, cybernetics
        # 'sword' matches equipment, 'dark hair' matches hair, 'neon visor' matches cybernetics
        assert "sword" in result
        assert "dark hair" in result
        assert "neon visor" in result

    def test_empty_prompt_returns_empty(self):
        """Empty input should return the original (empty) prompt."""
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _condense_for_video("", profile, "wan")
        assert result == ""

    def test_all_filtered_returns_original(self):
        """If all tags are filtered out, return the original prompt."""
        prompt = "solo, 1girl, score_9, score_8_up"
        profile = GENRE_VIDEO_PROFILES["default"]
        # After stripping all boilerplate, nothing remains → fallback to original
        result = _condense_for_video(prompt, profile, "wan")
        assert result == prompt


# ---------------------------------------------------------------------------
# TestBuildVideoNegative — 5 tests
# ---------------------------------------------------------------------------

class TestBuildVideoNegative:
    """_build_video_negative(style_anchor, genre_profile, nsm_negative)."""

    def test_base_always_present(self):
        """Base negative terms should always be included."""
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _build_video_negative("", profile)
        assert "low quality" in result
        assert "blurry" in result
        assert "deformed face" in result
        assert "bad hands" in result

    def test_photorealistic_excludes_anime(self):
        """Photorealistic style should add anime/cartoon exclusions."""
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _build_video_negative("photorealistic, cinematic", profile)
        assert "anime" in result
        assert "cartoon" in result
        assert "illustration" in result

    def test_anime_excludes_photo(self):
        """Anime style should add photorealistic exclusions."""
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _build_video_negative("anime style, detailed", profile)
        assert "photorealistic" in result
        assert "photograph" in result
        assert "live action" in result

    def test_genre_additions_included(self):
        """Genre-specific negative additions should be appended."""
        profile = GENRE_VIDEO_PROFILES["cyberpunk"]
        result = _build_video_negative("", profile)
        assert "modern casual" in result
        assert "peaceful" in result

    def test_nsm_negative_appended(self):
        """NSM character state negative should be appended."""
        profile = GENRE_VIDEO_PROFILES["default"]
        result = _build_video_negative("", profile, nsm_negative="wrong eye color")
        assert "wrong eye color" in result
        # Base should still be there
        assert "low quality" in result
