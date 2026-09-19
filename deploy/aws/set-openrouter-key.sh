#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/james}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/secrets/provider.env}"
if [[ "$(id -u)" == "0" ]]; then
  INSTALLER="install"
else
  INSTALLER="sudo install"
fi

read -r -s -p "OpenRouter API key (input hidden): " OPENROUTER_API_KEY
printf '\n'
[[ -n "$OPENROUTER_API_KEY" ]] || { echo "Key is empty" >&2; exit 1; }
export OPENROUTER_API_KEY

tmp_file="$(mktemp)"
cleanup() { rm -f "$tmp_file"; unset OPENROUTER_API_KEY; }
trap cleanup EXIT
chmod 0600 "$tmp_file"

awk '
  BEGIN { updated = 0 }
  /^OPENROUTER_API_KEY=/ {
    print "OPENROUTER_API_KEY=" ENVIRON["OPENROUTER_API_KEY"]
    updated = 1
    next
  }
  { print }
  END {
    if (!updated) print "OPENROUTER_API_KEY=" ENVIRON["OPENROUTER_API_KEY"]
  }
' "$ENV_FILE" > "$tmp_file"

$INSTALLER 0600 "$tmp_file" "$ENV_FILE"
echo "OpenRouter key installed in $ENV_FILE (value not displayed)."

