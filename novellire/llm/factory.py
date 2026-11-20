"""Provider selection at startup.

The default is the local Ollama provider. Cloud inference is used only when
``[cloud].enabled`` is true, and a missing key stops startup with an actionable
error instead of silently falling back to another provider.
"""

from __future__ import annotations

from ..config import Settings
from ..errors import MissingCloudKeyError
from .base import LLMProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Return the provider named by the configuration."""
    if not settings.cloud.enabled:
        return OllamaProvider(
            base_url=settings.ollama.base_url,
            request_timeout=settings.ollama.request_timeout_seconds,
            connect_timeout=settings.ollama.connect_timeout_seconds,
            keep_alive=settings.ollama.keep_alive,
        )

    api_key = settings.cloud.api_key()
    if not api_key:
        raise MissingCloudKeyError(
            "Cloud inference is enabled in config.toml, but the environment "
            f"variable {settings.cloud.api_key_env} is empty. Set it, or set "
            "cloud.enabled = false to return to local Ollama inference."
        )
    return OpenAICompatibleProvider(
        base_url=settings.cloud.base_url,
        api_key=api_key,
        request_timeout=settings.cloud.request_timeout_seconds,
        connect_timeout=settings.cloud.connect_timeout_seconds,
    )
