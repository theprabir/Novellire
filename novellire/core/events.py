"""Extract structured episodic events from a chapter.

The model returns JSON, but small local models are unreliable about fencing and
occasional chatter, so parsing is tolerant: the first object is read, unknown
fields are ignored, and every list is cleaned and bounded before storage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    ProjectNotFoundError,
    RecordNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_event_extraction_prompt
from ..storage.event_repository import EventDraft, EventRepository, NarrativeEvent
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import CharacterRecord, CharacterRepository
from .chapters import ChapterService
from .settings_service import GenerationSettings

EVENT_CHAR_LIMIT = 12_000
EVENT_MAX_OUTPUT_TOKENS = 900
EVENT_MAX_ITEMS = 12
EVENT_DETAIL_LIMIT = 200
EVENT_LIST_LIMIT = 8
EVENT_SUMMARY_EDIT_LIMIT = 1_000


@dataclass(frozen=True)
class EventExtractionOutcome:
    events: list[NarrativeEvent]
    model: str
    duration_ms: int


class EventExtractionService:
    """Ask the model for events, validate them, and replace the chapter's rows."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterService,
        events: EventRepository,
        characters: CharacterRepository,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._events = events
        self._characters = characters

    def extract(
        self, chapter_id: int, settings: GenerationSettings
    ) -> EventExtractionOutcome:
        chapter = self._chapters.require_chapter(chapter_id)
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )

        content = chapter.content.strip()
        if not content:
            raise InvalidInputError(
                "Add chapter text before extracting events."
            )

        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before extracting events. Install one with "
                "`ollama pull qwen2.5:1.5b` if the list is empty."
            )

        system_prompt, user_prompt = build_event_extraction_prompt(
            project_name=project.name,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            content=content[:EVENT_CHAR_LIMIT],
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.1,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 400), EVENT_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )

        drafts = parse_event_payload(result.text)
        events = self._events.replace_for_chapter(
            chapter.project_id,
            chapter.id,
            drafts,
            model=result.model or model,
        )
        self.ensure_links(chapter.project_id)
        events = self._events.list_for_chapter(chapter.id)
        return EventExtractionOutcome(
            events=events,
            model=result.model or model,
            duration_ms=result.duration_ms,
        )

    def ensure_links(self, project_id: int) -> None:
        """Resolve character names and aliases for events that need it."""
        characters = self._characters.list_for_project(project_id)
        for event in self._events.list_unresolved(project_id):
            self._events.set_character_links(
                event.id, match_event_characters(event, characters)
            )

    def update_event(
        self,
        event_id: int,
        *,
        summary: str,
        characters: list[str],
        locations: list[str],
        objects: list[str],
        threads: list[str],
    ) -> NarrativeEvent:
        event = self._events.get(event_id)
        if event is None:
            raise RecordNotFoundError("That event no longer exists.")
        cleaned_summary = _text(summary, EVENT_SUMMARY_EDIT_LIMIT)
        if not cleaned_summary:
            raise InvalidInputError("An event needs a summary.")
        updated = self._events.update(
            event_id,
            summary=cleaned_summary,
            characters=_clean_list(characters),
            locations=_clean_list(locations),
            objects=_clean_list(objects),
            threads=_clean_list(threads),
        )
        if updated is None:
            raise RecordNotFoundError("That event no longer exists.")
        self.ensure_links(updated.project_id)
        refreshed = self._events.get(event_id)
        if refreshed is None:
            raise RecordNotFoundError("That event no longer exists.")
        return refreshed

    def delete_event(self, event_id: int) -> None:
        if not self._events.delete(event_id):
            raise RecordNotFoundError("That event no longer exists.")


def match_event_characters(
    event: NarrativeEvent, characters: list[CharacterRecord]
) -> dict[int, str]:
    """Map matching character profiles to the name or alias that matched."""
    mentions = {_normalize(value) for value in event.characters}
    summary = _normalize(event.summary)
    links: dict[int, str] = {}
    for character in characters:
        matched = _matched_name(character, mentions, summary)
        if matched:
            links[character.id] = matched
    return links


def _matched_name(
    character: CharacterRecord, mentions: set[str], summary: str
) -> str:
    for name in (character.name, *character.aliases):
        cleaned = name.strip()
        normalized = _normalize(cleaned)
        if len(normalized) < 3:
            continue
        if normalized in mentions or _contains_phrase(summary, normalized):
            return cleaned
    first = character.name.strip().split(" ")[0]
    normalized_first = _normalize(first)
    if len(normalized_first) >= 3 and (
        normalized_first in mentions
        or _contains_phrase(summary, normalized_first)
    ):
        return first
    return ""


def _normalize(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _contains_phrase(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    return (
        re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.UNICODE
        )
        is not None
    )


def _clean_list(values: list[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for value in values:
        text = _text(value, EVENT_DETAIL_LIMIT)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= EVENT_LIST_LIMIT:
            break
    return tuple(cleaned)


def parse_event_payload(text: str) -> list[EventDraft]:
    """Read the first JSON object in a model reply as event drafts."""
    cleaned = (text or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMResponseError(
            "The model did not return event data. Try again, or use a larger model."
        )
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise LLMResponseError(
            "The model returned malformed event data. Try again."
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise LLMResponseError(
            "The model returned event data in an unexpected shape. Try again."
        )

    drafts: list[EventDraft] = []
    for item in payload["events"]:
        if not isinstance(item, dict):
            continue
        summary = _text(item.get("summary"), EVENT_DETAIL_LIMIT)
        if not summary:
            continue
        drafts.append(
            EventDraft(
                summary=summary,
                characters=_strings(item.get("characters")),
                locations=_strings(item.get("locations")),
                objects=_strings(item.get("objects")),
                threads=_strings(item.get("threads")),
            )
        )
        if len(drafts) >= EVENT_MAX_ITEMS:
            break
    return drafts


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    cleaned: list[str] = []
    for item in value:
        text = _text(item, EVENT_DETAIL_LIMIT)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= EVENT_LIST_LIMIT:
            break
    return tuple(cleaned)
