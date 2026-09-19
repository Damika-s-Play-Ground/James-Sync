#!/usr/bin/env python3
"""bsc-realtime-ingest.py — near-real-time ingest of WhatsApp groups into bsc-data.db.

Runs ONE pass per invocation (every minute via Hermes cron job
"James BSC Realtime Ingest"). Reuses the battle-tested fetch logic from
bsc-data-sync.py (fetch_whatsapp_group, init_db, seed_sources,
fetch_week_ahead_newsletter) so the batch layer and this layer can never
drift in parsing/extraction behavior.

Design notes:
  * Reads come from the LOCAL wacli store (populated real-time by the
    `wacli sync --follow` daemon), so each pass is ~200-300ms when idle.
  * No DEV alerts, no staleness checks here — alerting stays in the
    45-min batch sync (bsc-data-sync.py), which remains as safety net,
    attachment retry path, and backfill when the daemon is down.
  * Newsletter scan is throttled: full scan only when new messages were
    ingested this pass, or at most once per hour otherwise (avoids
    hammering Jina Reader every 60s).
  * Quiet by design: logs only new items, errors, and an hourly
    heartbeat, to keep the log file small at 1440 runs/day.

Exit code is always 0 — the scheduler must never see this fail loudly;
errors are logged for the next investigation instead.
"""
import importlib.util
import logging
import pathlib
import sqlite3
import sys
import time
from datetime import datetime, timezone

WS = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
SCRIPTS = WS / "scripts"
LOG_PATH = WS / "logs" / "cron" / "BSC_Realtime_Ingest.log"
NEWSLETTER_SCAN_MIN_INTERVAL = 3600  # seconds between scans without new messages

# ── Import bsc-data-sync.py (hyphenated filename → importlib) ────────────────
spec = importlib.util.spec_from_file_location("bsc_data_sync", str(SCRIPTS / "bsc-data-sync.py"))
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)

# The imported module configured the ROOT logger with a FileHandler pointing
# at BSC_Data_Sync.log. Replace it so ingest activity lands in its own log.
_root = logging.getLogger()
for _h in list(_root.handlers):
    _root.removeHandler(_h)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH)],
)
log = logging.getLogger("realtime-ingest")


def main():
    t0 = time.time()
    conn = sqlite3.connect(str(bsc.DB_PATH), timeout=30)
    conn.execute("PRAGMA busy_timeout=5000")
    bsc.init_db(conn)
    bsc.seed_sources(conn)

    total_new = 0
    errors = []
    for s in bsc.SOURCES:
        if s["type"] != "whatsapp_group":
            continue
        try:
            total_new += bsc.fetch_whatsapp_group(conn, s)
        except Exception as e:
            errors.append(f"{s['name']}: {e}")
            log.error(f"source error {s['name']}: {e}")

    # Newsletter scan (throttled: fresh content or hourly; failures back off 5 min)
    if total_new > 0 or _newsletter_scan_due():
        try:
            n = bsc.fetch_week_ahead_newsletter(conn)
            if n:
                log.info(f"newsletter: fetched {n} new Week Ahead document(s)")
            _mark_newsletter_scanned(failed=False)
        except Exception as e:
            log.warning(f"newsletter scan error: {e}")
            _mark_newsletter_scanned(failed=True)  # short backoff, retry soon

    conn.close()

    elapsed_ms = int((time.time() - t0) * 1000)
    if errors:
        log.warning(f"pass done with {len(errors)} error(s) in {elapsed_ms}ms: {'; '.join(errors[:3])}")
    elif total_new > 0:
        log.info(f"pass done: {total_new} new item(s) in {elapsed_ms}ms")
    else:
        _hourly_heartbeat(elapsed_ms)


_last_heartbeat = {"ts": 0.0}
_newsletter_state = WS / "state" / "realtime-newsletter-scan.json"


def _newsletter_scan_due() -> bool:
    try:
        import json
        data = json.loads(_newsletter_state.read_text())
        interval = 300 if data.get("last_fail") else NEWSLETTER_SCAN_MIN_INTERVAL
        return time.time() - data.get("last_scan", 0) >= interval
    except Exception:
        return True


def _mark_newsletter_scanned(failed: bool = False):
    try:
        import json
        _newsletter_state.write_text(json.dumps(
            {"last_scan": time.time(), "last_fail": failed}))
    except Exception:
        pass


def _hourly_heartbeat(elapsed_ms: int):
    now = time.time()
    if now - _last_heartbeat["ts"] >= 3600:
        _last_heartbeat["ts"] = now
        log.info(f"heartbeat: idle, pass ok in {elapsed_ms}ms")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error(f"FATAL pass error: {e}")
    sys.exit(0)
