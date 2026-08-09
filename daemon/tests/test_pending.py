"""Resolution races: the failure modes here approve the wrong thing."""

from __future__ import annotations

import asyncio

import pytest

from soflectl.pending import PendingTable


async def test_open_then_resolve():
    table = PendingTable()
    req = table.open("s1", "Read", "x")
    assert table.resolve("s1", "allow") is True
    assert await req.future == "allow"


async def test_resolving_nothing_is_false_not_an_error():
    assert PendingTable().resolve("nope", "allow") is False


async def test_resolve_twice_is_idempotent():
    # server.py's finally-block always resolves, even after a button already did.
    table = PendingTable()
    req = table.open("s1", "Read", "x")
    assert table.resolve("s1", "allow") is True
    assert table.resolve("s1", "defer") is False
    assert await req.future == "allow"


async def test_get_returns_none_after_resolution():
    table = PendingTable()
    table.open("s1", "Read", "x")
    assert table.get("s1") is not None
    table.resolve("s1", "deny")
    assert table.get("s1") is None


async def test_second_request_defers_the_first():
    table = PendingTable()
    first = table.open("s1", "Read", "a")
    second = table.open("s1", "Write", "b")
    assert await first.future == "defer"
    assert table.get("s1") is second


async def test_sessions_are_independent():
    table = PendingTable()
    a = table.open("s1", "Read", "a")
    b = table.open("s2", "Read", "b")
    table.resolve("s1", "allow")
    assert await a.future == "allow"
    assert not b.future.done()
    assert table.any_waiting() is True
    table.resolve("s2", "deny")
    assert table.any_waiting() is False


async def test_timeout_race_against_a_late_resolve():
    """A button pressed just after the timeout must not leak a decision."""
    table = PendingTable()
    req = table.open("s1", "Read", "x")

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(req.future), timeout=0.01)

    # The server's finally-block resolves to defer; a later button press finds
    # nothing pending and is a no-op rather than approving a dead request.
    assert table.resolve("s1", "defer") is True
    assert table.resolve("s1", "allow") is False
    assert await req.future == "defer"
