"""Author-recorded character state snapshots with chapter provenance."""

from __future__ import annotations

from ..errors import (
    InvalidInputError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..storage.repositories import ProjectRepository
from ..storage.state_repository import (
    CharacterStateRecord,
    CharacterStateRepository,
)
from ..storage.story_repositories import (
    ChapterRepository,
    CharacterRepository,
)

STATE_FIELD_LIMITS = {
    "location": 300,
    "status": 500,
    "goals": 500,
    "knowledge": 500,
}


class CharacterStateService:
    def __init__(
        self,
        projects: ProjectRepository,
        characters: CharacterRepository,
        chapters: ChapterRepository,
        states: CharacterStateRepository,
    ) -> None:
        self._projects = projects
        self._characters = characters
        self._chapters = chapters
        self._states = states

    def list_for_project(self, project_id: int) -> list[CharacterStateRecord]:
        self._require_project(project_id)
        return self._states.list_for_project(project_id)

    def create(
        self,
        project_id: int,
        *,
        character_id: int,
        chapter_id: int,
        location: str = "",
        status: str = "",
        goals: str = "",
        knowledge: str = "",
    ) -> CharacterStateRecord:
        self._require_project(project_id)
        character = self._characters.get(character_id)
        if character is None or character.project_id != project_id:
            raise InvalidInputError("Choose a character from this project.")
        chapter = self._chapters.get(chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise InvalidInputError("Choose a chapter from this project.")
        fields = clean_state_fields(location, status, goals, knowledge)
        return self._states.create(
            project_id=project_id,
            character_id=character_id,
            chapter_id=chapter_id,
            **fields,
        )

    def update(
        self,
        state_id: int,
        *,
        location: str,
        status: str,
        goals: str,
        knowledge: str,
    ) -> CharacterStateRecord:
        self._require_state(state_id)
        return _present(
            self._states.update(
                state_id,
                **clean_state_fields(location, status, goals, knowledge),
            )
        )

    def delete(self, state_id: int) -> None:
        self._require_state(state_id)
        if not self._states.delete(state_id):
            raise RecordNotFoundError("That state snapshot no longer exists.")

    def _require_project(self, project_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError("That project no longer exists.")

    def _require_state(self, state_id: int) -> CharacterStateRecord:
        record = self._states.get(state_id)
        if record is None:
            raise RecordNotFoundError("That state snapshot no longer exists.")
        return record


def clean_state_fields(
    location: str, status: str, goals: str, knowledge: str
) -> dict[str, str]:
    values = {
        "location": _clean(location, STATE_FIELD_LIMITS["location"]),
        "status": _clean(status, STATE_FIELD_LIMITS["status"]),
        "goals": _clean(goals, STATE_FIELD_LIMITS["goals"]),
        "knowledge": _clean(knowledge, STATE_FIELD_LIMITS["knowledge"]),
    }
    if not any(values.values()):
        raise InvalidInputError(
            "Record at least one state detail: location, status, goals, or knowledge."
        )
    return values


def _clean(value: str, limit: int) -> str:
    return " ".join((value or "").split())[:limit].strip()


def _present(record: CharacterStateRecord | None) -> CharacterStateRecord:
    if record is None:
        raise RecordNotFoundError("That state snapshot no longer exists.")
    return record
