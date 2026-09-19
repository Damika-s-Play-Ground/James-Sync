"""Primary/fallback routing with explicit, auditable behavior."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from .codex import CodexCliProvider
from .openrouter import OpenRouterProvider
from .types import GenerationResult, ProviderError

LOGGER = logging.getLogger(__name__)


class ProviderRouter:
    """Try Codex first, then OpenRouter when fallback is enabled.

    The fallback is only selected after a complete Codex failure.  We do not
    send a second response when Codex succeeded, and provider errors are kept
    in metadata so dashboards can show which path handled a message.
    """

    def __init__(
        self,
        *,
        primary: CodexCliProvider | None = None,
        fallback: OpenRouterProvider | None = None,
        fallback_enabled: bool | None = None,
        on_error: Callable[[ProviderError], None] | None = None,
    ) -> None:
        self.primary = primary or CodexCliProvider()
        self.fallback = fallback or OpenRouterProvider()
        if fallback_enabled is None:
            fallback_enabled = os.getenv("JAMES_LLM_FALLBACK_ENABLED", "1").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self.fallback_enabled = fallback_enabled
        self.on_error = on_error

    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        try:
            return self.primary.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        except ProviderError as primary_error:
            if self.on_error:
                self.on_error(primary_error)
            LOGGER.warning("primary provider failed (%s): %s", primary_error.provider, primary_error)
            if not self.fallback_enabled:
                raise
            try:
                result = self.fallback.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            except ProviderError as fallback_error:
                if self.on_error:
                    self.on_error(fallback_error)
                raise ProviderError(
                    f"primary {primary_error.provider} failed; fallback {fallback_error.provider} failed: {fallback_error}",
                    provider="router",
                    retryable=primary_error.retryable or fallback_error.retryable,
                ) from fallback_error
            metadata = dict(result.metadata)
            metadata["fallback_from"] = primary_error.provider
            return GenerationResult(
                text=result.text,
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                metadata=metadata,
            )

