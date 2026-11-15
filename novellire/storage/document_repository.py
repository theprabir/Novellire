"""Persistence for the four workspace documents.

A project owns exactly one row per document kind: master story bible, character
bible, chapter map, and style guide. The row is created on first save and updated
in place afterwards, so the document kinds can never be duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass

from .database import Database, utc_now_iso

_COLUMNS = "project_id, kind, content, derived, created_at, updated_at"


@dataclass(frozen=True)
class ProjectDocument:
    project_id: int
    kind: str
    content: str
    derived: bool
    created_at: str
    updated_at: str


class DocumentRepository:
    """Read and upsert the workspace documents of a project."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self, project_id: int, kind: str) -> ProjectDocument | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM project_documents "
                "WHERE project_id = ? AND kind = ?",
                (project_id, kind),
            ).fetchone()
        return _row_to_document(row) if row is not None else None

    def list_for_project(self, project_id: int) -> list[ProjectDocument]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM project_documents WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [_row_to_document(row) for row in rows]

    def upsert(
        self, project_id: int, kind: str, *, content: str, derived: bool = False
    ) -> ProjectDocument:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO project_documents
                    (project_id, kind, content, derived, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (project_id, kind) DO UPDATE SET
                    content = excluded.content,
                    derived = excluded.derived,
                    updated_at = excluded.updated_at
                """,
                (project_id, kind, content, 1 if derived else 0, now, now),
            )

        document = self.get(project_id, kind)
        assert document is not None  # written in the transaction above
        return document


def _row_to_document(row) -> ProjectDocument:  # noqa: ANN001 - sqlite3.Row
    return ProjectDocument(
        project_id=int(row["project_id"]),
        kind=str(row["kind"]),
        content=str(row["content"]),
        derived=bool(row["derived"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
