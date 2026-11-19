"""Server-owned review of a draft against its plan and canon.

One inference produces structured findings. The server validates each proposed
edit: the quoted prose must appear exactly once in the reviewed text, so a
finding can only change words that are actually there, and nothing the model
writes is executed. Applying a finding changes the visible draft; the chapter
still changes only through the author's insert, which takes the approval-locked
edit path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..errors import InvalidInputError, LLMResponseError, ProjectNotFoundError
from ..llm.base import GenerationRequest, LLMProvider
from ..prompts.templates import build_review_prompt
from ..storage.repositories import ProjectRepository
from .chapters import ChapterService
from .context import GenerationContextBuilder, prompt_blocks
from .settings_service import GenerationSettings

REVIEW_SOURCE_CHARS = 12_000
REVIEW_MAX_OUTPUT_TOKENS = 1_200
REVIEW_MAX_FINDINGS = 8
REVIEW_QUOTE_CHARS = 1_200
REVIEW_REPLACEMENT_CHARS = 1_200
REVIEW_FIELD_CHARS = 400
REVIEW_OVERALL_CHARS = 600
REVIEW_KINDS = ("continuity", "plan", "pacing", "prose")


@dataclass(frozen=True)
class ReviewFinding:
    id: int
    kind: str
    issue: str
    quote: str
    replacement: str
    reason: str


@dataclass(frozen=True)
class ReviewResult:
    source: str  # "draft" (unsaved text) or "chapter" (saved prose)
    overall: str
    findings: tuple[ReviewFinding, ...]
    model: str
    reviewed_chars: int


class ChapterReviewService:
    """Review prose once and return only findings the server could verify."""

    def __init__(
        self,
        provider: LLMProvider,
        projects: ProjectRepository,
        chapters: ChapterService,
        context_builder: GenerationContextBuilder,
    ) -> None:
        self._provider = provider
        self._projects = projects
        self._chapters = chapters
        self._context_builder = context_builder

    def review(
        self,
        chapter_id: int,
        *,
        settings: GenerationSettings,
        draft: str | None = None,
    ) -> ReviewResult:
        chapter = self._chapters.require_chapter(chapter_id)
        project = self._projects.get(chapter.project_id)
        if project is None:
            raise ProjectNotFoundError(
                "That project no longer exists. Choose another project."
            )
        reviewed = (chapter.content if draft is None else draft).strip()
        if not reviewed:
            raise InvalidInputError("Add chapter text before reviewing it.")
        if len(reviewed) > REVIEW_SOURCE_CHARS:
            raise InvalidInputError(
                f"This draft is {len(reviewed):,} characters, more than one "
                f"review can carry ({REVIEW_SOURCE_CHARS:,}). Split it or "
                "review a shorter passage, so no part of the prose is dropped."
            )
        model = (settings.model or "").strip()
        if not model:
            raise InvalidInputError("Choose a model before reviewing prose.")

        plan = (chapter.objectives or "").strip()
        context = self._context_builder.build(
            project.id,
            instructions=plan or chapter.title,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            context_notes=chapter.summary or plan,
            context_window=settings.context_window,
            output_tokens=min(settings.num_predict, REVIEW_MAX_OUTPUT_TOKENS),
        )
        system_prompt, user_prompt = build_review_prompt(
            project_name=project.name,
            genre=project.genre,
            narrative_style=project.narrative_style,
            content=reviewed,
            chapter_title=chapter.title,
            chapter_position=chapter.position,
            chapter_plan=context.chapter_plan or plan,
            chapter_summary=chapter.summary,
            **prompt_blocks(context),
        )
        result = self._provider.generate(
            GenerationRequest(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=0.2,
                top_p=settings.top_p,
                num_predict=min(
                    max(settings.num_predict, 600), REVIEW_MAX_OUTPUT_TOKENS
                ),
                context_window=settings.context_window,
            )
        )
        overall, findings = parse_review_payload(result.text, reviewed)
        return ReviewResult(
            source="chapter" if draft is None else "draft",
            overall=overall,
            findings=tuple(findings),
            model=result.model or model,
            reviewed_chars=len(reviewed),
        )


def parse_review_payload(
    text: str, reviewed: str
) -> tuple[str, list[ReviewFinding]]:
    """Parse the review JSON and keep only findings that quote the draft.

    A quote must appear exactly once in the prose. That is what makes an
    applied finding safe: the server never guesses which occurrence to change.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMResponseError("The model did not return a review JSON object.")
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError) as exc:
        raise LLMResponseError("The model returned invalid review JSON.") from exc
    if not isinstance(data, dict):
        raise LLMResponseError("The model returned an unexpected review structure.")

    overall = _phrase(data.get("overall"), REVIEW_OVERALL_CHARS)
    findings: list[ReviewFinding] = []
    items = data.get("findings")
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        quote = _verbatim(item.get("quote"), REVIEW_QUOTE_CHARS)
        if not quote or reviewed.count(quote) != 1:
            continue
        replacement = _verbatim(item.get("replacement"), REVIEW_REPLACEMENT_CHARS)
        if replacement == quote:
            continue
        kind = str(item.get("kind") or "").strip().casefold()
        findings.append(
            ReviewFinding(
                id=len(findings) + 1,
                kind=kind if kind in REVIEW_KINDS else "prose",
                issue=_phrase(item.get("issue"), REVIEW_FIELD_CHARS),
                quote=quote,
                replacement=replacement,
                reason=_phrase(item.get("reason"), REVIEW_FIELD_CHARS),
            )
        )
        if len(findings) >= REVIEW_MAX_FINDINGS:
            break
    return overall, findings


def _verbatim(value: object, limit: int) -> str:
    """Keep prose exactly as written, so it can still be found in the draft."""
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit:
        return ""
    return cleaned


def _phrase(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()
