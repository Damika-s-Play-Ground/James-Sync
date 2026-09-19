#!/usr/bin/env bash
# Watchdog for the realtime ingest daemon — ensures it's running.
# Runs every 5 minutes via Hermes cron "James BSC Realtime Ingest Watchdog".
set -euo pipefail
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
mkdir -p logs/cron
PID_FILE="$WORKSPACE/state/bsc-realtime-ingest.pid"
LOG_FILE="$WORKSPACE/logs/cron/BSC_Realtime_Ingest.hermes.log"
DAEMON_WRAPPER="/opt/data/scripts/james-bsc-realtime-ingest.sh"

mkdir -p "$(dirname "$PID_FILE")"

alert_dev() {
    wacli send text --to "REDACTED_JID" --message "$1" >/dev/null 2>&1 || true
}

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi
    return 1
}

# Check if the process is alive
if pid=$(is_running); then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Realtime ingest daemon running (pid=$pid)"
    exit 0
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Realtime ingest daemon dead — restarting"
alert_dev "⚠️ bsc-realtime-ingest daemon not running — restarting"

# Restart via the wrapper (which also acquires flock)
bash "$DAEMON_WRAPPER" &
sleep 2
new_pid=$(is_running)
if [[ -n "$new_pid" ]]; then
    echo "$new_pid" > "$PID_FILE"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Realtime ingest daemon restarted (pid=$new_pid)"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Failed to restart realtime ingest daemon"
    alert_dev "❌ Failed to restart bsc-realtime-ingest daemon"
fi
