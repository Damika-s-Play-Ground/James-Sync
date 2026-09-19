#!/usr/bin/env python3
"""BSC agent safe-send: final guarded delivery to the public School Assistant group.

Called by bsc-agent-draft.py cmd_send via subprocess:
    python3 bsc-agent-safe-send.py --input <payload.json> --send

Input JSON fields (written by bsc-agent-draft.py):
    decision        — must be "SEND"
    audience        — must be "Year 4" or "Year 4 parents"
    final_message   — the exact text to send (already validated upstream)
    evidence        — non-empty list
    risk_flags      — must be empty/absent
    target_group    — must be PUBLIC JID (REDACTED_JID)
    items           — REQUIRED list of per-bullet verification rows. Each row:
                      {bullet_index, text, source, source_message_id,
                       source_excerpt, applies_to_year_groups,
                       target_audience_detected, verification_status,
                       parent_safe, rejection_reason}

Exit codes:
    0   — sent OK, prints message id
    1   — validation failure or send failure (stderr contains reason)
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, re, subprocess, sys
from datetime import datetime, timezone

PUBLIC = os.getenv("BSC_PUBLIC_JID", "REDACTED_JID")
DEV    = os.getenv("BSC_DEV_JID", "REDACTED_JID")

# Explicit year/audience exclusions (always blocked in final_message)
YEAR3_RE  = re.compile(r"\b(year\s*3|y3\b|3b\b)\b", re.I)
SENIOR_RE = re.compile(r"\b(year\s*[5-9]|y[5-9]\b|sixth\s*form|senior\s*school)\b", re.I)

# Whole-Junior / Key Stage wording. Allowed only if the same bullet line ALSO
# contains an explicit Year-4 marker. Catches generic KS wording leaks where
# the source was for another year group with no Y4 qualifier.
KS_RE = re.compile(r"\b(key\s*stage\s*[12]|ks[12]|whole[\s-]+junior)\b", re.I)
Y4_MARKER_RE = re.compile(r"\b(year\s*4|y4\b|4b\b)\b", re.I)

ALLOWED_AUDIENCES = ("Year 4", "Year 4 parents")
AUDIT_LOG = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/bsc-agent-drafts/audit.log")
VALID_STATUSES = ("verified", "ambiguous", "rejected")
Y4_LIKE = {
    "year 4", "y4", "4b",
    "all", "junior", "all-junior", "whole-junior", "whole junior",
    "junior school", "ks2", "whole school",
}


def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _split_bullets(text: str):
    """Split final_message into bullet/line units for per-line wording checks.

    A bullet is any line that begins with a common bullet glyph or hyphen, or
    any non-empty line if none of those are present.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    bullets = [l for l in lines if l.startswith(("•", "-", "*", "—"))]
    return bullets or lines


def validate_items(items, message_text):
    """Per-item verification. Raises via die() on failure."""
    if not isinstance(items, list) or len(items) == 0:
        die("items[] is required and must be non-empty (per-bullet verification metadata)")

    required = {
        "bullet_index", "text", "source", "source_excerpt",
        "applies_to_year_groups", "target_audience_detected",
        "verification_status", "parent_safe",
    }

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            die(f"items[{i}] must be an object")
        missing = required - set(it.keys())
        if missing:
            die(f"items[{i}] missing fields: {sorted(missing)}")

        src = str(it.get("source", "")).strip().lower()
        smi = str(it.get("source_message_id", "")).strip().lower()
        if src.startswith("ical") or smi.startswith("ical-") or "calendar" in src:
            die(f"items[{i}] source={it.get('source')!r} source_message_id={it.get('source_message_id')!r} — iCal/calendar sources are disabled (2026-06-15: inaccurate details + redundant with newsletter)")

        st = it.get("verification_status")
        if st not in VALID_STATUSES:
            die(f"items[{i}] verification_status must be one of {VALID_STATUSES}, got {st!r}")
        if st != "verified":
            reason = it.get("rejection_reason")
            die(f"items[{i}] not verified (status={st}, reason={reason!r}) — refusing public send")
        if it.get("parent_safe") is not True:
            die(f"items[{i}] parent_safe is not true — refusing public send")

        years = it.get("applies_to_year_groups")
        if not isinstance(years, list) or len(years) == 0:
            die(f"items[{i}] applies_to_year_groups must be a non-empty list")
        norm = [str(y).strip().lower() for y in years]
        if not any(y in Y4_LIKE for y in norm):
            die(f"items[{i}] applies_to_year_groups {years!r} does not include Year 4 / all-Junior")


def validate(p: dict) -> str:
    """Run all safety gates. Returns final_message on success, raises on failure."""
    if p.get("decision") != "SEND":
        decision = p.get("decision")
        die(f"decision must be SEND, got {decision!r}")

    audience = p.get("audience", "")
    if audience not in ALLOWED_AUDIENCES:
        die(f"audience must be one of {ALLOWED_AUDIENCES!r}, got {audience!r}")

    target = p.get("target_group", "")
    if target != PUBLIC:
        die(f"target_group must be {PUBLIC}, got {target!r}")

    msg = (p.get("final_message") or "").strip()
    if not msg:
        die("final_message is empty")
    if len(msg) > 4000:
        die(f"final_message too long ({len(msg)} chars, max 4000)")

    # Legacy explicit-year blocks (still useful as belt-and-braces)
    if YEAR3_RE.search(msg):
        die("Year 3 content detected in final_message — blocked")
    if SENIOR_RE.search(msg):
        die("Senior school content detected in final_message — blocked")

    # KS1/KS2/whole-Junior wording must be accompanied by an explicit Year 4
    # marker in the same bullet. Belt-and-braces against generic KS wording leaks.
    for bullet in _split_bullets(msg):
        if KS_RE.search(bullet) and not Y4_MARKER_RE.search(bullet):
            sample = bullet[:200]
            die(f"KS1/KS2/whole-Junior wording without explicit Year-4 marker in bullet: {sample!r}")

    evidence = p.get("evidence")
    if not evidence or not isinstance(evidence, list) or len(evidence) == 0:
        die("evidence list is required and must be non-empty")

    risk_flags = p.get("risk_flags")
    if risk_flags:
        die(f"risk_flags present — should be HOLD, not SEND: {risk_flags}")

    # NEW: per-item verification (the main protection)
    validate_items(p.get("items"), msg)

    return msg


def wa_send(jid: str, text: str) -> str:
    """Send via wacli. Returns message id string. Raises RuntimeError on failure."""
    p = subprocess.run(
        ["wacli", "send", "text", "--to", jid, "--message", text],
        text=True, capture_output=True, timeout=60
    )
    if p.returncode:
        raise RuntimeError(p.stderr[-1000:] or p.stdout[-1000:])
    m = re.search(r"\(id\s+([^\)]+)\)", p.stdout)
    return m.group(1) if m else p.stdout.strip()


def main():
    ap = argparse.ArgumentParser(description="BSC safe-send — guarded public delivery")
    ap.add_argument("--input", required=True, help="Path to payload JSON file")
    ap.add_argument("--send", action="store_true", help="Actually send (dry-run if omitted)")
    ap.add_argument("--dev-only", action="store_true",
                    help="Send to DEV group instead of PUBLIC (for testing only)")
    args = ap.parse_args()

    inp = pathlib.Path(args.input)
    if not inp.exists():
        die(f"input file not found: {inp}")

    try:
        payload = json.loads(inp.read_text())
    except Exception as e:
        die(f"failed to parse input JSON: {e}")

    msg = validate(payload)

    if not args.send:
        print(f"DRY-RUN OK — would send {len(msg)} chars to {PUBLIC}")
        print("---")
        print(msg)
        sys.exit(0)

    target_jid = PUBLIC
    if args.dev_only:
        target_jid = DEV
        print(f"DEV-ONLY mode — sending to {DEV} instead of PUBLIC", file=sys.stderr)

    try:
        msg_id = wa_send(target_jid, msg)
    except RuntimeError as e:
        die(f"wacli send failed: {e}")

    # Write audit log entry so bsc-public-send-auditor.py can verify this send
    sha = hashlib.sha256(msg.encode()).hexdigest()
    audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "draft_id": payload.get("draft_id", inp.stem),
        "action": "SENT",
        "sha": sha,
        "msg_id": msg_id,
        "target": target_jid,
        "chars": len(msg),
    }
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")
    except Exception as e:
        print(f"WARNING: failed to write audit log: {e}", file=sys.stderr)

    print(msg_id)


if __name__ == "__main__":
    main()
