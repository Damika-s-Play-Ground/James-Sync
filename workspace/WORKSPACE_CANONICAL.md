# Workspace Canonical Path

`/opt/data/james-bsc-live-clean/data/.ocplatform/workspace` is the single canonical BSC workspace.

- All BSC pipeline code, the data layer (`bsc-data-sync.py`, `bsc-data-client.py`, `bsc-data-dump.py`, `state/bsc-data.db`), docs, and OCPlatform-scheduled jobs reference paths under this directory only.
- Never write `.openclaw/workspace` when referring to BSC code or docs — that path holds OpenClaw runtime state and James's identity files only.
- The gateway-outbound-healthcheck script is the one exception: it lives under `.openclaw/workspace/scripts/` because OpenClaw runtime expects it there. Do not move it.

Established 2026-06-14 during the workspace consolidation pass.
