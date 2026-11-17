"""Persistence for chapter revision snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .database import Database

MAX_REVISIONS_PER_CHAPTER = 50


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ChapterRevision:
    id: int
    chapter_id: int
    title: str
    content: str
    word_count: int
    source: str
    created_at: str


class RevisionRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        chapter_id: int,
        title: str,
        content: str,
        word_count: int,
        source: str,
    ) -> ChapterRevision:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chapter_revisions
                    (chapter_id, title, content, word_count, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    title,
                    content,
                    word_count,
                    source,
                    _utc_now_iso(),
                ),
            )
            # Keep history bounded. The subquery leaves the newest revisions.
            connection.execute(
                """
                DELETE FROM chapter_revisions
                WHERE chapter_id = ?
                  AND id NOT IN (
                      SELECT id FROM chapter_revisions
                      WHERE chapter_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (chapter_id, chapter_id, MAX_REVISIONS_PER_CHAPTER),
            )
        return _require(self.get(int(cursor.lastrowid)))

    def get(self, revision_id: int) -> ChapterRevision | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM chapter_revisions WHERE id = ?", (revision_id,)
            ).fetchone()
        return _row_to_revision(row) if row is not None else None

    def get_for_chapter(
        self, chapter_id: int, revision_id: int
    ) -> ChapterRevision | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM chapter_revisions
                WHERE id = ? AND chapter_id = ?
                """,
                (revision_id, chapter_id),
            ).fetchone()
        return _row_to_revision(row) if row is not None else None

    def list_for_chapter(self, chapter_id: int) -> list[ChapterRevision]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chapter_revisions
                WHERE chapter_id = ?
                ORDER BY id DESC
                """,
                (chapter_id,),
            ).fetchall()
        return [_row_to_revision(row) for row in rows]


def _row_to_revision(row: Any) -> ChapterRevision:
    return ChapterRevision(
        id=int(row["id"]),
        chapter_id=int(row["chapter_id"]),
        title=str(row["title"]),
        content=str(row["content"]),
        word_count=int(row["word_count"]),
        source=str(row["source"]),
        created_at=str(row["created_at"]),
    )


def _require(revision: ChapterRevision | None) -> ChapterRevision:
    if revision is None:
        raise RuntimeError("Revision disappeared after writing.")
    return revision
