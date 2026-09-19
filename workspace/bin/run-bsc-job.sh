#!/usr/bin/env bash
set -u
JOB_NAME="$1"
shift
DEV_GROUP="${BSC_DEV_JID:-REDACTED_JID}"
WORKDIR="/opt/data/james-bsc-live-clean/data/.ocplatform/workspace"
LOG_DIR="$WORKDIR/logs/cron"
LOCK_DIR="$WORKDIR/state/locks"
mkdir -p "$LOG_DIR" "$LOCK_DIR"
SAFE_NAME="$(echo "$JOB_NAME" | tr ' /:' '___' | tr -cd 'A-Za-z0-9_.-')"
LOG_FILE="$LOG_DIR/${SAFE_NAME}.log"
LOCK_FILE="$LOCK_DIR/${SAFE_NAME}.lock"
START="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

(
  flock -n 9 || { echo "[$START] SKIPPED: already running" >> "$LOG_FILE"; exit 0; }
  echo "===== $JOB_NAME start $START =====" >> "$LOG_FILE"
  cd "$WORKDIR"
  set +e
  "$@" >> "$LOG_FILE" 2>&1
  code=$?
  set -e
  END="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  if [ "$code" -eq 0 ]; then
    echo "===== $JOB_NAME ok $END =====" >> "$LOG_FILE"
    exit 0
  fi
  echo "===== $JOB_NAME FAILED exit=$code $END =====" >> "$LOG_FILE"
  TAIL="$(tail -40 "$LOG_FILE" | tail -c 3000)"
  MSG="Cron job \"$JOB_NAME\" failed with exit code $code

Last log lines:
$TAIL"
  if command -v wacli >/dev/null 2>&1; then
    wacli send text --to "$DEV_GROUP" --message "$MSG" >> "$LOG_FILE" 2>&1 || true
  fi
  exit "$code"
) 9>"$LOCK_FILE"
