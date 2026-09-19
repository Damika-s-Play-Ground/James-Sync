#!/usr/bin/env python3
"""
bsc-data-client.py — Query helper for all LLM preview jobs.
Import this instead of running wacli fetches inline.
"""
import sqlite3, json, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/bsc-data.db")

class BSCDataClient:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"bsc-data.db not found at {self.db_path}. Run bsc-data-sync.py first."
            )
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")

    def is_cache_fresh(self, max_age_minutes=120):
        """Returns True if at least one successful sync within max_age_minutes."""
        row = self._conn.execute("""
            SELECT synced_at FROM sync_log
            WHERE status='ok'
            ORDER BY synced_at DESC LIMIT 1
        """).fetchone()
        if not row:
            return False
        last = datetime.fromisoformat(row["synced_at"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - last).total_seconds() / 60
        return age_min <= max_age_minutes

    def last_sync_age_minutes(self):
        """Returns minutes since last successful sync, or None."""
        row = self._conn.execute("""
            SELECT synced_at FROM sync_log WHERE status='ok'
            ORDER BY synced_at DESC LIMIT 1
        """).fetchone()
        if not row:
            return None
        last = datetime.fromisoformat(row["synced_at"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() / 60

    def get_new_message_count(self, since_iso):
        """Count messages ingested after since_iso. Use for urgent-slot change gate."""
        row = self._conn.execute("""
            SELECT COUNT(*) as cnt FROM messages
            WHERE timestamp > ? AND source_id LIKE 'wa:%'
        """, (since_iso,)).fetchone()
        return row["cnt"] if row else 0

    def get_recent_messages(self, hours=72, audience=None):
        """
        Returns list of dicts: message + joined attachment data.
        audience: 'year3', 'junior_school', 'sport_ecas', 'parent_community', or None (all).
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        query = """
            SELECT m.id, m.source_id, m.sender_jid, m.sender_name,
                   m.timestamp, m.text, m.has_attachment,
                   s.name as group_name, s.audience,
                   a.extracted_text, a.extracted_links,
                   a.extraction_status, a.file_name
            FROM messages m
            JOIN sources s ON m.source_id = s.id
            LEFT JOIN attachments a ON a.message_id = m.id
            WHERE m.timestamp > ? AND s.active = 1
        """
        params = [cutoff]
        if audience:
            query += " AND (s.audience = ? OR s.audience = 'all')"
            params.append(audience)
        query += " ORDER BY m.timestamp DESC"

        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_current_newsletter(self):
        """Returns the latest newsletter/Week Ahead document, or None."""
        row = self._conn.execute("""
            SELECT id, source_id, issue_date, raw_text, parsed_json, fetched_at
            FROM documents WHERE is_current=1
            ORDER BY fetched_at DESC LIMIT 1
        """).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("parsed_json"):
            try:
                d["parsed"] = json.loads(d["parsed_json"])
            except Exception:
                pass
        return d

    def search(self, query, limit=20):
        """Full-text search across messages + attachment text."""
        rows = self._conn.execute("""
            SELECT f.message_id, f.source_id, f.timestamp, f.text, f.attachment_text
            FROM fts_content f
            WHERE fts_content MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_sync_status(self):
        """Returns recent sync log entries per source."""
        rows = self._conn.execute("""
            SELECT sl.source_id, s.name, sl.synced_at, sl.new_count, sl.status, sl.error
            FROM sync_log sl
            JOIN sources s ON sl.source_id = s.id
            WHERE sl.id IN (
                SELECT MAX(id) FROM sync_log GROUP BY source_id
            )
            ORDER BY sl.synced_at DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()

