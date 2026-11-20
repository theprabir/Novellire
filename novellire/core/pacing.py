"""Pacing and repetition review, measured without a model.

Pacing is reported, not judged: paragraph length, sentence length, and how much
of a chapter is dialogue. Those measurements come from the Style profile, so
both surfaces report the same numbers from one implementation. Repetition is
counted here: a four-word phrase that appears at least three times is listed
with the chapters and sentences it appears in. Adjacent repeated windows with
the same count are merged into one longer phrase, so one crutch sentence is one
finding rather than three overlapping ones. Deliberate refrains are the author's
call; nothing is rewritten, flagged in the chapter, or sent anywhere.
"""

from __future__ import annotations

import re

from ..storage.story_repositories import ChapterRecord, ChapterRepository
from .style import StyleProfileService
from .text import average, clip, split_sentences

PACING_PHRASE_WORDS = 4
PACING_MIN_REPETITIONS = 3
PACING_MAX_FINDINGS = 12
PACING_MAX_OCCURRENCES = 5
PACING_EXCERPT_CHARS = 160
PACING_MAX_WORDS = 200_000

_WORD = re.compile(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)?", re.UNICODE)
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by did do for from had has have he her hers
    him his i if in into is it its me my no not of on or our she so than that
    the their them then there these they this those to up was we were what when
    where which who will with you your
    """.split()
)


class PacingReviewService:
    """Report pacing and repeated phrases in the stored manuscript. No model."""

    def __init__(
        self, style: StyleProfileService, chapters: ChapterRepository
    ) -> None:
        self._style = style
        self._chapters = chapters

    def review(self, project_id: int) -> dict[str, object]:
        profile = self._style.profile(project_id)
        rows = profile["chapters"]  # type: ignore[assignment]
        counts = profile["counts"]  # type: ignore[assignment]
        chapters = [
            chapter
            for chapter in self._chapters.list_for_project(project_id)
            if (chapter.content or "").strip()
        ]
        phrase_counts, truncated = _count_phrases(chapters)
        repeated = _merge_repeated(phrase_counts)[:PACING_MAX_FINDINGS]
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
                "words": counts["words"],
                "phrases": len(repetitions),
                "truncated": truncated,
            },
            "pacing": {
                "words": counts["words"],
                "sentences": counts["sentences"],
                "paragraphs": counts["paragraphs"],
                "average_paragraph_words": average(
                    counts["words"], counts["paragraphs"]
                ),
                "longest_paragraph_words": max(
                    (
                        row["longest_paragraph_words"]
                        for row in rows  # type: ignore[union-attr]
                    ),
                    default=0,
                ),
                "average_sentence_words": profile["average_sentence_words"],
                "dialogue_paragraphs": counts["dialogue_paragraphs"],
                "dialogue_share": profile["dialogue_share"],
            },
            "chapters": rows,
            "repetitions": repetitions,
        }


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
                        "excerpt": clip(sentence, PACING_EXCERPT_CHARS),
                    }
                )
    return found
