"""Manuscript export tests."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from novellire.api.app import create_app
from novellire.config import AnalysisSettings, GenerationDefaults, Settings
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


def test_a_one_word_chapter_reads_naturally(
    export_service: ExportService, chapter_service, sample_project
) -> None:
    chapter_service.create_chapter(
        project_id=sample_project.id, title="Ash", content="Ash."
    )

    result = export_service.build(sample_project.id)

    assert "*1 word*" in result.content
    assert "_1 chapter · 1 word_" in result.content


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
        export_service.build(sample_project.id, file_format="pdf")


def _write_parts(chapter_service, project) -> None:
    chapter_service.create_chapter(
        project_id=project.id,
        title="The Gate",
        part="Part One",
        content="Mira opened the gate.",
    )
    chapter_service.create_chapter(
        project_id=project.id,
        title="The Fall",
        part="Part One",
        content="Ash covered the square.",
    )
    chapter_service.create_chapter(
        project_id=project.id,
        title="The Road",
        part="Part Two",
        content="They left at dawn.",
    )


def test_markdown_export_prints_each_part_once_and_chapter_word_counts(
    export_service: ExportService, chapter_service, sample_project
) -> None:
    _write_parts(chapter_service, sample_project)

    result = export_service.build(sample_project.id)

    content = result.content
    assert content.count("# Part One") == 1
    assert content.count("# Part Two") == 1
    assert content.index("# Part One") < content.index("## Chapter 1 — The Gate")
    assert content.index("## Chapter 2 — The Fall") < content.index("# Part Two")
    assert content.index("# Part Two") < content.index("## Chapter 3 — The Road")
    assert "*4 words*" in content
    assert "_3 chapters · 12 words_" in content
    assert result.word_count == 12


def test_text_export_names_parts_and_chapter_word_counts(
    export_service: ExportService, chapter_service, sample_project
) -> None:
    _write_parts(chapter_service, sample_project)

    result = export_service.build(sample_project.id, file_format="text")

    assert result.content.index("PART ONE") < result.content.index(
        "Chapter 1 — The Gate"
    )
    assert result.content.index("PART TWO") < result.content.index(
        "Chapter 3 — The Road"
    )
    assert "Chapter 1 — The Gate (4 words)" in result.content
    assert "3 chapters · 12 words" in result.content


def test_docx_export_is_a_word_package_with_headings_and_counts(
    export_service: ExportService, chapter_service, sample_project
) -> None:
    _write_parts(chapter_service, sample_project)

    result = export_service.build(sample_project.id, file_format="docx")

    assert result.filename == "ashfall.docx"
    assert result.content == ""
    assert result.content_type.startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert result.word_count == 12
    assert result.data is not None and result.data.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        names = set(archive.namelist())
        document = archive.read("word/document.xml").decode("utf-8")
        styles = archive.read("word/styles.xml").decode("utf-8")
    assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml"} <= names
    assert ElementTree.fromstring(document) is not None
    assert ElementTree.fromstring(styles) is not None
    assert "Chapter 1 — The Gate" in document
    assert "Part Two" in document
    assert document.count("Part One") == 1
    assert "4 words" in document
    assert 'w:val="Heading2"' in document
    assert 'w:styleId="Heading1"' in styles


def test_api_serves_the_docx_as_an_attachment(
    database, fake_provider, sample_project, chapter_service, tmp_path: Path
) -> None:
    _write_parts(chapter_service, sample_project)
    settings = Settings(
        data_dir=tmp_path / "api-data",
        generation=GenerationDefaults(model="fake-model"),
        analysis=AnalysisSettings(auto_run=False),
    )
    with TestClient(
        create_app(settings=settings, database=database, provider=fake_provider)
    ) as client:
        response = client.get(
            f"/api/projects/{sample_project.id}/export?format=docx"
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == (
        'attachment; filename="ashfall.docx"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "Chapter 3 — The Road" in document
