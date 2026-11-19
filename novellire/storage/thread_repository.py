"""Persistence for author decisions about recorded plot threads.

A row is only written when the author resolves a thread; reopening deletes it.
Threads themselves stay in the events that raised them, so this table never
duplicates narrative content.
"""

from __future__ import annotations

from dataclasses import dataclass

from .database import Database, utc_now_iso

_COLUMNS = """
    t.id, t.project_id, t.thread_key, t.thread, t.status, t.note,
    t.chapter_id, c.title AS chapter_title, c.position AS chapter_position,
    t.created_at, t.updated_at
"""

_FROM = """
    FROM thread_resolutions t
    LEFT JOIN chapters c ON c.id = t.chapter_id
"""


@dataclass(frozen=True)
class ThreadResolution:
    id: int
    project_id: int
    thread_key: str
    thread: str
    status: str
    note: str
    chapter_id: int | None
    chapter_title: str
    chapter_position: int | None
    created_at: str
    updated_at: str


class ThreadResolutionRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def list_for_project(self, project_id: int) -> list[ThreadResolution]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} {_FROM} WHERE t.project_id = ? ORDER BY t.id",
                (project_id,),
            ).fetchall()
        return [_row_to_resolution(row) for row in rows]

    def upsert(
        self,
        *,
        project_id: int,
        thread_key: str,
        thread: str,
        status: str,
        note: str,
        chapter_id: int | None,
    ) -> ThreadResolution:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO thread_resolutions
                    (project_id, thread_key, thread, status, note, chapter_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (project_id, thread_key) DO UPDATE SET
                    thread = excluded.thread,
                    status = excluded.status,
                    note = excluded.note,
                    chapter_id = excluded.chapter_id,
                    updated_at = excluded.updated_at
                """,
                (
                    project_id,
                    thread_key,
                    thread,
                    status,
                    note,
                    chapter_id,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                f"SELECT {_COLUMNS} {_FROM} WHERE t.project_id = ? AND t.thread_key = ?",
                (project_id, thread_key),
            ).fetchone()
        if row is None:
            raise RuntimeError("The thread resolution could not be reloaded.")
        return _row_to_resolution(row)

    def delete_for_thread(self, project_id: int, thread_key: str) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM thread_resolutions WHERE project_id = ? AND thread_key = ?",
                (project_id, thread_key),
            )
        return cursor.rowcount > 0


def _row_to_resolution(row) -> ThreadResolution:  # noqa: ANN001
    return ThreadResolution(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        thread_key=str(row["thread_key"]),
        thread=str(row["thread"]),
        status=str(row["status"]),
        note=str(row["note"]),
        chapter_id=int(row["chapter_id"]) if row["chapter_id"] is not None else None,
        chapter_title=str(row["chapter_title"] or ""),
        chapter_position=(
            int(row["chapter_position"])
            if row["chapter_position"] is not None
            else None
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
