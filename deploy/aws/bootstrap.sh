#!/usr/bin/env bash
set -euo pipefail

# Idempotent Amazon Linux 2023 bootstrap. Run as root (or through SSM with
# sudo). It installs only host prerequisites, clones a public Git ref, and
# prepares protected runtime directories. It does not copy credentials or
# restore WhatsApp state.

APP_ROOT="${APP_ROOT:-/opt/james}"
REPO_URL="${REPO_URL:-https://github.com/Damika-s-Play-Ground/James-Sync.git}"
REF="${REF:-main}"
COMPOSE_VERSION="${COMPOSE_VERSION:-2.39.4}"
AUTO_START="${AUTO_START:-0}"

if [[ "$(id -u)" != "0" ]]; then
  echo "Run as root" >&2
  exit 1
fi

dnf install -y git ca-certificates jq openssl
if ! command -v curl >/dev/null 2>&1; then
  # Amazon Linux commonly ships curl-minimal; avoid replacing it with the
  # conflicting full curl package.
  dnf install -y curl-minimal
fi
systemctl enable --now docker

plugin_dir=/usr/local/lib/docker/cli-plugins
compose_bin="$plugin_dir/docker-compose"
if ! docker compose version >/dev/null 2>&1; then
  install -d -m 0755 "$plugin_dir"
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  curl --fail --location --silent --show-error \
    "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
    --output "$tmp_dir/docker-compose-linux-x86_64"
  curl --fail --location --silent --show-error \
    "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/checksums.txt" \
    --output "$tmp_dir/checksums.txt"
  (cd "$tmp_dir" && grep 'docker-compose-linux-x86_64$' checksums.txt | sha256sum -c -)
  install -m 0755 "$tmp_dir/docker-compose-linux-x86_64" "$compose_bin"
fi

install -d -m 0750 "$APP_ROOT" "$APP_ROOT/secrets" "$APP_ROOT/data" "$APP_ROOT/codex" "$APP_ROOT/backups"
if [[ ! -d "$APP_ROOT/app/.git" ]]; then
  git clone --no-checkout "$REPO_URL" "$APP_ROOT/app"
fi
git -C "$APP_ROOT/app" fetch --depth 1 origin "$REF"
git -C "$APP_ROOT/app" checkout --detach "FETCH_HEAD"

if [[ ! -f "$APP_ROOT/secrets/compose.env" ]]; then
  install -m 0600 "$APP_ROOT/app/compose.env.example" "$APP_ROOT/secrets/compose.env"
fi
if [[ ! -f "$APP_ROOT/secrets/provider.env" ]]; then
  install -m 0600 "$APP_ROOT/app/james/provider.env.example" "$APP_ROOT/secrets/provider.env"
fi
install -m 0644 "$APP_ROOT/app/deploy/aws/james.service" /etc/systemd/system/james.service
systemctl daemon-reload
systemctl enable james.service

echo "James source: $(git -C "$APP_ROOT/app" rev-parse HEAD)"
echo "Compose: $(docker compose version)"
echo "Secrets staged at $APP_ROOT/secrets; edit them before strict startup."

if [[ "$AUTO_START" == "1" ]]; then
  systemctl start james.service
fi
