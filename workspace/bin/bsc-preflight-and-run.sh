#!/usr/bin/env bash
# bsc-preflight-and-run.sh — preflight guard + runner for BSC legacy scripts.
# Called by OCPlatform BSC Weekly Digest cron job.
#
# Usage:
#   bsc-preflight-and-run.sh <mode> <command...>
#   bsc-preflight-and-run.sh weekly python3 /path/to/bsc-calendar-monitor.py --mode=weekly
#
# Preflight checks:
#   - Script path argument must exist on disk
#   - If BSC_DRY_RUN=1, set env and allow through
#   - Alerts dev group on preflight failure (never public group)
#
set -euo pipefail

MODE="${1:-}"
shift || true

WS="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace"
DEV="REDACTED_JID@g.us"
LOG_DIR="$WS/logs/cron"
mkdir -p "$LOG_DIR"

alert_dev() {
  local msg="$1"
  if command -v wacli >/dev/null 2>&1; then
    wacli send text --to "$DEV" --message "$msg" >/dev/null 2>&1 || true
  fi
  echo "$msg" >&2
}

# Find the python script argument (first arg ending in .py)
SCRIPT_PATH=""
for arg in "$@"; do
  if [[ "$arg" == *.py ]]; then
    SCRIPT_PATH="$arg"
    break
  fi
done

# Preflight: script must exist
if [[ -n "$SCRIPT_PATH" && ! -f "$SCRIPT_PATH" ]]; then
  alert_dev "⚠️ BSC PREFLIGHT FAIL (mode=$MODE): Script not found: $SCRIPT_PATH
No BSC job run. Check workspace scripts."
  exit 127
fi

# Run
exec "$@"
