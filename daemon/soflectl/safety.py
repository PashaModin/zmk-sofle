"""What may be approved from the keyboard, and how it is summarised.

A physical approve button is an approval-fatigue machine, and a 16-character
screen cannot show a reviewable command. The rules here are deliberately
conservative; see docs/soflectl.md for the reasoning.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

# Leading `VAR=value` assignments, which would otherwise hide the real command
# from a prefix match: `FOO=bar rm -rf /` must not pass as an allowed prefix.
_ASSIGNMENT = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*=(\"[^\"]*\"|'[^']*'|\S*)(\s+|$)")

# Anything that chains, substitutes, or redirects means the text after the
# allowed prefix can do something entirely different. `git diff && rm -rf /`
# starts with an allowed prefix and is obviously not allowed.
_SHELL_METACHARACTERS = re.compile(r"[;&|<>`$()\n]")


def strip_env_assignments(command: str) -> str:
    """Remove leading VAR=value pairs from a shell command."""
    previous = None
    current = command
    while previous != current:
        previous = current
        current = _ASSIGNMENT.sub("", current, count=1)
    return current.strip()


def bash_command_allowed(cfg: Config, command: str) -> bool:
    """True if a Bash command matches one of the narrow allowed prefixes."""
    if not command or not command.strip():
        return False

    stripped = strip_env_assignments(command)
    if not stripped:
        return False

    # Reject before prefix matching, not after: the prefix is only meaningful
    # if it describes the whole command.
    if _SHELL_METACHARACTERS.search(stripped):
        return False

    collapsed = " ".join(stripped.split())
    for prefix in cfg.bash_prefix_allow:
        if collapsed == prefix or collapsed.startswith(prefix + " "):
            return True
    return False


def eligible_for_hardware_approval(cfg: Config, tool_name: str, tool_input: dict) -> bool:
    """Whether this request may be answered with a button at all.

    Anything returning False gets no decision from us, so Claude Code shows its
    normal prompt. That is the safe direction.
    """
    if not tool_name:
        return False

    if tool_name == "Bash":
        return bash_command_allowed(cfg, (tool_input or {}).get("command", ""))

    return tool_name in cfg.hardware_approvable


def summarize(tool_name: str, tool_input: dict, width: int = 16) -> str:
    """One line describing the request, truncated for the display.

    Truncation keeps the head of the string. `rm -rf /very/long/path` cut from
    the right still reads `rm -rf /very/lon`, which tells you what you need;
    cut from the left it reads `/long/path`, which tells you nothing.
    """
    tool_input = tool_input or {}

    if tool_name == "Bash":
        text = " ".join(str(tool_input.get("command", "")).split())
    elif tool_name in ("Read", "Edit", "Write", "NotebookEdit"):
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        # The tail of a path is the informative part, unlike a command.
        text = path.rsplit("/", 1)[-1] if path else ""
    elif tool_name in ("Grep", "Glob"):
        text = str(tool_input.get("pattern", ""))
    elif tool_name in ("WebFetch", "WebSearch"):
        text = str(tool_input.get("url") or tool_input.get("query") or "")
    else:
        text = ""

    text = " ".join(text.split())
    return text[:width]


def log_decision(
    cfg: Config,
    *,
    session_id: str,
    tool_name: str,
    tool_input: dict,
    decision: str,
    source: str,
) -> None:
    """Append one decision to the audit log.

    This is what lets you answer "what did I approve at 2am". The untruncated
    tool input is recorded deliberately - the screen only ever showed you a
    summary, so the log has to hold the rest.
    """
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "decision": decision,
            "source": source,
        }
        with cfg.decision_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        # Never let logging break an approval; the button press matters more.
        log.warning("could not write decision log: %s", exc)
