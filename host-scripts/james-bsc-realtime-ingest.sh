#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron state/locks
exec 9>"$BSC_WORKSPACE/state/locks/Realtime_Ingest.lock"
flock -n 9 || exit 0   # previous pass still running — skip silently
python3 scripts/bsc-realtime-ingest.py >> logs/cron/BSC_Realtime_Ingest.hermes.log 2>&1
