"""Narrative context for generation: documents plus relevant canon records.

The four workspace documents are broad, author-written summaries. The story bible
entries and character profiles hold the detailed canon, and there can be many of
them, so this module selects only the records that match the request. Matching is
lexical (names, aliases, titles, and shared words), which keeps local inference
fast and needs no embeddings or extra index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..storage.search_repository import SearchRepository
from ..storage.story_repositories import (
    ChapterRecord,
    ChapterRepository,
    CharacterRecord,
    CharacterRepository,
    StoryBibleEntry,
    StoryBibleRepository,
)
from .characters import FIELD_LABELS, PROFILE_FIELDS
from .documents import ProjectDocumentService
from .story_bible import CATEGORY_LABELS

STORY_BIBLE_MAX_ENTRIES = 6
CHARACTER_MAX_PROFILES = 5
STORY_BIBLE_CHAR_LIMIT = 3_000
CHARACTER_CHAR_LIMIT = 3_000
ENTRY_CONTENT_LIMIT = 700
PROFILE_FIELD_LIMIT = 300
MEMORY_MAX_CHAPTERS = 6
MEMORY_CHAR_LIMIT = 3_000
MEMORY_SUMMARY_LIMIT = 600
MEMORY_EXCERPT_LIMIT = 500
MEMORY_SEARCH_LIMIT = 30
MEMORY_TERMS_LIMIT = 12

# Canon basics worth carrying even when the request names nothing specific.
FOUNDATIONAL_CATEGORIES = (
    "premise",
    "main_storyline",
    "themes",
    "metaphysical_rules",
    "world_building",
)

_STOPWORDS = frozenset(
    """
    about above after again against all also and any are because been before
    being below between both but can could did does doing down during each few
    for from further had has have having here how into its itself just more most
    other over own same she should some such than that the their them then there
    these they this those through too under until very was were what when where
    which while who whom why will with would you your
    """.split()
)

_WORD = re.compile(r"[a-z0-9']+")

# Words that describe the act of writing rather than the story being written.
_MEMORY_STOPWORDS = _STOPWORDS | frozenset(
    """
    chapter chapters continue draft drafted generate generation next prose scene
    scenes story write writes writing words
    """.split()
)


@dataclass(frozen=True)
class MemoryChapter:
    """One earlier chapter retrieved for the prompt, with its provenance."""

    id: int
    position: int
    title: str
    summary: str
    excerpt: str


@dataclass(frozen=True)
class GenerationContext:
    """Everything the prompt carries outside the request itself."""

    master_bible: str = ""
    character_bible: str = ""
    chapter_map: str = ""
    style_guide: str = ""
    bible_entries: str = ""
    character_profiles: str = ""
    memory_chapters: tuple[MemoryChapter, ...] = ()

    @property
    def earlier_chapters(self) -> str:
        """Prompt block for retrieved chapters, within the memory budget."""
        return _join_with_budget(
            [_format_memory(chapter) for chapter in self.memory_chapters],
            MEMORY_CHAR_LIMIT,
        )

    def documents(self) -> dict[str, str]:
        return {
            "master_bible": self.master_bible,
            "character_bible": self.character_bible,
            "chapter_map": self.chapter_map,
            "style_guide": self.style_guide,
        }


class GenerationContextBuilder:
    """Assemble workspace documents and relevance-ranked canon for a request."""

    def __init__(
        self,
        documents: ProjectDocumentService,
        bible_entries: StoryBibleRepository,
        characters: CharacterRepository,
        chapters: ChapterRepository,
        search: SearchRepository,
    ) -> None:
        self._documents = documents
        self._bible_entries = bible_entries
        self._characters = characters
        self._chapters = chapters
        self._search = search

    def build(
        self,
        project_id: int,
        *,
        instructions: str,
        chapter_id: int | None = None,
        chapter_title: str = "",
        scene_title: str = "",
        context_notes: str = "",
    ) -> GenerationContext:
        chapter = self._chapters.get(chapter_id) if chapter_id is not None else None
        query_text = " ".join(
            part
            for part in (
                instructions,
                chapter_title,
                scene_title,
                context_notes,
                chapter.summary if chapter else "",
                chapter.objectives if chapter else "",
            )
            if part and part.strip()
        ).casefold()
        query_tokens = _tokens(query_text)

        documents = self._documents.context_for_prompt(project_id)
        entries = self._ranked_entries(project_id, query_text, query_tokens)
        profiles = self._ranked_characters(
            project_id,
            query_text,
            query_tokens,
            viewpoint_id=chapter.viewpoint_character_id if chapter else None,
        )
        memory = self._retrieve_chapters(
            project_id, _memory_terms(query_text), current=chapter
        )

        return GenerationContext(
            master_bible=documents.get("master_bible", ""),
            character_bible=documents.get("character_bible", ""),
            chapter_map=documents.get("chapter_map", ""),
            style_guide=documents.get("style_guide", ""),
            bible_entries=_join_with_budget(
                [_format_entry(entry) for entry in entries],
                STORY_BIBLE_CHAR_LIMIT,
            ),
            character_profiles=_join_with_budget(
                [_format_character(character) for character in profiles],
                CHARACTER_CHAR_LIMIT,
            ),
            memory_chapters=tuple(memory),
        )

    def _retrieve_chapters(
        self,
        project_id: int,
        terms: list[str],
        *,
        current: ChapterRecord | None,
    ) -> list[MemoryChapter]:
        """Pick earlier chapters that match the request, best rank first."""
        if not terms:
            return []
        selected: list[MemoryChapter] = []
        for hit in self._search.search_terms(
            project_id, terms, limit=MEMORY_SEARCH_LIMIT
        ):
            if hit.source_kind != "chapter":
                continue
            source = self._chapters.get(hit.source_id)
            if source is None or not source.content.strip():
                continue
            if current is not None and (
                source.id == current.id or source.position >= current.position
            ):
                continue
            if any(item.id == source.id for item in selected):
                continue
            excerpt = " ".join((hit.excerpt or "").split())
            summary = source.summary.strip()
            if summary:
                # The index body begins with the summary, so the snippet often
                # repeats it. Drop that copy to keep the prompt budget for prose.
                flat_summary = " ".join(summary.split())
                if excerpt.startswith(flat_summary):
                    excerpt = excerpt[len(flat_summary) :].lstrip(" .…—-\n")
            if not summary and not excerpt:
                continue
            selected.append(
                MemoryChapter(
                    id=source.id,
                    position=source.position,
                    title=source.title,
                    summary=summary,
                    excerpt=excerpt,
                )
            )
            if len(selected) >= MEMORY_MAX_CHAPTERS:
                break
        return selected

    def _ranked_entries(
        self, project_id: int, query_text: str, query_tokens: set[str]
    ) -> list[StoryBibleEntry]:
        scored: list[tuple[int, str, StoryBibleEntry]] = []
        foundational: list[StoryBibleEntry] = []
        for entry in self._bible_entries.list_for_project(project_id):
            score = _entry_score(entry, query_text, query_tokens)
            if entry.category in FOUNDATIONAL_CATEGORIES:
                foundational.append(entry)
            if score:
                scored.append((score, entry.updated_at, entry))

        if not scored:
            return foundational[:2]

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry for _, _, entry in scored[:STORY_BIBLE_MAX_ENTRIES]]

    def _ranked_characters(
        self,
        project_id: int,
        query_text: str,
        query_tokens: set[str],
        *,
        viewpoint_id: int | None,
    ) -> list[CharacterRecord]:
        scored: list[tuple[int, str, CharacterRecord]] = []
        candidates: list[CharacterRecord] = []
        for character in self._characters.list_for_project(project_id):
            candidates.append(character)
            score = _character_score(
                character, query_text, query_tokens, viewpoint_id
            )
            if score:
                scored.append((score, character.updated_at, character))

        if not scored:
            # A small cast is the whole cast; a large one stays out of the prompt.
            return candidates if len(candidates) <= 2 else []

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            character for _, _, character in scored[:CHARACTER_MAX_PROFILES]
        ]


def _entry_score(
    entry: StoryBibleEntry, query_text: str, query_tokens: set[str]
) -> int:
    title_tokens = _tokens(entry.title)
    score = 3 * len(title_tokens & query_tokens)
    score += len(_tokens(entry.content) & query_tokens)
    title = entry.title.strip().casefold()
    if len(title) >= 3 and title in query_text:
        score += 6
    if entry.category in FOUNDATIONAL_CATEGORIES:
        score += 1
    return score


def _character_score(
    character: CharacterRecord,
    query_text: str,
    query_tokens: set[str],
    viewpoint_id: int | None,
) -> int:
    score = 0
    name = character.name.strip().casefold()
    if len(name) >= 3 and name in query_text:
        score += 12
    for alias in character.aliases:
        alias_text = alias.strip().casefold()
        if len(alias_text) >= 3 and alias_text in query_text:
            score += 8
    score += 4 * len(_tokens(character.name) & query_tokens)
    profile_text = " ".join(
        getattr(character, field) for field in PROFILE_FIELDS
    )
    score += len(_tokens(profile_text) & query_tokens)
    if viewpoint_id is not None and character.id == viewpoint_id:
        score += 20
    return score


def _format_entry(entry: StoryBibleEntry) -> str:
    label = CATEGORY_LABELS.get(entry.category, entry.category)
    content = _trim(entry.content, ENTRY_CONTENT_LIMIT)
    if not content:
        return f"[{label}] {entry.title}"
    return f"[{label}] {entry.title}\n{content}"


def _format_character(character: CharacterRecord) -> str:
    alias_note = (
        f" (also: {', '.join(character.aliases)})" if character.aliases else ""
    )
    lines = [f"{character.name}{alias_note}"]
    for field in PROFILE_FIELDS:
        value = _trim(getattr(character, field), PROFILE_FIELD_LIMIT)
        if value:
            lines.append(f"{FIELD_LABELS[field]}: {value}")
    return "\n".join(lines)


def _memory_terms(text: str) -> list[str]:
    """Ordered, deduplicated retrieval terms for the generation request."""
    terms: list[str] = []
    for word in _WORD.findall((text or "").casefold()):
        if len(word) < 3 or word in _MEMORY_STOPWORDS or word in terms:
            continue
        terms.append(word)
        if len(terms) >= MEMORY_TERMS_LIMIT:
            break
    return terms


def _format_memory(chapter: MemoryChapter) -> str:
    lines = [f"Chapter {chapter.position} — {chapter.title}"]
    if chapter.summary:
        lines.append(f"Summary: {_trim(chapter.summary, MEMORY_SUMMARY_LIMIT)}")
    if chapter.excerpt:
        lines.append(f"Passage: {_trim(chapter.excerpt, MEMORY_EXCERPT_LIMIT)}")
    return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return {
        word
        for word in _WORD.findall((text or "").casefold())
        if len(word) >= 3 and word not in _STOPWORDS
    }


def _trim(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def _join_with_budget(blocks: list[str], limit: int) -> str:
    kept: list[str] = []
    total = 0
    for block in blocks:
        extra = len(block) + (2 if kept else 0)
        if kept and total + extra > limit:
            break
        kept.append(block)
        total += extra
    return "\n\n".join(kept)
