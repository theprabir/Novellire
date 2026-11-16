"""Author-controlled, typed character relationship records."""

from __future__ import annotations

from ..errors import (
    InvalidInputError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..storage.event_repository import EventRepository
from ..storage.relationship_repository import (
    RelationshipRecord,
    RelationshipRepository,
)
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import CharacterRepository

RELATIONSHIP_TYPE_LABELS: dict[str, str] = {
    "ally": "Ally",
    "rival": "Rival",
    "family": "Family",
    "mentor": "Mentor",
    "romantic": "Romantic",
    "debt": "Debt",
    "other": "Other",
}
RELATIONSHIP_TYPES = tuple(RELATIONSHIP_TYPE_LABELS)
RELATIONSHIP_STATUSES = ("proposed", "approved", "rejected")
RELATIONSHIP_DESCRIPTION_LIMIT = 1_000


class RelationshipService:
    def __init__(
        self,
        projects: ProjectRepository,
        characters: CharacterRepository,
        events: EventRepository,
        relationships: RelationshipRepository,
    ) -> None:
        self._projects = projects
        self._characters = characters
        self._events = events
        self._relationships = relationships

    def list_for_project(self, project_id: int) -> list[RelationshipRecord]:
        self._require_project(project_id)
        return self._relationships.list_for_project(project_id)

    def create(
        self,
        project_id: int,
        *,
        character_a_id: int,
        character_b_id: int,
        relation_type: str,
        description: str = "",
        source_event_id: int | None = None,
    ) -> RelationshipRecord:
        self._require_project(project_id)
        first, second = sorted((character_a_id, character_b_id))
        if first == second:
            raise InvalidInputError(
                "Choose two different characters for a relationship."
            )
        for character_id in (first, second):
            character = self._characters.get(character_id)
            if character is None or character.project_id != project_id:
                raise InvalidInputError(
                    "Choose two characters from this project."
                )
        if source_event_id is not None:
            event = self._events.get(source_event_id)
            if event is None or event.project_id != project_id:
                raise InvalidInputError(
                    "The source event does not belong to this project."
                )
        return self._relationships.create(
            project_id=project_id,
            character_a_id=first,
            character_b_id=second,
            relation_type=_relation_type(relation_type),
            description=_description(description),
            status="proposed",
            source_event_id=source_event_id,
        )

    def update(
        self,
        record_id: int,
        *,
        relation_type: str | None = None,
        description: str | None = None,
    ) -> RelationshipRecord:
        record = self._require_record(record_id)
        return _present(
            self._relationships.update(
                record_id,
                relation_type=(
                    _relation_type(relation_type)
                    if relation_type is not None
                    else record.relation_type
                ),
                description=(
                    _description(description)
                    if description is not None
                    else record.description
                ),
            )
        )

    def set_status(self, record_id: int, status: str) -> RelationshipRecord:
        self._require_record(record_id)
        if status not in RELATIONSHIP_STATUSES:
            raise InvalidInputError("Choose a valid relationship status.")
        return _present(self._relationships.set_status(record_id, status))

    def delete(self, record_id: int) -> None:
        self._require_record(record_id)
        if not self._relationships.delete(record_id):
            raise RecordNotFoundError("That relationship no longer exists.")

    def _require_project(self, project_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError("That project no longer exists.")

    def _require_record(self, record_id: int) -> RelationshipRecord:
        record = self._relationships.get(record_id)
        if record is None:
            raise RecordNotFoundError("That relationship no longer exists.")
        return record


def _relation_type(value: str) -> str:
    normalized = " ".join((value or "").split()).casefold()
    if normalized not in RELATIONSHIP_TYPE_LABELS:
        raise InvalidInputError("Choose a valid relationship type.")
    return normalized


def _description(value: str) -> str:
    return " ".join((value or "").split())[:RELATIONSHIP_DESCRIPTION_LIMIT].strip()


def _present(record: RelationshipRecord | None) -> RelationshipRecord:
    if record is None:
        raise RecordNotFoundError("That relationship no longer exists.")
    return record
