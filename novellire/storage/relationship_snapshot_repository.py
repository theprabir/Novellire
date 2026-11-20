"""Persistence for the recorded state of a relationship in one chapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .database import Database


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RelationshipSnapshotRecord:
    id: int
    project_id: int
    relationship_id: int
    chapter_id: int
    chapter_title: str
    chapter_position: int
    relation_type: str
    description: str
    created_at: str


_COLUMNS = """
    s.id, s.project_id, s.relationship_id, s.chapter_id,
    c.title AS chapter_title, c.position AS chapter_position,
    s.relation_type, s.description, s.created_at
"""

_FROM = """
    FROM relationship_snapshots s
    JOIN chapters c ON c.id = s.chapter_id
"""


class RelationshipSnapshotRepository:
    """One snapshot per relationship per chapter, kept as evolution history."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def upsert(
        self,
        *,
        project_id: int,
        relationship_id: int,
        chapter_id: int,
        relation_type: str,
        description: str,
    ) -> RelationshipSnapshotRecord:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO relationship_snapshots
                    (project_id, relationship_id, chapter_id, relation_type,
                     description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (relationship_id, chapter_id) DO UPDATE SET
                    relation_type = excluded.relation_type,
                    description = excluded.description
                """,
                (
                    project_id,
                    relationship_id,
                    chapter_id,
                    relation_type,
                    description,
                    _utc_now_iso(),
                ),
            )
        return _require(self.get(relationship_id, chapter_id))

    def get(
        self, relationship_id: int, chapter_id: int
    ) -> RelationshipSnapshotRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"""
                SELECT {_COLUMNS} {_FROM}
                WHERE s.relationship_id = ? AND s.chapter_id = ?
                """,
                (relationship_id, chapter_id),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def list_for_project(self, project_id: int) -> list[RelationshipSnapshotRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_COLUMNS} {_FROM}
                WHERE s.project_id = ?
                ORDER BY c.position, s.id
                """,
                (project_id,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: Any) -> RelationshipSnapshotRecord:
    return RelationshipSnapshotRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        relationship_id=int(row["relationship_id"]),
        chapter_id=int(row["chapter_id"]),
        chapter_title=str(row["chapter_title"]),
        chapter_position=int(row["chapter_position"]),
        relation_type=str(row["relation_type"]),
        description=str(row["description"]),
        created_at=str(row["created_at"]),
    )


def _require(
    record: RelationshipSnapshotRecord | None,
) -> RelationshipSnapshotRecord:
    if record is None:
        raise RuntimeError("Relationship snapshot disappeared after writing.")
    return record
