#!/usr/bin/env bash
# wacli-sync-watchdog.sh — Watchdog for the persistent wacli sync daemon.
#
# Runs every 5 minutes via cron. Restarts the daemon if it's not running.
# Also checks if the daemon is "stale" (connected but not receiving messages).
# Sends a dev alert on first restart after a gap.
#
# Cron: */5 * * * * /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/bin/run-bsc-job.sh "wacli Sync Watchdog" bash /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/scripts/wacli-sync-watchdog.sh

set -euo pipefail

WORKSPACE="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace"
PID_FILE="$WORKSPACE/state/wacli-sync-daemon.pid"
LOG_FILE="$WORKSPACE/logs/cron/wacli-sync-daemon.log"
WATCHDOG_STATE="$WORKSPACE/state/wacli-sync-watchdog.json"
DEV_GROUP="${BSC_DEV_JID:-REDACTED_JID}"
DAEMON_SCRIPT="$WORKSPACE/scripts/wacli-sync-daemon.sh"

mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$WATCHDOG_STATE")"

alert_dev() {
  wacli send text --to "$DEV_GROUP" --message "$1" >/dev/null 2>&1 || true
}

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if is_running; then
  # Daemon is alive — check for staleness (optional: log last message time)
  echo "[${NOW_ISO}] Watchdog: daemon running (pid=$(cat "$PID_FILE"))" 

  # Update watchdog state
  python3 -c "
import json, sys
from datetime import datetime, timezone
state_path = '${WATCHDOG_STATE}'
try:
    with open(state_path) as f:
        state = json.load(f)
except:
    state = {}
state['last_alive_check'] = '${NOW_ISO}'
state['status'] = 'running'
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null || true

else
  # Daemon is down — restart it
  echo "[${NOW_ISO}] Watchdog: daemon not running, restarting..."
  echo "[${NOW_ISO}] Watchdog: daemon not running, restarting..." >> "$LOG_FILE"

  bash "$DAEMON_SCRIPT" start

  # Read previous state to know if this is a first restart or repeated failure
  PREV_STATUS=$(python3 -c "
import json
try:
    with open('${WATCHDOG_STATE}') as f:
        s = json.load(f)
    print(s.get('status','unknown'))
except:
    print('unknown')
" 2>/dev/null)

  if [[ "$PREV_STATUS" != "restarted" ]]; then
    alert_dev "⚠️ wacli sync daemon was down — restarted at ${NOW_ISO}. Monitor for message delivery."
  fi

  python3 -c "
import json
from datetime import datetime
state_path = '${WATCHDOG_STATE}'
try:
    with open(state_path) as f:
        state = json.load(f)
except:
    state = {}
state['last_restart'] = '${NOW_ISO}'
state['status'] = 'restarted'
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null || true
fi

# NOTE: the old per-5-min "BSC source staleness alert" block was removed on
# 2026-08-23 — it had no dedupe and spammed DEV whenever a low-traffic group
# was quiet (e.g. Sport & ECAs during school holidays). Pipeline-health
# alerting now lives solely in bsc-data-sync.py::_check_staleness, which
# compares wacli-store newest vs DB newest and only fires on real ingestion
# lag (once/day/source).
