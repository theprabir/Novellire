"""Story bible service: categorised, project-scoped narrative documentation."""

from __future__ import annotations

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.story_repositories import StoryBibleEntry, StoryBibleRepository
from ..storage.repositories import ProjectRepository
from .validation import clean_optional_text, clean_required_text

# Categories required by PROJECT_SPEC.md section 3.2, with display labels.
STORY_BIBLE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("premise", "Premise"),
    ("main_storyline", "Main storyline"),
    ("subplots", "Subplots"),
    ("themes", "Themes"),
    ("narrative_structure", "Narrative structure"),
    ("world_building", "World-building"),
    ("historical_background", "Historical background"),
    ("geography", "Geography"),
    ("technology", "Technology"),
    ("metaphysical_rules", "Metaphysical rules"),
    ("cultural_systems", "Cultural systems"),
    ("important_objects", "Important objects"),
    ("organizations", "Organizations"),
    ("locations", "Locations"),
    ("terminology", "Terminology"),
)

CATEGORY_LABELS: dict[str, str] = dict(STORY_BIBLE_CATEGORIES)
CATEGORY_KEYS: tuple[str, ...] = tuple(CATEGORY_LABELS)
CATEGORY_BY_LABEL: dict[str, str] = {
    label: key for key, label in STORY_BIBLE_CATEGORIES
}

TITLE_MAX_LENGTH = 200
CONTENT_MAX_LENGTH = 200_000


class StoryBibleService:
    """Create, list, and update story bible entries for a project."""

    def __init__(
        self, repository: StoryBibleRepository, projects: ProjectRepository
    ) -> None:
        self._repository = repository
        self._projects = projects

    def create_entry(
        self, *, project_id: int, category: str, title: str, content: str = ""
    ) -> StoryBibleEntry:
        self._require_project(project_id)
        return self._repository.create(
            project_id=project_id,
            category=_clean_category(category),
            title=clean_required_text(title, "Title", max_length=TITLE_MAX_LENGTH),
            content=clean_optional_text(
                content, "Content", max_length=CONTENT_MAX_LENGTH
            ),
        )

    def list_entries(
        self, project_id: int, *, category: str | None = None
    ) -> list[StoryBibleEntry]:
        if category is not None:
            category = _clean_category(category)
        return self._repository.list_for_project(project_id, category=category)

    def update_entry(
        self,
        entry_id: int,
        *,
        category: str | None = None,
        title: str | None = None,
        content: str | None = None,
    ) -> StoryBibleEntry:
        fields: dict[str, object] = {}
        if category is not None:
            fields["category"] = _clean_category(category)
        if title is not None:
            fields["title"] = clean_required_text(
                title, "Title", max_length=TITLE_MAX_LENGTH
            )
        if content is not None:
            fields["content"] = clean_optional_text(
                content, "Content", max_length=CONTENT_MAX_LENGTH
            )
        return self._repository.update(entry_id, **fields)

    def _require_project(self, project_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )


def _clean_category(category: str) -> str:
    cleaned = (category or "").strip().lower()
    if cleaned not in CATEGORY_LABELS:
        raise InvalidInputError(
            "Category must be one of: "
            + ", ".join(CATEGORY_LABELS[key] for key in CATEGORY_KEYS)
            + "."
        )
    return cleaned
