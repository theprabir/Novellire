# Changelog

All notable changes to Novellire are documented here.
The project follows semantic versioning for the application, not the schema.

## [0.1.1] — 2026-11-15

Phase 2 data model, released on the Phase 1 line. The complete Phase 2 milestone
(`v0.2`) still requires document import, event extraction, and chapter summaries.
Schema version is now 2; existing Phase 1 databases upgrade in place.

### Added

- Schema migration 2 adds `story_bible_entries`, `characters`,
  `character_aliases`, `chapters`, and `scenes`. Existing Phase 1 databases are
  upgraded in place; no data is rewritten or dropped.
- Story bible service with the categories from the specification
  (premise, storyline, subplots, themes, structure, world-building, history,
  geography, technology, metaphysical rules, cultures, objects, organizations,
  locations, terminology), duplicate protection per project and category, and
  project scoping.
- Character profiles with identity fields (physical description, age,
  personality, motivations, goals, fears, strengths, weaknesses, background,
  secrets, arc) plus case-insensitive names and normalised aliases. Evolving
  narrative state is deliberately excluded.
- Chapter map: ordered chapters per project with part/act, summary, objectives,
  target words, status, and an optional viewpoint character validated against
  the same project.
- Scenes: ordered within a chapter, with summary, objectives, status, and draft
  text; word counts are recomputed whenever content changes.
- Workspace page with story bible, character, and chapter/scene tabs, including
  editing forms for every entity.
- Shared validation, work-status, and word-count helpers; duplicate and missing
  record errors are surfaced as author-facing messages.
- Tests for story bible categories and duplicates, alias normalisation, chapter
  ordering and viewpoint rules, scene ordering and word counts, and an explicit
  v1-to-v2 migration test.

### Known limitations

- Chapters and scenes cannot be reordered or deleted yet.
- Scene drafts are plain text with no revision history.
- No relationships, character knowledge, timeline, or retrieval tables yet.

## [0.1.0] — Phase 1: Foundation

### Added

- Repository structure, `pyproject.toml`, and a Git ignore policy that excludes
  databases, drafts, configuration, and model weights.
- SQLite persistence with a versioned migration runner, WAL journaling,
  foreign-key enforcement, and busy-timeout handling.
- `projects` table plus a project service for creation, selection, renaming,
  updating, and archival, with validation and duplicate-name protection.
- `generations` table as an append-only log of successful and failed attempts,
  including model, prompts, parameters, token counts, duration, and truncation.
- `app_settings` table for the active project, selected model, and generation
  parameters, with safe fallback to configured defaults.
- Provider abstraction (`LLMProvider` protocol) with model discovery,
  availability probing, and non-streaming generation.
- Ollama provider with explicit handling for unreachable server, timeouts,
  missing models, empty output, malformed JSON, HTTP failures, and truncated
  completions.
- Jinja2 scene-writing prompts built from project metadata and author notes.
- Streamlit interface: project dashboard, writing workspace with model and
  parameter controls plus generation history, and a settings page for
  connection status, installed models, and defaults.
- Pytest suite covering migrations, project validation and persistence,
  provider payloads and error mapping, generation persistence and failures, and
  settings fallbacks. All inference is stubbed.
- README with installation, execution, configuration, and architecture details,
  plus `config.example.toml`.

### Known limitations

- Model discovery is Ollama-only; no other provider is implemented.
- Editing, approval, revision history, and manuscript export are not available.
- No narrative memory, retrieval, or continuity checking yet (Phases 3–5).
- Streaming generation is not supported; one request runs at a time.
