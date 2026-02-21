"""Unit tests for vision helper functions in packages.visual_pipeline.vision.

Tests extract_json_from_vision, vision_issues_to_categories, build_feature_checklist,
and the VISION_ISSUE_TO_REJECTION mapping.
"""

import pytest

from packages.visual_pipeline.vision import (
    extract_json_from_vision,
    vision_issues_to_categories,
    build_feature_checklist,
    VISION_ISSUE_TO_REJECTION,
)


# ---------------------------------------------------------------------------
# extract_json_from_vision
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_json_plain_valid():
    """Plain valid JSON string is parsed correctly."""
    result = extract_json_from_vision('{"key": "value"}')
    assert result == {"key": "value"}


@pytest.mark.unit
def test_extract_json_markdown_fences():
    """JSON wrapped in ```json ... ``` markdown fences is extracted."""
    raw = '```json\n{"character_match": 8, "solo": true}\n```'
    result = extract_json_from_vision(raw)
    assert result == {"character_match": 8, "solo": True}


@pytest.mark.unit
def test_extract_json_surrounding_text():
    """JSON embedded in surrounding prose is found and parsed."""
    raw = 'Here is the result: {"key": "value"} done.'
    result = extract_json_from_vision(raw)
    assert result == {"key": "value"}


@pytest.mark.unit
def test_extract_json_empty_string():
    """Empty string returns None."""
    assert extract_json_from_vision("") is None


@pytest.mark.unit
def test_extract_json_no_json_at_all():
    """Plain text with no braces returns None."""
    assert extract_json_from_vision("just some text with no JSON") is None


@pytest.mark.unit
def test_extract_json_malformed():
    """Malformed JSON (unclosed brace) returns None."""
    assert extract_json_from_vision('{"key": ') is None


@pytest.mark.unit
def test_extract_json_nested_object():
    """Nested JSON objects are extracted correctly."""
    raw = '{"outer": {"inner": 42}, "list": [1, 2, 3]}'
    result = extract_json_from_vision(raw)
    assert result == {"outer": {"inner": 42}, "list": [1, 2, 3]}


# ---------------------------------------------------------------------------
# vision_issues_to_categories
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_issues_solo_false():
    """solo=False in the review produces 'not_solo' category."""
    review = {"solo": False, "clarity": 8, "character_match": 8, "issues": []}
    cats = vision_issues_to_categories(review)
    assert "not_solo" in cats


@pytest.mark.unit
def test_issues_low_clarity():
    """clarity < 5 produces 'bad_quality' category."""
    review = {"solo": True, "clarity": 3, "character_match": 8, "issues": []}
    cats = vision_issues_to_categories(review)
    assert "bad_quality" in cats


@pytest.mark.unit
def test_issues_low_character_match():
    """character_match < 4 produces 'wrong_appearance' category."""
    review = {"solo": True, "clarity": 8, "character_match": 2, "issues": []}
    cats = vision_issues_to_categories(review)
    assert "wrong_appearance" in cats


@pytest.mark.unit
def test_issues_keyword_match_in_issues_list():
    """Issue string containing 'blurry' keyword maps to 'bad_quality'."""
    review = {
        "solo": True,
        "clarity": 8,
        "character_match": 8,
        "issues": ["blurry image, out of focus"],
    }
    cats = vision_issues_to_categories(review)
    assert "bad_quality" in cats


@pytest.mark.unit
def test_issues_perfect_review_empty():
    """A perfect review (high scores, no issues, solo=True) yields an empty list."""
    review = {
        "solo": True,
        "clarity": 9,
        "character_match": 9,
        "training_value": 9,
        "issues": [],
    }
    cats = vision_issues_to_categories(review)
    assert cats == []


# ---------------------------------------------------------------------------
# build_feature_checklist
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_feature_checklist_with_species_and_colors():
    """Checklist includes species and key color entries."""
    appearance = {
        "species": "dragon-turtle (NOT human)",
        "key_colors": {"shell": "green", "skin": "yellow-orange"},
    }
    result = build_feature_checklist(appearance)
    assert "Species/Type: dragon-turtle (NOT human)" in result
    assert "shell: green" in result
    assert "skin: yellow-orange" in result


@pytest.mark.unit
def test_build_feature_checklist_empty_dict():
    """Empty appearance dict returns empty string."""
    assert build_feature_checklist({}) == ""


@pytest.mark.unit
def test_build_feature_checklist_none_input():
    """None input returns empty string."""
    assert build_feature_checklist(None) == ""


# ---------------------------------------------------------------------------
# VISION_ISSUE_TO_REJECTION structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vision_issue_to_rejection_has_expected_categories():
    """VISION_ISSUE_TO_REJECTION values should all be valid rejection categories."""
    valid_categories = {"not_solo", "bad_quality", "wrong_appearance", "wrong_style", "wrong_pose"}
    for keyword, category in VISION_ISSUE_TO_REJECTION.items():
        assert category in valid_categories, (
            f"Keyword '{keyword}' maps to unexpected category '{category}'"
        )
