#!/usr/bin/env bash
# james-bsc-scheduled-6am-summary.sh — daily 6am Colombo time (00:30 UTC)
# Builds scheduled artifacts for today's activities; PUBLIC sends go only through bsc-agent-safe-send.py.
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"

export BSC_SCHEDULED_MODE=public
export BSC_ALLOW_PUBLIC_AUTOSEND=1

mkdir -p logs/cron state/locks state/bsc-agent-drafts
LOG="logs/cron/BSC_Scheduled_6am_Summary.hermes.log"
printf '[%s] preflight job=daily-6am-summary
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
python3 -m py_compile scripts/bsc_scheduled_jobs.py scripts/bsc-agent-safe-send.py >> "$LOG" 2>&1

exec 9>"$BSC_WORKSPACE/state/locks/Scheduled_6am_Summary.lock"
flock -n 9 || { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] another run in progress, skipping" >> "$LOG"; exit 0; }

if python3 scripts/bsc_scheduled_jobs.py daily-6am-summary >> "$LOG" 2>&1; then
  printf '[%s] completed job=daily-6am-summary status=ok
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
else
  rc=$?
  printf '[%s] completed job=daily-6am-summary status=failed rc=%s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >> "$LOG"
  exit "$rc"
fi
