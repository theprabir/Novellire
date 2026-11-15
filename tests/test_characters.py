"""Character profiles: aliases, uniqueness, updates, project scoping."""

from __future__ import annotations

import pytest

from novellire.core.characters import CharacterService, MAX_ALIASES
from novellire.errors import (
    DuplicateEntryError,
    InvalidInputError,
    ProjectNotFoundError,
)
from novellire.storage.repositories import Project, ProjectRepository


def test_create_character_stores_profile_and_aliases(
    character_service: CharacterService, sample_project: Project
) -> None:
    character = character_service.create_character(
        project_id=sample_project.id,
        name="  Mira Voss  ",
        aliases=["M", "mira voss", "  M  ", ""],
        physical_description="Tall, burn scars on both hands.",
        age="34",
        personality="Watchful",
        motivations="Find the vault",
        character_arc="From courier to keeper",
    )

    assert character.id > 0
    assert character.name == "Mira Voss"
    assert character.aliases == ("M", "mira voss")
    assert character.age == "34"
    assert character.character_arc == "From courier to keeper"


def test_duplicate_name_is_case_insensitive(
    character_service: CharacterService, sample_project: Project
) -> None:
    character_service.create_character(project_id=sample_project.id, name="Mira")

    with pytest.raises(DuplicateEntryError):
        character_service.create_character(project_id=sample_project.id, name="MIRA")


def test_blank_name_is_rejected(
    character_service: CharacterService, sample_project: Project
) -> None:
    with pytest.raises(InvalidInputError):
        character_service.create_character(project_id=sample_project.id, name="   ")


def test_too_many_aliases_are_rejected(
    character_service: CharacterService, sample_project: Project
) -> None:
    aliases = [f"Alias {index}" for index in range(MAX_ALIASES + 1)]
    with pytest.raises(InvalidInputError, match="at most"):
        character_service.create_character(
            project_id=sample_project.id, name="Mira", aliases=aliases
        )


def test_characters_are_listed_alphabetically_with_aliases(
    character_service: CharacterService, sample_project: Project
) -> None:
    character_service.create_character(
        project_id=sample_project.id, name="Zephyr", aliases=["Zef"]
    )
    character_service.create_character(
        project_id=sample_project.id, name="Ash", aliases=["Ashline", "Ash"]
    )

    characters = character_service.list_characters(sample_project.id)

    assert [character.name for character in characters] == ["Ash", "Zephyr"]
    assert characters[0].aliases == ("Ash", "Ashline")


def test_update_character_profile(
    character_service: CharacterService, sample_project: Project
) -> None:
    character = character_service.create_character(
        project_id=sample_project.id, name="Mira", personality="Watchful"
    )

    updated = character_service.update_character(
        character.id, name="Mira Voss", goals="Reach the vault"
    )

    assert updated.name == "Mira Voss"
    assert updated.goals == "Reach the vault"
    assert updated.personality == "Watchful"


def test_update_to_existing_name_is_rejected(
    character_service: CharacterService, sample_project: Project
) -> None:
    character_service.create_character(project_id=sample_project.id, name="Mira")
    other = character_service.create_character(
        project_id=sample_project.id, name="Kestrel"
    )

    with pytest.raises(DuplicateEntryError):
        character_service.update_character(other.id, name="mira")


def test_set_aliases_replaces_the_list(
    character_service: CharacterService, sample_project: Project
) -> None:
    character = character_service.create_character(
        project_id=sample_project.id, name="Mira", aliases=["M"]
    )

    updated = character_service.set_aliases(character.id, ["Voss", "the Courier"])

    assert updated.aliases == ("the Courier", "Voss")
    assert character_service.get_character(character.id).aliases == (
        "the Courier",
        "Voss",
    )


def test_character_lookup_is_project_scoped(
    character_service: CharacterService, project_repository: ProjectRepository
) -> None:
    first = project_repository.create(name="Ashfall")
    second = project_repository.create(name="Meridian")
    character_service.create_character(project_id=first.id, name="Mira")

    assert len(character_service.list_characters(first.id)) == 1
    assert character_service.list_characters(second.id) == []


def test_missing_project_is_rejected(
    character_service: CharacterService,
) -> None:
    with pytest.raises(ProjectNotFoundError):
        character_service.create_character(project_id=4242, name="Mira")


def test_unknown_character_returns_none(
    character_service: CharacterService,
) -> None:
    assert character_service.get_character(4242) is None
