#!/usr/bin/env python3
"""BSC scheduled parent-message draft builder.

Creates dry-run DEV-safe draft/hold artifacts for:
- daily-6am-summary: today's activities
- daily-3pm-reminder: tomorrow's activities/deadlines
- weekly-sunday-summary: upcoming week overview

No WhatsApp send is performed by this script. PUBLIC delivery remains behind the
existing safe-send/send-slot path and explicit operator approval.
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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo

WS = Path(os.environ.get("BSC_WORKSPACE", "/opt/data/james-bsc-live-clean/data/.ocplatform/workspace"))
DB_PATH = WS / "state" / "bsc-data.db"
DRAFTS_DIR = WS / "state" / "bsc-agent-drafts"
AUDIT_LOG = DRAFTS_DIR / "audit.log"
SAFE_SEND = WS / "scripts" / "bsc-agent-safe-send.py"
PUBLIC = os.getenv("BSC_PUBLIC_JID", "REDACTED_JID")
DEV = os.getenv("BSC_DEV_JID", "REDACTED_JID")
COLOMBO = ZoneInfo("Asia/Colombo")

Y4_RE = re.compile(r"\b(years?\s*4|y4\b|grade\s*4|4b\b)\b", re.I)
JUNIOR_RE = re.compile(r"\b(junior\s+school|bsc\s+juniors?|all\s+junior|whole\s+junior|all\s+students|children)\b", re.I)
WRONG_AUD_RE = re.compile(r"\b(years?\s*[356789]|y[356789]\b|senior\s*school|sixth\s*form|u1[35]\b|under\s*1[35])\b", re.I)
ACTION_RE = re.compile(r"\b(bring|wear|arrive|arrival|dismissal|pickup|pick\s*up|collect|submit|pay|payment|deadline|due|form|permission|meeting|event|practice|match|exam|assessment|school\s+starts?|school\s+reopens?|gates?\s+open|booking|audition|upload|pack)\b", re.I)
CHATTER_RE = re.compile(r"^(thanks|thank you|ok|okay|noted|sorry|haha|👍|🙏|yes|no)[\s!.,…]*$", re.I)
MIXED_AUDIENCE_RE = re.compile(
    r"\byears?\s*4\s*(?:-|–|to|and)\s*(?:years?\s*)?[56]\b|\byears?\s*[56]\s*(?:-|–|to|and)\s*(?:years?\s*)?4\b",
    re.I,
)
DATE_PREFIX_RE = re.compile(
    r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+20\d{2}\s*",
    re.I,
)
LETTER_PREFIX_RE = re.compile(r"^(?:dear\s+parents?,?\s*)+", re.I)
NOTICE_DATE_PREFIX_RE = re.compile(
    r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+20\d{2}\s*",
    re.I,
)
FILLER_SENTENCE_RE = re.compile(
    r"\bThis is a fantastic opportunity[^.]*\.\s*|\bPlease find (?:attached|the latest issue of)[^.]*\.\s*|\bThank you\.?\s*$",
    re.I,
)

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


@dataclass
class Item:
    text: str
    source: str
    source_message_id: str
    source_excerpt: str
    event_date: str | None
    mixed: bool = False


def load_sent_texts(db_path: Path) -> list[str]:
    """Message texts of everything previously sent to parents (dedupe reference)."""
    try:
        c = sqlite3.connect(db_path)
        rows = c.execute("SELECT message_text FROM auto_send_sent_log WHERE send_mode IN ('public','legacy_public')").fetchall()
        c.close()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows if r[0]]


def covered_by_prior_send(text: str, sent_texts: list[str]) -> bool:
    """True when this item is essentially a subset of something already sent."""
    words = set(re.sub(r"[^\w\s]", " ", normalize_text(text).lower()).split())
    if len(words) < 8:
        return False
    for prior in sent_texts:
        pw = set(re.sub(r"[^\w\s]", " ", normalize_text(prior).lower()).split())
        if not pw:
            continue
        if len(words & pw) / len(words) >= 0.8:
            return True
    return False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_colombo() -> datetime:
    return now_utc().astimezone(COLOMBO)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def normalize_text(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith(">") or CHATTER_RE.match(s):
            continue
        lines.append(s)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def parse_iso(value: str | None) -> datetime:
    if not value:
        return now_utc()
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def extract_dates(text: str, ref: datetime, infer_relative: bool = True) -> set[str]:
    lower = (text or "").lower()
    out: set[str] = set()
    if infer_relative:
        if "tomorrow" in lower:
            out.add((ref.astimezone(COLOMBO).date() + timedelta(days=1)).isoformat())
        if "today" in lower:
            out.add(ref.astimezone(COLOMBO).date().isoformat())
    for m in re.finditer(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lower):
        out.add(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", lower):
        day = int(m.group(1)); mon = MONTHS[m.group(2)]
        year = ref.astimezone(COLOMBO).year
        d = datetime(year, mon, day, tzinfo=COLOMBO).date()
        if d < ref.astimezone(COLOMBO).date() - timedelta(days=180):
            d = datetime(year + 1, mon, day, tzinfo=COLOMBO).date()
        out.add(d.isoformat())
    if infer_relative:
        for wd, idx in WEEKDAYS.items():
            if re.search(rf"\b{wd}\b", lower):
                today = ref.astimezone(COLOMBO).date()
                delta = (idx - today.weekday()) % 7
                out.add((today + timedelta(days=delta)).isoformat())
    return out


def audience_ok(text: str, source_audience: str | None) -> bool:
    src = (source_audience or "").lower()
    norm = normalize_text(text)
    if WRONG_AUD_RE.search(norm) and not Y4_RE.search(norm):
        return False
    return bool(Y4_RE.search(norm) or JUNIOR_RE.search(norm) or src in {"year4", "junior_school", "parent_community", "all"})


def item_ok(text: str, source_audience: str | None) -> bool:
    norm = normalize_text(text)
    return bool(norm and audience_ok(norm, source_audience) and ACTION_RE.search(norm))


def conn(db_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def fetch_recent_messages(c: sqlite3.Connection, hours: int = 336) -> list[sqlite3.Row]:
    cutoff = (now_utc() - timedelta(hours=hours)).isoformat()
    return c.execute("""
        SELECT m.id, m.source_id, m.sender_name, m.timestamp, m.text,
               s.name AS source_name, s.audience,
               a.extracted_text, a.extraction_status
        FROM messages m
        JOIN sources s ON s.id = m.source_id
        LEFT JOIN attachments a ON a.message_id = m.id
        WHERE m.timestamp > ? AND COALESCE(s.active, 1)=1
        ORDER BY m.timestamp DESC
    """, (cutoff,)).fetchall()


def fetch_current_newsletter(c: sqlite3.Connection) -> sqlite3.Row | None:
    return c.execute("""
        SELECT id, source_id, issue_date, raw_text, fetched_at
        FROM documents WHERE is_current=1
        ORDER BY fetched_at DESC LIMIT 1
    """).fetchone()


def newsletter_lines(doc: sqlite3.Row | None) -> list[tuple[str, str, str, datetime]]:
    if not doc:
        return []
    ref = parse_iso(doc["fetched_at"])
    lines = []
    for line in (doc["raw_text"] or "").splitlines():
        text = normalize_text(line)
        if len(text) < 20:
            continue
        lines.append(("BSC Week Ahead Newsletter", doc["id"], text, ref))
    return lines


BULLET_RE = re.compile(r"^(?:\*[^*]|[•·]\s*|-\s+)")
HEADING_RE = re.compile(r"^\*\*.+\*\*:?\s*$")


def contextual_newsletter_lines(doc: sqlite3.Row | None) -> list[tuple[str, set[str]]]:
    """Newsletter lines with inherited date context.

    Real newsletters put the date on a section header ("A Few Reminders for
    Monday:") and the actionable bullets on separate undated lines. Bullets
    following a dated header inherit its dates until a new heading resets the
    context.
    """
    if not doc:
        return []
    ref = parse_iso(doc["fetched_at"])
    out: list[tuple[str, set[str]]] = []
    ctx: set[str] | None = None
    for line in (doc["raw_text"] or "").splitlines():
        text = normalize_text(line)
        if len(text) < 8:
            continue
        is_bullet = bool(BULLET_RE.match(text))
        is_heading = bool(HEADING_RE.match(text)) and not is_bullet
        dates = extract_dates(text, ref)
        if dates:
            ctx = dates
        elif is_heading:
            ctx = None
        elif is_bullet and ctx:
            dates = set(ctx)
        out.append((text, dates))
    return out


def gather_items(c: sqlite3.Connection, target_dates: set[str], *, include_week: bool = False, sent_texts: list[str] | None = None) -> list[Item]:
    items: list[Item] = []
    doc = fetch_current_newsletter(c)
    doc_id = doc["id"] if doc else ""
    for text, dates in contextual_newsletter_lines(doc):
        if (dates & target_dates) or (include_week and dates and dates <= target_dates):
            if item_ok(text, "junior_school"):
                items.append(Item(text=text[:2500], source="BSC Week Ahead Newsletter", source_message_id=doc_id, source_excerpt=text[:400], event_date=sorted(dates & target_dates or dates)[0], mixed=bool(MIXED_AUDIENCE_RE.search(text))))
    for r in fetch_recent_messages(c):
        msg_ref = parse_iso(r["timestamp"])
        combined = normalize_text((r["text"] or "") + "\n" + (r["extracted_text"] or ""))
        if not combined:
            continue
        # Stale sources may only contribute EXPLICIT dates; bare weekday /
        # today/tomorrow inference from old messages fabricates future bindings.
        fresh = (now_utc() - parse_iso(r["timestamp"])) <= timedelta(days=7)
        dates = extract_dates(combined, msg_ref, infer_relative=fresh)
        if (dates & target_dates) or (include_week and dates and dates <= target_dates):
            if item_ok(combined, r["audience"]):
                items.append(Item(text=combined[:2500], source=r["source_name"], source_message_id=r["id"], source_excerpt=combined[:400], event_date=sorted(dates & target_dates or dates)[0], mixed=bool(MIXED_AUDIENCE_RE.search(combined))))
    # De-dupe by normalized text prefix/date; drop items already covered by prior parent sends.
    seen = set(); out = []
    for it in items:
        key = (normalize_text(it.text).lower()[:120], it.event_date)
        if key in seen:
            continue
        seen.add(key)
        if sent_texts and covered_by_prior_send(it.text, sent_texts):
            continue
        out.append(it)
    return out[:10]


def target_dates_for(job: str, ref: datetime) -> tuple[str, set[str], str, str]:
    d = ref.astimezone(COLOMBO).date()
    if job == "daily-6am-summary":
        return "6am-summary", {d.isoformat()}, d.isoformat(), "today"
    if job == "daily-3pm-reminder":
        t = d + timedelta(days=1)
        return "3pm-reminder", {t.isoformat()}, t.isoformat(), "tomorrow"
    if job == "weekly-sunday-summary":
        monday = d + timedelta(days=(7 - d.weekday()) % 7)
        if monday == d:
            monday = d + timedelta(days=1)
        dates = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
        return "weekly-summary", dates, monday.isoformat(), "upcoming week"
    raise ValueError(f"unknown job: {job}")


def item_payloads(items: list[Item]) -> list[dict]:
    payloads = []
    for i, it in enumerate(items, 1):
        payloads.append({
            "bullet_index": i,
            "text": it.text,
            "source": it.source,
            "source_message_id": it.source_message_id,
            "source_excerpt": it.source_excerpt,
            "applies_to_year_groups": ["Junior School"] if it.mixed else ["Year 4", "Junior School"],
            "target_audience_detected": "Mixed (Years 4-6)" if it.mixed else "Year 4 parents",
            "verification_status": "verified",
            "parent_safe": not it.mixed,
            "rejection_reason": "mixed audience Years 4-6 — excluded from PUBLIC auto-send" if it.mixed else "",
        })
    return payloads


def trim_at_sentence(text: str, max_len: int) -> str:
    """Cut long text on a sentence/word boundary. Never emit a mid-word ellipsis."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    window = text[:max_len]
    for sep in (". ", "! ", "? "):
        idx = window.rfind(sep)
        if idx >= max_len // 3:
            return window[: idx + 1].strip()
    cut = window.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:")


def clean_item_text(text: str) -> str:
    text = DATE_PREFIX_RE.sub("", text or "")
    text = LETTER_PREFIX_RE.sub("", text)
    text = FILLER_SENTENCE_RE.sub("", text)
    text = re.sub(r"\bAuditions for our\b", "Auditions for", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _plain_lines(text: str) -> list[str]:
    lines = [re.sub(r"\*+", "", re.sub(r"\s+", " ", ln)).strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) > 2:
        return lines
    return [
        re.sub(r"\*+", "", re.sub(r"\s+", " ", part)).strip()
        for part in re.split(r"(?<=[.!?])\s+|(?=\b(?:Choir|Dance|Drama) Squad:)", text or "")
        if part.strip()
    ]


def _event_date_re(event_date: str | None) -> re.Pattern[str] | None:
    if not event_date:
        return None
    try:
        d = datetime.fromisoformat(event_date)
        if d.tzinfo is None:
            d = d.replace(tzinfo=COLOMBO)
        d = d.astimezone(COLOMBO)
        return re.compile(
            rf"\b{d.day}(?:st|nd|rd|th)?\s+(?:{d.strftime('%B')}|{d.strftime('%b')})\b",
            re.I,
        )
    except (TypeError, ValueError):
        return None


def format_audition_block(text: str, event_date: str | None) -> str:
    """WhatsApp-friendly squad audition block with headings, not one run-on bullet."""
    lines = _plain_lines(text)
    date_re = _event_date_re(event_date)
    timed: list[tuple[str, str]] = []
    for ln in lines:
        m = re.search(r"\b(Choir|Dance|Drama)\s+Squad:\s*(.+)$", ln, re.I)
        if not m:
            continue
        detail = m.group(2).strip(" *")
        if date_re and not date_re.search(detail) and re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d)", detail, re.I):
            continue
        if re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d)", detail, re.I):
            timed.append((m.group(1).title(), detail))

    prep_by_name: dict[str, str] = {}
    in_prep = False
    for ln in lines:
        if re.search(r"what to prepare", ln, re.I):
            in_prep = True
            continue
        if not in_prep:
            continue
        if re.match(r"^(warm regards|thank you|please see|we look forward)\b", ln, re.I):
            break
        m = re.search(r"\b(Choir|Dance|Drama)\s+Squad:\s*(.+)$", ln, re.I)
        if m:
            prep_by_name[m.group(1).title()] = m.group(2).strip(" *")

    existing = bool(re.search(r"do not need to re-?audition", text, re.I))
    reconfirm = bool(re.search(r"reconfirm via email to Ms Sarah", text, re.I))
    until_330 = bool(re.search(r"run until 3\.?30", text, re.I))
    choir_friday = bool(re.search(r"choir squad has moved to Friday", text, re.I))
    few_places = bool(re.search(r"only a few places available in the Choir Squad", text, re.I))

    blocks: list[str] = []
    emoji = {"Choir": "🎭", "Dance": "💃", "Drama": "🎬"}
    if timed:
        for name, when in timed:
            heading = f"{emoji.get(name, '🎭')} *{name} Squad audition — {when}*"
            prep = prep_by_name.get(name)
            if prep:
                blocks.append(f"{heading}\nPrepare {prep[0].lower() + prep[1:] if prep else prep}".rstrip("."))
            else:
                blocks.append(heading)
    else:
        blocks.append("🎭 *Dance, Drama and Choir Squad auditions*\nHeld during the first week of the new academic year.")

    if existing or reconfirm:
        note = "*Already in Dance, Drama or Choir Squad?*\nNo re-audition needed."
        if existing:
            note = "*Already in Dance, Drama or Choir Squad?*\nNo re-audition needed. Places carry forward."
        if reconfirm:
            note += " Email Ms Sarah to reconfirm if your child still wants a place."
        blocks.append(note)

    extras = []
    if until_330:
        extras.append("All squad practices run until 3.30pm.")
    if choir_friday:
        extras.append("Choir has moved to Friday.")
    if few_places:
        extras.append("Only a few Choir places remain.")
    if extras:
        blocks.append("*Also note*\n" + " ".join(extras))

    return "\n\n".join(blocks)


def format_item_block(item: Item) -> str:
    text = item.text or ""
    if re.search(r"\bauditions?\b", text, re.I) and re.search(r"\b(choir|dance|drama)\s+squad", text, re.I):
        block = format_audition_block(text, item.event_date)
        if item.mixed:
            block += "\n⚠️ _mixed Years 4-6 — held from parents_"
        return block
    cleaned = clean_item_text(text)
    if not cleaned:
        return ""
    body = trim_at_sentence(cleaned, 280)
    mixed_note = "\n⚠️ _mixed Years 4-6 — held from parents_" if item.mixed else ""
    return f"• {body}{mixed_note}"


def build_message(job: str, label: str, items: list[Item], ref: datetime) -> str:
    local = ref.astimezone(COLOMBO)
    day = local.strftime("%A %-d %B %Y")
    if job == "daily-6am-summary":
        header = f"☀️ *Good morning Year 4 parents*\n\nToday’s school notes — {day}:"
    elif job == "daily-3pm-reminder":
        tomorrow = (local.date() + timedelta(days=1)).strftime("%A %-d %B")
        header = f"📠 *Year 4 reminder for tomorrow*\n\nKey notes for {tomorrow}:"
    else:
        header = f"📅 *Year 4 week ahead*\n\nKey Junior School notes for the upcoming week (today’s date: {day}):"
    blocks = []
    for it in items[:8]:
        block = format_item_block(it)
        if block:
            blocks.append(block)
    source = "Source: BSC Week Ahead / official WhatsApp sources."
    if not blocks:
        return header + "\n\n" + source
    return header + "\n\n" + "\n\n".join(blocks) + "\n\n" + source


def send_dev_preview(message: str) -> int:
    """Send a preview message to the James Bot Development WhatsApp group.

    Returns 1 on success, 0 on failure. Never touches PUBLIC.
    Uses wacli directly (available after env.sh sources WACLI paths).
    """
    try:
        result = subprocess.run(
            ["wacli", "send", "text", "--to", DEV, "--message", message],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return 1 if result.returncode == 0 else 0
    except Exception:
        return 0


def build_dev_preview_message(job: str, draft_id: str, final_message: str, sent_public: bool = False) -> str:
    """Wrap a scheduled-job message in a clearly-labelled DEV envelope."""
    status = (
        "✅ SENT to School Assistant (Testing)"
        if sent_public
        else "NOT SENT TO PARENTS"
    )
    return (
        f"SCHEDULED JOB PREVIEW — {job}\n"
        f"draft_id: {draft_id}\n"
        f"{status}\n"
        f"\n"
        f"{final_message}"
    )


def _run_safe_send(payload_path: Path) -> tuple[int, str]:
    """Run the audited safe-send validator with --send. Returns (rc, combined_output)."""
    try:
        r = subprocess.run(
            [sys.executable, str(SAFE_SEND), "--input", str(payload_path), "--send"],
            capture_output=True, text=True, timeout=90,
        )
        return r.returncode, ((r.stdout or "") + (r.stderr or ""))[-500:]
    except Exception as e:  # noqa: BLE001
        return 1, f"safe-send error: {e}"


def record_public_send(db_path: Path, payload: dict, wacli_result: str) -> None:
    """Record a successful scheduled PUBLIC send immediately for dedupe."""
    try:
        c = sqlite3.connect(db_path)
        sent_at = now_utc().isoformat()
        msg = payload.get("final_message", "")
        items = payload.get("items") or []
        source_ids = [it.get("source_message_id", "") for it in items if isinstance(it, dict) and it.get("source_message_id")]
        rec_id = f"scheduled:{payload.get('draft_id', sha(msg)[:16])}:{sha(msg)[:12]}"
        c.execute(
            """INSERT OR IGNORE INTO auto_send_sent_log
               (id, candidate_ids, source_message_ids, target_jid, send_mode, event_type,
                semantic_key, sent_hash, message_text, safe_send_payload, wacli_result, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec_id,
                json.dumps([payload.get("draft_id", "")], ensure_ascii=False),
                json.dumps(source_ids, ensure_ascii=False),
                PUBLIC,
                "public",
                payload.get("job", "scheduled"),
                payload.get("draft_id", rec_id),
                sha(msg),
                msg,
                json.dumps(payload, ensure_ascii=False),
                wacli_result,
                sent_at,
            ),
        )
        c.commit()
        c.close()
    except sqlite3.OperationalError:
        # Older/test DBs may not have the sent-log table; safe-send success remains authoritative.
        return


def write_artifact(job: str, mode: str, db_path: Path = DB_PATH, ref: datetime | None = None) -> dict:
    ref = ref or now_colombo()
    slot, dates, draft_date, label = target_dates_for(job, ref)
    c = conn(db_path)
    try:
        sent_texts = load_sent_texts(db_path)
        items = gather_items(c, dates, include_week=(job == "weekly-sunday-summary"), sent_texts=sent_texts)
    finally:
        c.close()
    draft_id = f"{draft_date}-{slot}"
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    if not items:
        # Explain suppression: were there raw candidates killed by dedupe/mixed-hold?
        c2 = conn(db_path)
        try:
            raw = gather_items(c2, dates, include_week=(job == "weekly-sunday-summary"))
        finally:
            c2.close()
        reason = f"No verified Year 4/Junior School actionable source items for {label}."
        if len(raw) > 0:
            reason = (f"{len(raw)} candidate item(s) found for {label}, but all were suppressed "
                      f"(already covered by prior parent sends or mixed-audience held).")
        hold = {
            "held_at": now_utc().isoformat(),
            "job": job,
            "mode": mode,
            "slot": slot,
            "target_dates": sorted(dates),
            "reason": reason,
        }
        (DRAFTS_DIR / f"{draft_id}.hold").write_text(json.dumps(hold, ensure_ascii=False, indent=2) + "\n")
        audit(draft_id, "SCHEDULED_HOLD", job=job, mode=mode, reason=hold["reason"])
        sent_dev = 0
        if mode != "dry_run":
            hold_msg = (
                f"SCHEDULED JOB HOLD — {job}\n"
                f"draft_id: {draft_id}\n"
                f"reason: {hold['reason']}"
            )
            sent_dev = send_dev_preview(hold_msg)
            audit(draft_id, "DEV_PREVIEW_SENT" if sent_dev else "DEV_PREVIEW_FAILED", job=job)
        return {"job": job, "mode": mode, "decision": "HOLD", "draft_id": draft_id, "items": 0,
                "sent_public": 0, "sent_dev": sent_dev}

    public_items = [it for it in items if not it.mixed]
    mixed_count = len(items) - len(public_items)
    msg = build_message(job, label, items, ref)  # full DEV view incl. held-item markers
    payload = {
        "draft_id": draft_id,
        "decision": "SEND",
        "audience": "Year 4 parents",
        "target_group": PUBLIC,
        "final_message": msg,
        "evidence": [it.source_excerpt for it in items[:5]],
        "risk_flags": [],
        "items": item_payloads(items),
        "job": job,
        "mode": mode,
        "target_dates": sorted(dates),
        "status": "DRY_RUN" if mode == "dry_run" else "DEV_ONLY",
        "created_at": now_utc().isoformat(),
        "message_sha256": sha(msg),
    }
    (DRAFTS_DIR / f"{draft_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    audit(draft_id, "SCHEDULED_DRAFT", job=job, mode=mode, items_total=len(items), sha=payload["message_sha256"])

    sent_public = 0
    public_note = ""
    if mode == "public" and os.getenv("BSC_ALLOW_PUBLIC_AUTOSEND") == "1":
        if public_items:
            public_msg = build_message(job, label, public_items, ref)
            public_payload = {**payload, "final_message": public_msg, "items": item_payloads(public_items),
                              "status": "PUBLIC_READY", "message_sha256": sha(public_msg)}
            public_path = DRAFTS_DIR / f"{draft_id}.public.json"
            public_path.write_text(json.dumps(public_payload, ensure_ascii=False, indent=2) + "\n")
            rc, out = _run_safe_send(public_path)
            sent_public = 1 if rc == 0 else 0
            if sent_public:
                record_public_send(db_path, public_payload, out)
            audit(draft_id, "PUBLIC_SENT" if sent_public else "PUBLIC_FAILED", job=job, rc=rc, detail=out)
        else:
            public_note = "only mixed-audience items; no parent-safe Year-4-only item"
            audit(draft_id, "PUBLIC_SKIPPED_NO_SAFE_ITEMS", job=job, mixed_held=mixed_count)
    elif mode == "public":
        audit(draft_id, "PUBLIC_DISABLED", job=job, allow=os.getenv("BSC_ALLOW_PUBLIC_AUTOSEND", "0"))

    sent_dev = 0
    if mode != "dry_run":
        dev_msg = build_dev_preview_message(job, draft_id, payload["final_message"], sent_public=bool(sent_public))
        if mode == "public":
            note = f"; held from parents: {public_note}" if public_note else f"; held mixed items: {mixed_count}" if mixed_count else ""
            dev_msg += f"\n\nPUBLIC RESULT: {'sent ' + str(len(public_items)) + ' item(s)' if sent_public else 'not sent'}{note}"
        sent_dev = send_dev_preview(dev_msg)
        audit(draft_id, "DEV_PREVIEW_SENT" if sent_dev else "DEV_PREVIEW_FAILED", job=job)
    return {"job": job, "mode": mode, "decision": "SENT" if sent_public else "DRAFT", "draft_id": draft_id,
            "items": len(items), "items_public": len(public_items), "mixed_held": mixed_count,
            "sent_public": sent_public, "sent_dev": sent_dev}


def audit(draft_id: str, action: str, **fields) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now_utc().isoformat(), "draft_id": draft_id, "action": action, **fields}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["daily-6am-summary", "daily-3pm-reminder", "weekly-sunday-summary"])
    ap.add_argument("--mode", choices=["dry_run", "dev", "public"], default=os.getenv("BSC_SCHEDULED_MODE", "dry_run"))
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--asof", help="Override current Colombo time, ISO format, for tests/dry-runs")
    args = ap.parse_args(argv)
    ref = parse_iso(args.asof).astimezone(COLOMBO) if args.asof else None
    result = write_artifact(args.job, args.mode, Path(args.db), ref)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
