"""Sequential analysis of written chapters into derived memory.

Author-owned memory is preserved: a chapter with a summary keeps it, stored
events are not re-extracted, and chapter insights live in their own derived
table. Content hashes let the scheduler skip chapters that have not changed.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ..errors import NovellireError
from ..storage.analysis_repository import (
    AnalysisStateRepository,
    ChapterInsightRepository,
)
from ..storage.event_repository import EventRepository
from .chapters import ChapterService
from .events import EventExtractionService
from .insights import ChapterInsightService
from .settings_service import GenerationSettings
from .summaries import ChapterSummaryService
from .text import content_hash


@dataclass(frozen=True)
class ChapterAnalysisStep:
    chapter_id: int
    title: str
    position: int
    status: str  # analysed | skipped | empty | failed
    detail: str = ""
    duration_ms: int | None = None


class ChapterAnalysisService:
    """Fill missing summary, event, and derived-insight memory for a project."""

    def __init__(
        self,
        summaries: ChapterSummaryService,
        events: EventExtractionService,
        insights: ChapterInsightService,
        chapters: ChapterService,
        event_repository: EventRepository,
        insight_repository: ChapterInsightRepository,
        state_repository: AnalysisStateRepository,
    ) -> None:
        self._summaries = summaries
        self._events = events
        self._insights = insights
        self._chapters = chapters
        self._event_repository = event_repository
        self._insight_repository = insight_repository
        self._state_repository = state_repository

    def analyze_project(
        self,
        project_id: int,
        settings: GenerationSettings,
        *,
        force: bool = False,
    ) -> Iterator[ChapterAnalysisStep]:
        for chapter in self._chapters.list_chapters(project_id):
            common = {
                "chapter_id": chapter.id,
                "title": chapter.title,
                "position": chapter.position,
            }
            if not chapter.content.strip():
                yield ChapterAnalysisStep(
                    **common, status="empty", detail="No chapter text to analyse."
                )
                continue

            digest = content_hash(chapter.content)
            state = self._state_repository.get(
                project_id, "chapter", str(chapter.id)
            )
            if (
                not force
                and state is not None
                and state.content_hash == digest
                and state.status == "completed"
            ):
                yield ChapterAnalysisStep(
                    **common,
                    status="skipped",
                    detail="Unchanged since last analysis.",
                )
                continue

            self._state_repository.mark(
                project_id, "chapter", str(chapter.id), digest, "running"
            )
            has_summary = bool(chapter.summary.strip())
            has_events = bool(self._event_repository.list_for_chapter(chapter.id))
            insight = self._insight_repository.get_for_chapter(chapter.id)
            needs_insight = insight is None or insight.content_hash != digest
            if has_summary and has_events and not needs_insight:
                self._state_repository.mark(
                    project_id, "chapter", str(chapter.id), digest, "completed"
                )
                yield ChapterAnalysisStep(
                    **common,
                    status="skipped",
                    detail="Summary, events, and insights already exist.",
                )
                continue

            actions: list[str] = []
            duration_ms = 0
            try:
                if not has_summary:
                    outcome = self._summaries.summarize(chapter.id, settings)
                    duration_ms += outcome.duration_ms
                    actions.append("summary")
                if not has_events:
                    outcome = self._events.extract(chapter.id, settings)
                    duration_ms += outcome.duration_ms
                    actions.append("events")
                if needs_insight:
                    outcome = self._insights.extract(chapter.id, settings)
                    duration_ms += outcome.duration_ms
                    actions.append("insights")
            except NovellireError as error:
                self._state_repository.mark(
                    project_id,
                    "chapter",
                    str(chapter.id),
                    digest,
                    "failed",
                    str(error),
                )
                yield ChapterAnalysisStep(
                    **common,
                    status="failed",
                    detail=str(error),
                    duration_ms=duration_ms or None,
                )
                return

            detail = "Added " + " and ".join(actions) + "."
            self._state_repository.mark(
                project_id,
                "chapter",
                str(chapter.id),
                digest,
                "completed",
                detail,
            )
            yield ChapterAnalysisStep(
                **common,
                status="analysed",
                detail=detail,
                duration_ms=duration_ms,
            )
