# Donely source mirror

This commit is the sanitized source mirror captured from the active Donely
Hermes instance on 2026-09-19.

Included:

- the active BSC workspace scripts, tests, bin helpers, policy documents, and
  workspace guidance;
- Hermes cron wrappers and the current root cron job inventory;
- host-level James wrappers and the Ikman extraction helpers;
- the Donely SOUL.md, custom Donely skill, and live learning notes.

WhatsApp JIDs and private IP addresses are replaced with REDACTED_JID and
REDACTED_IP. Live values must be supplied through the protected runtime
environment (hermes/env.sh, .env, or an AWS secret store); do not restore
them by editing Git files.

The BSC source/group identifiers and administrator list are also supplied
through the BSC_*_JID, BSC_*_SOURCE_ID, and BSC_ADMIN_JIDS environment
variables shown in hermes/env.example.

Excluded deliberately:

- WhatsApp authentication/stores (.wacli, wacli);
- databases, sessions, logs, media, caches, and parent message history;
- Hermes/OpenClaw credentials and model/MCP secrets;
- virtual environments, package caches, and the broken live .git directory.

Those items are in the encrypted runtime backup documented in
SECURE_RUNTIME_BACKUP.md.
