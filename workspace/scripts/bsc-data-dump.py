#!/usr/bin/env python3
"""
bsc-data-dump.py — Dump BSC context from bsc-data.db for LLM preview jobs.
Usage: python3 bsc-data-dump.py --hours 72 --slot urgent|6am|3pm|weekly

Output (stdout, plain text the agent reads):
  CACHE_AGE: <minutes>
  NEW_SINCE_LAST_CYCLE: <count>
  MESSAGES: <JSON array>
  NEWSLETTER: <text>
  WEEK_AHEAD: <JSON array of {date, day_name, raw_excerpt,
                              year_groups_mentioned, y3_relevant}>
"""
import argparse, json, re, sqlite3, sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

DB = Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace/state/bsc-data.db")
CYCLE_HOURS = {"urgent": 4, "6am": 24, "3pm": 24, "weekly": 168}


# ----------------------------- Week Ahead parser -----------------------------

MONTHS = {
    "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
    "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12,
}

# Match ONLY the upper-case 3-letter form ("15th JUN") — prose mentions
# like "Tuesday, 16th June" use mixed case and would otherwise create
# duplicate / misattributed entries from the Notices section above.
DATE_HEADER_RE = re.compile(
    r'\b(\d{1,2})(?:st|nd|rd|th)\s+'
    r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b'
)

FOOTER_RE = re.compile(
    r'(CONNECT WITH|Mrs Hannah Wells|hannah\.wells@|The British School in Colombo|'
    r'\+94|Reports published|Tuesday 23rd June|\[\]\(http://britishschool\.lk/events/\))',
    re.IGNORECASE,
)

YEAR_GROUP_PATTERNS = [
    # 'Yrs 1-2', 'Yr1', 'Year 1' all match Year 1
    ("Year 1",        re.compile(r'\bYear\s*1\b|\bYrs?\s*1\b|\bYrs?\s*1[-\u20136]|\bY1\b', re.I)),
    ("Year 2",        re.compile(r'\bYear\s*2\b|\bYrs?\s*[12][-\u20136]|\bYrs?\s*2\b|\bY2\b', re.I)),
    # 'Yrs 3-6', 'Yr3', 'Year 3' all match Year 3 (fixes 2026-06-25 last-day end-of-term miss)
    ("Year 3",        re.compile(r'\bYear\s*3\b|\bYrs?\s*3[-\u20136]|\bYrs?\s*3\b|\bY3\b', re.I)),
    ("Year 4",        re.compile(r'\bYear\s*4\b|\bYrs?\s*[34][-\u20136]|\bYrs?\s*4\b|\bY4\b', re.I)),
    ("Year 5",        re.compile(r'\bYear\s*5\b|\bYrs?\s*[345][-\u20136]|\bYrs?\s*5\b|\bY5\b', re.I)),
    ("Year 6",        re.compile(r'\bYear\s*6\b|\bYrs?\s*\d[-\u2013]6\b|\bYrs?\s*6\b|\bY6\b', re.I)),
    ("KS1",           re.compile(r'\bKS1\b|\bKey\s*Stage\s*1\b', re.I)),
    ("KS2",           re.compile(r'\bKS2\b|\bKey\s*Stage\s*2\b', re.I)),
    ("Nursery",       re.compile(r'\bNursery\b', re.I)),
    ("Reception",     re.compile(r'\bReception\b', re.I)),
    ("Playgroup",     re.compile(r'\bPlaygroup\b|\bPG\s*[A-C]\b', re.I)),
    ("EYFS",          re.compile(r'\bEYFS\b', re.I)),
    ("Junior School", re.compile(r'\bJunior\s+(?:School|Duke)\b|\bWhole\s+Junior\b', re.I)),
    ("Whole School",  re.compile(r'\bWhole\s+School\b|\bParent\s+Collective\b|\bStep\s+up\b', re.I)),
]


def _clean_block(block: str) -> str:
    block = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', block)
    block = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', block)
    block = re.sub(r'\*+', ' ', block)
    block = re.sub(r'_+', ' ', block)
    block = re.sub(r'\s+', ' ', block).strip()
    return block


def _year_groups_in(text: str) -> list:
    return [label for label, pat in YEAR_GROUP_PATTERNS if pat.search(text)]


def _y3_relevant(year_groups: list) -> bool:
    """Conservative Y3 relevance — explicit Year 3, whole-school items, or
    whole-Junior items without a competing senior year. KS2 alone is NOT
    enough (2026-06-14 Book Look incident: "KS2" iCal title actually meant
    Year 5 only).
    """
    if "Year 3" in year_groups:
        return True
    if "Whole School" in year_groups:
        return True
    if "Junior School" in year_groups and not any(
        yg in year_groups for yg in ["Year 4", "Year 5", "Year 6"]
    ):
        return True
    return False


def parse_week_ahead(raw_text, issue_date_iso):
    """Extract day-by-day events from the BSC Junior School Week Ahead.

    Returns list of {date, day_name, raw_excerpt, year_groups_mentioned,
                     y3_relevant} ordered by date. Empty list on bad input.
    """
    if not raw_text:
        return []
    try:
        issue_year = int(issue_date_iso[:4])
        issue_month = int(issue_date_iso[5:7])
    except (TypeError, ValueError, IndexError):
        return []

    matches = list(DATE_HEADER_RE.finditer(raw_text))
    if len(matches) < 2:
        return []

    results = []
    seen = set()
    for i, m in enumerate(matches):
        day = int(m.group(1))
        month = MONTHS.get(m.group(2).upper())
        if not month:
            continue
        year = issue_year + 1 if (issue_month - month) > 2 else issue_year
        try:
            event_date = date(year, month, day)
        except ValueError:
            continue
        if event_date.isoformat() in seen:
            continue
        seen.add(event_date.isoformat())

        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else min(start + 1500, len(raw_text))
        chunk = raw_text[start:end]
        footer = FOOTER_RE.search(chunk)
        if footer:
            chunk = chunk[:footer.start()]
        block = _clean_block(chunk)
        if not block or len(block) < 5:
            continue
        block = block[:600]

        ygs = _year_groups_in(block)
        results.append({
            "date": event_date.isoformat(),
            "day_name": event_date.strftime("%A"),
            "raw_excerpt": block,
            "year_groups_mentioned": ygs,
            "y3_relevant": _y3_relevant(ygs),
        })

    results.sort(key=lambda r: r["date"])
    return results


# --------------------------------- main --------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=72)
    p.add_argument("--slot", default="urgent", choices=["urgent","6am","3pm","weekly"])
    args = p.parse_args()

    if not DB.exists():
        print("ERROR: bsc-data.db not found. Run bsc-data-sync.py first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    now = datetime.now(timezone.utc)

    # --- CACHE AGE ---
    row = conn.execute(
        "SELECT synced_at FROM sync_log WHERE status='ok' ORDER BY synced_at DESC LIMIT 1"
    ).fetchone()
    if row:
        last = datetime.fromisoformat(row["synced_at"])
        if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        cache_age = int((now - last).total_seconds() / 60)
    else:
        cache_age = 9999
    print(f"CACHE_AGE: {cache_age}")

    # --- NEW SINCE LAST CYCLE ---
    cycle_h = CYCLE_HOURS.get(args.slot, 4)
    since_cycle = (now - timedelta(hours=cycle_h)).isoformat()
    row2 = conn.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE timestamp > ? AND source_id LIKE 'wa:%'",
        (since_cycle,)
    ).fetchone()
    new_count = row2["cnt"] if row2 else 0
    print(f"NEW_SINCE_LAST_CYCLE: {new_count}")

    # --- MESSAGES (recent, with attachment text) ---
    cutoff = (now - timedelta(hours=args.hours)).isoformat()
    rows = conn.execute("""
        SELECT m.id, m.timestamp, m.sender_name, m.text,
               s.name as group_name, s.audience,
               a.extracted_text, a.extracted_links, a.file_name, a.mime_type
        FROM messages m
        JOIN sources s ON m.source_id = s.id
        LEFT JOIN attachments a ON a.message_id = m.id
        WHERE m.timestamp > ? AND s.active = 1
          AND m.id NOT LIKE 'MANUAL:%'
          AND m.sender_jid NOT IN ('MANUAL:newsletter', 'SYSTEM')
        ORDER BY m.timestamp ASC
    """, (cutoff,)).fetchall()

    msgs = []
    for r in rows:
        entry = {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "sender": r["sender_name"],
            "group": r["group_name"],
            "audience": r["audience"],
            "text": r["text"] or "",
        }
        if r["extracted_text"]:
            entry["attachment_text"] = r["extracted_text"][:3000]
        if r["extracted_links"]:
            try:
                entry["attachment_links"] = json.loads(r["extracted_links"])
            except Exception:
                pass
        if r["file_name"]:
            entry["file_name"] = r["file_name"]
        if not entry["text"] and "attachment_text" not in entry:
            continue
        msgs.append(entry)
    print(f"MESSAGES: {json.dumps(msgs, ensure_ascii=False)}")

    # --- NEWSLETTER (latest Week Ahead) + WEEK_AHEAD structured days ---
    doc = conn.execute(
        "SELECT raw_text, issue_date, fetched_at FROM documents "
        "WHERE source_id='newsletter:week_ahead' AND is_current=1 "
        "ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    week_ahead = []
    if doc:
        raw_text = doc["raw_text"] or ""
        fetched_at = doc["fetched_at"] or ""
        issue_date_iso = doc["issue_date"]  # "YYYY-MM-DD"
        try:
            fa = datetime.fromisoformat(fetched_at.rstrip("Z"))
            if fa.tzinfo is None: fa = fa.replace(tzinfo=timezone.utc)
            age_h = int((now - fa).total_seconds() / 3600)
        except Exception:
            age_h = 9999
        print(f"NEWSLETTER: [fetched {age_h}h ago] {raw_text[:4000]}")
        week_ahead = parse_week_ahead(raw_text, issue_date_iso)
    else:
        print("NEWSLETTER: not available in DB")

    print(f"WEEK_AHEAD: {json.dumps(week_ahead, ensure_ascii=False)}")

    # --- EVENTS (iCal) --- DISABLED 2026-06-15 per Charitha: iCal is not a
    # valid source. Wrong day labels + non-Y3 items leaked. Authorised
    # sources are WhatsApp groups + Week Ahead newsletter (above).

    conn.close()


if __name__ == "__main__":
    main()
