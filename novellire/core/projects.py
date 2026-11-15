"""Project service: validation and use cases for novel projects."""

from __future__ import annotations

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.repositories import Project, ProjectRepository

NAME_MAX_LENGTH = 120
SHORT_TEXT_MAX_LENGTH = 120
LONG_TEXT_MAX_LENGTH = 4000
MAX_TARGET_WORD_COUNT = 20_000_000


class ProjectService:
    """Author-facing project operations on top of ``ProjectRepository``."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def create_project(
        self,
        *,
        name: str,
        description: str = "",
        genre: str = "",
        narrative_style: str = "",
        target_word_count: int | None = None,
    ) -> Project:
        return self._repository.create(
            name=_clean_name(name),
            description=_clean_text(description, "Description", LONG_TEXT_MAX_LENGTH),
            genre=_clean_text(genre, "Genre", SHORT_TEXT_MAX_LENGTH),
            narrative_style=_clean_text(
                narrative_style, "Narrative style", SHORT_TEXT_MAX_LENGTH
            ),
            target_word_count=_clean_target(target_word_count),
        )

    def list_projects(self, *, include_archived: bool = False) -> list[Project]:
        return self._repository.list(include_archived=include_archived)

    def get_project(self, project_id: int | None) -> Project | None:
        if project_id is None:
            return None
        return self._repository.get(project_id)

    def require_project(self, project_id: int | None) -> Project:
        project = self.get_project(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        return project

    def rename_project(self, project_id: int, name: str) -> Project:
        return self._repository.update(project_id, name=_clean_name(name))

    def update_project(
        self,
        project_id: int,
        *,
        description: str | None = None,
        genre: str | None = None,
        narrative_style: str | None = None,
        target_word_count: int | None = None,
    ) -> Project:
        fields: dict[str, object] = {}
        if description is not None:
            fields["description"] = _clean_text(
                description, "Description", LONG_TEXT_MAX_LENGTH
            )
        if genre is not None:
            fields["genre"] = _clean_text(genre, "Genre", SHORT_TEXT_MAX_LENGTH)
        if narrative_style is not None:
            fields["narrative_style"] = _clean_text(
                narrative_style, "Narrative style", SHORT_TEXT_MAX_LENGTH
            )
        if target_word_count is not None:
            fields["target_word_count"] = _clean_target(target_word_count)
        if not fields:
            return self.require_project(project_id)
        return self._repository.update(project_id, **fields)

    def archive_project(self, project_id: int) -> Project:
        return self._repository.set_archived(project_id, True)

    def restore_project(self, project_id: int) -> Project:
        return self._repository.set_archived(project_id, False)


def _clean_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise InvalidInputError("Project name is required.")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise InvalidInputError(
            f"Project name must be {NAME_MAX_LENGTH} characters or fewer."
        )
    return cleaned


def _clean_text(value: str, label: str, max_length: int) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) > max_length:
        raise InvalidInputError(
            f"{label} must be {max_length} characters or fewer."
        )
    return cleaned


def _clean_target(target_word_count: int | None) -> int | None:
    if target_word_count is None:
        return None
    try:
        value = int(target_word_count)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("Target word count must be a whole number.") from exc
    if value <= 0:
        raise InvalidInputError("Target word count must be greater than zero.")
    if value > MAX_TARGET_WORD_COUNT:
        raise InvalidInputError(
            f"Target word count must be {MAX_TARGET_WORD_COUNT:,} or fewer."
        )
    return value
