"""Author-facing workflow status for chapters and scenes."""

from __future__ import annotations

from ..errors import InvalidInputError

WORK_STATUSES: tuple[str, ...] = ("planned", "drafting", "drafted", "approved")

WORK_STATUS_LABELS: dict[str, str] = {
    "planned": "Planned",
    "drafting": "Drafting",
    "drafted": "Drafted",
    "approved": "Approved",
}


def validate_work_status(status: str) -> str:
    cleaned = (status or "").strip().lower()
    if cleaned not in WORK_STATUSES:
        raise InvalidInputError(
            f"Status must be one of: {', '.join(WORK_STATUSES)}."
        )
    return cleaned
