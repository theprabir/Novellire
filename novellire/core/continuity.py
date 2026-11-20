"""Continuity check: a saved chapter against recorded, cited canon.

Every canon record supplied to the model gets a short id (``C1``, ``C2``…), and
a finding is kept only when it cites one of those ids and quotes the chapter
exactly once. The server replaces each id with the record's own label, so a
finding can never claim provenance the project does not hold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    ProjectNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_continuity_prompt
from ..storage.event_repository import EventRepository
from ..storage.relationship_repository import RelationshipRepository
from ..storage.relationship_snapshot_repository import RelationshipSnapshotRepository
from ..storage.repositories import ProjectRepository
from ..storage.state_repository import CharacterStateRepository
from ..storage.story_repositories import (
    ChapterRepository,
    CharacterRepository,
    StoryBibleRepository,
)
from ..storage.thread_repository import ThreadResolutionRepository
from .threads import thread_key
from .settings_service import GenerationSettings

CONTINUITY_SOURCE_CHARS = 12_000
CONTINUITY_MAX_FINDINGS = 6
CONTINUITY_MAX_OUTPUT_TOKENS = 900
CONTINUITY_QUOTE_CHARS = 300
CONTINUITY_EXPLANATION_CHARS = 600
CONTINUITY_KINDS = (
    "character",
    "knowledge",
    "timeline",
    "location",
    "relationship",
    "object",
    "world",
    "plot",
    "other",
)
CONTINUITY_SEVERITIES = ("critical", "high", "medium", "low")
_MAX_STATES = 16
_MAX_RELATIONSHIPS = 10
_MAX_EVENTS = 10
_MAX_BIBLE_ENTRIES = 8

_FALLBACK_EXPLANATION = "Contradicts the cited canon record."
_LEDGER_FIELDS = ("location", "status", "goals", "knowledge")


@dataclass(frozen=True)
class CanonReference:
    id: str
    label: str


@dataclass(frozen=True)
class ContinuityFinding:
    id: int
    kind: str
    severity: str
    quote: str
    source_id: str
    source: str
    explanation: str
    suggestion: str


@dataclass(frozen=True)
class ContinuityReport:
    findings: tuple[ContinuityFinding, ...]
    canon_count: int
    model: str


class ContinuityCheckService:
    """Compare one saved chapter with the project's recorded canon."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        characters: CharacterRepository,
        states: CharacterStateRepository,
        relationships: RelationshipRepository,
        events: EventRepository,
        bible: StoryBibleRepository,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._characters = characters
        self._states = states
        self._relationships = relationships
        self._events = events
        self._bible = bible

    def check(self, chapter_id: int, *, settings: GenerationSettings) -> ContinuityReport:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            raise InvalidInputError("That chapter no longer exists.")
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        draft = (chapter.content or "").strip()
        if not draft:
            raise InvalidInputError(
                "Write or draft this chapter before checking its continuity."
            )
        if len(draft) > CONTINUITY_SOURCE_CHARS:
            raise InvalidInputError(
                f"This chapter is {len(draft):,} characters, more than one "
                f"continuity check can carry ({CONTINUITY_SOURCE_CHARS:,}). "
                "Check it chapter by chapter instead."
            )
        references = self._canon(chapter.project_id, chapter.position)
        if not references:
            raise InvalidInputError(
                "Record character state, approve a relationship, extract events, "
                "or add story bible entries before checking continuity."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError("Choose a model before checking continuity.")

        system_prompt, user_prompt = build_continuity_prompt(
            project_name=project.name,
            genre=project.genre,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            references="\n".join(
                f"{reference.id}: {reference.label}" for reference in references
            ),
            draft=draft,
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.2,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 500), CONTINUITY_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        findings = parse_continuity_payload(result.text, draft, references)
        return ContinuityReport(
            findings=tuple(findings),
            canon_count=len(references),
            model=result.model or model,
        )

    def _canon(self, project_id: int, position: int) -> list[CanonReference]:
        names = {
            character.id: character.name
            for character in self._characters.list_for_project(project_id)
        }
        chapter_rows = {
            chapter.id: chapter
            for chapter in self._chapters.list_for_project(project_id)
        }
        labels: list[str] = []

        states = [
            state
            for state in self._states.list_for_project(project_id)
            if (chapter := chapter_rows.get(state.chapter_id)) is not None
            and chapter.position <= position
        ]
        for state in states[-_MAX_STATES:]:
            chapter = chapter_rows[state.chapter_id]
            details = "; ".join(
                part
                for part in (
                    f"location: {state.location}" if state.location else "",
                    f"status: {state.status}" if state.status else "",
                    f"goals: {state.goals}" if state.goals else "",
                    f"knowledge: {state.knowledge}" if state.knowledge else "",
                )
                if part
            )
            labels.append(
                f"Character state · {names.get(state.character_id, 'Unknown')} · "
                f"chapter {chapter.position} “{chapter.title}” · {details}"
            )

        for relationship in self._relationships.list_for_project(project_id):
            if relationship.status != "approved":
                continue
            labels.append(
                "Approved relationship · "
                f"{names.get(relationship.character_a_id, 'Unknown')} and "
                f"{names.get(relationship.character_b_id, 'Unknown')} · "
                f"{relationship.relation_type} · {relationship.description}"
            )
            if sum(1 for label in labels if label.startswith("Approved")) >= (
                _MAX_RELATIONSHIPS
            ):
                break

        events = [
            event
            for event in self._events.list_for_project(project_id)
            if event.chapter_position <= position
        ]
        for event in events[-_MAX_EVENTS:]:
            threads = "; ".join(event.threads)
            labels.append(
                f"Event · chapter {event.chapter_position} "
                f"“{event.chapter_title}” · {event.summary}"
                + (f" · threads: {threads}" if threads else "")
            )

        for entry in self._bible.list_for_project(project_id)[:_MAX_BIBLE_ENTRIES]:
            labels.append(
                f"Story bible · {entry.category} · {entry.title} · "
                f"{_clip(entry.content, 300)}"
            )

        return [
            CanonReference(id=f"C{index}", label=label)
            for index, label in enumerate(labels, start=1)
        ]


class ContinuityLedgerService:
    """Compose the recorded timeline, knowledge, and threads for inspection.

    Deterministic: it reads stored records only, never the model. The ledger is
    what the author checks against, so it shows provenance rather than verdicts.
    """

    def __init__(
        self,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        characters: CharacterRepository,
        states: CharacterStateRepository,
        relationships: RelationshipRepository,
        events: EventRepository,
        threads: ThreadResolutionRepository,
        relationship_snapshots: RelationshipSnapshotRepository,
    ) -> None:
        self._projects = projects
        self._chapters = chapters
        self._characters = characters
        self._states = states
        self._relationships = relationships
        self._events = events
        self._threads = threads
        self._relationship_snapshots = relationship_snapshots

    def ledger(self, project_id: int) -> dict[str, object]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        chapters = self._chapters.list_for_project(project_id)
        chapter_rows = {chapter.id: chapter for chapter in chapters}
        characters = self._characters.list_for_project(project_id)
        names = {character.id: character.name for character in characters}
        events = self._events.list_for_project(project_id)
        events_by_chapter: dict[int, list] = {}
        for event in events:
            events_by_chapter.setdefault(event.chapter_id, []).append(event)

        timeline = [
            {
                "id": chapter.id,
                "position": chapter.position,
                "title": chapter.title,
                "status": chapter.status,
                "word_count": chapter.word_count,
                "events": [
                    {
                        "id": event.id,
                        "summary": event.summary,
                        "threads": list(event.threads),
                    }
                    for event in events_by_chapter.get(chapter.id, [])
                ],
            }
            for chapter in chapters
        ]

        states = self._states.list_for_project(project_id)
        grouped: dict[int, list] = {}
        for state in sorted(
            states,
            key=lambda item: (
                chapter_rows[item.chapter_id].position
                if item.chapter_id in chapter_rows
                else 0,
                item.id,
            ),
        ):
            grouped.setdefault(state.character_id, []).append(state)
        character_ledger = []
        for character_id in sorted(grouped, key=lambda item: names.get(item, "")):
            previous: dict[str, str] = {}
            snapshots = []
            for state in grouped[character_id]:
                chapter = chapter_rows.get(state.chapter_id)
                current = {
                    "location": state.location,
                    "status": state.status,
                    "goals": state.goals,
                    "knowledge": state.knowledge,
                }
                changed = [
                    field
                    for field in _LEDGER_FIELDS
                    if current[field] != previous.get(field, "")
                ]
                previous = current
                snapshots.append(
                    {
                        "chapter_position": chapter.position if chapter else 0,
                        "chapter_title": chapter.title if chapter else "",
                        **current,
                        "changed": changed,
                    }
                )
            character_ledger.append(
                {
                    "character_id": character_id,
                    "name": names.get(character_id, "Unknown"),
                    "snapshots": snapshots,
                }
            )

        threads: dict[str, dict[str, object]] = {}
        for event in events:
            chapter = chapter_rows.get(event.chapter_id)
            for thread in event.threads:
                key = thread.casefold()
                entry = threads.setdefault(
                    key, {"thread": thread, "chapters": [], "event_count": 0}
                )
                entry["event_count"] = int(entry["event_count"]) + 1
                if chapter is not None and all(
                    row["position"] != chapter.position for row in entry["chapters"]
                ):
                    entry["chapters"].append(
                        {"position": chapter.position, "title": chapter.title}
                    )
        resolutions = {
            resolution.thread_key: resolution
            for resolution in self._threads.list_for_project(project_id)
        }
        for key, entry in threads.items():
            resolution = resolutions.get(thread_key(str(entry["thread"])))
            entry["status"] = "resolved" if resolution else "open"
            entry["note"] = resolution.note if resolution else ""
            entry["resolved_chapter"] = (
                {
                    "position": resolution.chapter_position,
                    "title": resolution.chapter_title,
                }
                if resolution is not None and resolution.chapter_position is not None
                else None
            )
        thread_rows = sorted(
            threads.values(),
            key=lambda item: (
                item["chapters"][0]["position"] if item["chapters"] else 0,
                str(item["thread"]).casefold(),
            ),
        )

        relationship_rows = []
        snapshots_by_relationship: dict[int, list] = {}
        for snapshot in self._relationship_snapshots.list_for_project(project_id):
            snapshots_by_relationship.setdefault(
                snapshot.relationship_id, []
            ).append(snapshot)
        for record in self._relationships.list_for_project(project_id):
            if record.status == "rejected":
                continue
            previous: dict[str, str] | None = None
            history = []
            for snapshot in snapshots_by_relationship.get(record.id, []):
                current = {
                    "relation_type": snapshot.relation_type,
                    "description": snapshot.description,
                }
                changed = (
                    list(current)
                    if previous is None
                    else [
                        field_name
                        for field_name in current
                        if current[field_name] != previous.get(field_name, "")
                    ]
                )
                previous = current
                history.append(
                    {
                        "chapter_position": snapshot.chapter_position,
                        "chapter_title": snapshot.chapter_title,
                        **current,
                        "changed": changed,
                    }
                )
            relationship_rows.append(
                {
                    "relationship_id": record.id,
                    "character_a_name": record.character_a_name,
                    "character_b_name": record.character_b_name,
                    "relation_type": record.relation_type,
                    "description": record.description,
                    "status": record.status,
                    "history": history,
                }
            )
        relationship_rows.sort(
            key=lambda item: (
                str(item["character_a_name"]).casefold(),
                str(item["character_b_name"]).casefold(),
            )
        )

        return {
            "counts": {
                "chapters": len(chapters),
                "events": len(events),
                "states": len(states),
                "threads": len(thread_rows),
                "open_threads": sum(
                    1 for row in thread_rows if row["status"] == "open"
                ),
                "relationships": len(relationship_rows),
                "relationship_changes": sum(
                    len(row["history"]) for row in relationship_rows
                ),
            },
            "timeline": timeline,
            "characters": character_ledger,
            "threads": thread_rows,
            "relationships": relationship_rows,
        }


def parse_continuity_payload(
    text: str, draft: str, references: list[CanonReference]
) -> list[ContinuityFinding]:
    """Keep findings that quote the draft once and cite a supplied record."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError(
            "The model did not return a continuity JSON object."
        )
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError("The model returned invalid continuity JSON.") from exc
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an unexpected continuity structure."
        )

    by_id = {reference.id.casefold(): reference for reference in references}
    findings: list[ContinuityFinding] = []
    seen: set[tuple[str, str]] = set()
    items = data.get("findings")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        quote = _raw_text(item.get("quote"))
        if not quote or len(quote) > CONTINUITY_QUOTE_CHARS:
            continue
        if draft.count(quote) != 1:
            continue
        source_id = _raw_text(item.get("source")).strip("[]").upper()
        reference = by_id.get(source_id.casefold())
        if reference is None:
            continue
        key = (reference.id, quote)
        if key in seen:
            continue
        seen.add(key)
        kind = _raw_text(item.get("kind")).casefold()
        severity = _raw_text(item.get("severity")).casefold()
        findings.append(
            ContinuityFinding(
                id=len(findings) + 1,
                kind=kind if kind in CONTINUITY_KINDS else "other",
                severity=(
                    severity if severity in CONTINUITY_SEVERITIES else "medium"
                ),
                quote=quote,
                source_id=reference.id,
                source=reference.label,
                explanation=(
                    _clip(item.get("explanation"), CONTINUITY_EXPLANATION_CHARS)
                    or _FALLBACK_EXPLANATION
                ),
                suggestion=_clip(item.get("suggestion"), CONTINUITY_EXPLANATION_CHARS),
            )
        )
        if len(findings) >= CONTINUITY_MAX_FINDINGS:
            break
    return findings


def _raw_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clip(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
