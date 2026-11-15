# PROJECT_SPEC.md

## Novellire — Local-First AI Narrative Intelligence & Novel Writing Environment

* **Project Codename:** Novellire
* **Version:** 0.1.0 — Initial Product Specification
* **Status:** Architecture and development planning
* **License:** To be determined
* **Primary Platform:** Windows 11
* **Architecture:** Modular monolith
* **Primary Inference Runtime:** Ollama

---

### 1. Product Overview

#### 1.1 What is Novellire?
Novellire is a local-first AI-powered writing environment and LLM orchestration harness specifically designed for long-form fiction. It enables authors to plan, generate, revise, and manage novels with complex plots, interconnected characters, extensive world-building, historical timelines, emotional development, and long-range narrative dependencies.

Unlike conventional chatbot interfaces, Novellire maintains an independent, persistent representation of the entire fictional universe. Its primary innovation is automatic narrative relationship discovery and dynamic context construction.

An author should be able to request:

> *"Write Chapter 20."*

Novellire must independently determine what information from the existing narrative is relevant, regardless of whether that information originated in Chapter 1, Chapter 4, Chapter 13, or Chapter 19. The author must not manually identify historical chapters or explain every narrative connection—Novellire handles retrieval, memory assembly, generation, and continuity validation.

#### 1.2 Core Philosophy
> The LLM generates the prose. Novellire remembers, understands, organizes, and protects the narrative.

The system should remain model-independent and should not rely on any individual LLM's native memory capabilities.

#### 1.3 Target Audience
* Fiction writers
* Novelists
* Science-fiction authors
* Fantasy authors
* Historical-fiction writers
* Romance writers
* World-building enthusiasts
* AI-assisted creative writers
* Local LLM enthusiasts

#### 1.4 Supported Fiction Categories
The architecture should support:
* Science fiction
* Fantasy
* Historical fiction
* Romance
* Metaphysical fiction
* Mystery and thriller
* Literary fiction
* Philosophical fiction
* Multi-generational narratives
* Nonlinear storytelling
* Multiple protagonists and viewpoints
* Complex interconnected fictional universes

---

### 2. Product Objectives

The primary objectives are:
* Enable chapter-by-chapter AI-assisted novel generation.
* Maintain long-range narrative continuity.
* Automatically discover relationships between narrative events.
* Maintain persistent character knowledge and state.
* Track chronology and historical consistency.
* Preserve world-building and metaphysical rules.
* Provide dynamic narrative context retrieval.
* Support human-guided revision and canon approval.
* Support local inference without mandatory cloud services.
* Operate on low-resource consumer hardware.
* Support multiple local LLMs through a provider abstraction.
* Provide reliable project persistence and recovery.

---

### 3. Core Product Requirements

#### 3.1 Project Management
Users must be able to:
* Create multiple novel projects.
* Open existing projects.
* Rename and archive projects.
* Configure project metadata.
* Define genre and narrative style.
* Define target word count.
* Define chapter and scene structures.
* Import existing planning materials.
* Export complete projects.
* Back up and restore projects.

> **Note:** Each project must maintain independent narrative memory.

#### 3.2 Story Bible Management
The application must support structured story documentation. The story bible acts as the authoritative source for established world information.

**Required categories:**
* Overall premise
* Main storyline
* Subplots
* Themes
* Narrative structure
* World-building
* Historical background
* Geography
* Technology
* Metaphysical rules
* Cultural systems
* Important objects
* Organizations
* Locations
* Terminology

#### 3.3 Character Management
Each character should have a structured profile containing:
* Unique ID
* Name
* Aliases
* Physical description
* Age or age range
* Personality
* Motivations
* Goals
* Fears
* Strengths
* Weaknesses
* Background
* Secrets
* Relationships
* Character arc
* Current narrative status

> **Constraint:** Character information must distinguish between immutable identity information and evolving narrative state.

#### 3.4 Chapter and Scene Management
Users must be able to:
* Create chapters.
* Define chapter objectives.
* Organize chapters into acts or parts.
* Divide chapters into scenes.
* Specify required plot developments.
* Specify viewpoint characters.
* Define emotional objectives.
* Define target word counts.
* Generate individual scenes.
* Generate complete chapters through sequential scene generation.
* Edit and regenerate scenes.
* Preserve previous versions.

> **Note:** The chapter map should be treated as a narrative blueprint rather than merely a list of chapter titles.

---

### 4. Narrative Intelligence Engine

The Narrative Intelligence Engine is the defining subsystem of Novellire. It is responsible for understanding the current writing request and discovering relevant information from the entire existing narrative. The author must not be responsible for manually connecting chapters.

#### 4.1 Automatic Narrative Relationship Discovery
When a user requests a chapter, Novellire must:

1. Read the relevant chapter blueprint.
2. Extract entities, concepts, narrative requirements, and constraints.
3. Identify relevant characters, locations, objects, events, and themes.
4. Search the entire narrative knowledge base.
5. Discover direct and indirect relationships.
6. Retrieve relevant historical events.
7. Retrieve character and relationship states.
8. Retrieve relevant world-building rules.
9. Identify unresolved narrative threads.
10. Rank retrieved information.
11. Build a context package.
12. Send the package to the writing model.

> **Constraint:** Retrieval must not depend on manually specified chapter references.

#### 4.2 Retrieval Scope
Retrieval must be global within the project. Relevant information may originate from:
* Any previous chapter
* Any previous scene
* Character profiles
* World-building documents
* Historical documents
* Previously approved continuity records
* Relevant author-provided notes

Retrieval should support indirect relationships and conceptually related events.

**Example Workflow:**
* **Chapter 3:** Introduces an artifact.
* **Chapter 6:** Reveals its origin.
* **Chapter 9:** Establishes its importance to the antagonist.
* **Chapter 14:** Reveals its metaphysical significance.
* **Chapter 20:** Revisits the artifact.

The system should discover these relationships without explicit instructions from the user.

#### 4.3 Narrative Relationship Types
Initial relationship categories should include:
* `APPEARED_IN`
* `INTRODUCED_IN`
* `PARTICIPATED_IN`
* `KNOWS_ABOUT`
* `DISCOVERED`
* `REVEALED`
* `CAUSED`
* `RESULTED_IN`
* `LOCATED_AT`
* `BELONGS_TO`
* `RELATED_TO`
* `CONFLICTS_WITH`
* `FORESHADOWS`
* `REFERENCES`
* `SUPPRESSED`
* `SUPERSEDES`

Relationship types should be extensible, and every relationship must preserve its source and verification status.

#### 4.4 Narrative Dependency Graph
Novellire should maintain a logical graph of interconnected narrative entities. Edges represent established or proposed relationships.

**Node types:**
* Character
* Event
* Location
* Object
* Organization
* Historical fact
* World rule
* Relationship
* Mystery
* Plot thread
* Chapter
* Scene

The initial implementation should use SQLite relational tables to represent this graph—a dedicated graph database is not required. Graph traversal must support finding indirect relationships between entities.

---

### 5. Narrative Memory Architecture

Memory is independent of the LLM's context window. The initial architecture contains four memory categories.

#### 5.1 Canon Memory
Stores approved, relatively stable narrative truths. Canon must preserve provenance, and a generated statement must not automatically become canonical.

**Examples:**
* Character biographies
* World-building rules
* Historical facts
* Established metaphysical principles
* Geographic information
* Important object properties
* Approved character relationships

#### 5.2 Episodic Memory
Stores what happens throughout the narrative. Each record must reference its source chapter and scene.

**Each chapter and scene may produce:**
* Summary
* Important events
* Characters involved
* Locations
* Objects
* Revelations
* Dialogue-related developments
* Emotional developments
* Consequences
* Unresolved threads

#### 5.3 Narrative State Memory
Stores the current fictional-world state. State changes must preserve historical snapshots, and the system must distinguish current state from historical state.

**Examples:**
* Character location
* Character status
* Character knowledge
* Character beliefs
* Emotional state
* Relationships
* Possessions
* Injuries
* Current goals
* Active conflicts
* Current timeline position

#### 5.4 Retrieval Memory
Provides searchable access to the narrative knowledge base.

**Initial implementation:**
* SQLite FTS5
* Structured SQL retrieval
* Entity-based lookup
* Relationship traversal
* Chapter and scene metadata
* Keyword and alias matching

> **Note:** Later implementation may add semantic retrieval using embeddings. Semantic indexing must be optional and resource-aware.

---

### 6. Narrative Knowledge and Character Epistemology

A particularly important requirement is tracking what each character knows. This feature is essential for mysteries, unreliable narrators, secrets, dramatic irony, and suspense.

**The system must distinguish:**
* Objective narrative truth
* Character knowledge
* Character beliefs
* Character misconceptions
* Deliberately concealed information
* Information known only to the author
* Information revealed to the reader but not to characters

> **Example:** A villain's identity may be known to the reader in Chapter 12 but remain unknown to the protagonist until Chapter 20. The system must preserve this distinction.

**Knowledge records should contain:**
* Subject character
* Known fact
* Source event
* Acquisition chapter
* Acquisition scene
* Verification status
* Confidence or uncertainty
* Visibility scope

---

### 7. Dynamic Context Construction

The context builder prepares information for every generation request. It must not blindly load the entire novel.

#### 7.1 Context Components
A generation context may contain:
* System instructions
* Project identity and genre
* Relevant writing style
* Chapter objectives
* Scene requirements
* Relevant canon facts
* Relevant character profiles
* Current character states
* Historical event references
* Relevant narrative relationships
* Timeline information
* Relevant unresolved plot threads
* Negative constraints
* Immediate preceding scene context

#### 7.2 Context Ranking
Retrieved information should be ranked using configurable relevance signals.

**Possible signals:**
* Entity match
* Relationship match
* Semantic similarity, when available
* Narrative importance
* Recency
* Explicit chapter requirements
* Character relevance
* Plot-thread relevance
* Canon priority

> **Constraint:** Recency must not automatically override historical importance. An event from Chapter 2 may be more important than an event from Chapter 19.

#### 7.3 Token Budget
The context builder must operate within a configurable token budget. Token budgeting must be model-aware and configurable.

**It should:**
* Prioritize essential information.
* Deduplicate overlapping summaries.
* Preserve critical facts.
* Avoid excessive historical detail.
* Keep source references.
* Record which memories were selected.
* Report when relevant information could not fit.

---

### 8. Writing Engine

The writing engine is responsible for prose generation.

#### 8.1 Scene Generation
Generation must happen sequentially and receive:
* Scene objectives
* Relevant narrative context
* Characters and their current states
* Required emotional progression
* Viewpoint
* Location
* Style instructions
* Continuity constraints
* Target output length

#### 8.2 Chapter Generation
A chapter should be treated as an ordered collection of scenes.

**Workflow:**
1. Read the chapter map.
2. Create or retrieve the scene plan.
3. Generate the first scene.
4. Save the result.
5. Update temporary narrative context.
6. Generate the next scene.
7. Repeat until the chapter is complete.
8. Assemble the chapter.
9. Run editorial and continuity reviews.

#### 8.3 Revision Engine
Original and revised versions must be retained, and revision must preserve established facts unless explicitly instructed otherwise.

**Users must be able to request:**
* Rewrite
* Expand
* Condense
* Improve dialogue
* Improve emotional depth
* Improve descriptive writing
* Improve pacing
* Correct stylistic deviations
* Correct continuity issues

#### 8.4 Style Engine
The style engine must maintain a persistent writing specification and support style evaluation and revision suggestions.

**It may contain:**
* Narrative perspective
* Tense
* Sentence complexity
* Vocabulary
* Descriptive density
* Dialogue style
* Emotional intensity
* Pacing
* Literary influences supplied by the user
* Preferred stylistic devices
* Explicitly prohibited writing patterns

---

### 9. Continuity and Validation Engine

The validation engine evaluates generated content against the existing narrative.

#### 9.1 Validation Categories
* Character consistency
* Character knowledge consistency
* Timeline consistency
* Location consistency
* Relationship consistency
* Historical consistency
* World-rule consistency
* Object and possession consistency
* Plot-thread consistency
* Style compliance

#### 9.2 Validation Results
Each detected issue should contain:
* Issue identifier
* Severity
* Description
* Generated passage reference
* Conflicting source reference
* Explanation
* Suggested correction

**Severity levels:**
* Critical
* High
* Medium
* Low
* Informational

#### 9.3 Canon Conflict Resolution
The system must not automatically resolve important conflicts by overwriting established facts. Intentional retcons must be supported as explicit author actions.

**Resolution workflow:**
1. Identify the conflict.
2. Retrieve the source of the existing fact.
3. Identify the conflicting generated statement.
4. Explain the discrepancy.
5. Suggest possible resolutions.
6. Request author approval where necessary.

---

### 10. Persistence Architecture

* **Initial database:** SQLite
* **Initial search engine:** FTS5

Use normalized relational structures where practical, and use JSON columns only where flexible structured data provides a genuine benefit. Use explicit database migrations and maintain transaction safety.

**Logical entities:**
* `projects`
* `chapters`
* `scenes`
* `characters`
* `character_aliases`
* `character_states`
* `relationships`
* `locations`
* `objects`
* `events`
* `world_facts`
* `character_knowledge`
* `plot_threads`
* `memory_records`
* `memory_links`
* `generation_logs`
* `revision_history`
* `canon_changes`
* `source_references`

#### 10.1 Filesystem
The database remains the authoritative application store, while Markdown exports provide human-readable portability.

**Each project should have an exportable directory containing:**
* Story bible
* Character bible
* World-building documents
* Chapter map
* Historical timeline
* Writing style guide
* Generated chapters
* Approved continuity summaries
* Exported manuscript

---

### 11. Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Core** | Python 3.11+, SQLite, Pydantic, Pytest |
| **Inference** | Ollama, HTTP-based local inference interface |
| **UI** | Streamlit initially |
| **Document Processing** | `python-docx`, PDF extraction library, Markdown processing |
| **Prompt Management** | Jinja2 |
| **Search** | SQLite FTS5, Structured SQL queries, Optional future embeddings |

> **Future UI Possibilities:** FastAPI backend, React frontend, and dedicated desktop packaging. These are future possibilities, not mandatory dependencies for the initial release.

---

### 12. Hardware and Resource Constraints

The application must prioritize low resource consumption.

**Initial target hardware:**
* **OS:** Windows 11
* **CPU:** Intel i3-3240
* **RAM:** 8 GB DDR3 RAM (approximately 4 GB available RAM)
* **Graphics:** Integrated graphics
* **Storage:** 256 GB SSD

#### 12.1 Resource Management Requirements
* One model loaded at a time
* One generation request at a time
* No concurrent agents by default
* No unnecessary background inference
* Lazy loading of documents
* Database-backed memory
* Small context packages
* Configurable context limits
* On-demand indexing
* Lightweight UI
* Controlled output sizes

#### 12.2 Model Strategy
Model performance must be evaluated using actual narrative tasks. Model download size must not be treated as a proxy for total RAM usage, and the application must allow the user to configure models and inference parameters.

**Initial model candidates:**
* Qwen3 1.7B
* Qwen2.5 1.5B
* Llama 3.2 1B
* Gemma 3 1B

#### 12.3 Performance Goals
Do not promise a particular generation speed or RAM requirement without benchmarking.

**Metrics to measure:**
* Application idle RAM
* Peak application RAM
* Ollama process RAM
* Model loading time
* Prompt processing time
* Generation speed
* Retrieval latency
* Database size
* Context size

---

### 13. Reliability, Security, and Recovery

#### Reliability
* The system must preserve generated drafts and support recovery after interruption.
* Important operations must be transactional.
* Generation logs must preserve model identifiers, prompt versions, and relevant settings.

#### Recovery
Provide:
* Automatic project backups
* Database integrity checks
* Restore functionality
* Revision history
* Recovery of interrupted writing sessions
* Markdown manuscript exports

#### Security
* Localhost-only defaults
* No silent cloud calls
* No execution of generated code
* Imported content treated as untrusted
* Prompt injection resistance
* No sensitive project content in public logs
* Git ignore rules for private projects and model files

---

### 14. User Interface

The initial Streamlit interface should provide the following sections:

#### Dashboard
* Project overview
* Word count
* Chapter progress
* Recent activity
* Model status
* System resource indicators

#### Project Workspace
* Story bible
* Character database
* World-building
* Historical timeline
* Chapter map

#### Writing Workspace
* Chapter selection
* Scene selection
* Writing instructions
* Generation settings
* Generated prose editor
* Revision controls
* Save and approval actions

#### Memory Explorer
* Search narrative memory
* Browse characters
* Browse events
* Inspect source chapters
* View relationships
* Inspect character knowledge
* View narrative state

#### Continuity Inspector
* Timeline warnings
* Character inconsistencies
* Knowledge conflicts
* Canon conflicts
* Unresolved plot threads

#### Settings
* Model selection
* Context settings
* Generation parameters
* Memory retrieval settings
* Backup settings
* Application preferences

---

### 15. Development Roadmap

#### Phase 1 — Foundation (`v0.1`)
* Repository initialization
* Python environment
* Ollama provider
* Model configuration
* Basic Streamlit interface
* Project creation and persistence
* Basic text generation

> **Acceptance Criterion:** A user can create a project, connect to Ollama, generate text, and save it.

#### Phase 2 — Narrative Data (`v0.2`)
* Story bible management
* Character profiles
* Chapter and scene structures
* SQLite schema
* Document import
* Event extraction
* Chapter summaries

> **Acceptance Criterion:** A project can store and retrieve structured narrative information.

#### Phase 3 — Narrative Memory (`v0.3`)
* Canon memory
* Episodic memory
* Narrative state
* FTS5 search
* Entity matching
* Relationship discovery
* Dynamic context construction

> **Acceptance Criterion:** The system can retrieve relevant information from arbitrary earlier chapters without manual chapter references.

#### Phase 4 — Writing Harness (`v0.4`)
* Chapter planning
* Scene generation
* Sequential chapter writing
* Revision workflow
* Draft history
* Approval workflow

> **Acceptance Criterion:** A user can request an entire chapter and have Novellire generate it scene by scene using automatically retrieved narrative context.

#### Phase 5 — Continuity Intelligence (`v0.5`)
* Character knowledge tracking
* Relationship evolution
* Timeline validation
* Contradiction detection
* Plot-thread management
* Provenance tracking
* Canon change management

> **Acceptance Criterion:** The application can identify deliberately planted continuity violations in a test narrative.

#### Phase 6 — Editorial and Export System (`v0.6`)
* Style analysis
* Pacing review
* Repetition detection
* Revision suggestions
* DOCX export
* Markdown export
* Backup and restore

> **Acceptance Criterion:** A completed manuscript can be reviewed, exported, and restored.

#### Phase 7 — Stable Release (`v1.0`)
* UI refinement
* Documentation
* Installation guide
* Configuration system
* Performance optimization
* Test coverage
* Synthetic benchmark dataset
* Release packaging

> **Acceptance Criterion:** A user can independently install Novellire, create a project, import an existing novel blueprint, generate chapters, maintain continuity, and export the manuscript.

---

### 16. Benchmarking and Evaluation

Novellire must be evaluated on more than prose generation quality. Maintain deterministic tests for database and retrieval logic, and keep LLM-based evaluations separated from deterministic correctness tests.

**Create synthetic narrative datasets containing:**
* Multiple characters
* Multiple aliases
* Interconnected events
* Nonlinear timelines
* Hidden information
* Long-range plot dependencies
* Conflicting statements
* Unresolved mysteries

#### Retrieval Quality
* Recall of relevant historical events
* Precision of retrieved information
* Ability to identify indirect relationships
* Correct source attribution

#### Continuity Quality
* Character knowledge accuracy
* Timeline consistency
* Character-state accuracy
* Canon conflict detection
* Plot-thread consistency

#### Generation Quality
* Instruction adherence
* Style adherence
* Character voice consistency
* Repetition
* Narrative coherence

#### Performance
* RAM consumption
* CPU utilization
* Retrieval latency
* Generation latency
* Storage overhead

---

### 17. Future Features

These features are intentionally outside the initial implementation scope. Do not implement these prematurely.

**Potential future additions:**
* Semantic vector retrieval
* Optional knowledge graph visualization
* Multiple inference providers
* More sophisticated narrative dependency analysis
* Automatic foreshadowing detection
* Narrative pacing visualization
* Character relationship graphs
* Multiple writing styles and genre profiles
* Optional local embedding models
* Advanced editorial workflows
* Desktop application packaging
* Plugin architecture
* Multiple-language writing support

---

### 18. Non-Goals

Novellire is not initially intended to be:
* A generic autonomous AI agent
* A cloud-based writing subscription service
* A general-purpose chatbot
* A fully autonomous author that makes unapproved canon changes
* A multi-agent system running several models concurrently
* A replacement for human literary judgment
* A heavyweight distributed application

---

### 19. Definition of Product Success

Novellire succeeds when an author can manage a large, complex fictional universe without manually maintaining every connection between chapters.

**The defining demonstration:**
> An author requests a chapter late in a novel. Novellire automatically identifies relevant events from arbitrary earlier chapters, retrieves their source information, understands current narrative states, constructs a suitable context package, generates the chapter, and validates its consistency with established canon.

The author does not need to remember where every detail originated. The application remembers.

---

### 20. Final Product Principle

> **Novellire — Where stories remember themselves.**

A long-form narrative is not merely a sequence of chapters. It is a network of characters, events, relationships, memories, consequences, secrets, and ideas.

Novellire exists to preserve and intelligently navigate that network while giving authors the freedom to concentrate on storytelling.
