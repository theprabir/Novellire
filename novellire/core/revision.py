"""A revision checklist built from measured prose, without a model.

The plan points at exact passages: sentences over the long-sentence limit,
paragraphs over the dense-paragraph limit, and repeated phrases the pacing
review found in a chapter. Each item says what was measured and one concrete
next step, so the author decides what to change. Nothing is rewritten, and no
state is stored: an item disappears as soon as the prose changes, which keeps
the plan honest without a dismissal list to maintain.
"""

from __future__ import annotations

import re

from ..errors import ProjectNotFoundError
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRecord, ChapterRepository
from .pacing import PacingReviewService
from .style import STYLE_LONG_SENTENCE_WORDS
from .text import split_sentences

REVISION_DENSE_PARAGRAPH_WORDS = 180
REVISION_DENSE_PARAGRAPH_HIGH = 300
REVISION_MAX_ITEMS = 6
REVISION_QUOTE_CHARS = 300

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_KIND_LABELS = {
    "long_sentence": "Long sentence",
    "dense_paragraph": "Dense paragraph",
    "repetition": "Repeated phrase",
}


class RevisionPlanService:
    """Locate measured problems and suggest the smallest next step. No model."""

    def __init__(
        self,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        pacing: PacingReviewService,
    ) -> None:
        self._projects = projects
        self._chapters = chapters
        self._pacing = pacing

    def plan(self, project_id: int) -> dict[str, object]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        chapters = [
            chapter
            for chapter in self._chapters.list_for_project(project_id)
            if (chapter.content or "").strip()
        ]
        pacing = self._pacing.review(project_id)
        repeated: dict[int, list[dict[str, object]]] = {}
        for finding in pacing["repetitions"]:  # type: ignore[index]
            for occurrence in finding["occurrences"]:
                repeated.setdefault(occurrence["chapter_position"], []).append(
                    finding
                )

        rows = []
        for chapter in chapters:
            items = _chapter_items(chapter, repeated.get(chapter.position, []))
            if not items:
                continue
            rows.append(
                {
                    "id": chapter.id,
                    "position": chapter.position,
                    "title": chapter.title,
                    "words": chapter.word_count,
                    "items": items,
                }
            )

        return {
            "counts": {
                "chapters": len(chapters),
                "chapters_with_items": len(rows),
                "items": sum(len(row["items"]) for row in rows),
            },
            "chapters": rows,
        }


def _chapter_items(
    chapter: ChapterRecord, repetitions: list[dict[str, object]]
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for sentence in split_sentences(chapter.content):
        words = len(sentence.split())
        if words <= STYLE_LONG_SENTENCE_WORDS:
            continue
        items.append(
            {
                "kind": "long_sentence",
                "severity": "high" if words >= STYLE_LONG_SENTENCE_WORDS * 2 else "medium",
                "quote": _clip(sentence),
                "detail": f"{words} words in one sentence.",
                "suggestion": "Split it at a natural pause, or cut a clause.",
            }
        )

    for paragraph in re.split(r"\n\s*\n", chapter.content or ""):
        words = len(paragraph.split())
        if words <= REVISION_DENSE_PARAGRAPH_WORDS:
            continue
        items.append(
            {
                "kind": "dense_paragraph",
                "severity": (
                    "high" if words >= REVISION_DENSE_PARAGRAPH_HIGH else "medium"
                ),
                "quote": _clip(paragraph),
                "detail": f"{words} words in one paragraph.",
                "suggestion": "Break it where the subject or scene shifts.",
            }
        )

    seen: set[str] = set()
    for finding in repetitions:
        phrase = str(finding["phrase"])
        if phrase in seen:
            continue
        seen.add(phrase)
        items.append(
            {
                "kind": "repetition",
                "severity": "low",
                "quote": phrase,
                "detail": (
                    f"“{phrase}” appears {finding['count']} times across the "
                    "manuscript."
                ),
                "suggestion": (
                    "Vary one occurrence, or keep it as a deliberate refrain."
                ),
            }
        )

    items.sort(
        key=lambda item: (
            _SEVERITY_ORDER[str(item["severity"])],
            _KIND_LABELS[str(item["kind"])],
            str(item["quote"]),
        )
    )
    items = items[:REVISION_MAX_ITEMS]
    for index, item in enumerate(items, start=1):
        item["id"] = index
    return items


def _clip(text: str) -> str:
    return " ".join((text or "").split())[:REVISION_QUOTE_CHARS].strip()
