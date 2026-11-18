"""Chapter-scoped chat with fresh context and author-controlled notes.

Plan mode discusses the story and proposes compact planning notes. Model-written
notes are accepted while the author has not edited the notes; once the author
saves notes, subsequent model output cannot replace them. Write mode drafts prose
in the conversation without changing chapter text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_chat_prompt
from ..storage.chat_repository import (
    CHAT_MODES,
    ChatMessage,
    ChatRepository,
    ChatThread,
)
from ..storage.repositories import ProjectRepository
from .chapters import ChapterService
from .context import GenerationContext, GenerationContextBuilder
from .settings_service import GenerationSettings

CHAT_INSTRUCTION_LIMIT = 8_000
CHAT_NOTES_LIMIT = 8_000
CHAT_TITLE_LIMIT = 80
CHAT_HISTORY_MESSAGES = 12
CHAT_HISTORY_CHARS = 1_200
CHAT_CHAPTER_CHARS = 6_000
CHAT_OUTPUT_TOKENS = 900
NEW_THREAD_TITLE = "New conversation"

_PLANNING_BLOCK = re.compile(
    r"<planning_notes>(.*?)</planning_notes>", re.IGNORECASE | re.DOTALL
)


@dataclass(frozen=True)
class ChatThreadBundle:
    thread: ChatThread
    messages: tuple[ChatMessage, ...]


@dataclass(frozen=True)
class ChatReply:
    thread: ChatThread
    user_message: ChatMessage
    assistant_message: ChatMessage
    context_chapters: tuple[dict[str, object], ...]
    context_events: int


class ChatService:
    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterService,
        threads: ChatRepository,
        context_builder: GenerationContextBuilder,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._threads = threads
        self._context_builder = context_builder

    def list_threads(self, project_id: int) -> list[ChatThread]:
        self._require_project(project_id)
        return self._threads.list_threads(project_id)

    def create_thread(
        self,
        *,
        project_id: int,
        mode: str,
        chapter_id: int | None = None,
        title: str = "",
    ) -> ChatThread:
        self._require_project(project_id)
        normalized_mode = (mode or "").strip().casefold()
        if normalized_mode not in CHAT_MODES:
            raise InvalidInputError("Choose Plan or Write mode for a conversation.")
        if chapter_id is not None:
            chapter = self._chapters.require_chapter(chapter_id)
            if chapter.project_id != project_id:
                raise InvalidInputError(
                    "That chapter belongs to another project."
                )
        cleaned_title = _clean_title(title) or NEW_THREAD_TITLE
        return self._threads.create_thread(
            project_id=project_id,
            chapter_id=chapter_id,
            mode=normalized_mode,
            title=cleaned_title,
        )

    def get_thread_bundle(self, thread_id: int) -> ChatThreadBundle:
        thread = self._require_thread(thread_id)
        return ChatThreadBundle(
            thread=thread,
            messages=tuple(self._threads.list_messages(thread.id)),
        )

    def update_thread(
        self,
        thread_id: int,
        *,
        planning_notes: str | None = None,
        title: str | None = None,
    ) -> ChatThread:
        thread = self._require_thread(thread_id)
        if title is not None:
            cleaned = _clean_title(title)
            if cleaned:
                self._threads.set_title(thread.id, cleaned)
        if planning_notes is not None:
            notes = (planning_notes or "").strip()
            if len(notes) > CHAT_NOTES_LIMIT:
                raise InvalidInputError(
                    f"Planning notes must stay under {CHAT_NOTES_LIMIT} characters."
                )
            self._threads.set_planning_notes(
                thread.id, notes, source="author"
            )
        updated = self._threads.get_thread(thread.id)
        if updated is None:
            raise RecordNotFoundError("That conversation no longer exists.")
        return updated

    def send_message(
        self,
        thread_id: int,
        *,
        instructions: str,
        settings: GenerationSettings,
        target_words: int = 900,
    ) -> ChatReply:
        thread = self._require_thread(thread_id)
        project = self._projects.get(thread.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        text = (instructions or "").strip()
        if not text:
            raise InvalidInputError("Write a message before sending.")
        if len(text) > CHAT_INSTRUCTION_LIMIT:
            raise InvalidInputError(
                f"Messages must stay under {CHAT_INSTRUCTION_LIMIT} characters."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before chatting. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )

        chapter = (
            self._chapters.get_chapter(thread.chapter_id)
            if thread.chapter_id is not None
            else None
        )
        user_message = self._threads.add_message(
            thread.id, role="user", content=text
        )
        history_messages = self._threads.list_messages(thread.id)[:-1]
        history = _format_history(history_messages)
        prompt_text = text
        if thread.mode == "write":
            target = max(50, min(int(target_words), 6_000))
            prompt_text = f"{text}\n\nTarget length: about {target} words."

        context = self._context_builder.build(
            project.id,
            instructions=prompt_text,
            chapter_id=thread.chapter_id,
            chapter_title=chapter.title if chapter else "",
            context_notes=thread.planning_notes,
            context_window=settings.context_window,
            output_tokens=min(settings.num_predict, CHAT_OUTPUT_TOKENS),
        )
        system_prompt, user_prompt = build_chat_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            mode=thread.mode,
            instructions=prompt_text,
            chapter_title=chapter.title if chapter else "",
            chapter_plan=context.chapter_plan,
            chapter_text=_clip(
                chapter.content if chapter is not None else "",
                CHAT_CHAPTER_CHARS,
            ),
            planning_notes=thread.planning_notes,
            history=history,
            **_context_blocks(context),
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=settings.temperature,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 256), CHAT_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        reply = (result.text or "").strip()
        if not reply:
            raise LLMResponseError(
                "The model returned an empty response. Try again."
            )

        if thread.mode == "plan":
            suggested, reply = _extract_planning_notes(reply)
            if suggested and thread.planning_notes_source != "author":
                thread = self._threads.set_planning_notes(
                    thread.id, suggested, source="model"
                )
        assistant_message = self._threads.add_message(
            thread.id,
            role="assistant",
            content=reply,
            model=result.model or model,
        )
        if thread.title == NEW_THREAD_TITLE:
            self._threads.set_title(thread.id, _title_from(text))
        refreshed = self._threads.get_thread(thread.id)
        if refreshed is None:
            raise RecordNotFoundError("That conversation no longer exists.")
        return ChatReply(
            thread=refreshed,
            user_message=user_message,
            assistant_message=assistant_message,
            context_chapters=tuple(
                {
                    "id": item.id,
                    "position": item.position,
                    "title": item.title,
                }
                for item in context.memory_chapters
            ),
            context_events=len(context.memory_events),
        )

    def _require_project(self, project_id: int):  # noqa: ANN202 - project record
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        return project

    def _require_thread(self, thread_id: int) -> ChatThread:
        thread = self._threads.get_thread(thread_id)
        if thread is None:
            raise RecordNotFoundError("That conversation no longer exists.")
        return thread


def _context_blocks(context: GenerationContext) -> dict[str, str]:
    def clip(value: str, limit: int) -> str:
        return (value or "")[:limit]

    return {
        "master_bible": clip(
            context.master_bible, context.budget.master_bible_chars
        ),
        "character_bible": clip(
            context.character_bible, context.budget.character_bible_chars
        ),
        "chapter_map": clip(
            context.chapter_map, context.budget.chapter_map_chars
        ),
        "style_guide": clip(
            context.style_guide, context.budget.style_guide_chars
        ),
        "earlier_chapters": context.earlier_chapters,
        "earlier_events": context.earlier_events,
        "bible_entries": context.bible_entries,
        "character_profiles": context.character_profiles,
        "relationship_records": context.relationship_records,
        "character_states": context.character_states,
    }


def _format_history(messages: list[ChatMessage]) -> str:
    selected = messages[-CHAT_HISTORY_MESSAGES:]
    lines = []
    for message in selected:
        label = "Author" if message.role == "user" else "Novellire"
        content = " ".join(message.content.split())
        lines.append(f"{label}: {content[:CHAT_HISTORY_CHARS]}")
    return "\n\n".join(lines)


def _extract_planning_notes(text: str) -> tuple[str, str]:
    match = _PLANNING_BLOCK.search(text)
    if match is None:
        return "", text.strip()
    notes = match.group(1).strip()[:CHAT_NOTES_LIMIT]
    reply = _PLANNING_BLOCK.sub("", text).strip()
    return notes, reply


def _clean_title(value: str) -> str:
    return " ".join((value or "").split())[:CHAT_TITLE_LIMIT].strip()


def _title_from(text: str) -> str:
    title = " ".join(text.split())
    if len(title) <= CHAT_TITLE_LIMIT:
        return title
    return title[: CHAT_TITLE_LIMIT - 1].rstrip() + "…"


def _clip(text: str, limit: int) -> str:
    return (text or "")[:limit]
