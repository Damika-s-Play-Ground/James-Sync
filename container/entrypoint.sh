#!/usr/bin/env bash
set -euo pipefail

# Keep the upstream Hermes dispatcher and /opt/data contract intact while
# making the immutable James code available to every command and cron wrapper.
export JAMES_REPO_ROOT="${JAMES_REPO_ROOT:-/opt/james}"
export PYTHONPATH="${JAMES_REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ "${JAMES_INIT_RUNTIME:-1}" == "1" ]]; then
  mkdir -p /opt/data/james-bsc-live-clean/data \
    /opt/data/james-bsc-live-clean/logs/cron
fi

if [[ "${JAMES_VALIDATE_CONFIG:-0}" == "1" ]]; then
  /opt/james/container/runtime-init.sh
fi

# Keep a direct provider smoke-test/maintenance command available without
# bypassing the normal Hermes dispatcher for gateway/setup commands.
if [[ "${1:-}" == "james-llm" ]]; then
  shift
  exec /opt/james/bin/james-llm "$@"
fi

exec /opt/hermes/docker/entrypoint-dispatch.sh "$@"
