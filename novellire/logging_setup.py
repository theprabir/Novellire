"""Application logging setup.

Logs carry identifiers, model names, sizes, and timings only. Prompts and
generated prose are never logged, so diagnostics stay free of manuscript text.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """Attach a single stderr handler to the ``novellire`` logger tree."""
    global _CONFIGURED

    logger = logging.getLogger("novellire")
    logger.setLevel(level.upper())
    logger.propagate = False

    if not _CONFIGURED:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced application logger."""
    return logging.getLogger(f"novellire.{name}" if not name.startswith("novellire") else name)
