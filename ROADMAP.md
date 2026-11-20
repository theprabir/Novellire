# Novellire Roadmap

This roadmap replaces the earlier feature-by-feature plan. The goal is one simple
author flow, not a collection of disconnected panels.

## Product Flow

1. The author creates a project and writes four documents:
   Master Story Bible, Character Bible, Chapter Map, and Style Guide.
2. Saving or editing a document schedules analysis. Novellire parses the Chapter
   Map, extracts canon and characters, and updates derived memory with provenance.
3. The author previews the chapter outline and creates the blank chapter records
   from the Chapter Map. Existing authored chapters are never deleted or
   overwritten by this sync.
4. The author imports a pre-written chapter with an explicit chapter number.
   Novellire inserts it at that position and analyses its prose.
5. The author writes in Chat. Chat is chapter-scoped, large, and paired with a
   side-by-side chapter view.
6. Every completed chapter, whether imported or AI-written, updates memory:
   summary, events, character state, locations, relationships, and open threads.
7. The author approves a chapter when it is done. Approval locks its prose until
   it is explicitly reopened.

## Chat Modes

### Plan mode

Plan mode is for decisions, not prose. It may use the Chapter Map, scene plan,
documents, previous chapters, and retrieved memory.

After each planning exchange, Novellire maintains compact **planning notes** for
the selected chapter:

- decisions made;
- constraints and continuity requirements;
- character and location choices;
- unresolved questions;
- the intended scene sequence.

The notes are stored with the chapter/thread and are editable by the author. Raw
chat history is never the only copy of a decision.

### Write mode

Write mode drafts or revises prose. Switching to Write mode deliberately rebuilds
the prompt instead of carrying a long conversation:

1. Reload project documents.
2. Reload the Chapter Map entry and the saved planning notes.
3. Retrieve relevant earlier chapters, events, character states, and relationships.
4. Add current chapter prose and the author's latest instruction.
5. Generate.

This prevents a long planning conversation from silently falling out of the
model's context window. The chat transcript remains visible to the author; the
model receives the compact stored notes plus fresh retrieval.

### Mode rules

- Plan mode never modifies chapter prose.
- Write mode never relies only on earlier chat messages.
- AI-derived planning notes are shown to the author before they influence prose.
- Only one inference request runs at a time.
- Approved chapters cannot be written into until reopened.

## Target UI

Navigation: **Write · Outline · Read · Memory · Settings**.

- **Write:** chat on the left, selected chapter on the right, chapter selector in
  the header, collapsible history, context drawer, stop and revise controls.
- **Outline:** documents, detected chapter outline, chapter list, import with
  chapter number, and apply-outline preview.
- **Read:** manuscript reading and export.
- **Memory:** four compact sections (Story, Characters, Timeline, Open threads),
  search, and a review queue for AI-derived proposals. No nested inspector by
  default.
- **Settings:** model, 16k context option, appearance, backup.

The existing chapter editor remains available for manual correction and pasted
text, but it is no longer the primary writing surface.

## Milestones

### v0.4.2 — Outline and numbering foundation

- Parse Markdown-style Chapter Map headings into ordered chapter entries.
- Preview detected chapters and create missing blank chapter records.
- Allow a Chapter Map to continue after existing chapters, so a map starting at
  Chapter 15 works when Chapters 1–14 already exist.
- Never delete chapters or overwrite existing chapter prose during outline sync.
- Add optional chapter number when adding/importing a chapter; insert and reorder.
- Add 16,384-token context selection while keeping 8k as the low-resource default.
- Scale document and retrieved-memory prompt budgets with the selected window,
  reserving output and system/instruction space first.
- Keep schema at version 9; no destructive migration is required.

Acceptance: a Chapter Map with twelve entries creates twelve chapters; importing
a chapter at number seven places it at position seven; 16k is selectable.

### v0.4.3 — Automatic analysis and memory

Implemented:

- Every written chapter missing memory is analysed sequentially.
- Chapter and document saves queue background analysis.
- Content hashes skip unchanged chapters and documents.
- Missing summaries and episodic events are generated; existing author summaries
  and stored events are preserved.
- Character-state, location, relationship, and open-thread proposals are stored
  separately from author-controlled records.
- Per-chapter progress streams into the outline dialog.
- Failures stop the run without losing created chapters, and retrying fills only
  missing memory.

Remaining:

- Surface derived insight proposals in the Memory review queue rather than only
  through the API.
- Replace the Memory inspector with the compact four-section UI.
- Add a persistent retry queue for failures while Ollama is unavailable.

Acceptance: saving a chapter produces memory without manual buttons; unchanged
content is skipped; manual edits survive re-analysis.

### v0.4.4 — Chat shell and context assembly

Implemented first slice:

- Persistent project- and chapter-scoped chat threads and messages in SQLite.
- Plan and Write modes, selected when a conversation starts.
- Plan replies propose compact planning notes; notes remain editable, and an
  author edit locks them against later model replacement.
- Write mode rebuilds context from documents, notes, chapter, retrieval, canon,
  relationships, and character state on every turn.
- Chat uses the serialized local provider, so it cannot overlap another
  inference request.
- Replies stream token by token from Ollama; **Stop** stores the partial reply so
  it survives a reload.
- Chat is a full-height conversation surface with a Plan/Write switch inside the
  composer, and unsent drafts are stored per conversation.
- A Write-mode reply can be inserted into its chapter (append or replace) through
  the normal chapter edit path, so the approval lock and revision history apply.
- The selected chapter sits in a side-by-side pane that refreshes after an
  insert, with the pane preference remembered per browser.
- Every reply carries an expandable context drawer: the earlier chapters and
  memory events retrieval gave it, stored with the message (schema 12).
- A reply is checkpointed while it streams (schema 13). A crash, a closed
  browser, or a shutdown leaves the partial text above the composer, where the
  author keeps it as a message or discards it.

Acceptance: a planning discussion survives a page reload as compact notes; Write
mode starts from fresh context and streams prose into the chapter pane.

### v0.4.5 — Agentic writing and revision

Implemented first slice:

- Whole-chapter and last-response revision in Chat. A revision is a new message
  with its source recorded (schema 14); the prose it came from is never
  overwritten, and applying a revision goes through the approval-locked chapter
  edit path with its revision snapshot.
- Revision prompts rebuild fresh context from documents, planning notes, the
  chapter plan, retrieval, character state, and relationships.
- Prose longer than the 6,000-character revision budget is refused rather than
  clipped, so a partial revision can never replace a whole chapter.
- Selected-text revision: a passage selected in the chapter pane is revised on
  its own (schema 15) and applied back only to that passage, so a long chapter
  can be improved one piece at a time.
- Scene-by-scene drafting from the saved scene plan: one sequential inference
  per beat, each continuing from the previous scene, assembled into one editable
  draft (at most six beats a run). The server owns the loop.
- Inserting a draft or revision already queues automatic analysis, so completed
  prose gains memory without a separate action.
- Server-owned review pass: one structured inference compares a draft with its
  plan, documents, canon, character state, and retrieved memory. Only findings
  that quote the draft exactly once are kept, and applying one rewrites the
  draft, never the chapter; the model proposes text and executes nothing.
- Pre-draft discussion: one inference asks up to five questions the plan leaves
  undecided, the author answers what matters, and those answers become the draft
  instruction. The plan is not rewritten and answers are not stored as canon.

Remaining:

- Broader model-proposed actions beyond review findings (outline changes,
  approvals, reordering), all validated server-side before anything runs.
- Approval remains the final lock on prose.

Acceptance: the author can plan, write, revise, and approve a complete chapter in
Chat while memory updates automatically.

### v0.5 — Continuity intelligence

- Continuity check of a saved chapter against cited canon: character state,
  approved relationships, events, and story bible, with provenance for every
  finding (`0.5.0`).
- Deterministic continuity ledger in the Continuity view: recorded chapter
  timeline, per-character state changes, and unresolved thread provenance, all
  read-only and without inference (`0.5.1`).
- Plot-thread management: resolve a recorded thread with a note and the chapter
  where it paid off, or reopen it; the ledger reports open/resolved with
  provenance (`0.5.2`).
- Character knowledge tracking: propose location, status, goals, and knowledge
  updates from a finished chapter, review them field by field, and apply them as
  snapshots (`0.5.3`).
- Timeline validation: an optional story day per chapter, and a deterministic
  Continuity check that reports a chapter running backwards in recorded story
  time without treating a flashback as an error (`0.5.4`).
- Relationship evolution: propose how a pair of characters now stands from a
  finished chapter, apply the reviewed change, and record each chapter's
  relationship state so the ledger shows how it changed (`0.5.5`).
- Contradiction detection: a deterministic audit of conflicting relationship
  types and threads raised after resolution, plus a read-only inference that
  compares canon records and must cite two of them (`0.5.6`).
- Canon-change review and supersession: review changed state snapshots, mark an
  earlier record superseded by a later one with a note, and stop citing it as
  current canon while keeping it as history (`0.5.7`).
- Provenance display for every continuity finding: a cited canon record names
  its kind and source chapter, and a contradiction finding shows both
  (`0.5.8`).

Acceptance: a synthetic manuscript with planted contradictions produces the
expected findings.

### v0.6 — Editorial and export

- Style analysis and deviations: a deterministic profile of the stored prose
  (sentences, average and longest sentence, dialogue, long sentences), the Style
  Guide numbered into cited rules, and a read-only per-chapter deviation check
  (`0.6.1`).
- Pacing and repetition review: paragraph and sentence rhythm, dialogue density,
  and four-word phrases repeated three or more times with their source sentences,
  all measured locally without inference (`0.6.2`).
- Revision suggestions.
- DOCX and Markdown export: Markdown, plain text, and a locally generated Word
  document, with part breaks, chapter headings, and per-chapter and total word
  counts (`0.6.0`).
- Backup/restore verification.

Acceptance: a completed manuscript can be reviewed, exported, and restored.

### v1.0 — Stable release

- UI refinement and accessibility.
- Installation and configuration documentation.
- Performance and memory profiling.
- Synthetic retrieval/continuity benchmarks.
- Release packaging and recovery testing.

Acceptance: an author can install Novellire, build an outline, import or write a
novel, maintain continuity, and export the manuscript without cloud services.

## Data and Invariants

- SQLite migrations are explicit and preserve existing project data.
- One inference request at a time by default.
- AI-derived memory is never silently promoted to author canon.
- Chapter revisions are snapshotted before prose changes.
- Outline sync is additive and idempotent.
- Chapter numbering remains contiguous after insertions and deletions.
- Context budgets scale with the selected context window; 16k is a setting, not
  a promise that the host has enough RAM.
- Manual memory edits are retained and marked author-owned.

## Immediate Next Work

The first implementation slice is v0.4.2. It is deliberately foundation work:
chapter structure, outline import, numbering, and honest context selection must
be reliable before Chat writes into chapters.
