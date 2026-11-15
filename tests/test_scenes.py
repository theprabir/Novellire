"""Scenes: ordering, word counts, drafts, and status validation."""

from __future__ import annotations

import pytest

from novellire.core.chapters import ChapterService
from novellire.core.scenes import SceneService
from novellire.errors import InvalidInputError, RecordNotFoundError
from novellire.storage.repositories import Project


def _chapter(chapter_service: ChapterService, project: Project):
    return chapter_service.create_chapter(project_id=project.id, title="The Vault")


def test_scenes_append_in_order(
    scene_service: SceneService,
    chapter_service: ChapterService,
    sample_project: Project,
) -> None:
    chapter = _chapter(chapter_service, sample_project)

    first = scene_service.create_scene(chapter.id, title="Approach")
    second = scene_service.create_scene(chapter.id, title="Descent")

    assert (first.position, second.position) == (1, 2)
    assert [scene.title for scene in scene_service.list_scenes(chapter.id)] == [
        "Approach",
        "Descent",
    ]


def test_scene_word_count_is_computed(
    scene_service: SceneService,
    chapter_service: ChapterService,
    sample_project: Project,
) -> None:
    chapter = _chapter(chapter_service, sample_project)

    scene = scene_service.create_scene(
        chapter.id, title="Approach", content="Mira crossed the  empty square."
    )

    assert scene.word_count == 5


def test_updating_content_recomputes_word_count(
    scene_service: SceneService,
    chapter_service: ChapterService,
    sample_project: Project,
) -> None:
    chapter = _chapter(chapter_service, sample_project)
    scene = scene_service.create_scene(chapter.id, content="one two three")

    updated = scene_service.update_scene(
        scene.id, content="four five six seven", status="drafted"
    )

    assert updated.word_count == 4
    assert updated.status == "drafted"


def test_total_words_sums_scene_drafts(
    scene_service: SceneService,
    chapter_service: ChapterService,
    sample_project: Project,
) -> None:
    chapter = _chapter(chapter_service, sample_project)
    scene_service.create_scene(chapter.id, content="one two three")
    scene_service.create_scene(chapter.id, content="four five")

    assert scene_service.total_words(chapter.id) == 5


def test_scene_requires_existing_chapter(
    scene_service: SceneService,
) -> None:
    with pytest.raises(RecordNotFoundError):
        scene_service.create_scene(4242, title="Orphan")


def test_invalid_scene_status_is_rejected(
    scene_service: SceneService,
    chapter_service: ChapterService,
    sample_project: Project,
) -> None:
    chapter = _chapter(chapter_service, sample_project)

    with pytest.raises(InvalidInputError):
        scene_service.create_scene(chapter.id, title="Approach", status="done")


def test_update_unknown_scene_raises(
    scene_service: SceneService,
) -> None:
    with pytest.raises(RecordNotFoundError):
        scene_service.update_scene(4242, content="Nothing")
