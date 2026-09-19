#!/usr/bin/env python3
"""Public-send auditor.

Scans recent FromMe messages in the PUBLIC parent group and cross-references
them against state/bsc-agent-drafts/audit.log. Any send not matching an
audited authorised path is reported to the DEV group.

Designed to run every 30 minutes via OCPlatform cron. Idempotent — re-runs are
safe (uses last-checkpoint file).
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

WS = pathlib.Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
AUDIT_LOG = WS / "state" / "bsc-agent-drafts" / "audit.log"
CHECKPOINT = WS / "state" / "supervisor" / "public-send-auditor.checkpoint"
PUBLIC = os.getenv("BSC_PUBLIC_JID", "REDACTED_JID")
DEV = os.getenv("BSC_DEV_JID", "REDACTED_JID")

LOOKBACK_HOURS = 6  # cap how far back we look when no checkpoint exists


def now() -> datetime:
    return datetime.now(timezone.utc)


def load_audit_shas() -> set:
    """Return all message_sha256 values from audit.log entries with action=SENT."""
    shas = set()
    if not AUDIT_LOG.exists():
        return shas
    try:
        with open(AUDIT_LOG, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("action") == "SENT" and rec.get("sha"):
                        shas.add(rec["sha"])
                except Exception:
                    pass
    except Exception:
        pass
    return shas


def fetch_recent_public_sends(since_iso: str):
    """Return list of FromMe messages to PUBLIC since the given iso timestamp."""
    p = subprocess.run(
        ["wacli", "messages", "list", "--chat", PUBLIC, "--limit", "60", "--full", "--json"],
        text=True, capture_output=True, timeout=45,
    )
    if p.returncode:
        return []
    try:
        obj = json.loads(p.stdout)
    except Exception:
        return []
    rows = (obj.get("data") or {}).get("messages") or obj.get("data") or []
    out = []
    since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    for r in rows:
        if not r.get("FromMe"):
            continue
        ts = r.get("Timestamp") or ""
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if t < since_dt:
            continue
        text = (r.get("Text") or r.get("DisplayText") or "").strip()
        out.append({"ts": ts, "msg_id": r.get("Id") or "", "text": text})
    return out


def sha256_text(t: str) -> str:
    import hashlib
    return hashlib.sha256(t.encode()).hexdigest()


def alert_dev(text: str):
    try:
        subprocess.run(
            ["wacli", "send", "text", "--to", DEV, "--message", text],
            text=True, capture_output=True, timeout=30,
        )
    except Exception:
        pass


def read_checkpoint() -> str:
    if CHECKPOINT.exists():
        try:
            return CHECKPOINT.read_text().strip()
        except Exception:
            pass
    return (now() - timedelta(hours=LOOKBACK_HOURS)).isoformat()


def write_checkpoint(iso: str):
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(iso)


def main():
    since = read_checkpoint()
    audited = load_audit_shas()
    sends = fetch_recent_public_sends(since)

    if not sends:
        write_checkpoint(now().isoformat())
        print(f"no public sends since {since}")
        return 0

    unaudited = []
    for s in sends:
        # The audit log records the SHA of the message body. Compare exact.
        body = s["text"]
        if not body or len(body) < 10:
            continue  # skip empty/very short status messages
        digest = sha256_text(body)
        if digest in audited:
            continue
        unaudited.append({**s, "sha": digest})

    if unaudited:
        lines = ["⚠️ Unaudited public-group sends detected (bypassed safe-send):"]
        for u in unaudited[:5]:
            snip = (u["text"][:160] + "…") if len(u["text"]) > 160 else u["text"]
            lines.append(f"\n• {u['ts']} (sha {u['sha'][:8]}): {snip}")
        lines.append(
            "\nReview: each public send MUST go through bsc-agent-safe-send.py. "
            "See BSC_HARD_RULES.md → PUBLIC Send Rule."
        )
        alert_dev("\n".join(lines))
        print(f"alerted DEV: {len(unaudited)} unaudited send(s)")
    else:
        print(f"all {len(sends)} public send(s) audited")

    write_checkpoint(now().isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
