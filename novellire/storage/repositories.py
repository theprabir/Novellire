"""Repositories: the only place that reads or writes tables.

Repositories contain SQL and row mapping, not business rules (validation lives
in ``novellire.core``). Constraint violations are mapped to domain errors so
callers never need to know about SQLite.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..errors import DatabaseError, DuplicateProjectError, ProjectNotFoundError
from .database import Database, utc_now_iso

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_PROJECT_COLUMNS = (
    "id, name, description, genre, narrative_style, target_word_count, "
    "archived, created_at, updated_at"
)

_GENERATION_COLUMNS = (
    "id, project_id, model, system_prompt, prompt, output, word_count, "
    "temperature, top_p, num_predict, context_window, status, error, "
    "duration_ms, prompt_tokens, output_tokens, truncated, created_at"
)

_PROJECT_UPDATE_FIELDS = frozenset(
    {"name", "description", "genre", "narrative_style", "target_word_count"}
)


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    description: str
    genre: str
    narrative_style: str
    target_word_count: int | None
    archived: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class GenerationRecord:
    id: int
    project_id: int
    model: str
    system_prompt: str
    prompt: str
    output: str
    word_count: int
    temperature: float
    top_p: float
    num_predict: int
    context_window: int
    status: str
    error: str | None
    duration_ms: int
    prompt_tokens: int | None
    output_tokens: int | None
    truncated: bool
    created_at: str


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=int(row["id"]),
        name=str(row["name"]),
        description=str(row["description"]),
        genre=str(row["genre"]),
        narrative_style=str(row["narrative_style"]),
        target_word_count=(
            int(row["target_word_count"]) if row["target_word_count"] is not None else None
        ),
        archived=bool(row["archived"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_generation(row: sqlite3.Row) -> GenerationRecord:
    return GenerationRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        model=str(row["model"]),
        system_prompt=str(row["system_prompt"]),
        prompt=str(row["prompt"]),
        output=str(row["output"]),
        word_count=int(row["word_count"]),
        temperature=float(row["temperature"]),
        top_p=float(row["top_p"]),
        num_predict=int(row["num_predict"]),
        context_window=int(row["context_window"]),
        status=str(row["status"]),
        error=str(row["error"]) if row["error"] is not None else None,
        duration_ms=int(row["duration_ms"]),
        prompt_tokens=(
            int(row["prompt_tokens"]) if row["prompt_tokens"] is not None else None
        ),
        output_tokens=(
            int(row["output_tokens"]) if row["output_tokens"] is not None else None
        ),
        truncated=bool(row["truncated"]),
        created_at=str(row["created_at"]),
    )


class ProjectRepository:
    """CRUD access to novel projects."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        name: str,
        description: str = "",
        genre: str = "",
        narrative_style: str = "",
        target_word_count: int | None = None,
    ) -> Project:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO projects
                        (name, description, genre, narrative_style,
                         target_word_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        description,
                        genre,
                        narrative_style,
                        target_word_count,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateProjectError(
                    f"A project named '{name}' already exists."
                ) from exc
            project_id = int(cursor.lastrowid)

        project = self.get(project_id)
        if project is None:
            raise DatabaseError("The project was created but could not be reloaded.")
        return project

    def get(self, project_id: int) -> Project | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _row_to_project(row) if row is not None else None

    def list(self, *, include_archived: bool = False) -> list[Project]:
        sql = f"SELECT {_PROJECT_COLUMNS} FROM projects"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY name COLLATE NOCASE"
        with self._database.connection() as connection:
            rows = connection.execute(sql).fetchall()
        return [_row_to_project(row) for row in rows]

    def update(self, project_id: int, **fields: object) -> Project:
        unknown = set(fields) - _PROJECT_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported project fields: {sorted(unknown)}")

        if not fields:
            existing = self.get(project_id)
            if existing is None:
                raise ProjectNotFoundError(f"Project {project_id} was not found.")
            return existing

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = [*fields.values(), utc_now_iso(), project_id]
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    f"UPDATE projects SET {assignments}, updated_at = ? WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateProjectError(
                    "Another project already uses that name."
                ) from exc
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(f"Project {project_id} was not found.")

        project = self.get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} was not found.")
        return project

    def set_archived(self, project_id: int, archived: bool) -> Project:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE projects SET archived = ?, updated_at = ? WHERE id = ?",
                (1 if archived else 0, utc_now_iso(), project_id),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(f"Project {project_id} was not found.")
        project = self.get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} was not found.")
        return project


class GenerationRepository:
    """Immutable log of generation attempts, successful or failed."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        project_id: int,
        model: str,
        prompt: str,
        system_prompt: str = "",
        output: str = "",
        word_count: int = 0,
        temperature: float,
        top_p: float,
        num_predict: int,
        context_window: int,
        status: str,
        error: str | None = None,
        duration_ms: int = 0,
        prompt_tokens: int | None = None,
        output_tokens: int | None = None,
        truncated: bool = False,
    ) -> GenerationRecord:
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO generations
                        (project_id, model, system_prompt, prompt, output, word_count,
                         temperature, top_p, num_predict, context_window, status, error,
                         duration_ms, prompt_tokens, output_tokens, truncated, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        model,
                        system_prompt,
                        prompt,
                        output,
                        word_count,
                        temperature,
                        top_p,
                        num_predict,
                        context_window,
                        status,
                        error,
                        duration_ms,
                        prompt_tokens,
                        output_tokens,
                        1 if truncated else 0,
                        utc_now_iso(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DatabaseError(
                    "The generation could not be saved. The project may no longer exist."
                ) from exc
            generation_id = int(cursor.lastrowid)

        record = self.get(generation_id)
        if record is None:
            raise DatabaseError("The generation was saved but could not be reloaded.")
        return record

    def get(self, generation_id: int) -> GenerationRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_GENERATION_COLUMNS} FROM generations WHERE id = ?",
                (generation_id,),
            ).fetchone()
        return _row_to_generation(row) if row is not None else None

    def list_for_project(
        self, project_id: int, *, limit: int = 20
    ) -> list[GenerationRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_GENERATION_COLUMNS} FROM generations
                WHERE project_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (project_id, max(1, int(limit))),
            ).fetchall()
        return [_row_to_generation(row) for row in rows]

    def count_for_project(self, project_id: int) -> int:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM generations WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def produced_words(self, project_id: int) -> int:
        """Total words of successful generations for a project."""
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(word_count), 0) AS words FROM generations
                WHERE project_id = ? AND status = ?
                """,
                (project_id, STATUS_COMPLETED),
            ).fetchone()
        return int(row["words"]) if row is not None else 0


class AppSettingsRepository:
    """Key/value storage for lightweight UI preferences."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self, key: str) -> str | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row is not None else None

    def set(self, key: str, value: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE
                    SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, utc_now_iso()),
            )

    def delete(self, key: str) -> None:
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM app_settings WHERE key = ?", (key,))

    def all(self) -> dict[str, str]:
        with self._database.connection() as connection:
            rows = connection.execute("SELECT key, value FROM app_settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}
