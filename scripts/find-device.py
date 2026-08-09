#!/usr/bin/env python3
"""List HID interfaces so you can confirm the keyboard is exposing raw HID.

    python3 scripts/find-device.py

The interface soflectl wants reports usage page 0xFF60 and usage 0x61. A
keyboard exposes several interfaces; opening the wrong one gives you silence
rather than an error, which is why this script exists.
"""

from __future__ import annotations

import sys

USAGE_PAGE = 0xFF60
USAGE = 0x61


def main() -> int:
    try:
        import hid
    except ImportError:
        print("hidapi is not installed. Try: pip install hidapi", file=sys.stderr)
        return 1

    matches = []
    print(f"{'vid':>6} {'pid':>6} {'usage page':>11} {'usage':>6}  product")
    print("-" * 70)

    for info in sorted(hid.enumerate(), key=lambda d: (d.get("vendor_id", 0), d.get("product_id", 0))):
        page = info.get("usage_page", 0)
        usage = info.get("usage", 0)
        product = (info.get("product_string") or "").strip()
        manufacturer = (info.get("manufacturer_string") or "").strip()
        mark = ""
        if page == USAGE_PAGE and usage == USAGE:
            matches.append(info)
            mark = "  <-- raw HID, this is the one"
        print(
            f"0x{info.get('vendor_id', 0):04x} 0x{info.get('product_id', 0):04x} "
            f"{f'0x{page:04x}':>11} {f'0x{usage:02x}':>6}  "
            f"{manufacturer} {product}{mark}"
        )

    print()
    if not matches:
        print("No raw HID interface found. Check that:")
        print("  - the LEFT half is plugged in over USB (the right half has no USB)")
        print("  - it is running firmware built with CONFIG_AGENTCTL=y")
        print("  - on Linux, you have permission to open hidraw devices (udev rule)")
        return 1

    for info in matches:
        print(f"Found: vid=0x{info['vendor_id']:04x} pid=0x{info['product_id']:04x}")
        print(f"  path: {info['path']!r}")
    print()
    print("soflectl matches on usage page and usage, so you do not normally need")
    print("to put the vid/pid into Config at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
