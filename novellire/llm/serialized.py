"""One-inference-at-a-time provider wrapper.

Background analysis and interactive generation share the same provider. The lock
keeps CPU and RAM use predictable on the target hardware and prevents two model
requests from competing for the same Ollama instance.
"""

from __future__ import annotations

import threading

from .base import GenerationRequest, GenerationResult, LLMProvider, ModelInfo


class SerializedProvider:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return self._provider.is_available()

    def list_models(self) -> list[ModelInfo]:
        return self._provider.list_models()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        with self._lock:
            return self._provider.generate(request)
