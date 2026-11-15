"""Input validation helpers shared by the application services.

All helpers raise ``InvalidInputError`` with a message meant for the author, so
UI layers can render the message directly.
"""

from __future__ import annotations

from ..errors import InvalidInputError


def clean_required_text(value: str, label: str, *, max_length: int) -> str:
    """Strip and validate a required single-line field."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise InvalidInputError(f"{label} is required.")
    if len(cleaned) > max_length:
        raise InvalidInputError(f"{label} must be {max_length} characters or fewer.")
    return cleaned


def clean_optional_text(value: str, label: str, *, max_length: int) -> str:
    """Strip an optional field and enforce its length limit."""
    cleaned = (value or "").strip()
    if len(cleaned) > max_length:
        raise InvalidInputError(f"{label} must be {max_length} characters or fewer.")
    return cleaned


def validate_direction(value: str) -> str:
    """Validate a one-step move direction."""
    cleaned = (value or "").strip().lower()
    if cleaned not in ("up", "down"):
        raise InvalidInputError("Direction must be 'up' or 'down'.")
    return cleaned


def clean_word_target(
    value: int | None, label: str, *, maximum: int
) -> int | None:
    """Validate an optional whole-number word target."""
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError(f"{label} must be a whole number.") from exc
    if number <= 0:
        raise InvalidInputError(f"{label} must be greater than zero.")
    if number > maximum:
        raise InvalidInputError(f"{label} must be {maximum:,} or fewer.")
    return number
