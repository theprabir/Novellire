# Changelog

All notable changes to Novellire are documented here.
The project follows semantic versioning for the application, not the schema.

## [0.8.0] — 2026-11-20

Installation preflight, so a new install explains itself before the server
starts.

### Added

- **`novellire doctor`**: a read-only preflight that reports the Python version,
  the configuration file in use, whether the data directory is writable, the
  database's schema version with any pending upgrade and its project and chapter
  counts, and the provider this install will use. Each check that fails names
  one next step.
- The preflight opens the database through a read-only SQLite URI and never
  migrates it, creates no data directory, reads no cloud key into its report,
  and contacts no provider or model.
- `novellire doctor --json` prints the same report as JSON, and the command
  exits `1` when a check fails, so an install script or a release check can use
  it without parsing prose.
- `novellire/core/preflight.py` holds the checks and the report; the CLI and the
  tests share one implementation.

### Changed

- `load_settings` resolves its file with `resolve_config_path`, so the preflight
  and the server agree on exactly which configuration file is read.

Schema stays at 19; no dependencies were added.

## [0.7.0] — 2026-11-20

Synthetic retrieval/continuity benchmarks and opt-in cloud inference.

### Added

- **Benchmark sample**: `samples/benchmark_novel` is a deterministic
  27-chapter manuscript with five named characters and aliases, a brass
  astrolabe planted in chapter 2 and needed in chapter 27, a secret held by one
  character, an unresolved lighthouse-lens mystery, a move from the lighthouse
  to the flooded archive, and a pair of relationship records that contradict
  each other. `annotations.json` records the canon and the retrieval probes;
  `build.py` regenerates the whole sample.
- **Retrieval benchmark**: `tests/test_benchmark.py` seeds the sample through the
  real services and measures retrieval separately from prose. All three probes
  must meet recall 1.0, precision 1.0, and mean reciprocal rank 1.0, and the
  chapter-2 detail must be returned for chapter 27 without relying on recency.
- **Continuity benchmark**: the same suite asserts the open mystery, the
  location change with provenance, the secret held by only one character, the
  planted relationship contradiction, and a continuity check that keeps only a
  finding quoting the draft once and citing the recorded location state.
- **Opt-in cloud inference**: an OpenAI-compatible provider
  (`novellire/llm/openai_compatible.py`) supports model discovery, generation,
  streaming, usage reporting, and actionable auth/model/timeout errors. It is
  used only when `[cloud].enabled` is true and the key environment variable is
  set; a missing key stops startup instead of falling back silently.
- `GET /api/providers/status` reports the active provider, its base URL, its
  privacy note, availability, and models. `/api/ollama/status` remains as an
  alias. `GET /api/settings` now describes the active provider.
- App Settings shows the active provider, its privacy note, and configuration
  guidance instead of the earlier “planned” card.

### Changed

- The cloud key is read only from the environment variable named by
  `cloud.api_key_env`; it is never written to `config.toml`, the database, or the
  browser.
- New environment overrides: `NOVELLIRE_CLOUD_ENABLED`, `NOVELLIRE_CLOUD_URL`,
  and `NOVELLIRE_CLOUD_MODEL`.

Schema stays at 19; no dependencies were added.

## [0.6.4] — 2026-11-20

Backup and restore verification, plus a simplification pass over the editorial
reviews.

### Added

- **Backup verification**: `POST /api/backup/verify` checks an uploaded file
  without restoring or changing anything and reports its schema version, whether
  an upgrade is required, its project, chapter, and character counts, and its
  size.
- Choosing **Restore backup** now verifies the file first and shows that report
  in the confirmation, so a wrong or damaged file is refused before anything is
  replaced.
- A snapshot is verified before it is offered for download: header, SQLite
  integrity, Novellire tables, and schema version. A failed snapshot is removed
  instead of being handed out.
- A restore is verified again after replacement and migration. If that check
  fails, the pre-restore safety copy is put back automatically.

### Changed

- The style profile is now the only implementation of chapter measurement
  (sentences, paragraphs, dialogue, averages, longest paragraph). Pacing reuses
  it, so the Style and Pacing sections cannot disagree, and duplicate
  measurement code is gone.
- `average`, `percent`, and `clip` live in `core/text.py` instead of three
  private copies.

Schema stays at 19.

## [0.6.3] — 2026-11-20

Revision suggestions located in the prose, without a model.

### Added

- **Revision suggestions** on the Style surface, and `GET
  /api/projects/{id}/revision-plan`: a per-chapter checklist built from the
  measurements above.
  - a sentence over 35 words, quoted, with its word count (high at 70+);
  - a paragraph over 180 words, quoted, with its word count (high at 300+);
  - a repeated phrase the pacing review found in that chapter, with how often it
    appears, so the same finding is not repeated once per occurrence.
- Each item says one next step and links to the chapter editor. At most six
  items per chapter, ordered by severity, then kind.
- The plan stores nothing. Items disappear when the prose changes, so there is no
  dismissal state to keep in sync with the manuscript, and nothing is rewritten.

Schema stays at 19; the plan is derived from existing records.

## [0.6.2] — 2026-11-20

Pacing and repetition review, measured locally without a model.

### Added

- **Pacing** on the Style surface: paragraphs, average and longest paragraph,
  average sentence, and the share of paragraphs carrying dialogue, per chapter
  and for the manuscript. It reports measurements rather than verdicts, so a
  deliberately slow chapter is not flagged as wrong.
- **Repeated phrases**: a four-word phrase appearing three or more times is
  listed with its count, the chapters it appears in, and up to five example
  sentences. Adjacent repeated windows with the same count are merged, so one
  crutch sentence is one finding (`“the gate was sealed with iron”`) instead of
  three overlapping four-word ones. Windows made only of stopwords are ignored.
- `GET /api/projects/{id}/pacing` returns counts, the pacing summary, per-chapter
  rows, and the repetition findings. The review reads at most 200,000 words at
  once and reports `truncated` instead of implying it read the whole manuscript.
- Sentence splitting moved to `core/text.py`, shared by the style profile and the
  pacing review.

Schema stays at 19; pacing reads existing records only.

## [0.6.1] — 2026-11-20

Style analysis and deviations against the project's Style Guide.

### Added

- **Style** view and `GET /api/projects/{id}/style`: a deterministic profile of
  the stored manuscript — chapters, words, sentences, average and longest
  sentence, paragraphs with dialogue, and long sentences — per chapter and in
  total, counted locally with no model.
- The Style Guide is numbered into citable rules (`S1`, `S2`…): one rule per
  paragraph, with a short heading line labelling the paragraph under it. A guide
  that is a single paragraph becomes one rule, and a heading with no text under
  it still becomes a rule of its own.
- **Check deviations** per chapter and `POST /api/chapters/{id}/style-check`: one
  read-only inference compares a saved chapter with those rules. A deviation is
  kept only when it cites a supplied rule and quotes the chapter exactly once (at
  most 300 characters); the server attaches the guide's own words, clamps the
  aspect and severity, drops duplicates, and returns at most six. Nothing is
  written.
- Refusals before inference: no Style Guide, an empty chapter, a chapter over
  12,000 characters, or no model.

### Fixed

- A one-word chapter now prints “1 word” instead of “1 words” in Markdown, plain
  text, Word, and the manuscript summary.

Schema stays at 19; style analysis reads existing records only.

## [0.6.0] — 2026-11-20

Manuscript export: Markdown, plain text, and Word, all generated locally.

### Added

- **Word (.docx) export** built from stored prose with no document library and no
  network access: a small WordprocessingML package with title, heading, and word
  count styles. `GET /api/projects/{id}/export?format=docx` returns the file as
  an attachment; Markdown and text still return JSON for preview and copy.
- **Part breaks**: a non-empty chapter part prints once, where it starts
  (`# Part One` in Markdown, an upper-case line in text, a Heading 1 in Word).
- **Word counts**: each chapter heading is followed by its own count, and the
  manuscript opens with a chapter and word total. Counts come from the stored
  per-chapter `word_count`, so no prose is recounted differently from the app.
- The optional document appendix now applies to Word as well as Markdown; plain
  text still omits it, as before.
- The Export view offers Word alongside Markdown and plain text and links
  straight to the generated `.docx`.

Schema stays at 19; export reads existing records only.

## [0.5.8] — 2026-11-20

Provenance on every continuity finding.

### Added

- Each canon record handed to a check now carries a **kind** (character state,
  relationship, event, story bible) and, where it has one, its **chapter**:
  position and title. A relationship uses the chapter of its source event; a
  bible entry has a kind and no chapter.
- Continuity findings return `source_kind`, `source_chapter_position`, and
  `source_chapter_title` alongside the cited record, and the chapter dialog
  shows a **Provenance** line under the citation.
- Contradiction-scan findings return the same three fields for both cited
  records (`source_a_*`, `source_b_*`), so the scan dialog shows where each side
  came from rather than only its record label.
- Deterministic findings already named their chapters; nothing about them
  changed.

Schema stays at 19; provenance is derived from records that already exist.

## [0.5.7] — 2026-11-20

Canon-change review and supersession.

### Added

- Continuity gains **Canon changes**: every adjacent pair of character-state
  snapshots that differ, with the character, the two chapters, the fields that
  changed, and the values before and after. Unchanged pairs are left out.
- **Mark superseded** records that the later snapshot replaces the earlier one,
  with an optional note, or **Undo** clears the decision. The earlier record is
  never deleted or rewritten; it stays in the ledger marked *superseded* with
  the chapter that replaced it and the note.
- A superseded snapshot is excluded from the canon a continuity check (and the
  contradiction scan) may cite, so a replaced fact is no longer treated as
  current canon. Everything else — the ledger, the review list, the record
  itself — keeps its full provenance.
- `GET /api/projects/{id}/supersessions` returns `counts` and `changes`;
  `PUT /api/projects/{id}/supersessions` sets or clears the decision. Marking
  twice updates the note rather than adding a second decision.

### Migrations

- Schema 19 adds `canon_supersessions`, unique per project, record kind, and
  earlier record, with `ON DELETE CASCADE` from the project.

## [0.5.6] — 2026-11-20

Contradiction detection inside recorded canon.

### Added

- Continuity gains a **Contradiction audit**, deterministic and model-free. It
  reports a pair recorded with two different relationship types (approved,
  proposed, or both) and a thread recorded as resolved in one chapter whose key
  still appears in an event from a later chapter. Each finding lists the records
  it comes from, including the resolving chapter's note and the later events.
- **Scan canon with AI** compares the recorded canon records with each other in
  one read-only inference. Every finding must cite two different supplied record
  ids, so the server can attach the real records; citations to one id, an
  unknown id, a reversed duplicate, or a finding with no summary are dropped.
- `GET /api/projects/{id}/contradictions` returns the deterministic audit with
  its counts; `POST /api/projects/{id}/contradictions/scan` returns the cited
  findings. Neither writes anything, so no canon record changes.
- The audit treats a deliberate re-raise as the author's call: it reports the
  conflict and says to reopen the thread or record the aftermath, and changes
  nothing itself.

Schema stays at 18; every result is derived from records that already exist.

## [0.5.5] — 2026-11-20

Relationship evolution, recorded chapter by chapter.

### Added

- **Suggest relationships** in the chapter editor. One inference reads the saved
  chapter against the character roster (names and aliases) and the recorded
  relationships, and proposes how a pair of characters now stands: a type from
  the existing list and one sentence about the current state.
- The server resolves every proposed name to a real character, orders the pair,
  and drops unknown names, a character paired with itself, duplicates, and
  proposals with no description. The chapter text is refused over 12,000
  characters rather than clipped.
- Proposals are shown with an editable type and description, and each says
  whether it creates a new relationship or updates one already recorded.
  **Apply selected** writes them and records the relationship's state for that
  chapter; applying twice in the same chapter updates that chapter's entry
  instead of duplicating it.
- The Continuity view gains **Relationship evolution**: every recorded
  relationship with its current type, description, and approval status, plus
  each chapter that recorded it and which fields changed there.
- `POST /api/chapters/{id}/relationship-proposals` proposes; `/apply` re-checks
  both characters against the project before writing. The first call writes
  nothing, so inference still cannot change canon on its own.

### Migrations

- Schema 18 adds `relationship_snapshots`, one row per relationship per chapter,
  unique on that pair, with `ON DELETE CASCADE` from the relationship and the
  chapter. Existing relationships keep no history until a chapter records one.

## [0.5.4] — 2026-11-20

Timeline validation from author-recorded story days.

### Added

- **Story day** in the chapter editor: an optional whole number counting from the
  story start (day 0). It is stored with the chapter and returned by the chapter
  API, so chronology is recorded explicitly instead of inferred from prose.
- The Continuity view gains **Timeline validation**, composed without a model:
  how many chapters are anchored, the elapsed days between anchors, and a
  finding for any chapter whose story day runs backwards from the chapter before
  it. A deliberate flashback is the author's call, so the finding names both
  chapters and days without changing anything.
- `GET /api/projects/{id}/timeline` returns `counts`, `anchors` (chapter, story
  day, elapsed since the previous anchor), and `findings`.
- Chapter create and update accept `story_day` between 0 and 1,000,000. Sending
  `null` clears the anchor; a negative or fractional value is refused.

### Migrations

- Schema 17 adds `chapters.story_day`. It is nullable, so existing chapters keep
  no anchor and are reported as unanchored rather than guessed.

## [0.5.3] — 2026-11-19

Knowledge tracking: proposed character-state updates from a chapter.

### Added

- **Suggest state updates** in the chapter editor. One inference reads the saved
  chapter against the character roster (names and aliases) and each character's
  most recent recorded state, and proposes location, status, goals, and
  knowledge changes.
- The server resolves every proposed name to a real character, dropping unknown
  names, duplicates, and proposals without any detail, and clamps each field to
  the recorded-state limits. The chapter text is refused over 12,000 characters
  rather than clipped.
- Proposals are shown with editable fields and checkboxes. **Apply selected**
  records them as snapshots for that chapter, updating an existing snapshot for
  the same character and chapter instead of duplicating it.
- `POST /api/chapters/{id}/state-proposals` proposes; `/apply` re-checks every
  character against the project before writing. Nothing is written by the first
  call, so the model still cannot change canon on its own.

Schema stays at 16.

## [0.5.2] — 2026-11-19

Plot-thread management, schema version 16.

### Added

- A recorded thread can be **resolved** from the Continuity view with an optional
  note and the chapter where it paid off, or **reopened**. The decision is
  matched case- and spacing-insensitively, so the same thread always has at most
  one decision, and resolving twice updates it instead of duplicating it.
- `PUT /api/projects/{id}/threads` sets the status. Reopening removes the
  decision; the events that raised the thread are never touched.
- The ledger now reports `status`, `note`, and the resolving chapter for each
  thread, plus an `open_threads` count, and the Continuity view shows resolved
  threads with their provenance.

### Schema

- Migration 16 adds `thread_resolutions`, unique per project and thread key, with
  `ON DELETE CASCADE` from the project and `ON DELETE SET NULL` for its chapter.

## [0.5.1] — 2026-11-19

The Continuity surface is live and deterministic.

### Added

- **Continuity** (the Phase 5 nav entry) now shows the recorded canon instead of
  a placeholder: chapter counts, the timeline with each chapter's extracted
  events, per-character state snapshots with the fields that changed at each
  chapter, and unresolved threads with the chapters that raised them. No model
  is involved.
- `GET /api/projects/{id}/continuity` composes the ledger from chapters, events,
  character states, and characters. Provenance is the chapter position and
  title; threads are matched case-insensitively and count their events.
- The ledger reports only what is stored. A character's state is unique per
  chapter (existing 409 guard), so it makes no warnings it cannot prove.

Schema stays at 15.

## [0.5.0] — 2026-11-19

First v0.5 slice: continuity checking with cited provenance.

### Added

- **Check continuity** in the chapter editor compares the saved chapter with its
  recorded canon: character-state snapshots up to that chapter, approved
  relationships, extracted events, and story bible entries. Every supplied
  record gets an id (`C1`, `C2`…).
- A finding is kept only when it cites one of those ids and quotes the chapter
  exactly once (at most 300 characters, one occurrence). Ids are replaced with
  the record's own label, so provenance is never invented by the model.
  Kind and severity are clamped to fixed lists, duplicates are dropped, and at
  most six findings are returned.
- `POST /api/chapters/{id}/continuity` is read-only and works on approved
  chapters. Without content, without any canon, or beyond 12,000 characters it
  refuses with an explanation instead of checking a partial picture.

Schema stays at 15.

## [0.4.14] — 2026-11-19

Novellire can discuss a scene plan before drafting it.

### Added

- **Discuss plan** in the chapter editor. One inference compares the saved scene
  plan with the chapter summary, documents, canon, character state, and
  retrieved memory, and asks up to five questions whose answers would change the
  prose. Duplicate and empty questions are dropped.
- Each question has an optional answer field, and **Draft with answers** passes
  the answered pairs to the scene-by-scene draft as its author instruction. The
  plan itself is never rewritten, and answers are not stored as canon.
- `POST /api/chapters/{id}/discuss` is read-only. A chapter without a scene plan
  or a plan over 6,000 characters is refused rather than clipped, and a
  malformed response is reported as a 502.

Schema stays at 15.

## [0.4.13] — 2026-11-19

A draft can be reviewed before it reaches the chapter.

### Added

- **Review draft** in the generated-draft dialog. One inference compares the
  draft with the saved scene plan, documents, canon, character state, and
  retrieved memory, and returns an overall note plus up to eight findings:
  `continuity`, `plan`, `pacing`, or `prose`.
- Every finding must quote prose that appears exactly once in the reviewed
  draft. The server drops a finding whose quote is absent, ambiguous, too long,
  or identical to its replacement, so an applied edit can only change words
  that are actually there. The model proposes text; it executes nothing.
- Applying a finding rewrites the visible draft. The chapter still changes only
  through the normal insert, so the approval lock and revision snapshot apply.
- `POST /api/chapters/{id}/review` reviews either an unsaved `draft` or the
  saved chapter text, without modifying either. Prose over the 12,000-character
  review budget is refused rather than clipped.

Schema stays at 15.

## [0.4.12] — 2026-11-19

A chapter can be drafted scene by scene from its saved plan.

### Added

- **Draft scene by scene** in the chapter editor. The saved scene plan is split
  into beats and drafted with one inference per beat, in order, each continuing
  from the end of the previous scene. The assembled text opens in the normal
  editable draft dialog, so nothing reaches the chapter until the author inserts
  it and the approval lock and revision snapshot still apply.
- `POST /api/chapters/{id}/draft-sequence`. The server owns the loop: the model
  never chooses what runs next. At most six beats per run, and each scene gets a
  fair share of the target length.
- A chapter with no scene plan, an approved chapter, an imported chapter, and a
  plan with more beats than one run drafts are refused with a clear message
  before any inference starts.

### Changed

- Inserting a draft or revision already queues background analysis, so a
  completed chapter gains memory without a separate action.

## [0.4.11] — 2026-11-19

A revision can rewrite one selected passage. Schema 15 records the passage it
came from.

### Added

- **A selected passage can be revised in place.** Select text in the Chat
  chapter pane, choose **Revise selection**, and Novellire rewrites only those
  words. The result is a new message labelled *Passage revision*; **Apply to
  passage** replaces exactly that passage and leaves the rest of the chapter
  untouched, through the normal approval-locked edit path that snapshots the
  previous prose.
- `POST /api/chat/threads/{id}/revisions` and `.../revisions/stream` accept an
  optional `source_text` with a `chapter` scope. The passage is stored on the
  reply, so it can still be applied after a reload.
- A passage that is not in the current chapter is refused before any model
  call, so a revision cannot be applied to text it did not come from.

### Changed

- A passage revision refuses `replace: true` when it is applied. It may only
  change the words it came from, never the whole chapter.

### Migrations

- Schema 15 adds `chat_messages.revision_source`. Existing messages keep an
  empty value and behave exactly as before.

## [0.4.10] — 2026-11-19

Chat can revise prose. Schema 14 records what a revision came from.

### Added

- **A reply can be revised from Chat.** The author picks a model reply, says
  what should change, and Novellire streams a complete revision as a new
  message. The original reply stays in the conversation for comparison, so
  nothing is overwritten before the author chooses.
- **A whole chapter can be revised the same way.** The revision uses fresh
  documents, retrieval, planning notes, and the chapter plan. The chapter text
  is untouched until the author inserts the revision through the normal
  approval-locked edit path, which snapshots the previous prose first.
- Revisions are labelled in the transcript with `revision_scope` (`reply` or
  `chapter`) and, for replies, `revision_of`, the reply that was revised.
- `POST /api/chat/threads/{id}/revisions` and
  `POST /api/chat/threads/{id}/revisions/stream`. The revision instruction is
  stored as an author message, and the prompt carries the exact prose to revise
  plus the current documents, memory, and planning notes.
- Plan-mode conversations, approved chapters, empty sources, and a reply
  revision with no reply to revise are refused with a clear message instead of
  generating prose that cannot be applied.

### Changed

- A revision whose source is longer than the 6,000-character budget is refused
  with a message naming the limit, instead of being clipped. A partial revision
  could otherwise be inserted over the whole chapter.

### Migrations

- Schema 14 adds `chat_messages.revision_scope` and
  `chat_messages.revision_of`. Existing messages keep empty values and behave
  exactly as before.

## [0.4.9] — 2026-11-19

Chat replies survive an interruption. Schema 13 adds reply checkpoints.

### Added

- **A streaming reply is checkpointed while it is written.** Text that has
  arrived is saved at most once per 1,200 characters or two seconds, so a
  crashed process, a closed browser, or a shutdown no longer loses a reply that
  was already on screen. Finished replies and author-stopped replies clear their
  checkpoint; a checkpoint is never shown as a message on its own.
- A conversation with an interrupted reply shows it above the composer with
  **Keep as reply** and **Discard**. Keeping stores it as a model message with
  its model and timestamp; discarding removes it.
- `GET /api/chat/threads/{id}` returns `draft` (the checkpoint, or `null`),
  `POST /api/chat/threads/{id}/draft/recover` keeps it as a message, and
  `DELETE /api/chat/threads/{id}/draft` discards it.
- A reply that fails mid-stream keeps its checkpoint, so the text produced
  before the failure can still be kept. Planning notes are not re-derived from
  recovered partial text.
- Sending a new message while an interrupted reply is unresolved is refused with
  a clear message instead of silently overwriting the checkpoint.

### Migrations

- Schema 13 adds `chat_drafts`: at most one in-progress reply per conversation,
  cascaded with its thread. Existing conversations are unaffected.

## [0.4.8] — 2026-11-19

A side-by-side chapter pane for Chat and a context drawer for its replies.
Schema goes to 12 so the retrieval behind a reply survives a reload.

### Added

- **Chapter pane.** A chapter-scoped conversation shows its chapter beside the
  messages: position, title, workflow status, word count, and the prose as it
  stands. The pane refreshes after an insert, hides behind the header button
  with the choice remembered per browser, and offers **Open in editor** for
  manual correction. Below 1080px it slides over the conversation instead of
  squeezing the feed.
- **Context drawer.** Each model reply can expand to show what retrieval gave
  it: the earlier chapters used, by position and title, and how many memory
  events were retrieved. The context is stored on the message
  (`chat_messages.context_json`), so it is still there after a reload rather
  than only in the tab that produced the reply.
- `GET /api/chat/threads/{id}` and both chat send endpoints now return
  `context` on each message: `{"chapters": [...], "events": 0}`, or `null` for
  an author message and for replies stored before schema 12.

### Migrations

- Schema 12 adds `context_json` to `chat_messages`; existing conversations keep
  their messages and gain an empty context.

## [0.4.7] — 2026-11-18

Per-conversation drafts and inserting Write replies into chapters. Schema stays
at 11.

### Added

- **Insert into chapter.** A Write-mode reply in a chapter-scoped conversation
  can be appended to the chapter or used to replace its text:
  `POST /api/chat/threads/{id}/messages/{id}/insert` with `{"replace": false}`.
  The chapter takes its normal edit path, so the previous text is snapshotted
  into revision history and the approval lock still applies: an approved chapter
  is refused until it is reopened.
- Insert is offered only for model replies in Write mode on a chapter-scoped
  conversation. Plan replies and project-wide conversations are rejected with a
  clear message, and the button is disabled with a reopen hint when the chapter
  is approved.
- After inserting, the manuscript, chapter word counts, and project tree refresh
  in place, and background analysis is queued for the changed chapter.

### Fixed

- Switching Plan/Write now reports an error instead of silently snapping back
  when the running server is older than the interface: an old server ignores the
  `mode` field, answers 200 with the unchanged thread, and the toggle used to
  follow that response without explanation.
- An unsent chat draft was stored under one global key, so text typed in one
  conversation appeared in every other one. Drafts are now keyed per
  conversation, with a separate key for a chat that does not exist yet; a draft
  is carried into the new conversation and cleared when its message is sent.

## [0.4.6] — 2026-11-18

Chat rebuilt as a focused conversation surface. Schema stays at 11.

### Changed

- The Chat screen is a full-height conversation surface: a 768px centred feed is
  the only scrolling region and the composer stays pinned to the bottom.
- Author messages are right-aligned rounded bubbles. Model replies are flush
  left and rendered as markdown — headings, lists, quotes, inline code, and
  fenced code blocks with a copy button. Markdown builds DOM nodes and never
  assigns HTML, so generated text cannot inject markup.
- The composer is a floating rounded card with an auto-expanding textarea.
  Enter sends, Shift + Enter adds a line, and there are no attachment controls.
- A segmented **Plan / Write** switch inside the composer changes the reply mode
  mid-conversation; the next reply uses the new mode. `PATCH
  /api/chat/threads/{id}` now accepts `mode`.
- One circular action button sends (up arrow) and becomes a square **Stop**
  control while a reply streams.
- Planning notes moved out of the layout into an optional panel behind the
  header button and appear only in Plan mode.
- Conversations open in a slide-over drawer, so the writing column stays clear.
- An unsent draft survives a reload through `localStorage`.

### Added

- `novellire/web/static/js/markdown.js`, a small markdown-to-DOM renderer.
- `novellire/web/static/js/views/chat.js`; the Continuity scope stays in
  `scopes.js`.

## [0.4.5] — 2026-11-18

Streamed Chat replies. Schema stays at 11.

### Added

- **Chat replies stream token by token.**
  `POST /api/chat/threads/{id}/messages/stream` returns newline-delimited JSON:
  `start` (the stored author message and thread), `delta` (text as the model
  produces it), `done` (the stored reply and updated thread), or `error`.
- `OllamaProvider.generate_stream` reads Ollama's streamed NDJSON, maps a
  mid-stream error line, reports truncation, and closes the connection. A
  provider without streaming falls back to one complete delta.
- The serialized provider holds its single-request lock for the whole stream, so
  interactive chat and background analysis still never overlap.
- **Stop** aborts the reply. The server stores the text received so far before
  the stream closes, so a stopped or interrupted reply survives a reload.
- The composer swaps **Send** for **Stop** while generating and shows a caret
  where the next token will arrive.

### Changed

- Turn preparation (validation, author message storage, prompt context) is shared
  by the blocking and streaming chat paths, and runs before the stream starts so
  a validation failure is still a normal 4xx response.
- An untitled conversation is named from its first author message as soon as that
  message is stored.

### Deferred

- Side-by-side chapter pane, context drawer, chat draft checkpoints, and inserting
  a Write-mode reply into the chapter.

## [0.4.4] — 2026-11-18

Persistent chat shell. Schema 11 adds chat threads and messages.

### Added

- **Chat** now stores project-wide or chapter-scoped conversations in SQLite.
  Threads, messages, mode, and planning notes survive a page reload.
- **Plan mode** discusses causality, continuity, and consequences without writing
  prose. A compact `<planning_notes>` block in the reply is extracted into
  editable notes for the chapter.
- **Write mode** drafts prose in the conversation. Every turn rebuilds context
  from the workspace documents, selected chapter, planning notes, retrieved
  earlier chapters and events, canon, relationships, and character state.
- Planning notes track whether they were model-maintained or author-edited. Once
  the author saves notes, later model replies cannot replace them.
- The first author message names an untitled conversation automatically.

### Changed

- Chat is no longer a placeholder scope and is included in normal navigation.
- Chat inference shares the same serialized local provider as generation and
  background analysis, so only one request runs at a time.

### Deferred

- True token streaming, reconnect-after-interrupt, chat draft checkpoints, and
  inserting a Write-mode reply directly into a chapter remain for the next slice.

## [0.4.3] — 2026-11-17

Automatic analysis for every written chapter. Schema 10 adds analysis hashes and
derived chapter insights.

### Added

- **Build chapters** now analyses every written chapter missing memory, not only
  chapters before the first Chapter Map entry.
- Saving a chapter or workspace document queues background analysis. Only one
  inference request runs at a time, including interactive generation.
- Content hashes in `analysis_state` skip chapters and documents that have not
  changed since their last successful analysis.
- Chapter analysis also extracts derived character states, locations,
  relationships, and open threads into `chapter_insights`. These are separate
  proposals and never overwrite author-controlled memory records.
- New endpoints expose analysis status and derived insights:
  `GET /api/projects/{id}/analysis/status`,
  `GET /api/projects/{id}/insights`, and
  `GET /api/chapters/{id}/insights`.
- Analysis streams per-chapter progress into the outline dialog and reports
  analysed, skipped, empty, and failed chapters.
- A chapter summary written by the author is preserved; a chapter with stored
  events is not re-extracted, so manual event edits are preserved.
- If analysis fails partway, outline creation remains saved and the dialog shows
  the failing chapter. Reopening **Build chapters** retries only missing memory.
- The outline preview now reports how many earlier chapters will be analysed.

### Changed

- Outline analysis now covers the whole manuscript; its preview reports every
  written chapter that will be analysed.
- Outline parsing and first-chapter lookup share one saved Chapter Map path.
- The outline dialog remains dismissible while analysis progress is shown.

## [0.4.2] — 2026-11-17

Outline and chapter-number foundation. Schema stays at 9.

### Added

- Chapter Map headings such as `## Chapter 1: The Missing Face` are parsed into
  an ordered outline. Body text below each heading becomes that chapter's scene
  plan. A map may continue after existing chapters: with fourteen chapters
  written, a map starting at Chapter 15 creates Chapters 15 onward and leaves the
  earlier chapters untouched.
- **Build chapters** previews the detected outline and creates only the missing
  chapter records. Existing chapters, including authored prose and titles, are
  never deleted or overwritten.
- **Add chapter** accepts an optional chapter number. Importing at an existing
  position shifts later chapters down and keeps numbering contiguous.
- The model settings and drafting dialog now offer a **16,384-token** context
  window, with 8k retained as the low-resource default.
- Prompt budgets now scale with the selected context window. Output tokens and
  system/instruction space are reserved first, then documents, canon, and
  retrieved memory receive larger shares as the window grows.

### Changed

- Chapter outline sync is additive and idempotent: applying the same Chapter Map
  twice creates nothing the second time.
- Outline numbering must be contiguous without gaps or duplicates. A map may
  start above 1 only when existing chapters reach the chapter immediately before
  it.

## [0.4.1] — 2026-11-17

Chapter planning. Schema stays at 9.

### Added

- The chapter editor exposes an editable scene plan alongside the summary and
  chapter text.
- **Plan with AI** builds a scene-by-scene plan from the chapter summary,
  existing plan, workspace documents, and retrieved narrative memory. The
  result is editable and is not saved until the author chooses **Use plan**.
- The saved scene plan is included in the writing prompt as a **Chapter plan**
  block, so Draft with AI follows the author's intended beat sequence.
- `POST /api/chapters/{id}/plan` records the planning attempt in generation
  history, like prose generation.

### Deferred

- Sequential scene-by-scene drafting and automatic chapter assembly.

## [0.4.0] — 2026-11-17

Chapter approval boundary. Schema stays at 9.

### Added

- The chapter editor exposes workflow status: planned, drafting, drafted, or
  approved.
- Approved chapters lock their prose. Changing text requires the same request
  to reopen the chapter by setting another status, so AI insertion, manual
  replacement, and revision restore cannot silently overwrite approved text.
- Approved chapters hide **Draft with AI**; History still compares revisions,
  but restore is disabled with a reopen warning.
- API regression coverage for reopening before text edits and before restoring
  an older revision.

## [0.3.8] — 2026-11-17

Revision history hardening and comparison. Schema stays at 9.

### Added

- History compares each revision with the current editor text in two columns,
  highlighting removed and added words. Large rewrites fall back to
  whole-passage highlighting instead of building an unbounded diff table.
- Revision history keeps the newest 50 snapshots per chapter. Older snapshots
  are pruned in the same transaction that records a new one.
- Restore is disabled while the editor has unsaved text, so a restore cannot
  silently discard the author's current draft.
- The pre-edit snapshot is written before the chapter update, matching restore
  ordering, so a successful content change cannot be saved without history.

### Changed

- Revision detail lookup is scoped to its chapter:
  `GET /api/chapters/{id}/revisions/{revision_id}` replaces
  `GET /api/chapter-revisions/{revision_id}`.

## [0.3.7] — 2026-11-16

Chapter revision history. Schema 9 adds `chapter_revisions`.

### Added

- Saving changed chapter text automatically snapshots the previous version with
  its title, word count, source, and timestamp. Identical saves and empty
  initial text do not create snapshots.
- The chapter editor has a **History** dialog with timestamps, word counts,
  lazy-loaded full text previews, and restore. Restoring first snapshots the
  current text, so every restore can be undone from history.
- `GET /api/chapters/{id}/revisions`, `GET /api/chapter-revisions/{id}`, and
  `POST /api/chapters/{id}/revisions/{id}/restore`.

### Deferred

- Revision pruning or a revision-count limit.
- Revision labels, comparisons, and an approval workflow for drafts.

## [0.3.6] — 2026-11-16

Narrative state memory. Schema 8 adds `character_states`.

### Added

- Author-recorded character state snapshots tied to a chapter and character,
  with location, status, goals, and knowledge fields.
- One snapshot per character/chapter. The latest chapter position is current;
  earlier snapshots remain as history.
- Memory shows each character's current snapshot plus expandable earlier history,
  with record, edit, and delete controls.
- `GET/POST /api/projects/{id}/character-states`,
  `PATCH /api/character-states/{id}`, and
  `DELETE /api/character-states/{id}`.
- Current state for selected character profiles is included in generation context
  as a **Current character state** prompt block.

### Fixed

- Deleting a chapter no longer silently cascades its authored character-state
  snapshots. Chapter deletion is blocked until those snapshots are removed.

### Deferred

- Automatic state extraction or inference from prose/events.
- Character knowledge timelines and belief tracking beyond the authored snapshot.

## [0.3.5] — 2026-11-16

Approved relationship records now reach generation context. Schema stays at 7.

### Added

- Approved relationship records are included in the generation prompt when at
  least one of their characters is selected for the context, with the type and
  author note. At most six records are included in a 1,200-character block.
- Proposed and rejected records never enter context. Derived co-occurrence
  associations remain excluded.
- The prompt labels the block **Approved character relationships** and the system
  prompt names approved relationships as reference material.

## [0.3.4] — 2026-11-16

Typed, author-approved relationship records. Schema 7 adds
`character_relationships`.

### Added

- Relationship records are typed (ally, rival, family, mentor, romantic, debt,
  other), stored between two canonical, project-scoped characters.
- Every record starts as `proposed`. Authors can approve, reject, reopen, edit,
  or delete it; only approved records count as canon.
- Optional source event and chapter provenance is preserved, including the
  event summary and narrative chapter position.
- `GET/POST /api/projects/{id}/relationship-records`,
  `PATCH /api/relationship-records/{id}`,
  `PATCH /api/relationship-records/{id}/status`, and
  `DELETE /api/relationship-records/{id}`.
- Memory separates **Recorded** relationships from **Derived** associations.
  Derived rows can prefill a typed record with their latest event as provenance;
  manual records are also supported.
- `/api/meta` exposes the relationship type vocabulary used by the UI.

### Deferred

- Automatic relationship-type inference.
- Injecting approved relationship records into generation context.

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
