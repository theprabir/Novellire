"""Timeline validation: recorded story days against narrative chapter order.

Chapter position is narrative order. An optional story-day anchor says when a
chapter happens in the story's own calendar, counted from the story start (day
zero). Validation is deterministic: it compares anchors the author recorded and
never calls a model, so every finding is a fact about the stored timeline rather
than a guess, and a flashback remains the author's decision to make.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..errors import ProjectNotFoundError
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRepository

STORY_DAY_MAX = 1_000_000


@dataclass(frozen=True)
class TimelineFinding:
    id: int
    kind: str
    severity: str
    chapter_id: int
    position: int
    title: str
    story_day: int
    previous_position: int
    previous_title: str
    previous_day: int
    detail: str


class TimelineValidationService:
    """Check recorded story days for chapters that run backwards in time."""

    def __init__(
        self, projects: ProjectRepository, chapters: ChapterRepository
    ) -> None:
        self._projects = projects
        self._chapters = chapters

    def validate(self, project_id: int) -> dict[str, object]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        chapters = self._chapters.list_for_project(project_id)
        anchors: list[dict[str, object]] = []
        findings: list[TimelineFinding] = []
        previous = None
        for chapter in chapters:
            elapsed = (
                chapter.story_day - previous.story_day
                if chapter.story_day is not None
                and previous is not None
                and previous.story_day is not None
                else None
            )
            anchors.append(
                {
                    "chapter_id": chapter.id,
                    "position": chapter.position,
                    "title": chapter.title,
                    "story_day": chapter.story_day,
                    "elapsed": elapsed,
                }
            )
            if chapter.story_day is None:
                continue
            if previous is not None and chapter.story_day < previous.story_day:
                findings.append(
                    TimelineFinding(
                        id=len(findings) + 1,
                        kind="out_of_order",
                        severity="high",
                        chapter_id=chapter.id,
                        position=chapter.position,
                        title=chapter.title,
                        story_day=chapter.story_day,
                        previous_position=previous.position,
                        previous_title=previous.title,
                        previous_day=previous.story_day,
                        detail=(
                            f"Chapter {chapter.position} is anchored to story day "
                            f"{chapter.story_day}, before chapter "
                            f"{previous.position} on day {previous.story_day}. "
                            "Move the chapter or correct one of the days unless "
                            "this is a deliberate flashback."
                        ),
                    )
                )
            previous = chapter

        return {
            "counts": {
                "chapters": len(chapters),
                "anchored": sum(
                    1 for anchor in anchors if anchor["story_day"] is not None
                ),
                "unanchored": sum(
                    1 for anchor in anchors if anchor["story_day"] is None
                ),
                "findings": len(findings),
            },
            "anchors": anchors,
            "findings": [asdict(finding) for finding in findings],
        }
