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

MIGRATION_2_STORY_BIBLE = """
CREATE TABLE story_bible_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    title TEXT NOT NULL COLLATE NOCASE,
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, category, title)
)
"""

MIGRATION_2_STORY_BIBLE_INDEX = """
CREATE INDEX idx_story_bible_project
    ON story_bible_entries (project_id, category)
"""

MIGRATION_2_CHARACTERS = """
CREATE TABLE characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    physical_description TEXT NOT NULL DEFAULT '',
    age TEXT NOT NULL DEFAULT '',
    personality TEXT NOT NULL DEFAULT '',
    motivations TEXT NOT NULL DEFAULT '',
    goals TEXT NOT NULL DEFAULT '',
    fears TEXT NOT NULL DEFAULT '',
    strengths TEXT NOT NULL DEFAULT '',
    weaknesses TEXT NOT NULL DEFAULT '',
    background TEXT NOT NULL DEFAULT '',
    secrets TEXT NOT NULL DEFAULT '',
    character_arc TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, name)
)
"""

MIGRATION_2_CHARACTERS_INDEX = """
CREATE INDEX idx_characters_project ON characters (project_id, name)
"""

MIGRATION_2_CHARACTER_ALIASES = """
CREATE TABLE character_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    alias TEXT NOT NULL COLLATE NOCASE,
    UNIQUE (character_id, alias)
)
"""

MIGRATION_2_CHAPTERS = """
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    part TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    objectives TEXT NOT NULL DEFAULT '',
    viewpoint_character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    target_word_count INTEGER,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'drafting', 'drafted', 'approved')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, position)
)
"""

MIGRATION_2_CHAPTERS_INDEX = """
CREATE INDEX idx_chapters_project ON chapters (project_id, position)
"""

MIGRATION_2_SCENES = """
CREATE TABLE scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    objectives TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'drafting', 'drafted', 'approved')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (chapter_id, position)
)
"""

MIGRATION_2_SCENES_INDEX = """
CREATE INDEX idx_scenes_chapter ON scenes (chapter_id, position)
"""

MIGRATION_3_DOCUMENTS = """
CREATE TABLE project_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL
        CHECK (kind IN ('master_bible', 'character_bible', 'chapter_map', 'style_guide')),
    content TEXT NOT NULL DEFAULT '',
    derived INTEGER NOT NULL DEFAULT 0 CHECK (derived IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, kind)
)
"""

MIGRATION_3_CHAPTER_CONTENT = """
ALTER TABLE chapters ADD COLUMN content TEXT NOT NULL DEFAULT ''
"""

MIGRATION_3_CHAPTER_WORDS = """
ALTER TABLE chapters ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0
"""

MIGRATION_3_CHAPTER_ORIGIN = """
ALTER TABLE chapters ADD COLUMN origin TEXT NOT NULL DEFAULT 'written'
    CHECK (origin IN ('written', 'imported'))
"""

MIGRATION_3_BACKFILL_CONTENT = """
UPDATE chapters SET content = COALESCE((
    SELECT group_concat(content, char(10) || char(10))
    FROM (SELECT content FROM scenes WHERE scenes.chapter_id = chapters.id ORDER BY position)
), '')
"""

MIGRATION_3_BACKFILL_WORDS = """
UPDATE chapters SET word_count = COALESCE((
    SELECT SUM(word_count) FROM scenes WHERE scenes.chapter_id = chapters.id
), 0)
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
    (
        2,
        (
            MIGRATION_2_STORY_BIBLE,
            MIGRATION_2_STORY_BIBLE_INDEX,
            MIGRATION_2_CHARACTERS,
            MIGRATION_2_CHARACTERS_INDEX,
            MIGRATION_2_CHARACTER_ALIASES,
            MIGRATION_2_CHAPTERS,
            MIGRATION_2_CHAPTERS_INDEX,
            MIGRATION_2_SCENES,
            MIGRATION_2_SCENES_INDEX,
        ),
    ),
    (
        3,
        (
            MIGRATION_3_DOCUMENTS,
            MIGRATION_3_CHAPTER_CONTENT,
            MIGRATION_3_CHAPTER_WORDS,
            MIGRATION_3_CHAPTER_ORIGIN,
            MIGRATION_3_BACKFILL_CONTENT,
            MIGRATION_3_BACKFILL_WORDS,
        ),
    ),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]
