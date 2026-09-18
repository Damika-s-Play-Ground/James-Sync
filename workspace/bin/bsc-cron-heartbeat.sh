#!/usr/bin/env bash
# BSC OS cron heartbeat — proves the OS cron daemon is alive.
# Runs every minute via crontab. Writes a sentinel timestamp.
# If this file goes stale, the fallback supervisor can detect cron failure.
set -euo pipefail

SENTINEL="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/supervisor/os-cron-heartbeat"
mkdir -p "$(dirname "$SENTINEL")"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$SENTINEL"
