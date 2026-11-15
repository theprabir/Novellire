"""Application configuration: defaults, TOML loading, and environment overrides.

Configuration is intentionally small for Phase 1: paths, Ollama connection
settings, and generation defaults. Per-project and per-model selections are
stored in the database instead (see ``novellire.core.settings_service``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ConfigurationError

PACKAGE_DIR = Path(__file__).resolve().parent
APP_ROOT = PACKAGE_DIR.parent
DEFAULT_CONFIG_FILE = APP_ROOT / "config.toml"


class OllamaSettings(BaseModel):
    """Connection settings for a local Ollama server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str = "http://localhost:11434"
    request_timeout_seconds: float = Field(default=180.0, gt=0)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    keep_alive: str = "5m"


class GenerationDefaults(BaseModel):
    """Default generation parameters, all overridable in the UI.

    The defaults are deliberately conservative: a small context window and a
    bounded output length keep memory use reasonable on an 8 GB machine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = ""
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    num_predict: int = Field(default=700, ge=32, le=8192)
    context_window: int = Field(default=4096, ge=512, le=32768)


class Settings(BaseModel):
    """Validated application settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path = APP_ROOT / "data"
    log_level: str = "INFO"
    ollama: OllamaSettings = OllamaSettings()
    generation: GenerationDefaults = GenerationDefaults()

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        path = value.expanduser()
        return path if path.is_absolute() else (APP_ROOT / path).resolve()

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @property
    def database_path(self) -> Path:
        return self.data_dir / "novellire.db"


def _merge_ollama_override(raw: dict[str, object], base_url: str) -> dict[str, object]:
    existing = raw.get("ollama")
    section = dict(existing) if isinstance(existing, dict) else {}
    section["base_url"] = base_url
    return section


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from TOML, applying environment overrides.

    A missing configuration file is not an error: defaults are used.
    """
    configured = os.environ.get("NOVELLIRE_CONFIG")
    path = config_path or (Path(configured) if configured else DEFAULT_CONFIG_FILE)

    raw: dict[str, object] = {}
    if path.is_file():
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(
                f"Could not read the configuration file at {path}: {exc}"
            ) from exc

    data_dir_override = os.environ.get("NOVELLIRE_DATA_DIR")
    if data_dir_override:
        raw["data_dir"] = data_dir_override

    ollama_url_override = os.environ.get("NOVELLIRE_OLLAMA_URL")
    if ollama_url_override:
        raw["ollama"] = _merge_ollama_override(raw, ollama_url_override)

    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid configuration in {path}: {exc}"
        ) from exc
