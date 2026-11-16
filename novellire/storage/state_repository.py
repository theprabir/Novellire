"""Persistence for author-recorded character-state snapshots."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..errors import DuplicateEntryError
from .database import Database


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class CharacterStateRecord:
    id: int
    project_id: int
    character_id: int
    character_name: str
    chapter_id: int
    chapter_title: str
    chapter_position: int
    location: str
    status: str
    goals: str
    knowledge: str
    created_at: str
    updated_at: str
    is_current: bool = False


_COLUMNS = """
    s.id, s.project_id, s.character_id, ch.name AS character_name,
    s.chapter_id, c.title AS chapter_title, c.position AS chapter_position,
    s.location, s.status, s.goals, s.knowledge, s.created_at, s.updated_at
"""

_FROM = """
    FROM character_states s
    JOIN characters ch ON ch.id = s.character_id
    JOIN chapters c ON c.id = s.chapter_id
"""


class CharacterStateRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        project_id: int,
        character_id: int,
        chapter_id: int,
        location: str,
        status: str,
        goals: str,
        knowledge: str,
    ) -> CharacterStateRecord:
        now = _utc_now_iso()
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO character_states
                        (project_id, character_id, chapter_id, location, status,
                         goals, knowledge, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        character_id,
                        chapter_id,
                        location,
                        status,
                        goals,
                        knowledge,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEntryError(
                    "That character already has a state snapshot for this chapter."
                ) from exc
        return _require(self.get(int(cursor.lastrowid)))

    def get(self, state_id: int) -> CharacterStateRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} {_FROM} WHERE s.id = ?", (state_id,)
            ).fetchone()
            if row is None:
                return None
            latest = connection.execute(
                f"""
                SELECT s.id {_FROM}
                WHERE s.character_id = ?
                ORDER BY c.position DESC, s.id DESC
                LIMIT 1
                """,
                (int(row["character_id"]),),
            ).fetchone()
        record = _row_to_state(row)
        return _with_current(record, latest is not None and int(latest["id"]) == state_id)

    def count_for_chapter(self, chapter_id: int) -> int:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM character_states WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
        return int(row["total"])

    def list_for_project(self, project_id: int) -> list[CharacterStateRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} {_FROM}
                WHERE s.project_id = ?
                ORDER BY c.position DESC, s.id DESC
                """,
                (project_id,),
            ).fetchall()
        records = [_row_to_state(row) for row in rows]
        current: set[int] = set()
        for index, record in enumerate(records):
            if record.character_id not in current:
                current.add(record.character_id)
                records[index] = _with_current(record, True)
        return records

    def update(
        self,
        state_id: int,
        *,
        location: str,
        status: str,
        goals: str,
        knowledge: str,
    ) -> CharacterStateRecord | None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE character_states
                SET location = ?, status = ?, goals = ?, knowledge = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (location, status, goals, knowledge, _utc_now_iso(), state_id),
            )
        return self.get(state_id)

    def delete(self, state_id: int) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM character_states WHERE id = ?", (state_id,)
            )
            return cursor.rowcount > 0


def _row_to_state(row: Any) -> CharacterStateRecord:
    return CharacterStateRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        character_id=int(row["character_id"]),
        character_name=str(row["character_name"]),
        chapter_id=int(row["chapter_id"]),
        chapter_title=str(row["chapter_title"]),
        chapter_position=int(row["chapter_position"]),
        location=str(row["location"]),
        status=str(row["status"]),
        goals=str(row["goals"]),
        knowledge=str(row["knowledge"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _with_current(
    record: CharacterStateRecord, is_current: bool
) -> CharacterStateRecord:
    return CharacterStateRecord(
        id=record.id,
        project_id=record.project_id,
        character_id=record.character_id,
        character_name=record.character_name,
        chapter_id=record.chapter_id,
        chapter_title=record.chapter_title,
        chapter_position=record.chapter_position,
        location=record.location,
        status=record.status,
        goals=record.goals,
        knowledge=record.knowledge,
        created_at=record.created_at,
        updated_at=record.updated_at,
        is_current=is_current,
    )


def _require(record: CharacterStateRecord | None) -> CharacterStateRecord:
    if record is None:
        raise RuntimeError("Character state disappeared after writing.")
    return record
