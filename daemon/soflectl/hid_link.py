"""Framing over raw HID, plus a keyboard-free stand-in for development."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Awaitable, Callable, Protocol

from . import protocol
from .config import Config

log = logging.getLogger(__name__)

EventHandler = Callable[[int, bytes], Awaitable[None]]


class Link(Protocol):
    """What the server needs from a transport."""

    rows: int
    cols: int

    def set_line(self, row: int, text: str) -> None: ...
    def set_sync(self, *args) -> None: ...
    def set_mode(self, mode: int) -> None: ...
    def clear(self) -> None: ...
    async def run(self) -> None: ...


class _BaseLink:
    def __init__(self, cfg: Config, on_event: EventHandler) -> None:
        self.cfg = cfg
        self.on_event = on_event
        self.rows = protocol.ROWS
        self.cols = protocol.COLS
        self._last_frame: list[str] | None = None

    # -- framing --------------------------------------------------------

    def _write(self, payload: bytes) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def set_line(self, row: int, text: str) -> None:
        self._write(protocol.pack_set_line(row, text, self.cols))

    def set_sync(self, status, badge, idx, count, label0, label1) -> None:
        self._write(protocol.pack_set_sync(status, badge, idx, count, label0, label1))

    def set_mode(self, mode: int) -> None:
        self._write(protocol.pack_set_mode(mode))

    def clear(self) -> None:
        self._last_frame = None
        self._write(protocol.pack_clear())

    def send_frame(self, lines: list[str]) -> None:
        """Push only the rows that changed.

        Every PostToolUse triggers a repaint, and the keyboard is on the far
        end of a 32-byte-per-report link, so sending 16 unchanged rows on every
        tool call would be pure waste.
        """
        previous = self._last_frame
        for row, text in enumerate(lines[: self.rows]):
            if previous is None or previous[row] != text:
                self.set_line(row, text)
        self._last_frame = list(lines[: self.rows])

    def note_geometry(self, rows: int, cols: int) -> None:
        """Adopt the geometry the keyboard reported in its HELLO packet."""
        if rows and cols and (rows, cols) != (self.rows, self.cols):
            log.info("keyboard reports %dx%d text frame", cols, rows)
            self.rows, self.cols = rows, cols
            self._last_frame = None


class HidLink(_BaseLink):
    """Real keyboard over USB (or BLE) raw HID. Reconnects when unplugged."""

    def __init__(self, cfg: Config, on_event: EventHandler) -> None:
        super().__init__(cfg, on_event)
        self._dev = None

    def _find_path(self):
        import hid

        for info in hid.enumerate(self.cfg.vid, self.cfg.pid):
            if (
                info.get("usage_page") == self.cfg.usage_page
                and info.get("usage") == self.cfg.usage_id
            ):
                return info["path"]
        return None

    def _write(self, payload: bytes) -> None:
        if self._dev is None:
            return
        buf = payload.ljust(self.cfg.report_size, b"\x00")
        # Windows hidapi expects a leading report ID byte; POSIX does not.
        if sys.platform == "win32":
            buf = b"\x00" + buf
        try:
            self._dev.write(buf)
        except OSError as exc:
            log.warning("HID write failed, will reconnect: %s", exc)
            self._close()

    def _close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            except OSError:
                pass
        self._dev = None
        self._last_frame = None

    async def run(self) -> None:
        import hid

        loop = asyncio.get_running_loop()
        complained = False

        while True:
            if self._dev is None:
                path = await loop.run_in_executor(None, self._find_path)
                if path is None:
                    if not complained:
                        log.warning(
                            "no raw HID interface (usage page 0x%04X, usage 0x%02X); "
                            "is the keyboard plugged in and running agentctl?",
                            self.cfg.usage_page,
                            self.cfg.usage_id,
                        )
                        complained = True
                    await asyncio.sleep(1.0)
                    continue
                try:
                    dev = hid.device()
                    dev.open_path(path)
                    dev.set_nonblocking(False)
                except OSError as exc:
                    log.warning("could not open HID device: %s", exc)
                    await asyncio.sleep(1.0)
                    continue
                self._dev = dev
                complained = False
                log.info("connected to keyboard")

            try:
                # Blocking read, so it must not run on the event loop thread.
                data = await loop.run_in_executor(
                    None, self._dev.read, self.cfg.report_size, 200
                )
            except OSError as exc:
                log.info("keyboard went away (%s); waiting for it to come back", exc)
                self._close()
                continue

            if data:
                await self.on_event(data[0], bytes(data[1:]))


class FakeLink(_BaseLink):
    """Prints frames to the terminal and reads button names from stdin.

    Lets the whole hook path be developed and tested with no keyboard attached.
    Input is one token per line: UP, DOWN, LEFT, RIGHT, CENTER, optionally
    suffixed with ' hold', or CW / CCW for the encoder.
    """

    def __init__(self, cfg: Config, on_event: EventHandler) -> None:
        super().__init__(cfg, on_event)
        self._frame = [""] * self.rows
        self._mode = 0

    def _write(self, payload: bytes) -> None:
        op = payload[0]
        if op == protocol.SET_LINE:
            row, length = payload[1], payload[2]
            self._frame[row] = payload[3 : 3 + length].decode("ascii", "replace")
            self._draw()
        elif op == protocol.CLEAR:
            self._frame = [""] * self.rows
            self._draw()
        elif op == protocol.SET_MODE:
            self._mode = payload[1]
            self._draw()

    def _draw(self) -> None:
        border = "+" + "-" * self.cols + "+"
        flag = "  <<< APPROVAL PENDING" if self._mode else ""
        print("\n" + border + flag)
        for line in self._frame:
            print("|" + line.ljust(self.cols)[: self.cols] + "|")
        print(border, flush=True)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        names = {b.name: int(b) for b in protocol.Button}

        print("fake keyboard: type UP/DOWN/LEFT/RIGHT/CENTER (+ ' hold'), CW, CCW", flush=True)

        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return
            parts = line.strip().upper().split()
            if not parts:
                continue

            token = parts[0]
            if token in ("CW", "CCW"):
                await self.on_event(
                    protocol.EV_ENCODER, bytes([0, 1 if token == "CW" else 0])
                )
                continue

            if token not in names:
                print(f"unknown input: {token}", flush=True)
                continue

            action = protocol.ACT_HOLD if len(parts) > 1 and parts[1].startswith("HOLD") else protocol.ACT_TAP
            await self.on_event(protocol.EV_BUTTON, bytes([names[token], action]))


def make_link(cfg: Config, on_event: EventHandler, fake: bool = False) -> Link:
    return FakeLink(cfg, on_event) if fake else HidLink(cfg, on_event)
