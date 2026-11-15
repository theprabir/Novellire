"""Project service and repository behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from novellire.core.projects import NAME_MAX_LENGTH, ProjectService
from novellire.errors import (
    DuplicateProjectError,
    InvalidInputError,
    ProjectNotFoundError,
)
from novellire.storage.database import Database
from novellire.storage.repositories import ProjectRepository


def test_create_project_persists_fields(project_service: ProjectService) -> None:
    project = project_service.create_project(
        name="  Ashfall  ",
        description=" A city beneath a dying star. ",
        genre="Science fiction",
        narrative_style="Close third person",
        target_word_count=90_000,
    )

    assert project.id > 0
    assert project.name == "Ashfall"
    assert project.description == "A city beneath a dying star."
    assert project.genre == "Science fiction"
    assert project.target_word_count == 90_000
    assert project.archived is False
    assert project.created_at


def test_blank_name_is_rejected(project_service: ProjectService) -> None:
    with pytest.raises(InvalidInputError):
        project_service.create_project(name="   ")


def test_overlong_name_is_rejected(project_service: ProjectService) -> None:
    with pytest.raises(InvalidInputError):
        project_service.create_project(name="x" * (NAME_MAX_LENGTH + 1))


def test_non_positive_target_is_rejected(project_service: ProjectService) -> None:
    with pytest.raises(InvalidInputError):
        project_service.create_project(name="Ashfall", target_word_count=0)


def test_duplicate_name_is_case_insensitive(project_service: ProjectService) -> None:
    project_service.create_project(name="Ashfall")
    with pytest.raises(DuplicateProjectError):
        project_service.create_project(name="ashFALL")


def test_listing_is_sorted_and_excludes_archived(
    project_service: ProjectService,
) -> None:
    project_service.create_project(name="Zephyr")
    archived = project_service.create_project(name="Meridian")
    project_service.create_project(name="Ashfall")

    active_names = [project.name for project in project_service.list_projects()]
    assert active_names == ["Ashfall", "Meridian", "Zephyr"]

    project_service.archive_project(archived.id)
    assert [p.name for p in project_service.list_projects()] == ["Ashfall", "Zephyr"]
    assert "Meridian" in {
        p.name for p in project_service.list_projects(include_archived=True)
    }

    project_service.restore_project(archived.id)
    assert "Meridian" in {p.name for p in project_service.list_projects()}


def test_rename_project(project_service: ProjectService) -> None:
    project = project_service.create_project(name="Ashfall")
    renamed = project_service.rename_project(project.id, "Ashfall Reborn")
    assert renamed.name == "Ashfall Reborn"


def test_rename_to_existing_name_is_rejected(project_service: ProjectService) -> None:
    project_service.create_project(name="Ashfall")
    other = project_service.create_project(name="Meridian")
    with pytest.raises(DuplicateProjectError):
        project_service.rename_project(other.id, "Ashfall")


def test_update_project_keeps_other_fields(project_service: ProjectService) -> None:
    project = project_service.create_project(
        name="Ashfall", genre="Science fiction", narrative_style="Third person"
    )
    updated = project_service.update_project(project.id, genre="Fantasy")
    assert updated.genre == "Fantasy"
    assert updated.narrative_style == "Third person"
    assert updated.name == "Ashfall"


def test_update_missing_project_raises(project_service: ProjectService) -> None:
    with pytest.raises(ProjectNotFoundError):
        project_service.update_project(4242, genre="Fantasy")


def test_get_project_handles_missing_and_none(project_service: ProjectService) -> None:
    assert project_service.get_project(None) is None
    assert project_service.get_project(4242) is None


def test_projects_survive_reopening_the_database(tmp_path: Path) -> None:
    path = tmp_path / "persistent.db"
    first = Database(path)
    first.initialize()
    ProjectService(ProjectRepository(first)).create_project(name="Ashfall")

    second = Database(path)
    second.initialize()
    projects = ProjectService(ProjectRepository(second)).list_projects()
    assert [project.name for project in projects] == ["Ashfall"]
