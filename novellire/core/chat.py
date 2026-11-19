"""Chapter-scoped chat with fresh context and author-controlled notes.

Plan mode discusses the story and proposes compact planning notes. Model-written
notes are accepted while the author has not edited the notes; once the author
saves notes, subsequent model output cannot replace them. Write mode drafts prose
in the conversation without changing chapter text.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    NovellireError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..logging_setup import get_logger
from ..prompts.templates import build_chat_prompt, build_chat_revision_prompt
from ..storage.chat_repository import (
    CHAT_MODES,
    ChatDraft,
    ChatMessage,
    ChatRepository,
    ChatThread,
)
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRecord
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
CHAT_CHECKPOINT_CHARS = 1_200
CHAT_CHECKPOINT_SECONDS = 2.0
CHAT_REVISION_SOURCE_CHARS = 6_000
CHAT_REVISION_TOKENS = 1_800
REVISION_SCOPES = ("reply", "chapter")
NEW_THREAD_TITLE = "New conversation"

logger = get_logger("core.chat")

_PLANNING_BLOCK = re.compile(
    r"<planning_notes>(.*?)</planning_notes>", re.IGNORECASE | re.DOTALL
)


@dataclass(frozen=True)
class ChatThreadBundle:
    thread: ChatThread
    messages: tuple[ChatMessage, ...]
    draft: ChatDraft | None = None


@dataclass(frozen=True)
class ChatReply:
    thread: ChatThread
    user_message: ChatMessage
    assistant_message: ChatMessage
    context_chapters: tuple[dict[str, object], ...]
    context_events: int


@dataclass(frozen=True)
class _ChatTurn:
    """Everything needed to generate one reply, prepared before streaming."""

    thread: ChatThread
    system_prompt: str
    user_prompt: str
    model: str
    num_predict: int
    user_message: ChatMessage
    context_chapters: tuple[dict[str, object], ...]
    context_events: int
    revision_scope: str = ""
    revision_of: int | None = None


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
            draft=self._threads.get_draft(thread.id),
        )

    def update_thread(
        self,
        thread_id: int,
        *,
        planning_notes: str | None = None,
        title: str | None = None,
        mode: str | None = None,
    ) -> ChatThread:
        thread = self._require_thread(thread_id)
        if mode is not None:
            normalized_mode = (mode or "").strip().casefold()
            if normalized_mode not in CHAT_MODES:
                raise InvalidInputError(
                    "Choose Plan or Write mode for a conversation."
                )
            self._threads.set_mode(thread.id, normalized_mode)
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
        turn = self._prepare_turn(
            thread_id,
            instructions=instructions,
            settings=settings,
            target_words=target_words,
        )
        return self._generate(turn, settings)

    def _generate(self, turn: _ChatTurn, settings: GenerationSettings) -> ChatReply:
        """Generate one complete reply outside a stream."""
        result = self._provider.generate(
            GenerationRequest(
                prompt=turn.user_prompt,
                system_prompt=turn.system_prompt,
                model=turn.model,
                temperature=settings.temperature,
                top_p=settings.top_p,
                num_predict=turn.num_predict,
                context_window=settings.context_window,
            )
        )
        text = (result.text or "").strip()
        if not text:
            raise LLMResponseError("The model returned an empty response. Try again.")
        assistant_message, updated = self._finish_turn(
            turn, text, result.model or turn.model
        )
        return ChatReply(
            thread=updated,
            user_message=turn.user_message,
            assistant_message=assistant_message,
            context_chapters=turn.context_chapters,
            context_events=turn.context_events,
        )

    def _prepare_turn(
        self,
        thread_id: int,
        *,
        instructions: str,
        settings: GenerationSettings,
        target_words: int,
    ) -> _ChatTurn:
        """Validate, store the author message, and rebuild prompt context."""
        thread = self._require_thread(thread_id)
        project = self._require_project(thread.project_id)
        text = (instructions or "").strip()
        if not text:
            raise InvalidInputError("Write a message before sending.")
        if len(text) > CHAT_INSTRUCTION_LIMIT:
            raise InvalidInputError(
                f"Messages must stay under {CHAT_INSTRUCTION_LIMIT} characters."
            )
        model = self._require_model(settings, "chatting")
        self._require_no_draft(thread, "sending another message")
        chapter = self._chapter_for(thread)
        # History is every message before this one.
        history = _format_history(self._threads.list_messages(thread.id))
        prompt_text = text
        if thread.mode == "write":
            target = max(50, min(int(target_words), 6_000))
            prompt_text = f"{text}\n\nTarget length: about {target} words."

        context = self._retrieval(
            project,
            thread,
            instructions=prompt_text,
            chapter=chapter,
            settings=settings,
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
        return self._turn(
            thread,
            text,
            model=model,
            num_predict=min(max(settings.num_predict, 256), CHAT_OUTPUT_TOKENS),
            context=context,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def stream_message(
        self,
        thread_id: int,
        *,
        instructions: str,
        settings: GenerationSettings,
        target_words: int = 900,
    ) -> Iterator[dict[str, object]]:
        """Prepare eagerly, then stream reply events as newline-delimited JSON.

        Preparation happens before the response starts, so a validation or
        missing-model failure is still an ordinary 4xx rather than a stream that
        dies on its first event.
        """
        turn = self._prepare_turn(
            thread_id,
            instructions=instructions,
            settings=settings,
            target_words=target_words,
        )
        return self._reply_events(turn, settings)

    def revise_message(
        self,
        thread_id: int,
        *,
        instructions: str,
        settings: GenerationSettings,
        scope: str = "reply",
        message_id: int | None = None,
    ) -> ChatReply:
        turn = self._prepare_revision_turn(
            thread_id,
            scope=scope,
            message_id=message_id,
            instructions=instructions,
            settings=settings,
        )
        return self._generate(turn, settings)

    def stream_revision(
        self,
        thread_id: int,
        *,
        instructions: str,
        settings: GenerationSettings,
        scope: str = "reply",
        message_id: int | None = None,
    ) -> Iterator[dict[str, object]]:
        """Stream a revision without changing the prose it came from."""
        turn = self._prepare_revision_turn(
            thread_id,
            scope=scope,
            message_id=message_id,
            instructions=instructions,
            settings=settings,
        )
        return self._reply_events(turn, settings)

    def _prepare_revision_turn(
        self,
        thread_id: int,
        *,
        scope: str,
        message_id: int | None,
        instructions: str,
        settings: GenerationSettings,
    ) -> _ChatTurn:
        """Validate a revision request and build its prompt.

        A revision never overwrites the prose it came from. The result is a new
        message that the author can compare with the original, and insert into
        the chapter through the normal locked edit path.
        """
        thread = self._require_thread(thread_id)
        project = self._require_project(thread.project_id)
        normalized_scope = (scope or "").strip().casefold()
        if normalized_scope not in REVISION_SCOPES:
            raise InvalidInputError(
                "Choose whether to revise a reply or the chapter."
            )
        if thread.mode != "write":
            raise InvalidInputError(
                "Switch this conversation to Write mode before revising prose."
            )
        text = (instructions or "").strip()
        if not text:
            raise InvalidInputError("Describe how the prose should change.")
        if len(text) > CHAT_INSTRUCTION_LIMIT:
            raise InvalidInputError(
                "Revision instructions must stay under "
                f"{CHAT_INSTRUCTION_LIMIT} characters."
            )
        model = self._require_model(settings, "revising prose")
        self._require_no_draft(thread, "revising")
        chapter = self._chapter_for(thread)
        revision_of: int | None = None
        if normalized_scope == "reply":
            target = (
                self._threads.get_message(message_id)
                if message_id is not None
                else _last_assistant_message(
                    self._threads.list_messages(thread.id)
                )
            )
            if (
                target is None
                or target.thread_id != thread.id
                or target.role != "assistant"
            ):
                raise InvalidInputError("There is no model reply to revise.")
            source_text = target.content.strip()
            if not source_text:
                raise InvalidInputError("That reply is empty.")
            revision_of = target.id
        else:
            if chapter is None:
                raise InvalidInputError(
                    "This conversation is project-wide. Start a chapter-scoped "
                    "chat to revise its prose."
                )
            if chapter.status == "approved":
                raise InvalidInputError(
                    "This chapter is approved. Reopen it before revising it."
                )
            source_text = chapter.content.strip()
            if not source_text:
                raise InvalidInputError("Add chapter text before revising it.")
        # A clipped source would let a partial revision replace the whole
        # chapter, so prose over the budget is refused instead.
        if len(source_text) > CHAT_REVISION_SOURCE_CHARS:
            noun = "chapter" if normalized_scope == "chapter" else "reply"
            raise InvalidInputError(
                f"This {noun} is {len(source_text):,} characters, more than one "
                f"revision can carry ({CHAT_REVISION_SOURCE_CHARS:,}). Split it "
                "or revise a shorter passage, so no part of the prose is dropped."
            )

        context = self._retrieval(
            project,
            thread,
            instructions=text,
            chapter=chapter,
            settings=settings,
            output_tokens=min(settings.num_predict, CHAT_REVISION_TOKENS),
        )
        system_prompt, user_prompt = build_chat_revision_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            scope=normalized_scope,
            instructions=text,
            source_text=source_text,
            chapter_title=chapter.title if chapter else "",
            chapter_plan=context.chapter_plan,
            planning_notes=thread.planning_notes,
            **_context_blocks(context),
        )
        return self._turn(
            thread,
            text,
            model=model,
            num_predict=min(max(settings.num_predict, 512), CHAT_REVISION_TOKENS),
            context=context,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            revision_scope=normalized_scope,
            revision_of=revision_of,
        )

    def _reply_events(
        self, turn: _ChatTurn, settings: GenerationSettings
    ) -> Iterator[dict[str, object]]:
        yield {
            "type": "start",
            "thread": asdict(turn.thread),
            "user": asdict(turn.user_message),
        }
        request = GenerationRequest(
            prompt=turn.user_prompt,
            system_prompt=turn.system_prompt,
            model=turn.model,
            temperature=settings.temperature,
            top_p=settings.top_p,
            num_predict=turn.num_predict,
            context_window=settings.context_window,
        )
        pieces: list[str] = []
        model = turn.model
        # A reply is checkpointed while it streams so a crash, a closed browser,
        # or a shutdown leaves recoverable text instead of nothing.
        checkpoint = _Checkpoint(self._threads, turn.thread.id)
        try:
            stream = getattr(self._provider, "generate_stream", None)
            if stream is None:
                result = self._provider.generate(request)
                text = (result.text or "").strip()
                if not text:
                    raise LLMResponseError(
                        "The model returned an empty response. Try again."
                    )
                pieces.append(text)
                yield {"type": "delta", "text": text}
                model = result.model or model
            else:
                for chunk in stream(request):
                    if chunk.text:
                        pieces.append(chunk.text)
                        yield {"type": "delta", "text": chunk.text}
                        checkpoint.observe(chunk.text, pieces, model)
                    if chunk.model:
                        model = chunk.model
            text = "".join(pieces).strip()
            if not text:
                raise LLMResponseError(
                    "The model returned an empty response. Try again."
                )
            assistant_message, thread = self._finish_turn(turn, text, model)
            checkpoint.clear()
            yield {
                "type": "done",
                "thread": asdict(thread),
                "assistant": asdict(assistant_message),
                "context": _turn_context(turn),
            }
        except GeneratorExit:
            # The author stopped the reply or closed the page. Keep what arrived.
            partial = "".join(pieces).strip()
            if partial:
                self._save_interrupted(turn, partial, model)
            checkpoint.clear()
            raise
        except NovellireError as exc:
            # Any checkpoint stays, so the partial reply can be kept or
            # discarded once the failure is reported.
            yield {"type": "error", "message": str(exc)}
        except Exception:  # noqa: BLE001 - a stream must end with a readable event
            logger.exception("Chat stream failed unexpectedly")
            yield {
                "type": "error",
                "message": "The reply failed while streaming. Try again.",
            }

    def _finish_turn(
        self, turn: _ChatTurn, text: str, model: str
    ) -> tuple[ChatMessage, ChatThread]:
        thread = turn.thread
        if thread.mode == "plan":
            suggested, text = _extract_planning_notes(text)
            if suggested and thread.planning_notes_source != "author":
                thread = self._threads.set_planning_notes(
                    thread.id, suggested, source="model"
                )
        assistant_message = self._threads.add_message(
            thread.id,
            role="assistant",
            content=text,
            model=model,
            context=_turn_context(turn),
            revision_scope=turn.revision_scope,
            revision_of=turn.revision_of,
        )
        refreshed = self._threads.get_thread(thread.id)
        if refreshed is None:
            raise RecordNotFoundError("That conversation no longer exists.")
        return assistant_message, refreshed

    def _save_interrupted(self, turn: _ChatTurn, text: str, model: str) -> None:
        try:
            self._finish_turn(turn, text, model)
        except Exception:  # noqa: BLE001 - the connection is already gone
            logger.warning("Could not store an interrupted chat reply")

    def insert_reply(
        self,
        thread_id: int,
        message_id: int,
        *,
        replace: bool = False,
    ) -> ChapterRecord:
        """Write a Write-mode reply into its chapter, respecting the approval lock."""
        thread = self._require_thread(thread_id)
        message = self._threads.get_message(message_id)
        if message is None or message.thread_id != thread.id:
            raise RecordNotFoundError(
                "That reply no longer exists in this conversation."
            )
        if message.role != "assistant":
            raise InvalidInputError(
                "Only a model reply can be inserted into the chapter."
            )
        if thread.mode != "write":
            raise InvalidInputError(
                "Switch this conversation to Write mode before inserting prose."
            )
        if thread.chapter_id is None:
            raise InvalidInputError(
                "This conversation is project-wide. Start a chapter-scoped chat "
                "to insert prose."
            )
        chapter = self._chapters.require_chapter(thread.chapter_id)
        prose = message.content.strip()
        if not prose:
            raise InvalidInputError("That reply is empty.")
        existing = chapter.content.rstrip()
        content = prose if replace or not existing else f"{existing}\n\n{prose}"
        if content == chapter.content:
            return chapter
        # ChapterService enforces the approval lock and snapshots the revision.
        return self._chapters.update_chapter(chapter.id, content=content)

    def recover_draft(self, thread_id: int) -> ChatMessage:
        """Keep an interrupted reply checkpoint as a stored model message.

        Planning notes are not re-derived from a partial reply; the author can
        still edit the notes by hand.
        """
        thread = self._require_thread(thread_id)
        draft = self._threads.get_draft(thread.id)
        if draft is None:
            raise RecordNotFoundError("There is no interrupted reply to keep.")
        message = self._threads.add_message(
            thread.id,
            role="assistant",
            content=draft.content,
            model=draft.model,
        )
        self._threads.clear_draft(thread.id)
        return message

    def discard_draft(self, thread_id: int) -> None:
        thread = self._require_thread(thread_id)
        self._threads.clear_draft(thread.id)

    def _require_project(self, project_id: int):  # noqa: ANN202 - project record
        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        return project

    def _require_model(self, settings: GenerationSettings, action: str) -> str:
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                f"Choose a model before {action}. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )
        return model

    def _require_no_draft(self, thread: ChatThread, action: str) -> None:
        if self._threads.get_draft(thread.id) is not None:
            raise InvalidInputError(
                "This conversation has an interrupted reply. Keep or discard it "
                f"before {action}."
            )

    def _chapter_for(self, thread: ChatThread) -> ChapterRecord | None:
        if thread.chapter_id is None:
            return None
        return self._chapters.get_chapter(thread.chapter_id)

    def _retrieval(
        self,
        project,  # noqa: ANN001 - project record
        thread: ChatThread,
        *,
        instructions: str,
        chapter: ChapterRecord | None,
        settings: GenerationSettings,
        output_tokens: int,
    ) -> GenerationContext:
        """Rebuild the retrieval context shared by chat and revision turns."""
        return self._context_builder.build(
            project.id,
            instructions=instructions,
            chapter_id=thread.chapter_id,
            chapter_title=chapter.title if chapter else "",
            context_notes=thread.planning_notes,
            context_window=settings.context_window,
            output_tokens=output_tokens,
        )

    def _turn(
        self,
        thread: ChatThread,
        instructions: str,
        *,
        model: str,
        num_predict: int,
        context: GenerationContext,
        system_prompt: str,
        user_prompt: str,
        revision_scope: str = "",
        revision_of: int | None = None,
    ) -> _ChatTurn:
        """Store the author message and finish describing one prepared turn."""
        user_message = self._threads.add_message(
            thread.id, role="user", content=instructions
        )
        return _ChatTurn(
            thread=self._auto_title(thread, instructions),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            num_predict=num_predict,
            user_message=user_message,
            context_chapters=tuple(
                {"id": item.id, "position": item.position, "title": item.title}
                for item in context.memory_chapters
            ),
            context_events=len(context.memory_events),
            revision_scope=revision_scope,
            revision_of=revision_of,
        )

    def _auto_title(self, thread: ChatThread, text: str) -> ChatThread:
        """Name a new conversation from its first message."""
        if thread.title != NEW_THREAD_TITLE:
            return thread
        self._threads.set_title(thread.id, _title_from(text))
        renamed = self._threads.get_thread(thread.id)
        return renamed or thread

    def _require_thread(self, thread_id: int) -> ChatThread:
        thread = self._threads.get_thread(thread_id)
        if thread is None:
            raise RecordNotFoundError("That conversation no longer exists.")
        return thread


class _Checkpoint:
    """Best-effort persistence of a reply while it streams.

    A checkpoint is written at most once per ``CHAT_CHECKPOINT_CHARS`` characters
    or ``CHAT_CHECKPOINT_SECONDS`` seconds, so recovery costs a handful of small
    writes rather than one per token. A failed checkpoint is logged and never
    interrupts the reply itself.
    """

    def __init__(self, threads: ChatRepository, thread_id: int) -> None:
        self._threads = threads
        self._thread_id = thread_id
        self._observed = 0
        self._saved = 0
        self._saved_at = time.monotonic()

    def observe(self, chunk: str, pieces: list[str], model: str) -> None:
        if not chunk:
            return
        self._observed += len(chunk)
        now = time.monotonic()
        if (
            self._observed - self._saved < CHAT_CHECKPOINT_CHARS
            and now - self._saved_at < CHAT_CHECKPOINT_SECONDS
        ):
            return
        self._write(pieces, model, now)

    def _write(self, pieces: list[str], model: str, now: float) -> None:
        content = "".join(pieces).strip()
        if not content:
            return
        try:
            self._threads.save_draft(
                self._thread_id, content=content, model=model
            )
        except Exception:  # noqa: BLE001 - a checkpoint must not break the reply
            logger.warning("Could not checkpoint an in-progress chat reply")
            return
        self._saved = self._observed
        self._saved_at = now

    def clear(self) -> None:
        try:
            self._threads.clear_draft(self._thread_id)
        except Exception:  # noqa: BLE001 - the reply or its message already exists
            logger.warning("Could not clear a chat reply checkpoint")


def _turn_context(turn: _ChatTurn) -> dict[str, object]:
    """What retrieval handed this reply, kept with the message for the drawer."""
    return {
        "chapters": list(turn.context_chapters),
        "events": turn.context_events,
    }


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


def _last_assistant_message(messages: list[ChatMessage]) -> ChatMessage | None:
    for message in reversed(messages):
        if message.role == "assistant":
            return message
    return None


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
