# Changelog

All notable changes to Novellire are documented here.
The project follows semantic versioning for the application, not the schema.

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
