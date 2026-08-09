"""HTTP hook endpoint and button dispatch.

Claude Code POSTs every lifecycle event to a single URL; we dispatch on
hook_event_name. Only PermissionRequest blocks - it waits for a button press,
and everything else is a fast registry write plus a screen update.
"""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from . import protocol, render
from .config import Config
from .pending import PendingTable
from .protocol import Status
from .registry import Registry, short_cwd
from .safety import eligible_for_hardware_approval, log_decision, summarize

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------------


async def paint(app: web.Application) -> None:
    link = app["link"]
    lines, sync = render.build_frame(
        app["reg"], app["pending"], app["detail_mode"], rows=link.rows, cols=link.cols
    )
    link.send_frame(lines)
    link.set_sync(*sync)


def _halt_response(app: web.Application, session_id: str) -> web.Response | None:
    """Consume a pending halt request for this session, if any.

    There is no channel to a session between hook calls, so a halt can only be
    delivered on the next hook that session happens to fire. That means "stops
    at the next checkpoint", not "stops now".
    """
    if session_id in app["halt_requested"]:
        app["halt_requested"].discard(session_id)
        log.info("halting session %s at this checkpoint", session_id)
        return web.json_response(
            {"continue": False, "stopReason": "Halted from the keyboard"}
        )
    return None


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------


async def on_session_start(app, sid, body):
    cwd = body.get("cwd", "")
    app["reg"].upsert(
        sid,
        status=Status.IDLE,
        cwd=cwd,
        title=body.get("session_title") or short_cwd(cwd),
    )
    await paint(app)
    return web.Response(status=204)


async def on_session_end(app, sid, body):
    app["reg"].drop(sid)
    app["pending"].resolve(sid, "defer")
    await paint(app)
    return web.Response(status=204)


async def on_user_prompt_submit(app, sid, body):
    app["reg"].upsert(sid, status=Status.THINKING)
    await paint(app)
    return _halt_response(app, sid) or web.Response(status=204)


async def on_pre_tool_use(app, sid, body):
    app["reg"].upsert(sid, status=Status.TOOL, last_tool=body.get("tool_name", ""))
    await paint(app)
    return _halt_response(app, sid) or web.Response(status=204)


async def on_post_tool_use(app, sid, body):
    st = app["reg"].get(sid)
    # Leave WAITING alone: a permission request may still be outstanding.
    if st is not None and st.status != Status.WAITING:
        app["reg"].upsert(sid, status=Status.THINKING)
    await paint(app)
    return web.Response(status=204)


async def on_post_tool_failure(app, sid, body):
    app["reg"].upsert(sid, status=Status.ERROR, last_tool=body.get("tool_name", ""))
    await paint(app)
    return web.Response(status=204)


async def on_notification(app, sid, body):
    kind = body.get("notification_type", "")
    if kind in ("idle_prompt", "agent_needs_input"):
        app["reg"].upsert(sid, status=Status.WAITING)
    elif kind == "agent_completed":
        app["reg"].upsert(sid, status=Status.DONE)
    await paint(app)
    return web.Response(status=204)


async def on_stop(app, sid, body):
    app["reg"].upsert(sid, status=Status.DONE, last_tool="")
    await paint(app)
    return web.Response(status=204)


async def on_stop_failure(app, sid, body):
    app["reg"].upsert(sid, status=Status.ERROR)
    await paint(app)
    return web.Response(status=204)


async def on_teammate_idle(app, sid, body):
    app["reg"].upsert(sid, status=Status.WAITING)
    await paint(app)
    return web.Response(status=204)


async def on_permission_request(app, sid, body):
    """The one that blocks. Waits for a button, or falls through to Claude."""
    cfg: Config = app["cfg"]
    tool = body.get("tool_name", "")
    tool_input = body.get("tool_input") or {}

    if not eligible_for_hardware_approval(cfg, tool, tool_input):
        # No decision: Claude Code shows its own prompt, unchanged.
        return web.Response(status=204)

    st = app["reg"].upsert(sid, status=Status.WAITING, last_tool=tool)
    st.pending_count += 1

    request = app["pending"].open(sid, tool, summarize(tool, tool_input, app["link"].cols), tool_input)

    # Focus must move before the screen is painted, so the button always acts
    # on the thing that just started blinking.
    app["reg"].auto_focus_waiting()
    app["link"].set_mode(protocol.MODE_PENDING)
    await paint(app)

    try:
        decision = await asyncio.wait_for(request.future, timeout=cfg.approve_timeout_s)
    except asyncio.TimeoutError:
        # Timing out never approves. It hands the decision back to the terminal.
        decision = "defer"
    except asyncio.CancelledError:
        app["pending"].resolve(sid, "defer")
        raise
    finally:
        app["pending"].resolve(sid, "defer")  # idempotent cleanup
        st.pending_count = max(0, st.pending_count - 1)
        if st.status == Status.WAITING:
            st.status = Status.TOOL
        if not app["pending"].any_waiting():
            app["link"].set_mode(protocol.MODE_NORMAL)
        await paint(app)

    log_decision(
        cfg,
        session_id=sid,
        tool_name=tool,
        tool_input=tool_input,
        decision=decision,
        source="keyboard",
    )

    if decision == "allow":
        return web.json_response(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "allow"},
                }
            }
        )

    if decision == "deny":
        return web.json_response(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": "Denied from the keyboard",
                    },
                }
            }
        )

    # defer: no decision, so the normal prompt appears.
    return web.Response(status=204)


HANDLERS = {
    "SessionStart": on_session_start,
    "SessionEnd": on_session_end,
    "UserPromptSubmit": on_user_prompt_submit,
    "PreToolUse": on_pre_tool_use,
    "PermissionRequest": on_permission_request,
    "PostToolUse": on_post_tool_use,
    "PostToolUseFailure": on_post_tool_failure,
    "Notification": on_notification,
    "Stop": on_stop,
    "StopFailure": on_stop_failure,
    "TeammateIdle": on_teammate_idle,
}


async def handle_hook(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        log.warning("hook body was not JSON")
        return web.Response(status=204)

    event = body.get("hook_event_name")
    sid = body.get("session_id") or "?"

    handler = HANDLERS.get(event)
    if handler is None:
        return web.Response(status=204)

    try:
        return await handler(request.app, sid, body)
    except asyncio.CancelledError:
        raise
    except Exception:
        # A broken daemon must never break a session. Returning 204 means "no
        # opinion", which is the same as not being here at all.
        log.exception("hook handler for %s failed", event)
        return web.Response(status=204)


async def handle_health(request: web.Request) -> web.Response:
    reg: Registry = request.app["reg"]
    return web.json_response(
        {
            "sessions": reg.count(),
            "focus": reg.focus_index(),
            "pending": request.app["pending"].any_waiting(),
        }
    )


# ---------------------------------------------------------------------------
# Button dispatch
# ---------------------------------------------------------------------------


async def do_action(app: web.Application, action: str | None) -> None:
    if not action:
        return

    reg: Registry = app["reg"]
    pending: PendingTable = app["pending"]
    st = reg.focused()

    if action in ("approve", "deny", "defer"):
        if st is None or pending.get(st.session_id) is None:
            return  # nothing pending: a press here does nothing at all
        pending.resolve(
            st.session_id,
            {"approve": "allow", "deny": "deny", "defer": "defer"}[action],
        )
    elif action == "focus_next":
        reg.focus_next(+1)
    elif action == "focus_prev":
        reg.focus_next(-1)
    elif action == "ack":
        if st is not None and st.status in (Status.DONE, Status.ERROR):
            reg.upsert(st.session_id, status=Status.IDLE)
    elif action == "cycle_detail":
        app["detail_mode"] = (app["detail_mode"] + 1) % render.DETAIL_MODES
    elif action == "halt":
        if st is not None:
            app["halt_requested"].add(st.session_id)
            log.info("halt queued for %s; takes effect at its next checkpoint", st.session_id)
    else:
        log.warning("unknown action %r", action)

    await paint(app)


async def on_hid_event(app: web.Application, op: int, payload: bytes) -> None:
    cfg: Config = app["cfg"]

    if op == protocol.EV_BUTTON and len(payload) >= 2:
        try:
            name = protocol.Button(payload[0]).name
        except ValueError:
            return
        action = "hold" if payload[1] == protocol.ACT_HOLD else "tap"
        await do_action(app, cfg.bindings.get(f"{name}:{action}"))

    elif op == protocol.EV_ENCODER and len(payload) >= 2:
        key = f"ENC{payload[0]}:{'cw' if payload[1] else 'ccw'}"
        await do_action(app, cfg.bindings.get(key))

    elif op == protocol.EV_HELLO and len(payload) >= 3:
        log.info("keyboard hello: protocol v%d, %dx%d", payload[0], payload[2], payload[1])
        app["link"].note_geometry(payload[1], payload[2])
        app["link"].clear()
        await paint(app)

    elif op == protocol.EV_PONG:
        pass


def make_app(cfg: Config, link_factory) -> web.Application:
    app = web.Application()
    app["cfg"] = cfg
    app["reg"] = Registry()
    app["pending"] = PendingTable()
    app["detail_mode"] = render.DETAIL_TOOL
    app["halt_requested"] = set()

    async def on_event(op: int, payload: bytes) -> None:
        await on_hid_event(app, op, payload)

    app["link"] = link_factory(on_event)

    app.router.add_post("/hook", handle_hook)
    app.router.add_get("/health", handle_health)

    async def start_link(app_: web.Application):
        task = asyncio.create_task(app_["link"].run())
        await paint(app_)
        yield
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    app.cleanup_ctx.append(start_link)
    return app
