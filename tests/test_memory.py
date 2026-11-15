"""Chapter summary generation and full-text memory search."""

from __future__ import annotations

import pytest

from novellire.core.documents import ProjectDocumentService
from novellire.core.memory import MemoryService
from novellire.core.settings_service import GenerationSettings
from novellire.core.summaries import ChapterSummaryService
from novellire.errors import InvalidInputError
from novellire.storage.document_repository import DocumentRepository
from novellire.storage.search_repository import SearchRepository


@pytest.fixture()
def memory_service(database, project_repository) -> MemoryService:
    return MemoryService(SearchRepository(database), project_repository)


@pytest.fixture()
def document_service(database, project_repository) -> ProjectDocumentService:
    return ProjectDocumentService(DocumentRepository(database), project_repository)


@pytest.fixture()
def summary_service(
    fake_provider, project_repository, chapter_service
) -> ChapterSummaryService:
    return ChapterSummaryService(fake_provider, project_repository, chapter_service)


def test_search_finds_chapter_prose(
    memory_service: MemoryService, chapter_service, sample_project
) -> None:
    chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira crossed the ash square without looking back.",
    )

    hits = memory_service.search(sample_project.id, "ash")

    assert len(hits) == 1
    assert hits[0].kind == "chapter"
    assert hits[0].title == "The Gate"
    assert "ash" in hits[0].excerpt.lower()


def test_search_labels_documents_with_their_display_title(
    memory_service: MemoryService,
    document_service: ProjectDocumentService,
    sample_project,
) -> None:
    document_service.save_document(
        sample_project.id, "master_bible", "The star is dimming, not dying."
    )

    hits = memory_service.search(sample_project.id, "dimming")

    assert len(hits) == 1
    assert hits[0].kind == "master_bible"
    assert hits[0].title == "Master Story Bible"


def test_updating_a_document_reindexes_it(
    memory_service: MemoryService,
    document_service: ProjectDocumentService,
    sample_project,
) -> None:
    document_service.save_document(
        sample_project.id, "master_bible", "The star is dimming."
    )
    assert memory_service.search(sample_project.id, "star")

    document_service.save_document(
        sample_project.id, "master_bible", "The moon is rising."
    )

    assert memory_service.search(sample_project.id, "star") == []
    assert [hit.kind for hit in memory_service.search(sample_project.id, "moon")] == [
        "master_bible"
    ]


def test_search_matches_stored_summaries(
    memory_service: MemoryService, chapter_service, sample_project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="The gate opened.",
    )
    chapter_service.update_chapter(
        chapter.id, summary="Mira confronts the keeper of the archive."
    )

    hits = memory_service.search(sample_project.id, "keeper")

    assert [hit.kind for hit in hits] == ["chapter"]
    assert "keeper" in hits[0].excerpt.lower()


def test_search_is_scoped_to_one_project(
    memory_service: MemoryService, chapter_service, project_service, sample_project
) -> None:
    chapter_service.create_chapter(
        project_id=sample_project.id, title="One", content="Ash on the square."
    )
    other = project_service.create_project(name="Other Book")
    chapter_service.create_chapter(
        project_id=other.id, title="Two", content="Ash on a different square."
    )

    hits = memory_service.search(sample_project.id, "ash")

    assert [hit.title for hit in hits] == ["One"]


def test_deleting_a_chapter_removes_it_from_the_index(
    memory_service: MemoryService, chapter_service, sample_project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="One", content="Ash on the square."
    )
    assert memory_service.search(sample_project.id, "ash")

    chapter_service.delete_chapter(chapter.id)

    assert memory_service.search(sample_project.id, "ash") == []


def test_blank_search_is_rejected(
    memory_service: MemoryService, sample_project
) -> None:
    with pytest.raises(InvalidInputError, match="Enter a word"):
        memory_service.search(sample_project.id, "   ")


def test_chapter_summary_is_generated_and_stored(
    summary_service: ChapterSummaryService,
    chapter_service,
    fake_provider,
    sample_project,
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id,
        title="The Gate",
        content="Mira pressed the archive key to her palm.",
    )

    outcome = summary_service.summarize(
        chapter.id, GenerationSettings(model="fake-model")
    )

    assert outcome.chapter.summary == " ".join(["word"] * 120)
    assert outcome.duration_ms == 42
    request = fake_provider.requests[0]
    assert "Mira pressed the archive key" in request.prompt
    assert "Chapter 1 — The Gate" in request.prompt
    assert "80 to 150 words" in request.prompt


def test_summary_requires_chapter_text(
    summary_service: ChapterSummaryService, chapter_service, sample_project
) -> None:
    chapter = chapter_service.create_chapter(
        project_id=sample_project.id, title="Empty"
    )

    with pytest.raises(InvalidInputError, match="Add chapter text"):
        summary_service.summarize(
            chapter.id, GenerationSettings(model="fake-model")
        )
