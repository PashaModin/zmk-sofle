"""End-to-end through the aiohttp app, with a recording stand-in for the link."""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from soflectl import protocol
from soflectl.config import Config
from soflectl.protocol import Status
from soflectl.server import make_app, on_hid_event


class RecordingLink:
    """Captures what would have gone to the keyboard."""

    def __init__(self, cfg, on_event):
        self.cfg = cfg
        self.on_event = on_event
        self.rows = protocol.ROWS
        self.cols = protocol.COLS
        self.frames: list[list[str]] = []
        self.modes: list[int] = []
        self.syncs: list[tuple] = []
        self.cleared = 0

    def send_frame(self, lines):
        self.frames.append(list(lines))

    def set_line(self, row, text):
        pass

    def set_sync(self, *args):
        self.syncs.append(args)

    def set_mode(self, mode):
        self.modes.append(mode)

    def clear(self):
        self.cleared += 1

    def note_geometry(self, rows, cols):
        pass

    async def run(self):
        await asyncio.Event().wait()


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.state_dir = tmp_path / "state"
    c.approve_timeout_s = 1.0
    return c


@pytest.fixture
async def client(cfg, aiohttp_client):
    app = make_app(cfg, lambda on_event: RecordingLink(cfg, on_event))
    return await aiohttp_client(app)


async def post(client, payload):
    return await client.post("/hook", json=payload)


async def test_session_lifecycle(client):
    app = client.app
    resp = await post(client, {
        "hook_event_name": "SessionStart",
        "session_id": "s1",
        "cwd": "/home/me/zmk-sofle",
    })
    assert resp.status == 204
    assert app["reg"].count() == 1
    assert app["reg"].focused().title == "zmk-sofle"

    await post(client, {"hook_event_name": "SessionEnd", "session_id": "s1"})
    assert app["reg"].count() == 0


async def test_tool_events_update_status(client):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})
    await post(client, {
        "hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Read",
    })
    assert app["reg"].get("s1").status == Status.TOOL
    assert app["reg"].get("s1").last_tool == "Read"

    await post(client, {"hook_event_name": "Stop", "session_id": "s1"})
    assert app["reg"].get("s1").status == Status.DONE


async def test_unknown_event_is_ignored(client):
    resp = await post(client, {"hook_event_name": "SomethingNew", "session_id": "s1"})
    assert resp.status == 204


async def test_malformed_body_does_not_500(client):
    resp = await client.post("/hook", data="not json")
    assert resp.status == 204


async def test_ineligible_tool_gets_no_decision(client):
    """Anything off the allowlist must fall straight through to the terminal."""
    resp = await post(client, {
        "hook_event_name": "PermissionRequest",
        "session_id": "s1",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"},
    })
    assert resp.status == 204
    assert await resp.text() == ""


async def test_approve_from_a_button(client):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})

    task = asyncio.create_task(post(client, {
        "hook_event_name": "PermissionRequest",
        "session_id": "s1",
        "tool_name": "Read",
        "tool_input": {"file_path": "/x/notes.md"},
    }))

    # Wait for the request to register as pending.
    for _ in range(100):
        await asyncio.sleep(0.01)
        if app["pending"].get("s1") is not None:
            break
    assert app["pending"].get("s1") is not None
    assert protocol.MODE_PENDING in app["link"].modes

    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.RIGHT, protocol.ACT_TAP]))

    resp = await task
    body = await resp.json()
    assert body["hookSpecificOutput"]["decision"]["behavior"] == "allow"
    assert app["link"].modes[-1] == protocol.MODE_NORMAL


async def test_deny_from_a_button(client):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})

    task = asyncio.create_task(post(client, {
        "hook_event_name": "PermissionRequest",
        "session_id": "s1",
        "tool_name": "Read",
        "tool_input": {"file_path": "/x/notes.md"},
    }))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if app["pending"].get("s1") is not None:
            break

    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.LEFT, protocol.ACT_TAP]))

    body = await (await task).json()
    assert body["hookSpecificOutput"]["decision"]["behavior"] == "deny"


async def test_timeout_defers_and_never_approves(client, cfg):
    cfg.approve_timeout_s = 0.05
    resp = await post(client, {
        "hook_event_name": "PermissionRequest",
        "session_id": "s1",
        "tool_name": "Read",
        "tool_input": {"file_path": "/x"},
    })
    assert resp.status == 204          # no decision -> Claude Code prompts
    assert await resp.text() == ""


async def test_button_with_nothing_pending_does_nothing(client):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})
    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.RIGHT, protocol.ACT_TAP]))
    assert app["reg"].get("s1").status == Status.IDLE


async def test_focus_moves_to_the_session_that_is_asking(client):
    """The button must act on what the screen shows, never a stale selection."""
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/a"})
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s2", "cwd": "/b"})
    assert app["reg"].focused().session_id == "s1"

    task = asyncio.create_task(post(client, {
        "hook_event_name": "PermissionRequest",
        "session_id": "s2",
        "tool_name": "Read",
        "tool_input": {"file_path": "/b/x"},
    }))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if app["pending"].get("s2") is not None:
            break

    assert app["reg"].focused().session_id == "s2"

    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.RIGHT, protocol.ACT_TAP]))
    body = await (await task).json()
    assert body["hookSpecificOutput"]["decision"]["behavior"] == "allow"


async def test_encoder_cycles_focus(client):
    app = client.app
    for i in range(3):
        await post(client, {"hook_event_name": "SessionStart", "session_id": f"s{i}", "cwd": f"/{i}"})
    await on_hid_event(app, protocol.EV_ENCODER, bytes([0, 1]))
    assert app["reg"].focus_index() == 1
    await on_hid_event(app, protocol.EV_ENCODER, bytes([0, 0]))
    assert app["reg"].focus_index() == 0


async def test_hello_resets_the_display(client):
    app = client.app
    await on_hid_event(app, protocol.EV_HELLO, bytes([1, protocol.ROWS, protocol.COLS]))
    assert app["link"].cleared == 1


async def test_ack_clears_a_finished_session(client):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})
    await post(client, {"hook_event_name": "Stop", "session_id": "s1"})
    assert app["reg"].get("s1").status == Status.DONE
    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.CENTER, protocol.ACT_TAP]))
    assert app["reg"].get("s1").status == Status.IDLE


async def test_halt_takes_effect_at_the_next_hook(client):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})
    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.CENTER, protocol.ACT_HOLD]))
    assert "s1" in app["halt_requested"]

    resp = await post(client, {
        "hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Read",
    })
    body = await resp.json()
    assert body["continue"] is False
    assert "s1" not in app["halt_requested"]   # consumed, not sticky


async def test_decision_log_records_the_untruncated_input(client, cfg):
    app = client.app
    await post(client, {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/x"})
    long_path = "/x/" + "y" * 200
    task = asyncio.create_task(post(client, {
        "hook_event_name": "PermissionRequest",
        "session_id": "s1",
        "tool_name": "Read",
        "tool_input": {"file_path": long_path},
    }))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if app["pending"].get("s1") is not None:
            break
    await on_hid_event(app, protocol.EV_BUTTON, bytes([protocol.Button.RIGHT, protocol.ACT_TAP]))
    await task

    text = cfg.decision_log.read_text()
    assert long_path in text
    assert '"decision": "allow"' in text


async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status == 200
    assert (await resp.json())["sessions"] == 0
