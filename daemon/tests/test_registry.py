"""Focus behaviour. Drift here means approving the wrong session."""

from __future__ import annotations

import time

from soflectl.protocol import Status
from soflectl.registry import Registry


def test_upsert_creates_then_updates():
    reg = Registry()
    reg.upsert("s1", title="a")
    reg.upsert("s1", title="b")
    assert reg.count() == 1
    assert reg.focused().title == "b"


def test_order_is_insertion_order():
    reg = Registry()
    for i in range(3):
        reg.upsert(f"s{i}", title=str(i))
    assert [s.title for s in reg.all()] == ["0", "1", "2"]


def test_focus_wraps_both_ways():
    reg = Registry()
    for i in range(3):
        reg.upsert(f"s{i}")
    reg.focus_next(+1)
    reg.focus_next(+1)
    assert reg.focus_index() == 2
    reg.focus_next(+1)
    assert reg.focus_index() == 0
    reg.focus_next(-1)
    assert reg.focus_index() == 2


def test_focus_on_empty_registry_is_safe():
    reg = Registry()
    reg.focus_next(+1)
    assert reg.focused() is None
    assert reg.focus_pos() == ""


def test_drop_keeps_focus_in_range():
    reg = Registry()
    for i in range(3):
        reg.upsert(f"s{i}")
    reg.focus_next(+2)          # focus on s2, the last one
    reg.drop("s2")
    assert reg.focus_index() < reg.count()
    assert reg.focused() is not None


def test_drop_last_session_leaves_nothing_focused():
    reg = Registry()
    reg.upsert("s1")
    reg.drop("s1")
    assert reg.focused() is None
    assert reg.count() == 0


def test_drop_unknown_session_is_a_noop():
    reg = Registry()
    reg.upsert("s1")
    reg.drop("nope")
    assert reg.count() == 1


def test_auto_focus_waiting_picks_the_oldest_waiter():
    reg = Registry()
    reg.upsert("s0", status=Status.IDLE)
    older = reg.upsert("s1", status=Status.WAITING, pending_count=1)
    time.sleep(0.01)
    reg.upsert("s2", status=Status.WAITING, pending_count=1)

    reg.focus_next(+0)
    reg.auto_focus_waiting()
    assert reg.focused().session_id == older.session_id


def test_auto_focus_waiting_ignores_waiters_without_a_request():
    reg = Registry()
    reg.upsert("s0", status=Status.IDLE)
    reg.upsert("s1", status=Status.WAITING, pending_count=0)
    reg.auto_focus_waiting()
    assert reg.focused().session_id == "s0"


def test_auto_focus_waiting_leaves_focus_alone_when_nobody_waits():
    reg = Registry()
    reg.upsert("s0")
    reg.upsert("s1")
    reg.focus_next(+1)
    reg.auto_focus_waiting()
    assert reg.focus_index() == 1
