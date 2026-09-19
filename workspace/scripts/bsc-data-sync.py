#!/usr/bin/env python3
"""
bsc-data-sync.py — BSC Shared Data Fetch Layer
Runs every 45 min via Hermes cron (job "James BSC Data Sync"). No LLM.
Fetches all sources → writes bsc-data.db.
"""
import sqlite3, json, os, sys, time, hashlib, subprocess, logging, re, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
DB_PATH   = WORKSPACE / "state" / "bsc-data.db"
ATT_DIR   = WORKSPACE / "state" / "bsc-attachments"
LOG_DIR   = WORKSPACE / "logs" / "cron"
DEV_GROUP = os.getenv("BSC_DEV_JID", "REDACTED_JID")
YEAR4_JID = os.getenv("BSC_YEAR4_JID", "REDACTED_JID")
JUNIOR_SCHOOL_JID = os.getenv("BSC_JUNIOR_SCHOOL_JID", "REDACTED_JID")
SPORT_ECAS_JID = os.getenv("BSC_SPORT_ECAS_JID", "REDACTED_JID")
PARENT_COMMUNITY_JID = os.getenv("BSC_PARENT_COMMUNITY_JID", "REDACTED_JID")
YEAR4_SOURCE_ID = os.getenv("BSC_YEAR4_SOURCE_ID", "wa:REDACTED_GROUP_ID")
JUNIOR_SCHOOL_SOURCE_ID = os.getenv("BSC_JUNIOR_SCHOOL_SOURCE_ID", "wa:REDACTED_GROUP_ID")
SPORT_ECAS_SOURCE_ID = os.getenv("BSC_SPORT_ECAS_SOURCE_ID", "wa:REDACTED_GROUP_ID")
PARENT_COMMUNITY_SOURCE_ID = os.getenv("BSC_PARENT_COMMUNITY_SOURCE_ID", "wa:REDACTED_GROUP_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "BSC_Data_Sync.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("bsc-data-sync")

SOURCES = [
    # Same WhatsApp subgroup as last year; BSC renamed it from Yr3 2025/26 to Yr4 2026/27.
    # Keep the stable source id/JID so historical messages remain in one timeline, but update
    # source metadata and audience for the new academic year.
    {"id": YEAR4_SOURCE_ID, "type": "whatsapp_group", "name": "BSC Yr4 Parents 2026/27",
     "config": {"jid": YEAR4_JID, "limit": 500}, "audience": "year4", "ttl_min": 0},
    {"id": JUNIOR_SCHOOL_SOURCE_ID, "type": "whatsapp_group", "name": "BSC Junior School",
     "config": {"jid": JUNIOR_SCHOOL_JID, "limit": 500}, "audience": "junior_school", "ttl_min": 0},
    {"id": SPORT_ECAS_SOURCE_ID, "type": "whatsapp_group", "name": "BSC Sport & ECAs",
     "config": {"jid": SPORT_ECAS_JID, "limit": 500}, "audience": "sport_ecas", "ttl_min": 0},
    {"id": PARENT_COMMUNITY_SOURCE_ID, "type": "whatsapp_group", "name": "BSC Parent Community",
     "config": {"jid": PARENT_COMMUNITY_JID, "limit": 500}, "audience": "parent_community", "ttl_min": 0},
    {"id": "newsletter:week_ahead", "type": "newsletter", "name": "BSC Week Ahead Newsletter",
     "config": {}, "audience": "all", "ttl_min": 0},
]


# ── DB init ──────────────────────────────────────────────────────────────────

def init_db(conn):
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA busy_timeout=5000;
    PRAGMA foreign_keys=ON;

    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY, type TEXT, name TEXT,
        config TEXT, audience TEXT, active INTEGER DEFAULT 1,
        ttl_min INTEGER DEFAULT 90, added_at TEXT
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        source_id TEXT REFERENCES sources(id),
        sender_jid TEXT, sender_name TEXT,
        timestamp TEXT, text TEXT,
        has_attachment INTEGER DEFAULT 0,
        raw_json TEXT, ingested_at TEXT
    );

    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT REFERENCES messages(id),
        raw_path TEXT, extracted_text TEXT,
        extracted_links TEXT, extraction_method TEXT,
        extraction_status TEXT, mime_type TEXT, file_name TEXT
    );

    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, source_id TEXT REFERENCES sources(id),
        issue_date TEXT, content_hash TEXT,
        raw_text TEXT, parsed_json TEXT,
        fetched_at TEXT, is_current INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT, synced_at TEXT,
        new_count INTEGER, status TEXT,
        error TEXT, duration_ms INTEGER
    );

    CREATE VIRTUAL TABLE IF NOT EXISTS fts_content USING fts5(
        message_id UNINDEXED, source_id UNINDEXED, timestamp UNINDEXED,
        text, attachment_text,
        tokenize="unicode61 remove_diacritics 2"
    );

    CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source_id);
    CREATE INDEX IF NOT EXISTS idx_messages_ts     ON messages(timestamp);
    CREATE INDEX IF NOT EXISTS idx_att_msg         ON attachments(message_id);
    """)
    conn.commit()

def seed_sources(conn):
    now = datetime.now(timezone.utc).isoformat()
    for s in SOURCES:
        # Upsert, not INSERT OR IGNORE: WhatsApp communities get renamed at term/year
        # rollover while keeping the same JID. The shared DB metadata must track that.
        conn.execute("""
            INSERT INTO sources (id, type, name, config, audience, active, ttl_min, added_at)
            VALUES (?,?,?,?,?,1,?,?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type,
                name=excluded.name,
                config=excluded.config,
                audience=excluded.audience,
                ttl_min=excluded.ttl_min,
                active=1
        """, (s["id"], s["type"], s["name"], json.dumps(s["config"]),
              s["audience"], s["ttl_min"], now))
    conn.commit()


# ── TTL check ────────────────────────────────────────────────────────────────

def needs_sync(conn, source_id, ttl_min):
    row = conn.execute("""
        SELECT synced_at FROM sync_log
        WHERE source_id=? AND status='ok'
        ORDER BY synced_at DESC LIMIT 1
    """, (source_id,)).fetchone()
    if not row:
        return True
    last = datetime.fromisoformat(row[0])
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() > ttl_min * 60

# ── wacli sync ───────────────────────────────────────────────────────────────

def wacli_sync_once():
    log.info("Running wacli sync --once ...")
    t0 = time.time()
    r = subprocess.run(["wacli", "sync", "--once", "--lock-wait", "60s"], capture_output=True, text=True, timeout=120)
    elapsed = int((time.time() - t0) * 1000)
    if r.returncode != 0:
        log.warning(f"wacli sync --once exited {r.returncode}: {r.stderr[:200]}")
    else:
        log.info(f"wacli sync --once done in {elapsed}ms")
    return r.returncode == 0

def fetch_whatsapp_group(conn, source):
    jid    = source["config"]["jid"]
    limit  = source["config"].get("limit", 200)
    src_id = source["id"]
    t0     = time.time()

    log.info(f"Fetching {source['name']} ({jid}) ...")
    r = subprocess.run(
        ["wacli", "messages", "list", "--chat", jid, "--limit", str(limit), "--json"],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        log.error(f"wacli messages list failed for {jid}: {r.stderr[:200]}")
        _log_sync(conn, src_id, 0, "error", r.stderr[:500], int((time.time()-t0)*1000))
        return 0

    try:
        parsed = json.loads(r.stdout)
        # wacli returns {"success":true,"data":{"messages":[...]}}
        if isinstance(parsed, dict):
            if "data" in parsed and isinstance(parsed["data"], dict):
                msgs = parsed["data"].get("messages", [])
            elif "messages" in parsed:
                msgs = parsed["messages"]
            else:
                msgs = []
        elif isinstance(parsed, list):
            msgs = parsed
        else:
            msgs = []
    except json.JSONDecodeError as e:
        log.error(f"JSON parse error for {jid}: {e}")
        _log_sync(conn, src_id, 0, "error", str(e), int((time.time()-t0)*1000))
        return 0

    new_count = 0
    now_iso   = datetime.now(timezone.utc).isoformat()
    ATT_DIR.mkdir(parents=True, exist_ok=True)

    for m in msgs:
        msg_id = m.get("MsgID") or m.get("ID") or m.get("id") or m.get("MessageID") or ""
        if not msg_id:
            continue
        # Normalise timestamp
        ts = m.get("Timestamp") or m.get("timestamp") or ""
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        text     = m.get("Text") or m.get("text") or m.get("Body") or m.get("body") or m.get("MediaCaption") or ""
        sender   = m.get("SenderJID") or m.get("sender") or ""
        s_name   = m.get("SenderName") or m.get("sender_name") or ""
        fname_att = m.get("Filename") or m.get("FileName") or m.get("file_name") or ""
        mime_att  = m.get("MimeType") or m.get("mime_type") or ""
        media_type = m.get("MediaType") or m.get("media_type") or ""
        # Only mark as extractable attachment if DirectPath is set (media available) AND
        # it's a document/image type — skip reactions, stickers, voice, revoked
        direct_path = m.get("DirectPath") or m.get("direct_path") or ""
        is_reaction = bool(m.get("ReactionEmoji") or m.get("ReactionToID"))
        is_doc_or_image = fname_att or any(t in mime_att.lower() for t in ["pdf", "application/", "image/", "jpeg", "png", "webp"])
        has_att = 1 if (direct_path and is_doc_or_image and not is_reaction) else 0

        existing = conn.execute("SELECT id FROM messages WHERE id=?", (msg_id,)).fetchone()
        if existing:
            continue

        conn.execute("""
            INSERT OR IGNORE INTO messages
              (id, source_id, sender_jid, sender_name, timestamp, text, has_attachment, raw_json, ingested_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (msg_id, src_id, sender, s_name, ts, text, has_att, json.dumps(m), now_iso))

        # FTS index
        conn.execute("""
            INSERT OR REPLACE INTO fts_content (message_id, source_id, timestamp, text, attachment_text)
            VALUES (?,?,?,?,'')
        """, (msg_id, src_id, ts, text))

        new_count += 1

        # Queue attachment download if present
        if has_att:
            _maybe_download_attachment(conn, msg_id, m, jid)

    conn.commit()
    elapsed = int((time.time() - t0) * 1000)
    log.info(f"  {source['name']}: {new_count} new messages in {elapsed}ms")
    _log_sync(conn, src_id, new_count, "ok", None, elapsed)
    return new_count

def _daemon_alive():
    pid_file = WORKSPACE / "state" / "wacli-sync-daemon.pid"
    if not pid_file.exists():
        return False
    try:
        import os as _os
        _os.kill(int(pid_file.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def _maybe_download_attachment(conn, msg_id, msg_data, jid):
    existing = conn.execute("SELECT id FROM attachments WHERE message_id=?", (msg_id,)).fetchone()
    if existing:
        return
    mime = msg_data.get("MimeType") or msg_data.get("mime_type") or ""
    fname = msg_data.get("Filename") or msg_data.get("FileName") or msg_data.get("file_name") or ""
    if _daemon_alive():
        # Daemon holds the store lock; media download would fail with
        # "store is locked". Record a RETRYABLE marker — swept by
        # _retry_deferred_attachments() once the daemon is observed down.
        log.warning(f"  Attachment deferred for {msg_id} (sync daemon running)")
        _insert_attachment(conn, msg_id, "", None, None, "none", "daemon_running", mime, fname)
        return
    _download_and_extract(conn, msg_id, msg_data, jid)


def _download_and_extract(conn, msg_id, msg_data, jid):
    mime = msg_data.get("MimeType") or msg_data.get("mime_type") or ""
    fname = msg_data.get("Filename") or msg_data.get("FileName") or msg_data.get("file_name") or ""
    ext = Path(fname).suffix.lower() if fname else (".pdf" if "pdf" in mime else ".bin")
    raw_path = ATT_DIR / f"{msg_id}{ext}"
    try:
        log.info(f"  Downloading attachment for {msg_id} ...")
        r = subprocess.run(
            ["wacli", "media", "download", "--chat", jid, "--id", msg_id, "--output", str(raw_path)],
            capture_output=True, text=True, timeout=60
        )
        err_text = r.stderr[:200] if r.stderr else ""
        if "403" in err_text or "410" in err_text:
            # Expired CDN link — normal for old messages, skip silently
            _insert_attachment(conn, msg_id, str(raw_path), None, None, "none", "expired", mime, fname)
            return
        if r.returncode != 0 or not raw_path.exists():
            log.warning(f"  Attachment download failed for {msg_id}: {err_text[:80]}")
            _insert_attachment(conn, msg_id, str(raw_path), None, None, "none", "download_failed", mime, fname)
            return
    except Exception as e:
        log.warning(f"  Attachment exception {msg_id}: {e}")
        _insert_attachment(conn, msg_id, str(raw_path), None, None, "none", "download_error", mime, fname)
        return

    extracted_text, extracted_links, method = _extract_attachment(raw_path, mime)
    _insert_attachment(conn, msg_id, str(raw_path), extracted_text, extracted_links, method,
                       "ok" if extracted_text else "no_text", mime, fname)

    # Update FTS with attachment text
    if extracted_text:
        conn.execute("""
            UPDATE fts_content SET attachment_text=? WHERE message_id=?
        """, (extracted_text, msg_id))


def _retry_deferred_attachments(conn):
    """Retry attachments marked daemon_running once the sync daemon is down.

    Marker rows exist purely so the `existing` short-circuit doesn't hide
    them; we delete-then-redownload so status transitions stay honest.
    """
    rows = conn.execute("""
        SELECT a.message_id FROM attachments a
        WHERE a.extraction_status='daemon_running'
        LIMIT 200
    """).fetchall()
    if not rows:
        return
    log.info(f"Retrying {len(rows)} deferred attachment(s) ...")
    for (msg_id,) in rows:
        conn.execute("DELETE FROM attachments WHERE message_id=? AND extraction_status='daemon_running'", (msg_id,))
        mrow = conn.execute("SELECT raw_json FROM messages WHERE id=?", (msg_id,)).fetchone()
        if not mrow or not mrow[0]:
            continue
        try:
            msg_data = json.loads(mrow[0])
        except Exception:
            continue
        # Resolve the chat JID from the source config (raw_json may not carry it)
        srow = conn.execute("""
            SELECT s.config FROM sources s JOIN messages m ON m.source_id=s.id WHERE m.id=?
        """, (msg_id,)).fetchone()
        jid = ""
        if srow and srow[0]:
            try:
                jid = json.loads(srow[0]).get("jid", "")
            except Exception:
                jid = ""
        if jid:
            _download_and_extract(conn, msg_id, msg_data, jid)
    conn.commit()

def _extract_attachment(path: Path, mime: str):
    mime = mime.lower()
    try:
        if "pdf" in mime or path.suffix.lower() == ".pdf":
            import fitz
            doc = fitz.open(str(path))
            text = "\n".join(page.get_text() for page in doc)
            links = []
            for page in doc:
                for link in page.get_links():
                    if link.get("uri"):
                        links.append(link["uri"])
            return text.strip(), json.dumps(links), "pymupdf"
        elif any(x in mime for x in ["image/", "jpg", "jpeg", "png", "webp"]):
            import subprocess as sp
            r = sp.run(["tesseract", str(path), "stdout", "-l", "eng"],
                       capture_output=True, text=True, timeout=30)
            return r.stdout.strip(), None, "tesseract"
    except Exception as e:
        log.warning(f"  Extraction failed for {path}: {e}")
    return None, None, "failed"

def _insert_attachment(conn, msg_id, raw_path, text, links, method, status, mime, fname):
    conn.execute("""
        INSERT OR IGNORE INTO attachments
          (message_id, raw_path, extracted_text, extracted_links,
           extraction_method, extraction_status, mime_type, file_name)
        VALUES (?,?,?,?,?,?,?,?)
    """, (msg_id, raw_path, text, links, method, status, mime, fname))


# ── Week Ahead Newsletter Fetch ──────────────────────────────────────────────

WEEK_AHEAD_PATTERN = re.compile(
    r'(https?://(?:shorturl\.at|bit\.ly|tinyurl\.com|s\.bsc\.lk|ow\.ly|rb\.gy)/\S+)',
    re.IGNORECASE
)
WEEK_AHEAD_MSG_PATTERN = re.compile(
    r'(?:week.ahead|weekly.notice|week.beginning|week.commencing)',
    re.IGNORECASE
)

def _jina_fetch(url: str, timeout: int = 20, attempts: int = 3) -> str:
    """Fetch URL content via Jina Reader (handles shortlinks + Cloudflare).

    Retries with backoff — r.jina.ai occasionally 5xx/timeouts; a single
    transient blip used to cost a full hourly scan cycle.
    """
    jina_url = f"https://r.jina.ai/{url}"
    last_err = None
    for i in range(attempts):
        req = urllib.request.Request(jina_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(2 * (i + 1))  # 2s, 4s
    raise RuntimeError(f"Jina fetch failed for {url} after {attempts} attempts: {last_err}")

def fetch_week_ahead_newsletter(conn):
    """Scan recent messages for Week Ahead shortlinks and fetch+store the content."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    rows = conn.execute(
        "SELECT id, text, timestamp FROM messages WHERE timestamp >= ? AND text IS NOT NULL",
        (cutoff,)
    ).fetchall()

    fetched = 0
    for msg_id, text, ts in rows:
        if not WEEK_AHEAD_MSG_PATTERN.search(text):
            continue
        urls = WEEK_AHEAD_PATTERN.findall(text)
        if not urls:
            continue
        url = urls[0]
        doc_id = f"newsletter:{msg_id}"
        existing = conn.execute("SELECT id FROM documents WHERE id=?", (doc_id,)).fetchone()
        if existing:
            continue
        try:
            log.info(f"  Week Ahead: fetching {url} (msg {msg_id})")
            content = _jina_fetch(url)
            # Trim boilerplate — take first 8000 chars of substantive content
            content = content[:30000].strip()
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            issue_date = ts[:10]
            # Ensure the newsletter source row exists (no TTL-based fetching, just a registry entry)
            conn.execute("""
                INSERT OR IGNORE INTO sources (id, type, name, config, audience, active, ttl_min, added_at)
                VALUES ('newsletter:week_ahead','newsletter','BSC Week Ahead Newsletter','{}','all',1,0,?)
            """, (datetime.now(timezone.utc).isoformat(),))
            # Mark all previous newsletters as not current
            conn.execute("UPDATE documents SET is_current=0 WHERE source_id='newsletter:week_ahead'")
            conn.execute("""
                INSERT OR REPLACE INTO documents
                    (id, source_id, issue_date, content_hash, raw_text, parsed_json, fetched_at, is_current)
                VALUES (?,?,?,?,?,?,?,1)
            """, (
                doc_id, "newsletter:week_ahead", issue_date,
                content_hash, content, None,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
            fetched += 1
            log.info(f"  Week Ahead stored: {len(content)} chars from {url}")
        except Exception as e:
            log.warning(f"  Week Ahead fetch failed for {url}: {e}")

    return fetched


def run_retention(conn):
    # Messages older than 90 days — cascade through child tables first
    old_ids = [row[0] for row in conn.execute(
        "SELECT id FROM messages WHERE timestamp < datetime('now', '-90 days')"
    ).fetchall()]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        conn.execute(f"DELETE FROM attachments WHERE message_id IN ({placeholders})", old_ids)
        conn.execute(f"DELETE FROM fts_content WHERE message_id IN ({placeholders})", old_ids)
        conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", old_ids)
        log.info(f"Retention: deleted {len(old_ids)} old messages")
    # Attachment raw files older than 30 days (keep extracted_text in DB)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    for row in conn.execute("SELECT raw_path FROM attachments WHERE extraction_status='ok'").fetchall():
        p = Path(row[0])
        if p.exists() and p.stat().st_mtime < cutoff.timestamp():
            p.unlink(missing_ok=True)
    # Newsletters: keep last 8 weeks
    conn.execute("""
        DELETE FROM documents
        WHERE source_id LIKE 'newsletter%'
          AND is_current=0
          AND fetched_at < datetime('now', '-56 days')
    """)
    conn.commit()

def _log_sync(conn, source_id, new_count, status, error, duration_ms):
    conn.execute("""
        INSERT INTO sync_log (source_id, synced_at, new_count, status, error, duration_ms)
        VALUES (?,?,?,?,?,?)
    """, (source_id, datetime.now(timezone.utc).isoformat(), new_count, status, error, duration_ms))
    conn.commit()


# ── Alerting ─────────────────────────────────────────────────────────────────

STALENESS_THRESHOLD_DAYS = 4
STALENESS_ALERT_STATE = WORKSPACE / "state" / "bsc-staleness-alerted.json"

def _check_daemon_health(conn, errors):
    """Check if wacli sync daemon is running, and alert if any BSC source is stale."""
    pid_file = WORKSPACE / "state" / "wacli-sync-daemon.pid"
    daemon_ok = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            import os as _os
            _os.kill(pid, 0)
            daemon_ok = True
            log.info(f"wacli sync daemon running (pid={pid})")
        except (OSError, ValueError):
            pass
    if not daemon_ok:
        log.warning("wacli sync daemon NOT running — falling back to sync --once")
        ok = wacli_sync_once()
        if not ok:
            errors.append("wacli sync --once fallback failed")
        alert_dev("⚠️ wacli sync daemon not found — ran sync --once as fallback. Check watchdog.")
    _check_staleness(conn)

def _store_latest(jid):
    """Newest message timestamp for a JID straight from the wacli store, or None."""
    try:
        r = subprocess.run(
            ["wacli", "messages", "list", "--read-only", "--chat", jid, "--limit", "1", "--json"],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0:
            return None
        parsed = json.loads(r.stdout)
        msgs = (parsed.get("data") or {}).get("messages") or []
        return msgs[0].get("Timestamp") if msgs else None
    except Exception:
        return None


PIPELINE_LAG_THRESHOLD_MIN = 15  # realtime ingest keeps DB within ~2 min of store


def _check_staleness(conn):
    """Alert DEV only on PIPELINE failures, never on group quietness.

    Old behaviour alerted when any group had no new messages for >4 days —
    which spammed DEV all summer whenever a low-traffic group went quiet
    (Sport & ECAs: silent since 2026-07-31 while school is on holiday).

    New logic per source:
      * store newest vs DB newest. If DB trails the wacli store by more than
        PIPELINE_LAG_THRESHOLD_MIN → messages exist on WhatsApp but are not
        reaching the shared layer → real incident → alert (once/day/source).
      * If store ≈ DB (or both quiet) → pipeline healthy → no alert.
    """
    now = datetime.now(timezone.utc)
    try:
        alerted = json.loads(STALENESS_ALERT_STATE.read_text())
    except Exception:
        alerted = {}

    lags = []
    for s in SOURCES:
        if s["type"] != "whatsapp_group":
            continue
        src_id, jid, name = s["id"], s["config"]["jid"], s["name"]

        db_row = conn.execute(
            "SELECT MAX(timestamp) FROM messages WHERE source_id=?", (src_id,)
        ).fetchone()
        db_latest = db_row[0] if db_row else None

        store_latest = _store_latest(jid)

        # No messages anywhere → genuinely dead/quiet group, not our problem
        if not store_latest and not db_latest:
            continue

        def _parse(v):
            ts = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts

        lag_min = None
        if store_latest and not db_latest:
            lag_min = float("inf")  # messages exist but none ingested → broken
        elif store_latest and db_latest:
            lag_min = (_parse(store_latest) - _parse(db_latest)).total_seconds() / 60

        if lag_min is not None and lag_min > PIPELINE_LAG_THRESHOLD_MIN:
            last_alerted_str = alerted.get(src_id, "")
            today = now.date().isoformat()
            if last_alerted_str[:10] != today:
                shown = "never" if db_latest is None else f"{_parse(db_latest).isoformat()}"
                lags.append(f"• {name}: DB {shown} behind store {store_latest}")
                alerted[src_id] = now.isoformat()
        else:
            log.info(f"staleness: {name} pipeline OK ({'quiet' if not store_latest else 'in sync'})")

    if lags:
        msg = ("⚠️ BSC ingestion pipeline lag (" + now.strftime("%Y-%m-%d %H:%M UTC") + ")\n"
               + "\n".join(lags) + "\n\nMessages are reaching the wacli store but NOT bsc-data.db. "
               "Check bsc-data-sync / realtime-ingest logs.")
        alert_dev(msg)
        log.warning(f"Pipeline lag alert: {lags}")

    try:
        STALENESS_ALERT_STATE.write_text(json.dumps(alerted, indent=2))
    except Exception as e:
        log.warning(f"failed to write staleness state: {e}")

def alert_dev(msg):
    try:
        subprocess.run(
            ["wacli", "send", "text", "--chat", DEV_GROUP, "--text", f"[bsc-data-sync] {msg}"],
            capture_output=True, timeout=15
        )
    except Exception:
        pass

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== bsc-data-sync starting ===")
    t_start = time.time()
    ATT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)
    seed_sources(conn)

    errors = []

    # Persistent daemon (wacli-sync-daemon) handles live WhatsApp delivery.
    # bsc-data-sync no longer calls wacli sync --once; it only reads from
    # the wacli local store which the daemon keeps current in real-time.
    wa_sources = [s for s in SOURCES if s["type"] == "whatsapp_group"]
    _check_daemon_health(conn, errors)

    # Fetch each source
    total_new = 0
    for s in SOURCES:
        if not needs_sync(conn, s["id"], s["ttl_min"]):
            log.info(f"  Skipping {s['name']} (within TTL)")
            continue
        try:
            if s["type"] == "whatsapp_group":
                total_new += fetch_whatsapp_group(conn, s)
        except Exception as e:
            err = f"{s['name']}: {e}"
            log.error(f"  Source error: {err}")
            errors.append(err)

    # Fetch Week Ahead newsletter content from shortlinks in messages
    try:
        newsletter_count = fetch_week_ahead_newsletter(conn)
        if newsletter_count:
            log.info(f"  Newsletter: fetched {newsletter_count} new Week Ahead document(s)")
            total_new += newsletter_count
    except Exception as e:
        log.warning(f"  Newsletter fetch error: {e}")

    # Retry attachments deferred while the sync daemon held the store lock
    if not _daemon_alive():
        try:
            _retry_deferred_attachments(conn)
        except Exception as e:
            log.warning(f"  Deferred-attachment retry error: {e}")

    # Weekly retention (run if Sunday)
    if datetime.now(timezone.utc).weekday() == 6:
        run_retention(conn)

    conn.close()

    elapsed = int(time.time() - t_start)
    if errors:
        alert_dev(f"WARN: {len(errors)} source error(s): {'; '.join(errors[:3])}")
        log.warning(f"Completed with {len(errors)} error(s) in {elapsed}s")
    else:
        log.info(f"=== bsc-data-sync done: {total_new} new items in {elapsed}s ===")

if __name__ == "__main__":
    main()
