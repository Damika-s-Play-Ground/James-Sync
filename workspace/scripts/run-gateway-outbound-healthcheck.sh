#!/bin/bash
# Wrapper for gateway outbound healthcheck
# Called by OCPlatform cron job

set -euo pipefail

WORKSPACE=/opt/data/james-bsc-live-clean/data/.ocplatform/workspace
cd "$WORKSPACE"

# Default: dry-run mode without send, no reload
DRY_RUN="${GATEWAY_HEALTH_DRY_RUN:-1}"
SEND_PROBE="${GATEWAY_HEALTH_SEND_PROBE:-0}"
FORCE_PROBE="${GATEWAY_HEALTH_FORCE_PROBE:-0}"

python3 scripts/gateway-outbound-healthcheck.py "$DRY_RUN" "$SEND_PROBE" "$FORCE_PROBE"
