"""Unit tests for packages.core.events — EventBus async event emitter."""

import asyncio

import pytest

from packages.core.events import (
    GENERATION_SUBMITTED,
    IMAGE_APPROVED,
    IMAGE_REJECTED,
    EventBus,
)


@pytest.mark.unit
def test_eventbus_starts_empty():
    """A fresh EventBus has no handlers and zero emit count."""
    bus = EventBus()
    assert bus._emit_count == 0
    assert bus._error_count == 0
    assert len(bus._handlers) == 0


@pytest.mark.unit
def test_on_decorator_registers_handler():
    """The @bus.on() decorator registers an async handler."""
    bus = EventBus()

    @bus.on("test.event")
    async def handler(data):
        pass

    assert len(bus._handlers["test.event"]) == 1
    assert bus._handlers["test.event"][0] is handler


@pytest.mark.unit
def test_subscribe_registers_handler():
    """bus.subscribe() registers a handler imperatively."""
    bus = EventBus()

    async def my_handler(data):
        pass

    bus.subscribe("test.event", my_handler)
    assert len(bus._handlers["test.event"]) == 1
    assert bus._handlers["test.event"][0] is my_handler


@pytest.mark.unit
async def test_emit_calls_handler():
    """emit() invokes registered handlers with event data."""
    bus = EventBus()
    received = []

    @bus.on("test.event")
    async def handler(data):
        received.append(data)

    await bus.emit("test.event", {"key": "value"})
    assert len(received) == 1
    assert received[0]["key"] == "value"
    assert bus._emit_count == 1


@pytest.mark.unit
async def test_emit_calls_multiple_handlers():
    """emit() invokes all registered handlers concurrently."""
    bus = EventBus()
    results = []

    @bus.on("multi")
    async def handler_a(data):
        results.append("a")

    @bus.on("multi")
    async def handler_b(data):
        results.append("b")

    await bus.emit("multi", {"x": 1})
    assert sorted(results) == ["a", "b"]
    assert bus._emit_count == 1


@pytest.mark.unit
async def test_emit_no_handlers_no_error():
    """emit() with no handlers for the event does not raise or increment counters."""
    bus = EventBus()
    await bus.emit("nonexistent.event", {"data": 1})
    # emit_count stays 0 because the early return fires before incrementing
    assert bus._emit_count == 0
    assert bus._error_count == 0


@pytest.mark.unit
async def test_handler_error_increments_error_count():
    """A handler that raises is caught; error_count increments, other handlers still run."""
    bus = EventBus()
    good_results = []

    @bus.on("fail")
    async def bad_handler(data):
        raise ValueError("intentional failure")

    @bus.on("fail")
    async def good_handler(data):
        good_results.append("ok")

    await bus.emit("fail", {})
    assert bus._error_count == 1
    assert len(good_results) == 1


@pytest.mark.unit
def test_stats_returns_correct_counts():
    """stats() reflects registered events, handlers, and counters."""
    bus = EventBus()

    @bus.on("event.a")
    async def h1(data):
        pass

    @bus.on("event.a")
    async def h2(data):
        pass

    @bus.on("event.b")
    async def h3(data):
        pass

    stats = bus.stats()
    assert set(stats["registered_events"]) == {"event.a", "event.b"}
    assert stats["total_handlers"] == 3
    assert stats["total_emits"] == 0
    assert stats["total_errors"] == 0


@pytest.mark.unit
def test_event_constants_are_nonempty_strings():
    """Event type constants should be non-empty strings."""
    for const in (IMAGE_APPROVED, IMAGE_REJECTED, GENERATION_SUBMITTED):
        assert isinstance(const, str)
        assert len(const) > 0
