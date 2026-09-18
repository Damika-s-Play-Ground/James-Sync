#!/usr/bin/env bash
# james-bsc-scheduled-weekly-summary.sh — Sunday 3pm Colombo time (09:30 UTC)
# Builds scheduled artifacts for the upcoming week; PUBLIC sends go only through bsc-agent-safe-send.py.
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"

export BSC_SCHEDULED_MODE=public
export BSC_ALLOW_PUBLIC_AUTOSEND=1

mkdir -p logs/cron state/locks state/bsc-agent-drafts
LOG="logs/cron/BSC_Scheduled_Weekly_Summary.hermes.log"
printf '[%s] preflight job=weekly-sunday-summary\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
python3 -m py_compile scripts/bsc_scheduled_jobs.py scripts/bsc-agent-safe-send.py >> "$LOG" 2>&1

exec 9>"$BSC_WORKSPACE/state/locks/Scheduled_Weekly_Summary.lock"
flock -n 9 || { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] another run in progress, skipping" >> "$LOG"; exit 0; }

if python3 scripts/bsc_scheduled_jobs.py weekly-sunday-summary >> "$LOG" 2>&1; then
  printf '[%s] completed job=weekly-sunday-summary status=ok\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
else
  rc=$?
  printf '[%s] completed job=weekly-sunday-summary status=failed rc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >> "$LOG"
  exit "$rc"
fi
