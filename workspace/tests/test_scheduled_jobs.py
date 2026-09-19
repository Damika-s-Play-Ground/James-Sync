#!/usr/bin/env python3
"""Tests for scheduled BSC summary/reminder builders.

dev mode sends a preview to the DEV WhatsApp group via sj.send_dev_preview —
these tests mock that function so no real WhatsApp traffic occurs.
"""
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

WS = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
sys.path.insert(0, str(WS / "scripts"))
import bsc_scheduled_jobs as sj


def make_db(path: pathlib.Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE sources (id TEXT PRIMARY KEY, name TEXT, audience TEXT, active INTEGER DEFAULT 1);
    CREATE TABLE messages (
      id TEXT PRIMARY KEY, source_id TEXT, sender_jid TEXT, sender_name TEXT,
      timestamp TEXT, text TEXT, has_attachment INTEGER, raw_json TEXT, ingested_at TEXT
    );
    CREATE TABLE attachments (
      message_id TEXT PRIMARY KEY, extracted_text TEXT, extracted_links TEXT,
      extraction_status TEXT, file_name TEXT
    );
    CREATE TABLE documents (
      id TEXT PRIMARY KEY, source_id TEXT, issue_date TEXT, content_hash TEXT,
      raw_text TEXT, parsed_json TEXT, fetched_at TEXT, is_current INTEGER
    );
    CREATE TABLE auto_send_sent_log (
      id TEXT PRIMARY KEY,
      candidate_ids TEXT NOT NULL,
      source_message_ids TEXT NOT NULL,
      target_jid TEXT NOT NULL,
      send_mode TEXT NOT NULL,
      event_type TEXT,
      semantic_key TEXT NOT NULL,
      sent_hash TEXT NOT NULL,
      message_text TEXT NOT NULL,
      safe_send_payload TEXT NOT NULL,
      wacli_result TEXT,
      sent_at TEXT NOT NULL
    );
    """)
    conn.execute("INSERT INTO sources VALUES (?,?,?,?)", ("wa:junior", "BSC Junior School", "junior_school", 1))
    newsletter = """
Title: Junior School Week Ahead
Monday 24 August: Junior School gates open at 7am; Year 4 students should arrive by 7:20am.
Tuesday 25 August: Junior School students should bring PE kit for practice.
Wednesday 26 August: Year 4 parents should submit the permission form.
"""
    conn.execute(
        "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
        ("newsletter:test", "newsletter:week_ahead", "2026-08-23", "hash", newsletter, None, "2026-08-23T04:30:00+00:00", 1),
    )
    conn.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "msg-1", "wa:junior", "admin@s.whatsapp.net", "BSC Admin",
            "2026-08-23T04:40:00+00:00",
            "Dear Year 4 parents, Monday 24 August: please arrive by 7:20am.",
            0, "{}", "2026-08-23T04:41:00+00:00",
        ),
    )
    conn.commit(); conn.close()


class ScheduledJobsTests(unittest.TestCase):
    def run_job(self, job: str, mode: str) -> tuple[dict, pathlib.Path]:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        db = root / "bsc-data.db"
        make_db(db)
        sj.DRAFTS_DIR = root / "drafts"
        sj.AUDIT_LOG = sj.DRAFTS_DIR / "audit.log"
        ref = sj.parse_iso("2026-08-23T15:00:00+05:30").astimezone(sj.COLOMBO)
        return sj.write_artifact(job, mode, db, ref), root

    # ---------- dry_run: artifacts only, zero sends ----------
    def test_dry_run_never_sends(self):
        with mock.patch.object(sj, "send_dev_preview") as fake_send:
            result, root = self.run_job("daily-3pm-reminder", "dry_run")
            fake_send.assert_not_called()
        self.assertEqual(result["decision"], "DRAFT")
        self.assertEqual(result["sent_dev"], 0)
        self.assertEqual(result["sent_public"], 0)
        payload = json.loads((root / "drafts" / "2026-08-24-3pm-reminder.json").read_text())
        self.assertEqual(payload["status"], "DRY_RUN")

    def test_dry_run_hold_never_sends(self):
        empty_db_dir = tempfile.TemporaryDirectory()
        self.addCleanup(empty_db_dir.cleanup)
        root = pathlib.Path(empty_db_dir.name)
        db = root / "bsc-data.db"
        make_db(db)
        conn = sqlite3.connect(db)
        conn.execute("UPDATE documents SET raw_text=''")
        conn.execute("DELETE FROM messages")
        conn.commit(); conn.close()
        sj.DRAFTS_DIR = root / "drafts"
        sj.AUDIT_LOG = sj.DRAFTS_DIR / "audit.log"
        ref = sj.parse_iso("2026-08-23T15:00:00+05:30").astimezone(sj.COLOMBO)
        with mock.patch.object(sj, "send_dev_preview") as fake_send:
            result = sj.write_artifact("daily-3pm-reminder", "dry_run", db, ref)
            fake_send.assert_not_called()
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["sent_dev"], 0)

    # ---------- dev: sends preview to DEV only ----------
    def test_dev_mode_sends_preview_to_dev_group(self):
        with mock.patch.object(sj, "send_dev_preview", return_value=1) as fake_send:
            result, root = self.run_job("daily-3pm-reminder", "dev")
            self.assertEqual(fake_send.call_count, 1)
            sent_msg = fake_send.call_args[0][0]
        self.assertEqual(result["decision"], "DRAFT")
        self.assertEqual(result["sent_dev"], 1)
        self.assertEqual(result["sent_public"], 0)
        self.assertIn("NOT SENT TO PARENTS", sent_msg)
        self.assertIn("daily-3pm-reminder", sent_msg)

    def test_dev_mode_hold_notice_sent_to_dev(self):
        empty_db_dir = tempfile.TemporaryDirectory()
        self.addCleanup(empty_db_dir.cleanup)
        root = pathlib.Path(empty_db_dir.name)
        db = root / "bsc-data.db"
        make_db(db)
        conn = sqlite3.connect(db)
        conn.execute("UPDATE documents SET raw_text=''")
        conn.execute("DELETE FROM messages")
        conn.commit(); conn.close()
        sj.DRAFTS_DIR = root / "drafts"
        sj.AUDIT_LOG = sj.DRAFTS_DIR / "audit.log"
        ref = sj.parse_iso("2026-08-23T15:00:00+05:30").astimezone(sj.COLOMBO)
        with mock.patch.object(sj, "send_dev_preview", return_value=1) as fake_send:
            result = sj.write_artifact("daily-3pm-reminder", "dev", db, ref)
            self.assertEqual(fake_send.call_count, 1)
            hold_msg = fake_send.call_args[0][0]
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["sent_dev"], 1)
        self.assertIn("SCHEDULED JOB HOLD", hold_msg)

    def test_dev_send_failure_reported_not_raised(self):
        with mock.patch.object(sj, "send_dev_preview", return_value=0) as fake_send:
            result, _root = self.run_job("daily-6am-summary", "dev")
            fake_send.assert_called_once()
        self.assertEqual(result["sent_dev"], 0)
        self.assertEqual(result["sent_public"], 0)

    def test_weekly_summary_dev_send(self):
        with mock.patch.object(sj, "send_dev_preview", return_value=1) as fake_send:
            result, root = self.run_job("weekly-sunday-summary", "dev")
            self.assertEqual(fake_send.call_count, 1)
        self.assertEqual(result["decision"], "DRAFT")
        self.assertEqual(result["sent_dev"], 1)
        self.assertEqual(result["sent_public"], 0)
        payload = json.loads((root / "drafts" / "2026-08-24-weekly-summary.json").read_text())
        self.assertIn("2026-08-24", payload["target_dates"])
        self.assertIn("2026-08-30", payload["target_dates"])

    # ---------- public: gated, Year-4-only, via safe-send ----------
    def test_public_without_flag_never_sends(self):
        env = {k: v for k, v in os.environ.items() if k != "BSC_ALLOW_PUBLIC_AUTOSEND"}
        with mock.patch.object(sj, "send_dev_preview", return_value=1) as fake_send, \
             mock.patch.object(sj, "_run_safe_send") as fake_ss, \
             mock.patch.dict(os.environ, env, clear=True):
            result, root = self.run_job("daily-3pm-reminder", "public")
            fake_ss.assert_not_called()
            self.assertEqual(fake_send.call_count, 1)  # DEV transparency copy only
        self.assertEqual(result["sent_public"], 0)
        audit = (root / "drafts" / "audit.log").read_text()
        self.assertIn("PUBLIC_DISABLED", audit)

    def test_public_sends_year4_only_items_via_safe_send(self):
        extra_db_dir = tempfile.TemporaryDirectory()
        self.addCleanup(extra_db_dir.cleanup)
        root = pathlib.Path(extra_db_dir.name)
        db = root / "bsc-data.db"
        make_db(db)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            ("msg-mixed", "wa:junior", "admin@s.whatsapp.net", "BSC Admin",
             "2026-08-23T12:00:00+00:00",
             "Monday 24 August: Years 4-6 BYOL configuration session. Year 4 students must bring their laptop.",
             0, "{}", "2026-08-23T12:01:00+00:00"),
        )
        conn.commit(); conn.close()
        sj.DRAFTS_DIR = root / "drafts"
        sj.AUDIT_LOG = sj.DRAFTS_DIR / "audit.log"
        ref = sj.parse_iso("2026-08-23T15:00:00+05:30").astimezone(sj.COLOMBO)
        sent_payloads = []

        def fake_safe_send(path):
            sent_payloads.append(json.loads(pathlib.Path(path).read_text()))
            return 0, "DRY-RUN OK"

        env = dict(os.environ, BSC_ALLOW_PUBLIC_AUTOSEND="1")
        with mock.patch.object(sj, "_run_safe_send", side_effect=fake_safe_send), \
             mock.patch.object(sj, "send_dev_preview", return_value=1) as fake_send, \
             mock.patch.dict(os.environ, env, clear=True):
            result = sj.write_artifact("daily-3pm-reminder", "public", db, ref)

        self.assertEqual(result["sent_public"], 1)
        self.assertGreaterEqual(result["mixed_held"], 1)
        pub = sent_payloads[0]
        self.assertNotIn("BYOL", pub["final_message"])          # mixed item excluded from parents
        self.assertIn("gates open at 7am", pub["final_message"])  # Y4-only item included
        dev_msg = fake_send.call_args[0][0]
        self.assertIn("SENT to School Assistant (Testing)", dev_msg)
        self.assertIn("held from parents", dev_msg)
        audit = (root / "drafts" / "audit.log").read_text()
        self.assertIn("PUBLIC_SENT", audit)

    def test_dedupe_skips_items_already_sent_to_parents(self):
        extra_db_dir = tempfile.TemporaryDirectory()
        self.addCleanup(extra_db_dir.cleanup)
        root = pathlib.Path(extra_db_dir.name)
        db = root / "bsc-data.db"
        make_db(db)
        conn = sqlite3.connect(db)
        sent_text = "Reminder: Junior School gates open at 7am and Year 4 students should arrive by 7:20am."
        conn.execute(
            """INSERT INTO auto_send_sent_log
               (id, candidate_ids, source_message_ids, target_jid, send_mode, event_type,
                semantic_key, sent_hash, message_text, safe_send_payload, wacli_result, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("legacy-test", "", "", sj.PUBLIC, "legacy_public", "legacy_public", "legacy-test", "hash", sent_text, "{}", "", "2026-08-23T00:00:00+00:00"),
        )
        conn.commit(); conn.close()
        sj.DRAFTS_DIR = root / "drafts"
        sj.AUDIT_LOG = sj.DRAFTS_DIR / "audit.log"
        ref = sj.parse_iso("2026-08-23T15:00:00+05:30").astimezone(sj.COLOMBO)
        with mock.patch.object(sj, "send_dev_preview"):
            result = sj.write_artifact("daily-3pm-reminder", "dry_run", db, ref)
        payload = json.loads((root / "drafts" / "2026-08-24-3pm-reminder.json").read_text())
        self.assertNotIn("gates open at 7am", payload["final_message"])   # covered by prior send
        self.assertIn("arrive by 7:20am", payload["final_message"])       # fresh item kept
        self.assertEqual(result["decision"], "DRAFT")
    def test_parent_message_format_is_concise_and_human_readable(self):
        item = sj.Item(
            text=(
                "Friday 14th August 2026 Dear Parents, Auditions for our Dance, Drama and Choir Squads "
                "will be held during the first week of the new academic year. This is a fantastic opportunity "
                "for children passionate about the performing arts to join our vibrant, creative squads. "
                "Important Notes: Children already in the Dance, Drama, or Choir Squads do not need to audition again."
            ),
            source="BSC Junior School",
            source_message_id="msg-audition",
            source_excerpt="audition excerpt",
            event_date="2026-08-25",
        )
        ref = sj.parse_iso("2026-08-24T15:00:00+05:30").astimezone(sj.COLOMBO)

        msg = sj.build_message("daily-3pm-reminder", "tomorrow", [item], ref)

        self.assertIn("Tuesday 25 August", msg)
        self.assertIn("Dance, Drama and Choir Squad auditions", msg)
        self.assertNotIn("This is a fantastic opportunity", msg)
        self.assertNotIn("2026-08-25", msg)
        self.assertNotIn("alread...", msg)
        self.assertNotIn("carried...", msg)

        full = sj.Item(
            text=(
                "Friday 14th August 2026\n\nDear Parents,\n\n"
                "Auditions for our Dance, Drama and Choir Squads will be held during the first week of the new academic year. "
                "This is a fantastic opportunity for children passionate about the performing arts to join our vibrant, creative squads.\n\n"
                "*Important Notes:*\n"
                "Children already in the Dance, Drama, or Choir Squads do not need to re-audition. "
                "Their places will be carried forward into the new academic year. "
                "We do need you to reconfirm via email to Ms Sarah that your child still wants a place in the squad.\n\n"
                "*Audition Information:*\n"
                "Choir Squad: *Friday 28th August 1.45 - 3.30pm*\n"
                "Dance Squad: *Thursday 3rd September 1.45pm - 3.30pm*\n"
                "Drama Squad: *Tuesday 25th  August 1.45pm - 3.30pm*\n\n"
                "*What to prepare:*\n"
                "Dance Squad: A short dance (1–2 minutes)\n"
                "Drama Squad: A short monologue (up to 1 minute)\n"
                "Choir Squad: A short song (1–2 minutes, any style)"
            ),
            source="BSC Junior School",
            source_message_id="msg-audition-full",
            source_excerpt="audition excerpt",
            event_date="2026-08-28",
        )
        full_msg = sj.build_message(
            "daily-3pm-reminder",
            "tomorrow",
            [full],
            sj.parse_iso("2026-08-27T15:00:00+05:30").astimezone(sj.COLOMBO),
        )
        self.assertIn("Friday 28 August", full_msg)
        self.assertIn("Choir Squad audition — Friday 28th August 1.45 - 3.30pm", full_msg)
        self.assertIn("Email Ms Sarah to reconfirm", full_msg)
        self.assertIn("short song", full_msg)
        self.assertIn("\n\n", full_msg)
        self.assertNotIn("...", full_msg)
        self.assertNotIn("Dance Squad: Thursday 3rd September", full_msg)
        self.assertNotIn("• Auditions for Dance", full_msg)

    def test_public_send_is_recorded_immediately_for_dedupe(self):
        extra_db_dir = tempfile.TemporaryDirectory()
        self.addCleanup(extra_db_dir.cleanup)
        root = pathlib.Path(extra_db_dir.name)
        db = root / "bsc-data.db"
        make_db(db)
        sj.DRAFTS_DIR = root / "drafts"
        sj.AUDIT_LOG = sj.DRAFTS_DIR / "audit.log"
        ref = sj.parse_iso("2026-08-23T15:00:00+05:30").astimezone(sj.COLOMBO)

        def fake_safe_send(path):
            return 0, "MSG123"

        env = dict(os.environ, BSC_ALLOW_PUBLIC_AUTOSEND="1")
        with mock.patch.object(sj, "_run_safe_send", side_effect=fake_safe_send), \
             mock.patch.object(sj, "send_dev_preview", return_value=1), \
             mock.patch.dict(os.environ, env, clear=True):
            result = sj.write_artifact("daily-3pm-reminder", "public", db, ref)

        self.assertEqual(result["sent_public"], 1)
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT send_mode, target_jid, message_text, wacli_result FROM auto_send_sent_log"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "public")
        self.assertEqual(rows[0][1], sj.PUBLIC)
        self.assertIn("Year 4", rows[0][2])
        self.assertIn("MSG123", rows[0][3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
