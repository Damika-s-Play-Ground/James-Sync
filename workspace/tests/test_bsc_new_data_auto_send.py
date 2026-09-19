#!/usr/bin/env python3
"""TDD tests for the new bsc-new-data-auto-send candidate/gate engine.

These tests target the pure-Python gate/candidate functions. They do NOT
call wacli or send anything. Run:

    cd /opt/data/james-bsc-live-clean/data/.ocplatform/workspace
    python3 -m pytest tests/test_bsc_new_data_auto_send.py -v
"""
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

WS = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
SAFE_SEND = WS / "scripts" / "bsc-agent-safe-send.py"
PUBLIC = "REDACTED_JID"

# Import the module under test
sys.path.insert(0, str(WS / "scripts"))
import bsc_new_data_auto_send as m


def _verified_item(idx, text, year="Year 4",
                   source="newsletter:week_ahead",
                   source_id="newsletter:week_ahead:doc-x"):
    return {
        "bullet_index": idx,
        "text": text,
        "source": source,
        "source_message_id": source_id,
        "source_excerpt": f"{text} (from source)",
        "applies_to_year_groups": [year],
        "target_audience_detected": year,
        "verification_status": "verified",
        "parent_safe": True,
        "rejection_reason": None,
    }


def _base_payload(message, items):
    return {
        "decision": "SEND",
        "audience": "Year 4",
        "target_group": PUBLIC,
        "final_message": message,
        "evidence": ["test evidence"],
        "risk_flags": [],
        "items": items,
    }


def run_safe_send(payload):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        path = f.name
    try:
        p = subprocess.run(
            [sys.executable, str(SAFE_SEND), "--input", path],
            text=True, capture_output=True, timeout=30,
        )
        return p.returncode, p.stdout, p.stderr
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


class RelevanceGateTests(unittest.TestCase):
    def test_thanks_rejected(self):
        r = m.classify_relevance("Thanks for the update.")
        self.assertFalse(r["pass"])
        self.assertEqual(r["event_type"], "irrelevant")

    def test_reaction_rejected(self):
        r = m.classify_relevance("Noted 👍")
        self.assertFalse(r["pass"])

    def test_school_reopen_passes(self):
        r = m.classify_relevance("School reopens on Monday 24 August.")
        self.assertTrue(r["pass"])

    def test_question_rejected(self):
        r = m.classify_relevance("Do we need to bring laptops tomorrow?")
        self.assertFalse(r["pass"])
        self.assertEqual(r["event_type"], "question_or_rumour")

    def test_authoritative_notice_with_question_heading_can_pass_relevance(self):
        text = (
            "Dear Year 4 Parents, We will be conducting the BYOL configuration session. "
            "Who needs to bring their laptop? Newly enrolled students. "
            "Drop-off: 24 August. Windows laptops: Parents must pre-configure the laptop."
        )
        r = m.classify_relevance(text, authoritative_notice=True)
        self.assertTrue(r["pass"])
        self.assertEqual(r["event_type"], "bring_wear_tomorrow")

    def test_untrusted_question_heading_still_rejected(self):
        text = "Who needs to bring their laptop? Newly enrolled students should bring it tomorrow."
        r = m.classify_relevance(text, authoritative_notice=False)
        self.assertFalse(r["pass"])
        self.assertEqual(r["event_type"], "question_or_rumour")

    def test_system_sync_marker_rejected(self):
        r = m.classify_relevance("[SYNC GAP — Jun 13–16: messages not received by wacli session]")
        self.assertFalse(r["pass"])
        self.assertEqual(r["event_type"], "system_marker")


class AudienceGateTests(unittest.TestCase):
    def test_year6_only_rejected(self):
        r = m.classify_audience("Year 6 camp payment due Friday.", "year6")
        self.assertFalse(r["pass"])

    def test_year4_passes(self):
        r = m.classify_audience("Year 4 students arrive by 7:25am.", "year4")
        self.assertTrue(r["pass"])

    def test_whole_junior_passes(self):
        r = m.classify_audience("All Junior students arrive by 7:30am.", "junior_school")
        self.assertTrue(r["pass"])

    def test_mixed_year4_year6_held(self):
        r = m.classify_audience("Year 4 and Year 6 students attend.", "junior_school")
        self.assertEqual(r["decision"], "held_mixed_audience")

    def test_mixed_years_4_to_6_held(self):
        r = m.classify_audience("BYOL Configuration – Years 4-6", "year4")
        self.assertEqual(r["decision"], "held_mixed_audience")


class DateGateTests(unittest.TestCase):
    def test_tomorrow_from_reference(self):
        r = m.verify_date_relevance("tomorrow", "2026-08-23T10:00:00+05:30")
        self.assertTrue(r["pass"])
        self.assertEqual(r["event_date"], "2026-08-24")

    def test_historical_message_rejected_as_stale(self):
        # Message from March with "tomorrow" should be rejected as stale when evaluated today
        r = m.verify_date_relevance(
            "deadline tomorrow",
            "2026-03-19T04:38:00+05:30",  # reference_time (message timestamp)
            "2026-08-23T12:00:00+00:00",   # evaluation_time (cron run time)
        )
        self.assertFalse(r["pass"])
        self.assertEqual(r["decision"], "rejected_stale_date")

    def test_old_date_rejected(self):
        r = m.verify_date_relevance("2026-07-01", "2026-08-23T10:00:00+05:30")
        self.assertFalse(r["pass"])

    def test_day_date_mismatch_rejected(self):
        r = m.verify_date_relevance("Friday 24 August", "2026-08-23T10:00:00+05:30")
        self.assertFalse(r["pass"])


class AttachmentGateTests(unittest.TestCase):
    def test_daemon_running_held(self):
        r = m.classify_attachment(1, "daemon_running")
        self.assertEqual(r["decision"], "held_attachment_pending")

    def test_no_attachment_passes(self):
        r = m.classify_attachment(0, None)
        self.assertTrue(r["pass"])


class DedupeGateTests(unittest.TestCase):
    def test_same_exact_rejected(self):
        r = m.is_duplicate("school reopens monday 24 august",
                           "school|2026-08-24|school_reopen|arrive_0725",
                           {"school|2026-08-24|school_reopen|arrive_0725"},
                           {"sha1"})
        self.assertFalse(r["pass"])

    def test_new_semantic_passes(self):
        r = m.is_duplicate("laptop reminder tomorrow",
                           "school|2026-08-24|laptop|bring",
                           {"school|2026-08-24|school_reopen|arrive_0725"},
                           set())
        self.assertTrue(r["pass"])

    def test_legacy_audit_backfill_uses_normalized_exact_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            drafts = root / "drafts"
            drafts.mkdir()
            msg = "Year 4 reminder: School reopens tomorrow, Monday 24 August.\n\n• Arrive by 7:25am"
            raw_sha = __import__('hashlib').sha256(msg.encode()).hexdigest()
            (drafts / "legacy-draft.json").write_text(json.dumps({"final_message": msg}))
            audit = root / "audit.log"
            audit.write_text(json.dumps({
                "ts": "2026-08-23T11:10:01+00:00",
                "draft_id": "legacy-draft",
                "action": "SENT",
                "sha": raw_sha,
                "msg_id": "3EBOLD",
                "target": m.PUBLIC,
                "chars": len(msg),
            }) + "\n")
            db = root / "test.db"
            conn = sqlite3.connect(db)
            changed = m.backfill_legacy_public_sends(conn, audit, drafts)
            conn.commit()
            self.assertEqual(changed, 1)
            row = conn.execute("select id, send_mode, sent_hash, message_text from auto_send_sent_log").fetchone()
            conn.close()
            self.assertEqual(row[0], f"legacy:{raw_sha[:16]}")
            self.assertEqual(row[1], "public")
            self.assertEqual(row[2], m.exact_hash(msg))
            self.assertNotEqual(row[2], raw_sha)
            self.assertEqual(row[3], msg)

    def test_legacy_backfill_hash_blocks_runtime_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            drafts = root / "drafts"
            drafts.mkdir()
            msg = "Year 4 reminder: School reopens tomorrow, Monday 24 August.\n\n• Arrive by 7:25am"
            raw_sha = __import__('hashlib').sha256(msg.encode()).hexdigest()
            (drafts / "legacy-draft.json").write_text(json.dumps({"final_message": msg}))
            audit = root / "audit.log"
            audit.write_text(json.dumps({
                "ts": "2026-08-23T11:10:01+00:00",
                "draft_id": "legacy-draft",
                "action": "SENT",
                "sha": raw_sha,
                "msg_id": "3EBOLD",
                "target": m.PUBLIC,
            }) + "\n")
            conn = sqlite3.connect(root / "test.db")
            m.backfill_legacy_public_sends(conn, audit, drafts)
            sent_semantic, sent_hashes = m.load_sent_sets(conn, ("public",))
            conn.close()
            duplicate = m.is_duplicate(msg, "different-semantic-key", sent_semantic, sent_hashes)
            self.assertFalse(duplicate["pass"])
            self.assertEqual(duplicate["reason"], "exact hash already sent")


class SafeSendIntegrationTests(unittest.TestCase):
    def test_generated_payload_passes_dry_run(self):
        msg = "Year 4 reminder: School reopens tomorrow, Monday 24 August.\n\n• Arrive by 7:25am\n• Wear formal uniform"
        items = [_verified_item(0, "School reopens tomorrow, Monday 24 August.\n• Arrive by 7:25am\n• Wear formal uniform")]
        payload = _base_payload(msg, items)
        rc, out, err = run_safe_send(payload)
        self.assertEqual(rc, 0, f"expected dry-run OK, got rc={rc}\nstderr={err}")
        self.assertIn("DRY-RUN OK", out)

    def test_year5_leakage_fails(self):
        msg = "Year 5 camp payment due Friday."
        items = [_verified_item(0, "Year 5 camp", year="Year 5")]
        rc, _, err = run_safe_send(_base_payload(msg, items))
        self.assertNotEqual(rc, 0)
        self.assertTrue(
            "Senior school content" in err or "applies_to_year_groups" in err,
            f"expected Year 5 leakage to be blocked, stderr={err!r}",
        )


class DevPreviewTests(unittest.TestCase):
    def _make_db(self, text=None):
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        path = pathlib.Path(tmp.name)
        conn = sqlite3.connect(path)
        conn.executescript('''
        CREATE TABLE sources (id TEXT PRIMARY KEY, name TEXT, audience TEXT);
        CREATE TABLE messages (
          id TEXT PRIMARY KEY, source_id TEXT, sender_jid TEXT, sender_name TEXT,
          timestamp TEXT, text TEXT, has_attachment INTEGER, raw_json TEXT, ingested_at TEXT
        );
        CREATE TABLE attachments (message_id TEXT PRIMARY KEY, extracted_text TEXT, extraction_status TEXT);
        ''')
        conn.execute("INSERT INTO sources VALUES (?,?,?)", ('src-year4', 'BSC Yr4 Parents 2026/27', 'year4'))
        conn.execute("""
            INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            'msg-dev-1', 'src-year4', 'admin@s.whatsapp.net', 'Amrit Kamalaneson',
            m.now_utc(), text or 'Year 4 students must bring PE kit tomorrow. Please arrive by 7:25am.',
            0, '{}', m.now_utc(),
        ))
        conn.commit(); conn.close()
        return path

    def test_dev_preview_message_is_clearly_not_parent_sent(self):
        candidate = {
            'id': 'auto:msg-dev-1', 'source_name': 'BSC Yr4 Parents 2026/27',
            'source_message_id': 'msg-dev-1', 'event_type': 'bring_wear_tomorrow',
            'event_date': '2026-08-24', 'draft_text': 'Year 4 reminder: bring PE kit tomorrow.',
            'gate_json': json.dumps({'date': {'reason': 'verified tomorrow'}}),
        }
        msg = m.build_dev_preview_message(candidate, m.build_safe_send_payload(candidate))
        self.assertIn('AUTO-SEND DEV PREVIEW', msg)
        self.assertIn('NOT SENT TO PARENTS', msg)
        self.assertIn('BSC Yr4 Parents 2026/27', msg)
        self.assertIn('Year 4 reminder: bring PE kit tomorrow.', msg)

    def test_dev_mode_sends_preview_to_dev_only_and_records_log(self):
        db = self._make_db()
        calls = []
        class Result:
            returncode = 0
            stdout = 'sent message (id dev-preview-test)'
            stderr = ''
        def fake_runner(cmd, text=True, capture_output=True, timeout=60):
            calls.append(cmd)
            return Result()
        try:
            summary = m.run(db, limit=10, mode='dev', send_runner=fake_runner)
            self.assertEqual(summary['sent_dev'], 1)
            self.assertEqual(summary['sent_public'], 0)
            self.assertEqual(calls, [['wacli', 'send', 'text', '--to', m.DEV, '--message', mock.ANY]])
            self.assertIn('NOT SENT TO PARENTS', calls[0][-1])
            conn = sqlite3.connect(db)
            rows = conn.execute("select send_mode,target_jid,message_text from auto_send_sent_log where send_mode='dev'").fetchall()
            conn.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], 'dev')
            self.assertEqual(rows[0][1], m.DEV)
            self.assertIn('AUTO-SEND DEV PREVIEW', rows[0][2])
        finally:
            db.unlink(missing_ok=True)

    def test_dev_mode_dedupes_preview_spam(self):
        db = self._make_db()
        calls = []
        class Result:
            returncode = 0
            stdout = 'sent message (id dev-preview-test)'
            stderr = ''
        def fake_runner(cmd, text=True, capture_output=True, timeout=60):
            calls.append(cmd)
            return Result()
        try:
            first = m.run(db, limit=10, mode='dev', send_runner=fake_runner)
            conn = sqlite3.connect(db)
            conn.execute('delete from auto_send_processed_messages')
            conn.commit(); conn.close()
            second = m.run(db, limit=10, mode='dev', send_runner=fake_runner)
            self.assertEqual(first['sent_dev'], 1)
            self.assertEqual(second['sent_dev'], 0)
            self.assertEqual(len(calls), 1)
        finally:
            db.unlink(missing_ok=True)


class CircuitBreakerTests(unittest.TestCase):
    def test_public_requires_explicit_flag(self):
        self.assertFalse(m.public_allowed("public", "school_reopen", False))

    def test_public_with_flag_passes(self):
        self.assertTrue(m.public_allowed("public", "school_reopen", True))

    def test_public_category_not_allowlisted(self):
        self.assertFalse(m.public_allowed("public", "laptop", True))

    def test_daily_limit_blocks(self):
        self.assertFalse(m.daily_limit_reached(4, 4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
