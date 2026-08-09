"""The table of live Claude Code sessions, plus which one the buttons act on."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .protocol import Status


@dataclass
class SessionState:
    session_id: str
    title: str = ""
    cwd: str = ""
    status: Status = Status.IDLE
    detail: list[str] = field(default_factory=list)
    last_tool: str = ""
    pending_count: int = 0
    updated_at: float = field(default_factory=time.monotonic)


def short_cwd(cwd: str) -> str:
    """Last path component, which is usually the repository name."""
    if not cwd:
        return "?"
    return cwd.rstrip("/").rsplit("/", 1)[-1] or "/"


class Registry:
    """Ordered session table with a focus cursor.

    Order is insertion order, so cycling with the encoder is stable rather than
    jumping around as sessions update.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._order: list[str] = []
        self._focus: int = 0

    # -- mutation -------------------------------------------------------

    def upsert(self, session_id: str, **fields) -> SessionState:
        st = self._sessions.get(session_id)
        if st is None:
            st = SessionState(session_id=session_id)
            self._sessions[session_id] = st
            self._order.append(session_id)
        for key, value in fields.items():
            setattr(st, key, value)
        st.updated_at = time.monotonic()
        return st

    def drop(self, session_id: str) -> None:
        if session_id not in self._sessions:
            return
        idx = self._order.index(session_id)
        del self._sessions[session_id]
        del self._order[idx]
        if not self._order:
            self._focus = 0
        elif idx < self._focus or self._focus >= len(self._order):
            # Keep pointing at the same session where possible, and never off
            # the end of the list.
            self._focus = max(0, min(self._focus - 1, len(self._order) - 1))

    # -- reads ----------------------------------------------------------

    def count(self) -> int:
        return len(self._order)

    def focus_index(self) -> int:
        return self._focus

    def focus_pos(self) -> str:
        """Human-facing '2/4', or empty when there is nothing to show."""
        if not self._order:
            return ""
        return f"{self._focus + 1}/{len(self._order)}"

    def focused(self) -> SessionState | None:
        if not self._order:
            return None
        return self._sessions[self._order[self._focus]]

    def all(self) -> list[SessionState]:
        return [self._sessions[sid] for sid in self._order]

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    # -- focus ----------------------------------------------------------

    def focus_next(self, step: int = 1) -> None:
        if not self._order:
            self._focus = 0
            return
        self._focus = (self._focus + step) % len(self._order)

    def focus_on(self, session_id: str) -> bool:
        try:
            self._focus = self._order.index(session_id)
        except ValueError:
            return False
        return True

    def auto_focus_waiting(self) -> None:
        """Point focus at the longest-waiting session that needs an answer.

        This is the single most important correctness detail in the daemon. If
        focus could drift, you would eventually approve session B's write while
        reading session A on the screen.
        """
        waiting = [
            self._sessions[sid]
            for sid in self._order
            if self._sessions[sid].status == Status.WAITING
            and self._sessions[sid].pending_count > 0
        ]
        if not waiting:
            return
        oldest = min(waiting, key=lambda s: s.updated_at)
        self.focus_on(oldest.session_id)
