"""Database snapshots, validation, and restore safety."""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing

import pytest

from novellire.core.backup import BackupService
from novellire.errors import InvalidInputError


@pytest.fixture()
def backup_service(database) -> BackupService:
    return BackupService(database)


def test_snapshot_is_a_consistent_novellire_database(
    backup_service: BackupService, project_service
) -> None:
    project_service.create_project(name="Original")
    path, filename = backup_service.snapshot()

    assert path.is_file()
    assert filename.startswith("novellire-backup-")
    assert path.read_bytes().startswith(b"SQLite format 3\x00")
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT name FROM projects").fetchone()[0] == (
            "Original"
        )
    path.unlink()


def test_restore_replaces_data_and_keeps_a_safety_copy(
    backup_service: BackupService, project_service, database
) -> None:
    project_service.create_project(name="Original")
    snapshot, _ = backup_service.snapshot()
    payload = snapshot.read_bytes()
    snapshot.unlink()
    project_service.create_project(name="Later")

    outcome = backup_service.restore(payload)

    assert outcome.projects == 1
    assert outcome.chapters == 0
    names = [project.name for project in project_service.list_projects()]
    assert names == ["Original"]
    safety = backup_service.backup_dir / outcome.safety_backup
    assert safety.is_file()
    with closing(sqlite3.connect(safety)) as connection:
        assert connection.execute("SELECT name FROM projects").fetchone()[0] == (
            "Later"
        )
    safety.unlink()


def test_restore_rejects_non_sqlite_without_touching_data(
    backup_service: BackupService, project_service
) -> None:
    project_service.create_project(name="Original")

    with pytest.raises(InvalidInputError, match="not a Novellire"):
        backup_service.restore(b"this is not a database")

    names = [project.name for project in project_service.list_projects()]
    assert names == ["Original"]


def test_restore_rejects_an_empty_file(
    backup_service: BackupService, project_service
) -> None:
    project_service.create_project(name="Original")

    with pytest.raises(InvalidInputError, match="Choose a Novellire backup"):
        backup_service.restore(b"")


def test_restore_rejects_a_backup_from_a_newer_schema(
    backup_service: BackupService, project_service
) -> None:
    project_service.create_project(name="Original")
    snapshot, _ = backup_service.snapshot()
    with closing(sqlite3.connect(snapshot)) as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (999, "2030-01-01T00:00:00+00:00"),
        )
        connection.commit()
    payload = snapshot.read_bytes()
    snapshot.unlink()

    with pytest.raises(InvalidInputError, match="newer version"):
        backup_service.restore(payload)

    assert [project.name for project in project_service.list_projects()] == [
        "Original"
    ]


def test_restore_rejects_corrupt_sqlite_payload(
    backup_service: BackupService, project_service, tmp_path
) -> None:
    project_service.create_project(name="Original")
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"SQLite format 3\x00" + b"garbage" * 500)

    with pytest.raises(InvalidInputError):
        backup_service.restore(corrupt.read_bytes())

    assert [project.name for project in project_service.list_projects()] == [
        "Original"
    ]


def test_snapshot_survives_wal_content(
    backup_service: BackupService, project_service, database, tmp_path
) -> None:
    """A project committed through the app is present in the snapshot."""
    project_service.create_project(name="Committed")
    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM projects"
        ).fetchone()[0] == 1

    path, _ = backup_service.snapshot()
    copy = tmp_path / "copy.db"
    shutil.copy2(path, copy)
    with closing(sqlite3.connect(copy)) as connection:
        assert connection.execute(
            "SELECT name FROM projects"
        ).fetchone()[0] == "Committed"
    path.unlink()
