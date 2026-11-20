# Novellire

AI narrative intelligence & novel writing environment.

Novellire is an LLM orchestration harness for long-form fiction. It keeps a
project's master story bible, character bible, chapter map, style guide, chapter
text, and generation history in one SQLite database, and writes prose with a
model running on your own machine.

`v0.2.0` replaces the Streamlit prototype with a browser interface: a FastAPI
server exposes a small JSON API and serves a static client written in HTML, CSS,
and vanilla JavaScript. No build step, no frontend framework, and no external
assets — the interface loads from the same loopback process that owns the data.

## Privacy and network use

By default Novellire runs entirely on your machine, and what leaves it depends on
the provider you choose.

- **Local models (the only mode implemented today).** Inference goes to an Ollama
  server on `http://localhost:11434`. Prompts, story bibles, and prose stay on
  this machine. Novellire sends no telemetry and loads no remote fonts, scripts,
  or stylesheets.
- **Cloud API providers (planned).** A later release adds hosted providers next
  to local models. They will be opt-in: you configure a provider and its key, and
  you select it explicitly. While a cloud provider is selected, the prompt and
  the project context needed for that request are sent to that provider under its
  own terms. Novellire will label the active provider in the interface and
  document each provider's data flow before it ships.
- **Never silent.** Novellire does not enable cloud inference, analytics, or
  background uploads on its own, and it will not switch providers behind your
  back.

The server has no authentication and binds `127.0.0.1` by default. Do not expose
it to a network interface you do not trust.

## Setup

### Requirements

- Windows 11 (developed and tested there), macOS, or Linux
- Python 3.11 or newer
- A modern browser (the client is plain ES modules; no bundler)
- [Ollama](https://ollama.com) for generation, reachable on
  `http://localhost:11434`
- A model small enough for the machine. On 8 GB RAM, start with:

  ```bash
  ollama pull qwen2.5:1.5b
  ```

### Install

Clone the repository and install it into a virtual environment (PowerShell or
Git Bash):

```bash
git clone https://github.com/theprabir/Novellire.git
cd Novellire
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS or Linux the activation command is `source .venv/bin/activate`.

Optional: copy `config.example.toml` to `config.toml` to change the Ollama
endpoint, timeouts, or default generation parameters. Novellire runs without a
configuration file using built-in defaults.

### Run

Start Ollama in one terminal:

```bash
ollama serve
```

Start Novellire in another:

```bash
novellire
# or: python -m novellire
```

Then open <http://127.0.0.1:8000>. Options: `--host`, `--port`, `--log-level`.
The default host is loopback and the default port is `8000`.

The interface has these surfaces:

- **Home** — the library overview: every project with word counts, generation
  counts, and target progress, plus a continue-writing card and the author's
  GitHub and Instagram links. Home is not the workspace; opening a project moves
  into that novel's workspace.
- **Workspace** — a project's writing surface, with four documents plus the
  chapter list:
  - *Master Story Bible* — complete storyline, themes and metaphysics, historical
    background, world rules, and important events.
  - *Character Bible* — personalities and motivations, physical descriptions,
    relationships and romantic developments, secrets and internal conflicts,
    and character arcs.
  - *Chapter Map* — chapter objectives, key events, emotional progression, plot
    revelations, and cliffhangers.
  - *Style Guide* — narrative perspective, sentence structure, vocabulary,
    dialogue style, descriptive density, emotional intensity, and what to avoid.
  Each document is one editor; its categories are shown as placeholder guidance,
  not as separate forms. All four are fed to generation.
  *Chapters* holds the manuscript itself. Add a chapter with a title and paste its
  full text: Novellire counts and displays words and marks it pre-written, and
  the AI never rewrites it. New chapters can be drafted from the documents, and
  drafts are editable before insertion. Saving changed chapter text keeps the
  previous version in **History**. Each revision can be compared side by side
  with the current draft, with removed and added words highlighted, then
  restored; restoring also saves the current text first, and the newest 50
  snapshots are kept per chapter. Restore is blocked while there are unsaved
  editor changes. A chapter with text can be summarised or have its **events
  extracted** into episodic memory. Each chapter has a workflow status; when it
  is **approved**, its prose is locked and must be reopened before manual edits,
  AI insertion, or a revision restore can change it. Each chapter also has an
  editable **scene plan**; **Plan with AI** proposes one from the chapter
  summary, project documents, and retrieved memory, and the saved plan is
  included when the chapter is drafted. A Chapter Map with numbered headings can
  be previewed with **Build chapters**, which creates only missing chapter
  records and leaves existing chapters untouched. A map may continue after
  written chapters: with fourteen chapters already written, a map starting at
  Chapter 15 creates Chapters 15 onward. When earlier written chapters exist,
  **Build chapters** then analyses them sequentially: it adds missing summaries
  and episodic events while leaving author-written summaries and stored events
  untouched, and streams per-chapter progress in the dialog. New chapters can be
  inserted at a chosen chapter number, shifting later chapters down. Chapters, and the
  legacy scene records inside them, can be moved up or down and deleted;
  positions are renumbered in the same transaction so the order stays contiguous
  in the database.
  Generation receives the four documents plus the story bible entries and
  character profiles that match the request. Matching uses names, aliases,
  titles, categories, and shared words, and the chapter's viewpoint character,
  so established canon reaches the model without flooding its context window.
  It also retrieves earlier chapters through the Memory index and adds their
  summaries and short passages, with chapter numbers and titles, under an
  **Earlier chapters** prompt section. Extracted episodic events are ranked
  against the same request and added under **Earlier events**, including their
  characters, locations, objects, and unresolved threads. The draft dialog shows
  exactly which chapters and events were given to the model.
- **Project settings** — details for one novel: title, premise, genre, narrative
  style, and word target, plus archiving. Reached from Home or the Workspace
  header.
- **Preview** — the reading surface. Cream paper in both themes, a Garamond-first
  serif stack, drop caps, chapter navigation, and live reading size and measure
  controls.
- **App settings** — installation-wide preferences: appearance (theme, accent,
  interface and reading fonts, sizes, reading width), the Ollama connection and
  generation defaults, data locations, build information, and backup/restore.
  Backups are consistent SQLite snapshots; a restore validates the file, keeps a
  pre-restore safety copy, migrates older schemas, and requires confirmation.
- **Export** — compile the manuscript into Markdown, Word (.docx), or plain
  text, with an optional appendix of the four project documents. Each part
  becomes a part break, every chapter heading carries its word count, and the
  file opens with a chapter and word total. Markdown and text are previewed and
  can be copied; the Word document is generated locally and downloaded. Only
  chapters with text are included.
- **Memory** — full-text search over every chapter's prose, stored summaries,
  and the four project documents. Results are labelled by source and link back
  to the chapter or document. Chapter summaries are generated by the model from
  the saved text and stored on the chapter. **Summarise all chapters** runs the
  project sequentially, skips chapters that already have a summary (and ones
  without text), and streams per-chapter progress into the page. **Episodic
  memory** shows extracted events with their characters, locations, objects,
  unresolved threads, and the chapter that produced them. Events are linked to
  character profiles by name or alias, can be filtered by character, and can be
  edited or deleted in place. **Character relationships** are split into
  author-controlled typed records and derived associations. Records are
  proposed, approved, rejected, edited, or deleted in place; only approved
  records count as canon, while derived co-occurrence stays clearly marked as
  non-canon with event provenance. Approved records are included in generation
  context when their characters are selected; proposed, rejected, and derived
  associations are never injected. **Character state** records authored
  snapshots per chapter (location, status, goals, knowledge), shows the latest
  chapter as current with earlier snapshots as history, and supplies current
  state for selected characters to generation.
- **Chat** — a full-height conversation surface scoped to the project or one
  chapter. A centred 768px feed is the only thing that scrolls; the composer
  floats above the bottom edge. **Plan** and **Write** can be switched from the
  composer at any point in a conversation: Plan keeps compact, editable planning
  notes, while Write rebuilds its context from the documents, notes, chapter, and
  memory on every turn. Replies stream token by token and render as markdown;
  the round action button becomes **Stop**, which keeps the text received so far.
  In Write mode, a reply can be **revised**: Novellire rewrites the chosen reply,
  or the whole chapter, from fresh context, keeps the original in the transcript
  for comparison, and leaves the chapter untouched until the revision is
  inserted. A reply can also be **inserted into its chapter** — appended, or used
  to replace the chapter text — with the previous text kept in revision history
  and approved chapters refused until reopened. A chapter-scoped conversation
  shows its chapter in a **side-by-side pane** that refreshes after an insert,
  and every reply can expand a **context drawer** listing the earlier chapters
  and memory events retrieval gave it. A reply in progress is checkpointed while
  it streams, so a crash, a closed browser, or a shutdown leaves an **interrupted
  reply** above the composer to keep as a message or discard. Conversations live
  in a slide-over drawer, and a reload reopens the stored conversation, its pane,
  and the draft belonging to it.
- **Continuity** — the recorded canon, without a model: the chapter timeline with
  extracted events, each character's state changes, relationship evolution,
  open and resolved threads, timeline validation, canon changes awaiting a
  decision, and a deterministic contradiction audit. A saved chapter can be
  checked against cited canon, and the canon can be scanned with AI, every
  finding citing records the project holds.
- **Style** — how the manuscript actually reads: sentences, average and longest
  sentence, paragraphs with dialogue, and long sentences, per chapter and in
  total. Counted locally without a model. The Style Guide is numbered into rules,
  and a per-chapter **Check deviations** pass, read-only, reports only departures
  that cite one of those rules and quote the chapter exactly once. The same
  surface adds **pacing** (paragraph and sentence rhythm, dialogue density per
  chapter) and **repeated phrases** (a four-word phrase seen three or more times,
  with its example sentences), both measured locally with no model. **Revision
  suggestions** turn those measurements into a located per-chapter checklist — a
  quoted long sentence or dense paragraph, a repeated phrase, one next step —
  linking straight to the chapter editor and disappearing as the prose changes.

Appearance choices are stored in the database (`app_settings`, key
`appearance.settings`) and mirrored to `localStorage`, so the workspace reopens
with the same look with no flash of the wrong theme.

## Tests

```bash
pytest
```

327 tests run fully offline. All inference is stubbed, so no model or Ollama
server is needed. `tests/test_api.py` drives the real FastAPI app with a test
client and covers project scoping, error mapping, document saves, pre-written
chapter protection, automatic style-guide learning, generation persistence,
summary storage, full-text search, event extraction, character linking,
event-aware generation, backup/restore, export, chapter revisions, and
appearance round-trips.

## Architecture

```
novellire/
  __main__.py              CLI entry point (--host, --port, --log-level)
  api/
    app.py                 Application factory, JSON API, static client serving
  web/                     Browser client (no build step)
    index.html             Shell, icon sprite, theme bootstrap, modal, toasts
    static/app.css         Design tokens, layout, reader, settings, scopes
    static/js/app.js       Boot, routing, state, appearance, sidebar chrome
    static/js/api.js       JSON fetch wrapper, error mapping, NDJSON streams
    static/js/markdown.js  Safe markdown-to-DOM renderer for model replies
    static/js/ui.js        DOM helpers, modal, toasts, prose rendering
    static/js/views/       home, project-settings, projects, workspace,
                           preview, export, memory, settings, chat, continuity, style, scopes
  config.py                Settings model, TOML loading, env overrides
  errors.py                User-facing error hierarchy
  logging_setup.py         Logging (never logs prompts or prose)
  core/
    projects.py            Project validation and use cases
    backup.py              Snapshot, validation, and safe database restore
    settings_service.py    Persisted generation and appearance preferences
    generation.py          Prompt -> provider -> saved record
    documents.py           Workspace document definitions and save/read service
    style_guide.py         Learns a style guide from the manuscript
    style.py               Measured prose and cited departures from the guide
    pacing.py              Paragraph rhythm, dialogue density, repeated phrases
    revision.py            Located revision suggestions from measured prose
    story_bible.py         Categorised story bible entries (legacy API)
    characters.py          Character profiles and aliases (legacy API)
    context.py             Ranked canon and earlier-chapter context for generation
    summaries.py           Chapter summary generation and storage
    events.py              Event extraction, character linking, and editing
    relationships.py       Typed, author-approved relationship records
    character_states.py    Author-recorded character state snapshots
    memory.py              Search results labelled by chapter or document
    export.py              Markdown, text, and Word manuscript compilation
    docx.py                Minimal dependency-free Word document writer
    chapters.py            Ordered chapters with pasted or drafted text
    scenes.py              Ordered scenes and scene drafts (legacy API)
    work_status.py         Shared planned/drafting/drafted/approved values
    validation.py          Shared input validation helpers
    text.py                Word counting
  llm/
    base.py                Provider-neutral request/result types + protocol
    ollama.py              Ollama HTTP provider and error mapping
  prompts/
    templates.py           Jinja2 prompt templates
  storage/
    schema.py              Ordered, versioned migrations
    database.py            Connection handling, PRAGMAs, migration runner
    repositories.py        SQL access for projects, generations, settings
    document_repository.py SQL access for workspace documents
    search_repository.py   FTS5 queries over the search index
    event_repository.py    Episodic events with chapter provenance
    relationship_repository.py  Typed relationship records with provenance
    state_repository.py    Character state snapshots with chapter provenance
    story_repositories.py  SQL access for story bible, characters, chapters, scenes
tests/                     Pytest suite with a fake provider
```

The API is a transport layer, not a second implementation. Validation, prompt
construction, storage, and inference all live in the existing services, so the
browser client and the CLI share exactly the same rules.

Rules that hold throughout the codebase:

- Browser code renders and calls the JSON API; it never runs SQL or builds
  prompts, and all author text is inserted as text rather than markup.
- All inference goes through `novellire.llm.base.LLMProvider`.
- Every schema change is a new numbered migration; applied versions are never
  edited.
- Generation logs are append-only, so failed attempts remain visible.
- Story records are project-scoped through foreign keys; chapters and scenes keep
  their own order and never share narrative memory across projects.
- Character profiles hold identity information only. Evolving state (location,
  knowledge, relationships) is a separate concern reserved for a later phase.

## API

FastAPI publishes interactive docs at <http://127.0.0.1:8000/api/docs> and the
OpenAPI document at `/api/openapi.json`. Errors return a JSON `detail` string with
a matching status: `400` validation, `404` missing project or record, `409`
duplicate, `422` schema, `502` provider failure.

## Configuration

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `data_dir` | `data` | Where `novellire.db` lives |
| `log_level` | `INFO` | Application log level |
| `ollama.base_url` | `http://localhost:11434` | Local Ollama endpoint |
| `ollama.request_timeout_seconds` | `180` | Generation timeout |
| `ollama.connect_timeout_seconds` | `5` | Connection timeout |
| `ollama.keep_alive` | `5m` | Model residency in Ollama |
| `generation.model` | `""` | Initial model selection |
| `generation.temperature` | `0.8` | Sampling temperature |
| `generation.top_p` | `0.9` | Nucleus sampling |
| `generation.num_predict` | `700` | Maximum output tokens |
| `generation.context_window` | `4096` | `num_ctx` passed to the model; UI offers 2k–16k and prompt budgets scale with it |
| `analysis.auto_run` | `true` | Queue background chapter analysis after chapter and document saves |

Environment overrides: `NOVELLIRE_CONFIG`, `NOVELLIRE_DATA_DIR`,
`NOVELLIRE_OLLAMA_URL`.

The data directory, databases, `config.toml`, and generated drafts are ignored
by Git. Never commit a novel project's database.

## Database schema

| Version | Contents |
| :--- | :--- |
| 1 | `projects`, `generations`, `app_settings` |
| 2 | `story_bible_entries`, `characters`, `character_aliases`, `chapters`, `scenes` |
| 3 | `project_documents`; chapter `content`, `word_count`, `origin` |
| 4 | `search_index` (FTS5) with triggers over chapters and documents |
| 5 | `narrative_events` with chapter provenance and entity lists |
| 6 | `event_characters` links between extracted events and character profiles |
| 7 | `character_relationships` author records |
| 8 | `character_states` authored snapshots tied to chapters |
| 9 | `chapter_revisions` snapshots of earlier chapter text |
| 10 | `analysis_state` content hashes and `chapter_insights` derived proposals |
| 11 | `chat_threads` and `chat_messages` for persistent conversations |
| 12 | chat message `context_json`, the retrieval each reply was given |
| 13 | `chat_drafts` checkpoints of a reply that was still streaming |
| 14 | chat message revision scope and the reply a revision came from |
| 15 | the chapter passage a revision rewrote, so it applies only there |
| 16 | `thread_resolutions` author decisions about recorded plot threads |
| 17 | chapters' optional `story_day` anchor for timeline validation |
| 18 | `relationship_snapshots`: each relationship's state in a chapter |
| 19 | `canon_supersessions`: author decisions that a later record replaces one |

Migrations are applied in order inside transactions; an existing database is
upgraded in place without losing projects, generations, or chapter text.

## Status

Current release: **v0.6.3** (schema version 19). `v0.6.3` turns the measured
review into revision suggestions: a per-chapter checklist quoting long sentences,
dense paragraphs, and repeated phrases, each with one next step, linking to the
chapter editor and storing nothing. `v0.6.2` adds a deterministic
pacing and repetition review to the Style surface: paragraph and sentence rhythm,
dialogue density per chapter, and four-word phrases repeated three or more times
with the sentences they appear in, all counted locally without a model. `v0.6.1` adds style analysis:
the Style view measures the stored prose locally and numbers the Style Guide into
rules, and a read-only per-chapter check reports deviations that cite one of
those rules and quote the chapter exactly once. A one-word chapter now reads
“1 word”. `v0.6.0` starts editorial and
export work with a complete manuscript export: Markdown, plain text, and a
locally generated Word document, each with part breaks, chapter headings, and
per-chapter and total word counts. `v0.5.8` adds provenance to
every continuity finding: the cited canon record now also names its kind and the
chapter it came from, and contradiction findings show that for both sides.
`v0.5.7` reviews canon changes:
Continuity lists state snapshots that differ from the one before them, and the
author can mark the earlier record superseded, with a note, so it stays as
history but is no longer cited as current canon. `v0.5.6` detects contradictions
inside recorded canon: a deterministic audit reports a character pair recorded
with conflicting relationship types or a thread raised again after its recorded
resolution, and a read-only scan compares the canon records with each other,
keeping only findings that cite two records the project holds. `v0.5.5` follows relationship
evolution: a chapter can propose how a pair of characters now stands, the author
reviews and applies it, and each chapter's relationship state is recorded with
provenance, so Continuity shows how the relationship changed. `v0.5.4` validates
the recorded timeline: a chapter can carry an optional story day, and Continuity
reports any chapter that runs backwards in story time against the chapter before
it, while leaving deliberate flashbacks to the author. `v0.5.3` proposes character
state updates from a finished chapter, validated against the roster and applied
only when the author confirms. `v0.5.2` lets the author
resolve or reopen a recorded plot thread, keeping the note and the chapter where
it paid off. `v0.5.1` turns the Continuity
page into a deterministic ledger of the recorded canon: the chapter timeline,
each character's state changes, and unresolved threads, all with chapter
provenance. `v0.5.0` starts continuity
intelligence: a saved chapter can be checked against its recorded canon, and
every finding must cite a supplied record and quote the chapter exactly once.
`v0.4.14` discusses a saved
scene plan before drafting: Novellire asks what the plan leaves undecided, and
the author's answers feed the scene-by-scene draft. `v0.4.13` reviews a generated
draft against its plan and canon and proposes findings, each quoting prose the
server verified in the draft, which the author can apply to the draft.
`v0.4.12` drafts a chapter
scene by scene from its saved plan, one sequential inference per beat, into one
editable draft. `v0.4.11` lets the author
revise one selected passage in Chat and apply it in place, leaving the rest of
the chapter untouched. `v0.4.10` adds revision to
Chat: the author can rewrite a chosen reply, or the whole chapter, from fresh
context, compare the result with the original, and only then insert it into the
chapter. `v0.4.9` checkpoints a chat
reply while it streams, so a crashed process, a closed browser, or a shutdown
leaves recoverable text that the author can keep or discard. `v0.4.8` adds a
side-by-side chapter pane to Chat and a context drawer showing the retrieval
behind each reply, stored with the message so it survives a reload. `v0.4.7`
scopes chat drafts per conversation and adds **Insert into chapter** for
Write-mode replies, respecting the approval lock and keeping a revision
snapshot. `v0.4.6` rebuilds Chat as a
full-height conversation surface: a centred scrolling feed, markdown replies, a
pinned floating composer, a Plan/Write switch inside the chat, and one
Send/Stop button. `v0.4.5` streams Chat replies as the model
produces them, keeping the partial reply when stopped. `v0.4.4` adds persistent
project- and chapter-scoped Chat with Plan and Write modes, retrieval-backed
context, and author-controlled planning notes. `v0.4.3` adds automatic analysis
of every written chapter, queued after chapter and document saves with content
hashes, derived character-state/location/relationship/open-thread proposals, and
preservation of manual memory. `v0.4.2` adds Chapter Map outline
import, chapter-number insertion, and context budgets that scale with the
selected 16k window. `v0.4.1` adds
editable chapter scene plans, AI plan proposals, and plan-aware drafting.
`v0.4.0` adds chapter
workflow status and locks approved prose against manual, AI, and
revision-restore changes until the chapter is reopened. `v0.3.8` added
side-by-side revision
comparison, a 50-snapshot cap per chapter, and unsaved-edit protection for
restore. `v0.3.7` added automatic chapter revision history; schema 9 stores the
snapshots. It builds on `v0.3.6`, author-recorded character state snapshots with
current/history views and generation context; `v0.3.5`, approved relationship
records in generation context;
`v0.3.4`, typed author-approved relationship records with optional event
provenance; `v0.3.3`, relationship discovery from shared events; `v0.3.2`,
event-to-character linking with
conservative name/alias matching and event editing; `v0.3.1`, validated backup
and restore with pre-restore safety copies; `v0.3.0`, event-aware generation;
`v0.2.9`, structured event extraction; `v0.2.8`, earlier chapter retrieval in
generation; `v0.2.7`, sequential bulk summaries; `v0.2.6`, the FTS5 Memory index;
`v0.2.5`, manuscript export; and `v0.2.4`, which separated Home from the
Workspace and added chapter and scene ordering.

The Phase 1 foundation, the Phase 2 narrative data model, and local manuscript
memory are complete, and the interface is a browser harness. Still missing:
semantic (embedding) retrieval, continuity validation, and cloud API providers. Continuity exists as a designed UI scope only. The older story bible entry, character, and scene endpoints remain
for compatibility but are no longer part of the Workspace.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Prabir Kumar Das.
