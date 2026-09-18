#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
bash scripts/wacli-sync-watchdog.sh >> logs/cron/wacli_Sync_Watchdog.hermes.log 2>&1
