"""Repositories for Phase 2 narrative structure.

Story bible entries, characters with aliases, chapters, and scenes. All access is
project-scoped through foreign keys, and constraint violations are mapped to
domain errors so callers never see SQLite details.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..errors import DatabaseError, DuplicateEntryError, RecordNotFoundError
from .database import Database, utc_now_iso

_STORY_BIBLE_COLUMNS = (
    "id, project_id, category, title, content, created_at, updated_at"
)

_CHARACTER_COLUMNS = (
    "id, project_id, name, physical_description, age, personality, motivations, "
    "goals, fears, strengths, weaknesses, background, secrets, character_arc, "
    "created_at, updated_at"
)

_CHAPTER_COLUMNS = (
    "id, project_id, position, title, part, summary, objectives, "
    "viewpoint_character_id, target_word_count, status, created_at, updated_at, "
    "content, word_count, origin"
)

_SCENE_COLUMNS = (
    "id, chapter_id, position, title, summary, objectives, content, word_count, "
    "status, created_at, updated_at"
)

_STORY_BIBLE_UPDATE_FIELDS = frozenset({"category", "title", "content"})
_CHARACTER_UPDATE_FIELDS = frozenset(
    {
        "name",
        "physical_description",
        "age",
        "personality",
        "motivations",
        "goals",
        "fears",
        "strengths",
        "weaknesses",
        "background",
        "secrets",
        "character_arc",
    }
)
_CHAPTER_UPDATE_FIELDS = frozenset(
    {
        "title",
        "part",
        "summary",
        "objectives",
        "viewpoint_character_id",
        "target_word_count",
        "status",
        "content",
        "word_count",
    }
)
_SCENE_UPDATE_FIELDS = frozenset(
    {"title", "summary", "objectives", "content", "word_count", "status"}
)


@dataclass(frozen=True)
class StoryBibleEntry:
    id: int
    project_id: int
    category: str
    title: str
    content: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CharacterRecord:
    id: int
    project_id: int
    name: str
    physical_description: str
    age: str
    personality: str
    motivations: str
    goals: str
    fears: str
    strengths: str
    weaknesses: str
    background: str
    secrets: str
    character_arc: str
    created_at: str
    updated_at: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChapterRecord:
    id: int
    project_id: int
    position: int
    title: str
    part: str
    summary: str
    objectives: str
    viewpoint_character_id: int | None
    target_word_count: int | None
    status: str
    created_at: str
    updated_at: str
    content: str = ""
    word_count: int = 0
    origin: str = "written"


@dataclass(frozen=True)
class SceneRecord:
    id: int
    chapter_id: int
    position: int
    title: str
    summary: str
    objectives: str
    content: str
    word_count: int
    status: str
    created_at: str
    updated_at: str


def _row_to_entry(row: sqlite3.Row) -> StoryBibleEntry:
    return StoryBibleEntry(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        category=str(row["category"]),
        title=str(row["title"]),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_character(
    row: sqlite3.Row, aliases: tuple[str, ...] = ()
) -> CharacterRecord:
    return CharacterRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        name=str(row["name"]),
        physical_description=str(row["physical_description"]),
        age=str(row["age"]),
        personality=str(row["personality"]),
        motivations=str(row["motivations"]),
        goals=str(row["goals"]),
        fears=str(row["fears"]),
        strengths=str(row["strengths"]),
        weaknesses=str(row["weaknesses"]),
        background=str(row["background"]),
        secrets=str(row["secrets"]),
        character_arc=str(row["character_arc"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        aliases=aliases,
    )


def _row_to_chapter(row: sqlite3.Row) -> ChapterRecord:
    viewpoint = row["viewpoint_character_id"]
    target = row["target_word_count"]
    return ChapterRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        position=int(row["position"]),
        title=str(row["title"]),
        part=str(row["part"]),
        summary=str(row["summary"]),
        objectives=str(row["objectives"]),
        viewpoint_character_id=int(viewpoint) if viewpoint is not None else None,
        target_word_count=int(target) if target is not None else None,
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        content=str(row["content"]),
        word_count=int(row["word_count"]),
        origin=str(row["origin"]),
    )


def _row_to_scene(row: sqlite3.Row) -> SceneRecord:
    return SceneRecord(
        id=int(row["id"]),
        chapter_id=int(row["chapter_id"]),
        position=int(row["position"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        objectives=str(row["objectives"]),
        content=str(row["content"]),
        word_count=int(row["word_count"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class StoryBibleRepository:
    """CRUD for categorised story bible entries."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self, *, project_id: int, category: str, title: str, content: str = ""
    ) -> StoryBibleEntry:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO story_bible_entries
                        (project_id, category, title, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, category, title, content, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEntryError(
                    f"A story bible entry titled '{title}' already exists in that category."
                ) from exc
            entry_id = int(cursor.lastrowid)

        entry = self.get(entry_id)
        if entry is None:
            raise DatabaseError("The story bible entry could not be reloaded.")
        return entry

    def get(self, entry_id: int) -> StoryBibleEntry | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_STORY_BIBLE_COLUMNS} FROM story_bible_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return _row_to_entry(row) if row is not None else None

    def list_for_project(
        self, project_id: int, *, category: str | None = None
    ) -> list[StoryBibleEntry]:
        sql = f"SELECT {_STORY_BIBLE_COLUMNS} FROM story_bible_entries WHERE project_id = ?"
        parameters: list[object] = [project_id]
        if category is not None:
            sql += " AND category = ?"
            parameters.append(category)
        sql += " ORDER BY category, title COLLATE NOCASE"
        with self._database.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [_row_to_entry(row) for row in rows]

    def update(self, entry_id: int, **fields: object) -> StoryBibleEntry:
        _check_fields(fields, _STORY_BIBLE_UPDATE_FIELDS)
        if not fields:
            return _require(self.get(entry_id), "story bible entry")

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = [*fields.values(), utc_now_iso(), entry_id]
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    f"UPDATE story_bible_entries SET {assignments}, updated_at = ? "
                    "WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEntryError(
                    "Another story bible entry already uses that title in this category."
                ) from exc
            if cursor.rowcount == 0:
                raise RecordNotFoundError("That story bible entry no longer exists.")

        return _require(self.get(entry_id), "story bible entry")


class CharacterRepository:
    """CRUD for character profiles and their aliases."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        project_id: int,
        name: str,
        aliases: tuple[str, ...] = (),
        physical_description: str = "",
        age: str = "",
        personality: str = "",
        motivations: str = "",
        goals: str = "",
        fears: str = "",
        strengths: str = "",
        weaknesses: str = "",
        background: str = "",
        secrets: str = "",
        character_arc: str = "",
    ) -> CharacterRecord:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO characters
                        (project_id, name, physical_description, age, personality,
                         motivations, goals, fears, strengths, weaknesses, background,
                         secrets, character_arc, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        name,
                        physical_description,
                        age,
                        personality,
                        motivations,
                        goals,
                        fears,
                        strengths,
                        weaknesses,
                        background,
                        secrets,
                        character_arc,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEntryError(
                    f"A character named '{name}' already exists in this project."
                ) from exc
            character_id = int(cursor.lastrowid)
            _insert_aliases(connection, character_id, aliases)

        return _require(self.get(character_id), "character")

    def get(self, character_id: int) -> CharacterRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_CHARACTER_COLUMNS} FROM characters WHERE id = ?",
                (character_id,),
            ).fetchone()
            if row is None:
                return None
            alias_rows = connection.execute(
                "SELECT alias FROM character_aliases WHERE character_id = ? "
                "ORDER BY alias COLLATE NOCASE",
                (character_id,),
            ).fetchall()
        aliases = tuple(str(alias["alias"]) for alias in alias_rows)
        return _row_to_character(row, aliases)

    def list_for_project(self, project_id: int) -> list[CharacterRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT {_CHARACTER_COLUMNS} FROM characters WHERE project_id = ? "
                "ORDER BY name COLLATE NOCASE",
                (project_id,),
            ).fetchall()
            alias_rows = connection.execute(
                """
                SELECT a.character_id AS character_id, a.alias AS alias
                FROM character_aliases a
                JOIN characters c ON c.id = a.character_id
                WHERE c.project_id = ?
                ORDER BY a.alias COLLATE NOCASE
                """,
                (project_id,),
            ).fetchall()

        grouped: dict[int, list[str]] = {}
        for alias in alias_rows:
            grouped.setdefault(int(alias["character_id"]), []).append(str(alias["alias"]))
        return [
            _row_to_character(row, tuple(grouped.get(int(row["id"]), ())))
            for row in rows
        ]

    def update(self, character_id: int, **fields: object) -> CharacterRecord:
        _check_fields(fields, _CHARACTER_UPDATE_FIELDS)
        if not fields:
            return _require(self.get(character_id), "character")

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = [*fields.values(), utc_now_iso(), character_id]
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    f"UPDATE characters SET {assignments}, updated_at = ? WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateEntryError(
                    "Another character already uses that name in this project."
                ) from exc
            if cursor.rowcount == 0:
                raise RecordNotFoundError("That character no longer exists.")

        return _require(self.get(character_id), "character")

    def replace_aliases(
        self, character_id: int, aliases: tuple[str, ...]
    ) -> CharacterRecord:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id FROM characters WHERE id = ?", (character_id,)
            ).fetchone()
            if row is None:
                raise RecordNotFoundError("That character no longer exists.")
            connection.execute(
                "DELETE FROM character_aliases WHERE character_id = ?", (character_id,)
            )
            _insert_aliases(connection, character_id, aliases)
            connection.execute(
                "UPDATE characters SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), character_id),
            )

        return _require(self.get(character_id), "character")


class ChapterRepository:
    """CRUD for chapters, appended in order within a project."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        project_id: int,
        title: str,
        part: str = "",
        summary: str = "",
        objectives: str = "",
        viewpoint_character_id: int | None = None,
        target_word_count: int | None = None,
        status: str = "planned",
        content: str = "",
        word_count: int = 0,
        origin: str = "written",
    ) -> ChapterRecord:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_position "
                "FROM chapters WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            position = int(row["next_position"]) if row is not None else 1
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO chapters
                        (project_id, position, title, part, summary, objectives,
                         viewpoint_character_id, target_word_count, status,
                         created_at, updated_at, content, word_count, origin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        position,
                        title,
                        part,
                        summary,
                        objectives,
                        viewpoint_character_id,
                        target_word_count,
                        status,
                        now,
                        now,
                        content,
                        word_count,
                        origin,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DatabaseError(
                    "The chapter could not be added because its position conflicts "
                    "with another chapter. Try again."
                ) from exc
            chapter_id = int(cursor.lastrowid)

        return _require(self.get(chapter_id), "chapter")

    def get(self, chapter_id: int) -> ChapterRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_CHAPTER_COLUMNS} FROM chapters WHERE id = ?",
                (chapter_id,),
            ).fetchone()
        return _row_to_chapter(row) if row is not None else None

    def list_for_project(self, project_id: int) -> list[ChapterRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT {_CHAPTER_COLUMNS} FROM chapters WHERE project_id = ? "
                "ORDER BY position",
                (project_id,),
            ).fetchall()
        return [_row_to_chapter(row) for row in rows]

    def update(self, chapter_id: int, **fields: object) -> ChapterRecord:
        _check_fields(fields, _CHAPTER_UPDATE_FIELDS)
        if not fields:
            return _require(self.get(chapter_id), "chapter")

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = [*fields.values(), utc_now_iso(), chapter_id]
        with self._database.transaction() as connection:
            try:
                cursor = connection.execute(
                    f"UPDATE chapters SET {assignments}, updated_at = ? WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                raise DatabaseError(
                    "The chapter could not be updated because a reference is invalid."
                ) from exc
            if cursor.rowcount == 0:
                raise RecordNotFoundError("That chapter no longer exists.")

        return _require(self.get(chapter_id), "chapter")


class SceneRepository:
    """CRUD for scenes, appended in order within a chapter."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        *,
        chapter_id: int,
        title: str = "",
        summary: str = "",
        objectives: str = "",
        content: str = "",
        word_count: int = 0,
        status: str = "planned",
    ) -> SceneRecord:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_position "
                "FROM scenes WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
            position = int(row["next_position"]) if row is not None else 1
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO scenes
                        (chapter_id, position, title, summary, objectives, content,
                         word_count, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chapter_id,
                        position,
                        title,
                        summary,
                        objectives,
                        content,
                        word_count,
                        status,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DatabaseError(
                    "The scene could not be added. The chapter may no longer exist."
                ) from exc
            scene_id = int(cursor.lastrowid)

        return _require(self.get(scene_id), "scene")

    def get(self, scene_id: int) -> SceneRecord | None:
        with self._database.connection() as connection:
            row = connection.execute(
                f"SELECT {_SCENE_COLUMNS} FROM scenes WHERE id = ?", (scene_id,)
            ).fetchone()
        return _row_to_scene(row) if row is not None else None

    def list_for_chapter(self, chapter_id: int) -> list[SceneRecord]:
        with self._database.connection() as connection:
            rows = connection.execute(
                f"SELECT {_SCENE_COLUMNS} FROM scenes WHERE chapter_id = ? "
                "ORDER BY position",
                (chapter_id,),
            ).fetchall()
        return [_row_to_scene(row) for row in rows]

    def update(self, scene_id: int, **fields: object) -> SceneRecord:
        _check_fields(fields, _SCENE_UPDATE_FIELDS)
        if not fields:
            return _require(self.get(scene_id), "scene")

        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = [*fields.values(), utc_now_iso(), scene_id]
        with self._database.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE scenes SET {assignments}, updated_at = ? WHERE id = ?", values
            )
            if cursor.rowcount == 0:
                raise RecordNotFoundError("That scene no longer exists.")

        return _require(self.get(scene_id), "scene")

    def total_words(self, chapter_id: int) -> int:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(word_count), 0) AS words FROM scenes "
                "WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
        return int(row["words"]) if row is not None else 0


def _insert_aliases(
    connection: sqlite3.Connection, character_id: int, aliases: tuple[str, ...]
) -> None:
    for alias in aliases:
        connection.execute(
            "INSERT OR IGNORE INTO character_aliases (character_id, alias) "
            "VALUES (?, ?)",
            (character_id, alias),
        )


def _check_fields(fields: dict[str, object], allowed: frozenset[str]) -> None:
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unsupported fields: {sorted(unknown)}")


def _require(value, label: str):  # noqa: ANN001 - small internal helper
    if value is None:
        raise RecordNotFoundError(f"That {label} no longer exists.")
    return value
