"""Daemon configuration.

Key bindings live here rather than in the firmware, so changing what a button
does needs a daemon restart rather than a reflash. The firmware only reports
which physical control moved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "soflectl"
    return Path.home() / ".local" / "state" / "soflectl"


@dataclass
class Config:
    # --- hook server ---------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8787

    # --- HID link ------------------------------------------------------
    # 0 means "match any vendor/product"; the usage page and usage are what
    # actually identify the right interface. Run scripts/find-device.py to see
    # what your keyboard exposes.
    vid: int = 0x0000
    pid: int = 0x0000
    usage_page: int = 0xFF60
    usage_id: int = 0x61
    report_size: int = 32

    # --- approvals -----------------------------------------------------
    # How long a PermissionRequest waits for a button before giving up and
    # letting Claude Code show its own prompt. Must stay below the hook's own
    # timeout in settings.json, or the hook is cancelled first.
    approve_timeout_s: float = 90.0

    # Only these tools may be approved from the keyboard. Everything else falls
    # straight through to the normal on-screen prompt. Widening this is a
    # deliberate edit, never a default. See docs/soflectl.md.
    hardware_approvable: set[str] = field(
        default_factory=lambda: {
            "Read",
            "Grep",
            "Glob",
            "WebSearch",
            "WebFetch",
            "Edit",
            "Write",
            "NotebookEdit",
        }
    )

    # Bash is deliberately absent above: a 16-character screen cannot show you
    # a reviewable command. Narrow allowances go here instead, matched as
    # prefixes against tool_input.command after stripping VAR=value prefixes.
    bash_prefix_allow: tuple[str, ...] = (
        "git status",
        "git diff",
        "git log",
        "npm test",
        "pytest",
    )

    # --- bindings ------------------------------------------------------
    bindings: dict[str, str] = field(
        default_factory=lambda: {
            "RIGHT:tap": "approve",
            "LEFT:tap": "deny",
            "DOWN:tap": "focus_next",
            "UP:tap": "focus_prev",
            "UP:hold": "cycle_detail",
            "CENTER:tap": "ack",
            "CENTER:hold": "halt",
            "ENC0:cw": "focus_next",
            "ENC0:ccw": "focus_prev",
        }
    )

    # --- logging -------------------------------------------------------
    state_dir: Path = field(default_factory=_default_state_dir)

    @property
    def decision_log(self) -> Path:
        return self.state_dir / "decisions.jsonl"
