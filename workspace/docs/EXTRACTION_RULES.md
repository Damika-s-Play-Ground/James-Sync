# BSC Extraction Rules

**Authoritative reference for all BSC filtering, guard, and pre-inclusion rules.**
Consolidated from: `BSC_HARD_RULES.md`, `bsc-agent-draft.py`, `bsc-agent-safe-send.py`, OCPlatform cron job prompts.
Last updated: 2026-06-13

---

## 1. Audience Scope — WHO receives messages

**Target group: School Assistant (Testing) `REDACTED_JID` — Year 3 parents ONLY.**

### INCLUDE:
- Year 3 / Y3 / Y3-B / YB / 3B explicit items
- Whole-Junior School or whole-school notices that genuinely apply to Year 3

### EXCLUDE:
- Year 4 / Y4 / Y4-B / 4B (hard-blocked — automated regex check)
- Year 5 / Y5 / Year 6 / Y6 / Senior School / Sixth Form
- U11 / U13 / U15 age-group items (unless explicitly include Year 3)
- Reception / Year 1 / Year 2

### Test:
> "Does this item explicitly mention Year 3, or is it a whole-Junior/whole-school item that includes Year 3?"
> If NO → EXCLUDE immediately.

### Automated guard (bsc-agent-safe-send.py):
```python
YEAR4_RE  = re.compile(r'\b(year\s*4|y4\b|4b\b)', re.I)
SENIOR_RE = re.compile(r'\b(year\s*[5-9]|y[5-9]\b|sixth\s*form|senior\s*school)\b', re.I)
```
If either pattern matches `final_message` → hard block, exit 1.


---

## 2. Date Relevance Filter — WHEN it applies

**Slot-specific date targets:**

| Slot | Target date | Notes |
|------|-------------|-------|
| 6am | Today (Asia/Colombo) | Actions for today |
| 3pm | Tomorrow (Asia/Colombo) | Heads-up for tomorrow |
| 4hr urgent (0700/1100/1400/1900/2300/0300) | Today unless source explicitly says otherwise | New urgent items since last cycle |
| Weekly (Sunday 3pm) | Coming week (Monday → Friday) | Week-ahead summary |

### INCLUDE:
- Items happening on the target date
- Items with a date range that includes the target date
- Multi-day items where the target date falls within the active window

### EXCLUDE:
- Items that already finished (end date before target)
- Items that haven't started yet (start date after target)
- Stale notices for past dates
- Items with relative language ("tomorrow", "today", "final day") — resolve against the **source WhatsApp message timestamp**, not the reminder run time

### Test:
> "Does this item's date range include the target date?"
> If NO → EXCLUDE immediately.


---

## 3. Actionability Filter — WHY it matters

**Only include items that need parent action or awareness.**

### INCLUDE:
- Events requiring preparation (kit, materials, permission slip)
- Deadlines (forms, payments, consent, sign-up)
- Schedule changes (cancellations, venue changes, pickup changes)
- New urgent notices

### EXCLUDE:
- General school philosophy / policy statements
- Past events / retrospective summaries
- Standing policies already communicated (e.g. "Performing Arts until 3:30pm for rest of term" — weekly/activity-day only, not daily)
- Vague "we encourage" statements with no specific action

### Test:
> "Does a Year 3 parent need to know this to prepare their child for the target date, or to take action?"
> If NO → EXCLUDE immediately.

---

## 4. Sport / ECA / Football Rule

Football, sport fixtures, and ECA items require **explicit** Year 3 / Y3-B / KS2 / Junior School applicability stated in the source.

- Do NOT infer Year 3 applies from a generic fixtures list.
- Age-group items (U11, U13, U15) only apply if they explicitly include Year 3 children.


---

## 5. Evidence Requirement

Every included item must have **exact source evidence** — a specific entry from:
- BSC Week Ahead newsletter (fetched, not cached guess)
- BSC iCal calendar
- WhatsApp group message (with message timestamp)
- Downloaded attachment (PDF/image — read via `pdftotext` or `tesseract`)

**No item may appear in a SEND draft without named evidence.**

The `evidence` field in the JSON payload must be a non-empty list. `bsc-agent-draft.py` and `bsc-agent-safe-send.py` both reject payloads with empty `evidence`.

---

## 6. Attachment & Link Rules

**Hard rule:** When a WhatsApp message contains a document/image attachment:
1. Download and read the full attachment before deciding relevance
2. Extract embedded hyperlinks from PDFs (use pypdf annotations, not just text extraction)
3. If an actionable item has a link/form/resource — include it in the message bullet
4. Do NOT include an item without its associated link/resource if one exists in the attachment



---

## 7. Cross-Slot Dedupe Guard

Before any public send, `bsc-agent-draft.py cmd_send` checks:

1. **Prior SENT drafts today** — for all other slots, checks `state/bsc-agent-drafts/<date>-<slot>.json` where `status == "SENT"`. Word overlap ratio > 0.70 → AUTO_HOLD.
2. **Recent public messages** — queries `wacli messages list --chat <PUBLIC> --limit 20`. Word overlap ratio > 0.75 → AUTO_HOLD.
3. Self-comparison excluded — the current draft's own `draft_id` is never compared against itself.

On AUTO_HOLD: status written to draft JSON, dev group notified, no public send.

```python
def _word_overlap(a, b):
    # Returns intersection / max(|a|, |b|) — Jaccard-like word overlap
    ...
# Thresholds: prior-draft=0.70, public-recent=0.75
```

---

## 8. Admin Approval / HOLD Gate

Before public send, `bsc-agent-draft.py cmd_send` reads **dev group replies** since the draft was created:

- **HOLD keywords** (`hold`, `stop`, `reject`, `cancel`, `do not send`, `don't send`, `wait`) → AUTO_HOLD
- **Approve keywords** (`approve`, `approved`, `send`, `ok`, `okay`, `yes`) → allow proceed
- **Any other non-empty reply** from an admin → AUTO_HOLD (treat as pending discussion)

**Admins** (trusted JIDs):
- `REDACTED_JID` (Charitha)
- `REDACTED_JID` (Damika Anupama)
- `REDACTED_JID` (Damika Anupama alt)

Nobody else can trigger HOLD or approve, regardless of what they write in dev group.


---

## 9. HOLD-State Persistence

When the preview job decides HOLD:
- A `.hold` marker is written to `state/bsc-agent-drafts/<draft_id>.hold`
- NO `.json` draft file is created
- Dev group is notified with the HOLD reason
- The send-slot script (`bsc-agent-send-slot.py`) checks for `.hold` and exits 0 silently (no public send, no error)
- Retry jobs check for both `.json` AND `.hold` before re-running — if either exists, reply DONE and stop

This prevents retry jobs from re-extracting when primary intentionally held.

---

## 10. send_at Window Rule

Drafts include a `send_at` UTC timestamp.

- **Preview jobs** run 15 minutes before the public send time
- **Send-slot jobs** (OS cron) call `bsc-agent-draft.py send` at the scheduled public time
- `cmd_send` checks `now() >= send_at` before proceeding (unless `--force` is passed)
- `--force` is available but should only be used for manual recovery

**Slot → send_at mapping (Asia/Colombo):**

| Slot | Preview time | Public send time |
|------|-------------|-----------------|
| 6am | 05:45 | 06:00 |
| 3pm | 14:45 | 15:00 |
| urgent-0700 | 06:45 | 07:00 |
| urgent-1100 | 10:45 | 11:00 |
| urgent-1400 | 13:45 | 14:00 |
| urgent-1900 | 18:45 | 19:00 |
| urgent-2300 | 22:45 | 23:00 |
| urgent-0300 | 02:45 | 03:00 |


---

## 11. Exact-Draft Immutability Rule

**The public send job MUST NOT re-extract at send time.**

- `bsc-agent-draft.py preview` stores exact bytes as `final_message` in the draft JSON
- `bsc-agent-draft.py send` reads the stored `message` field — never touches sources again
- `bsc-agent-safe-send.py` receives the stored final_message and applies only regex guards

The stored draft is the **single source of truth** for public delivery. No re-extraction, no re-summarization, no reformatting at send time.

---

## 12. Message Format Rules (Mobile/WhatsApp)

**Parent-facing BSC messages must be mobile-friendly:**
- Use single asterisks for bold: `*text*` (NOT `**text**`)
- No horizontal separator lines (`──────`) — breaks readability on small screens
- No internal commentary (`Gate checks:`, `Evidence:`, audit labels, confidence scores)
- Plain bullet points; let WhatsApp wrap naturally
- Links included inline within bullets or on their own line
- Keep it concise — action-first, parent perspective

**Never include in visible message:**
- Structured audit dumps
- Confidence labels
- Evidence quotes
- Exclusion reasoning
- Risk flags
- Architecture or extraction explanations

These stay internal to the agent's reasoning/JSON payload only.


---

## 13. Routing Rules — Where messages go

| Message type | Destination |
|-------------|-------------|
| Preview of candidate message | James Bot Development `REDACTED_JID` only |
| HOLD reason | James Bot Development only |
| Public send | School Assistant (Testing) `REDACTED_JID` |
| Failure alerts / errors | James Bot Development or Arian - School (private) |
| Cron framework output, confirmations, diagnostics | NEVER to School Assistant (Testing) |

**Hard rule:** `bsc-agent-safe-send.py` validates `target_group == PUBLIC` and refuses to send anywhere else. The `--dev-only` flag overrides to DEV for testing.

---

## 14. JSON Payload Schema (Preview Input)

Fields required by `bsc-agent-draft.py preview --input`:

```json
{
  "decision":     "SEND" | "HOLD",
  "audience":     "Year 3" | "Year 3 parents",
  "target_date":  "YYYY-MM-DD",
  "slot":         "6am" | "3pm" | "weekly" | "urgent-0700" | "urgent-1100" | "urgent-1400" | "urgent-1900" | "urgent-2300" | "urgent-0300",
  "send_at":      "<ISO-8601 with Asia/Colombo offset, e.g. 2026-06-14T06:00:00+05:30>",
  "final_message": "<exact text to send>",
  "evidence":     ["source 1", "source 2", ...],
  "exclusions":   ["excluded item reason", ...],
  "risk_flags":   []
}
```

Rules enforced by `validate_year3()` in `bsc-agent-draft.py`:
- `decision` must be `"SEND"`
- `audience` must be `"Year 3"` or `"Year 3 parents"`
- `final_message` must be non-empty
- No `year 4 / y4 / 4b` in `final_message`
- `evidence` must be non-empty
- `risk_flags` must be empty (non-empty → should be HOLD)
- `send_at` must be in the future


---

## 15. Standing Policy Rule

**Do NOT include standing policies as daily action items.**

Items that are standing policies (communicated once, ongoing for rest of term) must NOT appear in every daily reminder. Examples:
- "Performing Arts Squads until 3:30pm for rest of term"
- General swimming participation policy

These should only be mentioned:
- Weekly (in the Sunday digest)
- On the specific relevant activity day
- When the policy changes

Daily messages: only items requiring parent action **today/tomorrow** — kit, forms, payment, event timing, pickup change, deadline, non-uniform, special materials.

---

## 16. Source Freshness Rules

Always gather from ALL relevant sources before drafting:

1. **BSC iCal calendar** — `bsc-ical` skill for official events, term dates, fixtures
2. **WhatsApp groups** (run `wacli sync --once` first):
   - BSC Yr3 Parents 2025/26: `REDACTED_JID`
   - BSC Junior School: `REDACTED_JID`
   - BSC Sport & ECAs: `REDACTED_JID`
   - BSC Parent Community: `REDACTED_JID`
3. **Week Ahead newsletter** — fetch current issue, verify the newsletter's own issue date/title (do not trust `fetched_at` alone)
4. **Attachments** — download and read ALL; extract embedded links from PDFs

Never answer from a single source or from stale cache alone.

---

## 17. Week Ahead Cache Discipline

- Always validate the newsletter's own issue date/title before using cached items
- Do not trust `fetched_at` timestamp alone — it reflects when you downloaded it, not which week it covers
- If the cached newsletter is for a different week than the target date → re-fetch

---

## 18. Failure Handling Rules

On any failure (source unavailable, extraction error, guard rejection):
- Default to **HOLD** — never guess, never hallucinate an item
- Report failure to Development group only (`REDACTED_JID`)
- Never post failure/error/technical content to School Assistant (Testing)
- Exit codes: `bsc-agent-send-slot.py` exits 0 for HOLD/no-draft (expected); exits 1 for actual errors


---

## 19. Execution Flow — Full Pre-Inclusion Checklist

For EVERY candidate item from any source:

1. **Extract**: Source name, exact text, date range, year group mentioned
2. **Gate 1 — Audience**: Year 3 relevant? → If NO → EXCLUDE
3. **Gate 2 — Date**: Date range includes target date? → If NO → EXCLUDE
4. **Gate 3 — Actionable**: Parent needs to act or prepare? → If NO → EXCLUDE
5. **Gate 4 — Sport/ECA**: If sport/ECA — explicit Year 3/KS2/Junior applicability? → If NO → EXCLUDE
6. **Gate 5 — Standing policy**: Is this a standing policy already communicated? → If YES → EXCLUDE (unless weekly slot or policy-day)
7. **Evidence confirmed**: Source is named and specific? → If NO → EXCLUDE
8. **Attachment/link check**: If source has attachment or link → downloaded and included?
9. **Include**: Only items that pass all gates

**Final check before writing final_message:**
- Re-read every bullet
- Does each pass all gates?
- No Year 4/Senior content anywhere in the text?
- Mobile format (single `*`, no dividers, no internal labels)?

---

## Authority & Enforcement

- **Authority:** designated administrators (phone/LID values are kept in the protected runtime configuration)
- **Scope:** These rules apply to ALL BSC School Assistant sends, all slots, all agent jobs
- **No exceptions:** These are hard rules, not guidelines
- **Saved/updated:** 2026-06-13

---

*Sources: `BSC_HARD_RULES.md`, `scripts/bsc-agent-draft.py`, `scripts/bsc-agent-safe-send.py`, OCPlatform cron job prompts (6am, 3pm, 4hr preview, weekly, retry jobs), `MEMORY.md`*
