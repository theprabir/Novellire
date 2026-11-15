"""Provider-neutral inference types.

The protocol is intentionally narrow: model discovery, availability, and a
single non-streaming generation call. No writing, memory, or storage logic
belongs here, so another local provider can be added without touching them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelInfo:
    """A model advertised by a provider."""

    name: str
    size_bytes: int | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    family: str | None = None


@dataclass(frozen=True)
class GenerationRequest:
    """A single text generation request."""

    prompt: str
    model: str
    system_prompt: str = ""
    temperature: float = 0.8
    top_p: float = 0.9
    num_predict: int = 700
    context_window: int = 4096
    seed: int | None = None
    stop: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GenerationResult:
    """The outcome of a successful generation."""

    text: str
    model: str
    duration_ms: int
    truncated: bool = False
    prompt_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface every local inference provider implements."""

    def is_available(self) -> bool:
        """Return True when the provider answers a lightweight request."""
        ...

    def list_models(self) -> list[ModelInfo]:
        """Return installed models, sorted by name."""
        ...

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate text or raise an ``LLMError`` subclass."""
        ...
