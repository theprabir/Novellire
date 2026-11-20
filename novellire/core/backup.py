"""Consistent database snapshots, verified restores, and file checks.

Downloads are produced with SQLite's backup API rather than copying a file that
may have a live WAL. A snapshot is verified before it is handed out, an uploaded
backup can be checked without touching the live database, and a restore
validates the upload's header, integrity, Novellire tables, and schema version
before replacing anything. A pre-restore copy is kept, and the restored database
is verified after migration, so a bad restore is recoverable.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..errors import InvalidInputError
from ..logging_setup import get_logger
from ..storage.database import Database
from ..storage.schema import LATEST_SCHEMA_VERSION

logger = get_logger("core.backup")

SQLITE_HEADER = b"SQLite format 3\x00"
MAX_BACKUP_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class BackupReport:
    schema_version: int
    latest_schema_version: int
    upgrade_required: bool
    projects: int
    chapters: int
    characters: int
    size_bytes: int


@dataclass(frozen=True)
class RestoreOutcome:
    projects: int
    chapters: int
    safety_backup: str


class BackupService:
    def __init__(self, database: Database) -> None:
        self._database = database

    @property
    def backup_dir(self) -> Path:
        return self._database.path.parent / "backups"

    def snapshot(self) -> tuple[Path, str]:
        """Create a verified, downloadable snapshot and return its path and name."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"novellire-backup-{stamp}.db"
        target = self.backup_dir / filename
        self._copy_database(self._database.path, target)
        try:
            report = _inspect_database(target, target.stat().st_size)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        logger.info(
            "Verified snapshot: schema=%s projects=%s chapters=%s",
            report.schema_version,
            report.projects,
            report.chapters,
        )
        return target, filename

    def verify(self, payload: bytes) -> BackupReport:
        """Check an uploaded backup without restoring or writing to the data."""
        _check_payload(payload)
        handle, staging_name = tempfile.mkstemp(
            dir=self._database.path.parent, suffix=".verify.db"
        )
        os.close(handle)
        staging = Path(staging_name)
        try:
            staging.write_bytes(payload)
            return _inspect_database(staging, len(payload))
        finally:
            staging.unlink(missing_ok=True)

    def restore(self, payload: bytes) -> RestoreOutcome:
        _check_payload(payload)

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        handle, staging_name = tempfile.mkstemp(
            dir=self._database.path.parent, suffix=".restore.db"
        )
        os.close(handle)
        staging = Path(staging_name)
        try:
            staging.write_bytes(payload)
            _inspect_database(staging, len(payload))
            safety = self._write_safety_copy()

            self._checkpoint()
            try:
                os.replace(staging, self._database.path)
            except OSError as error:
                raise InvalidInputError(
                    "Could not replace the database. Close any other Novellire "
                    f"process and try again. Your data is unchanged; a safety "
                    f"copy is at {safety}."
                ) from error

            self._clear_sidecars()
            try:
                self._database.initialize()
            except Exception as error:  # noqa: BLE001 - restore must not lose data
                logger.exception("Restore failed after replacing the database")
                self._restore_safety_copy(safety)
                raise InvalidInputError(
                    "That backup could not be migrated to the current schema. "
                    "Your previous database has been restored."
                ) from error
            try:
                _inspect_database(
                    self._database.path, self._database.path.stat().st_size
                )
            except InvalidInputError as error:
                logger.exception("Restored database failed verification")
                self._restore_safety_copy(safety)
                raise InvalidInputError(
                    "That backup failed verification after restore. Your "
                    "previous database has been restored."
                ) from error

            projects, chapters = self._counts()
            logger.info(
                "Restored backup: projects=%s chapters=%s safety=%s",
                projects,
                chapters,
                safety.name,
            )
            return RestoreOutcome(
                projects=projects,
                chapters=chapters,
                safety_backup=safety.name,
            )
        finally:
            staging.unlink(missing_ok=True)

    def _write_safety_copy(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        target = self.backup_dir / f"pre-restore-{stamp}.db"
        self._copy_database(self._database.path, target)
        return target

    def _restore_safety_copy(self, safety: Path) -> None:
        self._copy_database(safety, self._database.path)
        self._clear_sidecars()
        self._database.initialize()

    def _checkpoint(self) -> None:
        with closing(sqlite3.connect(self._database.path)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _clear_sidecars(self) -> None:
        for suffix in ("-wal", "-shm"):
            Path(f"{self._database.path}{suffix}").unlink(missing_ok=True)

    def _counts(self) -> tuple[int, int]:
        with self._database.connection() as connection:
            projects = int(
                connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            )
            chapters = int(
                connection.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
            )
        return projects, chapters

    @staticmethod
    def _copy_database(source_path: Path, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(source_path)
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()


def _check_payload(payload: bytes) -> None:
    if not payload:
        raise InvalidInputError("Choose a Novellire backup file to restore.")
    if len(payload) > MAX_BACKUP_BYTES:
        raise InvalidInputError(
            "That backup is larger than 512 MB and cannot be restored here."
        )
    if not payload.startswith(SQLITE_HEADER):
        raise InvalidInputError("That file is not a Novellire SQLite backup.")


def _inspect_database(path: Path, size_bytes: int) -> BackupReport:
    """Validate a Novellire database file and summarise what it holds."""
    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as error:
        raise InvalidInputError("That backup could not be opened.") from error
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        if row is None or str(row[0]) != "ok":
            raise InvalidInputError(
                "That backup failed SQLite's integrity check and was not restored."
            )
        tables = {
            str(item[0])
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not {"schema_migrations", "projects"} <= tables:
            raise InvalidInputError(
                "That file is a SQLite database, but not a Novellire backup."
            )
        versions = [
            int(item[0])
            for item in connection.execute("SELECT version FROM schema_migrations")
        ]
        if not versions:
            raise InvalidInputError("That backup has no schema history.")
        newest = max(versions)
        if newest > LATEST_SCHEMA_VERSION:
            raise InvalidInputError(
                "That backup was created by a newer version of Novellire. "
                "Upgrade this installation before restoring it."
            )
        return BackupReport(
            schema_version=newest,
            latest_schema_version=LATEST_SCHEMA_VERSION,
            upgrade_required=newest < LATEST_SCHEMA_VERSION,
            projects=_count_rows(connection, tables, "projects"),
            chapters=_count_rows(connection, tables, "chapters"),
            characters=_count_rows(connection, tables, "characters"),
            size_bytes=size_bytes,
        )
    except sqlite3.DatabaseError as error:
        raise InvalidInputError(
            "That backup is not a readable SQLite database."
        ) from error
    finally:
        connection.close()


def _count_rows(connection: sqlite3.Connection, tables: set[str], table: str) -> int:
    if table not in tables:
        return 0
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
