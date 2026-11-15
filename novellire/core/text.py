"""Small text helpers shared by writing and storage services."""

from __future__ import annotations


def count_words(text: str) -> int:
    """Whitespace-delimited word count; cheap and dependency-free."""
    return len(text.split())
