# James model providers

James uses one provider boundary for reply generation:

1. `CodexCliProvider` invokes `codex exec` with the mounted Codex login and
   returns only the final stdout response.
2. `OpenRouterProvider` calls the OpenAI-compatible
   `https://openrouter.ai/api/v1/chat/completions` endpoint.
3. `ProviderRouter` calls Codex first. OpenRouter is called only if Codex
   fails and `JAMES_LLM_FALLBACK_ENABLED` is enabled.

## Credentials

Do not put either credential in Git, the image, or command-line arguments.

- Codex: mount a protected `CODEX_HOME` containing the authenticated Codex CLI
  state, or provide the short-lived `CODEX_ACCESS_TOKEN` at runtime.
- OpenRouter: inject `OPENROUTER_API_KEY` from the EC2 secret store and set an
  explicit `OPENROUTER_MODEL` available to the account.

The CLI entrypoint is:

```bash
PYTHONPATH=/opt/james python3 -m james.providers.cli --json --system "$SOUL" "$PROMPT"
```

For a text-only result, omit `--json`. Errors contain provider names and
latency is included in the normalized result; prompts and credentials are not
logged by the adapter.

## Codex plan/authentication note

`codex exec` can reuse the CLI's saved authentication in `CODEX_HOME`. A
ChatGPT/Codex login is not the same thing as an OpenAI API key: preserve the
mounted login or use the supported non-interactive access token flow. If the
Codex account/session is unavailable, the router falls back to OpenRouter.

