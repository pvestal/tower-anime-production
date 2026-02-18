"""Unit tests for packages.core.generation — build_character_negatives and POSE_VARIATIONS."""

import json

import pytest

from packages.core.generation import build_character_negatives, POSE_VARIATIONS


@pytest.mark.unit
class TestBuildCharacterNegatives:
    """Tests for build_character_negatives(appearance_data) -> str."""

    def test_none_returns_empty(self):
        assert build_character_negatives(None) == ""

    def test_empty_dict_returns_empty(self):
        assert build_character_negatives({}) == ""

    def test_empty_string_returns_empty(self):
        assert build_character_negatives("") == ""

    def test_invalid_json_string_returns_empty(self):
        assert build_character_negatives("not valid json {{{") == ""

    def test_dragon_turtle_not_human_includes_human_negatives(self):
        result = build_character_negatives({"species": "dragon-turtle (NOT human)"})
        for term in ("human", "human face", "human skin"):
            assert term in result, f"Expected '{term}' in result: {result}"

    def test_star_shaped_creature_includes_child_negatives(self):
        result = build_character_negatives({"species": "star-shaped creature (NOT human)"})
        for term in ("child", "boy", "girl", "humanoid"):
            assert term in result, f"Expected '{term}' in result: {result}"

    def test_mushroom_creature_includes_mushroom_negatives(self):
        result = build_character_negatives({"species": "mushroom creature (NOT human)"})
        for term in ("human child", "boy wearing hat"):
            assert term in result, f"Expected '{term}' in result: {result}"

    def test_human_species_no_not_human_marker(self):
        result = build_character_negatives({"species": "human"})
        assert result == ""

    def test_common_errors_depicted_as_child(self):
        result = build_character_negatives({"common_errors": ["depicted as child"]})
        for term in ("child", "teenager"):
            assert term in result, f"Expected '{term}' in result: {result}"

    def test_common_errors_letter_m_instead_of_l(self):
        result = build_character_negatives({"common_errors": ["letter M instead of L on cap"]})
        assert "letter M on cap" in result

    def test_json_string_input_parsed_correctly(self):
        data = {"species": "dragon-turtle (NOT human)", "common_errors": ["depicted as child"]}
        result_from_dict = build_character_negatives(data)
        result_from_str = build_character_negatives(json.dumps(data))
        assert result_from_dict == result_from_str
        assert "human" in result_from_str
        assert "child" in result_from_str

    def test_pose_variations_has_at_least_15_entries(self):
        assert len(POSE_VARIATIONS) >= 15

    def test_pose_variations_all_nonempty_strings(self):
        for pose in POSE_VARIATIONS:
            assert isinstance(pose, str), f"Expected str, got {type(pose)}"
            assert len(pose) > 0, "Found empty pose variation"
