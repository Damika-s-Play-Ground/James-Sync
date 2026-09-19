#!/usr/bin/env bash
set -euo pipefail

# Validate the mutable contract before a gateway is started. This script is
# intentionally side-effect-light: it creates only expected directories and
# refuses to print secret values.
mkdir -p /opt/data/james-bsc-live-clean/data /opt/data/james-bsc-live-clean/logs/cron
if [[ ! -d "${CODEX_HOME:-/opt/codex}" ]]; then
  echo "CODEX_HOME does not exist: ${CODEX_HOME:-/opt/codex}" >&2
  exit 1
fi

exec james-llm --health --strict

