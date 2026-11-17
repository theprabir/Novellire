"""Sequential analysis of chapters that precede a Chapter Map outline.

This is deliberately conservative about author-owned memory. A chapter with a
summary keeps it; a chapter with stored events keeps them. Only missing memory is
derived, one inference request at a time. A failure stops the run so a stopped
Ollama or missing model does not repeat the same error for every chapter.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ..errors import NovellireError
from ..storage.event_repository import EventRepository
from .chapters import ChapterService
from .events import EventExtractionService
from .settings_service import GenerationSettings
from .summaries import ChapterSummaryService


@dataclass(frozen=True)
class ChapterAnalysisStep:
    chapter_id: int
    title: str
    position: int
    status: str  # analysed | skipped | empty | failed
    detail: str = ""
    duration_ms: int | None = None


class ChapterAnalysisService:
    """Fill missing summary and event memory for chapters before an outline."""

    def __init__(
        self,
        summaries: ChapterSummaryService,
        events: EventExtractionService,
        chapters: ChapterService,
        event_repository: EventRepository,
    ) -> None:
        self._summaries = summaries
        self._events = events
        self._chapters = chapters
        self._event_repository = event_repository

    def analyze_before_position(
        self,
        project_id: int,
        before_position: int,
        settings: GenerationSettings,
    ) -> Iterator[ChapterAnalysisStep]:
        for chapter in self._chapters.list_chapters(project_id):
            if chapter.position >= before_position:
                continue
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

            has_summary = bool(chapter.summary.strip())
            has_events = bool(self._event_repository.list_for_chapter(chapter.id))
            if has_summary and has_events:
                yield ChapterAnalysisStep(
                    **common,
                    status="skipped",
                    detail="Summary and events already exist.",
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
            except NovellireError as error:
                yield ChapterAnalysisStep(
                    **common,
                    status="failed",
                    detail=str(error),
                    duration_ms=duration_ms or None,
                )
                return
            yield ChapterAnalysisStep(
                **common,
                status="analysed",
                detail="Added " + " and ".join(actions) + ".",
                duration_ms=duration_ms,
            )
