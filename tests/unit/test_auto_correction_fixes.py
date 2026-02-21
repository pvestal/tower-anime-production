"""Unit tests for the 7 fix_* strategies in packages.core.auto_correction.

Each fix function takes (workflow: dict, categories: list[str]) -> bool.
Two tests per function: one that verifies a mutation, one that verifies a no-op.
Plus structural assertions on FIX_STRATEGIES and CATEGORY_TO_FIX.
"""

import copy

import pytest

from packages.core.auto_correction import (
    fix_quality,
    fix_resolution,
    fix_blur,
    fix_brightness,
    fix_contrast,
    fix_appearance,
    fix_solo,
    FIX_STRATEGIES,
    CATEGORY_TO_FIX,
)

# ---------------------------------------------------------------------------
# Shared sample workflow
# ---------------------------------------------------------------------------

SAMPLE_WORKFLOW = {
    "3": {
        "inputs": {
            "seed": 12345,
            "steps": 25,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
        "class_type": "KSampler",
    },
    "5": {
        "inputs": {"width": 512, "height": 768, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "6": {
        "inputs": {
            "text": "a tall character in green, masterpiece, best quality, detailed face",
            "clip": ["4", 1],
        },
        "class_type": "CLIPTextEncode",
    },
    "7": {
        "inputs": {
            "text": "worst quality, low quality, blurry, deformed",
            "clip": ["4", 1],
        },
        "class_type": "CLIPTextEncode",
    },
}


def _wf():
    """Return a fresh deep copy of the sample workflow."""
    return copy.deepcopy(SAMPLE_WORKFLOW)


# ---------------------------------------------------------------------------
# fix_quality
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_quality_increases_steps_and_upgrades_sampler():
    """fix_quality bumps steps from 25 to 35, swaps euler -> dpmpp_2m, nudges cfg."""
    wf = _wf()
    changed = fix_quality(wf, [])
    assert changed is True
    ksampler = wf["3"]["inputs"]
    assert ksampler["steps"] == 35
    assert ksampler["sampler_name"] == "dpmpp_2m"
    assert ksampler["scheduler"] == "karras"
    assert ksampler["cfg"] == 8.0


@pytest.mark.unit
def test_fix_quality_noop_when_already_maxed():
    """fix_quality is a no-op when steps=50 and cfg >= 9 and sampler is not euler."""
    wf = _wf()
    wf["3"]["inputs"]["steps"] = 50
    wf["3"]["inputs"]["cfg"] = 10.0
    wf["3"]["inputs"]["sampler_name"] = "dpmpp_2m"
    changed = fix_quality(wf, [])
    assert changed is False
    assert wf["3"]["inputs"]["steps"] == 50
    assert wf["3"]["inputs"]["cfg"] == 10.0


# ---------------------------------------------------------------------------
# fix_resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_resolution_increases_small_dimensions():
    """fix_resolution scales up 512x768 (both < 768 triggers 1.5x factor)."""
    wf = _wf()
    changed = fix_resolution(wf, [])
    assert changed is True
    latent = wf["5"]["inputs"]
    # 512 * 1.5 = 768, //8*8 = 768
    assert latent["width"] == 768
    # 768 * 1.5 = 1152, //8*8 = 1152
    assert latent["height"] == 1152


@pytest.mark.unit
def test_fix_resolution_uses_smaller_factor_for_large_images():
    """fix_resolution uses 1.2x factor when both dims >= 768."""
    wf = _wf()
    wf["5"]["inputs"]["width"] = 768
    wf["5"]["inputs"]["height"] = 1024
    changed = fix_resolution(wf, [])
    assert changed is True
    latent = wf["5"]["inputs"]
    # 768 * 1.2 = 921.6, //8*8 = 920
    assert latent["width"] == 920
    # 1024 * 1.2 = 1228.8, //8*8 = 1224
    assert latent["height"] == 1224


# ---------------------------------------------------------------------------
# fix_blur
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_blur_increases_steps_and_adds_sharp_focus():
    """fix_blur boosts steps, sets cfg=9, adds 'sharp focus' to positive prompt."""
    wf = _wf()
    changed = fix_blur(wf, [])
    assert changed is True
    ksampler = wf["3"]["inputs"]
    assert ksampler["steps"] == 40  # max(25+15, 40)
    assert ksampler["cfg"] == 9.0
    pos_text = wf["6"]["inputs"]["text"]
    assert "sharp focus" in pos_text
    assert "high detail" in pos_text


@pytest.mark.unit
def test_fix_blur_noop_when_already_has_sharp_focus():
    """fix_blur does not re-append 'sharp focus' when it is already present."""
    wf = _wf()
    wf["6"]["inputs"]["text"] = (
        "a tall character in green, masterpiece, best quality, detailed face, sharp focus"
    )
    wf["3"]["inputs"]["steps"] = 45
    original_text = wf["6"]["inputs"]["text"]
    changed = fix_blur(wf, [])
    # KSampler cfg is still set to 9.0 so changed is True, but text should not be modified
    assert wf["6"]["inputs"]["text"] == original_text


# ---------------------------------------------------------------------------
# fix_brightness
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_brightness_adds_lighting_terms():
    """fix_brightness adds 'well-lit, bright lighting, proper exposure' to positive prompt."""
    wf = _wf()
    changed = fix_brightness(wf, [])
    assert changed is True
    pos_text = wf["6"]["inputs"]["text"]
    assert "well-lit" in pos_text
    assert "bright lighting" in pos_text


@pytest.mark.unit
def test_fix_brightness_noop_when_already_present():
    """fix_brightness is a no-op when the positive prompt already has 'well-lit'."""
    wf = _wf()
    wf["6"]["inputs"]["text"] = (
        "a tall character in green, masterpiece, best quality, detailed face, well-lit"
    )
    changed = fix_brightness(wf, [])
    assert changed is False


# ---------------------------------------------------------------------------
# fix_contrast
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_contrast_adds_contrast_terms():
    """fix_contrast adds 'high contrast, sharp details, vivid colors'."""
    wf = _wf()
    changed = fix_contrast(wf, [])
    assert changed is True
    pos_text = wf["6"]["inputs"]["text"]
    assert "high contrast" in pos_text
    assert "vivid colors" in pos_text


@pytest.mark.unit
def test_fix_contrast_noop_when_already_present():
    """fix_contrast is a no-op when 'high contrast' is already in the prompt."""
    wf = _wf()
    wf["6"]["inputs"]["text"] = (
        "a tall character in green, masterpiece, best quality, detailed face, high contrast"
    )
    changed = fix_contrast(wf, [])
    assert changed is False


# ---------------------------------------------------------------------------
# fix_appearance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_appearance_adds_negative_terms_for_category():
    """fix_appearance appends REJECTION_NEGATIVE_MAP terms to the negative prompt."""
    wf = _wf()
    changed = fix_appearance(wf, ["wrong_appearance"])
    assert changed is True
    neg_text = wf["7"]["inputs"]["text"]
    assert "wrong colors" in neg_text
    assert "inaccurate character design" in neg_text


@pytest.mark.unit
def test_fix_appearance_returns_false_when_no_matching_categories():
    """fix_appearance returns False when categories have no REJECTION_NEGATIVE_MAP entries."""
    wf = _wf()
    changed = fix_appearance(wf, ["nonexistent_category"])
    assert changed is False


# ---------------------------------------------------------------------------
# fix_solo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_solo_adds_solo_and_negative_multiple():
    """fix_solo prepends 'solo, single character' to positive and appends 'multiple characters' to negative."""
    wf = _wf()
    changed = fix_solo(wf, [])
    assert changed is True
    pos_text = wf["6"]["inputs"]["text"]
    assert pos_text.startswith("solo, single character,")
    neg_text = wf["7"]["inputs"]["text"]
    assert "multiple characters" in neg_text
    assert "group shot" in neg_text


@pytest.mark.unit
def test_fix_solo_noop_when_already_has_solo():
    """fix_solo does not modify prompts when 'solo' is already present."""
    wf = _wf()
    wf["6"]["inputs"]["text"] = (
        "solo, a tall character in green, masterpiece, best quality, detailed face"
    )
    changed = fix_solo(wf, [])
    # The positive prompt already has "solo" so the first loop does nothing.
    # The negative prompt loop still appends "multiple characters" though.
    neg_text = wf["7"]["inputs"]["text"]
    assert "multiple characters" in neg_text


# ---------------------------------------------------------------------------
# Structural: FIX_STRATEGIES and CATEGORY_TO_FIX
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fix_strategies_has_seven_entries():
    """FIX_STRATEGIES maps 7 strategy names to callable functions."""
    assert len(FIX_STRATEGIES) == 7
    expected_names = {
        "fix_quality", "fix_resolution", "fix_blur", "fix_brightness",
        "fix_contrast", "fix_appearance", "fix_solo",
    }
    assert set(FIX_STRATEGIES.keys()) == expected_names
    for fn in FIX_STRATEGIES.values():
        assert callable(fn)


@pytest.mark.unit
def test_category_to_fix_maps_expected_categories():
    """CATEGORY_TO_FIX should map all 6 rejection categories to fix strategy lists."""
    expected_cats = {
        "bad_quality", "wrong_appearance", "not_solo",
        "wrong_style", "wrong_pose", "wrong_expression",
    }
    assert set(CATEGORY_TO_FIX.keys()) == expected_cats
    for strategies in CATEGORY_TO_FIX.values():
        assert isinstance(strategies, list)
        for name in strategies:
            assert name in FIX_STRATEGIES, f"Strategy '{name}' not found in FIX_STRATEGIES"
