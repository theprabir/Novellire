"""Canon-change review: mark an earlier recorded fact as replaced by a later one.

Character state already keeps one snapshot per character per chapter. Adjacent
snapshots that differ are changes the author may want to settle: the earlier
record stays in the database with its provenance, but the author can record that
a later snapshot supersedes it, with an optional note. Superseded snapshots are
left out of the canon a continuity check may cite, so a replaced fact is not
treated as current canon, while the ledger still shows it as history.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..errors import (
    InvalidInputError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..storage.repositories import ProjectRepository
from ..storage.state_repository import CharacterStateRecord, CharacterStateRepository
from ..storage.story_repositories import ChapterRepository, CharacterRepository
from ..storage.supersession_repository import (
    SupersessionRecord,
    SupersessionRepository,
)

SUPERSESSION_NOTE_LIMIT = 1_000
STATE_FIELDS = ("location", "status", "goals", "knowledge")


@dataclass(frozen=True)
class CanonChange:
    earlier_id: int
    later_id: int
    character_id: int
    character_name: str
    earlier_chapter_position: int
    earlier_chapter_title: str
    later_chapter_position: int
    later_chapter_title: str
    changed: tuple[str, ...]
    earlier_details: dict[str, str]
    later_details: dict[str, str]
    superseded: bool
    note: str


class SupersessionService:
    """Review snapshot changes and record which earlier record was replaced."""

    def __init__(
        self,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        characters: CharacterRepository,
        states: CharacterStateRepository,
        supersessions: SupersessionRepository,
    ) -> None:
        self._projects = projects
        self._chapters = chapters
        self._characters = characters
        self._states = states
        self._supersessions = supersessions

    def review(self, project_id: int) -> dict[str, object]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        states = self._states.list_for_project(project_id)
        decisions = {
            decision.earlier_id: decision
            for decision in self._supersessions.list_for_project(project_id)
        }
        grouped: dict[int, list[CharacterStateRecord]] = {}
        for state in states:
            grouped.setdefault(state.character_id, []).append(state)

        changes: list[CanonChange] = []
        for character_id, snapshots in grouped.items():
            ordered = sorted(snapshots, key=lambda item: item.chapter_position)
            for earlier, later in zip(ordered, ordered[1:]):
                changed = tuple(
                    field
                    for field in STATE_FIELDS
                    if getattr(earlier, field) != getattr(later, field)
                )
                if not changed:
                    continue
                decision = decisions.get(earlier.id)
                changes.append(
                    CanonChange(
                        earlier_id=earlier.id,
                        later_id=later.id,
                        character_id=character_id,
                        character_name=earlier.character_name,
                        earlier_chapter_position=earlier.chapter_position,
                        earlier_chapter_title=earlier.chapter_title,
                        later_chapter_position=later.chapter_position,
                        later_chapter_title=later.chapter_title,
                        changed=changed,
                        earlier_details={
                            field: getattr(earlier, field) for field in STATE_FIELDS
                        },
                        later_details={
                            field: getattr(later, field) for field in STATE_FIELDS
                        },
                        superseded=decision is not None,
                        note=decision.note if decision is not None else "",
                    )
                )
        changes.sort(
            key=lambda change: (
                change.later_chapter_position,
                change.character_name.casefold(),
                change.earlier_id,
            )
        )

        return {
            "counts": {
                "characters": len(grouped),
                "changes": len(changes),
                "superseded": sum(1 for change in changes if change.superseded),
                "pending": sum(1 for change in changes if not change.superseded),
            },
            "changes": [asdict(change) for change in changes],
        }

    def set_superseded(
        self,
        project_id: int,
        *,
        earlier_id: int,
        later_id: int,
        note: str = "",
        superseded: bool = True,
    ) -> SupersessionRecord | None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        earlier = self._state(project_id, earlier_id)
        later = self._state(project_id, later_id)
        if earlier.character_id != later.character_id:
            raise InvalidInputError(
                "A record can only be superseded by a later record for the same "
                "character."
            )
        if later.chapter_position <= earlier.chapter_position:
            raise InvalidInputError(
                "Choose an earlier record and a later record for the same "
                "character."
            )
        if not superseded:
            self._supersessions.delete(project_id, "state", earlier.id)
            return None
        return self._supersessions.upsert(
            project_id=project_id,
            record_kind="state",
            earlier_id=earlier.id,
            later_id=later.id,
            note=_note(note),
        )

    def _state(self, project_id: int, state_id: int) -> CharacterStateRecord:
        state = self._states.get(state_id)
        if state is None or state.project_id != project_id:
            raise RecordNotFoundError(
                "That character state no longer exists in this project."
            )
        return state


def _note(value: str) -> str:
    return " ".join((value or "").split())[:SUPERSESSION_NOTE_LIMIT].strip()
