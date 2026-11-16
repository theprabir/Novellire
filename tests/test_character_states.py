"""Author-recorded character state snapshots."""

from __future__ import annotations

import pytest

from novellire.core.character_states import CharacterStateService
from novellire.errors import DuplicateEntryError, InvalidInputError
from novellire.storage.state_repository import CharacterStateRepository
from novellire.storage.story_repositories import (
    ChapterRepository,
    CharacterRepository,
)


@pytest.fixture()
def state_service(
    database, project_repository
) -> CharacterStateService:
    return CharacterStateService(
        project_repository,
        CharacterRepository(database),
        ChapterRepository(database),
        CharacterStateRepository(database),
    )


def test_current_state_follows_chapter_order_not_insertion(
    state_service: CharacterStateService,
    character_service,
    chapter_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    first = chapter_service.create_chapter(
        project_id=sample_project.id, title="Part One"
    )
    second = chapter_service.create_chapter(
        project_id=sample_project.id, title="Part Two"
    )

    later = state_service.create(
        sample_project.id,
        character_id=mira.id,
        chapter_id=second.id,
        location="The gate",
        status="Injured",
        goals="Find the ledger",
    )
    earlier = state_service.create(
        sample_project.id,
        character_id=mira.id,
        chapter_id=first.id,
        location="The archive",
    )

    states = state_service.list_for_project(sample_project.id)

    assert [state.id for state in states] == [later.id, earlier.id]
    assert states[0].is_current is True
    assert states[1].is_current is False
    assert states[0].chapter_title == "Part Two"
    assert states[1].chapter_title == "Part One"

    state_service.delete(later.id)
    remaining = state_service.list_for_project(sample_project.id)
    assert remaining[0].id == earlier.id
    assert remaining[0].is_current is True


def test_one_snapshot_per_character_and_chapter(
    state_service: CharacterStateService,
    character_service,
    chapter_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Gate"
    )
    state_service.create(
        sample_project.id,
        character_id=mira.id,
        chapter_id=chapter.id,
        location="The gate",
    )

    with pytest.raises(DuplicateEntryError, match="already has a state"):
        state_service.create(
            sample_project.id,
            character_id=mira.id,
            chapter_id=chapter.id,
            location="Somewhere else",
        )


def test_update_and_validation(
    state_service: CharacterStateService,
    character_service,
    chapter_service,
    sample_project,
) -> None:
    mira = character_service.create_character(
        project_id=sample_project.id, name="Mira Voss"
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Gate"
    )
    state = state_service.create(
        sample_project.id,
        character_id=mira.id,
        chapter_id=chapter.id,
        location="The gate",
    )

    updated = state_service.update(
        state.id,
        location="The keep",
        status="",
        goals="Open the sealed door",
        knowledge="She knows the gate is warded",
    )

    assert updated.location == "The keep"
    assert updated.goals == "Open the sealed door"
    assert updated.knowledge == "She knows the gate is warded"

    with pytest.raises(InvalidInputError, match="at least one state detail"):
        state_service.create(
            sample_project.id,
            character_id=mira.id,
            chapter_id=chapter.id,
        )
    with pytest.raises(InvalidInputError, match="chapter from this project"):
        state_service.create(
            sample_project.id,
            character_id=mira.id,
            chapter_id=9999,
            location="Nowhere",
        )
