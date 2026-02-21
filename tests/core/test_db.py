"""Tests for packages.core.db — connection pool, cache management, constants."""

import pytest

from packages.core.db import invalidate_char_cache
import packages.core.db as db_module
from packages.core.replenishment import DEFAULT_TARGET, MAX_CONCURRENT


@pytest.mark.unit
def test_invalidate_char_cache_clears_cache():
    """invalidate_char_cache empties _char_project_cache and resets _cache_time."""
    # Set cache to non-empty state
    db_module._char_project_cache = {
        "luigi": {"name": "Luigi", "slug": "luigi"},
        "bowser": {"name": "Bowser", "slug": "bowser"},
    }
    db_module._cache_time = 9999999.0

    invalidate_char_cache()

    assert db_module._char_project_cache == {}
    assert db_module._cache_time == 0


@pytest.mark.unit
def test_default_target_is_reasonable():
    """DEFAULT_TARGET should be a positive integer in a sensible range."""
    assert isinstance(DEFAULT_TARGET, int)
    assert 5 <= DEFAULT_TARGET <= 100


@pytest.mark.unit
def test_max_concurrent_is_reasonable():
    """MAX_CONCURRENT should be a small positive integer."""
    assert isinstance(MAX_CONCURRENT, int)
    assert 1 <= MAX_CONCURRENT <= 10
