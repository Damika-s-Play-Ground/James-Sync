#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
bash bin/bsc-send-slot-dispatcher.sh >> logs/cron/Send_Slot_Dispatcher.hermes.log 2>&1
