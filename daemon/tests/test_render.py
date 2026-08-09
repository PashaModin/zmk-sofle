"""Golden frames. The width here is the width the firmware actually has."""

from __future__ import annotations

import pytest

from soflectl import render
from soflectl.pending import PendingTable
from soflectl.protocol import COLS, ROWS, Status
from soflectl.registry import Registry, short_cwd


@pytest.fixture
def reg():
    return Registry()


@pytest.fixture
def pending():
    return PendingTable()


def test_no_sessions(reg, pending):
    lines, sync = render.build_frame(reg, pending)
    assert lines[0] == "soflectl"
    assert lines[2] == "no sessions"
    assert len(lines) == ROWS
    assert sync == (int(Status.IDLE), 0, 0, 0, "", "")


def test_frame_is_always_exactly_the_right_shape(reg, pending):
    for count in range(0, 6):
        reg_local = Registry()
        for i in range(count):
            reg_local.upsert(f"s{i}", title=f"repo{i}", status=Status.TOOL)
        lines, _ = render.build_frame(reg_local, pending)
        assert len(lines) == ROWS
        assert all(len(line) <= COLS for line in lines), lines


def test_single_session_lists_and_marks_focus(reg, pending):
    reg.upsert("s1", title="zmk-sofle", status=Status.THINKING, last_tool="Read")
    lines, sync = render.build_frame(reg, pending)
    assert lines[0] == "soflectl 1/1"
    assert lines[2].startswith(">")
    assert "zmk-sofle"[:4] in lines[2]
    assert sync[0] == int(Status.THINKING)
    assert sync[3] == 1


def test_four_sessions_all_listed_focus_marked(reg, pending):
    for i in range(4):
        reg.upsert(f"s{i}", title=f"repo{i}", status=Status.IDLE)
    reg.focus_next(+2)
    lines, sync = render.build_frame(reg, pending)
    assert lines[0] == "soflectl 3/4"
    marked = [line for line in lines if line.startswith(">")]
    assert len(marked) == 1
    assert "repo2" in marked[0]
    assert sync[2] == 2 and sync[3] == 4


async def test_pending_request_takes_over_the_screen(reg, pending):
    reg.upsert("s1", title="zmk-sofle", status=Status.WAITING)
    pending.open("s1", "Read", "notes.md")
    lines, sync = render.build_frame(reg, pending)
    assert lines[0] == "APPROVE?"
    assert "Read" in lines
    assert "notes.md" in lines
    # The three outcomes must be spelled out; you should never have to remember.
    joined = " ".join(lines)
    assert "L = no" in joined and "R = yes" in joined and "D = terminal" in joined


async def test_pending_for_another_session_does_not_hijack_the_screen(reg, pending):
    reg.upsert("s1", title="a", status=Status.IDLE)
    reg.upsert("s2", title="b", status=Status.WAITING)
    pending.open("s2", "Read", "x")
    # Focus is still s1, so we must NOT show s2's approval prompt.
    lines, _ = render.build_frame(reg, pending)
    assert lines[0] != "APPROVE?"


def test_non_ascii_title_does_not_break_width(reg, pending):
    reg.upsert("s1", title="café-☕-repo", status=Status.IDLE)
    lines, _ = render.build_frame(reg, pending)
    assert all(len(line) <= COLS for line in lines)


def test_long_title_is_truncated_not_wrapped(reg, pending):
    reg.upsert("s1", title="a" * 100, status=Status.IDLE, last_tool="b" * 100)
    lines, _ = render.build_frame(reg, pending)
    assert all(len(line) <= COLS for line in lines)


def test_detail_modes_change_the_last_line(reg, pending):
    reg.upsert("s1", title="t", cwd="/home/me/zmk-sofle", last_tool="Grep", status=Status.IDLE)
    tool, _ = render.build_frame(reg, pending, render.DETAIL_TOOL)
    cwd, _ = render.build_frame(reg, pending, render.DETAIL_CWD)
    title, _ = render.build_frame(reg, pending, render.DETAIL_TITLE)
    assert "Grep" in tool
    assert "zmk-sofle" in cwd
    assert "t" in title


def test_pending_badge_shows_in_the_list(reg, pending):
    reg.upsert("s1", title="repo", status=Status.WAITING, pending_count=1)
    lines, sync = render.build_frame(reg, pending)
    assert any("!" in line for line in lines)
    assert sync[1] == 1


def test_short_cwd():
    assert short_cwd("/home/me/zmk-sofle") == "zmk-sofle"
    assert short_cwd("/home/me/zmk-sofle/") == "zmk-sofle"
    assert short_cwd("") == "?"
    assert short_cwd("/") == "/"
