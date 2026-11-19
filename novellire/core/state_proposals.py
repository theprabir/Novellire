"""Proposed character-state updates for a chapter, reviewed before writing.

One inference reads a saved chapter against the character roster and the latest
recorded state, and proposes what changed. The server resolves every proposed
name to a real character, drops unknown or empty proposals, and writes nothing:
applying is a separate, author-triggered call that re-validates each record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..errors import (
    InvalidInputError,
    LLMResponseError,
    ProjectNotFoundError,
)
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_state_update_prompt
from ..storage.repositories import ProjectRepository
from ..storage.state_repository import (
    CharacterStateRecord,
    CharacterStateRepository,
)
from ..storage.story_repositories import ChapterRepository, CharacterRepository
from .character_states import STATE_FIELD_LIMITS, CharacterStateService
from .settings_service import GenerationSettings

PROPOSAL_SOURCE_CHARS = 12_000
PROPOSAL_MAX_UPDATES = 8
PROPOSAL_MAX_OUTPUT_TOKENS = 800
PROPOSAL_FIELD_ORDER = ("location", "status", "goals", "knowledge")


@dataclass(frozen=True)
class StateUpdateProposal:
    character_id: int
    character_name: str
    location: str
    status: str
    goals: str
    knowledge: str
    existing_state_id: int | None


@dataclass(frozen=True)
class StateUpdateInput:
    character_id: int
    location: str = ""
    status: str = ""
    goals: str = ""
    knowledge: str = ""


class CharacterStateProposalService:
    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        characters: CharacterRepository,
        states: CharacterStateRepository,
        state_service: CharacterStateService,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._characters = characters
        self._states = states
        self._state_service = state_service

    def propose(
        self, chapter_id: int, *, settings: GenerationSettings
    ) -> list[StateUpdateProposal]:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            raise InvalidInputError("That chapter no longer exists.")
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        text = (chapter.content or "").strip()
        if not text:
            raise InvalidInputError(
                "Write or draft this chapter before asking for state updates."
            )
        if len(text) > PROPOSAL_SOURCE_CHARS:
            raise InvalidInputError(
                f"This chapter is {len(text):,} characters, more than one state "
                f"pass can carry ({PROPOSAL_SOURCE_CHARS:,}). Check it chapter "
                "by chapter instead."
            )
        characters = self._characters.list_for_project(chapter.project_id)
        if not characters:
            raise InvalidInputError(
                "Add characters to this project before asking for state updates."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before proposing state updates."
            )

        states = self._states.list_for_project(chapter.project_id)
        current = {
            state.character_id: state for state in states if state.is_current
        }
        roster = "\n".join(
            f"{character.name}"
            + (f" (also called {', '.join(character.aliases)})" if character.aliases else "")
            for character in characters
        )
        recorded = "\n".join(
            f"{state.character_name} · chapter {state.chapter_position} "
            f"“{state.chapter_title}” · {_details(state)}"
            for state in current.values()
        )
        system_prompt, user_prompt = build_state_update_prompt(
            project_name=project.name,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            roster=roster,
            recorded_states=recorded,
            chapter_text=text,
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.2,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 400), PROPOSAL_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        return parse_state_proposals(
            result.text,
            characters=characters,
            states=states,
            chapter_id=chapter.id,
        )

    def apply(
        self, chapter_id: int, updates: list[StateUpdateInput]
    ) -> list[CharacterStateRecord]:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            raise InvalidInputError("That chapter no longer exists.")
        if not updates:
            raise InvalidInputError("Choose at least one proposed update to apply.")
        characters = {
            character.id: character
            for character in self._characters.list_for_project(chapter.project_id)
        }
        existing = {
            state.character_id: state
            for state in self._states.list_for_project(chapter.project_id)
            if state.chapter_id == chapter.id
        }
        applied: list[CharacterStateRecord] = []
        seen: set[int] = set()
        for update in updates:
            if update.character_id in seen:
                continue
            seen.add(update.character_id)
            if update.character_id not in characters:
                raise InvalidInputError(
                    "Choose characters from this project for every update."
                )
            record = existing.get(update.character_id)
            if record is not None:
                applied.append(
                    self._state_service.update(
                        record.id,
                        location=update.location,
                        status=update.status,
                        goals=update.goals,
                        knowledge=update.knowledge,
                    )
                )
            else:
                applied.append(
                    self._state_service.create(
                        chapter.project_id,
                        character_id=update.character_id,
                        chapter_id=chapter.id,
                        location=update.location,
                        status=update.status,
                        goals=update.goals,
                        knowledge=update.knowledge,
                    )
                )
        return applied


def parse_state_proposals(
    text: str,
    *,
    characters: list,
    states: list[CharacterStateRecord],
    chapter_id: int,
) -> list[StateUpdateProposal]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError(
            "The model did not return a state-update JSON object."
        )
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(
            "The model returned invalid state-update JSON."
        ) from exc
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an unexpected state-update structure."
        )

    by_name: dict[str, int] = {}
    for character in characters:
        by_name[character.name.casefold()] = character.id
        for alias in character.aliases:
            by_name.setdefault(alias.casefold(), character.id)
    existing = {
        state.character_id: state.id
        for state in states
        if state.chapter_id == chapter_id
    }
    proposals: list[StateUpdateProposal] = []
    seen: set[int] = set()
    items = data.get("updates")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = item.get("character")
        if not isinstance(name, str):
            continue
        character_id = by_name.get(" ".join(name.split()).casefold())
        if character_id is None or character_id in seen:
            continue
        fields = {
            field: _clip(item.get(field), STATE_FIELD_LIMITS[field])
            for field in PROPOSAL_FIELD_ORDER
        }
        if not any(fields.values()):
            continue
        seen.add(character_id)
        proposals.append(
            StateUpdateProposal(
                character_id=character_id,
                character_name=next(
                    character.name
                    for character in characters
                    if character.id == character_id
                ),
                existing_state_id=existing.get(character_id),
                **fields,
            )
        )
        if len(proposals) >= PROPOSAL_MAX_UPDATES:
            break
    return proposals


def _details(state: CharacterStateRecord) -> str:
    return "; ".join(
        part
        for part in (
            f"location: {state.location}" if state.location else "",
            f"status: {state.status}" if state.status else "",
            f"goals: {state.goals}" if state.goals else "",
            f"knowledge: {state.knowledge}" if state.knowledge else "",
        )
        if part
    )


def _clip(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
