"""Proposed relationship changes for a chapter, reviewed before writing.

One inference reads a saved chapter against the character roster and the
recorded relationships, and proposes how a pair now stands. The server resolves
every name to a real character and drops unknown, repeated, or single-character
pairs, so the proposal list can never name someone the project does not hold.
Applying is a separate, author-triggered call that records each relationship's
state for that chapter, so the ledger shows how it evolved.
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
from ..prompts.templates import build_relationship_update_prompt
from ..storage.relationship_repository import (
    RelationshipRecord,
    RelationshipRepository,
)
from ..storage.relationship_snapshot_repository import (
    RelationshipSnapshotRecord,
    RelationshipSnapshotRepository,
)
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRepository, CharacterRepository
from .relationships import (
    RELATIONSHIP_DESCRIPTION_LIMIT,
    RELATIONSHIP_TYPE_LABELS,
    RelationshipService,
)
from .settings_service import GenerationSettings

PROPOSAL_SOURCE_CHARS = 12_000
PROPOSAL_MAX_UPDATES = 6
PROPOSAL_MAX_OUTPUT_TOKENS = 800


@dataclass(frozen=True)
class RelationshipProposal:
    character_a_id: int
    character_b_id: int
    character_a_name: str
    character_b_name: str
    relation_type: str
    description: str
    existing_relationship_id: int | None
    existing_status: str


@dataclass(frozen=True)
class RelationshipUpdateInput:
    character_a_id: int
    character_b_id: int
    relation_type: str
    description: str = ""


@dataclass(frozen=True)
class RelationshipEvolution:
    relationship: RelationshipRecord
    snapshot: RelationshipSnapshotRecord


class RelationshipEvolutionService:
    """Propose how relationships change, then record them chapter by chapter."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        characters: CharacterRepository,
        relationships: RelationshipRepository,
        relationship_service: RelationshipService,
        snapshots: RelationshipSnapshotRepository,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._characters = characters
        self._relationships = relationships
        self._relationship_service = relationship_service
        self._snapshots = snapshots

    def propose(
        self, chapter_id: int, *, settings: GenerationSettings
    ) -> list[RelationshipProposal]:
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
                "Write or draft this chapter before asking for relationship "
                "changes."
            )
        if len(text) > PROPOSAL_SOURCE_CHARS:
            raise InvalidInputError(
                f"This chapter is {len(text):,} characters, more than one "
                f"relationship pass can carry ({PROPOSAL_SOURCE_CHARS:,}). "
                "Check it chapter by chapter instead."
            )
        characters = self._characters.list_for_project(chapter.project_id)
        if len(characters) < 2:
            raise InvalidInputError(
                "Add at least two characters to this project before proposing "
                "relationship changes."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before proposing relationship changes."
            )

        records = [
            record
            for record in self._relationships.list_for_project(chapter.project_id)
            if record.status != "rejected"
        ]
        roster = "\n".join(
            f"{character.name}"
            + (
                f" (also called {', '.join(character.aliases)})"
                if character.aliases
                else ""
            )
            for character in characters
        )
        recorded = "\n".join(
            f"{record.character_a_name} and {record.character_b_name} · "
            f"{record.relation_type} · {record.status}"
            + (f" · {record.description}" if record.description else "")
            for record in records
        )
        system_prompt, user_prompt = build_relationship_update_prompt(
            project_name=project.name,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            roster=roster,
            recorded_relationships=recorded,
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
        return parse_relationship_proposals(
            result.text,
            characters=characters,
            relationships=records,
        )

    def apply(
        self, chapter_id: int, updates: list[RelationshipUpdateInput]
    ) -> list[RelationshipEvolution]:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            raise InvalidInputError("That chapter no longer exists.")
        if not updates:
            raise InvalidInputError("Choose at least one proposed change to apply.")
        characters = {
            character.id
            for character in self._characters.list_for_project(chapter.project_id)
        }
        existing = {
            (record.character_a_id, record.character_b_id): record
            for record in self._relationships.list_for_project(chapter.project_id)
            if record.status != "rejected"
        }
        applied: list[RelationshipEvolution] = []
        seen: set[tuple[int, int]] = set()
        for update in updates:
            first, second = sorted((update.character_a_id, update.character_b_id))
            if first == second:
                raise InvalidInputError(
                    "Choose two different characters for a relationship."
                )
            if first not in characters or second not in characters:
                raise InvalidInputError("Choose two characters from this project.")
            if (first, second) in seen:
                continue
            seen.add((first, second))
            record = existing.get((first, second))
            if record is not None:
                relationship = self._relationship_service.update(
                    record.id,
                    relation_type=update.relation_type,
                    description=update.description,
                )
            else:
                relationship = self._relationship_service.create(
                    chapter.project_id,
                    character_a_id=first,
                    character_b_id=second,
                    relation_type=update.relation_type,
                    description=update.description,
                )
                existing[(first, second)] = relationship
            snapshot = self._snapshots.upsert(
                project_id=chapter.project_id,
                relationship_id=relationship.id,
                chapter_id=chapter.id,
                relation_type=relationship.relation_type,
                description=relationship.description,
            )
            applied.append(
                RelationshipEvolution(relationship=relationship, snapshot=snapshot)
            )
        return applied


def parse_relationship_proposals(
    text: str,
    *,
    characters: list,
    relationships: list[RelationshipRecord],
) -> list[RelationshipProposal]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError(
            "The model did not return a relationship JSON object."
        )
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(
            "The model returned invalid relationship JSON."
        ) from exc
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an unexpected relationship structure."
        )

    by_name: dict[str, int] = {}
    names: dict[int, str] = {}
    for character in characters:
        names[character.id] = character.name
        by_name[character.name.casefold()] = character.id
        for alias in character.aliases:
            by_name.setdefault(alias.casefold(), character.id)
    existing = {
        (record.character_a_id, record.character_b_id): record
        for record in relationships
    }
    proposals: list[RelationshipProposal] = []
    seen: set[tuple[int, int]] = set()
    items = data.get("relationships")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        first = by_name.get(_clean(item.get("character_a")))
        second = by_name.get(_clean(item.get("character_b")))
        if first is None or second is None or first == second:
            continue
        pair = (min(first, second), max(first, second))
        if pair in seen:
            continue
        description = _clip(item.get("description"), RELATIONSHIP_DESCRIPTION_LIMIT)
        if not description:
            continue
        relation_type = _clean(item.get("relation_type"))
        record = existing.get(pair)
        seen.add(pair)
        proposals.append(
            RelationshipProposal(
                character_a_id=pair[0],
                character_b_id=pair[1],
                character_a_name=names[pair[0]],
                character_b_name=names[pair[1]],
                relation_type=(
                    relation_type
                    if relation_type in RELATIONSHIP_TYPE_LABELS
                    else "other"
                ),
                description=description,
                existing_relationship_id=record.id if record is not None else None,
                existing_status=record.status if record is not None else "",
            )
        )
        if len(proposals) >= PROPOSAL_MAX_UPDATES:
            break
    return proposals


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).casefold()


def _clip(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
