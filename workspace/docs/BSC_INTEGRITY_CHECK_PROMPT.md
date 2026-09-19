# BSC System Integrity Check — Prompt

> Updated: 2026-06-17 | Concise version with data extraction health

---

Run the following checks and report ONLY failures or warnings. If everything is healthy, reply with a single line: `✅ All systems healthy`.

## 1. wacli Sync Daemon
- Check: `cat /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/wacli-sync-daemon.pid` and verify PID is alive
- Check: last 5 lines of `/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/logs/cron/wacli-sync-daemon.log` for "Connected" or "Reconnecting"
- FAIL if: daemon is not running, or last log entry is >10 min old with no "Connected"

## 2. Source Staleness (data extraction health)
Run:
```
python3 -c "
import sqlite3
from datetime import datetime, timezone
conn = sqlite3.connect('/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/bsc-data.db')
sources = {
  'wa:REDACTED_GROUP_ID': 'Sport & ECAs',
  'wa:REDACTED_GROUP_ID': 'Yr3 Parents',
  'wa:REDACTED_GROUP_ID': 'Junior School',
  'wa:REDACTED_GROUP_ID': 'Parent Community',
}
now = datetime.now(timezone.utc)
for src_id, name in sources.items():
    row = conn.execute(\"SELECT MAX(timestamp) FROM messages WHERE source_id=? AND id NOT LIKE 'MANUAL:%'\", (src_id,)).fetchone()
    ts = row[0] or 'none'
    if ts != 'none':
        gap = (now - datetime.fromisoformat(ts.replace('Z','+00:00'))).days
        status = '🔴' if gap >= 4 else ('⚠️' if gap >= 2 else '✅')
        print(f'{status} {name}: {gap}d gap (last: {ts[:10]})')
    else:
        print(f'🔴 {name}: no messages')
conn.close()
"
```
- FAIL if any source shows 🔴 (4+ day gap)
- WARN if any source shows ⚠️ (2-3 day gap)

## 3. Attachment Extraction Health
Run:
```
python3 -c "
import sqlite3
conn = sqlite3.connect('/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/bsc-data.db')
total = conn.execute('SELECT COUNT(*) FROM attachments').fetchone()[0]
failed = conn.execute(\"SELECT COUNT(*) FROM attachments WHERE extraction_status IN ('download_failed','expired','no_text')\").fetchone()[0]
ok = conn.execute(\"SELECT COUNT(*) FROM attachments WHERE extraction_status='ok'\").fetchone()[0]
print(f'Attachments: {total} total, {ok} extracted OK, {failed} failed/expired')
# Check for recent unextracted attachments (has_attachment=1 but no attachments row)
unextracted = conn.execute(\"SELECT COUNT(*) FROM messages m WHERE m.has_attachment=1 AND m.timestamp > datetime('now','-7 days') AND NOT EXISTS (SELECT 1 FROM attachments a WHERE a.message_id=m.id)\").fetchone()[0]
if unextracted > 0:
    print(f'⚠️ {unextracted} recent messages with unextracted attachments')
conn.close()
"
```
- WARN if unextracted recent attachments > 0

## 4. Draft Pipeline
- Check last 10 lines of audit.log: `tail -10 /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/bsc-agent-drafts/audit.log`
- FAIL if any draft is in AUTO_HOLD with reason `items_missing` or `items_unverified`
- WARN if any PENDING draft has send_at more than 2 hours in the past

## 5. Cron Watchdog
- Check: watchdog cron is in crontab: `crontab -l | grep watchdog`
- FAIL if not found

## 6. Gateway Outbound Health
- Run: `GATEWAY_HEALTH_DRY_RUN=1 python3 /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/scripts/gateway-outbound-healthcheck.py`
- Report only if FAIL or WARN

---

**Output format:** One line per check. Only include failing/warning checks. If all pass → `✅ All systems healthy`.
