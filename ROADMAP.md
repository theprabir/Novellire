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
- Never delete chapters or overwrite existing chapter prose during outline sync.
- Add optional chapter number when adding/importing a chapter; insert and reorder.
- Add 16,384-token context selection while keeping 8k as the low-resource default.
- Keep schema at version 9; no destructive migration is required.

Acceptance: a Chapter Map with twelve entries creates twelve chapters; importing
a chapter at number seven places it at position seven; 16k is selectable.

### v0.4.3 — Automatic analysis and memory

- Add a sequential analysis job queue with content hashes and retry status.
- Saving a document or chapter schedules analysis after the save succeeds.
- Analyses: chapter summary, events, character-state proposals, locations,
  relationships, open threads, and document-derived canon.
- Store provenance and derived/manual status. Manual records are protected.
- Replace the Memory inspector with the compact four-section UI.
- Preserve work when Ollama is unavailable and expose a clear retry action.

Acceptance: saving a chapter produces memory without manual buttons; unchanged
content is skipped; manual edits survive re-analysis.

### v0.4.4 — Chat shell and context assembly

- Persistent project and chapter-scoped chat threads.
- Plan and Write modes.
- Stored, editable planning notes maintained after planning exchanges.
- Write mode rebuilds context from documents, notes, chapter, and retrieval.
- Streaming from Ollama with stop and reconnect support.
- Large chat layout with side-by-side chapter view and context drawer.
- Draft checkpoints survive interruption.

Acceptance: a planning discussion survives a page reload as compact notes; Write
mode starts from fresh context and streams prose into the chapter pane.

### v0.4.5 — Agentic writing and revision

- Bounded orchestration: discuss, plan, draft scene by scene, assemble, review,
  revise.
- The server validates model-proposed actions; the model never executes tools.
- Whole-chapter and last-response revision; selected-text revision follows.
- Automatic analysis after draft completion.
- Approval remains the final lock on prose.

Acceptance: the author can plan, write, revise, and approve a complete chapter in
Chat while memory updates automatically.

### v0.5 — Continuity intelligence

- Timeline validation.
- Character knowledge tracking.
- Relationship evolution.
- Contradiction detection.
- Plot-thread management.
- Canon-change review and supersession.
- Provenance display for every continuity finding.

Acceptance: a synthetic manuscript with planted contradictions produces the
expected findings.

### v0.6 — Editorial and export

- Style analysis and deviations.
- Pacing and repetition review.
- Revision suggestions.
- DOCX and Markdown export.
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
