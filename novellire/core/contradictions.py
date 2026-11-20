"""Contradictions inside recorded canon: deterministic audit plus one read.

Two passes share the same read-only shape. The audit compares records that must
agree structurally (one pair cannot hold two different relationship types, and a
thread resolved in one chapter cannot be raised later as unresolved); it never
calls a model. The scan compares the canon records with each other in one
inference, and every finding must cite two different records the project holds,
so a finding cannot claim provenance that does not exist. Neither pass writes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..errors import InvalidInputError, LLMResponseError, ProjectNotFoundError
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_canon_contradiction_prompt
from ..storage.event_repository import EventRepository
from ..storage.relationship_repository import RelationshipRepository
from ..storage.repositories import ProjectRepository
from ..storage.thread_repository import ThreadResolutionRepository
from .continuity import CanonReference, ContinuityCheckService
from .settings_service import GenerationSettings
from .threads import thread_key

SCAN_MAX_FINDINGS = 6
SCAN_MAX_OUTPUT_TOKENS = 900
SCAN_DETAIL_CHARS = 600
SCAN_KINDS = (
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
SCAN_SEVERITIES = ("critical", "high", "medium", "low")
# Every chapter position is below this, so the scan sees the whole project.
_ALL_CHAPTERS = 1_000_000
_MAX_SOURCES = 4


@dataclass(frozen=True)
class ContradictionFinding:
    id: int
    kind: str
    severity: str
    summary: str
    detail: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class CanonContradiction:
    id: int
    kind: str
    severity: str
    source_a: str
    source_b: str
    source_a_label: str
    source_b_label: str
    summary: str
    detail: str
    suggestion: str


@dataclass(frozen=True)
class ContradictionScanResult:
    findings: tuple[CanonContradiction, ...]
    canon_count: int
    model: str


class ContradictionAuditService:
    """Deterministic checks over records that must agree with each other."""

    def __init__(
        self,
        projects: ProjectRepository,
        relationships: RelationshipRepository,
        events: EventRepository,
        threads: ThreadResolutionRepository,
    ) -> None:
        self._projects = projects
        self._relationships = relationships
        self._events = events
        self._threads = threads

    def audit(self, project_id: int) -> dict[str, object]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        records = [
            record
            for record in self._relationships.list_for_project(project_id)
            if record.status != "rejected"
        ]
        findings: list[ContradictionFinding] = []

        pairs: dict[tuple[int, int], list] = {}
        for record in sorted(records, key=lambda item: item.id):
            pairs.setdefault(
                (record.character_a_id, record.character_b_id), []
            ).append(record)
        for rows in pairs.values():
            types = sorted({row.relation_type for row in rows})
            if len(rows) < 2 or len(types) < 2:
                continue
            findings.append(
                ContradictionFinding(
                    id=len(findings) + 1,
                    kind="conflicting_relationships",
                    severity="high",
                    summary=(
                        f"{rows[0].character_a_name} and "
                        f"{rows[0].character_b_name} are recorded as both "
                        f"{' and '.join(types)}."
                    ),
                    detail=(
                        "Two recorded relationships describe the same pair with "
                        "different types. Keep the one that is true and reject "
                        "or delete the other."
                    ),
                    sources=tuple(
                        f"Relationship #{row.id} · {row.relation_type} · "
                        f"{row.status}"
                        + (f" · {row.description}" if row.description else "")
                        for row in rows
                    ),
                )
            )

        events = self._events.list_for_project(project_id)
        resolutions = [
            resolution
            for resolution in self._threads.list_for_project(project_id)
            if resolution.chapter_position is not None
        ]
        for resolution in resolutions:
            later = [
                event
                for event in events
                if event.chapter_position > resolution.chapter_position
                and any(
                    thread_key(thread) == resolution.thread_key
                    for thread in event.threads
                )
            ]
            if not later:
                continue
            findings.append(
                ContradictionFinding(
                    id=len(findings) + 1,
                    kind="thread_after_resolution",
                    severity="medium",
                    summary=(
                        f"“{resolution.thread}” is recorded as resolved in "
                        f"chapter {resolution.chapter_position} but is raised "
                        "again later."
                    ),
                    detail=(
                        "A later event still carries this thread. If it is the "
                        "same unresolved question, reopen the thread; if the "
                        "later mention is aftermath, the resolution note should "
                        "say so."
                    ),
                    sources=(
                        f"Resolution · chapter {resolution.chapter_position} "
                        f"“{resolution.chapter_title}”"
                        + (f" · {resolution.note}" if resolution.note else ""),
                        *(
                            f"Event · chapter {event.chapter_position} "
                            f"“{event.chapter_title}” · {event.summary}"
                            for event in later[:_MAX_SOURCES]
                        ),
                    ),
                )
            )

        return {
            "counts": {
                "relationships": len(records),
                "thread_resolutions": len(resolutions),
                "findings": len(findings),
            },
            "findings": [asdict(finding) for finding in findings],
        }


class ContradictionScanService:
    """One read-only inference that compares the canon records with each other."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        continuity: ContinuityCheckService,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._continuity = continuity

    def scan(
        self, project_id: int, *, settings: GenerationSettings
    ) -> ContradictionScanResult:
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        references = self._continuity.canon_records(project_id, _ALL_CHAPTERS)
        if len(references) < 2:
            raise InvalidInputError(
                "Record at least two canon facts — character state, an approved "
                "relationship, an extracted event, or a story bible entry — "
                "before scanning for contradictions."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before scanning canon for contradictions."
            )

        system_prompt, user_prompt = build_canon_contradiction_prompt(
            project_name=project.name,
            references="\n".join(
                f"{reference.id}: {reference.label}" for reference in references
            ),
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.2,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 500), SCAN_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        return ContradictionScanResult(
            findings=tuple(
                parse_canon_contradictions(result.text, references)
            ),
            canon_count=len(references),
            model=result.model or model,
        )


def parse_canon_contradictions(
    text: str, references: list[CanonReference]
) -> list[CanonContradiction]:
    """Keep contradictions that cite two different supplied records."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError(
            "The model did not return a contradiction JSON object."
        )
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(
            "The model returned invalid contradiction JSON."
        ) from exc
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an unexpected contradiction structure."
        )

    by_id = {reference.id.casefold(): reference for reference in references}
    findings: list[CanonContradiction] = []
    seen: set[tuple[str, str]] = set()
    items = data.get("findings")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        first = by_id.get(_raw(item.get("source_a")).strip("[]").casefold())
        second = by_id.get(_raw(item.get("source_b")).strip("[]").casefold())
        if first is None or second is None or first.id == second.id:
            continue
        pair = tuple(sorted((first.id, second.id)))
        if pair in seen:
            continue
        summary = _clip(item.get("summary"), SCAN_DETAIL_CHARS)
        if not summary:
            continue
        seen.add(pair)
        kind = _raw(item.get("kind")).casefold()
        severity = _raw(item.get("severity")).casefold()
        findings.append(
            CanonContradiction(
                id=len(findings) + 1,
                kind=kind if kind in SCAN_KINDS else "other",
                severity=severity if severity in SCAN_SEVERITIES else "medium",
                source_a=first.id,
                source_b=second.id,
                source_a_label=first.label,
                source_b_label=second.label,
                summary=summary,
                detail=_clip(item.get("detail"), SCAN_DETAIL_CHARS),
                suggestion=_clip(item.get("suggestion"), SCAN_DETAIL_CHARS),
            )
        )
        if len(findings) >= SCAN_MAX_FINDINGS:
            break
    return findings


def _raw(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clip(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
