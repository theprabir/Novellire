"""Database lifecycle, PRAGMA, and migration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novellire.errors import DatabaseError
from novellire.storage.database import Database
from novellire.storage.repositories import ProjectRepository
from novellire.storage.schema import LATEST_SCHEMA_VERSION, MIGRATIONS


def test_initialize_applies_migrations(database: Database) -> None:
    assert database.schema_version() == LATEST_SCHEMA_VERSION
    assert database.is_current() is True


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "twice.db")
    db.initialize()
    db.initialize()

    with db.connection() as connection:
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [row["version"] for row in rows] == [
        version for version, _ in MIGRATIONS
    ]


def test_expected_tables_exist(database: Database) -> None:
    with database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "projects",
        "app_settings",
        "generations",
        "story_bible_entries",
        "characters",
        "character_aliases",
        "chapters",
        "scenes",
        "schema_migrations",
    } <= names


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


def test_migration_2_upgrades_an_existing_v1_database(tmp_path: Path) -> None:
    """A Phase 1 database keeps its data and gains the Phase 2 tables."""
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for statement in MIGRATIONS[0][1]:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)",
        ("2026-01-01T00:00:00+00:00",),
    )
    connection.execute(
        "INSERT INTO projects (name, created_at, updated_at) VALUES (?, ?, ?)",
        ("Legacy", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    assert database.schema_version() == LATEST_SCHEMA_VERSION == 2
    assert [project.name for project in ProjectRepository(database).list()] == [
        "Legacy"
    ]
    with database.connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"chapters", "scenes", "characters", "story_bible_entries"} <= tables
