#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/james}"
REF="${REF:-main}"

if [[ "$(id -u)" != "0" ]]; then
  echo "Run as root" >&2
  exit 1
fi

git -C "$APP_ROOT/app" fetch --depth 1 origin "$REF"
git -C "$APP_ROOT/app" checkout --detach "FETCH_HEAD"

test -s "$APP_ROOT/secrets/provider.env" || { echo "provider.env is empty" >&2; exit 1; }
test -s "$APP_ROOT/secrets/compose.env" || { echo "compose.env is empty" >&2; exit 1; }

cd "$APP_ROOT/app"
docker compose -f compose.yaml -f deploy/aws/compose.aws.yaml \
  --env-file "$APP_ROOT/secrets/compose.env" build --pull
docker compose -f compose.yaml -f deploy/aws/compose.aws.yaml \
  --env-file "$APP_ROOT/secrets/compose.env" up -d

docker compose -f compose.yaml -f deploy/aws/compose.aws.yaml \
  --env-file "$APP_ROOT/secrets/compose.env" run --rm --no-deps hermes james-llm --health --strict
docker compose -f compose.yaml -f deploy/aws/compose.aws.yaml \
  --env-file "$APP_ROOT/secrets/compose.env" ps

