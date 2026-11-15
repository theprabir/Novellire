"""Command-line entry point: `novellire` or `python -m novellire`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn

from .config import load_settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="novellire",
        description="Run the Novellire local web application.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Loopback only by default (default: 127.0.0.1).",
    )
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Uvicorn log level; defaults to the configured log level.",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    uvicorn.run(
        "novellire.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level=(args.log_level or settings.log_level.lower()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
