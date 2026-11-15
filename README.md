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
  drafts are editable before insertion. Chapters, and the legacy scene records
  inside them, can be moved up or down and deleted; positions are renumbered in
  the same transaction so the order stays contiguous in the database.
  Generation receives the four documents plus the story bible entries and
  character profiles that match the request. Matching uses names, aliases,
  titles, categories, and shared words, and the chapter's viewpoint character,
  so established canon reaches the model without flooding its context window.
- **Project settings** — details for one novel: title, premise, genre, narrative
  style, and word target, plus archiving. Reached from Home or the Workspace
  header.
- **Preview** — the reading surface. Cream paper in both themes, a Garamond-first
  serif stack, drop caps, chapter navigation, and live reading size and measure
  controls.
- **App settings** — installation-wide preferences: appearance (theme, accent,
  interface and reading fonts, sizes, reading width), the Ollama connection and
  generation defaults, data locations, and build information.
- **Export** — compile the manuscript into Markdown or plain text, with an
  optional appendix of the four project documents. The file is previewed and can
  be downloaded or copied; only chapters with text are included.
- **Memory** — full-text search over every chapter's prose, stored summaries,
  and the four project documents. Results are labelled by source and link back
  to the chapter or document. Chapter summaries are generated by the model from
  the saved text and stored on the chapter.
- **Chat, Continuity** — designed scopes. Their layout, filters, and detail panes
  are reserved and labelled with the phase that will connect them; they show no
  project data yet.

Appearance choices are stored in the database (`app_settings`, key
`appearance.settings`) and mirrored to `localStorage`, so the workspace reopens
with the same look with no flash of the wrong theme.

## Tests

```bash
pytest
```

141 tests run fully offline. All inference is stubbed, so no model or Ollama
server is needed. `tests/test_api.py` drives the real FastAPI app with a test
client and covers project scoping, error mapping, document saves, pre-written
chapter protection, automatic style-guide learning, generation persistence,
summary storage, full-text search, export, and appearance round-trips.

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
    static/js/api.js       JSON fetch wrapper and error mapping
    static/js/ui.js        DOM helpers, modal, toasts, prose rendering
    static/js/views/       home, project-settings, projects, workspace,
                           preview, export, memory, settings, scopes
  config.py                Settings model, TOML loading, env overrides
  errors.py                User-facing error hierarchy
  logging_setup.py         Logging (never logs prompts or prose)
  core/
    projects.py            Project validation and use cases
    settings_service.py    Persisted generation and appearance preferences
    generation.py          Prompt -> provider -> saved record
    documents.py           Workspace document definitions and save/read service
    style_guide.py         Learns a style guide from the manuscript
    story_bible.py         Categorised story bible entries (legacy API)
    characters.py          Character profiles and aliases (legacy API)
    context.py             Relevance-ranked canon context for generation
    summaries.py           Chapter summary generation and storage
    memory.py              Search results labelled by chapter or document
    export.py              Markdown and text manuscript compilation
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
| `generation.context_window` | `4096` | `num_ctx` passed to the model |

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

Migrations are applied in order inside transactions; an existing database is
upgraded in place without losing projects, generations, or chapter text.

## Status

Current release: **v0.2.6** (schema version 4). `v0.2.6` adds the Memory phase:
generated chapter summaries, an FTS5 index kept in sync by database triggers,
and a searchable Memory surface. It builds on `v0.2.5`, which added manuscript
export, and on `v0.2.4`, which separated Home from the project Workspace and
added reordering and deletion for chapters and scenes.

The Phase 1 foundation, the Phase 2 narrative data model, and local manuscript
memory are complete, and the interface is a browser harness. Still missing:
event and entity extraction, semantic (embedding) retrieval, continuity
validation, and cloud API providers. Chat and Continuity exist as designed UI
scopes only. The older story bible entry, character, and scene endpoints remain
for compatibility but are no longer part of the Workspace.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Prabir Kumar Das.
