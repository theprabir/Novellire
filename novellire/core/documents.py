"""The four workspace documents: the only long-form inputs the author maintains.

The subcategories are guidance, not separate records. They are surfaced as
placeholder text so the editor stays a single document per file.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.document_repository import DocumentRepository, ProjectDocument
from ..storage.repositories import ProjectRepository
from .validation import clean_optional_text

CONTENT_MAX_LENGTH = 400_000


@dataclass(frozen=True)
class WorkspaceDocument:
    """Metadata for one writable workspace document."""

    kind: str
    title: str
    summary: str
    placeholder: str


WORKSPACE_DOCUMENTS: tuple[WorkspaceDocument, ...] = (
    WorkspaceDocument(
        kind="master_bible",
        title="Master Story Bible",
        summary="The permanent source of truth for the novel.",
        placeholder=(
            "Complete storyline\n"
            "Themes and metaphysics\n"
            "Historical background\n"
            "World rules\n"
            "Important events"
        ),
    ),
    WorkspaceDocument(
        kind="character_bible",
        title="Character Bible",
        summary="Everything the AI needs to know about your characters.",
        placeholder=(
            "Personalities and motivations\n"
            "Physical descriptions\n"
            "Relationships and romantic developments\n"
            "Secrets and internal conflicts\n"
            "Character arcs"
        ),
    ),
    WorkspaceDocument(
        kind="chapter_map",
        title="Chapter Map",
        summary="Your complete novel blueprint, chapter by chapter.",
        placeholder=(
            "Chapter objectives\n"
            "Key events\n"
            "Emotional progression\n"
            "Plot revelations\n"
            "Cliffhangers"
        ),
    ),
    WorkspaceDocument(
        kind="style_guide",
        title="Style Guide",
        summary="The literary identity of your novel.",
        placeholder=(
            "Narrative perspective\n"
            "Sentence structure\n"
            "Vocabulary\n"
            "Dialogue style\n"
            "Descriptive density\n"
            "Emotional intensity\n"
            "Rules about what to avoid"
        ),
    ),
)

DOCUMENT_KINDS: tuple[str, ...] = tuple(item.kind for item in WORKSPACE_DOCUMENTS)
DOCUMENTS_BY_KIND = {item.kind: item for item in WORKSPACE_DOCUMENTS}


class ProjectDocumentService:
    """Read and save project documents, always project-scoped."""

    def __init__(
        self,
        repository: DocumentRepository,
        projects: ProjectRepository,
    ) -> None:
        self._repository = repository
        self._projects = projects

    def list_documents(self, project_id: int) -> list[dict[str, object]]:
        self._require_project(project_id)
        stored = {doc.kind: doc for doc in self._repository.list_for_project(project_id)}
        payload: list[dict[str, object]] = []
        for definition in WORKSPACE_DOCUMENTS:
            record = stored.get(definition.kind)
            payload.append(
                {
                    "kind": definition.kind,
                    "title": definition.title,
                    "summary": definition.summary,
                    "placeholder": definition.placeholder,
                    "content": record.content if record else "",
                    "derived": record.derived if record else False,
                    "updated_at": record.updated_at if record else None,
                }
            )
        return payload

    def get_document(self, project_id: int, kind: str) -> ProjectDocument | None:
        self._require_kind(kind)
        return self._repository.get(project_id, kind)

    def save_document(self, project_id: int, kind: str, content: str) -> ProjectDocument:
        self._require_project(project_id)
        self._require_kind(kind)
        cleaned = clean_optional_text(
            content, "Document content", max_length=CONTENT_MAX_LENGTH
        )
        return self._repository.upsert(project_id, kind, content=cleaned, derived=False)

    def save_derived(
        self, project_id: int, kind: str, content: str
    ) -> ProjectDocument:
        self._require_project(project_id)
        self._require_kind(kind)
        return self._repository.upsert(project_id, kind, content=content, derived=True)

    def context_for_prompt(self, project_id: int) -> dict[str, str]:
        """Return the stored documents keyed by kind, for prompt assembly."""
        context: dict[str, str] = {}
        for record in self._repository.list_for_project(project_id):
            if record.content.strip():
                context[record.kind] = record.content
        return context

    def _require_project(self, project_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )

    def _require_kind(self, kind: str) -> None:
        if kind not in DOCUMENTS_BY_KIND:
            raise InvalidInputError("That document does not exist.")
