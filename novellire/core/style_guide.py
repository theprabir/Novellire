"""Style-guide learning from pre-written chapters and the workspace documents.

The author can run this explicitly, and generation runs it once automatically when
the style guide is empty but the project already has manuscript text.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    ProjectNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_style_guide_prompt
from ..storage.document_repository import ProjectDocument
from ..storage.repositories import ProjectRepository
from .chapters import ChapterService
from .documents import ProjectDocumentService
from .settings_service import GenerationSettings
from .text import count_words

MANUSCRIPT_CHAR_LIMIT = 14_000
DOCUMENT_CHAR_LIMIT = 2_000
STYLE_MAX_OUTPUT_TOKENS = 1_200


@dataclass(frozen=True)
class StyleGuideOutcome:
    content: str
    model: str
    word_count: int
    duration_ms: int


class StyleGuideService:
    """Derive a style guide from manuscript prose and project documents."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterService,
        documents: ProjectDocumentService,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._documents = documents

    def has_source_material(self, project_id: int) -> bool:
        return self._chapters.has_written_content(project_id)

    def analyze(
        self,
        project_id: int,
        settings: GenerationSettings,
        *,
        force: bool = False,
    ) -> StyleGuideOutcome:
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )

        existing = self._documents.get_document(project_id, "style_guide")
        if (
            existing is not None
            and existing.content.strip()
            and not existing.derived
            and not force
        ):
            raise InvalidInputError(
                "Your style guide was written by hand. Clear it first if you want "
                "Novellire to write a new one from the manuscript."
            )

        manuscript = self._chapters.manuscript_text(project_id)
        if not manuscript.strip():
            raise InvalidInputError(
                "Add at least one chapter with text before analysing the style guide."
            )

        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before analysing the manuscript. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )

        system_prompt, user_prompt = build_style_guide_prompt(
            project_name=project.name,
            genre=project.genre,
            manuscript=manuscript[:MANUSCRIPT_CHAR_LIMIT],
            master_bible=self._document_text(project_id, "master_bible"),
            character_bible=self._document_text(project_id, "character_bible"),
            chapter_map=self._document_text(project_id, "chapter_map"),
        )

        request = GenerationRequest(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=0.3,
            top_p=settings.top_p,
            num_predict=min(max(settings.num_predict, 700), STYLE_MAX_OUTPUT_TOKENS),
            context_window=settings.context_window,
        )
        result = self._provider.generate(request)
        content = result.text.strip()
        if not content:
            raise LLMResponseError(
                "The model returned an empty style guide. Try again with a larger model."
            )

        self._documents.save_derived(project_id, "style_guide", content)
        return StyleGuideOutcome(
            content=content,
            model=result.model or model,
            word_count=count_words(content),
            duration_ms=result.duration_ms,
        )

    def _document_text(self, project_id: int, kind: str) -> str:
        document: ProjectDocument | None = self._documents.get_document(
            project_id, kind
        )
        if document is None:
            return ""
        return document.content[:DOCUMENT_CHAR_LIMIT]
