#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_ROOT="${APP_ROOT:-/opt/james}"
BUNDLE="${BUNDLE:-$APP_ROOT/backups/20260919/james-runtime-freeze.bundle.tgz}"
KEY_FILE="${KEY_FILE:-$APP_ROOT/secrets/runtime-aes.key}"
TARGET="${TARGET:-$APP_ROOT/data}"
EXPECTED_SHA256="${EXPECTED_SHA256:-dc9981bd04ed05069e0b26e63fdc87e31136d95fc1be1ae94788b9dfc4810683}"

if [[ "$(id -u)" != "0" ]]; then
  echo "Run as root" >&2
  exit 1
fi
test -r "$BUNDLE" || { echo "Missing encrypted bundle: $BUNDLE" >&2; exit 1; }
test -r "$KEY_FILE" || { echo "Missing decrypted AES key" >&2; exit 1; }

actual_sha256="$(sha256sum "$BUNDLE" | awk '{print $1}')"
[[ "$actual_sha256" == "$EXPECTED_SHA256" ]] || {
  echo "Bundle hash mismatch" >&2
  exit 1
}

work_dir="$(mktemp -d "$APP_ROOT/backups/runtime-restore.XXXXXX")"
cleanup() { rm -rf "$work_dir"; }
trap cleanup EXIT

tar -xzf "$BUNDLE" -C "$work_dir"
test -r "$work_dir/runtime.tar.gz.enc" || { echo "Encrypted runtime archive missing" >&2; exit 1; }

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass "file:${KEY_FILE}" \
  -in "$work_dir/runtime.tar.gz.enc" \
  -out "$work_dir/runtime.tar.gz"

install -d -m 0750 "$TARGET"
tar -xzf "$work_dir/runtime.tar.gz" -C "$TARGET" --no-same-owner --no-same-permissions
echo "Runtime restored to $TARGET from verified encrypted bundle"

