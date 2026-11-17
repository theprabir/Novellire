"""Persistence for automatic-analysis hashes and derived chapter insights."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from .database import Database


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AnalysisStateRecord:
    project_id: int
    source_kind: str
    source_key: str
    content_hash: str
    status: str
    detail: str
    updated_at: str


class AnalysisStateRepository:
    """Track the last analysed hash and status for chapters and documents."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(
        self, project_id: int, source_kind: str, source_key: str
    ) -> AnalysisStateRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT project_id, source_kind, source_key, content_hash, "
                "status, detail, updated_at FROM analysis_state "
                "WHERE project_id = ? AND source_kind = ? AND source_key = ?",
                (project_id, source_kind, source_key),
            ).fetchone()
        return _row_to_state(row) if row is not None else None

    def mark(
        self,
        project_id: int,
        source_kind: str,
        source_key: str,
        content_hash: str,
        status: str,
        detail: str = "",
    ) -> AnalysisStateRecord:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO analysis_state
                    (project_id, source_kind, source_key, content_hash, status,
                     detail, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, source_kind, source_key) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    detail = excluded.detail,
                    updated_at = excluded.updated_at
                """,
                (
                    project_id,
                    source_kind,
                    source_key,
                    content_hash,
                    status,
                    detail,
                    now,
                ),
            )
        record = self.get(project_id, source_kind, source_key)
        if record is None:
            raise RuntimeError("Analysis state disappeared after writing.")
        return record

    def list_for_project(self, project_id: int) -> list[AnalysisStateRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                "SELECT project_id, source_kind, source_key, content_hash, "
                "status, detail, updated_at FROM analysis_state "
                "WHERE project_id = ? ORDER BY source_kind, source_key",
                (project_id,),
            ).fetchall()
        return [_row_to_state(row) for row in rows]


@dataclass(frozen=True)
class ChapterInsightRecord:
    id: int
    project_id: int
    chapter_id: int
    content_hash: str
    character_states: tuple[dict[str, str], ...]
    locations: tuple[dict[str, str], ...]
    relationships: tuple[dict[str, str], ...]
    open_threads: tuple[str, ...]
    model: str
    created_at: str
    updated_at: str


class ChapterInsightRepository:
    """Derived chapter insights, kept separate from author-controlled memory."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get_for_chapter(self, chapter_id: int) -> ChapterInsightRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM chapter_insights WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
        return _row_to_insight(row) if row is not None else None

    def upsert(
        self,
        *,
        project_id: int,
        chapter_id: int,
        content_hash: str,
        character_states: Sequence[dict[str, str]],
        locations: Sequence[dict[str, str]],
        relationships: Sequence[dict[str, str]],
        open_threads: Sequence[str],
        model: str,
    ) -> ChapterInsightRecord:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO chapter_insights
                    (project_id, chapter_id, content_hash, character_states,
                     locations, relationships, open_threads, model, created_at,
                     updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    character_states = excluded.character_states,
                    locations = excluded.locations,
                    relationships = excluded.relationships,
                    open_threads = excluded.open_threads,
                    model = excluded.model,
                    updated_at = excluded.updated_at
                """,
                (
                    project_id,
                    chapter_id,
                    content_hash,
                    _encode(character_states),
                    _encode(locations),
                    _encode(relationships),
                    _encode(open_threads),
                    model,
                    now,
                    now,
                ),
            )
        record = self.get_for_chapter(chapter_id)
        if record is None:
            raise RuntimeError("Chapter insights disappeared after writing.")
        return record

    def list_for_project(self, project_id: int) -> list[ChapterInsightRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT i.* FROM chapter_insights i
                JOIN chapters c ON c.id = i.chapter_id
                WHERE i.project_id = ?
                ORDER BY c.position
                """,
                (project_id,),
            ).fetchall()
        return [_row_to_insight(row) for row in rows]


def _encode(values: Sequence[dict[str, str]] | Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _decode_list(value: str) -> list[Any]:
    try:
        data = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _row_to_state(row: Any) -> AnalysisStateRecord:
    return AnalysisStateRecord(
        project_id=int(row["project_id"]),
        source_kind=str(row["source_kind"]),
        source_key=str(row["source_key"]),
        content_hash=str(row["content_hash"]),
        status=str(row["status"]),
        detail=str(row["detail"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_insight(row: Any) -> ChapterInsightRecord:
    return ChapterInsightRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        chapter_id=int(row["chapter_id"]),
        content_hash=str(row["content_hash"]),
        character_states=tuple(
            item for item in _decode_list(row["character_states"]) if isinstance(item, dict)
        ),
        locations=tuple(
            item for item in _decode_list(row["locations"]) if isinstance(item, dict)
        ),
        relationships=tuple(
            item for item in _decode_list(row["relationships"]) if isinstance(item, dict)
        ),
        open_threads=tuple(
            str(item) for item in _decode_list(row["open_threads"]) if isinstance(item, str)
        ),
        model=str(row["model"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
