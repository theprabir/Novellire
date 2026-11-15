"""Scene service: ordered scenes inside a chapter, with drafted prose."""

from __future__ import annotations

from ..errors import InvalidInputError, RecordNotFoundError
from ..storage.story_repositories import (
    ChapterRepository,
    SceneRecord,
    SceneRepository,
)
from .text import count_words
from .validation import clean_optional_text
from .work_status import validate_work_status

TITLE_MAX_LENGTH = 200
TEXT_MAX_LENGTH = 20_000
CONTENT_MAX_LENGTH = 200_000


class SceneService:
    """Create, list, and edit scenes for a chapter."""

    def __init__(
        self, repository: SceneRepository, chapters: ChapterRepository
    ) -> None:
        self._repository = repository
        self._chapters = chapters

    def create_scene(
        self,
        chapter_id: int,
        *,
        title: str = "",
        summary: str = "",
        objectives: str = "",
        content: str = "",
        status: str = "planned",
    ) -> SceneRecord:
        self._require_chapter(chapter_id)
        cleaned_content = clean_optional_text(
            content, "Scene content", max_length=CONTENT_MAX_LENGTH
        )
        return self._repository.create(
            chapter_id=chapter_id,
            title=clean_optional_text(
                title, "Scene title", max_length=TITLE_MAX_LENGTH
            ),
            summary=clean_optional_text(summary, "Summary", max_length=TEXT_MAX_LENGTH),
            objectives=clean_optional_text(
                objectives, "Objectives", max_length=TEXT_MAX_LENGTH
            ),
            content=cleaned_content,
            word_count=count_words(cleaned_content),
            status=validate_work_status(status),
        )

    def list_scenes(self, chapter_id: int) -> list[SceneRecord]:
        return self._repository.list_for_chapter(chapter_id)

    def get_scene(self, scene_id: int) -> SceneRecord | None:
        return self._repository.get(scene_id)

    def require_scene(self, scene_id: int) -> SceneRecord:
        scene = self._repository.get(scene_id)
        if scene is None:
            raise RecordNotFoundError("That scene no longer exists.")
        return scene

    def update_scene(
        self,
        scene_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        objectives: str | None = None,
        content: str | None = None,
        status: str | None = None,
    ) -> SceneRecord:
        self.require_scene(scene_id)
        fields: dict[str, object] = {}

        if title is not None:
            fields["title"] = clean_optional_text(
                title, "Scene title", max_length=TITLE_MAX_LENGTH
            )
        if summary is not None:
            fields["summary"] = clean_optional_text(
                summary, "Summary", max_length=TEXT_MAX_LENGTH
            )
        if objectives is not None:
            fields["objectives"] = clean_optional_text(
                objectives, "Objectives", max_length=TEXT_MAX_LENGTH
            )
        if content is not None:
            cleaned = clean_optional_text(
                content, "Scene content", max_length=CONTENT_MAX_LENGTH
            )
            fields["content"] = cleaned
            fields["word_count"] = count_words(cleaned)
        if status is not None:
            fields["status"] = validate_work_status(status)

        return self._repository.update(scene_id, **fields)

    def total_words(self, chapter_id: int) -> int:
        return self._repository.total_words(chapter_id)

    def _require_chapter(self, chapter_id: int) -> None:
        if self._chapters.get(chapter_id) is None:
            if not isinstance(chapter_id, int):
                raise InvalidInputError("Chapter is invalid.")
            raise RecordNotFoundError("That chapter no longer exists.")
