"""Persisted UI settings: selected model, generation parameters, active project.

These values live in the database rather than in the configuration file because
they change from the interface. Corrupt or outdated stored values fall back to
the configured defaults instead of breaking startup.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import GenerationDefaults
from ..logging_setup import get_logger
from ..storage.repositories import AppSettingsRepository

logger = get_logger("core.settings")

GENERATION_SETTINGS_KEY = "generation.settings"
ACTIVE_PROJECT_KEY = "active_project_id"


class GenerationSettings(BaseModel):
    """Validated generation parameters for one request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = ""
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class AppSettingsService:
    """Reads and writes per-installation preferences."""

    def __init__(
        self,
        repository: AppSettingsRepository,
        defaults: GenerationDefaults | None = None,
    ) -> None:
        self._repository = repository
        self._defaults = defaults or GenerationDefaults()

    def default_generation_settings(self) -> GenerationSettings:
        return GenerationSettings(
            model=self._defaults.model,
            temperature=self._defaults.temperature,
            top_p=self._defaults.top_p,
            num_predict=self._defaults.num_predict,
            context_window=self._defaults.context_window,
        )

    def generation_settings(self) -> GenerationSettings:
        """Return saved settings, or configuration defaults when unset/invalid."""
        raw = self._repository.get(GENERATION_SETTINGS_KEY)
        if not raw:
            return self.default_generation_settings()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Stored generation settings were not valid JSON; using defaults")
            return self.default_generation_settings()
        if not isinstance(data, dict):
            logger.warning("Stored generation settings had an unexpected shape; using defaults")
            return self.default_generation_settings()
        try:
            return GenerationSettings.model_validate(data)
        except ValidationError:
            logger.warning("Stored generation settings failed validation; using defaults")
            return self.default_generation_settings()

    def save_generation_settings(self, settings: GenerationSettings) -> None:
        self._repository.set(
            GENERATION_SETTINGS_KEY, json.dumps(settings.model_dump(), sort_keys=True)
        )

    def active_project_id(self) -> int | None:
        raw = self._repository.get(ACTIVE_PROJECT_KEY)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning("Stored active project id was not a number; ignoring it")
            return None

    def set_active_project_id(self, project_id: int | None) -> None:
        if project_id is None:
            self._repository.delete(ACTIVE_PROJECT_KEY)
        else:
            self._repository.set(ACTIVE_PROJECT_KEY, str(int(project_id)))
