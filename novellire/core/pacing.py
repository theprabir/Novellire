"""Pacing and repetition review, measured without a model.

Pacing is reported, not judged: paragraph length, sentence length, and how much
of a chapter is dialogue, per chapter and for the manuscript. Repetition is
counted: a four-word phrase that appears at least three times is listed with the
chapters and sentences it appears in. Adjacent repeated windows with the same
count are merged into one longer phrase, so one crutch sentence is one finding
rather than three overlapping ones. Deliberate refrains are the author's call;
nothing is rewritten, flagged in the chapter, or sent anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import ProjectNotFoundError
from ..storage.repositories import ProjectRepository
from ..storage.story_repositories import ChapterRecord, ChapterRepository
from .text import split_sentences

PACING_PHRASE_WORDS = 4
PACING_MIN_REPETITIONS = 3
PACING_MAX_FINDINGS = 12
PACING_MAX_OCCURRENCES = 5
PACING_EXCERPT_CHARS = 160
PACING_MAX_WORDS = 200_000

_WORD = re.compile(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)?", re.UNICODE)
_DIALOGUE = re.compile(r"[\"\u201c\u201d\u201e\u00ab\u00bb]")
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by did do for from had has have he her hers
    him his i if in into is it its me my no not of on or our she so than that
    the their them then there these they this those to up was we were what when
    where which who will with you your
    """.split()
)


@dataclass(frozen=True)
class ChapterPacing:
    id: int
    position: int
    title: str
    words: int
    sentences: int
    paragraphs: int
    average_paragraph_words: float
    longest_paragraph_words: int
    average_sentence_words: float
    dialogue_paragraphs: int
    dialogue_share: int


class PacingReviewService:
    """Measure pacing and repeated phrases in the stored manuscript. No model."""

    def __init__(
        self, projects: ProjectRepository, chapters: ChapterRepository
    ) -> None:
        self._projects = projects
        self._chapters = chapters

    def review(self, project_id: int) -> dict[str, object]:
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
        counts, truncated = _count_phrases(chapters)
        repeated = _merge_repeated(counts)[:PACING_MAX_FINDINGS]
        occurrences = _collect_occurrences(
            chapters, {source for _, _, source in repeated}
        )
        repetitions = [
            {
                "id": index,
                "phrase": phrase,
                "count": count,
                "occurrences": occurrences.get(source, []),
            }
            for index, (phrase, count, source) in enumerate(repeated, start=1)
        ]

        return {
            "counts": {
                "chapters": len(rows),
                "words": words,
                "phrases": len(repetitions),
                "truncated": truncated,
            },
            "pacing": {
                "words": words,
                "sentences": sentences,
                "paragraphs": paragraphs,
                "average_paragraph_words": _average(words, paragraphs),
                "longest_paragraph_words": max(
                    (row.longest_paragraph_words for row in rows), default=0
                ),
                "average_sentence_words": _average(words, sentences),
                "dialogue_paragraphs": dialogue,
                "dialogue_share": _percent(dialogue, paragraphs),
            },
            "chapters": [
                {
                    "id": row.id,
                    "position": row.position,
                    "title": row.title,
                    "words": row.words,
                    "sentences": row.sentences,
                    "paragraphs": row.paragraphs,
                    "average_paragraph_words": row.average_paragraph_words,
                    "longest_paragraph_words": row.longest_paragraph_words,
                    "average_sentence_words": row.average_sentence_words,
                    "dialogue_paragraphs": row.dialogue_paragraphs,
                    "dialogue_share": row.dialogue_share,
                }
                for row in rows
            ],
            "repetitions": repetitions,
        }


def _measure_chapter(chapter: ChapterRecord) -> ChapterPacing:
    text = chapter.content or ""
    paragraphs = [
        paragraph for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()
    ]
    lengths = [len(paragraph.split()) for paragraph in paragraphs]
    sentences = split_sentences(text)
    dialogue = sum(1 for paragraph in paragraphs if _DIALOGUE.search(paragraph))
    return ChapterPacing(
        id=chapter.id,
        position=chapter.position,
        title=chapter.title,
        words=chapter.word_count,
        sentences=len(sentences),
        paragraphs=len(paragraphs),
        average_paragraph_words=_average(chapter.word_count, len(paragraphs)),
        longest_paragraph_words=max(lengths) if lengths else 0,
        average_sentence_words=_average(chapter.word_count, len(sentences)),
        dialogue_paragraphs=dialogue,
        dialogue_share=_percent(dialogue, len(paragraphs)),
    )


def _count_phrases(
    chapters: list[ChapterRecord],
) -> tuple[dict[str, int], bool]:
    """Count four-word phrases, ignoring windows made only of stopwords."""
    counts: dict[str, int] = {}
    analyzed = 0
    truncated = False
    for chapter in chapters:
        for sentence in split_sentences(chapter.content):
            tokens = _WORD.findall(sentence.casefold())
            analyzed += len(tokens)
            if analyzed > PACING_MAX_WORDS:
                truncated = True
                break
            for start in range(len(tokens) - PACING_PHRASE_WORDS + 1):
                window = tokens[start : start + PACING_PHRASE_WORDS]
                if all(token in _STOPWORDS for token in window):
                    continue
                phrase = " ".join(window)
                counts[phrase] = counts.get(phrase, 0) + 1
        if truncated:
            break
    return counts, truncated


def _merge_repeated(counts: dict[str, int]) -> list[tuple[str, int, str]]:
    """Join overlapping windows repeated the same number of times.

    ``("the gate was", "gate was sealed", …)`` with one count becomes a single
    ``"the gate was sealed"`` finding. The third value is a four-word source
    phrase used to collect the occurrences, since the merged phrase is longer
    than the detected window.
    """
    merged: dict[str, tuple[int, str]] = {
        phrase: (count, phrase)
        for phrase, count in counts.items()
        if count >= PACING_MIN_REPETITIONS
    }
    overlap = PACING_PHRASE_WORDS - 1
    changed = True
    while changed:
        changed = False
        for phrase in list(merged):
            if phrase not in merged:
                continue
            words = phrase.split()
            for other in list(merged):
                if other == phrase or other not in merged:
                    continue
                if merged[other][0] != merged[phrase][0]:
                    continue
                if words[-overlap:] != other.split()[:overlap]:
                    continue
                combined = " ".join(words + other.split()[-1:])
                if (
                    combined in merged
                    and merged[combined][0] != merged[phrase][0]
                ):
                    continue
                merged[combined] = (merged[phrase][0], merged[phrase][1])
                del merged[phrase]
                del merged[other]
                changed = True
                break
            if changed:
                break
    return sorted(
        (
            (phrase, count, source)
            for phrase, (count, source) in merged.items()
        ),
        key=lambda row: (-row[1], row[0]),
    )


def _collect_occurrences(
    chapters: list[ChapterRecord], sources: set[str]
) -> dict[str, list[dict[str, object]]]:
    """Find up to five example sentences for each reported phrase."""
    found: dict[str, list[dict[str, object]]] = {
        source: [] for source in sources
    }
    if not found:
        return found
    for chapter in chapters:
        for sentence in split_sentences(chapter.content):
            tokens = _WORD.findall(sentence.casefold())
            for start in range(len(tokens) - PACING_PHRASE_WORDS + 1):
                phrase = " ".join(tokens[start : start + PACING_PHRASE_WORDS])
                bucket = found.get(phrase)
                if bucket is None or len(bucket) >= PACING_MAX_OCCURRENCES:
                    continue
                bucket.append(
                    {
                        "chapter_position": chapter.position,
                        "chapter_title": chapter.title,
                        "excerpt": _clip(sentence, PACING_EXCERPT_CHARS),
                    }
                )
    return found


def _average(total: int, count: int) -> float:
    return round(total / count, 1) if count else 0.0


def _percent(part: int, whole: int) -> int:
    return round(part / whole * 100) if whole else 0


def _clip(text: str, limit: int) -> str:
    return " ".join((text or "").split())[:limit].strip()
