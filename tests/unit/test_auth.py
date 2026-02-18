"""Unit tests for packages.core.auth — trusted network check and rate limiter."""

import pytest

from packages.core.auth import RateLimiter, is_trusted_network


# ---------------------------------------------------------------------------
# is_trusted_network
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_trusted_network_local_subnet():
    """192.168.50.100 is in the 192.168.50.0/24 trusted range."""
    assert is_trusted_network("192.168.50.100") is True


@pytest.mark.unit
def test_trusted_network_localhost():
    """127.0.0.1 is in the 127.0.0.0/8 trusted range."""
    assert is_trusted_network("127.0.0.1") is True


@pytest.mark.unit
def test_untrusted_network_public_ip():
    """8.8.8.8 is not in any trusted network."""
    assert is_trusted_network("8.8.8.8") is False


@pytest.mark.unit
def test_untrusted_network_invalid_ip():
    """Invalid IP string returns False (no exception)."""
    assert is_trusted_network("invalid") is False


@pytest.mark.unit
def test_trusted_network_loopback_variant():
    """127.0.0.254 is also in 127.0.0.0/8."""
    assert is_trusted_network("127.0.0.254") is True


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_rate_limiter_allows_within_limit():
    """First N requests within the limit are allowed."""
    limiter = RateLimiter()
    assert limiter.is_allowed("user1", 3, 60) is True
    assert limiter.is_allowed("user1", 3, 60) is True
    assert limiter.is_allowed("user1", 3, 60) is True


@pytest.mark.unit
def test_rate_limiter_blocks_over_limit():
    """The (N+1)th request within the window is blocked."""
    limiter = RateLimiter()
    for _ in range(3):
        limiter.is_allowed("user2", 3, 60)
    assert limiter.is_allowed("user2", 3, 60) is False


@pytest.mark.unit
def test_rate_limiter_separate_keys():
    """Different keys have independent counters."""
    limiter = RateLimiter()
    for _ in range(3):
        limiter.is_allowed("key_a", 3, 60)
    # key_a is exhausted
    assert limiter.is_allowed("key_a", 3, 60) is False
    # key_b is fresh
    assert limiter.is_allowed("key_b", 3, 60) is True
