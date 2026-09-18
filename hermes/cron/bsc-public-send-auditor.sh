#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
python3 scripts/bsc-public-send-auditor.py >> logs/cron/BSC_Public_Send_Auditor.hermes.log 2>&1
