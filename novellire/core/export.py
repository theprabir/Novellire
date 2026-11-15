"""Compile a project's chapters and documents into a portable manuscript.

Export is deliberately plain: Markdown or text, built from stored chapter text in
position order. No prose is rewritten, and an empty manuscript is rejected rather
than producing a blank file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.repositories import Project, ProjectRepository
from ..storage.story_repositories import ChapterRecord
from .chapters import ChapterService
from .documents import ProjectDocumentService
from .text import count_words

EXPORT_FORMATS = ("markdown", "text")
_MARKDOWN = "markdown"
_TEXT = "text"
_EXTENSIONS = {_MARKDOWN: "md", _TEXT: "txt"}


@dataclass(frozen=True)
class ExportResult:
    filename: str
    content: str
    file_format: str
    content_type: str
    word_count: int


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
            raise InvalidInputError("Export format must be 'markdown' or 'text'.")

        chapters = [
            chapter
            for chapter in self._chapters.list_chapters(project_id)
            if chapter.content.strip()
        ]
        if not chapters:
            raise InvalidInputError(
                "Add or draft at least one chapter with text before exporting."
            )

        if cleaned_format == _MARKDOWN:
            content = self._markdown(project, chapters, include_documents)
            content_type = "text/markdown; charset=utf-8"
        else:
            content = self._text(project, chapters)
            content_type = "text/plain; charset=utf-8"

        suffix = "-with-documents" if include_documents and cleaned_format == _MARKDOWN else ""
        return ExportResult(
            filename=f"{_slug(project.name)}{suffix}.{_EXTENSIONS[cleaned_format]}",
            content=content,
            file_format=cleaned_format,
            content_type=content_type,
            word_count=sum(chapter.word_count for chapter in chapters),
        )

    def _markdown(
        self, project: Project, chapters: list[ChapterRecord], include_documents: bool
    ) -> str:
        parts = [f"# {project.name}"]
        meta = " · ".join(
            value for value in (project.genre, project.narrative_style) if value
        )
        if meta:
            parts.append(f"*{meta}*")

        for chapter in chapters:
            parts.append(f"## Chapter {chapter.position} — {chapter.title}")
            parts.append(chapter.content)

        if include_documents:
            documents = [
                document
                for document in self._documents.list_documents(project.id)
                if str(document["content"]).strip()
            ]
            if documents:
                parts.append("# Project documents")
                for document in documents:
                    parts.append(f"## {document['title']}")
                    parts.append(str(document["content"]))

        return "\n\n".join(parts).rstrip() + "\n"

    def _text(self, project: Project, chapters: list[ChapterRecord]) -> str:
        header = [project.name.upper()]
        meta = " · ".join(
            value for value in (project.genre, project.narrative_style) if value
        )
        if meta:
            header.append(meta)

        parts = [header]
        for chapter in chapters:
            parts.append([f"Chapter {chapter.position} — {chapter.title}", chapter.content])

        lines = ["\n".join(part) if isinstance(part, list) else str(part) for part in parts]
        return "\n\n".join(lines).rstrip() + "\n"


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return cleaned or "manuscript"
