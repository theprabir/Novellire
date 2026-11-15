"""Project memory: searchable chapter summaries, prose, and documents."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.repositories import ProjectRepository
from ..storage.search_repository import SearchRepository
from .documents import DOCUMENTS_BY_KIND


@dataclass(frozen=True)
class MemoryHit:
    kind: str
    title: str
    source_id: int
    excerpt: str


class MemoryService:
    """Search one project's full-text index and label the results."""

    def __init__(
        self, repository: SearchRepository, projects: ProjectRepository
    ) -> None:
        self._repository = repository
        self._projects = projects

    def search(
        self, project_id: int, query: str, *, limit: int = 20
    ) -> list[MemoryHit]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        cleaned = (query or "").strip()
        if not cleaned:
            raise InvalidInputError("Enter a word or phrase to search.")

        hits: list[MemoryHit] = []
        for hit in self._repository.search(project_id, cleaned, limit=limit):
            document = DOCUMENTS_BY_KIND.get(hit.source_kind)
            title = document.title if document is not None else hit.title
            hits.append(
                MemoryHit(
                    kind=hit.source_kind,
                    title=title or hit.title,
                    source_id=hit.source_id,
                    excerpt=hit.excerpt,
                )
            )
        return hits
