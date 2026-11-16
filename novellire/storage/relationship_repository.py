"""Persistence for author-controlled character relationship records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .database import Database


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RelationshipRecord:
    id: int
    project_id: int
    character_a_id: int
    character_b_id: int
    character_a_name: str
    character_b_name: str
    relation_type: str
    description: str
    status: str
    source_event_id: int | None
    source_chapter_id: int | None
    source_chapter_title: str
    source_chapter_position: int | None
    source_summary: str
    created_at: str
    updated_at: str


_COLUMNS = """
    r.id, r.project_id, r.character_a_id, r.character_b_id,
    ca.name AS character_a_name, cb.name AS character_b_name,
    r.relation_type, r.description, r.status, r.source_event_id,
    e.chapter_id AS source_chapter_id,
    c.title AS source_chapter_title,
    c.position AS source_chapter_position,
    e.summary AS source_summary,
    r.created_at, r.updated_at
"""

_FROM = """
    FROM character_relationships r
    JOIN characters ca ON ca.id = r.character_a_id
    JOIN characters cb ON cb.id = r.character_b_id
    LEFT JOIN narrative_events e ON e.id = r.source_event_id
    LEFT JOIN chapters c ON c.id = e.chapter_id
"""


class RelationshipRepository:
    """CRUD for typed relationship records; derived pairs stay separate."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        project_id: int,
        character_a_id: int,
        character_b_id: int,
        relation_type: str,
        description: str,
        status: str,
        source_event_id: int | None,
    ) -> RelationshipRecord:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO character_relationships
                    (project_id, character_a_id, character_b_id, relation_type,
                     description, status, source_event_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    character_a_id,
                    character_b_id,
                    relation_type,
                    description,
                    status,
                    source_event_id,
                    now,
                    now,
                ),
            )
        return _require(self.get(int(cursor.lastrowid)))

    def get(self, record_id: int) -> RelationshipRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} {_FROM} WHERE r.id = ?", (record_id,)
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def list_for_project(self, project_id: int) -> list[RelationshipRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} {_FROM}
                WHERE r.project_id = ?
                ORDER BY
                    CASE r.status
                        WHEN 'approved' THEN 0
                        WHEN 'proposed' THEN 1
                        ELSE 2
                    END,
                    r.updated_at DESC, r.id DESC
                """,
                (project_id,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def update(
        self,
        record_id: int,
        *,
        relation_type: str,
        description: str,
    ) -> RelationshipRecord | None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE character_relationships
                SET relation_type = ?, description = ?, updated_at = ?
                WHERE id = ?
                """,
                (relation_type, description, utc_now_iso(), record_id),
            )
        return self.get(record_id)

    def set_status(self, record_id: int, status: str) -> RelationshipRecord | None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE character_relationships
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, utc_now_iso(), record_id),
            )
        return self.get(record_id)

    def delete(self, record_id: int) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM character_relationships WHERE id = ?", (record_id,)
            )
            return cursor.rowcount > 0


def _row_to_record(row: Any) -> RelationshipRecord:
    return RelationshipRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        character_a_id=int(row["character_a_id"]),
        character_b_id=int(row["character_b_id"]),
        character_a_name=str(row["character_a_name"]),
        character_b_name=str(row["character_b_name"]),
        relation_type=str(row["relation_type"]),
        description=str(row["description"]),
        status=str(row["status"]),
        source_event_id=(
            int(row["source_event_id"])
            if row["source_event_id"] is not None
            else None
        ),
        source_chapter_id=(
            int(row["source_chapter_id"])
            if row["source_chapter_id"] is not None
            else None
        ),
        source_chapter_title=str(row["source_chapter_title"] or ""),
        source_chapter_position=(
            int(row["source_chapter_position"])
            if row["source_chapter_position"] is not None
            else None
        ),
        source_summary=str(row["source_summary"] or ""),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _require(record: RelationshipRecord | None) -> RelationshipRecord:
    if record is None:
        raise RuntimeError("Relationship record disappeared after writing.")
    return record
