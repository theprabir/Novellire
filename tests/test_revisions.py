"""Chapter revision history and restore."""

from __future__ import annotations

import pytest

from novellire.errors import RecordNotFoundError


def test_content_edits_create_revisions_and_restore_snapshots_current(
    chapter_service, sample_project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="First draft.",
    )

    chapter_service.update_chapter(chapter.id, content="Second draft.")
    revisions = chapter_service.list_revisions(chapter.id)
    assert len(revisions) == 1
    assert revisions[0].content == "First draft."
    assert revisions[0].source == "edit"

    # Saving identical text must not create noise.
    chapter_service.update_chapter(chapter.id, content="Second draft.")
    assert len(chapter_service.list_revisions(chapter.id)) == 1

    chapter_service.update_chapter(chapter.id, content="Third draft.")
    revisions = chapter_service.list_revisions(chapter.id)
    assert [revision.content for revision in revisions] == [
        "Second draft.",
        "First draft.",
    ]

    oldest = revisions[-1]
    restored = chapter_service.restore_revision(chapter.id, oldest.id)

    assert restored.content == "First draft."
    assert restored.word_count == 2
    revisions = chapter_service.list_revisions(chapter.id)
    assert len(revisions) == 3
    assert revisions[0].source == "restore"
    assert revisions[0].content == "Third draft."


def test_empty_initial_content_does_not_create_an_empty_revision(
    chapter_service, sample_project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="Blank"
    )
    chapter_service.update_chapter(chapter.id, content="Now written.")

    assert chapter_service.list_revisions(chapter.id) == []


def test_revision_must_belong_to_the_chapter(
    chapter_service, sample_project
) -> None:
    first = chapter_service.create_chapter(
        project_id=sample_project.id, title="First", content="One."
    )
    second = chapter_service.create_chapter(
        project_id=sample_project.id, title="Second", content="Two."
    )
    chapter_service.update_chapter(first.id, content="One revised.")
    revision = chapter_service.list_revisions(first.id)[0]

    with pytest.raises(RecordNotFoundError, match="revision"):
        chapter_service.restore_revision(second.id, revision.id)
