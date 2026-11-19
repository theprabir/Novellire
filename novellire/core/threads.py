"""Author decisions about recorded plot threads.

Threads come from extracted events. Resolving one records where and how it paid
off; reopening removes that decision. Neither changes the events themselves, so
no narrative content is rewritten by this slice.
"""

from __future__ import annotations

from ..errors import InvalidInputError, ProjectNotFoundError
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRepository
from ..storage.thread_repository import (
    ThreadResolution,
    ThreadResolutionRepository,
)

THREAD_TEXT_LIMIT = 300
THREAD_NOTE_LIMIT = 1_000
THREAD_STATUSES = ("open", "resolved")


def thread_key(thread: str) -> str:
    """Match a thread regardless of spacing or case."""
    return " ".join(thread.split()).casefold()


class ThreadService:
    def __init__(
        self,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        threads: ThreadResolutionRepository,
    ) -> None:
        self._projects = projects
        self._chapters = chapters
        self._threads = threads

    def set_status(
        self,
        project_id: int,
        *,
        thread: str,
        status: str,
        note: str = "",
        chapter_id: int | None = None,
    ) -> ThreadResolution | None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        cleaned = " ".join((thread or "").split())
        if not cleaned:
            raise InvalidInputError("Choose a recorded thread first.")
        if len(cleaned) > THREAD_TEXT_LIMIT:
            raise InvalidInputError(
                f"That thread text is {len(cleaned):,} characters, longer than "
                f"the {THREAD_TEXT_LIMIT:,}-character limit."
            )
        normalized = (status or "").strip().casefold()
        if normalized not in THREAD_STATUSES:
            raise InvalidInputError("Choose a valid thread status.")
        if chapter_id is not None:
            chapter = self._chapters.get(chapter_id)
            if chapter is None or chapter.project_id != project_id:
                raise InvalidInputError("Choose a chapter from this project.")
        key = thread_key(cleaned)
        if normalized == "open":
            self._threads.delete_for_thread(project_id, key)
            return None
        return self._threads.upsert(
            project_id=project_id,
            thread_key=key,
            thread=cleaned,
            status="resolved",
            note=_note(note),
            chapter_id=chapter_id,
        )


def _note(note: str) -> str:
    return " ".join((note or "").split())[:THREAD_NOTE_LIMIT].strip()
