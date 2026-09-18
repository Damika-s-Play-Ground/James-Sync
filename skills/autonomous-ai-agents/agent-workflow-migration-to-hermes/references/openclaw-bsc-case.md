# OpenClaw BSC case note

Sanitized detail from a workflow migration session. Use as a pattern, not as fixed facts.

## Source workflow shape

- Old runtime: OpenClaw agent in a separate container.
- Workflow: school parent-message reliability pipeline.
- Data plane: periodic sync script fills a SQLite/FTS database from multiple WhatsApp groups plus a newsletter source.
- Reasoning plane: agent cron creates preview drafts and structured per-bullet evidence.
- Delivery plane: OS cron chooses a draft and calls a final safe-send script, which uses a messaging CLI.
- Safety gate: final delivery script enforces structured `items[]`, target audience, source validation, risk flags, and target group before sending.
- Problem found before migration: old runtime had two cron layers; the agent CLI job list did not show OS cron public sends, causing hidden overlap/double-send risk.

## Useful migration artifacts to request/export

```text
.ocplatform/workspace/BSC_HARD_RULES.md
.ocplatform/workspace/AGENTS.md
.ocplatform/workspace/docs/
.ocplatform/workspace/scripts/
.ocplatform/workspace/tests/
.ocplatform/workspace/state/<draft-store>/
.ocplatform/workspace/state/<data-db>
.openclaw/workspace/{AGENTS.md,SOUL.md,USER.md,MEMORY.md,memory/,bin/}
.openclaw/cron/jobs.json
root crontab snapshot
```

Adapt paths to the actual runtime. Avoid copying raw messaging stores or provider tokens unless explicitly approved.

## Export script shape

```bash
OUT="/data/workflow-export-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
cd /data
tar --warning=no-file-changed -czf "$OUT" \
  .ocplatform/workspace/AGENTS.md \
  .ocplatform/workspace/docs \
  .ocplatform/workspace/scripts \
  .ocplatform/workspace/tests \
  .ocplatform/workspace/state/<safe-state> \
  .openclaw/workspace/bin \
  .openclaw/cron/jobs.json
crontab -l -u root > /tmp/workflow-root-crontab.txt 2>/dev/null || true
tar -rzf "$OUT" -C /tmp workflow-root-crontab.txt 2>/dev/null || true
sha256sum "$OUT"
ls -lh "$OUT"
```

## Hermes cron mapping pattern

- Data sync: script-only cron if deterministic and quiet on no-op.
- Preview/draft generation: LLM-driven Hermes cron with imported prompt, safe/dev delivery target, and `workdir` set to migrated workspace.
- Public sends: disabled/no-op until the final delivery backend is authenticated and user approves; keep the code guard as final authority.
- Auditors/watchdogs: script-only cron with concise stdout only when action is required.

## Safety lessons

- Hidden OS cron can be more production-critical than visible agent cron.
- Job names can lie about local time; verify UTC schedule against timezone.
- Prompt-only channel reply rules are insufficient for production messaging bots.
- Code-level audience/routing gates should be migrated before schedules are enabled.

## Cutover discipline

Import and test the sync/preview paths before enabling any public send. All production delivery stays disabled or no-op pending explicit user approval — even when every gate looks correct locally.
