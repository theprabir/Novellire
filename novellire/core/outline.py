"""Parse the Chapter Map and create missing chapter records from it.

The Chapter Map is the macro outline. Its headings use an explicit, predictable
format so outline sync never has to guess at structure:

    ## Chapter 1: The Missing Face
    Optional plan text for this chapter...

Sync is additive: existing chapters are reported and left untouched. Deleting or
rewriting authored chapters is never part of applying an outline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import InvalidInputError
from ..storage.story_repositories import ChapterRecord
from .chapters import ChapterService
from .documents import ProjectDocumentService

MAX_OUTLINE_CHAPTERS = 500

_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?chapter\s+(\d+)\b(.*)$",
    re.IGNORECASE,
)
_LEADING_SEPARATOR = re.compile(r"^[\s:—–\-]+")
_TRAILING_MARKUP = re.compile(r"\*+\s*$")


@dataclass(frozen=True)
class OutlineEntry:
    number: int
    title: str
    objectives: str


@dataclass(frozen=True)
class OutlineItem:
    number: int
    title: str
    objectives: str
    action: str  # create | exists
    chapter_id: int | None = None


@dataclass(frozen=True)
class OutlinePreview:
    items: tuple[OutlineItem, ...]

    @property
    def create_count(self) -> int:
        return sum(1 for item in self.items if item.action == "create")

    @property
    def existing_count(self) -> int:
        return sum(1 for item in self.items if item.action == "exists")


@dataclass(frozen=True)
class OutlineApplyResult:
    created: tuple[ChapterRecord, ...]
    existing_count: int


def parse_chapter_map(content: str) -> list[OutlineEntry]:
    """Return ordered outline entries from Chapter Map text.

    Headings must be numbered from 1 without gaps, so applying the outline can
    create positions without inventing placeholder chapters. Body text below a
    heading becomes that chapter's scene plan.
    """
    entries: list[OutlineEntry] = []
    current_number: int | None = None
    current_title = ""
    body: list[str] = []

    def finish() -> None:
        if current_number is None:
            return
        entries.append(
            OutlineEntry(
                number=current_number,
                title=current_title or f"Chapter {current_number}",
                objectives="\n".join(body).strip(),
            )
        )

    for line in (content or "").splitlines():
        match = _HEADING.match(line)
        if match is None:
            if current_number is not None:
                body.append(line)
            continue
        finish()
        current_number = int(match.group(1))
        title = _TRAILING_MARKUP.sub("", match.group(2).strip())
        current_title = _LEADING_SEPARATOR.sub("", title).strip()
        body = []

    finish()

    if not entries:
        raise InvalidInputError(
            "No chapters were found. Add headings such as "
            "“## Chapter 1: The Missing Face” to the Chapter Map."
        )
    if len(entries) > MAX_OUTLINE_CHAPTERS:
        raise InvalidInputError(
            f"The Chapter Map has more than {MAX_OUTLINE_CHAPTERS} chapters."
        )

    numbers = [entry.number for entry in entries]
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        listed = ", ".join(str(number) for number in duplicates)
        raise InvalidInputError(
            f"Chapter numbers must be unique. Duplicate number(s): {listed}."
        )
    expected = list(range(1, max(numbers) + 1))
    if sorted(numbers) != expected:
        raise InvalidInputError(
            "Chapter numbers must run from 1 without gaps so the outline can be "
            "applied in order."
        )

    return sorted(entries, key=lambda entry: entry.number)


class OutlineService:
    """Preview and apply the saved Chapter Map's chapter structure."""

    def __init__(
        self,
        documents: ProjectDocumentService,
        chapters: ChapterService,
    ) -> None:
        self._documents = documents
        self._chapters = chapters

    def preview(self, project_id: int) -> OutlinePreview:
        document = self._documents.get_document(project_id, "chapter_map")
        if document is None or not document.content.strip():
            raise InvalidInputError(
                "Write the Chapter Map before building chapters from it."
            )
        entries = parse_chapter_map(document.content)
        existing = {
            chapter.position: chapter
            for chapter in self._chapters.list_chapters(project_id)
        }
        items = []
        for entry in entries:
            chapter = existing.get(entry.number)
            items.append(
                OutlineItem(
                    number=entry.number,
                    title=entry.title,
                    objectives=entry.objectives,
                    action="exists" if chapter is not None else "create",
                    chapter_id=chapter.id if chapter is not None else None,
                )
            )
        return OutlinePreview(items=tuple(items))

    def apply(self, project_id: int) -> OutlineApplyResult:
        preview = self.preview(project_id)
        created = []
        for item in preview.items:
            if item.action != "create":
                continue
            created.append(
                self._chapters.create_chapter(
                    project_id=project_id,
                    title=item.title,
                    objectives=item.objectives,
                    position=item.number,
                )
            )
        return OutlineApplyResult(
            created=tuple(created), existing_count=preview.existing_count
        )
