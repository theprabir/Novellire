"""Story bible entries: categories, duplicates, updates, project scoping."""

from __future__ import annotations

import pytest

from novellire.core.story_bible import StoryBibleService
from novellire.errors import (
    DuplicateEntryError,
    InvalidInputError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from novellire.storage.repositories import Project, ProjectRepository


def test_create_and_list_entries(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    story_bible_service.create_entry(
        project_id=sample_project.id,
        category="premise",
        title="The dying star",
        content="The sun is collapsing.",
    )
    story_bible_service.create_entry(
        project_id=sample_project.id,
        category="geography",
        title="Ashfall",
        content="A city built into a caldera.",
    )

    entries = story_bible_service.list_entries(sample_project.id)

    assert [entry.title for entry in entries] == ["Ashfall", "The dying star"]
    assert entries[0].category == "geography"
    assert entries[1].content == "The sun is collapsing."


def test_filtering_by_category(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    story_bible_service.create_entry(
        project_id=sample_project.id, category="premise", title="The dying star"
    )
    story_bible_service.create_entry(
        project_id=sample_project.id, category="geography", title="Ashfall"
    )

    premise_entries = story_bible_service.list_entries(
        sample_project.id, category="premise"
    )

    assert [entry.title for entry in premise_entries] == ["The dying star"]


def test_unknown_category_is_rejected(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    with pytest.raises(InvalidInputError, match="Category"):
        story_bible_service.create_entry(
            project_id=sample_project.id, category="magic_system", title="Rules"
        )


def test_blank_title_is_rejected(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    with pytest.raises(InvalidInputError):
        story_bible_service.create_entry(
            project_id=sample_project.id, category="premise", title="  "
        )


def test_duplicate_title_in_same_category_is_rejected(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    story_bible_service.create_entry(
        project_id=sample_project.id, category="premise", title="The dying star"
    )

    with pytest.raises(DuplicateEntryError):
        story_bible_service.create_entry(
            project_id=sample_project.id, category="premise", title="the dying star"
        )


def test_same_title_in_another_category_is_allowed(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    story_bible_service.create_entry(
        project_id=sample_project.id, category="premise", title="Ashfall"
    )
    entry = story_bible_service.create_entry(
        project_id=sample_project.id, category="locations", title="Ashfall"
    )

    assert entry.category == "locations"


def test_update_entry(
    story_bible_service: StoryBibleService, sample_project: Project
) -> None:
    entry = story_bible_service.create_entry(
        project_id=sample_project.id, category="premise", title="Draft premise"
    )

    updated = story_bible_service.update_entry(
        entry.id,
        category="main_storyline",
        title="The long fall",
        content="Mira must reach the vault.",
    )

    assert updated.category == "main_storyline"
    assert updated.title == "The long fall"
    assert updated.content == "Mira must reach the vault."


def test_update_unknown_entry_raises(
    story_bible_service: StoryBibleService,
) -> None:
    with pytest.raises(RecordNotFoundError):
        story_bible_service.update_entry(4242, title="Nothing")


def test_entries_are_scoped_to_their_project(
    story_bible_service: StoryBibleService, project_repository: ProjectRepository
) -> None:
    first = project_repository.create(name="Ashfall")
    second = project_repository.create(name="Meridian")
    story_bible_service.create_entry(
        project_id=first.id, category="premise", title="First premise"
    )

    assert story_bible_service.list_entries(second.id) == []
    assert len(story_bible_service.list_entries(first.id)) == 1


def test_missing_project_is_rejected(
    story_bible_service: StoryBibleService,
) -> None:
    with pytest.raises(ProjectNotFoundError):
        story_bible_service.create_entry(
            project_id=4242, category="premise", title="Orphan"
        )
