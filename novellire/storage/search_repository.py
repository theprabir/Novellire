"""Full-text search over the project's chapters and workspace documents.

The index is maintained by SQLite triggers (migration 4), so this repository only
reads. Queries are tokenised and quoted before reaching FTS5 so author input
cannot inject operators or malformed syntax.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .database import Database

MAX_QUERY_TOKENS = 12
MAX_LIMIT = 50
_TOKEN = re.compile(r"[^\W_]{2,}", re.UNICODE)


@dataclass(frozen=True)
class SearchHit:
    source_kind: str
    source_id: int
    title: str
    excerpt: str
    rank: float


class SearchRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def search(
        self, project_id: int, query: str, *, limit: int = 20
    ) -> list[SearchHit]:
        expression = match_expression(query)
        if expression is None:
            return []
        bounded = max(1, min(int(limit), MAX_LIMIT))
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT source_kind, source_id, title,
                       snippet(search_index, 1, '', '', ' … ', 24) AS excerpt,
                       bm25(search_index) AS rank
                FROM search_index
                WHERE search_index MATCH ? AND project_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (expression, project_id, bounded),
            ).fetchall()
        return [
            SearchHit(
                source_kind=str(row["source_kind"]),
                source_id=int(row["source_id"]),
                title=str(row["title"]),
                excerpt=str(row["excerpt"]),
                rank=float(row["rank"]),
            )
            for row in rows
        ]


def match_expression(query: str) -> str | None:
    """Turn author input into a quoted AND query, or None when unusable."""
    tokens = _TOKEN.findall((query or "").lower())[:MAX_QUERY_TOKENS]
    if not tokens:
        return None
    return " AND ".join(f'"{token}"' for token in tokens)
