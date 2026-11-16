"""Persistence for extracted episodic events.

Each row is one event with the entities it involves and any unresolved thread it
raises. Events always point at the chapter they came from, so Memory can show
provenance and deleting a chapter removes its events with it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from .database import Database, utc_now_iso

_COLUMNS = (
    "e.id, e.project_id, e.chapter_id, e.summary, e.characters, e.locations, "
    "e.objects, e.threads, e.model, e.created_at, "
    "c.title AS chapter_title, c.position AS chapter_position"
)


@dataclass(frozen=True)
class EventDraft:
    """An event as extracted from a model response, before storage."""

    summary: str
    characters: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    threads: tuple[str, ...] = ()


@dataclass(frozen=True)
class NarrativeEvent:
    id: int
    project_id: int
    chapter_id: int
    summary: str
    characters: tuple[str, ...]
    locations: tuple[str, ...]
    objects: tuple[str, ...]
    threads: tuple[str, ...]
    model: str
    created_at: str
    chapter_title: str
    chapter_position: int


class EventRepository:
    """Replace and read the episodic events of a project."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def replace_for_chapter(
        self,
        project_id: int,
        chapter_id: int,
        drafts: Sequence[EventDraft],
        *,
        model: str,
    ) -> list[NarrativeEvent]:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            connection.execute(
                "DELETE FROM narrative_events WHERE chapter_id = ?", (chapter_id,)
            )
            for draft in drafts:
                connection.execute(
                    """
                    INSERT INTO narrative_events
                        (project_id, chapter_id, summary, characters, locations,
                         objects, threads, model, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        chapter_id,
                        draft.summary,
                        _encode(draft.characters),
                        _encode(draft.locations),
                        _encode(draft.objects),
                        _encode(draft.threads),
                        model,
                        now,
                    ),
                )
        return self.list_for_chapter(chapter_id)

    def list_for_chapter(self, chapter_id: int) -> list[NarrativeEvent]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS}
                FROM narrative_events e
                JOIN chapters c ON c.id = e.chapter_id
                WHERE e.chapter_id = ?
                ORDER BY e.id
                """,
                (chapter_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_for_project(self, project_id: int) -> list[NarrativeEvent]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS}
                FROM narrative_events e
                JOIN chapters c ON c.id = e.chapter_id
                WHERE e.project_id = ?
                ORDER BY c.position, e.id
                """,
                (project_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]


def _encode(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _decode(value: str) -> tuple[str, ...]:
    try:
        data = json.loads(value or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(str(item) for item in data if isinstance(item, str) and item)


def _row_to_event(row) -> NarrativeEvent:  # noqa: ANN001 - sqlite3.Row
    return NarrativeEvent(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        chapter_id=int(row["chapter_id"]),
        summary=str(row["summary"]),
        characters=_decode(row["characters"]),
        locations=_decode(row["locations"]),
        objects=_decode(row["objects"]),
        threads=_decode(row["threads"]),
        model=str(row["model"]),
        created_at=str(row["created_at"]),
        chapter_title=str(row["chapter_title"]),
        chapter_position=int(row["chapter_position"]),
    )
