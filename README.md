# James-Sync

Secret-safe snapshot of the British School in Colombo (BSC) James WhatsApp pipeline that runs on Hermes.

This is **ops/code only**. Live env, WhatsApp session, JIDs, tokens, parent data, and logs are not in this repo.

## Layout

- `workspace/` — canonical BSC pipeline (`scripts/`, `tests/`, `docs/`, `bin/`)
- `host-scripts/` — Hermes cron wrappers under `/opt/data/scripts/james-*.sh`
- `hermes/` — env example, `run-bsc-command.sh`, cron wrappers, sanitized job list
- `docs/` — handoff notes with JIDs/IPs redacted

## Not included

- `hermes/env.sh` (use `hermes/env.example`)
- `docs/CREDENTIALS.md`
- WhatsApp stores, databases, media, logs, drafts
- Parent-facing message history

## Redaction

WhatsApp group JIDs and private network addresses are replaced with `REDACTED_*` placeholders. Fill `hermes/env.sh` on the live host.

## Restore notes

1. Copy `hermes/env.example` → `hermes/env.sh` and set `BSC_PUBLIC_JID` / `BSC_DEV_JID`.
2. Place workspace files at `$BSC_WORKSPACE`.
3. Do not send to the parent-facing group without explicit approval.
