# Hermes cron jobs (sanitized snapshot)

Script-only (`no_agent`). Secrets and JIDs omitted.

- **James BSC Data Sync** — `*/45 * * * *` — script `james-bsc-data-sync.sh` — enabled=True
- **James BSC Public-Send Auditor** — `*/30 * * * *` — script `james-bsc-public-send-auditor.sh` — enabled=True
- **James wacli Sync Watchdog** — `*/5 * * * *` — script `james-wacli-sync-watchdog.sh` — enabled=True
- **James BSC Heartbeat** — `* * * * *` — script `james-bsc-heartbeat.sh` — enabled=True
- **James Gateway Outbound Healthcheck** — `*/30 * * * *` — script `james-gateway-outbound-healthcheck.sh` — enabled=True
- **James BSC Send Slots** — `30 * * * *` — script `james-bsc-send-slots.sh` — enabled=True
- **James BSC Realtime Ingest** — `* * * * *` — script `james-bsc-realtime-ingest.sh` — enabled=True
- **James BSC New Data Auto-Send** — `*/5 * * * *` — script `james-bsc-new-data-auto-send.sh` — enabled=True
- **James BSC Scheduled 6am Summary** — `30 0 * * *` — script `james-bsc-scheduled-6am-summary.sh` — enabled=True
- **James BSC Scheduled 3pm Reminder** — `30 9 * * *` — script `james-bsc-scheduled-3pm-reminder.sh` — enabled=True
- **James BSC Scheduled Weekly Summary** — `30 9 * * 0` — script `james-bsc-scheduled-weekly-summary.sh` — enabled=True
- **James BSC Scheduled Healthcheck** — `*/30 * * * *` — script `james-bsc-scheduled-healthcheck.sh` — enabled=True
