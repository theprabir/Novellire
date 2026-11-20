"""Command-line entry point: `novellire` or `python -m novellire`.

`novellire doctor` runs the installation preflight and exits with ``1`` when a
check fails, so a new install can prove itself before the server starts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from .config import load_settings
from .core.preflight import format_report, run_preflight
from .errors import NovellireError


def run_doctor(argv: Sequence[str]) -> int:
    """Check the installation without starting the server or changing anything."""
    parser = argparse.ArgumentParser(
        prog="novellire doctor",
        description="Check that this installation can start. Changes nothing.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the report as JSON."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Check this configuration file instead of the default.",
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config) if args.config else None
    try:
        settings = load_settings(config_path)
    except NovellireError as exc:
        print(f"Novellire could not read its configuration: {exc}", file=sys.stderr)
        return 1

    report = run_preflight(settings, config_path)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if arguments and arguments[0] == "doctor":
        return run_doctor(arguments[1:])

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
    args = parser.parse_args(arguments)

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
