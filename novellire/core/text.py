"""Small text helpers shared by writing and storage services."""

from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    """Stable hash for deciding whether saved content needs re-analysis."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def count_words(text: str) -> int:
    """Whitespace-delimited word count; cheap and dependency-free."""
    return len(text.split())
