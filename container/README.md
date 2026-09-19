# Local Hermes container

The image contains the pinned upstream Hermes runtime, the pinned `wacli`
WhatsApp CLI, the versioned James workspace, and the Codex/OpenRouter provider
adapter. Mutable state is kept in
the named `hermes-data` and `codex-home` volumes. The WhatsApp linked-device
session, provider credentials, databases, logs, and media are intentionally not
part of Git or the image.

## Build and smoke-test

From the repository root:

```text
docker compose build
docker compose run --rm hermes --help
docker compose run --rm hermes --version
docker compose run --rm hermes james-llm --help
```

`setup` is optional at this stage. If provider credentials are available,
run it interactively and let Hermes write them to the mounted volume:

```text
docker compose run --rm hermes setup
```

No WhatsApp QR scan is needed locally. Do not run the gateway until setup has
been completed with a test provider configuration:

```text
docker compose up -d hermes
docker compose logs -f hermes
```

Codex authentication belongs in the `codex-home` volume (or an explicitly
mounted secret directory) and OpenRouter credentials are environment/secret
values. The provider order is Codex first, OpenRouter fallback.

The AWS profile pins `wacli` 0.18.2 and points it at the restored
`james-bsc-live-clean/data/.wacli` store. Upgrade that version deliberately and
review its release/checksum before rebuilding.

Before enabling strict startup validation, pair/login Codex and set the
OpenRouter key/model in the runtime secret store:

```bash
docker compose run --rm hermes james-llm --health
JAMES_VALIDATE_CONFIG=1 docker compose up -d hermes
```

Strict validation is deliberately off in the example Compose file so a fresh
image can be inspected before credentials are provisioned. The EC2 deployment
profile enables it.

Stop the container without deleting its state with `docker compose down`.
Do not use `docker compose down -v` unless the local Hermes state is meant to
be discarded.

## Migration to EC2

The same Compose file and image can be used on EC2. Attach an encrypted EBS
volume for `/opt/data` (or restore the named-volume backup), then run Hermes
setup and perform the WhatsApp QR pairing from an SSH/SSM terminal. The QR
session is created on EC2, not baked into the image. Pin a reviewed Hermes
image digest before production upgrades by changing `HERMES_IMAGE` in the
Compose environment.
