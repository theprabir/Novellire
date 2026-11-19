"""Database lifecycle, PRAGMA, and migration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novellire.errors import DatabaseError
from novellire.storage.database import Database
from novellire.storage.repositories import ProjectRepository
from novellire.storage.schema import LATEST_SCHEMA_VERSION, MIGRATIONS
from novellire.storage.search_repository import SearchRepository
from novellire.storage.story_repositories import ChapterRepository


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


def test_migration_3_backfills_chapter_content(tmp_path: Path) -> None:
    """A Phase 2 database keeps its scene prose as chapter text."""
    path = tmp_path / "legacy-v2.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for version, statements in MIGRATIONS[:2]:
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, "2026-01-01T00:00:00+00:00"),
        )
    stamp = "2026-01-01T00:00:00+00:00"
    connection.execute(
        "INSERT INTO projects (name, created_at, updated_at) VALUES (?, ?, ?)",
        ("Legacy", stamp, stamp),
    )
    connection.execute(
        "INSERT INTO chapters (project_id, position, title, created_at, updated_at) "
        "VALUES (1, 1, 'One', ?, ?)",
        (stamp, stamp),
    )
    for position, text, words in ((1, "First line.", 2), (2, "Second line.", 2)):
        connection.execute(
            "INSERT INTO scenes (chapter_id, position, content, word_count, "
            "created_at, updated_at) VALUES (1, ?, ?, ?, ?, ?)",
            (position, text, words, stamp, stamp),
        )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    chapter = ChapterRepository(database).list_for_project(1)[0]
    assert chapter.content == "First line.\n\nSecond line."
    assert chapter.word_count == 4
    assert chapter.origin == "written"
    assert database.schema_version() == LATEST_SCHEMA_VERSION == 12


def test_migration_4_indexes_existing_chapters_and_documents(tmp_path: Path) -> None:
    """A Phase 3 database gains a populated full-text index."""
    path = tmp_path / "legacy-v3.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for version, statements in MIGRATIONS[:3]:
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, "2026-01-01T00:00:00+00:00"),
        )
    stamp = "2026-01-01T00:00:00+00:00"
    connection.execute(
        "INSERT INTO projects (name, created_at, updated_at) VALUES (?, ?, ?)",
        ("Legacy", stamp, stamp),
    )
    connection.execute(
        "INSERT INTO chapters (project_id, position, title, content, word_count, "
        "created_at, updated_at) VALUES (1, 1, 'The Gate', 'Ash on the square.', 4, ?, ?)",
        (stamp, stamp),
    )
    connection.execute(
        "INSERT INTO project_documents (project_id, kind, content, derived, "
        "created_at, updated_at) VALUES (1, 'master_bible', 'The star is dimming.', 0, ?, ?)",
        (stamp, stamp),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    assert database.schema_version() == LATEST_SCHEMA_VERSION == 12
    hits = SearchRepository(database).search(1, "ash")
    assert [hit.source_kind for hit in hits] == ["chapter"]
    assert "Ash" in hits[0].excerpt

    with database.connection() as connection:
        kinds = {
            row["source_kind"]
            for row in connection.execute("SELECT source_kind FROM search_index")
        }
    assert kinds == {"chapter", "master_bible"}


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

    assert database.schema_version() == LATEST_SCHEMA_VERSION == 12
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
