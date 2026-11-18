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

MIGRATION_4_SEARCH_INDEX = """
CREATE VIRTUAL TABLE search_index USING fts5(
    title,
    body,
    project_id UNINDEXED,
    source_kind UNINDEXED,
    source_id UNINDEXED,
    tokenize = 'unicode61'
)
"""

MIGRATION_4_BACKFILL_CHAPTERS = """
INSERT INTO search_index (title, body, project_id, source_kind, source_id)
SELECT title, COALESCE(summary, '') || char(10) || content,
       project_id, 'chapter', id
FROM chapters
"""

MIGRATION_4_BACKFILL_DOCUMENTS = """
INSERT INTO search_index (title, body, project_id, source_kind, source_id)
SELECT kind, content, project_id, kind, id
FROM project_documents
"""

MIGRATION_4_CHAPTER_TRIGGERS = (
    """
    CREATE TRIGGER search_chapters_insert AFTER INSERT ON chapters BEGIN
        INSERT INTO search_index (title, body, project_id, source_kind, source_id)
        VALUES (new.title, COALESCE(new.summary, '') || char(10) || new.content,
                new.project_id, 'chapter', new.id);
    END
    """,
    """
    CREATE TRIGGER search_chapters_update
    AFTER UPDATE OF title, content, summary ON chapters BEGIN
        DELETE FROM search_index
        WHERE source_kind = 'chapter' AND source_id = old.id;
        INSERT INTO search_index (title, body, project_id, source_kind, source_id)
        VALUES (new.title, COALESCE(new.summary, '') || char(10) || new.content,
                new.project_id, 'chapter', new.id);
    END
    """,
    """
    CREATE TRIGGER search_chapters_delete AFTER DELETE ON chapters BEGIN
        DELETE FROM search_index
        WHERE source_kind = 'chapter' AND source_id = old.id;
    END
    """,
)

MIGRATION_4_DOCUMENT_TRIGGERS = (
    """
    CREATE TRIGGER search_documents_insert AFTER INSERT ON project_documents BEGIN
        INSERT INTO search_index (title, body, project_id, source_kind, source_id)
        VALUES (new.kind, new.content, new.project_id, new.kind, new.id);
    END
    """,
    """
    CREATE TRIGGER search_documents_update
    AFTER UPDATE OF content ON project_documents BEGIN
        DELETE FROM search_index
        WHERE source_kind = old.kind AND source_id = old.id;
        INSERT INTO search_index (title, body, project_id, source_kind, source_id)
        VALUES (new.kind, new.content, new.project_id, new.kind, new.id);
    END
    """,
    """
    CREATE TRIGGER search_documents_delete AFTER DELETE ON project_documents BEGIN
        DELETE FROM search_index
        WHERE source_kind = old.kind AND source_id = old.id;
    END
    """,
)


MIGRATION_5_EVENTS = """
CREATE TABLE narrative_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    characters TEXT NOT NULL DEFAULT '[]',
    locations TEXT NOT NULL DEFAULT '[]',
    objects TEXT NOT NULL DEFAULT '[]',
    threads TEXT NOT NULL DEFAULT '[]',
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
)
"""

MIGRATION_5_EVENTS_INDEX = """
CREATE INDEX idx_narrative_events_project_chapter
    ON narrative_events (project_id, chapter_id, id)
"""


MIGRATION_6_EVENT_LINKS = """
ALTER TABLE narrative_events
    ADD COLUMN links_resolved INTEGER NOT NULL DEFAULT 0
    CHECK (links_resolved IN (0, 1))
"""

MIGRATION_6_EVENT_CHARACTERS = """
CREATE TABLE event_characters (
    event_id INTEGER NOT NULL REFERENCES narrative_events(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    mention TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (event_id, character_id)
)
"""

MIGRATION_6_EVENT_CHARACTERS_INDEX = """
CREATE INDEX idx_event_characters_character
    ON event_characters (character_id, event_id)
"""


MIGRATION_7_RELATIONSHIPS = """
CREATE TABLE character_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    character_a_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    character_b_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'rejected')),
    source_event_id INTEGER REFERENCES narrative_events(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (character_a_id < character_b_id)
)
"""

MIGRATION_7_RELATIONSHIPS_INDEX = """
CREATE INDEX idx_character_relationships_project
    ON character_relationships (project_id, status, id)
"""

MIGRATION_7_RELATIONSHIPS_PAIR_INDEX = """
CREATE INDEX idx_character_relationships_pair
    ON character_relationships (character_a_id, character_b_id)
"""


MIGRATION_8_CHARACTER_STATES = """
CREATE TABLE character_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    location TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    goals TEXT NOT NULL DEFAULT '',
    knowledge TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (character_id, chapter_id)
)
"""

MIGRATION_8_CHARACTER_STATES_INDEX = """
CREATE INDEX idx_character_states_project
    ON character_states (project_id, character_id, chapter_id)
"""


MIGRATION_9_CHAPTER_REVISIONS = """
CREATE TABLE chapter_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    word_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'edit',
    created_at TEXT NOT NULL
)
"""

MIGRATION_9_CHAPTER_REVISIONS_INDEX = """
CREATE INDEX idx_chapter_revisions_chapter
    ON chapter_revisions (chapter_id, id)
"""


MIGRATION_10_ANALYSIS_STATE = """
CREATE TABLE analysis_state (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('chapter', 'document')),
    source_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    detail TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, source_kind, source_key)
)
"""

MIGRATION_10_ANALYSIS_STATE_INDEX = """
CREATE INDEX idx_analysis_state_project
    ON analysis_state (project_id, status)
"""

MIGRATION_10_CHAPTER_INSIGHTS = """
CREATE TABLE chapter_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL UNIQUE REFERENCES chapters(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    character_states TEXT NOT NULL DEFAULT '[]',
    locations TEXT NOT NULL DEFAULT '[]',
    relationships TEXT NOT NULL DEFAULT '[]',
    open_threads TEXT NOT NULL DEFAULT '[]',
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

MIGRATION_10_CHAPTER_INSIGHTS_INDEX = """
CREATE INDEX idx_chapter_insights_project
    ON chapter_insights (project_id, chapter_id)
"""

MIGRATION_11_CHAT_THREADS = """
CREATE TABLE chat_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK (mode IN ('plan', 'write')),
    title TEXT NOT NULL DEFAULT 'New conversation',
    planning_notes TEXT NOT NULL DEFAULT '',
    planning_notes_source TEXT NOT NULL DEFAULT ''
        CHECK (planning_notes_source IN ('', 'model', 'author')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

MIGRATION_11_CHAT_THREADS_INDEX = """
CREATE INDEX idx_chat_threads_project
    ON chat_threads (project_id, updated_at)
"""

MIGRATION_11_CHAT_MESSAGES = """
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
)
"""

MIGRATION_11_CHAT_MESSAGES_INDEX = """
CREATE INDEX idx_chat_messages_thread
    ON chat_messages (thread_id, id)
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
        (
            4,
            (
                MIGRATION_4_SEARCH_INDEX,
                MIGRATION_4_BACKFILL_CHAPTERS,
                MIGRATION_4_BACKFILL_DOCUMENTS,
                *MIGRATION_4_CHAPTER_TRIGGERS,
                *MIGRATION_4_DOCUMENT_TRIGGERS,
            ),
        ),
        (
            5,
            (
                MIGRATION_5_EVENTS,
                MIGRATION_5_EVENTS_INDEX,
            ),
        ),
        (
            6,
            (
                MIGRATION_6_EVENT_LINKS,
                MIGRATION_6_EVENT_CHARACTERS,
                MIGRATION_6_EVENT_CHARACTERS_INDEX,
            ),
        ),
        (
            7,
            (
                MIGRATION_7_RELATIONSHIPS,
                MIGRATION_7_RELATIONSHIPS_INDEX,
                MIGRATION_7_RELATIONSHIPS_PAIR_INDEX,
            ),
        ),
        (
            8,
            (
                MIGRATION_8_CHARACTER_STATES,
                MIGRATION_8_CHARACTER_STATES_INDEX,
            ),
        ),
        (
            9,
            (
                MIGRATION_9_CHAPTER_REVISIONS,
                MIGRATION_9_CHAPTER_REVISIONS_INDEX,
            ),
        ),
        (
            10,
            (
                MIGRATION_10_ANALYSIS_STATE,
                MIGRATION_10_ANALYSIS_STATE_INDEX,
                MIGRATION_10_CHAPTER_INSIGHTS,
                MIGRATION_10_CHAPTER_INSIGHTS_INDEX,
            ),
        ),
        (
            11,
            (
                MIGRATION_11_CHAT_THREADS,
                MIGRATION_11_CHAT_THREADS_INDEX,
                MIGRATION_11_CHAT_MESSAGES,
                MIGRATION_11_CHAT_MESSAGES_INDEX,
            ),
        ),
    )

LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]
