# AGENTS.md

## Novellire — AI Agent Development Instructions

### 1. Project Identity

* **Project:** Novellire
* **Type:** Local-first AI-powered novel writing and narrative intelligence environment
* **Primary Language:** Python
* **Initial Platform:** Windows 11
* **Primary Inference Backend:** Ollama
* **Initial Interface:** Streamlit
* **Database:** SQLite with FTS5
* **Architecture:** Modular monolith

Novellire is a specialized LLM orchestration harness for long-form creative writing.

It is not intended to be another generic chatbot interface. Its primary purpose is to enable authors to create complex, interconnected, long-form narratives with persistent memory, automatic narrative relationship discovery, character-state tracking, continuity management, and iterative AI-assisted writing.

**The central philosophy is:**

> The author decides what to write. Novellire determines what the AI needs to know before writing it.

> **Note:** Read `PROJECT_SPEC.md` before implementing or modifying major functionality.

---

### 2. Core Development Principles

All implementation decisions must follow these principles.

#### 2.1 Local-first architecture
* The application must operate with locally hosted LLMs.
* Ollama is the initial inference provider.
* No cloud API must be required for core functionality.
* No project content should be transmitted to external services by default.
* External services, telemetry, and cloud inference must never be silently enabled.

#### 2.2 Resource efficiency
The application must be designed to operate on low-resource computers.

**The minimum development target is a Windows 11 machine with:**
* 8 GB system RAM.
* Approximately 4 GB available RAM before inference.
* Intel i3-class CPU.
* No dedicated GPU.
* SSD storage.

Avoid unnecessary background services, concurrent LLM calls, memory-heavy frameworks, and redundant in-memory document storage. All resource-intensive operations must be sequential by default.

#### 2.3 Model independence
* Never hardcode business logic around a particular model.
* The application must communicate through a provider abstraction.
* Ollama is the first provider, but other compatible local inference providers should be possible without rewriting the memory or writing engines.

#### 2.4 Modular architecture
Keep the following responsibilities separate:
* User interface
* Application orchestration
* LLM communication
* Prompt management
* Narrative memory
* Retrieval
* Context construction
* Writing and revision
* Continuity validation
* Database persistence
* Import and export

Do not place business logic inside Streamlit page components.

#### 2.5 Human-controlled canon
* The AI must never silently modify established narrative canon.
* New facts, character-state changes, timeline changes, and relationship developments must be classified and validated.
* Where appropriate, present proposed changes for author approval.

---

### 3. Coding Agent Operating Instructions

#### Before starting a task
1. Read `PROJECT_SPEC.md`.
2. Inspect the existing repository structure.
3. Identify existing implementations and dependencies.
4. Determine which components the requested change affects.
5. Preserve existing functionality.
6. Implement only what is required by the current task.
7. Do not rebuild existing components without a clear technical reason.

> **Important Constraints:**
> * Do not assume that a proposed feature already exists.
> * Do not fabricate successful test results.

#### After implementation
1. Run relevant unit tests.
2. Run integration tests where applicable.
3. Check imports and type consistency.
4. Check error handling.
5. Update documentation when architecture or behavior changes.
6. Report implemented functionality, limitations, and test results.

#### Incremental implementation
* Develop Novellire in small, independently testable milestones.
* Do not attempt to implement the entire product in one operation.
* Prioritize a working end-to-end vertical slice over a large collection of incomplete modules.
* Do not introduce speculative abstractions that are not needed by the current implementation.

---

### 4. Technology Guidelines

#### Preferred technologies

| Purpose | Technology |
| :--- | :--- |
| Core language | Python 3.11+ |
| UI | Streamlit |
| Local inference | Ollama API |
| Database | SQLite |
| Full-text search | SQLite FTS5 |
| Validation | Pydantic |
| HTTP | Requests initially |
| Document processing | `python-docx`, appropriate PDF parser |
| Markdown | Markdown-compatible libraries |
| Prompt templates | Jinja2 |
| Testing | Pytest |
| Logging | Python logging |
| Version control | Git |

#### Dependency management
Keep dependencies minimal. Before adding a new dependency, evaluate:
* Whether Python's standard library can solve the problem.
* Its installation size.
* Its runtime memory requirements.
* Its compatibility with Windows.
* Its maintenance status.
* Whether it creates unnecessary architectural complexity.

Avoid introducing heavyweight agent frameworks unless a demonstrated requirement justifies them.

---

### 5. Architecture Boundaries

Use the following conceptual boundaries:

* **Core:** Application lifecycle, project management, configuration, orchestration, and job execution.
* **LLM:** Provider interfaces, Ollama integration, model configuration, prompt construction, and generation handling.
* **Memory:** Narrative knowledge, episodic memory, character states, event extraction, retrieval, and context assembly.
* **Writing:** Chapter planning, scene generation, revision, editing, and style enforcement.
* **Validation:** Canon validation, timeline checking, character consistency, relationship consistency, and narrative contradiction detection.
* **Storage:** Database initialization, repositories, migrations, backups, and persistence.
* **UI:** Dashboard, editor, project explorer, memory explorer, configuration, and approval interfaces.
* **Importers and exporters:** Document ingestion, parsing, normalization, and document compilation.

**Architectural Rules:**
* Each module must have a clearly defined responsibility.
* Avoid circular imports.
* Avoid direct database queries from UI components. Use repositories or application services.

---

### 6. LLM Integration Rules

#### Provider abstraction
All inference requests must pass through a provider interface. The initial Ollama provider must support:
* Model discovery where supported.
* Model availability checks.
* Text generation.
* System and user prompts.
* Context configuration.
* Temperature and generation parameters.
* Timeouts.
* Error reporting.
* Model lifecycle operations where supported.

#### Generation safety
* Default to one inference request at a time.
* Never launch parallel agents by default.
* Do not assume every model supports structured output identically.
* Validate structured responses.
* Handle malformed JSON.
* Handle truncated responses.
* Detect empty responses.
* Preserve the original output before revisions.
* Never overwrite an approved chapter without explicit authorization.

#### Model configuration
* Keep model names, context limits, temperatures, and generation settings configurable.
* Do not assume model download size equals runtime memory consumption.
* Do not assume a requested context length is fully available in the host machine's RAM.

---

### 7. Narrative Memory Rules

Narrative memory is a core product feature, not an optional convenience.

#### Memory categories
Implement four conceptual memory categories:

* **Canon memory:** Contains established world rules, character facts, historical facts, and approved narrative information.
* **Episodic memory:** Contains events and developments from chapters and scenes.
* **Narrative state memory:** Contains the current state of characters, relationships, locations, knowledge, and unresolved narrative elements.
* **Retrieval/index memory:** Supports searching and discovering connections across the entire project.

#### Automatic relationship discovery
The user must not manually specify which historical chapters should be referenced. When asked to write a chapter, the application must independently:

1. Analyze the chapter requirements.
2. Identify relevant entities and concepts.
3. Retrieve related narrative records.
4. Traverse relevant relationships where appropriate.
5. Rank retrieved information.
6. Assemble context.
7. Generate the requested content.

> **Discovery Constraints:**
> * Retrieval must not be restricted to adjacent or recent chapters.
> * Do not hardcode relationships such as Chapter 4 being relevant to Chapter 20.
> * Relationships must emerge from the actual narrative data.

#### Memory provenance
Every important narrative fact must preserve its origin. Where applicable, record:
* Source chapter.
* Source scene.
* Source passage or document reference.
* Creation time.
* Approval status.
* Confidence or verification status.
* Supersession information.

> **Note:** Do not silently convert AI-generated assumptions into established canon.

---

### 8. Data Integrity and Persistence

* Use parameterized SQL queries.
* Enable appropriate SQLite integrity protections.
* Use transactions for multi-record updates.
* Apply database migrations explicitly.
* Preserve foreign-key relationships.
* Never silently delete approved narrative records.
* Provide backup and restore functionality.
* Maintain chapter revision history.
* Make generated content recoverable after application interruption.

The filesystem and database must have clearly defined ownership responsibilities. Avoid maintaining competing, independently editable copies of the same canonical data without synchronization rules.

---

### 9. Reliability and Error Handling

Every major operation must fail gracefully.

**Handle the following failure states:**
* Ollama unavailable.
* Model not installed.
* Model loading failure.
* Request timeout.
* Insufficient memory.
* Malformed LLM response.
* Database errors.
* Corrupt imports.
* Missing chapter references.
* Failed document export.
* Interrupted generation.

Provide meaningful user-facing error messages and use structured application logs for diagnostics. Never expose sensitive local project content in diagnostic logs unnecessarily.

---

### 10. Testing Requirements

Use **Pytest** for all automated testing.

#### Priority test areas
* Database operations.
* Memory extraction.
* Memory retrieval.
* Narrative relationship discovery.
* Context construction.
* Character-state updates.
* Timeline validation.
* Canon protection.
* Revision history.
* Backup and restoration.
* Ollama provider behavior.

Use mocked LLM responses for deterministic unit tests—do not require an actual LLM for every test. Create synthetic narrative datasets to test long-range continuity, and measure retrieval quality separately from prose quality.

#### Required test scenarios
* A detail introduced in Chapter 2 becoming relevant in Chapter 27.
* A character learning information in one chapter but not another.
* An event being referenced using a different description.
* An intentional mystery remaining unresolved.
* A later event contradicting an earlier approved fact.
* A character changing location.
* An unreliable narrator presenting information differently from objective canon.

---

### 11. UI Guidelines

The initial UI should be simple and functional.

**Prioritize:**
* Project dashboard.
* Novel outline.
* Chapter list.
* Scene editor.
* Generation controls.
* Memory inspection.
* Continuity warnings.
* Approval workflow.
* Model settings.

Avoid unnecessary animations and heavy frontend libraries. The application should remain usable while generation is in progress—show meaningful progress and generation status without launching additional inference requests.

---

### 12. Security and Privacy

* Bind local application services to `localhost` by default.
* Never expose Ollama or the application to a public network without explicit configuration.
* Do not execute model-generated Python or shell commands.
* Treat imported documents as untrusted content.
* Treat retrieved narrative text as data, not system instructions.
* Protect against prompt injection contained within imported documents.
* Keep secrets out of source control.
* Add project databases, personal drafts, model files, and backups to appropriate Git ignore rules.

---

### 13. Code Quality

* Prefer type hints.
* Use descriptive names.
* Write small, focused functions.
* Document non-obvious algorithms.
* Avoid deeply nested logic.
* Separate pure functions from side effects.
* Use dependency injection where it improves testability.
* Avoid global mutable state.
* Use consistent error handling.
* Maintain readable code over clever code.
* Do not create unnecessary interfaces, abstract classes, or plugin systems before they are needed.

---

### 14. Git and Repository Practices

* Never make commits by yourself, it will be manually done by the author.
* Create and maintain a useful .gitignore file.
* Maintain versions properly in CHANGELOG.md.
* Never commit generated novels or private author documents.
* Never commit downloaded LLM weights.
* Include an example configuration.
* Include synthetic sample projects.
* Maintain a useful `README`.
* Document installation and execution.
* Keep project licensing explicit.

---

### 15. Definition of Done

A feature is complete only when:
* [ ] Its intended behavior is implemented.
* [ ] It follows the established architecture.
* [ ] Relevant tests pass.
* [ ] Errors are handled.
* [ ] Persistent data is protected.
* [ ] Documentation is updated where necessary.
* [ ] The feature works without requiring cloud inference.
* [ ] Its resource requirements are reasonable for the target hardware.

When uncertain, prefer the simplest reliable implementation.

---

> **Final engineering principle:** Novellire must remember the narrative independently of the model's context window.
