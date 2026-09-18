#!/usr/bin/env bash
# james-bsc-new-data-auto-send.sh — Auto-send candidate processor + gate engine.
#
# Runs the new-data auto-send engine. Default mode is dry_run (never sends).
# Sends to PUBLIC only if BSC_AUTO_SEND_MODE=public AND BSC_ALLOW_PUBLIC_AUTOSEND=1
# AND category allowlist includes event_type AND rate limits allow AND circuit breakers clear.
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"

# Phase 1 deployment is hard-forced to dry-run. Do not inherit ambient
# public/dev send flags from a shell or gateway process.
export BSC_AUTO_SEND_MODE=dev
export BSC_ALLOW_PUBLIC_AUTOSEND=0

mkdir -p logs/cron state/locks state/bsc-agent-drafts/auto-send-holds

# Prevent overlapping runs
exec 9>"$BSC_WORKSPACE/state/locks/New_Data_Auto_Send.lock"
flock -n 9 || { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] another run in progress, skipping"; exit 0; }

python3 scripts/bsc-new-data-auto-send.py >> logs/cron/BSC_New_Data_Auto_Send.hermes.log 2>&1
