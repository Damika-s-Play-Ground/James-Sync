#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
python3 scripts/bsc-scheduled-healthcheck.py >> logs/cron/BSC_Scheduled_Healthcheck.hermes.log
