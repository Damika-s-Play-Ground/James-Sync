from __future__ import annotations

import unittest

from james.providers.router import ProviderRouter
from james.providers.types import GenerationResult, ProviderError


class FakeProvider:
    def __init__(self, name: str, result: GenerationResult | None = None, error: ProviderError | None = None):
        self.name = name
        self.result = result
        self.error = error
        self.calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str) -> GenerationResult:
        self.calls += 1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


class ProviderRouterTests(unittest.TestCase):
    def test_primary_success_does_not_call_fallback(self) -> None:
        primary = FakeProvider("codex", GenerationResult("primary", "codex", "test", 1))
        fallback = FakeProvider("openrouter", GenerationResult("fallback", "openrouter", "test", 1))
        result = ProviderRouter(primary=primary, fallback=fallback).generate(system_prompt="s", user_prompt="u")
        self.assertEqual(result.text, "primary")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 0)

    def test_primary_failure_uses_fallback_and_records_source(self) -> None:
        primary = FakeProvider("codex", error=ProviderError("offline", provider="codex"))
        fallback = FakeProvider("openrouter", GenerationResult("fallback", "openrouter", "test", 2))
        result = ProviderRouter(primary=primary, fallback=fallback).generate(system_prompt="s", user_prompt="u")
        self.assertEqual(result.text, "fallback")
        self.assertEqual(result.metadata["fallback_from"], "codex")
        self.assertEqual(fallback.calls, 1)

    def test_disabled_fallback_re_raises_primary_error(self) -> None:
        primary = FakeProvider("codex", error=ProviderError("offline", provider="codex"))
        fallback = FakeProvider("openrouter", GenerationResult("fallback", "openrouter", "test", 2))
        with self.assertRaises(ProviderError):
            ProviderRouter(primary=primary, fallback=fallback, fallback_enabled=False).generate(
                system_prompt="s", user_prompt="u"
            )
        self.assertEqual(fallback.calls, 0)


if __name__ == "__main__":
    unittest.main()

