#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
bash scripts/run-gateway-outbound-healthcheck.sh >> logs/cron/Gateway_Outbound_Healthcheck.hermes.log 2>&1
