"""Chapter service: the ordered narrative blueprint for a project."""

from __future__ import annotations

from typing import Final

from ..errors import (
    InvalidInputError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import (
    ChapterRecord,
    ChapterRepository,
    CharacterRepository,
)
from .text import count_words
from .validation import (
    clean_optional_text,
    clean_required_text,
    clean_word_target,
)
from .work_status import validate_work_status

_UNSET: Final = object()

TITLE_MAX_LENGTH = 200
PART_MAX_LENGTH = 120
TEXT_MAX_LENGTH = 20_000
CONTENT_MAX_LENGTH = 400_000
MAX_TARGET_WORDS = 1_000_000
CHAPTER_ORIGINS = ("written", "imported")


class ChapterService:
    """Create, order, and edit chapters within a project."""

    def __init__(
        self,
        repository: ChapterRepository,
        projects: ProjectRepository,
        characters: CharacterRepository,
    ) -> None:
        self._repository = repository
        self._projects = projects
        self._characters = characters

    def create_chapter(
        self,
        *,
        project_id: int,
        title: str,
        part: str = "",
        summary: str = "",
        objectives: str = "",
        viewpoint_character_id: int | None = None,
        target_word_count: int | None = None,
        status: str = "planned",
        content: str = "",
        origin: str = "written",
    ) -> ChapterRecord:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        if viewpoint_character_id is not None:
            self._validate_viewpoint(project_id, viewpoint_character_id)

        cleaned_content = clean_optional_text(
            content, "Chapter text", max_length=CONTENT_MAX_LENGTH
        )
        validated_status = validate_work_status(status)
        if cleaned_content and validated_status == "planned":
            validated_status = "drafted"

        return self._repository.create(
            project_id=project_id,
            title=clean_required_text(title, "Chapter title", max_length=TITLE_MAX_LENGTH),
            part=clean_optional_text(part, "Part", max_length=PART_MAX_LENGTH),
            summary=clean_optional_text(summary, "Summary", max_length=TEXT_MAX_LENGTH),
            objectives=clean_optional_text(
                objectives, "Objectives", max_length=TEXT_MAX_LENGTH
            ),
            viewpoint_character_id=viewpoint_character_id,
            target_word_count=clean_word_target(
                target_word_count, "Target word count", maximum=MAX_TARGET_WORDS
            ),
            status=validated_status,
            content=cleaned_content,
            word_count=count_words(cleaned_content),
            origin=self._validate_origin(origin),
        )

    def list_chapters(self, project_id: int) -> list[ChapterRecord]:
        return self._repository.list_for_project(project_id)

    def get_chapter(self, chapter_id: int) -> ChapterRecord | None:
        return self._repository.get(chapter_id)

    def require_chapter(self, chapter_id: int) -> ChapterRecord:
        chapter = self._repository.get(chapter_id)
        if chapter is None:
            raise RecordNotFoundError("That chapter no longer exists.")
        return chapter

    def update_chapter(
        self,
        chapter_id: int,
        *,
        title: str | None = None,
        part: str | None = None,
        summary: str | None = None,
        objectives: str | None = None,
        status: str | None = None,
        viewpoint_character_id: object = _UNSET,
        target_word_count: object = _UNSET,
        content: str | None = None,
    ) -> ChapterRecord:
        chapter = self.require_chapter(chapter_id)
        fields: dict[str, object] = {}

        if title is not None:
            fields["title"] = clean_required_text(
                title, "Chapter title", max_length=TITLE_MAX_LENGTH
            )
        if part is not None:
            fields["part"] = clean_optional_text(
                part, "Part", max_length=PART_MAX_LENGTH
            )
        if summary is not None:
            fields["summary"] = clean_optional_text(
                summary, "Summary", max_length=TEXT_MAX_LENGTH
            )
        if objectives is not None:
            fields["objectives"] = clean_optional_text(
                objectives, "Objectives", max_length=TEXT_MAX_LENGTH
            )
        if status is not None:
            fields["status"] = validate_work_status(status)
        if viewpoint_character_id is not _UNSET:
            viewpoint = viewpoint_character_id
            if viewpoint is not None:
                if not isinstance(viewpoint, int):
                    raise InvalidInputError("Viewpoint character is invalid.")
                self._validate_viewpoint(chapter.project_id, viewpoint)
            fields["viewpoint_character_id"] = viewpoint
        if target_word_count is not _UNSET:
            fields["target_word_count"] = clean_word_target(
                target_word_count,  # type: ignore[arg-type]
                "Target word count",
                maximum=MAX_TARGET_WORDS,
            )
        if content is not None:
            cleaned = clean_optional_text(
                content, "Chapter text", max_length=CONTENT_MAX_LENGTH
            )
            fields["content"] = cleaned
            fields["word_count"] = count_words(cleaned)

        return self._repository.update(chapter_id, **fields)

    def _validate_origin(self, origin: str) -> str:
        cleaned = (origin or "written").strip().lower()
        if cleaned not in CHAPTER_ORIGINS:
            raise InvalidInputError(
                "Chapter origin must be 'written' or 'imported'."
            )
        return cleaned

    def manuscript_text(self, project_id: int) -> str:
        """Return every chapter's prose, in order, for analysis."""
        parts = [
            f"Chapter {chapter.position} - {chapter.title}\n\n{chapter.content}"
            for chapter in self.list_chapters(project_id)
            if chapter.content.strip()
        ]
        return "\n\n".join(parts)

    def has_written_content(self, project_id: int) -> bool:
        return any(
            chapter.content.strip() for chapter in self.list_chapters(project_id)
        )

    def _validate_viewpoint(self, project_id: int, character_id: int) -> None:
        character = self._characters.get(character_id)
        if character is None or character.project_id != project_id:
            raise InvalidInputError(
                "The viewpoint character must belong to the same project."
            )
