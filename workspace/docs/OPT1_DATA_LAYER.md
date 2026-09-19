# BSC Shared Data Fetch Layer — Opt 1 Plan

> Updated: 2026-06-13 | Concise reference

---
## Problem (measured)

Every LLM preview job independently fetches everything:

| Source | Cost per run |
|--------|-------------|
| `wacli sync --once` | **33 seconds** |
| 4× group reads (200 msgs) | ~70ms, ~10,000 tokens |
| Newsletter (Jina) | ~2,700ms, ~4,500 tokens |
| iCal (live) | unknown, ~2,500 tokens |
| **Total** | **~36s overhead, ~17,800 tokens/run** |

- 14 runs/day = ~215,000 input tokens/day
- 5 of 6 urgent slots return HOLD (nothing new) = ~89,000 tokens wasted
- Newsletter cache currently 5 days stale with no enforcement

## Solution: Decouple Fetch from Extraction

```
bsc-data-sync.py  (every 90 min, OS cron, NO LLM)
  → fetches all sources → writes bsc-data.db
  
All LLM preview jobs
  → read DB only (<5ms) → extract → draft
```

---

## Storage: SQLite + WAL

**Why SQLite over JSON files / DuckDB:**
- WAL mode: sync writes never block concurrent LLM reads
- FTS5 full-text search built in (critical as message volume grows)
- Single portable `.db` file, universal tooling
- DuckDB rejected: single-writer lock risks blocking LLM jobs mid-run

---

## Schema (6 tables)

```sql
-- Source registry — add new group/feed = one INSERT, zero code change
sources (id, type, name, config JSON, audience, active, added_at)

-- All messages from all WhatsApp groups (+ future sources)
messages (id PK, source_id FK, sender_jid, sender_name, 
          timestamp, text, has_attachment, raw_json, ingested_at)

-- Attachments: raw file on disk, extracted text inline in DB
attachments (id PK, message_id FK,  -- ← the critical link
             raw_path,              -- 'state/bsc-attachments/<msg_id>.pdf'
             extracted_text,        -- inline — fast to read at query time
             extracted_links JSON,  -- URLs extracted from PDF
             extraction_method, extraction_status, mime_type, file_name)

-- Newsletters, iCal — structured periodic documents
documents (id PK, source_id FK, issue_date, content_hash,
           raw_text, parsed_json, fetched_at, is_current)

-- Per-source sync history — TTL checks + audit
sync_log (id, source_id, synced_at, new_count, status, error, duration_ms)

-- FTS5: message body + attachment text searchable as one unit
CREATE VIRTUAL TABLE fts_content USING fts5(
    message_id UNINDEXED, source_id UNINDEXED, timestamp UNINDEXED,
    text, attachment_text,
    tokenize = "unicode61 remove_diacritics 2"
);
```

## Attachment Handling (Option B: file on disk + path in DB)

```
1. Detect: messages.has_attachment=1 AND no attachments row yet
2. wacli media download → state/bsc-attachments/<message_id>.<ext>
3. Extract:
   PDF  → pymupdf (fitz) → extracted_text + extracted_links
   Image → tesseract → extracted_text
4. INSERT INTO attachments (raw_path, extracted_text, extracted_links, ...)
5. INSERT OR REPLACE INTO fts_content (message body + attachment text merged)
```

**At query time — message + attachment arrive in one row:**
```sql
SELECT m.text, m.timestamp, s.name,
       a.extracted_text, a.extracted_links   -- already joined
FROM messages m
JOIN sources s ON m.source_id = s.id
LEFT JOIN attachments a ON a.message_id = m.id
WHERE m.timestamp > datetime('now', '-72 hours') AND s.active = 1
```

---

## Sync Engine (bsc-data-sync.py)

**TTLs per source type:**

| Type | TTL | Re-fetch trigger |
|------|-----|-----------------|
| whatsapp_group | 90 min | TTL expiry. `wacli sync --once` runs once per cycle (not per group) |
| newsletter | 24h | TTL expiry OR content hash changed |
| ical | 6h | TTL expiry |
| rss/future | configurable in sources.config | TTL + etag |

**Flow:**
```
1. Open DB (WAL mode)
2. SELECT * FROM sources WHERE active=1
3. wacli sync --once  (once per cycle — shared 33s cost)
4. For each source: check TTL → skip or fetch
5. INSERT new messages (ignore existing IDs)
6. For new messages with attachments: download → extract → insert
7. Update sync_log
8. Alert dev group on any fetch failure
```

---

## Client Helper (bsc-data-client.py)

Importable module used by all LLM preview jobs:

```python
data = BSCDataClient()

data.is_cache_fresh(max_age_minutes=120)      # freshness gate
data.get_recent_messages(hours=72)            # messages + attachments joined
data.get_new_message_count(since_iso)         # change-gate for urgent slots
data.get_current_newsletter()                 # latest newsletter doc
data.get_upcoming_events(days=14)             # parsed iCal events
data.search(query, limit=20)                  # FTS5 full-text search
```

## How LLM Jobs Change

**Before:** each job prompt contains fetch instructions (~36s overhead before LLM starts)

**After:**
```python
data = BSCDataClient()
if not data.is_cache_fresh(): write_hold("cache stale"); exit()

# Urgent slots only — skip LLM entirely if nothing new
if slot.startswith('urgent'):
    if data.get_new_message_count(since=last_cycle_ts) == 0:
        write_hold("no new messages"); exit()  # zero tokens burned

messages   = data.get_recent_messages(hours=72)
newsletter = data.get_current_newsletter()
events     = data.get_upcoming_events()
# → LLM extracts from pre-joined, pre-filtered context
```

---

## Cron Changes

**Add:** `bsc-data-sync.py` — OS crontab, every 90 min, zero LLM tokens
```
*/90 * * * * run-bsc-job.sh "BSC Data Sync" python3 bsc-data-sync.py
```

**Remove from all LLM job prompts:** wacli sync, group reads, newsletter fetch, iCal fetch

**Remove from OCPlatform:** standalone 1400 preview + 1400 retry jobs (2 jobs → 0, handled by generic urgent preview reading from DB)

---

## Scaling: Adding Sources

Adding a new WhatsApp group = one INSERT, zero code changes:
```sql
INSERT INTO sources VALUES
  ('wa:REDACTED_JID', 'whatsapp_group', 'BSC Year 4 Parents',
   '{"jid":"REDACTED_JID","limit":100}', 'year4', 1, '2026-09-01T00:00:00Z');
```

`audience` column lets LLM jobs filter by year group at the DB layer — Year 3 jobs never see Year 6 messages.

**Future source types** (add a handler, not a schema change): `rss`, `telegram_group`, `email_imap`, `web_page`

---

## Retention

```python
# Messages: purge > 90 days (weekly cleanup in sync script)
DELETE FROM messages WHERE timestamp < datetime('now', '-90 days');

# Attachment raw files: purge > 30 days; extracted_text stays in DB forever
# LLM reads extracted_text — never notices raw file is gone

# Newsletters: keep last 8 weeks, is_current=1 for latest only
```

**Estimated DB growth:** ~50MB after 1 year with 10 groups. SQLite handles ~1TB.

---

## Impact

| Metric | Before | After |
|--------|--------|-------|
| Input tokens/day | ~215,000 | ~65,000 (~70% reduction) |
| Wasted tokens on HOLD urgent runs | ~89,000 | ~0 |
| LLM job pre-start overhead | ~36 seconds | <5ms |
| Newsletter staleness | Up to 5+ days | Max 24h |
| Add new source | Code change in every job | One INSERT |
| Sync write blocks LLM reads | Race condition | WAL — zero blocking |

---

## Build Order

1. `bsc-data-sync.py` — DB init + all source handlers + attachment pipeline
2. `bsc-data-client.py` — query helpers
3. Seed `sources` table with 4 current groups + newsletter + iCal
4. OS crontab entry (90 min)
5. Run first sync, verify output
6. Update OCPlatform cron job prompts to use `BSCDataClient`
7. Remove 1400 special-case jobs
8. Monitor 24h, then add retention cleanup

> **Safe rollout:** Steps 1–5 run silently alongside live jobs. Switch happens only at Step 6. Revert = restore old prompt.
