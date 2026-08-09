"""Entry point: soflectl [--fake-hid] [--port N] [-v]."""

from __future__ import annotations

import argparse
import logging

from aiohttp import web

from .config import Config
from .hid_link import FakeLink, HidLink
from .server import make_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="soflectl",
        description="Drive a Sofle's displays and 5-way switch from Claude Code hooks.",
    )
    parser.add_argument(
        "--fake-hid",
        action="store_true",
        help="render frames to the terminal and read button names from stdin, "
        "instead of talking to a keyboard",
    )
    parser.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="bind port (default 8787)")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    cfg = Config()
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port

    link_cls = FakeLink if args.fake_hid else HidLink
    app = make_app(cfg, lambda on_event: link_cls(cfg, on_event))

    logging.getLogger(__name__).info(
        "listening on http://%s:%d/hook", cfg.host, cfg.port
    )
    web.run_app(app, host=cfg.host, port=cfg.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
