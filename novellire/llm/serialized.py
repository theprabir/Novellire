"""One-inference-at-a-time provider wrapper.

Background analysis and interactive generation share the same provider. The lock
keeps CPU and RAM use predictable on the target hardware and prevents two model
requests from competing for the same Ollama instance.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

from .base import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    ModelInfo,
)


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

    def generate_stream(
        self, request: GenerationRequest
    ) -> Iterator[GenerationChunk]:
        """Hold the lock for the whole stream, not just its first chunk.

        A provider without its own streaming support is wrapped as one complete
        chunk, so callers can use the streaming path unconditionally.
        """
        stream = getattr(self._provider, "generate_stream", None)
        with self._lock:
            if stream is None:
                result = self._provider.generate(request)
                yield GenerationChunk(
                    text=result.text,
                    model=result.model,
                    done=True,
                    truncated=result.truncated,
                )
            else:
                yield from stream(request)
