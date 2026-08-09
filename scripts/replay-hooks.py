#!/usr/bin/env python3
"""POST hook payloads at a running daemon, without needing Claude Code.

    python3 scripts/replay-hooks.py                  # a scripted demo session
    python3 scripts/replay-hooks.py fixtures/*.json  # replay captured payloads

Capturing real payloads is worth doing: a recorded PermissionRequest body is
worth more than any schema transcribed by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEMO = [
    {"hook_event_name": "SessionStart", "session_id": "demo-1", "cwd": "/home/you/zmk-sofle"},
    {"hook_event_name": "SessionStart", "session_id": "demo-2", "cwd": "/home/you/soflectl"},
    {"hook_event_name": "UserPromptSubmit", "session_id": "demo-1"},
    {"hook_event_name": "PreToolUse", "session_id": "demo-1", "tool_name": "Grep"},
    {"hook_event_name": "PostToolUse", "session_id": "demo-1", "tool_name": "Grep"},
    {
        "hook_event_name": "PermissionRequest",
        "session_id": "demo-2",
        "tool_name": "Read",
        "tool_input": {"file_path": "/home/you/soflectl/README.md"},
    },
    {"hook_event_name": "Stop", "session_id": "demo-1"},
]


def post(url: str, payload: dict, timeout: float) -> None:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    label = f"{payload.get('hook_event_name')} [{payload.get('session_id')}]"
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode().strip()
            print(f"{label}: {response.status} {text}")
    except urllib.error.URLError as exc:
        print(f"{label}: FAILED {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="JSON files to replay; omit for a demo")
    parser.add_argument("--url", default="http://127.0.0.1:8787/hook")
    parser.add_argument("--delay", type=float, default=0.8, help="seconds between events")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if args.files:
        payloads = [json.loads(open(path).read()) for path in args.files]
    else:
        payloads = DEMO
        print("replaying a demo session; a PermissionRequest will block until you")
        print("press a button on the keyboard (or type into --fake-hid stdin)\n")

    for payload in payloads:
        post(args.url, payload, args.timeout)
        time.sleep(args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
