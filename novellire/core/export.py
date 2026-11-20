"""Compile a project's chapters and documents into a portable manuscript.

Export is deliberately plain: Markdown, plain text, or a Word document, built
from stored chapter text in position order. A non-empty chapter part becomes a
part break, chapter word counts are printed and totalled, and no prose is
rewritten. An empty manuscript is rejected rather than producing a blank file,
and everything is generated locally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.repositories import Project, ProjectRepository
from ..storage.story_repositories import ChapterRecord
from .chapters import ChapterService
from .documents import ProjectDocumentService
from .docx import build_docx

EXPORT_FORMATS = ("markdown", "text", "docx")
_MARKDOWN = "markdown"
_TEXT = "text"
_DOCX = "docx"
_EXTENSIONS = {_MARKDOWN: "md", _TEXT: "txt", _DOCX: "docx"}
_DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@dataclass(frozen=True)
class ExportResult:
    filename: str
    content: str
    file_format: str
    content_type: str
    word_count: int
    data: bytes | None = None


class ExportService:
    """Build downloadable manuscripts for one project."""

    def __init__(
        self,
        projects: ProjectRepository,
        chapters: ChapterService,
        documents: ProjectDocumentService,
    ) -> None:
        self._projects = projects
        self._chapters = chapters
        self._documents = documents

    def build(
        self,
        project_id: int,
        *,
        file_format: str = _MARKDOWN,
        include_documents: bool = False,
    ) -> ExportResult:
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )

        cleaned_format = (file_format or _MARKDOWN).strip().lower()
        if cleaned_format not in EXPORT_FORMATS:
            raise InvalidInputError(
                "Export format must be 'markdown', 'text', or 'docx'."
            )

        chapters = [
            chapter
            for chapter in self._chapters.list_chapters(project_id)
            if chapter.content.strip()
        ]
        if not chapters:
            raise InvalidInputError(
                "Add or draft at least one chapter with text before exporting."
            )

        total_words = sum(chapter.word_count for chapter in chapters)
        metadata = " · ".join(
            value for value in (project.genre, project.narrative_style) if value
        )
        documents = (
            [
                document
                for document in self._documents.list_documents(project.id)
                if str(document["content"]).strip()
            ]
            if include_documents and cleaned_format != _TEXT
            else []
        )

        suffix = "-with-documents" if documents else ""
        filename = f"{_slug(project.name)}{suffix}.{_EXTENSIONS[cleaned_format]}"
        if cleaned_format == _MARKDOWN:
            content = self._markdown(project, chapters, metadata, total_words, documents)
            content_type = "text/markdown; charset=utf-8"
            data = None
        elif cleaned_format == _TEXT:
            content = self._text(project, chapters, metadata, total_words)
            content_type = "text/plain; charset=utf-8"
            data = None
        else:
            content = ""
            content_type = _DOCX_CONTENT_TYPE
            data = build_docx(
                self._docx_entries(project, chapters, metadata, total_words, documents)
            )
        return ExportResult(
            filename=filename,
            content=content,
            file_format=cleaned_format,
            content_type=content_type,
            word_count=total_words,
            data=data,
        )

    def _markdown(
        self,
        project: Project,
        chapters: list[ChapterRecord],
        metadata: str,
        total_words: int,
        documents: list[dict[str, object]],
    ) -> str:
        parts = [f"# {project.name}"]
        if metadata:
            parts.append(f"*{metadata}*")
        parts.append(f"_{_summary(chapters, total_words)}_")

        part = ""
        for chapter in chapters:
            if chapter.part and chapter.part != part:
                part = chapter.part
                parts.append(f"# {part}")
            parts.append(f"## Chapter {chapter.position} — {chapter.title}")
            parts.append(f"*{chapter.word_count:,} words*")
            parts.append(chapter.content)

        if documents:
            parts.append("# Project documents")
            for document in documents:
                parts.append(f"## {document['title']}")
                parts.append(str(document["content"]))

        return "\n\n".join(parts).rstrip() + "\n"

    def _text(
        self,
        project: Project,
        chapters: list[ChapterRecord],
        metadata: str,
        total_words: int,
    ) -> str:
        header = [project.name.upper()]
        if metadata:
            header.append(metadata)
        header.append(_summary(chapters, total_words))

        parts: list[str] = ["\n".join(header)]
        part = ""
        for chapter in chapters:
            if chapter.part and chapter.part != part:
                part = chapter.part
                parts.append(part.upper())
            parts.append(
                f"Chapter {chapter.position} — {chapter.title} "
                f"({chapter.word_count:,} words)"
            )
            parts.append(chapter.content)

        return "\n\n".join(parts).rstrip() + "\n"

    def _docx_entries(
        self,
        project: Project,
        chapters: list[ChapterRecord],
        metadata: str,
        total_words: int,
        documents: list[dict[str, object]],
    ) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = [("title", project.name)]
        if metadata:
            entries.append(("subtitle", metadata))
        entries.append(("summary", _summary(chapters, total_words)))

        part = ""
        for chapter in chapters:
            if chapter.part and chapter.part != part:
                part = chapter.part
                entries.append(("part", part))
            entries.append(
                ("chapter", f"Chapter {chapter.position} — {chapter.title}")
            )
            entries.append(("words", f"{chapter.word_count:,} words"))
            entries.append(("body", chapter.content))

        if documents:
            entries.append(("documents", "Project documents"))
            for document in documents:
                entries.append(("document", str(document["title"])))
                entries.append(("body", str(document["content"])))

        return entries


def _summary(chapters: list[ChapterRecord], total_words: int) -> str:
    return (
        f"{len(chapters)} chapter{'s' if len(chapters) != 1 else ''} · "
        f"{total_words:,} words"
    )


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return cleaned or "manuscript"
