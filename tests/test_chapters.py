"""Chapter structure: ordering, status, viewpoint, and validation."""

from __future__ import annotations

import pytest

from novellire.core.chapters import ChapterService
from novellire.core.characters import CharacterService
from novellire.errors import (
    InvalidInputError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from novellire.storage.repositories import Project, ProjectRepository


def test_chapters_append_in_order(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    first = chapter_service.create_chapter(
        project_id=sample_project.id, title="The Vault"
    )
    second = chapter_service.create_chapter(
        project_id=sample_project.id, title="Ashfall Square"
    )

    assert (first.position, second.position) == (1, 2)
    assert [chapter.title for chapter in chapter_service.list_chapters(sample_project.id)] == [
        "The Vault",
        "Ashfall Square",
    ]


def test_chapter_can_be_inserted_at_a_number(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    chapter_service.create_chapter(project_id=sample_project.id, title="One")
    chapter_service.create_chapter(project_id=sample_project.id, title="Two")
    chapter_service.create_chapter(project_id=sample_project.id, title="Three")

    inserted = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="One and a Half",
        content="Pasted prose.",
        origin="imported",
        position=2,
    )

    chapters = chapter_service.list_chapters(sample_project.id)
    assert inserted.position == 2
    assert [chapter.title for chapter in chapters] == [
        "One",
        "One and a Half",
        "Two",
        "Three",
    ]
    assert [chapter.position for chapter in chapters] == [1, 2, 3, 4]


def test_chapter_number_must_be_reachable(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    chapter_service.create_chapter(project_id=sample_project.id, title="One")

    with pytest.raises(InvalidInputError, match="between 1 and 2"):
        chapter_service.create_chapter(
            project_id=sample_project.id, title="Skipped", position=4
        )
    with pytest.raises(InvalidInputError, match="between 1 and 2"):
        chapter_service.create_chapter(
            project_id=sample_project.id, title="Zero", position=0
        )


def test_chapters_are_scoped_per_project(
    chapter_service: ChapterService, project_repository: ProjectRepository
) -> None:
    first = project_repository.create(name="Ashfall")
    second = project_repository.create(name="Meridian")

    chapter_service.create_chapter(project_id=first.id, title="First")
    second_chapter = chapter_service.create_chapter(project_id=second.id, title="Other")

    assert second_chapter.position == 1
    assert [c.title for c in chapter_service.list_chapters(first.id)] == ["First"]
    assert [c.title for c in chapter_service.list_chapters(second.id)] == ["Other"]


def test_create_chapter_stores_blueprint_fields(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Vault",
        part="Act One",
        summary="Mira opens the vault.",
        objectives="Reveal the brass key.",
        target_word_count=2_500,
    )

    assert chapter.part == "Act One"
    assert chapter.objectives == "Reveal the brass key."
    assert chapter.target_word_count == 2_500
    assert chapter.status == "planned"


def test_blank_title_is_rejected(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    with pytest.raises(InvalidInputError):
        chapter_service.create_chapter(project_id=sample_project.id, title="  ")


def test_invalid_status_is_rejected(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    with pytest.raises(InvalidInputError):
        chapter_service.create_chapter(
            project_id=sample_project.id, title="The Vault", status="finished"
        )


def test_negative_target_is_rejected(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    with pytest.raises(InvalidInputError):
        chapter_service.create_chapter(
            project_id=sample_project.id, title="The Vault", target_word_count=-5
        )


def test_missing_project_is_rejected(
    chapter_service: ChapterService,
) -> None:
    with pytest.raises(ProjectNotFoundError):
        chapter_service.create_chapter(project_id=4242, title="Orphan")


def test_viewpoint_character_must_belong_to_project(
    chapter_service: ChapterService,
    character_service: CharacterService,
    project_repository: ProjectRepository,
    sample_project: Project,
) -> None:
    other_project = project_repository.create(name="Meridian")
    foreign_character = character_service.create_character(
        project_id=other_project.id, name="Mira"
    )

    with pytest.raises(InvalidInputError, match="same project"):
        chapter_service.create_chapter(
            project_id=sample_project.id,
            title="The Vault",
            viewpoint_character_id=foreign_character.id,
        )


def test_viewpoint_and_target_can_be_set_and_cleared(
    chapter_service: ChapterService,
    character_service: CharacterService,
    sample_project: Project,
) -> None:
    character = character_service.create_character(
        project_id=sample_project.id, name="Mira"
    )
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Vault",
        viewpoint_character_id=character.id,
        target_word_count=2_000,
    )
    assert chapter.viewpoint_character_id == character.id

    cleared = chapter_service.update_chapter(
        chapter.id, viewpoint_character_id=None, target_word_count=None
    )

    assert cleared.viewpoint_character_id is None
    assert cleared.target_word_count is None


def test_update_chapter_keeps_unspecified_fields(
    chapter_service: ChapterService, sample_project: Project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Vault",
        summary="Original summary",
        target_word_count=1_000,
    )

    updated = chapter_service.update_chapter(
        chapter.id, title="The Sealed Vault", status="drafting"
    )

    assert updated.title == "The Sealed Vault"
    assert updated.status == "drafting"
    assert updated.summary == "Original summary"
    assert updated.target_word_count == 1_000


def test_update_unknown_chapter_raises(
    chapter_service: ChapterService,
) -> None:
    with pytest.raises(RecordNotFoundError):
        chapter_service.update_chapter(4242, title="Nothing")
