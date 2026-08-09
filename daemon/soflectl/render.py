"""Registry -> screen. Pure functions, no I/O; this is the tested part."""

from __future__ import annotations

from .pending import PendingTable
from .protocol import COLS, ROWS, Status
from .registry import Registry, SessionState

# Detail views cycled by the UP hold.
DETAIL_TOOL = 0
DETAIL_CWD = 1
DETAIL_TITLE = 2
DETAIL_MODES = 3

_STATUS_TEXT = {
    Status.IDLE: "idle",
    Status.THINKING: "thinking",
    Status.TOOL: "running",
    Status.WAITING: "WAITING",
    Status.DONE: "done",
    Status.ERROR: "ERROR",
    Status.OFFLINE: "offline",
}


def _fit(text: str, cols: int) -> str:
    return text[:cols]


def _session_line(st: SessionState, cols: int, marker: str) -> str:
    """One session as a list row: marker, title, status."""
    status = _STATUS_TEXT.get(st.status, "?")
    badge = "!" if st.pending_count else " "
    # Keep the status readable and give whatever is left to the title.
    title_room = max(1, cols - len(status) - 3)
    title = _fit(st.title or st.session_id[:6], title_room)
    return _fit(f"{marker}{badge}{title:<{title_room}} {status}", cols)


def build_frame(
    reg: Registry,
    pending: PendingTable,
    detail_mode: int = DETAIL_TOOL,
    rows: int = ROWS,
    cols: int = COLS,
) -> tuple[list[str], tuple]:
    """Return (frame lines, sync tuple).

    The frame is exactly `rows` strings of at most `cols` characters.
    """
    lines: list[str] = []
    focused = reg.focused()

    if focused is None:
        lines = ["soflectl", "", "no sessions"]
        sync = (int(Status.IDLE), 0, 0, 0, "", "")
        return _pad(lines, rows, cols), sync

    request = pending.get(focused.session_id)

    if request is not None:
        # An approval is on screen. Nothing else matters; give it the display.
        lines = [
            "APPROVE?",
            _fit(focused.title, cols),
            "",
            _fit(request.tool_name, cols),
            _fit(request.summary, cols),
            "",
            "L = no",
            "R = yes",
            "D = terminal",
        ]
    else:
        header = f"soflectl {reg.focus_pos()}"
        lines = [_fit(header, cols), ""]

        for st in reg.all():
            marker = ">" if st.session_id == focused.session_id else " "
            lines.append(_session_line(st, cols, marker))

        lines.append("")
        if detail_mode == DETAIL_CWD:
            lines.append(_fit(focused.cwd.rsplit("/", 1)[-1], cols))
        elif detail_mode == DETAIL_TITLE:
            lines.append(_fit(focused.title, cols))
        else:
            lines.append(_fit(focused.last_tool, cols))

    sync = (
        int(focused.status),
        min(255, focused.pending_count),
        reg.focus_index(),
        reg.count(),
        focused.title,
        focused.last_tool,
    )
    return _pad(lines, rows, cols), sync


def _pad(lines: list[str], rows: int, cols: int) -> list[str]:
    out = [_fit(line, cols) for line in lines[:rows]]
    out.extend("" for _ in range(rows - len(out)))
    return out
