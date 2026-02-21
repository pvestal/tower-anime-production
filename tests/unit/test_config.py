"""Unit tests for packages.core.config — sampler normalization and path constants."""

from pathlib import Path

import pytest

from packages.core.config import BASE_PATH, SAMPLER_MAP, normalize_sampler


@pytest.mark.unit
def test_normalize_sampler_dpmpp_2m_karras():
    """DPM++ 2M Karras maps to (dpmpp_2m, karras)."""
    assert normalize_sampler("DPM++ 2M Karras", None) == ("dpmpp_2m", "karras")


@pytest.mark.unit
def test_normalize_sampler_dpmpp_2m_sde_karras():
    """DPM++ 2M SDE Karras maps to (dpmpp_2m_sde, karras)."""
    assert normalize_sampler("DPM++ 2M SDE Karras", None) == ("dpmpp_2m_sde", "karras")


@pytest.mark.unit
def test_normalize_sampler_euler_a():
    """Euler a maps to (euler_ancestral, normal)."""
    assert normalize_sampler("Euler a", None) == ("euler_ancestral", "normal")


@pytest.mark.unit
def test_normalize_sampler_ddim():
    """DDIM maps to (ddim, ddim_uniform)."""
    assert normalize_sampler("DDIM", None) == ("ddim", "ddim_uniform")


@pytest.mark.unit
def test_normalize_sampler_none_defaults():
    """None sampler and scheduler fall back to (dpmpp_2m, karras)."""
    assert normalize_sampler(None, None) == ("dpmpp_2m", "karras")


@pytest.mark.unit
def test_normalize_sampler_unknown_passthrough():
    """Unknown sampler name is passed through unchanged with the given scheduler."""
    assert normalize_sampler("unknown_sampler", "custom_sched") == ("unknown_sampler", "custom_sched")


@pytest.mark.unit
def test_normalize_sampler_unknown_name_no_scheduler():
    """Unknown sampler with None scheduler falls back to karras for scheduler."""
    assert normalize_sampler("my_custom_sampler", None) == ("my_custom_sampler", "karras")


@pytest.mark.unit
def test_sampler_map_has_minimum_entries():
    """SAMPLER_MAP should have at least 8 entries."""
    assert len(SAMPLER_MAP) >= 8


@pytest.mark.unit
def test_base_path_is_datasets_directory():
    """BASE_PATH should be a Path ending with 'datasets'."""
    assert isinstance(BASE_PATH, Path)
    assert BASE_PATH.name == "datasets"
