# Changelog

All notable changes to Novellire are documented here.
The project follows semantic versioning for the application, not the schema.

## [0.2.1] — 2026-11-15

Interface bug-fix and packaging release on the 0.2 line. Schema version stays at
2 and no project data is migrated.

### Fixed

- Removed the sidebar collapse control. It shrank the sidebar to an icon rail,
  hid the project file tree, hid its own toggle, and persisted that state in
  `localStorage`, so the interface reopened compressed with no way back.
- The sidebar "New project" button had no click handler; it now opens the project
  dialog from any page.
- The mobile sidebar toggle rendered on desktop, where it did nothing, because
  `.icon-btn` overrode `.mobile-only`. It now appears only below 900px.
- Archiving a project left that project's bible, cast, and chapters in the
  sidebar. Reloading the project list now refreshes the project tree as well.
- The topbar theme toggle re-rendered the view and discarded unsaved editor text.
  It now applies the theme without touching the current view.
- The Preview reader's A+/A- controls stopped after one step because they read a
  stale appearance snapshot; they now step through the full 15-26px range.
- The breadcrumb repeated the section name ("Projects > Project > Projects").
- Modals without footer buttons rendered an empty bordered strip.
- The "System" theme preview drew mismatched split blocks.
- Project initials included punctuation, so "Salt & Ember" became "S&".
- Links and link-styled buttons underlined on hover, including sidebar items,
  tree rows, chapter links, and `Read`/`Open in editor` buttons.

### Changed

- The sidebar keeps a fixed width; the small-screen drawer remains.
- The workspace, reader, and settings layouts stack at 1080px instead of
  squeezing two columns into a mid-size window.

### Added

- `LICENSE` (MIT, Copyright (c) 2026 Prabir Kumar Das) and SPDX metadata in
  `pyproject.toml`, including repository and issue URLs.
- README setup rewritten around the public repository: clone, virtual
  environment, editable install, then `ollama serve` and `novellire`.
- The packaged project description is now "AI narrative intelligence & novel
  writing environment".

## [0.2.0] — 2026-11-15

The interface is rewritten as a browser harness served by a small FastAPI
application. Streamlit is gone, the data model and services are unchanged, and
schema version stays at 2.

### Changed

- Frontend stack replaced: the Streamlit pages were removed and the app now
  serves a static HTML/CSS/vanilla-JavaScript client from a FastAPI application
  factory (`novellire.api.app:create_app`). A `novellire` console script and
  `python -m novellire` start it on `127.0.0.1:8000` with `--host`, `--port`,
  and `--log-level`.
- `AGENTS.md` records HTML, CSS, and vanilla JavaScript as the interface stack;
  nothing else in that document changed.
- Appearance preferences (theme, accent, interface and reading fonts, sizes,
  reading width) moved into `app_settings` under `appearance.settings`, with a
  `localStorage` mirror and a pre-paint theme bootstrap.
- README rewritten for the new stack. The local-only privacy guarantee is now
  scoped to local models; cloud providers are documented as planned, explicit,
  opt-in additions.

### Added

- Application shell: sidebar with project switcher, navigation, and a collapsible
  project file tree; breadcrumb topbar with theme toggle and data reload; modal
  and toast primitives; responsive and collapsed-sidebar layouts.
- Projects page with per-project cards (words, generations, target progress) and
  create, edit, and archive dialogs.
- Workspace with a section switcher for story bible, characters, and chapters:
  searchable lists, a story bible entry editor, a character editor covering
  aliases and all eleven profile fields, a chapter editor with viewpoint, status,
  and target words, and a scene list with a full prose editor.
- Generation dialog inside the scene editor: model selection from the local
  Ollama server, target length, context notes, temperature, top-p, output limit,
  and context window, followed by an editable result that is inserted or
  appended into the scene. The saved generation log remains immutable.
- Preview reader: chapter navigation, cream paper surface in both themes, a
  Garamond-first serif stack, drop caps, scene ornaments, colophon, and live
  reading size and measure controls.
- Settings page: theme (system/light/dark), five accents, interface and reading
  fonts, both type sizes, reading width, Ollama status and generation defaults,
  data locations, build information, and a disabled "cloud API providers —
  planned" card so the future provider switch already has a home.
- Designed UI scopes for Chat, Memory, Continuity, and Export, each labelled with
  the phase that will connect it, so later backend features need no redesign.
- JSON API for appearance and generation settings, Ollama status, project tree,
  manuscript, story bible, characters with aliases, chapters, scenes, generation,
  and generation history, with errors mapped to `400`, `404`, `409`, `422`, and
  `502`.
- Tests: 17 HTTP tests driving the FastAPI app with a stub provider, plus two
  appearance service tests. 109 tests total.

### Removed

- Streamlit interface (`novellire/ui/`, root `app.py`) and the `streamlit`,
  `pandas`, `pyarrow`, `altair`, and `pydeck` dependencies.

### Known limitations

- Chat, Memory, Continuity, and Export are layout scopes; they display no data.
- Cloud API providers are not implemented yet.
- Generation prompts still use project metadata and author notes only; story
  bible entries, character profiles, and prior prose are not yet included.
- Chapters and scenes cannot be reordered or deleted.
- Scene drafts are plain text with no revision history, and there is no import.

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
