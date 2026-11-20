"""Style analysis against the author's Style Guide.

Two read-only passes. The profile measures stored prose without a model:
sentences, average sentence length, the longest sentence, and how many
paragraphs carry dialogue, per chapter and for the whole manuscript. The
deviation check compares one saved chapter with the numbered rules of the
project's Style Guide in one inference. Every deviation must cite a supplied
rule and quote the chapter exactly once, and the server attaches the guide's own
words, so a finding cannot invent a rule the author did not write.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..errors import InvalidInputError, LLMResponseError, ProjectNotFoundError
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_style_deviation_prompt
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRecord, ChapterRepository
from .documents import ProjectDocumentService
from .settings_service import GenerationSettings
from .text import split_sentences

STYLE_SOURCE_CHARS = 12_000
STYLE_MAX_OUTPUT_TOKENS = 900
STYLE_QUOTE_CHARS = 300
STYLE_DETAIL_CHARS = 600
STYLE_MAX_DEVIATIONS = 6
STYLE_MAX_RULES = 12
STYLE_RULE_CHARS = 400
STYLE_LABEL_CHARS = 120
STYLE_LONG_SENTENCE_WORDS = 35
STYLE_ASPECTS = (
    "perspective",
    "tense",
    "sentence",
    "vocabulary",
    "dialogue",
    "description",
    "emotion",
    "pacing",
    "other",
)
STYLE_SEVERITIES = ("critical", "high", "medium", "low")

_FALLBACK_EXPLANATION = "Departs from the cited style rule."
_DIALOGUE = re.compile(r"[\"\u201c\u201d\u201e\u00ab\u00bb]")


@dataclass(frozen=True)
class StyleRule:
    id: str
    label: str
    guidance: str


@dataclass(frozen=True)
class ChapterStyle:
    id: int
    position: int
    title: str
    words: int
    sentences: int
    paragraphs: int
    dialogue_paragraphs: int
    long_sentences: int
    average_sentence_words: float
    longest_sentence_words: int
    longest_sentence: str


@dataclass(frozen=True)
class StyleDeviation:
    id: int
    aspect: str
    severity: str
    quote: str
    rule_id: str
    rule: str
    explanation: str
    suggestion: str


@dataclass(frozen=True)
class StyleCheckResult:
    deviations: tuple[StyleDeviation, ...]
    rule_count: int
    model: str


def guide_rules(content: str) -> list[StyleRule]:
    """Number the author's Style Guide into rules a finding can cite.

    Each paragraph is one rule. A short heading line labels the paragraph that
    follows it, so a guide split into named sections cites the section as well as
    its text. A heading with nothing under it becomes a rule of its own.
    """
    blocks = [
        block
        for block in re.split(r"\n\s*\n", (content or "").replace("\r\n", "\n"))
        if block.strip()
    ]
    rules: list[StyleRule] = []
    heading = ""
    for index, block in enumerate(blocks):
        lines = [
            " ".join(line.split()) for line in block.splitlines() if line.strip()
        ]
        if not lines:
            continue
        if _is_heading(lines[0]) and (len(lines) > 1 or index < len(blocks) - 1):
            heading = lines[0].lstrip("#").strip()
            lines = lines[1:]
            if not lines:
                continue
        text = " ".join(lines)
        rules.append(_rule(len(rules) + 1, f"{heading}: {text}" if heading else text))
        heading = ""
        if len(rules) >= STYLE_MAX_RULES:
            break
    if heading and len(rules) < STYLE_MAX_RULES:
        rules.append(_rule(len(rules) + 1, heading))
    return rules


class StyleProfileService:
    """Measure the stored manuscript and number the guide's rules. No model."""

    def __init__(
        self,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        documents: ProjectDocumentService,
    ) -> None:
        self._projects = projects
        self._chapters = chapters
        self._documents = documents

    def profile(self, project_id: int) -> dict[str, object]:
        if self._projects.get(project_id) is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        chapters = [
            chapter
            for chapter in self._chapters.list_for_project(project_id)
            if (chapter.content or "").strip()
        ]
        rows = [_measure_chapter(chapter) for chapter in chapters]
        words = sum(row.words for row in rows)
        sentences = sum(row.sentences for row in rows)
        paragraphs = sum(row.paragraphs for row in rows)
        dialogue = sum(row.dialogue_paragraphs for row in rows)
        guide = self._documents.get_document(project_id, "style_guide")
        rules = guide_rules(guide.content if guide is not None else "")
        return {
            "counts": {
                "chapters": len(rows),
                "words": words,
                "sentences": sentences,
                "paragraphs": paragraphs,
                "dialogue_paragraphs": dialogue,
                "long_sentences": sum(row.long_sentences for row in rows),
                "rules": len(rules),
            },
            "average_sentence_words": _average(words, sentences),
            "dialogue_share": _percent(dialogue, paragraphs),
            "guide": {
                "present": bool(guide is not None and guide.content.strip()),
                "derived": bool(guide.derived) if guide is not None else False,
                "rules": [asdict(rule) for rule in rules],
            },
            "chapters": [asdict(row) for row in rows],
        }


class StyleDeviationService:
    """Compare one saved chapter with the numbered rules of the Style Guide."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterRepository,
        documents: ProjectDocumentService,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._documents = documents

    def check(
        self, chapter_id: int, *, settings: GenerationSettings
    ) -> StyleCheckResult:
        chapter = self._chapters.get(chapter_id)
        if chapter is None:
            raise InvalidInputError("That chapter no longer exists.")
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        draft = (chapter.content or "").strip()
        if not draft:
            raise InvalidInputError(
                "Write or draft this chapter before checking its style."
            )
        if len(draft) > STYLE_SOURCE_CHARS:
            raise InvalidInputError(
                f"This chapter is {len(draft):,} characters, more than one style "
                f"check can carry ({STYLE_SOURCE_CHARS:,}). Check it chapter by "
                "chapter instead."
            )
        guide = self._documents.get_document(chapter.project_id, "style_guide")
        rules = guide_rules(guide.content if guide is not None else "")
        if not rules:
            raise InvalidInputError(
                "Write the Style Guide in Workspace before checking style "
                "deviations."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError(
                "Choose a model before checking style deviations."
            )

        system_prompt, user_prompt = build_style_deviation_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            rules="\n".join(f"{rule.id}: {rule.guidance}" for rule in rules),
            draft=draft,
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.2,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 500), STYLE_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        return StyleCheckResult(
            deviations=tuple(parse_style_deviations(result.text, draft, rules)),
            rule_count=len(rules),
            model=result.model or model,
        )


def parse_style_deviations(
    text: str, draft: str, rules: list[StyleRule]
) -> list[StyleDeviation]:
    """Keep deviations that cite a supplied rule and quote the chapter once."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError("The model did not return a style JSON object.")
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError("The model returned invalid style JSON.") from exc
    if not isinstance(data, dict):
        raise LLMResponseError("The model returned an unexpected style structure.")

    by_id = {rule.id.casefold(): rule for rule in rules}
    deviations: list[StyleDeviation] = []
    seen: set[tuple[str, str]] = set()
    items = data.get("deviations")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        quote = _raw(item.get("quote"))
        if not quote or len(quote) > STYLE_QUOTE_CHARS:
            continue
        if draft.count(quote) != 1:
            continue
        rule_id = _raw(item.get("rule")).strip("[]").upper()
        rule = by_id.get(rule_id.casefold())
        if rule is None or (rule.id, quote) in seen:
            continue
        seen.add((rule.id, quote))
        aspect = _raw(item.get("aspect")).casefold()
        severity = _raw(item.get("severity")).casefold()
        deviations.append(
            StyleDeviation(
                id=len(deviations) + 1,
                aspect=aspect if aspect in STYLE_ASPECTS else "other",
                severity=(
                    severity if severity in STYLE_SEVERITIES else "medium"
                ),
                quote=quote,
                rule_id=rule.id,
                rule=rule.guidance,
                explanation=(
                    _clip(item.get("explanation"), STYLE_DETAIL_CHARS)
                    or _FALLBACK_EXPLANATION
                ),
                suggestion=_clip(item.get("suggestion"), STYLE_DETAIL_CHARS),
            )
        )
        if len(deviations) >= STYLE_MAX_DEVIATIONS:
            break
    return deviations


def _measure_chapter(chapter: ChapterRecord) -> ChapterStyle:
    text = chapter.content or ""
    sentences = split_sentences(text)
    lengths = [len(sentence.split()) for sentence in sentences]
    longest = max(lengths) if lengths else 0
    longest_sentence = ""
    if lengths:
        longest_sentence = _clip(sentences[lengths.index(longest)], 160)
    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    dialogue = sum(1 for paragraph in paragraphs if _DIALOGUE.search(paragraph))
    return ChapterStyle(
        id=chapter.id,
        position=chapter.position,
        title=chapter.title,
        words=chapter.word_count,
        sentences=len(sentences),
        paragraphs=len(paragraphs),
        dialogue_paragraphs=dialogue,
        long_sentences=sum(
            1 for length in lengths if length > STYLE_LONG_SENTENCE_WORDS
        ),
        average_sentence_words=_average(sum(lengths), len(lengths)),
        longest_sentence_words=longest,
        longest_sentence=longest_sentence,
    )


def _is_heading(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if text.startswith("#"):
        return True
    return (
        len(text) <= 48
        and len(text.split()) <= 6
        and not text.endswith((".", "!", "?", ":", ";"))
    )


def _rule(index: int, text: str) -> StyleRule:
    cleaned = _clip(text, STYLE_RULE_CHARS)
    return StyleRule(
        id=f"S{index}",
        label=cleaned[:STYLE_LABEL_CHARS].strip(),
        guidance=cleaned,
    )


def _average(total: int, count: int) -> float:
    return round(total / count, 1) if count else 0.0


def _percent(part: int, whole: int) -> int:
    return round(part / whole * 100) if whole else 0


def _raw(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clip(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
