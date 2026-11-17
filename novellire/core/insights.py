"""Derived chapter insights: state, locations, relationships, and threads.

These records are deliberately separate from author-controlled memory. They are
proposals produced from chapter prose, never silent edits to character-state or
relationship records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    ProjectNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_chapter_insight_prompt
from ..storage.analysis_repository import (
    ChapterInsightRecord,
    ChapterInsightRepository,
)
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRepository, CharacterRepository
from .relationships import RELATIONSHIP_TYPE_LABELS
from .settings_service import GenerationSettings
from .text import content_hash

INSIGHT_CHAR_LIMIT = 12_000
INSIGHT_MAX_OUTPUT_TOKENS = 1_000
INSIGHT_MAX_STATES = 12
INSIGHT_MAX_LOCATIONS = 12
INSIGHT_MAX_RELATIONSHIPS = 8
INSIGHT_MAX_THREADS = 12
INSIGHT_FIELD_LIMIT = 400
INSIGHT_NAME_LIMIT = 200


@dataclass(frozen=True)
class InsightOutcome:
    insight: ChapterInsightRecord
    model: str
    duration_ms: int


class ChapterInsightService:
    """Extract bounded derived insights from one chapter."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        characters: CharacterRepository,
        insights: ChapterInsightRepository,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._characters = characters
        self._insights = insights

    def extract(
        self, chapter_id: int, settings: GenerationSettings
    ) -> InsightOutcome:
        chapter = self._chapters.get_chapter(chapter_id)
        if chapter is None:
            raise InvalidInputError("That chapter no longer exists.")
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        content = chapter.content.strip()
        if not content:
            raise InvalidInputError("Add chapter text before extracting insights.")
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before extracting insights."
            )

        names = ", ".join(
            character.name
            for character in self._characters.list_for_project(chapter.project_id)[:40]
        )
        system_prompt, user_prompt = build_chapter_insight_prompt(
            project_name=project.name,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            content=content[:INSIGHT_CHAR_LIMIT],
            characters=names,
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.1,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 500), INSIGHT_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        drafts = parse_insight_payload(result.text)
        record = self._insights.upsert(
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            content_hash=content_hash(chapter.content),
            model=result.model or model,
            **drafts,
        )
        return InsightOutcome(
            insight=record,
            model=result.model or model,
            duration_ms=result.duration_ms,
        )


def parse_insight_payload(text: str) -> dict[str, Any]:
    """Parse the first JSON object and normalise every field and bound."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError(
            "The model did not return a chapter-insight JSON object."
        )
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(
            "The model returned invalid chapter-insight JSON."
        ) from exc
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an unexpected chapter-insight structure."
        )

    states = []
    for item in _list(data.get("character_states"))[:INSIGHT_MAX_STATES]:
        if not isinstance(item, dict):
            continue
        name = _name(item.get("name"))
        if not name:
            continue
        states.append(
            {
                "name": name,
                "location": _text(item.get("location")),
                "status": _text(item.get("status")),
                "goals": _text(item.get("goals")),
                "knowledge": _text(item.get("knowledge")),
            }
        )

    locations = []
    for item in _list(data.get("locations"))[:INSIGHT_MAX_LOCATIONS]:
        if not isinstance(item, dict):
            continue
        name = _name(item.get("name"))
        if not name:
            continue
        locations.append(
            {"name": name, "description": _text(item.get("description"))}
        )

    relationships = []
    for item in _list(data.get("relationships"))[:INSIGHT_MAX_RELATIONSHIPS]:
        if not isinstance(item, dict):
            continue
        first = _name(item.get("character_a"))
        second = _name(item.get("character_b"))
        if not first or not second or first.casefold() == second.casefold():
            continue
        relation_type = str(item.get("relation_type") or "").strip().casefold()
        relationships.append(
            {
                "character_a": first,
                "character_b": second,
                "relation_type": (
                    relation_type
                    if relation_type in RELATIONSHIP_TYPE_LABELS
                    else "other"
                ),
                "description": _text(item.get("description")),
            }
        )

    threads = []
    for item in _list(data.get("open_threads"))[:INSIGHT_MAX_THREADS]:
        if isinstance(item, str):
            cleaned = _text(item)
            if cleaned:
                threads.append(cleaned)

    return {
        "character_states": states,
        "locations": locations,
        "relationships": relationships,
        "open_threads": threads,
    }


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _name(value: Any) -> str:
    return _text(value)[:INSIGHT_NAME_LIMIT]


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:INSIGHT_FIELD_LIMIT].strip()
