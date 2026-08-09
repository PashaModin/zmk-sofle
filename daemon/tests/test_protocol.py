"""The C header and the Python module must not drift apart."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from soflectl import protocol

HEADER = Path(__file__).resolve().parents[2] / "agentctl" / "include" / "agentctl" / "protocol.h"


def _header_constants() -> dict[str, int]:
    """Pull the opcode and geometry constants out of the C header."""
    text = HEADER.read_text()
    found: dict[str, int] = {}

    # enum members written as `AC_SET_LINE = 0x01,`
    for name, value in re.findall(r"\b(AC_[A-Z_]+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", text):
        found[name] = int(value, 0)

    # bare #defines
    for name, value in re.findall(r"#define\s+(AGENTCTL_[A-Z_]+)\s+(\d+)\b", text):
        found[name] = int(value)

    # Implicit enum members continue from the previous one.
    for block in re.findall(r"enum\s*\w*\s*\{(.*?)\}", text, re.S):
        current = None
        for entry in block.split(","):
            entry = entry.split("/*")[0].strip()
            if not entry:
                continue
            if "=" in entry:
                name, _, value = entry.partition("=")
                name = name.strip()
                try:
                    current = int(value.strip(), 0)
                except ValueError:
                    continue
            else:
                name = entry
                current = 0 if current is None else current + 1
            if re.fullmatch(r"AC_[A-Z_0-9]+", name):
                found.setdefault(name, current)
                if found[name] != current:
                    found[name] = found[name]
    return found


def test_header_exists():
    assert HEADER.is_file(), f"expected the firmware header at {HEADER}"


@pytest.mark.parametrize(
    "c_name, py_value",
    [
        ("AC_SET_LINE", protocol.SET_LINE),
        ("AC_SET_SYNC", protocol.SET_SYNC),
        ("AC_CLEAR", protocol.CLEAR),
        ("AC_PING", protocol.PING),
        ("AC_SET_MODE", protocol.SET_MODE),
        ("AC_EV_BUTTON", protocol.EV_BUTTON),
        ("AC_EV_ENCODER", protocol.EV_ENCODER),
        ("AC_EV_HELLO", protocol.EV_HELLO),
        ("AC_EV_PONG", protocol.EV_PONG),
    ],
)
def test_opcodes_match_header(c_name, py_value):
    assert _header_constants()[c_name] == py_value


def test_status_enum_matches_header():
    consts = _header_constants()
    for status in protocol.Status:
        assert consts[f"AC_{status.name}"] == int(status)


def test_button_ids_match_header():
    consts = _header_constants()
    for button in protocol.Button:
        assert consts[f"AC_BTN_{button.name}"] == int(button)


def test_geometry_matches_header():
    consts = _header_constants()
    assert consts["AGENTCTL_ROWS"] == protocol.ROWS
    assert consts["AGENTCTL_COLS"] == protocol.COLS
    assert consts["AGENTCTL_LABEL_LEN"] == protocol.LABEL_LEN


def test_sync_payload_is_28_bytes_and_fits_a_report():
    packet = protocol.pack_set_sync(3, 1, 0, 2, "repo", "Read")
    assert len(packet) == 1 + 28
    assert len(packet) <= protocol.REPORT_SIZE


def test_sync_round_trips():
    packet = protocol.pack_set_sync(protocol.Status.WAITING, 2, 1, 4, "my-repo", "Bash")
    decoded = protocol.unpack_sync(packet[1:])
    assert decoded["status"] == int(protocol.Status.WAITING)
    assert decoded["badge"] == 2
    assert decoded["session_idx"] == 1
    assert decoded["session_count"] == 4
    assert decoded["label0"] == "my-repo"
    assert decoded["label1"] == "Bash"


def test_set_line_truncates_and_reports_its_own_length():
    packet = protocol.pack_set_line(0, "x" * 100, cols=16)
    assert packet[0] == protocol.SET_LINE
    assert packet[1] == 0
    assert packet[2] == 16
    assert len(packet) == 3 + 16
    assert len(packet) <= protocol.REPORT_SIZE


def test_set_line_replaces_unprintable_characters():
    # A missing glyph on a 1bpp font renders as a blank box; substitute instead.
    packet = protocol.pack_set_line(1, "café — ok", cols=16)
    body = packet[3:].decode("ascii")
    assert body == "caf? ? ok"


def test_labels_are_fixed_width():
    packet = protocol.pack_set_sync(0, 0, 0, 1, "ab", "")
    assert packet[5:17] == b"ab" + b" " * 10
    assert packet[17:29] == b" " * 12
