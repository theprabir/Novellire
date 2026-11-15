"""Manuscript export tests."""

from __future__ import annotations

import pytest

from novellire.core.documents import ProjectDocumentService
from novellire.core.export import ExportService
from novellire.errors import InvalidInputError
from novellire.storage.document_repository import DocumentRepository


@pytest.fixture()
def document_service(database, project_repository) -> ProjectDocumentService:
    return ProjectDocumentService(DocumentRepository(database), project_repository)


@pytest.fixture()
def export_service(
    project_repository, chapter_service, document_service
) -> ExportService:
    return ExportService(project_repository, chapter_service, document_service)


def _write_two_chapters(chapter_service, project) -> None:
    chapter_service.create_chapter(
        project_id=project.id,
        title="The Gate",
        content="Mira opened the gate.",
    )
    chapter_service.create_chapter(
        project_id=project.id,
        title="The Fall",
        content="Ash covered the square.",
    )


def test_markdown_export_orders_chapters_and_appends_documents(
    export_service: ExportService,
    chapter_service,
    document_service: ProjectDocumentService,
    sample_project,
) -> None:
    _write_two_chapters(chapter_service, sample_project)
    document_service.save_document(
        sample_project.id, "master_bible", "The gate is sealed with iron."
    )

    result = export_service.build(sample_project.id, include_documents=True)

    assert result.filename == "ashfall-with-documents.md"
    assert result.content_type.startswith("text/markdown")
    assert result.content.index("## Chapter 1 — The Gate") < result.content.index(
        "## Chapter 2 — The Fall"
    )
    assert "Mira opened the gate." in result.content
    assert "# Project documents" in result.content
    assert "The gate is sealed with iron." in result.content
    assert result.word_count == 8


def test_text_export_omits_markdown_and_documents(
    export_service: ExportService,
    chapter_service,
    document_service: ProjectDocumentService,
    sample_project,
) -> None:
    _write_two_chapters(chapter_service, sample_project)
    document_service.save_document(
        sample_project.id, "master_bible", "The gate is sealed with iron."
    )

    result = export_service.build(
        sample_project.id, file_format="text", include_documents=True
    )

    assert result.filename == "ashfall.txt"
    assert result.content_type.startswith("text/plain")
    assert "Chapter 1 — The Gate" in result.content
    assert "## Chapter" not in result.content
    assert "Project documents" not in result.content


def test_export_rejects_an_empty_manuscript(
    export_service: ExportService, sample_project
) -> None:
    with pytest.raises(InvalidInputError, match="at least one chapter"):
        export_service.build(sample_project.id)


def test_export_rejects_an_unknown_format(
    export_service: ExportService, chapter_service, sample_project
) -> None:
    _write_two_chapters(chapter_service, sample_project)

    with pytest.raises(InvalidInputError, match="format"):
        export_service.build(sample_project.id, file_format="docx")
