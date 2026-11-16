"""Generate and store chapter summaries for project memory."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    NovellireError,
    ProjectNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_chapter_summary_prompt
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRecord
from .chapters import ChapterService
from .settings_service import GenerationSettings

SUMMARY_CHAR_LIMIT = 12_000
SUMMARY_MAX_OUTPUT_TOKENS = 400

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryOutcome:
    chapter: ChapterRecord
    model: str
    duration_ms: int


@dataclass(frozen=True)
class SummaryStep:
    """One chapter's outcome in a bulk summary run."""

    chapter_id: int
    title: str
    position: int
    status: str  # summarised | skipped | empty | failed
    detail: str = ""
    duration_ms: int | None = None


class ChapterSummaryService:
    """Summarise chapter prose and save the result on the chapter."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterService,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters

    def summarize(
        self, chapter_id: int, settings: GenerationSettings
    ) -> SummaryOutcome:
        chapter = self._chapters.require_chapter(chapter_id)
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )

        content = chapter.content.strip()
        if not content:
            raise InvalidInputError(
                "Add chapter text before generating a summary."
            )

        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before summarising. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )

        system_prompt, user_prompt = build_chapter_summary_prompt(
            project_name=project.name,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            content=content[:SUMMARY_CHAR_LIMIT],
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.2,
                top_p=settings.top_p,
                num_predict=min(max(settings.num_predict, 200), SUMMARY_MAX_OUTPUT_TOKENS),
                context_window=settings.context_window,
            )
        )

        summary = result.text.strip()
        if not summary:
            raise LLMResponseError(
                "The model returned an empty summary. Try again with a larger model."
            )

        updated = self._chapters.update_chapter(chapter_id, summary=summary)
        return SummaryOutcome(
            chapter=updated,
            model=result.model or model,
            duration_ms=result.duration_ms,
        )

    def summarize_pending(
        self, project_id: int, settings: GenerationSettings
    ) -> Iterator[SummaryStep]:
        """Summarise each chapter in order, one inference request at a time.

        Chapters that already have a summary and chapters without text are
        reported but not sent to the model. The run stops at the first inference
        failure so a missing model or stopped Ollama does not repeat the same
        error for every remaining chapter.
        """
        for chapter in self._chapters.list_chapters(project_id):
            common = {
                "chapter_id": chapter.id,
                "title": chapter.title,
                "position": chapter.position,
            }
            if chapter.summary.strip():
                yield SummaryStep(
                    **common, status="skipped", detail="Already has a summary."
                )
                continue
            if not chapter.content.strip():
                yield SummaryStep(
                    **common, status="empty", detail="No chapter text to summarise."
                )
                continue
            try:
                outcome = self.summarize(chapter.id, settings)
            except NovellireError as error:
                logger.warning(
                    "Bulk summary stopped at chapter %s: %s", chapter.id, error
                )
                yield SummaryStep(**common, status="failed", detail=str(error))
                return
            yield SummaryStep(
                **common,
                status="summarised",
                duration_ms=outcome.duration_ms,
            )
