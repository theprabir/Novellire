"""Database lifecycle, PRAGMA, and migration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from novellire.errors import DatabaseError
from novellire.storage.database import Database
from novellire.storage.schema import LATEST_SCHEMA_VERSION


def test_initialize_applies_migrations(database: Database) -> None:
    assert database.schema_version() == LATEST_SCHEMA_VERSION
    assert database.is_current() is True


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "twice.db")
    db.initialize()
    db.initialize()

    with db.connection() as connection:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert [row["version"] for row in rows] == [1]


def test_expected_tables_exist(database: Database) -> None:
    with database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"projects", "app_settings", "generations", "schema_migrations"} <= names


def test_connections_enforce_foreign_keys_and_wal(database: Database) -> None:
    with database.connection() as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert foreign_keys == 1
    assert journal_mode.lower() == "wal"


def test_foreign_key_violation_is_reported(
    database: Database, generation_repository
) -> None:
    with pytest.raises(DatabaseError):
        generation_repository.create(
            project_id=9999,
            model="fake-model",
            prompt="prompt",
            temperature=0.7,
            top_p=0.9,
            num_predict=128,
            context_window=1024,
            status="completed",
        )


def test_data_directory_is_created(tmp_path: Path) -> None:
    db = Database(tmp_path / "nested" / "data" / "novellire.db")
    db.initialize()
    assert db.path.is_file()
