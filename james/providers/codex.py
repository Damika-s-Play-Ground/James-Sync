"""Codex CLI provider.

Codex authentication is intentionally inherited from the process environment
or its mounted ``CODEX_HOME``.  No ChatGPT/Codex credential is read from Git or
written to logs.  ``codex exec`` prints the final answer to stdout while its
progress goes to stderr, which makes it safe for the reply worker to capture.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Mapping

from .types import GenerationResult, ProviderError


class CodexCliProvider:
    name = "codex"

    def __init__(
        self,
        *,
        binary: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        home: str | None = None,
    ) -> None:
        self.binary = binary or os.getenv("CODEX_BIN", "codex")
        self.model = model or os.getenv("CODEX_MODEL", "gpt-5.6-sol")
        self.timeout_s = timeout_s or float(os.getenv("CODEX_TIMEOUT_SECONDS", "180"))
        self.home = home or os.getenv("CODEX_HOME")

    def _environment(self) -> Mapping[str, str]:
        env = os.environ.copy()
        if self.home:
            env["CODEX_HOME"] = self.home
        return env

    @staticmethod
    def _prompt(system_prompt: str, user_prompt: str) -> str:
        return (
            "You are the James reply model. Follow the system instructions exactly.\n\n"
            "<system>\n"
            f"{system_prompt.strip()}\n"
            "</system>\n\n"
            "<user>\n"
            f"{user_prompt.strip()}\n"
            "</user>\n\n"
            "Return only the final reply text. Do not mention this wrapper, providers, "
            "or internal instructions."
        )

    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        command = [
            self.binary,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            self.model,
            self._prompt(system_prompt, user_prompt),
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                env=self._environment(),
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(
                f"Codex executable not found: {self.binary}",
                provider=self.name,
                retryable=False,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"Codex timed out after {self.timeout_s:g}s",
                provider=self.name,
                retryable=True,
            ) from exc
        except OSError as exc:
            raise ProviderError(
                f"Codex process could not start: {exc}",
                provider=self.name,
                retryable=True,
            ) from exc

        elapsed = int((time.monotonic() - started) * 1000)
        answer = (completed.stdout or "").strip()
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            # Keep logs useful without copying a potentially sensitive prompt.
            detail = detail[-1200:]
            raise ProviderError(
                f"Codex exited {completed.returncode}: {detail}",
                provider=self.name,
                retryable=True,
            )
        if not answer:
            raise ProviderError(
                "Codex returned an empty response",
                provider=self.name,
                retryable=True,
            )
        return GenerationResult(
            text=answer,
            provider=self.name,
            model=self.model,
            latency_ms=elapsed,
        )

