#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
exec 9>"$BSC_WORKSPACE/state/locks/Send_Slots.lock" 2>/dev/null || { mkdir -p "$BSC_WORKSPACE/state/locks"; exec 9>"$BSC_WORKSPACE/state/locks/Send_Slots.lock"; }
flock -n 9 || exit 0
python3 scripts/bsc-send-slots-dispatch.py >> logs/cron/BSC_Send_Slots.hermes.log 2>&1
