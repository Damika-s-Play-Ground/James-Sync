#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
bash bin/bsc-cron-heartbeat.sh
