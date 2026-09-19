#!/usr/bin/env bash
# wacli-sync-daemon.sh — Persistent wacli sync --follow daemon.
#
# Replaces the 90-minute sync --once pattern with a live connection.
# Messages are delivered in real-time, eliminating the inter-window gap
# that caused missing messages (e.g. BSC Sport & ECAs June 13-16 gap).
#
# Managed by: wacli-sync-watchdog.sh (cron every 5 min)
# PID file:   /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/wacli-sync-daemon.pid
# Log:        /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/logs/cron/wacli-sync-daemon.log
#
# Usage: wacli-sync-daemon.sh [start|stop|status|restart]

set -euo pipefail

WORKSPACE="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace"
PID_FILE="$WORKSPACE/state/wacli-sync-daemon.pid"
LOG_FILE="$WORKSPACE/logs/cron/wacli-sync-daemon.log"
DEV_GROUP="${BSC_DEV_JID:-REDACTED_JID}"

mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"

alert_dev() {
  local msg="$1"
  wacli send text --to "$DEV_GROUP" --message "$msg" >/dev/null 2>&1 || true
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

do_start() {
  if is_running; then
    echo "wacli sync daemon already running (pid=$(cat "$PID_FILE"))"
    return 0
  fi

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting wacli sync --follow daemon" >> "$LOG_FILE"

  # Start in background, redirect output to log.
  # wacli sync (without --once) runs with --follow=true by default —
  # stays connected permanently and delivers messages in real-time.
  nohup wacli sync \
    >> "$LOG_FILE" 2>&1 &

  local pid=$!
  echo "$pid" > "$PID_FILE"
  echo "Started wacli sync daemon (pid=$pid)"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Daemon started (pid=$pid)" >> "$LOG_FILE"
}

do_stop() {
  if ! is_running; then
    echo "wacli sync daemon not running"
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid=$(cat "$PID_FILE")
  kill "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Stopped wacli sync daemon (pid=$pid)"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Daemon stopped (pid=$pid)" >> "$LOG_FILE"
}

do_status() {
  if is_running; then
    echo "RUNNING (pid=$(cat "$PID_FILE"))"
  else
    echo "STOPPED"
  fi
}

CMD="${1:-start}"
case "$CMD" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; sleep 2; do_start ;;
  status)  do_status ;;
  *)       echo "Usage: $0 [start|stop|status|restart]"; exit 1 ;;
esac
