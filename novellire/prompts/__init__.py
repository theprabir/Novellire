"""Prompt construction. Templates render with Jinja2 and stay small on purpose."""

from .templates import build_writing_prompt

__all__ = ["build_writing_prompt"]
