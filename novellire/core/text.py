"""Small text helpers shared by writing and storage services."""

from __future__ import annotations

import hashlib
import re

_SENTENCE_BREAK = re.compile(r"(?<=[.!?\u2026])\s+")


def content_hash(text: str) -> str:
    """Stable hash for deciding whether saved content needs re-analysis."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def count_words(text: str) -> int:
    """Whitespace-delimited word count; cheap and dependency-free."""
    return len(text.split())


def split_sentences(text: str) -> list[str]:
    """Split prose into sentence-sized pieces, collapsing whitespace first.

    Deliberately simple: a run of terminal punctuation followed by whitespace
    ends a sentence. Abbreviations are not special-cased, because both callers
    use this to count and compare, never to rewrite text.
    """
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return []
    return [part for part in _SENTENCE_BREAK.split(collapsed) if part.strip()]
