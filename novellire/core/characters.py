"""Character profiles: identity information only.

Evolving narrative state (location, knowledge, relationships) belongs to a later
phase, so this service deliberately stores stable profile fields. Keeping the
two concerns apart prevents generated assumptions from silently becoming canon.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import CharacterRecord, CharacterRepository
from .validation import clean_optional_text, clean_required_text

NAME_MAX_LENGTH = 120
ALIAS_MAX_LENGTH = 120
MAX_ALIASES = 20
PROFILE_MAX_LENGTH = 20_000

PROFILE_FIELDS: tuple[str, ...] = (
    "physical_description",
    "age",
    "personality",
    "motivations",
    "goals",
    "fears",
    "strengths",
    "weaknesses",
    "background",
    "secrets",
    "character_arc",
)

FIELD_LABELS: dict[str, str] = {
    "physical_description": "Physical description",
    "age": "Age",
    "personality": "Personality",
    "motivations": "Motivations",
    "goals": "Goals",
    "fears": "Fears",
    "strengths": "Strengths",
    "weaknesses": "Weaknesses",
    "background": "Background",
    "secrets": "Secrets",
    "character_arc": "Character arc",
}


class CharacterService:
    """Author-facing character operations."""

    def __init__(
        self, repository: CharacterRepository, projects: ProjectRepository
    ) -> None:
        self._repository = repository
        self._projects = projects

    def create_character(
        self,
        *,
        project_id: int,
        name: str,
        aliases: Sequence[str] = (),
        **profile: str,
    ) -> CharacterRecord:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        values = _clean_profile(profile)
        return self._repository.create(
            project_id=project_id,
            name=clean_required_text(name, "Character name", max_length=NAME_MAX_LENGTH),
            aliases=normalize_aliases(aliases),
            **values,
        )

    def list_characters(self, project_id: int) -> list[CharacterRecord]:
        return self._repository.list_for_project(project_id)

    def get_character(self, character_id: int) -> CharacterRecord | None:
        return self._repository.get(character_id)

    def update_character(
        self, character_id: int, *, name: str | None = None, **profile: str
    ) -> CharacterRecord:
        fields: dict[str, object] = _clean_profile(profile)
        if name is not None:
            fields["name"] = clean_required_text(
                name, "Character name", max_length=NAME_MAX_LENGTH
            )
        return self._repository.update(character_id, **fields)

    def set_aliases(
        self, character_id: int, aliases: Sequence[str]
    ) -> CharacterRecord:
        return self._repository.replace_aliases(
            character_id, normalize_aliases(aliases)
        )


def normalize_aliases(aliases: Sequence[str]) -> tuple[str, ...]:
    """Strip, deduplicate case-insensitively, and bound the alias list."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in aliases:
        alias = (raw or "").strip()
        if not alias:
            continue
        if len(alias) > ALIAS_MAX_LENGTH:
            raise InvalidInputError(
                f"Each alias must be {ALIAS_MAX_LENGTH} characters or fewer."
            )
        key = alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(alias)
    if len(cleaned) > MAX_ALIASES:
        raise InvalidInputError(
            f"A character can have at most {MAX_ALIASES} aliases."
        )
    return tuple(cleaned)


def _clean_profile(profile: dict[str, str]) -> dict[str, object]:
    unknown = set(profile) - set(PROFILE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported character fields: {sorted(unknown)}")
    return {
        field: clean_optional_text(
            value, FIELD_LABELS[field], max_length=PROFILE_MAX_LENGTH
        )
        for field, value in profile.items()
    }
