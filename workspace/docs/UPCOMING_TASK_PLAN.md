# Upcoming Task Plan

## BSC Agent-Draft Pipeline — Updated 2026-06-14 (consolidation pass)

---

### Phase 0 — COMPLETE (2026-06-13)
Phase 0 (docs/rules) done.

### Phase 0.5 — COMPLETE (2026-06-14)
- Deleted 12 disabled OCPlatform cron jobs (legacy + dry-run migration jobs).
- Archived: `scripts/system-health-check.py`, `scripts/git-auto-sync-safe.sh` → `archive/`.
- Deleted: `bsc-test.txt`, `test-tools.py`, `tmp_img1.jpg`, `tmp_img2.jpg`.
- Deleted: `state/bsc-monitor.db`, `state/health-check-state.json`, `state/locks/BSC_Weekly_Digest.lock`.
- Deleted: `tmp/parenting-song/`, `tmp/current/`.
- Updated BSC System Integrity Check prompt to reflect clean state.

### Phase 1 — COMPLETE (2026-06-14)
Data layer: `scripts/bsc-data-sync.py`, `scripts/bsc-data-client.py`, `scripts/bsc-data-dump.py`, `state/bsc-data.db` with WAL + 6 tables + FTS5.

### Phase 1.5 — COMPLETE (2026-06-14)
Backfill: 591 messages (Feb–Jun 2026) across all 4 BSC groups; 73 attachments processed; FTS populated. Retention policy (90 days for messages, 30 days for raw attachments) is active — current message count ≈ 465 after retention sweep.

### Phase 2 — COMPLETE (2026-06-14)
All 9 LLM preview jobs read from `bsc-data.db` via `bsc-data-dump.py`. Tokens 215k/day → 65k/day. Pre-LLM overhead ~36 s → <5 ms.

### Phase 2.5 — Consolidation pass (2026-06-14)
- Deleted OCPlatform jobs: `BSC Four-Hour Agent Notice Preview 1400` and `Retry 1400` (Opt 3 / P5 §Step 9 — the missed cleanup).
- Added OCPlatform job: `BSC Data Sync` (every 45 min UTC, runs `bsc-data-sync.py` via agentTurn). Closes the scheduling gap caused by OS cron daemon not running in this container.
- Removed preflight reference from `docs/EXTRACTION_RULES.md` — no live job invokes `bsc-attachment-preflight.py`. Script archived at `archive/bsc-attachment-preflight.py`, manifests at `archive/bsc-attachment-preflight-manifests/`.
- Reconciled the two workspaces: `.ocplatform/workspace` is canonical. Archived divergent agent scripts (`bsc-agent-draft/safe-send/send-slot.py`) and legacy BSC scripts from `.openclaw/workspace/scripts/` to `.ocplatform/workspace/archive/openclaw-workspace-legacy-scripts/`.
- Marked legacy `bsc-os-crontab` (in `.openclaw/workspace/`) as DEACTIVATED documentation. Cron daemon is not running in this container; all scheduling is via OCPlatform jobs.

### Active OCPlatform cron jobs (10, all enabled, post-consolidation)
1. Gateway Outbound Healthcheck
2. BSC System Integrity Check
3. BSC Data Sync
4. BSC 6am Agent Reminder Dry-Run
5. BSC 6am Agent Reminder Retry
6. BSC 3pm Agent Reminder Dry-Run
7. BSC 3pm Agent Reminder Retry
8. BSC Four-Hour Agent Notice Preview
9. BSC Four-Hour Agent Notice Retry
10. BSC Weekly Digest
(Plus the platform job `Tailscale Keepalive`.)

### Canonical workspace
`/opt/data/james-bsc-live-clean/data/.ocplatform/workspace` is the single source of truth for BSC pipeline code, data layer, docs, and OCPlatform-scheduled jobs. James the OpenClaw agent's runtime home stays at `/opt/data/james-bsc-live-clean/data/.openclaw/workspace` (identity files, gateway healthcheck script). See `WORKSPACE_CANONICAL.md` for path policy.

### Active scripts (under `/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/`)
- `scripts/bsc-data-sync.py`, `scripts/bsc-data-client.py`, `scripts/bsc-data-dump.py`
- `scripts/bsc-agent-draft.py`, `scripts/bsc-agent-safe-send.py`, `scripts/bsc-agent-send-slot.py`
- `scripts/gateway-outbound-healthcheck.py`, `scripts/run-gateway-outbound-healthcheck.sh`
- `bin/run-bsc-job.sh`, `bin/bsc-cron-heartbeat.sh`, `bin/bsc-preflight-and-run.sh`

### Phase 3 — Next steps
- Send chain flatten: merge `bsc-agent-send-slot.py` + `bsc-agent-draft.py send` + `bsc-agent-safe-send.py` into one `bsc-send.py`. Target ≥ 2026-06-21 (one week after Phase 2 stable).
- Monitor `BSC Data Sync` failure rate for one week — newsletter sync currently emits FK warnings on first attempt then self-recovers; investigate root cause in `bsc-data-sync.py` newsletter handler.
- Public send activation: today all preview jobs are DEV-ONLY. To go public, OCPlatform-side `bsc-agent-send-slot.py` jobs must be added with sensible schedules, replacing the dead `bsc-os-crontab`.
- Retention: `state/bsc-agent-drafts/` trim to 30-day rolling window.
