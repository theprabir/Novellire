# Changelog

All notable changes to Novellire are documented here.
The project follows semantic versioning for the application, not the schema.

## [0.3.3] — 2026-11-16

Character relationship discovery from episodic memory. Schema stays at 6.

### Added

- `GET /api/projects/{id}/relationships` derives character pairs from events
  where both profiles are linked. Each relationship reports shared-event count,
  latest event summary, latest chapter, and `derived` status.
- Memory now shows a **Character relationships** section under episodic memory,
  ordered by shared-event count. It refreshes after events are edited or
  deleted.
- Relationships are explicitly derived, not canon, and carry event/chapter
  provenance. No relationship data is stored separately yet.
- Latest relationship provenance follows chapter position rather than event
  insertion id, so extracting an earlier chapter later does not misreport it as
  the newest event. Event id breaks ties within one chapter.

## [0.3.2] — 2026-11-16

Event-to-character links, character filtering, and event editing. Schema 6 adds
`event_characters` and `narrative_events.links_resolved`.

### Added

- Extracted events are linked to character profiles by character name, first
  name, or alias. Links are written when extraction completes and lazily
  backfilled for older events when Memory loads them.
- Character name and alias changes invalidate the project's event links so the
  next Memory load resolves them against the updated profiles.
- First-name matching is conservative: stopwords such as “the” are never used
  as a first name, and a first name shared by multiple profiles does not link
  any of them. Full names and aliases still match exactly.
- Memory shows linked character names on each event and has an **All characters**
  filter that narrows events to one profile, with a visible match count.
- Events can be edited from Memory: summary, characters, locations, objects, and
  unresolved threads. Saving relinks the edited event. Events can also be
  deleted after confirmation.
- `PATCH /api/events/{id}` and `DELETE /api/events/{id}`.
- `novellire/core/events.py` now owns matching and link maintenance.

## [0.3.1] — 2026-11-16

Backup and restore. Schema stays at 5.

### Added

- `GET /api/backup` creates a consistent snapshot with SQLite's backup API
  (including committed WAL content) and downloads it as `novellire-backup-*.db`.
  The temporary download file is removed after the response.
- `POST /api/backup/restore` accepts a raw SQLite upload, verifies its header,
  `PRAGMA integrity_check`, Novellire tables, and schema history, and rejects
  backups created by a newer schema with a clear error. Valid older backups are
  migrated to the current schema after restore.
- A pre-restore safety copy is written to `data/backups/pre-restore-*.db` before
  the database is replaced. If migration of the restored file fails, the previous
  database is restored automatically.
- App settings now has **Download backup** and **Restore backup** controls. Restore
  requires confirmation, reports restored project and chapter counts, and reloads
  the client.
- `novellire/core/backup.py`.

## [0.3.0] — 2026-11-16

Event-aware generation. Schema stays at 5.

### Added

- Generation context now retrieves extracted episodic events as well as earlier
  chapters. Events are scored by request-term overlap in their summary and
  character/location/object/thread fields, with exact name matches weighted
  highest; events from chapters already retrieved as context receive a boost.
- Events from the current or later chapters are excluded, as are events with no
  relevance to the request. Up to 8 events / 2,000 characters are used, separate
  from the chapter budget.
- The prompt gains an **Earlier events** section with chapter number and title,
  event summary, characters, locations, objects, and unresolved threads.
- The generation response carries `context.events`; the draft dialog groups
  retrieved sources into Chapters and Events instead of listing chapters only.

## [0.2.9] — 2026-11-16

Episodic memory extraction. Schema version 5 adds `narrative_events`.

### Added

- `POST /api/chapters/{id}/events/extract` asks the model for structured events
  from a chapter: a summary plus characters, locations, objects, and unresolved
  threads. Responses are parsed tolerantly (markdown fences and surrounding
  chatter are ignored) and every field is cleaned and bounded before storage.
- Extracted events are stored with chapter provenance (chapter id, title, and
  position), the producing model, and a timestamp. Re-extracting a chapter
  replaces only that chapter's events, in one transaction; deleting the chapter
  removes them through the foreign key.
- `GET /api/projects/{id}/events` lists a project's events in chapter order.
- The chapter editor has an **Extract events** action beside Summarise.
- The Memory surface shows **Episodic memory** above search: each event card
  carries its chapter provenance, character/location/object chips, unresolved
  threads, and the extracting model.
- `novellire/core/events.py` and `novellire/storage/event_repository.py`.

### Changed

- Static CSS/JS and the HTML shell are served with `no-store`, and the app shell
  uses versioned asset URLs, so an upgrade no longer leaves the browser running a
  cached Memory module.

## [0.2.8] — 2026-11-16

Memory-aware generation. Schema stays at 4.

### Added

- Generation context now retrieves earlier chapters from the project's FTS
  index using the request's distinctive words, and includes their summaries and
  short passages in the prompt under an **Earlier chapters** section with
  chapter number and title. Up to six chapters / 3,000 characters are used.
- Retrieval is scoped to chapters before the one being written and excludes the
  current chapter, including when its existing summary matches the request.
- The generation response carries `context.chapters` with each source's id,
  position, title, summary, and excerpt. The generated-draft dialog lists those
  sources in a collapsible **Earlier chapters given to the model** panel, and the
  generate dialog explains that selection happens automatically.
- `SearchRepository.search_terms` provides OR-ranked retrieval for context;
  author-facing Memory search keeps its exact AND behaviour.

## [0.2.7] — 2026-11-16

Bulk chapter summaries. Schema stays at 4.

### Added

- `POST /api/projects/{id}/summaries` summarises the project one chapter at a
  time and streams newline-delimited progress events (`start`, one `step` per
  chapter, then `done`). Chapters that already have a summary and chapters
  without text are reported as skipped rather than sent to the model.
- The run stops at the first inference error and reports it, so a stopped Ollama
  or missing model does not repeat the same failure for every remaining chapter.
  Completed summaries are already saved when a later step fails.
- The Memory surface has a **Summarise all chapters** action with live per-chapter
  status rows and a final count. The button disables itself when the project has
  nothing left to summarise.
- `api.stream` in the browser client reads the NDJSON progress stream; the
  server-side orchestration stays in `ChapterSummaryService.summarize_pending`.

## [0.2.6] — 2026-11-15

Memory phase. Schema version 4 adds the full-text index; existing databases are
migrated in place.

### Added

- Chapter summaries: `POST /api/chapters/{id}/summarize` reads the saved chapter
  text, asks the configured model for an 80–150 word recap, and stores it on the
  chapter. Summaries are editable in the chapter editor and never rewrite prose.
- `search_index`, an SQLite FTS5 table over chapter titles, summaries, prose,
  and all four project documents. Insert, update, and delete triggers keep the
  index aligned with the manuscript, including cascaded deletes; the migration
  backfills existing chapters and documents.
- `GET /api/projects/{id}/search?q=…&limit=20` returns ranked hits labelled as a
  chapter or a document, with a snippet. Author input is tokenised and quoted, so
  FTS operators cannot be injected.
- The Memory surface searches this project only, shows source labels and
  excerpts, and links each hit back to its chapter or document.
- `novellire/core/summaries.py`, `novellire/core/memory.py`, and
  `novellire/storage/search_repository.py`.

### Changed

- Memory is a working nav item rather than a Phase 3 placeholder; Chat and
  Continuity remain designed scopes.

## [0.2.5] — 2026-11-15

Manuscript export. Schema stays at 3.

### Added

- The Export surface compiles every chapter with text, in order, into Markdown
  (`.md`) or plain text (`.txt`). Markdown can append the four project documents
  as an appendix. Files are previewed, downloaded, or copied in the browser; no
  prose is rewritten and nothing leaves the machine.
- `GET /api/projects/{id}/export?format=markdown|text&include_documents=true`
  returns the filename, content, content type, and word count. An empty
  manuscript is rejected with a 400 rather than producing a blank file.
- `novellire/core/export.py` builds exports from stored chapter text and
  documents; the Export page no longer shows the Phase 6 placeholder.

## [0.2.4] — 2026-11-15

Navigation, ordering, and settings separation. Schema stays at 3.

### Added

- Home is a separate overview route with its own nav item: the library of
  projects, a continue-writing card, and the author's GitHub and Instagram
  links. Opening a project moves to its Workspace, so the overview and the
  writing surface are no longer the same screen.
- Project settings is its own page (`#/project/settings`), reached from Home and
  from the Workspace header. It edits the novel's title, premise, genre,
  narrative style, and target, and holds the archive action.
- Chapters and scenes can be moved one position up or down and deleted from the
  Workspace. Moves swap neighbours inside a transaction and deletes renumber the
  remaining positions, so `(project_id, position)` and `(chapter_id, position)`
  stay unique and contiguous. Endpoints: `POST /api/chapters/{id}/move`,
  `DELETE /api/chapters/{id}`, `POST /api/scenes/{id}/move`,
  `DELETE /api/scenes/{id}`.
- GitHub (<https://github.com/theprabir>) and Instagram
  (<https://instagram.com/prabir.exe>) buttons in the sidebar footer and on Home.

### Changed

- Settings is now "App settings" and states plainly that it covers this
  installation (appearance, model connection, data paths), while novel details
  live in Project settings.
- The sidebar breadcrumb starts at Home and includes Project settings.

## [0.2.3] — 2026-11-15

Canon-aware generation on the 0.2 line. Schema stays at 3.

### Added

- Generation prompts now carry relevance-ranked story bible entries and character
  profiles alongside the four workspace documents. Matching uses names, aliases,
  titles, categories, and words shared with the instructions, chapter title,
  scene title, context notes, and the chapter's summary and objectives. The
  chapter's viewpoint character is always included.
- Canon context is bounded (at most 6 entries and 5 profiles, 3,000 characters
  each) so local context windows stay usable. A cast of two or fewer is included
  whole; larger casts only appear when a name or alias matches.
- `novellire/core/context.py` builds a `GenerationContext` that
  `GenerationService` consumes, keeping prompt assembly out of the API layer.

## [0.2.2] — 2026-11-15

Workspace restructure and chapter import on the 0.2 line. Schema version 3 adds
project documents and chapter text; existing projects are migrated in place.

### Changed

- The Workspace is now four author-written documents — Master Story Bible,
  Character Bible, Chapter Map, and Style Guide — each a single editor whose
  category prompts appear as placeholders. The per-entry story bible list, the
  Characters tab, the character profile editors, and the scene list and scene
  editor are gone from this surface.
- Generation receives all four documents (each clipped to 2,500 characters) and
  drafts into chapter text instead of scene text.
- The Preview reader renders chapter prose rather than scene prose.

### Added

- Chapters hold their own text. "Add chapter" takes a title and the full pasted
  text, stores the word count, and marks the chapter pre-written. The generation
  API refuses to write into a pre-written chapter with a 400.
- `project_documents` stores one row per project and document kind, plus chapter
  `content`, `word_count`, and `origin`. Migration 3 backfills chapter text by
  joining existing scenes in order.
- Style-guide learning: `POST /api/projects/{id}/style-guide/analyze` reads the
  manuscript and documents and stores a derived guide. The first generation for
  a project that has chapters but no guide does this automatically before
  writing, and the response reports `style_guide_inferred`. A hand-written guide
  is never overwritten.
- `GET`/`PUT /api/projects/{id}/documents`, and document titles, summaries, and
  placeholders in `/api/meta`.

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
