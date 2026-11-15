"""SQLite database lifecycle and connection handling.

Connections are opened per operation and closed immediately, which keeps
memory flat and avoids sharing a connection across the web server's worker
threads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..errors import DatabaseError
from .schema import LATEST_SCHEMA_VERSION, MIGRATIONS

CONNECT_TIMEOUT_SECONDS = 10.0
BUSY_TIMEOUT_MILLISECONDS = 5000


def utc_now_iso() -> str:
    """Return the current UTC time as a sortable ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _open_error(path: Path) -> DatabaseError:
    return DatabaseError(
        f"Could not open the Novellire database at {path}. "
        "Check that the data directory exists and is writable."
    )


class Database:
    """Owns the SQLite file, its PRAGMAs, and schema migrations."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=CONNECT_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # PRAGMA statements cannot use bound parameters; the value is a module
        # constant integer, so interpolation is safe here.
        connection.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_MILLISECONDS)}")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection for reads, translating SQLite errors."""
        try:
            connection = self._connect()
        except sqlite3.Error as exc:
            raise _open_error(self.path) from exc
        try:
            yield connection
        except sqlite3.Error as exc:
            raise DatabaseError(f"Database operation failed: {exc}") from exc
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside a transaction.

        ``sqlite3.IntegrityError`` is re-raised unchanged so repositories can map
        constraint violations (for example duplicate project names) to domain
        errors; every other SQLite failure becomes a ``DatabaseError``.
        """
        try:
            connection = self._connect()
        except sqlite3.Error as exc:
            raise _open_error(self.path) from exc
        try:
            yield connection
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise DatabaseError(f"Database operation failed: {exc}") from exc
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the database if needed and apply pending migrations."""
        with self.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
            applied = {
                int(row["version"])
                for row in connection.execute("SELECT version FROM schema_migrations")
            }

        for version, statements in MIGRATIONS:
            if version in applied:
                continue
            with self.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, utc_now_iso()),
                )

    def schema_version(self) -> int:
        """Return the highest applied migration version, or 0 for a fresh file."""
        with self.connection() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
        return int(row["version"]) if row and row["version"] is not None else 0

    def is_current(self) -> bool:
        return self.schema_version() >= LATEST_SCHEMA_VERSION
