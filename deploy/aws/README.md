# AWS EC2 deployment

The target is the existing Amazon Linux 2023 `m7i-flex.large` instance. Use
SSM rather than opening new inbound ports. `bootstrap.sh` is safe to rerun and
does not restore credentials or WhatsApp state.

## Bootstrap

From an SSM root shell:

```bash
sudo REPO_URL=https://github.com/Damika-s-Play-Ground/James-Sync.git \
  REF=main bash /tmp/bootstrap.sh
sudo nano /opt/james/secrets/provider.env
sudo nano /opt/james/secrets/compose.env
```

Set `CODEX_MODEL`, `OPENROUTER_MODEL`, and the OpenRouter key in
`provider.env`. Keep `CODEX_HOME=/opt/codex` in `compose.env`; authenticate
Codex inside the persistent volume with `docker compose run --rm hermes codex
login` or the supported access-token flow. Do not commit either file.

## Deploy/update

```bash
sudo bash /opt/james/app/deploy/aws/deploy.sh
sudo systemctl status james --no-pager
docker compose -f /opt/james/app/compose.yaml \
  -f /opt/james/app/deploy/aws/compose.aws.yaml \
  --env-file /opt/james/secrets/compose.env logs --tail=100 hermes
```

The Compose override binds `/opt/james/data` to `/opt/data` and `/opt/james/codex`
to `/opt/codex`, so replacing the image or checking out another Git commit does
not delete WhatsApp/runtime state. The systemd unit restarts the gateway after
host reboot. Strict provider validation blocks startup until Codex auth and
OpenRouter fallback settings are present.

## Runtime restore

The encrypted freeze is copied to `/opt/james/backups/20260919/`. After
provisioning a short-lived `/opt/james/secrets/runtime-aes.key` (32 raw bytes),
run:

```bash
sudo bash /opt/james/app/deploy/aws/restore-runtime.sh
sudo rm -f /opt/james/secrets/runtime-aes.key
```

The script verifies the bundle hash, decrypts only in a mode-0700 temporary
directory, extracts into the persistent data directory, and removes the
temporary archive on exit. The RSA recipient private key remains off-host.
