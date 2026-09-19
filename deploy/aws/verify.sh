#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/james}"
cd "$APP_ROOT/app"
dc=(docker compose -f compose.yaml -f deploy/aws/compose.aws.yaml --env-file "$APP_ROOT/secrets/compose.env")

"${dc[@]}" config --quiet
"${dc[@]}" run --rm --no-deps hermes james-llm --health --strict
"${dc[@]}" run --rm --no-deps --entrypoint /usr/local/bin/wacli hermes --read-only doctor
"${dc[@]}" ps

if [[ -n "${SMOKE_PROMPT:-}" ]]; then
  "${dc[@]}" run --rm --no-deps hermes james-llm --json "$SMOKE_PROMPT"
fi

