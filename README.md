# Novellire

Local-first AI narrative intelligence and novel writing environment.

Novellire is an LLM orchestration harness for long-form fiction. Phase 1 (`v0.1`)
establishes the foundation: projects stored in SQLite, a provider abstraction
over a local Ollama server, and a Streamlit workspace where an author can create
a project, describe a scene, generate prose with a local model, and find every
attempt saved back in the project.

No cloud service is contacted. No project text leaves the machine.

## Requirements

- Windows 11 (developed and tested there), macOS, or Linux
- Python 3.11 or newer
- [Ollama](https://ollama.com) installed and reachable on `http://localhost:11434`
- A model small enough for the machine. On 8 GB RAM, start with:

  ```bash
  ollama pull qwen2.5:1.5b
  ```

## Installation

From the repository root, in a terminal (PowerShell or Git Bash):

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS or Linux the activation command is `source .venv/bin/activate`.

Optional: copy `config.example.toml` to `config.toml` to change the Ollama
endpoint, timeouts, or default generation parameters. Novellire runs without a
configuration file using built-in defaults.

## Running

Start Ollama in one terminal:

```bash
ollama serve
```

Start Novellire in another:

```bash
streamlit run app.py
```

Then open <http://localhost:8501>. The interface has four pages:

- **Projects** — create, select, and archive novel projects; see word counts.
- **Workspace** — story bible entries by category, character profiles with
  aliases, and the chapter map with ordered scenes and scene drafts.
- **Writing** — choose a model, describe a scene, set generation parameters,
  generate, and browse saved generations.
- **Settings** — Ollama connection status, installed models, and default
  generation parameters.

## Tests

```bash
pytest
```

Tests run fully offline. All inference is stubbed, so no model or Ollama server
is needed.

## Architecture

```
app.py                     Streamlit entry point
novellire/
  config.py                Settings model, TOML loading, env overrides
  errors.py                User-facing error hierarchy
  logging_setup.py         Logging (never logs prompts or prose)
  core/
    projects.py            Project validation and use cases
    settings_service.py    Persisted model/parameter preferences
    generation.py          Prompt -> provider -> saved record
    story_bible.py         Categorised story bible entries
    characters.py          Character profiles and aliases
    chapters.py            Ordered chapter blueprint
    scenes.py              Ordered scenes and scene drafts
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
    story_repositories.py  SQL access for story bible, characters, chapters, scenes
  ui/
    app.py                 Shell and sidebar navigation
    projects_page.py       Project dashboard
    workspace_page.py      Story bible, characters, chapter map, scenes
    writing_page.py        Scene generation workspace
    settings_page.py       Model and application settings
    runtime.py             Cached context, provider probes
    components.py          Shared widgets
tests/                     Pytest suite with a fake provider
```

Rules that hold throughout the codebase:

- UI components render; they never run SQL or build prompts.
- All inference goes through `novellire.llm.base.LLMProvider`.
- Every schema change is a new numbered migration; applied versions are never edited.
- Generation logs are append-only, so failed attempts remain visible.
- Story records are project-scoped through foreign keys; chapters and scenes keep
  their own order and never share narrative memory across projects.
- Character profiles hold identity information only. Evolving state (location,
  knowledge, relationships) is a separate concern reserved for a later phase.

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

Migrations are applied in order inside transactions; an existing Phase 1
database is upgraded in place without losing projects or generations.

## Status

Current release: **v0.1.1** (schema version 2).

Phase 1 is complete (`v0.1.0`). Phase 2's narrative data model ships in
`v0.1.1`: story bible entries, character profiles with aliases, and an ordered
chapter and scene structure with scene drafts. The full Phase 2 milestone
(`v0.2`) still needs document import, event extraction, and chapter summaries;
retrieval, memory, continuity validation, and export remain unimplemented.

License: to be determined.
