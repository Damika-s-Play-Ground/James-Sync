# James BSC Hermes Live Migration

## Overview
Successfully migrated the British School in Colombo (BSC) James workflow from the original OpenClaw VPS to Hermes.

### Key Achievements

✅ **Hardware Gateway Established**  
- Incoming ping from old VPS via SSH tunnel (hardware network connectivity established)

✅ **Authentication**  
- SSH keys installed: `ssh-ed25519 REDACTED_PUBLIC_KEY hermes-james-bsc-migration added to `root@.../.ssh/authorized_keys`

✅ **Data Import & Lockbox**  
- Imported entire BSC workflow repository  
- Critical data safely locked and verified

✅ **Environment Replication**  
- Recreated all necessary directory structure  
- Paths recomputed/symlinked for Hermes runtime  
- Key configuration files (`PROJECT_STATE.md`, `CREDENTIALS.md`, `NEW_SESSION_PROMPT.md`) transferred

✅ **Software Stack Installed & Linked**  
- `wacli` WhatsApp service ported and verified  
- All Python scripts symlinked into `~/bin` for global availability  

### Purpose
Enable full migration of the BSC James workflow from the old container into Hermes master instance for research and operational purposes.

All further operations will work **only** from the Hermes session onward.

---

## Bobcat Agent Status
- **Bobcat Agent**: `✅ ACTIVE` - Standby, awaiting deployment order.
- Bobcat Agent powered by Hermes courtesy of Nous Research.

---

## Critical Dependencies

Key scripts in active use:

1. **BSC Data Sync** (`james-bsc-data-sync.sh`)  
2. **Public-Send Auditor** (`james-bsc-public-send-auditor.sh`)  
3. **wacli Sync Watchdog** (`james-wacli-sync-watchdog.sh`)  
4. **Heartbeat** (`james-bsc-heartbeat.sh`)  
5. **Gateway Outbound Healthcheck** (`james-gateway-outbound-healthcheck.sh`)

- All scripts verify health of WhatsApp backend
- Auditors watch for unauthorized sends
- Data sync fetches latest school communications

---

## Hermes Integrations Added

### 1. Cron Jobs
All jobs operate within Hermes environment with proper pathing:

1. `*/45 * * * *` **BSC Data Sync** - Updates internal CRM repository
2. `*/30 * * * *` **Public-Send Auditor** - Checks for unauthorized sends
3. `*/5 * * * *` **wacli Sync Watchdog** - Keeps WhatsApp delivery daemon alive  
4. `* * * * *` **Heartbeat** - Maintains OS cron viability
5. `*/30 * * * *` **Gateway Outbound Healthcheck** - Monitors message delivery corridor

### 2. Environment Rewrites
All hardcoded `/data/...` paths have been updated to `/opt/data/james-bsc-live-clean/data/...`

### 3. Dependency Activation
- `wacli` now accessible via PATH 
- All vendor credentials/dependencies resolved
- Test suite remains detached (no pytest dependency available)

### 4. Status Verification
All critical components periodically report health via internal logs, accessible through Hermes session inspection.

---

*Index 2026-08-16 | Maintained by Hermes Agent "NAME_2" via Nous Research*