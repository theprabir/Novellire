"""Persistent project and chapter-scoped chat threads."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .database import Database, utc_now_iso

CHAT_MODES = ("plan", "write")


@dataclass(frozen=True)
class ChatThread:
    id: int
    project_id: int
    chapter_id: int | None
    mode: str
    title: str
    planning_notes: str
    planning_notes_source: str
    created_at: str
    updated_at: str
    message_count: int = 0


@dataclass(frozen=True)
class ChatDraft:
    """A checkpoint of a reply that was still streaming when it stopped.

    A draft is never shown as a message. The author either keeps it, which
    stores it as a model reply, or discards it.
    """

    id: int
    thread_id: int
    content: str
    model: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatMessage:
    id: int
    thread_id: int
    role: str
    content: str
    model: str
    created_at: str
    context: dict[str, object] | None = None


class ChatRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def list_threads(self, project_id: int) -> list[ChatThread]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT t.*, (
                    SELECT COUNT(*) FROM chat_messages m
                    WHERE m.thread_id = t.id
                ) AS message_count
                FROM chat_threads t
                WHERE t.project_id = ?
                ORDER BY t.updated_at DESC, t.id DESC
                """,
                (project_id,),
            ).fetchall()
        return [_thread_from_row(row) for row in rows]

    def get_thread(self, thread_id: int) -> ChatThread | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT t.*, (
                    SELECT COUNT(*) FROM chat_messages m
                    WHERE m.thread_id = t.id
                ) AS message_count
                FROM chat_threads t WHERE t.id = ?
                """,
                (thread_id,),
            ).fetchone()
        return _thread_from_row(row) if row is not None else None

    def create_thread(
        self,
        *,
        project_id: int,
        chapter_id: int | None,
        mode: str,
        title: str = "New conversation",
    ) -> ChatThread:
        now = utc_now_iso()
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chat_threads
                    (project_id, chapter_id, mode, title, planning_notes,
                     planning_notes_source, created_at, updated_at)
                VALUES (?, ?, ?, ?, '', '', ?, ?)
                """,
                (project_id, chapter_id, mode, title, now, now),
            )
            thread_id = int(cursor.lastrowid)
        thread = self.get_thread(thread_id)
        if thread is None:
            raise RuntimeError("Chat thread disappeared after writing.")
        return thread

    def set_title(self, thread_id: int, title: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE chat_threads SET title = ?, updated_at = ? WHERE id = ?",
                (title, utc_now_iso(), thread_id),
            )

    def set_mode(self, thread_id: int, mode: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE chat_threads SET mode = ?, updated_at = ? WHERE id = ?",
                (mode, utc_now_iso(), thread_id),
            )

    def set_planning_notes(
        self, thread_id: int, notes: str, *, source: str
    ) -> ChatThread:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE chat_threads
                SET planning_notes = ?, planning_notes_source = ?, updated_at = ?
                WHERE id = ?
                """,
                (notes, source, utc_now_iso(), thread_id),
            )
        thread = self.get_thread(thread_id)
        if thread is None:
            raise RuntimeError("Chat thread disappeared after writing notes.")
        return thread

    def list_messages(self, thread_id: int) -> list[ChatMessage]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, thread_id, role, content, model, created_at,
                       context_json
                FROM chat_messages WHERE thread_id = ? ORDER BY id
                """,
                (thread_id,),
            ).fetchall()
        return [_message_from_row(row) for row in rows]

    def get_message(self, message_id: int) -> ChatMessage | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, thread_id, role, content, model, created_at,
                       context_json
                FROM chat_messages WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        return _message_from_row(row) if row is not None else None

    def add_message(
        self,
        thread_id: int,
        *,
        role: str,
        content: str,
        model: str = "",
        context: dict[str, object] | None = None,
    ) -> ChatMessage:
        now = utc_now_iso()
        context_json = json.dumps(context, ensure_ascii=False) if context else ""
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chat_messages
                    (thread_id, role, content, model, created_at, context_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (thread_id, role, content, model, now, context_json),
            )
            message_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE chat_threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )
            row = connection.execute(
                """
                SELECT id, thread_id, role, content, model, created_at,
                       context_json
                FROM chat_messages WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Chat message disappeared after writing.")
        return _message_from_row(row)


    def get_draft(self, thread_id: int) -> ChatDraft | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, thread_id, content, model, created_at, updated_at
                FROM chat_drafts WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
        return _draft_from_row(row) if row is not None else None

    def save_draft(
        self, thread_id: int, *, content: str, model: str = ""
    ) -> ChatDraft:
        """Write or replace the one in-progress reply checkpoint of a thread."""
        now = utc_now_iso()
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO chat_drafts
                    (thread_id, content, model, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (thread_id) DO UPDATE SET
                    content = excluded.content,
                    model = excluded.model,
                    updated_at = excluded.updated_at
                """,
                (thread_id, content, model, now, now),
            )
        draft = self.get_draft(thread_id)
        if draft is None:
            raise RuntimeError("Chat draft disappeared after writing.")
        return draft

    def clear_draft(self, thread_id: int) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "DELETE FROM chat_drafts WHERE thread_id = ?", (thread_id,)
            )


def _thread_from_row(row) -> ChatThread:  # noqa: ANN001 - sqlite3.Row
    return ChatThread(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        chapter_id=int(row["chapter_id"]) if row["chapter_id"] is not None else None,
        mode=str(row["mode"]),
        title=str(row["title"]),
        planning_notes=str(row["planning_notes"]),
        planning_notes_source=str(row["planning_notes_source"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        message_count=int(row["message_count"]),
    )


def _draft_from_row(row) -> ChatDraft:  # noqa: ANN001 - sqlite3.Row
    return ChatDraft(
        id=int(row["id"]),
        thread_id=int(row["thread_id"]),
        content=str(row["content"]),
        model=str(row["model"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _message_from_row(row) -> ChatMessage:  # noqa: ANN001 - sqlite3.Row
    return ChatMessage(
        id=int(row["id"]),
        thread_id=int(row["thread_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        model=str(row["model"]),
        created_at=str(row["created_at"]),
        context=_context_from_json(row["context_json"]),
    )


def _context_from_json(raw: object) -> dict[str, object] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None
