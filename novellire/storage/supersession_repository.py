"""Persistence for author decisions that one canon record replaces an earlier one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .database import Database


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SupersessionRecord:
    id: int
    project_id: int
    record_kind: str
    earlier_id: int
    later_id: int
    note: str
    created_at: str


class SupersessionRepository:
    """At most one decision per earlier record; marking again updates its note."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(
        self, project_id: int, record_kind: str, earlier_id: int
    ) -> SupersessionRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM canon_supersessions
                WHERE project_id = ? AND record_kind = ? AND earlier_id = ?
                """,
                (project_id, record_kind, earlier_id),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def list_for_project(self, project_id: int) -> list[SupersessionRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM canon_supersessions
                WHERE project_id = ?
                ORDER BY earlier_id
                """,
                (project_id,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def upsert(
        self,
        *,
        project_id: int,
        record_kind: str,
        earlier_id: int,
        later_id: int,
        note: str,
    ) -> SupersessionRecord:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO canon_supersessions
                    (project_id, record_kind, earlier_id, later_id, note,
                     created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (project_id, record_kind, earlier_id) DO UPDATE SET
                    later_id = excluded.later_id,
                    note = excluded.note
                """,
                (
                    project_id,
                    record_kind,
                    earlier_id,
                    later_id,
                    note,
                    _utc_now_iso(),
                ),
            )
        return _require(self.get(project_id, record_kind, earlier_id))

    def delete(self, project_id: int, record_kind: str, earlier_id: int) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM canon_supersessions
                WHERE project_id = ? AND record_kind = ? AND earlier_id = ?
                """,
                (project_id, record_kind, earlier_id),
            )
            return cursor.rowcount > 0


def _row_to_record(row: Any) -> SupersessionRecord:
    return SupersessionRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        record_kind=str(row["record_kind"]),
        earlier_id=int(row["earlier_id"]),
        later_id=int(row["later_id"]),
        note=str(row["note"]),
        created_at=str(row["created_at"]),
    )


def _require(record: SupersessionRecord | None) -> SupersessionRecord:
    if record is None:
        raise RuntimeError("Supersession disappeared after writing.")
    return record
