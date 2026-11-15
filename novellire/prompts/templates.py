"""Prompt templates for Phase 1 scene writing.

Prompts are built from explicit, author-supplied fields only. Phase 1 performs
no retrieval, so nothing is loaded from the database beyond project metadata.
Keeping prompts short also keeps prompt-processing time low on CPU inference.
"""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

_ENVIRONMENT = Environment(
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=False,
)

_SYSTEM_TEMPLATE = _ENVIRONMENT.from_string(
    """You are Novellire, a collaborator for a novelist writing long-form fiction.

Follow the author's instructions precisely.
Write prose only: no preamble, no commentary, no headings, no bullet points.
Stay consistent with the project details and any context notes supplied.
Do not invent facts that contradict established material; when a detail is
unknown, keep it vague rather than contradicting it.
Match the requested length approximately.

Project: {{ project_name }}
{% if genre %}Genre: {{ genre }}
{% endif %}
{% if narrative_style %}Narrative style: {{ narrative_style }}
{% endif %}"""
)

_USER_TEMPLATE = _ENVIRONMENT.from_string(
    """{% if chapter_title %}Chapter: {{ chapter_title }}
{% endif %}
{% if scene_title %}Scene: {{ scene_title }}
{% endif %}
Instructions:
{{ instructions }}

{% if context_notes %}Context notes from the author:
{{ context_notes }}

{% endif %}Target length: about {{ target_words }} words.

Write the scene now."""
)


def build_writing_prompt(
    *,
    project_name: str,
    genre: str = "",
    narrative_style: str = "",
    instructions: str,
    target_words: int,
    chapter_title: str = "",
    scene_title: str = "",
    context_notes: str = "",
) -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for a scene generation request."""
    values = {
        "project_name": project_name,
        "genre": genre,
        "narrative_style": narrative_style,
        "instructions": instructions,
        "target_words": target_words,
        "chapter_title": chapter_title,
        "scene_title": scene_title,
        "context_notes": context_notes,
    }
    system_prompt = _SYSTEM_TEMPLATE.render(**values).strip()
    user_prompt = _USER_TEMPLATE.render(**values).strip()
    return system_prompt, user_prompt
