"""Shared provider result/error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """A provider could not produce a response."""

    def __init__(self, message: str, *, provider: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


@dataclass(frozen=True)
class GenerationResult:
    """Normalized response returned by every provider."""

    text: str
    provider: str
    model: str
    latency_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)

