#!/usr/bin/env python3
"""Regression tests for the 2026-06-14 Year-4 verification gate.

Targets:
    bsc-agent-safe-send.py — per-item items[] gate + KS-without-Y4 wording guard
    bsc-agent-draft.py     — items[] missing/unverified triggers HOLD

These tests build payload JSON files in a tmp dir and invoke the scripts as
subprocesses. They do NOT call wacli (no --send for safe-send tests; no
cmd_send for draft tests where it would invoke wacli).

Run:
    cd /opt/data/james-bsc-live-clean/data/.ocplatform/workspace
    python3 -m pytest tests/test_bsc_verification_gate.py -v
or:
    cd /opt/data/james-bsc-live-clean/data/.ocplatform/workspace && python3 tests/test_bsc_verification_gate.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

WS = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
SAFE_SEND = WS / "scripts" / "bsc-agent-safe-send.py"
PUBLIC = "REDACTED_JID"


def _verified_item(idx, text, year="Year 4", source="newsletter:week_ahead", source_id="newsletter:week_ahead:doc-x"):
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


def _ambiguous_item(idx, text):
    return {
        "bullet_index": idx,
        "text": text,
        "source": "newsletter:week_ahead",
        "source_message_id": "newsletter:week_ahead:doc-x",
        "source_excerpt": f"{text} (from source)",
        "applies_to_year_groups": ["Key Stage 2"],
        "target_audience_detected": "ambiguous",
        "verification_status": "ambiguous",
        "parent_safe": False,
        "rejection_reason": "Year qualifier unclear in source",
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
    """Invoke safe-send in dry-run mode (no --send). Return (rc, stdout, stderr)."""
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


class SafeSendGateTests(unittest.TestCase):

    def test_book_look_y5_only_rejected(self):
        """The actual 2026-06-14 Book Look bullet should be blocked.

        Build the payload as if the agent (somehow) marked the item verified
        but the bullet wording in final_message still has "Key Stage 2" without
        a Year-4 marker. The wording guard must catch it.
        """
        bullet = "📚 *Book Look (Key Stage 2)* — 12:00–1:00 pm."
        msg = "*BSC Year 4 Weekly Digest*\n\n*📌 Tuesday 17 June*\n• " + bullet
        # Even with a "verified" item record, the wording-level guard fires
        items = [_verified_item(0, bullet, year="Year 4")]
        rc, out, err = run_safe_send(_base_payload(msg, items))
        self.assertNotEqual(rc, 0, f"expected non-zero, got rc={rc}\nstdout={out}\nstderr={err}")
        self.assertIn("KS1/KS2/whole-Junior wording without explicit Year-4 marker", err)

    def test_ks2_bullet_with_y4_marker_passes_wording(self):
        """A KS2 bullet that ALSO names Year 4 in the same line should pass
        the wording guard (and the verified item carries the structural OK)."""
        bullet = "📚 *Book Look (Key Stage 2 — Year 4 group)* — 12:00–1:00 pm."
        msg = "*BSC Year 4 Weekly Digest*\n\n*📌 Tuesday 17 June*\n• " + bullet
        items = [_verified_item(0, bullet)]
        rc, out, err = run_safe_send(_base_payload(msg, items))
        self.assertEqual(rc, 0, f"expected dry-run OK, got rc={rc}\nstderr={err}")
        self.assertIn("DRY-RUN OK", out)

    def test_ambiguous_item_blocks_send(self):
        # Bullet wording stays neutral so the wording guard doesn't fire first;
        # we want the item-level ambiguous check to be the one that blocks.
        bullet = "• Some Junior School event."
        msg = "*BSC Year 4 Weekly Digest*\n\n*📌 Tuesday*\n" + bullet
        items = [_ambiguous_item(0, "Some Junior School event")]
        rc, _, err = run_safe_send(_base_payload(msg, items))
        self.assertNotEqual(rc, 0)
        self.assertIn("not verified", err)

    def test_items_array_missing_blocks_send(self):
        msg = "*BSC Year 4 Weekly Digest*\n\n• Verified-looking bullet."
        payload = _base_payload(msg, [])
        del payload["items"]
        rc, _, err = run_safe_send(payload)
        self.assertNotEqual(rc, 0)
        self.assertIn("items[] is required", err)

    def test_items_array_empty_blocks_send(self):
        msg = "*BSC Year 4 Weekly Digest*\n\n• Verified-looking bullet."
        rc, _, err = run_safe_send(_base_payload(msg, []))
        self.assertNotEqual(rc, 0)
        self.assertIn("items[] is required", err)

    def test_item_with_year5_only_audience_blocked(self):
        """If the item itself says applies_to_year_groups=['Year 5'], block."""
        bullet = "• Some Year-5-only event."
        msg = "*BSC Year 4 Weekly Digest*\n\n" + bullet
        bad_item = _verified_item(0, "Some event", year="Year 5")
        rc, _, err = run_safe_send(_base_payload(msg, [bad_item]))
        self.assertNotEqual(rc, 0)
        # The audience check fires before the wording check
        self.assertIn("applies_to_year_groups", err)
        self.assertIn("Year 4", err)

    def test_verified_year4_passes(self):
        bullet = "• ☕ *Year 4 — Parent Collective meeting* — 7:30 am."
        msg = "*BSC Year 4 Weekly Digest*\n\n*📌 Monday 15 June*\n" + bullet
        items = [_verified_item(0, bullet, year="Year 4")]
        rc, out, err = run_safe_send(_base_payload(msg, items))
        self.assertEqual(rc, 0, f"expected dry-run OK, got rc={rc}\nstderr={err}")
        self.assertIn("DRY-RUN OK", out)

    def test_whole_junior_audience_allowed_with_explicit_marker_in_bullet(self):
        """Whole-Junior items can pass IF the bullet text marks Y4 explicitly."""
        bullet = "• Whole-Junior assembly — includes Year 4."
        msg = "*BSC Year 4 Weekly Digest*\n\n" + bullet
        items = [_verified_item(0, bullet, year="all-junior")]
        rc, out, err = run_safe_send(_base_payload(msg, items))
        self.assertEqual(rc, 0, f"expected OK, got rc={rc}\nstderr={err}")

    def test_year3_still_blocked_belt_and_braces(self):
        """Pre-existing Year-3 regex must still fire."""
        bullet = "• Year 3 sports day reminder."
        msg = "*BSC Year 4 Weekly Digest*\n\n" + bullet
        items = [_verified_item(0, bullet)]
        rc, _, err = run_safe_send(_base_payload(msg, items))
        self.assertNotEqual(rc, 0)
        self.assertIn("Year 3 content", err)

    def test_ical_sourced_item_rejected(self):
        """iCal/calendar is no longer a valid source (disabled 2026-06-15).
        Any items[] entry with source=ical:* or source_message_id starting
        with ical- must be rejected before reaching other gates.
        """
        bullet = "• Year 4 Showcase at 12:30pm."
        msg = "*BSC Year 4 6am*\n\n" + bullet
        items = [_verified_item(0, bullet, source="ical:bsc", source_id="ical-abc")]
        rc, _, err = run_safe_send(_base_payload(msg, items))
        self.assertNotEqual(rc, 0)
        self.assertIn("iCal/calendar sources are disabled", err)

    def test_calendar_sourced_item_rejected(self):
        """Defense-in-depth: 'calendar' in source value also blocks."""
        bullet = "• Year 4 Showcase at 12:30pm."
        msg = "*BSC Year 4 6am*\n\n" + bullet
        items = [_verified_item(0, bullet, source="calendar:gsuite")]
        rc, _, err = run_safe_send(_base_payload(msg, items))
        self.assertNotEqual(rc, 0)
        self.assertIn("iCal/calendar sources are disabled", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
