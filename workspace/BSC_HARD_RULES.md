# BSC Hard Rules — MANDATORY Pre-Inclusion Gates

**These are not guidelines. These are HARD RULES.**

Every item from the Week Ahead newsletter or WhatsApp groups must pass ALL THREE gates before inclusion in any BSC message to School Assistant (Testing). iCal/calendar is NOT a valid source (see "iCal Exclusion Rule" below).

## Gate 1: Year 3 Audience Filter

**School Assistant (Testing) = Year 3 parents ONLY**

### INCLUDE:
- Year 3 / Y3 / Y3-B / YB / 3B explicit items
- Whole-Junior School or whole-school notices that genuinely apply to Year 3

### EXCLUDE:
- Year 4 / Y4 / Y4-B / 4B explicit items
- Year 5 / Y5 / Year 6 / Y6 explicit items
- U11 / U13 / U15 age-group items (unless explicitly include Year 3)
- Reception / Year 1 / Year 2 explicit items
- Senior School items

### Test:
Ask: "Does this item explicitly mention Year 3, or is it a whole-Junior/whole-school item that includes Year 3?"
If NO → EXCLUDE immediately.

---

## Gate 2: Date Relevance Filter

**Target day: Tomorrow (the day after the reminder is sent)**

### INCLUDE:
- Items happening tomorrow
- Items with a date range that includes tomorrow
- Multi-day items where tomorrow falls within the active window

### EXCLUDE:
- Items that already finished (end date before tomorrow)
- Items that haven't started yet (start date after tomorrow)
- Stale notices for past dates
- Future events that don't start until after tomorrow

### Test:
Ask: "Does this item's date range include tomorrow (Friday 12 June 2026)?"
If NO → EXCLUDE immediately.

---

## Gate 3: Actionability Filter

**Only include items that need parent action or awareness**

### INCLUDE:
- Events requiring preparation (kit, materials, permission)
- Deadlines (forms, payments, consent)
- Schedule changes (cancellations, venue changes, pickup changes)
- New urgent notices

### EXCLUDE:
- General school philosophy / policy statements
- Past events / retrospective summaries
- Standing policies already communicated
- Vague "we encourage" statements with no specific action

### Test:
Ask: "Does a Year 3 parent need to know this to prepare their child for tomorrow, or to take action tomorrow?"
If NO → EXCLUDE immediately.

---

## Execution Flow

For EVERY candidate item:

1. **Extract**: Source, text, date range, year group
2. **Gate 1**: Year 3 relevant? → If NO, EXCLUDE
3. **Gate 2**: Date includes tomorrow? → If NO, EXCLUDE
4. **Gate 3**: Actionable? → If NO, EXCLUDE
5. **Include**: Only items that pass all three gates

## Final Check Before Sending

Before sending ANY BSC message to School Assistant (Testing):

1. Read the final message
2. For each bullet point, verify:
   - Is this Year 3 or whole-Junior including Year 3?
   - Does the date range include tomorrow?
   - Is this actionable?
3. If ANY bullet fails ANY gate → REMOVE IT
4. Send only after all bullets pass all gates

---

---

## iCal Exclusion Rule — HARD (Added 2026-06-15, code-enforced 2026-06-15)

**iCal is NOT a valid source for BSC parent-facing messages.** Fully removed from the pipeline on 2026-06-15.

- Do NOT use iCal/calendar events as a source for any parent message content.
- iCal gives bare dates with no day names, no context, no Year 3 specificity — it caused wrong day labels and wrong audience filtering (the 2026-06-14 "Book Look (Key Stage 2)" Year-5-only leak).
- The only authorised sources are:
  1. WhatsApp group messages (BSC Yr3 Parents, BSC Junior School, BSC Sport & ECAs, BSC Parent Community)
  2. The Junior School Week Ahead newsletter — including the day-by-day section surfaced as `WEEK_AHEAD` in `bsc-data-dump.py` output (`parse_week_ahead()`).
- If an event only appears in iCal and not in WhatsApp/newsletter, it does not go in the message.

Enforcement (all live as of 2026-06-15):
- `bsc-data-dump.py` no longer emits an `EVENTS:` section. It emits `WEEK_AHEAD:` instead, derived from the newsletter day-by-day section with per-day Year-3 attribution.
- `bsc-data-sync.py` no longer ships an iCal source row or `fetch_ical()` function.
- `bsc-data-client.py` no longer exposes `get_upcoming_events()`.
- `bsc-agent-safe-send.py` rejects any items[] entry with `source` starting with `ical` or `calendar`, or `source_message_id` starting with `ical-`.
- The `bsc-ical` skill files and the `state/bsc-ical-url.txt` sidecar were deleted; the DB `sources` and `documents` rows for `ical:bsc` were removed.
- All 7 cron job prompts were patched: zero references to `EVENTS`, `ical:bsc`, or `ical-<event-id>` remain; the schema only allows `newsletter:week_ahead` and `wa:<group-jid>` sources.

Reason: iCal was the root cause of multiple day/date errors and non-Year-3 items leaking into parent messages.

---

## Date/Day Accuracy Rule — HARD (Added 2026-06-15)

**Every date label (Mon/Tue/Wed etc.) in a parent-facing message MUST be verified by code before sending.**

- Never assume or guess the day of week from a date
- Always compute: `python3 -c "import datetime; print(datetime.date(YYYY,M,D).strftime('%A'))"` or equivalent
- This applies to all dates in all slots: 6am, 3pm, urgent, weekly
- If the day label is wrong, delete and resend — do not leave incorrect info with parents

Recurring failure logged: 2026-06-14 ("Sun 22 Jun" when 22 Jun is a Monday), 2026-06-14 ("Tuesday 17 June" when Tuesday is the 16th).

---

## Channel Reply Rule — HARD (Added 2026-06-14)

**When a message arrives via WhatsApp (group or DM), ALWAYS reply using `message(action=send)`.**

Never use the final text response — it routes back to the webchat/API session, NOT to WhatsApp.

This applies to:
- Every reply, including one-liners and acknowledgements
- Corrections, follow-ups, and clarifications
- All groups and DMs

No exceptions. If you're in a WhatsApp context → use `message(action=send)`.

---

**Saved: 2026-06-11**
**Authority: Charitha**
**Enforcement: MANDATORY — No exceptions**

---

## Additional Rule: Always Check Attachments AND Extract Links

**Hard rule:** When a WhatsApp message contains a document/image attachment:
1. Download and read the full attachment before deciding relevance
2. Extract embedded hyperlinks from PDFs (use pypdf annotations, not just text extraction)
3. Include the link in the message if the item is actionable and has a resource/form link
4. Do NOT include an item without its associated link/resource if one exists in the attachment

**Always include links/resources in 6am and 3pm parent messages when available.**

---

---

## Formatting Rule for Mobile/WhatsApp

**Hard rule:** Parent-facing BSC messages must be mobile-friendly:
- NO horizontal separator lines (──────) — breaks readability on small screens
- NO internal commentary like "Gate checks:", "Evidence:", etc. — parent-facing only
- Plain bullet points with single asterisks for bold (*text*)
- Include links inline within bullets or on their own line
- Keep lines short; let WhatsApp wrap naturally

---


---

## PUBLIC Send Rule — HARD (Added 2026-06-14 post-mortem)

**NEVER call `message(action=send, target="REDACTED_JID")` directly.**

The PUBLIC group `REDACTED_JID` (School Assistant Testing) is parent-facing. Direct `message(send)` calls bypass the verification gate (`bsc-agent-safe-send.py`) and can leak non-Year-3 content — this caused the 2026-06-14 Book Look incident.

**The ONLY authorized path to publish to PUBLIC:**
1. Write the JSON payload (with `items[]` per the ITEMS HARD RULE).
2. Run:  `python3 /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/scripts/bsc-agent-safe-send.py --input <payload>.json --send`
3. Or, equivalently, run:  `python3 /opt/data/james-bsc-live-clean/data/.ocplatform/workspace/scripts/bsc-agent-draft.py send <draft_id>`

If Damika or Charitha says "send to parents", do NOT call `message(send, target=PUBLIC)` directly. Build the payload, run safe-send (or bsc-agent-draft.py send), and only then confirm. The audit log at `state/bsc-agent-drafts/audit.log` records every authorised send; an out-of-band send will be detected and alerted to DEV.

Enforcement: Mandatory. The wording-level Year-3 gate and per-item verification only run inside safe-send — bypassing it means parents may receive non-Year-3 content.

