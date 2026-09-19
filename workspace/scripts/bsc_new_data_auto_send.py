#!/usr/bin/env python3
"""BSC new-data auto-send candidate/gate engine.

Phase 1/2 implementation: dry-run candidate detection + conservative gates.
No public/DEV sends are performed by default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from typing import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

WS = Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
DB_PATH = WS / "state" / "bsc-data.db"
LOG_DIR = WS / "logs" / "cron"
AUDIT_PATH = WS / "state" / "bsc-agent-drafts" / "auto-send-audit.jsonl"
HOLDS_DIR = WS / "state" / "bsc-agent-drafts" / "auto-send-holds"
SAFE_SEND = WS / "scripts" / "bsc-agent-safe-send.py"
PUBLIC = os.getenv("BSC_PUBLIC_JID", "REDACTED_JID")
DEV = os.getenv("BSC_DEV_JID", "REDACTED_JID")
COLOMBO = ZoneInfo("Asia/Colombo")

PUBLIC_CATEGORY_ALLOWLIST = {
    c.strip() for c in os.getenv(
        "BSC_AUTOSEND_PUBLIC_CATEGORIES",
        "school_reopen,school_closure,deadline_tomorrow,arrival_dismissal_change",
    ).split(",") if c.strip()
}

MAX_PUBLIC_SENDS_PER_RUN = int(os.getenv("BSC_AUTOSEND_MAX_PUBLIC_SENDS_PER_RUN", "1"))
MAX_PUBLIC_SENDS_PER_DAY = int(os.getenv("BSC_AUTOSEND_MAX_PUBLIC_SENDS_PER_DAY", "4"))
MAX_DEV_PREVIEWS_PER_RUN = int(os.getenv("BSC_AUTOSEND_MAX_DEV_PREVIEWS_PER_RUN", "1"))
MAX_DEV_PREVIEWS_PER_DAY = int(os.getenv("BSC_AUTOSEND_MAX_DEV_PREVIEWS_PER_DAY", "4"))
MIN_MINUTES_BETWEEN_PUBLIC_SENDS = int(os.getenv("BSC_AUTOSEND_MIN_MINUTES_BETWEEN_PUBLIC_SENDS", "60"))
MAX_CANDIDATES_PER_RUN_BEFORE_HOLD = int(os.getenv("BSC_AUTOSEND_MAX_CANDIDATES_PER_RUN", "10"))

TRUSTED_SOURCE_IDS = {
    "newsletter:week_ahead",
}
TRUSTED_SOURCE_AUDIENCES = {
    "year4",
    "junior_school",
    "parent_community",
}
TRUSTED_SENDER_HINTS = {
    "james",
    "school",
    "junior",
    "admin",
    "bsc",
    "teacher",
}

CHATTER_RE = re.compile(r"^(thanks|thank you|ok|okay|noted|sorry|haha|👍|🙏|🙈|🙂|😀|😂|yes|no)[\s!.,…]*$", re.I)
QUESTION_RE = re.compile(r"\?|\b(do we|does anyone|can someone|can anyone|anyone know|is it|are we|should we|i think|maybe|confirm|please confirm)\b", re.I)
WRONG_AUDIENCE_RE = re.compile(r"\b(years?\s*[356789]|y[356789]\b|senior\s*school|sixth\s*form|u1[35]\b|under\s*1[35])\b", re.I)
YEAR4_RE = re.compile(r"\b(years?\s*4|y4\b|grade\s*4|4b\b)\b", re.I)
JUNIOR_WIDE_RE = re.compile(r"\b(all\s+junior|junior\s+school|all\s+students|whole\s+school|whole\s+junior)\b", re.I)
MIXED_AUDIENCE_RE = re.compile(r"\b(years?\s*4\s*(?:-|–|to|and)\s*(?:years?\s*)?[56]|y4\b.{0,80}\by[56]\b)\b|\b(years?\s*[56]\s*(?:-|–|to|and)\s*(?:years?\s*)?4|y[56]\b.{0,80}\by4\b)\b|\b(years?\s*4|y4\b).{0,80}\b(years?\s*[56]|y[56]\b)\b|\b(years?\s*[56]|y[56]\b).{0,80}\b(years?\s*4|y4\b)\b", re.I)

EVENT_PATTERNS = [
    ("school_reopen", re.compile(r"\b(school\s+reopens?|term\s+starts?|reopen)\b", re.I)),
    ("school_closure", re.compile(r"\b(school\s+closed|school\s+closure|holiday|no\s+school)\b", re.I)),
    ("arrival_dismissal_change", re.compile(r"\b(arriv(?:e|al)|dismissal|pickup|pick\s*up|drop\s*off|collect)\b", re.I)),
    ("deadline_tomorrow", re.compile(r"\b(deadline|due|submit|form|permission|payment|pay)\b", re.I)),
    ("bring_wear_tomorrow", re.compile(r"\b(bring|wear|uniform|kit|laptop|device|book)\b", re.I)),
    ("event", re.compile(r"\b(meeting|event|practice|match|exam|assessment|transport)\b", re.I)),
]

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(COLOMBO)
    s = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(COLOMBO)


def normalize_text(text: str) -> str:
    text = text or ""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Drop WhatsApp quoted reply previews.
        if stripped.startswith(">"):
            continue
        # Drop pure chatter lines.
        if CHATTER_RE.match(stripped):
            continue
        lines.append(stripped)
    out = " ".join(lines)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def classify_relevance(text: str, authoritative_notice: bool = False) -> dict:
    norm = normalize_text(text)
    if "[SYNC GAP" in text or "[SYSTEM:" in text or "Injected from Week Ahead newsletter" in text:
        return {"pass": False, "event_type": "system_marker", "reason": "system/sync marker", "confidence": "low"}
    if not norm:
        return {"pass": False, "event_type": "irrelevant", "reason": "empty/chatter only", "confidence": "low"}
    if CHATTER_RE.match(norm):
        return {"pass": False, "event_type": "irrelevant", "reason": "chatter only", "confidence": "low"}
    if QUESTION_RE.search(norm):
        official_structure = re.search(r"\b(dear\s+parents|we\s+(will|are|have)|kindly|please\s+(find|complete|submit)|subject:)\b", norm, re.I)
        speculative = re.search(r"\b(do we|does anyone|can someone|can anyone|anyone know|is it|are we|should we|i think|maybe|please confirm)\b", norm, re.I)
        if not (authoritative_notice and official_structure and not speculative):
            return {"pass": False, "event_type": "question_or_rumour", "reason": "question/speculation", "confidence": "low"}
    for event_type, pat in EVENT_PATTERNS:
        if pat.search(norm):
            return {"pass": True, "event_type": event_type, "reason": f"matched {event_type}", "confidence": "high"}
    return {"pass": False, "event_type": "irrelevant", "reason": "no actionable signal", "confidence": "low"}


def classify_audience(text: str, source_audience: str | None) -> dict:
    norm = normalize_text(text)
    src = (source_audience or "").lower()
    if MIXED_AUDIENCE_RE.search(norm):
        return {"pass": False, "decision": "held_mixed_audience", "audience": "mixed", "reason": "mixed Year 4/other-year wording"}
    if WRONG_AUDIENCE_RE.search(norm) and not YEAR4_RE.search(norm):
        return {"pass": False, "decision": "rejected_wrong_audience", "audience": "wrong", "reason": "non-Year-4/senior marker"}
    if YEAR4_RE.search(norm) or src == "year4":
        return {"pass": True, "decision": "pass", "audience": "Year 4", "reason": "explicit Year 4/source year4"}
    if JUNIOR_WIDE_RE.search(norm) or src in {"junior_school", "parent_community", "all"}:
        return {"pass": True, "decision": "pass", "audience": "Year 4", "reason": "whole Junior/whole-school applies to Year 4"}
    return {"pass": False, "decision": "held_requires_human", "audience": "unclear", "reason": "no clear Year 4 applicability"}


def classify_attachment(has_attachment: int | bool, status: str | None) -> dict:
    if not has_attachment:
        return {"pass": True, "decision": "pass", "reason": "no attachment"}
    status = status or "missing"
    if status == "ok":
        return {"pass": True, "decision": "pass", "reason": "attachment extracted"}
    if status == "no_text":
        return {"pass": True, "decision": "pass", "reason": "attachment final no_text"}
    if status in {"daemon_running", "missing"}:
        return {"pass": False, "decision": "held_attachment_pending", "reason": f"attachment status {status}"}
    return {"pass": False, "decision": "held_requires_human", "reason": f"attachment status {status}"}


def _extract_explicit_date(text: str, ref: datetime) -> tuple[datetime | None, str | None, str | None]:
    lower = text.lower()
    if "tomorrow" in lower:
        return ref + timedelta(days=1), None, "tomorrow"
    if "today" in lower:
        return ref, None, "today"
    # ISO date
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lower)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=COLOMBO), None, "iso"
    # Weekday? DD Month
    weekday = None
    for name in WEEKDAYS:
        if re.search(rf"\b{name}\b", lower):
            weekday = name
            break
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", lower)
    if m:
        day = int(m.group(1)); mon = MONTHS[m.group(2)]
        year = ref.year
        dt = datetime(year, mon, day, tzinfo=COLOMBO)
        # If date is far behind ref and month/day no year, assume next year only for very-far future cycles.
        if dt.date() < ref.date() - timedelta(days=180):
            dt = datetime(year + 1, mon, day, tzinfo=COLOMBO)
        return dt, weekday, "day_month"
    return None, weekday, None


def verify_date_relevance(text: str, reference_time: str | None = None, evaluation_time: str | None = None) -> dict:
    """Parse date relative to message time, but judge freshness against run time.

    `reference_time` is the message timestamp, needed for words like today/tomorrow.
    `evaluation_time` is the cron/run time. Without this split, historical
    backfills from March look "fresh" relative to their own message timestamp.
    """
    ref = parse_dt(reference_time)
    eval_dt = parse_dt(evaluation_time) if evaluation_time else datetime.now(COLOMBO)
    dt, weekday, kind = _extract_explicit_date(text, ref)
    if dt is None:
        return {"pass": False, "decision": "rejected_ambiguous_date", "event_date": None, "reason": "no parseable date"}
    if weekday and dt.weekday() != WEEKDAYS[weekday]:
        return {"pass": False, "decision": "rejected_ambiguous_date", "event_date": dt.date().isoformat(), "reason": "day/date mismatch"}
    delta_from_now = (dt.date() - eval_dt.date()).days
    if delta_from_now < 0:
        return {"pass": False, "decision": "rejected_stale_date", "event_date": dt.date().isoformat(), "reason": "stale date"}
    if delta_from_now > 14:
        return {"pass": False, "decision": "held_requires_human", "event_date": dt.date().isoformat(), "reason": "too far in future"}
    return {"pass": True, "decision": "pass", "event_date": dt.date().isoformat(), "verified_day": dt.strftime("%A"), "reason": f"verified {kind}"}


def actionability_gate(text: str, event_type: str) -> dict:
    norm = normalize_text(text)
    if event_type in {"school_reopen", "school_closure"}:
        return {"pass": True, "reason": "high-importance school status"}
    if re.search(r"\b(arrive|bring|wear|submit|pay|complete|collect|pickup|drop\s*off|deadline|due|attend)\b", norm, re.I):
        return {"pass": True, "reason": "explicit parent/student action"}
    return {"pass": False, "decision": "rejected_no_action", "reason": "no clear parent action"}


def authority_level(source_id: str | None, source_audience: str | None, sender_name: str | None, sender_jid: str | None = None) -> str:
    sid = source_id or ""
    if sid in TRUSTED_SOURCE_IDS:
        return "trusted"
    src = (source_audience or "").lower()
    sender = (sender_name or "").lower()
    if src in TRUSTED_SOURCE_AUDIENCES and any(h in sender for h in TRUSTED_SENDER_HINTS):
        return "trusted"
    if src in TRUSTED_SOURCE_AUDIENCES:
        return "medium"
    return "unknown"


def exact_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).lower().encode()).hexdigest()


def semantic_key(audience: str, event_date: str | None, event_type: str, action: str) -> str:
    canon_action = re.sub(r"[^a-z0-9]+", "_", normalize_text(action).lower()).strip("_")[:80]
    return f"{audience.lower()}|{event_date or 'no-date'}|{event_type}|{canon_action}"


def is_duplicate(normalized_text: str, semantic: str, sent_semantic_keys: set[str], sent_hashes: set[str]) -> dict:
    h = exact_hash(normalized_text)
    if semantic in sent_semantic_keys:
        return {"pass": False, "decision": "rejected_duplicate", "reason": "semantic key already sent"}
    if h in sent_hashes:
        return {"pass": False, "decision": "rejected_duplicate", "reason": "exact hash already sent"}
    return {"pass": True, "reason": "not duplicate"}


def public_allowed(mode: str, event_type: str, allow_public_flag: bool) -> bool:
    return mode == "public" and allow_public_flag and event_type in PUBLIC_CATEGORY_ALLOWLIST


def daily_limit_reached(sent_today: int, max_per_day: int = MAX_PUBLIC_SENDS_PER_DAY) -> bool:
    # Returns True when more sends are allowed; historical test name expects False at/over limit.
    return sent_today < max_per_day


def build_safe_send_payload(candidate: dict, mode: str = "public") -> dict:
    text = candidate.get("draft_text") or candidate.get("normalized_text") or candidate.get("raw_text") or ""
    source_excerpt = (candidate.get("raw_text") or text)[:500]
    return {
        "decision": "SEND",
        "audience": "Year 4",
        "target_group": PUBLIC if mode != "dev" else DEV,
        "final_message": text.strip(),
        "evidence": [source_excerpt],
        "risk_flags": [],
        "items": [{
            "bullet_index": 0,
            "text": text.strip(),
            "source": candidate.get("source_id") or "unknown",
            "source_message_id": candidate.get("source_message_id") or candidate.get("id") or "unknown",
            "source_excerpt": source_excerpt,
            "applies_to_year_groups": ["Year 4"],
            "target_audience_detected": "Year 4",
            "verification_status": "verified",
            "parent_safe": True,
            "rejection_reason": None,
        }],
    }


def build_dev_preview_message(candidate: dict, payload: dict) -> str:
    """Build a preview message for DEV channel that clearly indicates it's not for parents."""
    final = payload["final_message"]
    source = candidate.get("source_name", "unknown")
    ev_type = candidate.get("event_type", "event")
    ev_date = candidate.get("event_date", "today")
    return (
        f"AUTO-SEND DEV PREVIEW\n"
        f"Source: {source}\n"
        f"Event: {ev_type}\n"
        f"Event Date: {ev_date}\n"
        f"\n"
        f"NOT SENT TO PARENTS\n"
        f"\n"
        f"{final}\n"
    )


def record_sent_log(
    conn: sqlite3.Connection,
    candidate: dict,
    mode: str,
    target_jid: str,
    message_text: str,
    payload_json: str,
    wacli_result: str | None = None,
) -> None:
    """Record a send event to auto_send_sent_log for audit and dedupe."""
    conn.execute(
        """INSERT INTO auto_send_sent_log
           (id, candidate_ids, source_message_ids, target_jid, send_mode, event_type,
            semantic_key, sent_hash, message_text, safe_send_payload, wacli_result, sent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            f"log-{datetime.now(timezone.utc).isoformat()}",
            candidate.get("id", ""),
            candidate.get("source_message_id", ""),
            target_jid,
            mode,
            candidate.get("event_type", ""),
            candidate.get("semantic_key", ""),
            candidate.get("exact_hash", exact_hash(candidate.get("draft_text") or "")),
            message_text,
            payload_json,
            wacli_result or "",
            now_utc(),
        ),
    )


def _draft_json_candidates(draft_id: str, drafts_dir: Path) -> list[Path]:
    """Return likely draft JSON paths for an audit.log draft_id."""
    raw = (draft_id or "").strip()
    if not raw:
        return []
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names:
            names.append(name)

    add(raw)
    add(raw.lstrip("."))
    for name in list(names):
        if name.endswith(".send"):
            add(name[:-5])
        if name.endswith("-send"):
            add(name[:-5])
        if name.endswith("-safesend"):
            add(name[:-9])
    return [drafts_dir / name if name.endswith(".json") else drafts_dir / f"{name}.json" for name in names]


def legacy_message_text_from_audit(entry: dict, drafts_dir: Path | None = None) -> str:
    """Resolve parent-facing text for a legacy SENT audit entry.

    Older send paths wrote audit.log SENT rows whose `sha` is SHA256(final_message).
    Runtime auto-send dedupe uses exact_hash(), i.e. SHA256(normalize_text(text).lower()).
    Recovering final_message keeps legacy sends in the same dedupe set as new sends.
    """
    for key in ("message_text", "final_message", "text"):
        if entry.get(key):
            return str(entry[key])
    ddir = drafts_dir or AUDIT_PATH.parent
    for path in _draft_json_candidates(str(entry.get("draft_id") or ""), ddir):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in ("final_message", "message"):
            if data.get(key):
                return str(data[key])
    return str(entry.get("draft_id") or "")


def legacy_semantic_key(entry: dict, message_text: str) -> str:
    draft_id = str(entry.get("draft_id") or "unknown")
    canon = re.sub(r"[^a-z0-9]+", "_", normalize_text(message_text).lower()).strip("_")[:80]
    return f"legacy_public|{draft_id}|{canon}"


def backfill_legacy_public_sends(
    conn: sqlite3.Connection,
    audit_path: Path = AUDIT_PATH.parent / "audit.log",
    drafts_dir: Path = AUDIT_PATH.parent,
) -> int:
    """Import legacy public SENT audit.log rows into auto_send_sent_log.

    Idempotent. Existing `legacy:*` rows are updated so `sent_hash` is the
    normalized exact_hash used by runtime duplicate detection, not the raw
    audit SHA of the original final_message.
    """
    ensure_tables(conn)
    if not audit_path.exists():
        return 0
    changed = 0
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("action") != "SENT" or entry.get("target") != PUBLIC:
            continue
        sha = str(entry.get("sha") or "").strip()
        if not sha:
            continue
        message_text = legacy_message_text_from_audit(entry, drafts_dir)
        legacy_id = f"legacy:{sha[:16]}"
        sent_hash = exact_hash(message_text)
        existing = conn.execute(
            "SELECT sent_hash, message_text FROM auto_send_sent_log WHERE id=?",
            (legacy_id,),
        ).fetchone()
        conn.execute(
            """INSERT OR REPLACE INTO auto_send_sent_log
               (id, candidate_ids, source_message_ids, target_jid, send_mode, event_type,
                semantic_key, sent_hash, message_text, safe_send_payload, wacli_result, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                legacy_id,
                str(entry.get("draft_id") or ""),
                str(entry.get("msg_id") or ""),
                PUBLIC,
                "public",
                "legacy_public",
                legacy_semantic_key(entry, message_text),
                sent_hash,
                message_text,
                json.dumps(entry, sort_keys=True),
                str(entry.get("msg_id") or ""),
                str(entry.get("ts") or now_utc()),
            ),
        )
        if existing is None or existing[0] != sent_hash or existing[1] != message_text:
            changed += 1
    return changed


def safe_send_dry_run(payload: dict) -> dict:
    HOLDS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HOLDS_DIR / f"safe-send-{hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]}.json"
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    p = subprocess.run([sys.executable, str(SAFE_SEND), "--input", str(tmp)], text=True, capture_output=True, timeout=30)
    return {"pass": p.returncode == 0, "stdout": p.stdout, "stderr": p.stderr, "payload_path": str(tmp)}


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS auto_send_processed_messages (
      message_id TEXT PRIMARY KEY,
      source_id TEXT NOT NULL,
      processed_at TEXT NOT NULL,
      decision TEXT NOT NULL,
      candidate_id TEXT
    );
    CREATE TABLE IF NOT EXISTS auto_send_candidates (
      id TEXT PRIMARY KEY,
      source_message_id TEXT NOT NULL,
      source_id TEXT NOT NULL,
      source_name TEXT,
      sender_name TEXT,
      sender_jid TEXT,
      message_timestamp TEXT,
      ingested_at TEXT,
      raw_text TEXT NOT NULL,
      attachment_text TEXT,
      normalized_text TEXT,
      has_attachment INTEGER DEFAULT 0,
      attachment_status TEXT,
      authority_level TEXT,
      event_type TEXT,
      audience TEXT,
      event_date TEXT,
      action_required TEXT,
      relevance_score INTEGER DEFAULT 0,
      confidence TEXT,
      semantic_key TEXT,
      exact_hash TEXT,
      draft_text TEXT,
      decision TEXT NOT NULL,
      decision_reason TEXT,
      gate_json TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auto_send_sent_log (
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


def load_sent_sets(conn: sqlite3.Connection, send_modes: tuple[str, ...] = ("public",)) -> tuple[set[str], set[str]]:
    try:
        placeholders = ",".join("?" for _ in send_modes)
        rows = conn.execute(
            f"SELECT semantic_key, sent_hash FROM auto_send_sent_log WHERE send_mode IN ({placeholders})",
            send_modes,
        ).fetchall()
    except sqlite3.OperationalError:
        return set(), set()
    return {r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]}


def classify_candidate(row: sqlite3.Row, sent_semantic: set[str], sent_hashes: set[str], evaluation_time: str | None = None) -> dict:
    raw = row["text"] or ""
    att_text = row["extracted_text"] or ""
    combined = f"{raw}\n{att_text}" if att_text else raw
    normalized = normalize_text(combined)
    gates = {}

    attach = classify_attachment(row["has_attachment"], row["extraction_status"])
    gates["attachment"] = attach
    if not attach["pass"]:
        decision = attach["decision"]
        reason = attach["reason"]
        event_type = None
    else:
        auth_for_relevance = authority_level(row["source_id"], row["audience"], row["sender_name"], row["sender_jid"])
        rel = classify_relevance(normalized, authoritative_notice=auth_for_relevance in {"trusted", "medium"})
        gates["relevance"] = rel
        if not rel["pass"]:
            decision = "rejected_question_or_rumour" if rel["event_type"] == "question_or_rumour" else "rejected_irrelevant"
            reason = rel["reason"]
            event_type = rel["event_type"]
        else:
            event_type = rel["event_type"]
            aud = classify_audience(normalized, row["audience"])
            gates["audience"] = aud
            if not aud["pass"]:
                decision = aud["decision"]
                reason = aud["reason"]
            else:
                auth = authority_level(row["source_id"], row["audience"], row["sender_name"], row["sender_jid"])
                gates["authority"] = {"level": auth, "pass": auth in {"trusted", "medium"}}
                if auth in {"low", "unknown"}:
                    decision = "rejected_untrusted_sender"
                    reason = f"authority={auth}"
                else:
                    date = verify_date_relevance(normalized, row["timestamp"], evaluation_time)
                    gates["date"] = date
                    if not date["pass"]:
                        decision = date["decision"]
                        reason = date["reason"]
                    else:
                        act = actionability_gate(normalized, event_type)
                        gates["actionability"] = act
                        if not act["pass"]:
                            decision = act["decision"]
                            reason = act["reason"]
                        else:
                            sem = semantic_key("Year 4", date["event_date"], event_type, normalized)
                            dup = is_duplicate(normalized, sem, sent_semantic, sent_hashes)
                            gates["dedupe"] = dup
                            if not dup["pass"]:
                                decision = dup["decision"]
                                reason = dup["reason"]
                            else:
                                decision = "drafted"
                                reason = "all dry-run gates passed"

    event_date = (gates.get("date") or {}).get("event_date")
    sem = semantic_key("Year 4", event_date, event_type or "unknown", normalized) if normalized else None
    cid = f"auto:{row['id']}"
    draft = draft_message(normalized, event_type, event_date) if decision == "drafted" else None
    return {
        "id": cid,
        "source_message_id": row["id"],
        "source_id": row["source_id"],
        "source_name": row["name"],
        "sender_name": row["sender_name"],
        "sender_jid": row["sender_jid"],
        "message_timestamp": row["timestamp"],
        "ingested_at": row["ingested_at"],
        "raw_text": raw,
        "attachment_text": att_text,
        "normalized_text": normalized,
        "has_attachment": row["has_attachment"] or 0,
        "attachment_status": row["extraction_status"],
        "authority_level": (gates.get("authority") or {}).get("level") or authority_level(row["source_id"], row["audience"], row["sender_name"], row["sender_jid"]),
        "event_type": event_type,
        "audience": "Year 4" if (gates.get("audience") or {}).get("pass") else (gates.get("audience") or {}).get("audience"),
        "event_date": event_date,
        "action_required": normalized[:240],
        "relevance_score": 100 if decision == "drafted" else 0,
        "confidence": (gates.get("relevance") or {}).get("confidence", "low"),
        "semantic_key": sem,
        "exact_hash": exact_hash(normalized),
        "draft_text": draft,
        "decision": decision,
        "decision_reason": reason,
        "gate_json": json.dumps(gates, sort_keys=True),
    }


def draft_message(text: str, event_type: str | None, event_date: str | None) -> str:
    clean = normalize_text(text)
    clean = re.sub(r"\b(thanks|thank you|please note that)\b[:,]?\s*", "", clean, flags=re.I)
    clean = clean.strip()
    if len(clean) > 650:
        clean = clean[:647].rstrip() + "..."
    prefix = "Year 4 reminder"
    if event_type in {"school_reopen", "school_closure"}:
        prefix = "Year 4 update"
    return f"{prefix}: {clean}"



def save_candidate(conn: sqlite3.Connection, c: dict) -> None:
    ts = now_utc()
    cols = [
        "id", "source_message_id", "source_id", "source_name", "sender_name", "sender_jid",
        "message_timestamp", "ingested_at", "raw_text", "attachment_text", "normalized_text",
        "has_attachment", "attachment_status", "authority_level", "event_type", "audience",
        "event_date", "action_required", "relevance_score", "confidence", "semantic_key",
        "exact_hash", "draft_text", "decision", "decision_reason", "gate_json",
    ]
    values = [c.get(col) for col in cols] + [ts, ts]
    conn.execute(f"""
        INSERT OR REPLACE INTO auto_send_candidates
        ({', '.join(cols)}, created_at, updated_at)
        VALUES ({', '.join(['?'] * (len(cols) + 2))})
    """, values)
    conn.execute("""
        INSERT OR REPLACE INTO auto_send_processed_messages
        (message_id, source_id, processed_at, decision, candidate_id)
        VALUES (?, ?, ?, ?, ?)
    """, (c["source_message_id"], c["source_id"], ts, c["decision"], c["id"]))
    audit(c)


def audit(c: dict) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": now_utc(),
        "candidate_id": c.get("id"),
        "source_message_id": c.get("source_message_id"),
        "decision": c.get("decision"),
        "reason": c.get("decision_reason"),
        "event_type": c.get("event_type"),
        "event_date": c.get("event_date"),
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def fetch_unprocessed(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("""
        SELECT
          m.id,
          m.source_id,
          s.name,
          s.audience,
          m.sender_jid,
          m.sender_name,
          m.timestamp,
          m.text,
          m.has_attachment,
          m.ingested_at,
          a.extracted_text,
          a.extraction_status
        FROM messages m
        JOIN sources s ON s.id = m.source_id
        LEFT JOIN attachments a ON a.message_id = m.id
        LEFT JOIN auto_send_processed_messages p ON p.message_id = m.id
        WHERE p.message_id IS NULL
        ORDER BY m.timestamp ASC
        LIMIT ?
    """, (limit,)).fetchall()


def count_sent_today(conn: sqlite3.Connection, mode: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        return conn.execute(
            "SELECT count(*) FROM auto_send_sent_log WHERE send_mode=? AND substr(sent_at,1,10)=?",
            (mode, today),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def send_text(target_jid: str, message: str, runner: Callable | None = None) -> str:
    cmd = ["wacli", "send", "text", "--to", target_jid, "--message", message]
    run = runner or subprocess.run
    p = run(cmd, text=True, capture_output=True, timeout=120)
    if getattr(p, "returncode", 0):
        raise RuntimeError((getattr(p, "stderr", "") or getattr(p, "stdout", "") or "wacli send failed")[-1000:])
    return (getattr(p, "stdout", "") or "ok").strip()


def run(db_path: Path = DB_PATH, limit: int = 50, mode: str | None = None, send_runner: Callable | None = None) -> dict:
    mode = mode or os.getenv("BSC_AUTO_SEND_MODE", "dry_run")
    evaluation_time = now_utc()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    backfill_legacy_public_sends(conn)
    sent_semantic, sent_hashes = load_sent_sets(conn, ("public", "dev"))
    rows = fetch_unprocessed(conn, limit)
    summary = {"mode": mode, "new_messages": len(rows), "sent_public": 0, "sent_dev": 0, "drafted": 0, "held": 0, "rejected": 0, "decisions": {}}
    summary["circuit_breaker"] = "too_many_candidates" if len(rows) > MAX_CANDIDATES_PER_RUN_BEFORE_HOLD else "none"

    dev_sent_this_run = 0
    public_sent_this_run = 0

    for row in rows:
        c = classify_candidate(row, sent_semantic, sent_hashes, evaluation_time)
        if c["decision"] == "drafted":
            payload = build_safe_send_payload(c, "public")
            dry = safe_send_dry_run(payload)
            if not dry["pass"]:
                c["decision"] = "held_requires_human"
                c["decision_reason"] = "safe-send dry-run failed: " + (dry["stderr"] or dry["stdout"])[:300]
            else:
                c["decision_reason"] += f"; safe-send dry-run OK; payload={dry['payload_path']}"
                if mode == "dev":
                    if dev_sent_this_run >= MAX_DEV_PREVIEWS_PER_RUN:
                        c["decision"] = "held_requires_human"
                        c["decision_reason"] += "; dev per-run limit reached"
                    elif count_sent_today(conn, "dev") >= MAX_DEV_PREVIEWS_PER_DAY:
                        c["decision"] = "held_requires_human"
                        c["decision_reason"] += "; dev daily limit reached"
                    else:
                        preview = build_dev_preview_message(c, payload)
                        try:
                            result = send_text(DEV, preview, send_runner)
                            record_sent_log(conn, c, "dev", DEV, preview, json.dumps(payload, sort_keys=True), result)
                            dev_sent_this_run += 1
                            summary["sent_dev"] += 1
                            sent_semantic.add(c.get("semantic_key"))
                            sent_hashes.add(c.get("exact_hash"))
                        except Exception as e:
                            c["decision"] = "held_requires_human"
                            c["decision_reason"] += f"; dev send failed: {e}"
                elif mode == "public":
                    if os.getenv("BSC_ALLOW_PUBLIC_AUTOSEND") != "1":
                        c["decision"] = "held_requires_human"
                        c["decision_reason"] += "; public autosend disabled"
                    elif c.get("event_type") not in PUBLIC_CATEGORY_ALLOWLIST:
                        c["decision"] = "held_requires_human"
                        c["decision_reason"] += "; category not public-allowlisted"
                    elif public_sent_this_run >= MAX_PUBLIC_SENDS_PER_RUN:
                        c["decision"] = "held_requires_human"
                        c["decision_reason"] += "; public per-run limit reached"
                    elif count_sent_today(conn, "public") >= MAX_PUBLIC_SENDS_PER_DAY:
                        c["decision"] = "held_requires_human"
                        c["decision_reason"] += "; public daily limit reached"
                    else:
                        try:
                            result = send_text(PUBLIC, payload["final_message"], send_runner)
                            record_sent_log(conn, c, "public", PUBLIC, payload["final_message"], json.dumps(payload, sort_keys=True), result)
                            public_sent_this_run += 1
                            summary["sent_public"] += 1
                        except Exception as e:
                            c["decision"] = "held_requires_human"
                            c["decision_reason"] += f"; public send failed: {e}"
        save_candidate(conn, c)
        summary["decisions"][c["decision"]] = summary["decisions"].get(c["decision"], 0) + 1
        if c["decision"] == "drafted":
            summary["drafted"] += 1
        elif c["decision"].startswith("held_"):
            summary["held"] += 1
        elif c["decision"].startswith("rejected_"):
            summary["rejected"] += 1
    conn.commit()
    conn.close()
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BSC new-data auto-send candidate processor (dry-run safe by default)")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--limit", type=int, default=int(os.getenv("BSC_AUTOSEND_LIMIT", "50")))
    ap.add_argument("--mode", default=os.getenv("BSC_AUTO_SEND_MODE", "dry_run"), choices=["dry_run", "dev", "public"])
    args = ap.parse_args(argv)
    print(f"=== bsc-new-data-auto-send start {now_utc()} ===")
    summary = run(Path(args.db), args.limit, args.mode)
    for k, v in summary.items():
        if k == "decisions":
            for dk, dv in sorted(v.items()):
                print(f"{dk}={dv}")
        else:
            print(f"{k}={v}")
    print("=== bsc-new-data-auto-send done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
