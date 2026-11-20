"""Installation preflight: prove an install can start, without changing anything.

``novellire doctor`` runs this before the server exists. Every check is
read-only: the data directory is never created, the database is opened through a
read-only SQLite URI and never migrated, and no provider or model is contacted.
The report is ordinary data, so the CLI, the tests, and a future health panel can
share one implementation.

Cloud keys are never read into the report. A check may name the environment
variable that should hold a key, but not its value.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..config import Settings, resolve_config_path
from ..storage.schema import LATEST_SCHEMA_VERSION

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    """One preflight check: what was found, and what to do about it."""

    name: str
    status: str
    detail: str
    hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class PreflightReport:
    """The outcome of every check, in the order they are shown."""

    version: str
    checks: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        """True when nothing failed. Warnings describe a usable install."""
        return all(check.status != FAIL for check in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if check.status == FAIL)

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if check.status == WARN)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
        }


def _check_python() -> CheckResult:
    current = sys.version_info
    version = f"{current.major}.{current.minor}.{current.micro}"
    if current >= (3, 11):
        return CheckResult("python", OK, f"Python {version}")
    return CheckResult(
        "python",
        FAIL,
        f"Python {version} is too old",
        "Novellire needs Python 3.11 or newer; recreate the virtual environment "
        "with a newer interpreter.",
    )


def _check_configuration(config_path: Path | None) -> CheckResult:
    path = resolve_config_path(config_path)
    if not path.is_file():
        return CheckResult(
            "configuration",
            OK,
            f"built-in defaults; no file at {path}",
        )
    return CheckResult("configuration", OK, f"loaded from {path}")


def _check_data_directory(settings: Settings) -> CheckResult:
    directory = settings.data_dir
    if directory.exists() and not directory.is_dir():
        return CheckResult(
            "data directory",
            FAIL,
            f"{directory} exists but is not a directory",
            "Move that file aside or set data_dir to a directory Novellire may use.",
        )
    if not directory.is_dir():
        return CheckResult(
            "data directory",
            OK,
            f"{directory} does not exist yet; created on first start",
        )

    probe = directory / f".doctor-write-test-{os.getpid()}"
    try:
        probe.write_bytes(b"")
    except OSError as exc:
        return CheckResult(
            "data directory",
            FAIL,
            f"{directory} is not writable ({exc.strerror or exc})",
            "Grant this user write access to the data directory, or point data_dir "
            "somewhere writable.",
        )
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    return CheckResult("data directory", OK, f"{directory} is writable")


def _check_database(settings: Settings) -> CheckResult:
    path = settings.database_path
    if not path.exists():
        return CheckResult(
            "database",
            OK,
            f"no database at {path}; created on first start "
            f"(schema {LATEST_SCHEMA_VERSION})",
        )

    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
            version = int(row["version"]) if row and row["version"] is not None else 0
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM projects) AS projects, "
                "(SELECT COUNT(*) FROM chapters) AS chapters"
            ).fetchone()
            projects = int(counts["projects"])
            chapters = int(counts["chapters"])
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return CheckResult(
            "database",
            FAIL,
            f"{path} could not be read as a Novellire database ({exc})",
            "Restore a backup of this file, or move it aside to start a new "
            "library. Novellire never overwrites an unreadable database.",
        )

    records = (
        f"{projects} project{'' if projects == 1 else 's'}, "
        f"{chapters} chapter{'' if chapters == 1 else 's'}"
    )
    if version > LATEST_SCHEMA_VERSION:
        return CheckResult(
            "database",
            WARN,
            f"schema {version} is newer than this install's {LATEST_SCHEMA_VERSION} "
            f"({records})",
            "This database was written by a newer Novellire. Update the application "
            "rather than opening it with this version.",
        )
    if version < LATEST_SCHEMA_VERSION:
        return CheckResult(
            "database",
            WARN,
            f"schema {version}, upgrade to {LATEST_SCHEMA_VERSION} on next start "
            f"({records})",
            "Starting Novellire applies the upgrade in place. Back up first if the "
            "library matters.",
        )
    return CheckResult(
        "database",
        OK,
        f"schema {version} is current ({records})",
    )


def _check_provider(settings: Settings) -> CheckResult:
    if not settings.cloud.enabled:
        return CheckResult(
            "provider",
            OK,
            f"Ollama (local) at {settings.ollama.base_url}; no API key needed",
        )

    key_env = settings.cloud.api_key_env
    if not settings.cloud.api_key():
        return CheckResult(
            "provider",
            FAIL,
            f"Cloud API is enabled at {settings.cloud.base_url}, "
            f"but {key_env} is empty",
            f"Set {key_env} in the environment that starts Novellire, or set "
            "cloud.enabled = false to stay local.",
        )
    model = settings.cloud.model or "provider default model"
    return CheckResult(
        "provider",
        OK,
        f"Cloud API at {settings.cloud.base_url}; key read from {key_env}; "
        f"{model}",
    )


def run_preflight(
    settings: Settings, config_path: Path | None = None
) -> PreflightReport:
    """Run every check and return the report. No network, no writes."""
    checks: Iterable[CheckResult] = (
        _check_python(),
        _check_configuration(config_path),
        _check_data_directory(settings),
        _check_database(settings),
        _check_provider(settings),
    )
    return PreflightReport(version=__version__, checks=tuple(checks))


def format_report(report: PreflightReport) -> str:
    """Render the report for a terminal: one line per check, hints indented."""
    width = max(len(check.name) for check in report.checks) + 2
    lines = [f"Novellire {report.version} preflight", ""]
    for check in report.checks:
        lines.append(f"  {check.status:<5} {check.name:<{width}}{check.detail}")
        if check.hint:
            lines.append(f"        {'':<{width}}hint: {check.hint}")

    failures = len(report.failures)
    warnings = len(report.warnings)
    lines.append("")
    if failures:
        lines.append(
            f"{failures} check{'' if failures == 1 else 's'} failed. "
            "Fix it and run `novellire doctor` again."
        )
    elif warnings:
        lines.append(
            f"Ready, with {warnings} warning{'' if warnings == 1 else 's'}. "
            "Start Novellire when the warning is acceptable."
        )
    else:
        lines.append("Ready. Start Novellire with `novellire`.")
    return "\n".join(lines)
