"""Versioned database schema.

Migrations are ordered and applied exactly once, inside a transaction. Each
migration is a tuple of individual statements so no implicit commits occur.
Later phases append new versions; existing versions are never edited.
"""

from __future__ import annotations

MIGRATION_1_PROJECTS = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    narrative_style TEXT NOT NULL DEFAULT '',
    target_word_count INTEGER,
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

MIGRATION_1_APP_SETTINGS = """
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

MIGRATION_1_GENERATIONS = """
CREATE TABLE generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    temperature REAL NOT NULL,
    top_p REAL NOT NULL,
    num_predict INTEGER NOT NULL,
    context_window INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    error TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER,
    output_tokens INTEGER,
    truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
    created_at TEXT NOT NULL
)
"""

MIGRATION_1_GENERATIONS_INDEX = """
CREATE INDEX idx_generations_project_created
    ON generations (project_id, created_at DESC)
"""

MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            MIGRATION_1_PROJECTS,
            MIGRATION_1_APP_SETTINGS,
            MIGRATION_1_GENERATIONS,
            MIGRATION_1_GENERATIONS_INDEX,
        ),
    ),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]
