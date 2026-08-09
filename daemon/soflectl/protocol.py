"""Wire protocol between the daemon and the keyboard.

This mirrors agentctl/include/agentctl/protocol.h. tests/test_protocol.py parses
that header and asserts the two agree, so a change on one side fails the suite
until the other catches up.
"""

from __future__ import annotations

import struct
from enum import IntEnum

REPORT_SIZE = 32
PROTO_VERSION = 1

# Text frame geometry. The keyboard reports its own in the HELLO packet; these
# are the defaults used until it does.
ROWS = 16
COLS = 16

LABEL_LEN = 12


class Status(IntEnum):
    """Session status. Values are shared with enum agentctl_status."""

    IDLE = 0
    THINKING = 1
    TOOL = 2
    WAITING = 3
    DONE = 4
    ERROR = 5
    OFFLINE = 6


# host -> keyboard
SET_LINE = 0x01
SET_SYNC = 0x02
CLEAR = 0x03
PING = 0x04
SET_MODE = 0x05

# keyboard -> host
EV_BUTTON = 0x81
EV_ENCODER = 0x82
EV_HELLO = 0x83
EV_PONG = 0x84


class Button(IntEnum):
    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3
    CENTER = 4


ACT_TAP = 0
ACT_HOLD = 1

MODE_NORMAL = 0
MODE_PENDING = 1

_SYNC_STRUCT = struct.Struct(f"<BBBB{LABEL_LEN}s{LABEL_LEN}s")
assert _SYNC_STRUCT.size == 28, "sync struct must stay 28 bytes"


def _ascii(text: str, width: int) -> bytes:
    """Encode to fixed-width printable ASCII, padded with spaces.

    Anything the 1bpp font cannot draw becomes '?' rather than a missing glyph.
    """
    out = bytearray()
    for ch in text[:width]:
        out.append(ord(ch) if 0x20 <= ord(ch) < 0x7F else ord("?"))
    out.extend(b" " * (width - len(out)))
    return bytes(out)


def pack_set_line(row: int, text: str, cols: int = COLS) -> bytes:
    """Build a SET_LINE packet placing `text` on `row`."""
    payload = _ascii(text, min(len(text), cols)).rstrip(b"\x00")
    return bytes([SET_LINE, row, len(payload)]) + payload


def pack_set_sync(
    status: int,
    badge: int,
    session_idx: int,
    session_count: int,
    label0: str,
    label1: str,
) -> bytes:
    """Build a SET_SYNC packet carrying the compact session summary."""
    return bytes([SET_SYNC]) + _SYNC_STRUCT.pack(
        int(status) & 0xFF,
        badge & 0xFF,
        session_idx & 0xFF,
        session_count & 0xFF,
        _ascii(label0, LABEL_LEN),
        _ascii(label1, LABEL_LEN),
    )


def pack_clear() -> bytes:
    return bytes([CLEAR])


def pack_set_mode(mode: int) -> bytes:
    return bytes([SET_MODE, mode & 0xFF])


def pack_ping(epoch_ms: int) -> bytes:
    return bytes([PING]) + struct.pack("<I", epoch_ms & 0xFFFFFFFF)


def unpack_sync(payload: bytes) -> dict:
    """Decode a SET_SYNC payload (without the opcode byte)."""
    status, badge, idx, count, label0, label1 = _SYNC_STRUCT.unpack(
        payload[: _SYNC_STRUCT.size]
    )
    return {
        "status": status,
        "badge": badge,
        "session_idx": idx,
        "session_count": count,
        "label0": label0.decode("ascii", "replace").rstrip(),
        "label1": label1.decode("ascii", "replace").rstrip(),
    }
