"""Application error hierarchy.

Every error in this module is meant to be shown to the author as-is, so messages
must stay actionable and must never include private manuscript content.
"""

from __future__ import annotations


class NovellireError(Exception):
    """Base class for errors the application handles and reports to the user."""


class ConfigurationError(NovellireError):
    """The configuration file is missing, unreadable, or invalid."""


class DatabaseError(NovellireError):
    """A storage operation failed."""


class ProjectNotFoundError(NovellireError):
    """The requested project does not exist."""


class DuplicateProjectError(NovellireError):
    """A project with the same name already exists."""


class InvalidInputError(NovellireError):
    """Author-supplied input failed validation."""


class LLMError(NovellireError):
    """Base class for inference provider failures."""


class LLMUnavailableError(LLMError):
    """The inference provider could not be reached."""


class LLMTimeoutError(LLMError):
    """The inference provider did not answer within the configured limit."""


class ModelNotFoundError(LLMError):
    """The requested model is not installed in the provider."""


class LLMResponseError(LLMError):
    """The provider answered with a malformed, empty, or failed response."""
