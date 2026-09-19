"""OpenRouter OpenAI-compatible chat-completions provider."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .types import GenerationResult, ProviderError


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("OPENROUTER_MODEL", "")
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).rstrip("/")
        self.timeout_s = timeout_s or float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60"))
        self.site_url = os.getenv("OPENROUTER_SITE_URL", "")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "James")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "james-sync/1",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-Title"] = self.app_name
        return headers

    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        if not self.api_key:
            raise ProviderError(
                "OPENROUTER_API_KEY is not configured",
                provider=self.name,
                retryable=False,
            )
        if not self.model:
            raise ProviderError(
                "OPENROUTER_MODEL is not configured",
                provider=self.name,
                retryable=False,
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except OSError:
                detail = str(exc)
            raise ProviderError(
                f"OpenRouter HTTP {exc.code}: {detail[-1200:]}",
                provider=self.name,
                retryable=exc.code >= 500 or exc.code == 429,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(
                f"OpenRouter request failed: {exc}",
                provider=self.name,
                retryable=True,
            ) from exc

        elapsed = int((time.monotonic() - started) * 1000)
        try:
            document: dict[str, Any] = json.loads(raw)
            content = document["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            answer = str(content).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "OpenRouter returned an invalid chat-completions response",
                provider=self.name,
                retryable=True,
            ) from exc
        if not answer:
            raise ProviderError(
                "OpenRouter returned an empty response",
                provider=self.name,
                retryable=True,
            )
        usage = document.get("usage", {})
        return GenerationResult(
            text=answer,
            provider=self.name,
            model=self.model,
            latency_ms=elapsed,
            metadata={"usage": usage} if isinstance(usage, dict) else {},
        )

