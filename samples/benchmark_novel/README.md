# Synthetic benchmark novel — *The Salt Cartographer*

A deterministic 27-chapter manuscript used to measure retrieval and continuity
without a model. Everything here is invented for testing; it is not a sample of
finished prose.

## What is planted

| Feature | Where | Why it matters |
| :--- | :--- | :--- |
| A detail that matters much later | Chapter 2 hides a **brass astrolabe** beneath the **third stair**; chapter 27 returns for it | Retrieval must reach back 25 chapters, not just the recent ones |
| Multiple characters and aliases | Ilse Marrow (*the Salt Surveyor*), Tamsin Roke (*Tam*, *the Ledger Girl*), Brann Ocque (*the Tidewarden*), Sera Vane (*the Gull*), Keeper Noll (*the Lampwright*) | Alias-aware character selection |
| A secret | Ilse knows who cut the lighthouse lens; Tamsin believes it was the storm | Knowledge stays with the character who holds it |
| An unresolved mystery | “Who cut the lighthouse lens?” is raised in chapters 6 and 26 | The ledger must keep it open, not resolve it |
| A location change | Ilse moves from Cinder Point lighthouse (chapter 1) to the flooded archive of Veyra (chapter 12) | State snapshots show the change with provenance |
| A planted contradiction | Ilse and Brann are recorded as both `ally` (approved) and `rival` (proposed) | The deterministic audit reports it |
| Unreliable narration | Chapter 2 hides the instrument; chapter 27 admits she knew where to look | The draft can conflict with recorded state |

The prose is controlled so the probes are measurable: `brass` and `astrolabe`
appear only in chapter 2 (and the current chapter 27), `flooded`/`archive` only
in chapters 12, 13, and 19, and `gull`/`ledger` only in chapters 9, 12, and 18.

## Files

- `blueprint/` — the four workspace documents, named by document kind
  (`master_bible`, `character_bible`, `chapter_map`, `style_guide`).
- `chapters/` — one Markdown file per chapter, headed `# {number}. {title}`.
- `annotations.json` — characters, aliases, secrets, state snapshots,
  relationships, events, and the retrieval probes with their expected chapters.
- `build.py` — the single source of truth. Edit it and rerun
  `python samples/benchmark_novel/build.py` to regenerate everything.

## Probes and expected results

| Probe | Query | Expected source chapters |
| :--- | :--- | :--- |
| `astrolabe` | “The brass astrolabe.” | 2 |
| `flooded_archive` | “The flooded archive.” | 12, 13, 19 |
| `gull_ledger` | “Gull ledger.” | 9, 12, 18 |

`tests/test_benchmark.py` seeds this project through the real services and
asserts recall 1.0, precision 1.0, and mean reciprocal rank 1.0 for all three
probes, then checks the ledger (open mystery, location change, knowledge) and
the planted contradiction. A stub provider supplies the continuity finding, so
the suite stays fully offline.

To import the sample by hand, create a project in Novellire and paste each
`blueprint/*.md` into the matching document, then add each chapter with its
number and text.
