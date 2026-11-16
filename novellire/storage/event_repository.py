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
    "c.title AS chapter_title, c.position AS chapter_position, "
    "COALESCE((SELECT group_concat(ec.character_id) FROM event_characters ec "
    "WHERE ec.event_id = e.id), '') AS character_ids"
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
    character_ids: tuple[int, ...] = ()


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

    def list_unresolved(self, project_id: int) -> list[NarrativeEvent]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS}
                FROM narrative_events e
                JOIN chapters c ON c.id = e.chapter_id
                WHERE e.project_id = ? AND e.links_resolved = 0
                ORDER BY c.position, e.id
                """,
                (project_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def get(self, event_id: int) -> NarrativeEvent | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_COLUMNS}
                FROM narrative_events e
                JOIN chapters c ON c.id = e.chapter_id
                WHERE e.id = ?
                """,
                (event_id,),
            ).fetchone()
        return _row_to_event(row) if row is not None else None

    def list_character_pairs(
        self, project_id: int
    ) -> list[tuple[int, int, int, int]]:
        """Return character pairs with shared-event counts and narrative order.

        Latest provenance follows chapter position, not insertion order, so
        extracting an earlier chapter later does not make it look newest.
        Event id breaks ties within the same chapter.
        """
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT ec_a.character_id AS character_a_id,
                       ec_b.character_id AS character_b_id,
                       ec_a.event_id AS event_id,
                       c.position AS chapter_position
                FROM event_characters ec_a
                JOIN event_characters ec_b
                  ON ec_b.event_id = ec_a.event_id
                 AND ec_b.character_id > ec_a.character_id
                JOIN narrative_events e ON e.id = ec_a.event_id
                JOIN chapters c ON c.id = e.chapter_id
                WHERE e.project_id = ?
                """,
                (project_id,),
            ).fetchall()

        # event_characters has one row per event/character, so the joined
        # rows are already distinct per event and pair.
        pairs: dict[tuple[int, int], tuple[int, tuple[int, int]]] = {}
        for row in rows:
            key = (int(row["character_a_id"]), int(row["character_b_id"]))
            count, latest = pairs.get(key, (0, (-1, -1)))
            candidate = (int(row["chapter_position"]), int(row["event_id"]))
            pairs[key] = (count + 1, max(latest, candidate))

        return sorted(
            (
                (a_id, b_id, count, latest[1])
                for (a_id, b_id), (count, latest) in pairs.items()
            ),
            key=lambda pair: (-pair[2], pair[0], pair[1]),
        )

    def reset_links(self, project_id: int) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE narrative_events SET links_resolved = 0
                WHERE project_id = ?
                """,
                (project_id,),
            )

    def set_character_links(
        self, event_id: int, links: dict[int, str]
    ) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "DELETE FROM event_characters WHERE event_id = ?", (event_id,)
            )
            for character_id, mention in links.items():
                connection.execute(
                    """
                    INSERT INTO event_characters (event_id, character_id, mention)
                    VALUES (?, ?, ?)
                    """,
                    (event_id, character_id, mention),
                )
            connection.execute(
                "UPDATE narrative_events SET links_resolved = 1 WHERE id = ?",
                (event_id,),
            )

    def update(
        self,
        event_id: int,
        *,
        summary: str,
        characters: Sequence[str],
        locations: Sequence[str],
        objects: Sequence[str],
        threads: Sequence[str],
    ) -> NarrativeEvent | None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE narrative_events SET
                    summary = ?, characters = ?, locations = ?, objects = ?,
                    threads = ?, links_resolved = 0
                WHERE id = ?
                """,
                (
                    summary,
                    _encode(characters),
                    _encode(locations),
                    _encode(objects),
                    _encode(threads),
                    event_id,
                ),
            )
        return self.get(event_id)

    def delete(self, event_id: int) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM narrative_events WHERE id = ?", (event_id,)
            )
            return cursor.rowcount > 0

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
        character_ids=tuple(
            int(value)
            for value in str(row["character_ids"] or "").split(",")
            if value
        ),
    )
