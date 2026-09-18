#!/usr/bin/env bash
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
mkdir -p "$BSC_WORKSPACE/logs/cron" "$BSC_WORKSPACE/state/locks" "$BSC_WORKSPACE/state/supervisor"
cd "$BSC_WORKSPACE"
exec "$@"
