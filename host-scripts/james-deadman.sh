#!/usr/bin/env bash
# james-deadman.sh — watches-the-watcher for the Hermes cron scheduler.
#
# Failure domain covered: Hermes scheduler stops/crashes while the rest of
# the container lives. All James automations (sync, ingest, slots, audits)
# are Hermes crons — when they die, NOTHING else notices. This loop is an
# independent process: if the os-cron-heartbeat sentinel goes stale, it
# alerts DEV directly via wacli (max once per 30 min).
#
# Limitation: this loop itself is not yet boot-persistent (needs an s6
# static service = image rebuild, or a container_boot.py hook). Restart it
# after container restarts until that lands.
set -u
SENTINEL="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/supervisor/os-cron-heartbeat"
STATE="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/deadman-state.json"
DEV_GROUP="REDACTED_JID"
MAX_AGE_SEC=600          # heartbeat writes every minute; 10 min stale = dead
ALERT_EVERY_SEC=1800     # re-alert cadence while still dead

mkdir -p "$(dirname "$STATE")"
last_alert=0

alert_dev() {
  wacli send text --to "$DEV_GROUP" --message "$1" >/dev/null 2>&1 || true
}

while true; do
  now=$(date +%s)
  age=-1
  if [ -f "$SENTINEL" ]; then
    mt=$(stat -c %Y "$SENTINEL" 2>/dev/null || echo 0)
    age=$((now - mt))
  fi
  if [ "$age" -ge 0 ] && [ "$age" -gt $MAX_AGE_SEC ]; then
    if [ $((now - last_alert)) -ge $ALERT_EVERY_SEC ]; then
      mins=$((age / 60))
      alert_dev "🚨 James DEAD-MAN SWITCH: Hermes cron heartbeat stale ${mins}m (threshold ${MAX_AGE_SEC}s). ALL James automations are stopped (sync, realtime ingest, send slots, audits, sweeps). Scheduler process needs attention."
      echo "[$(date -u +%FT%TZ)] ALERT sent (stale ${mins}m)" >> /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/logs/cron/Deadman.log
      last_alert=$now
    fi
  elif [ "$age" -ge 0 ]; then
    last_alert=0
  fi
  sleep 60
done
