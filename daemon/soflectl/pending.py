"""Permission requests waiting on a button press."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

log = logging.getLogger(__name__)

Decision = Literal["allow", "deny", "defer"]


@dataclass
class Pending:
    session_id: str
    tool_name: str
    summary: str  # already truncated for the display
    tool_input: dict = field(default_factory=dict)
    future: asyncio.Future = field(default_factory=asyncio.Future)


class PendingTable:
    """One outstanding request per session.

    Claude Code serialises permission prompts within a session, so a second
    request arriving for a session that already has one is a surprise worth
    logging rather than quietly handling.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, Pending] = {}

    def open(
        self, session_id: str, tool_name: str, summary: str, tool_input: dict | None = None
    ) -> Pending:
        existing = self._by_session.get(session_id)
        if existing is not None:
            log.warning(
                "second pending request for session %s (%s) while %s was outstanding; "
                "deferring the older one",
                session_id,
                tool_name,
                existing.tool_name,
            )
            self.resolve(session_id, "defer")

        pending = Pending(
            session_id=session_id,
            tool_name=tool_name,
            summary=summary,
            tool_input=tool_input or {},
            future=asyncio.get_running_loop().create_future(),
        )
        self._by_session[session_id] = pending
        return pending

    def get(self, session_id: str) -> Pending | None:
        return self._by_session.get(session_id)

    def resolve(self, session_id: str, decision: Decision) -> bool:
        """Settle a pending request. False if there was nothing to settle.

        Safe to call twice; the second call is a no-op. The server relies on
        that for its cleanup path.
        """
        pending = self._by_session.pop(session_id, None)
        if pending is None:
            return False
        if not pending.future.done():
            pending.future.set_result(decision)
            return True
        return False

    def any_waiting(self) -> bool:
        return bool(self._by_session)
