# PROJECT_STATE.md — BSC James Reliability Hardening

**Last updated:** 2026-06-16 by Claude (Opus 4.7)
**Owner:** Damika Anupama (damikaanupama@gmail.com)
**Stakeholders:** Charitha (BSC ops decisions), Donely (OpenClaw platform team)
**Deadline pressure:** Two-week sprint before BSC summer break — parent trust in the daily WhatsApp messages is the primary KPI.

This is a context handoff. A fresh AI session reading this should be able to pick up the work without re-deriving anything from chat history.

---

## 1. Core objective

**Make the BSC ("British School in Colombo") Year-3 parent WhatsApp pipeline reliable enough that parents stop catching errors.** James (the OpenClaw agent named `main`) sends scheduled BSC reminders into a parent-facing WhatsApp group. Two reliability bugs have eroded parent trust:

1. **Year-3 audience leaks.** The 2026-06-14 weekly digest leaked a "Book Look (Key Stage 2)" bullet that was actually Year-5-only. The agent inferred Year-3 inclusion from a KS2 iCal title without cross-checking the newsletter body.
2. **WhatsApp routing.** When a WhatsApp message arrives, James occasionally replies into the webchat session instead of the WhatsApp group — the AGENTS.md "Channel Reply Rule" is prompt-only, not code-enforced.
3. **Two-tier cron / silent overlap.** Public sends happen via OS `cron`, previews via `openclaw cron list`; `openclaw cron list` therefore only shows half the truth. A leftover OS cron is currently double-sending at 15:00 SLT on weekdays.

Hard rules from the user (verbatim, ALL still apply):

- **Do not send anything to the parent-facing testing group without explicit approval during this fix.**
- **If a destructive or production-impacting action is needed, stop and ask first.**
- **Do not say "it won't happen again" unless there is a verified enforceable fix.**
- **Do not rely on `AGENTS.md` alone if the actual send path can still fail.**
- **Year 3 audience filter must exclude Year 4/5/6 explicit items.**
- **Do not add "check with your class teacher" as a way to keep an unverified item.**

---

## 2. Progress so far (chronological, then by phase)

### Phase A — Diagnose live OCPlatform jobs and cron *(completed)*

- Walked through openclaw + OS cron, draft store, send-slot wrapper, safe-send guard, sync layer.
- Mapped where each piece lives (table in §3 below).
- Confirmed which jobs are live and which are legacy.

### Phase B — Reconcile state *(completed)*

- **B1**: Removed obsolete 14:00 OCPlatform job + crontab line for an old 1400 path.
- **B2**: Reconciled `bsc-attachment-preflight.py`.
- **B3**: Made the OS-crontab decision (kept as the canonical send path; openclaw owns previews only).
- **B4**: Reconciled divergent agent scripts between `.openclaw/workspace/scripts` (legacy archive) and `.ocplatform/workspace/scripts` (live).
- **B5**: Canonicalised James's identity files; archived legacy scripts under `/data/.ocplatform/workspace/archive/openclaw-workspace-legacy-scripts/`.
- **B6**: Reconciled docs (`BSC_HARD_RULES.md`, `AGENTS.md`, `docs/EXTRACTION_RULES.md`).

### Phase C — Quality fixes for the 2026-06-14 Year-3 leak *(completed)*

Plan from `/Users/damikaanupama/.claude/plans/yes-synchronous-moth.md`. Steps 1–7:

- **Step 1**: Verified WhatsApp routing via trajectories — confirmed AGENTS.md Channel Reply Rule exists but has zero code enforcement.
- **Step 2**: Patched `bsc-agent-safe-send.py` with per-item verification gates:
  - Required `items[]` array (one entry per bullet) with `bullet_index`, `text`, `source`, `source_message_id`, `source_excerpt`, `applies_to_year_groups`, `target_audience_detected`, `verification_status`, `parent_safe`, `rejection_reason`.
  - Rejects any item where `verification_status != "verified"` or `parent_safe != true`.
  - KS1/KS2/whole-Junior wording without an explicit Year-3 marker in the same bullet line → die.
  - Year-4 / Year 5–9 / sixth form / senior school regexes (legacy belt-and-braces).
- **Step 3**: `bsc-agent-draft.py` now carries `items[]` through and writes an audit log to `state/bsc-agent-drafts/audit.log` (append-only JSONL).
- **Step 4**: Updated all 7 OCPlatform preview/retry prompts to require the items[] schema and explicit newsletter cross-check for KS-titled items.
- **Step 5**: Regression tests at `/data/.ocplatform/workspace/tests/test_bsc_verification_gate.py` (11 cases including `test_book_look_y5_rejected`, `test_ks2_bullet_no_y3_marker_rejected`, `test_ambiguous_item_blocked`, `test_ical_sourced_item_rejected`, `test_calendar_sourced_item_rejected`).
- **Step 6**: End-to-end verification — all gates fire as expected.
- **Step 7**: Asked James to review; cross-checked against actual file contents.

### Phase D — Implement Option B (WEEK_AHEAD parser) *(completed)*

Root cause of 2026-06-15 06:00 SLT HOLD: iCal had been disabled 75 min before the cron ran, Year-3 Showcase wasn't in the 72h WhatsApp data, and the newsletter's day-by-day section was beyond the 8000-char DB truncation.

- **B1**: Bumped newsletter truncation 8000 → 30000 chars in `bsc-data-sync.py`.
- **B2**: Wrote `parse_week_ahead(raw_text, issue_date_iso)` in `bsc-data-dump.py` that extracts day-by-day events with per-day Year-3 attribution.
- **B3**: Dump now emits `WEEK_AHEAD: [...]` instead of removed `EVENTS:` line.
- **B4**: 10 parser tests at `/data/.ocplatform/workspace/tests/test_week_ahead_parser.py`, all pass.
- **B5**: Patched 6am preview prompt to require WEEK_AHEAD cross-check.

### Phase E — Full iCal removal (per Charitha) *(completed)*

iCal entries had inaccurate details and were redundant with the newsletter. Layered defense:

- **C1**: Audited iCal touch points across scripts, prompts, docs, DB, skill files.
- **C2**: Patched the 5 remaining cron prompts (6am Dry-Run, 6am Retry, 3pm Dry-Run, 3pm Retry, 4-Hour Preview, 4-Hour Retry, Weekly Digest) — added WEEK_AHEAD blocks, removed every `EVENTS`/`ical:bsc`/`ical-<event-id>` mention, added "Do NOT use the bsc-ical skill" guard.
- **C3**: Stripped `ical:bsc` from items[] schema.
- **C4**: Deleted bsc-ical skill files (`/data/.openclaw/skills/bsc-ical`, `.../bsc-ical.skill`, `state/bsc-ical-url.txt`).
- **C5**: Updated `BSC_HARD_RULES.md` (lines 97–115: "iCal Exclusion Rule — HARD") and `AGENTS.md`. Removed `ical:bsc` source row + iCal documents from DB.
- **C6**: End-to-end verification — 21 tests passing (10 parser + 11 safe-send gate). Verification script at `/tmp/final-verify.py` on remote.

### Phase F — Current investigation (2026-06-16) *(in progress)*

Two new asks from the user:

1. **Q1 — Does James reference all current resources?** → Answered. Audited last 4 BSC cron trajectories; dump is correctly feeding all 4 WhatsApp groups + newsletter + WEEK_AHEAD on every preview run. Inconsistencies parents see are from the LLM reasoning step, not the data plane.
2. **Q2 — Hidden crons + add 2pm SLT slot to Four-Hour Preview/Retry** → Found OS crontab has 9 BSC jobs `openclaw cron list` does NOT show. The `urgent-1400` OS cron fires at `30 9 UTC = 15:00 SLT` despite the "1400" name, **double-sending with the weekday 3pm send at 15:00 SLT**. Proposed openclaw cron edits + OS cron time fix; **awaiting user approval** before applying.

---

## 3. Architecture and code structure

### 3.1 Hosts and access

| What | Value |
|---|---|
| Remote container | `root@REDACTED_TAILSCALE_IP` (Tailscale; macOS user has key-based SSH; no password in chat) |
| Local working dir | `/Users/damikaanupama` (this Mac) |
| Container OS | Debian-flavoured Linux, TZ = `Etc/UTC` |
| Container HOME | `/data` |
| Container shell | bash |
| OpenClaw gateway port | `18789` |
| OpenClaw agent name | `main` (a.k.a. "James Jr") — runs as PID 7 inside the container, `donely/default` model |
| OpenClaw harness version | 2026.5.6 / gitSha `7c70458` |
| Container date | reference: 2026-06-15 was the day of the last incident; today is 2026-06-16 (per `currentDate` memory) |

### 3.2 WhatsApp identifiers (group JIDs; operational, not auth secrets)

| Group | JID |
|---|---|
| **PUBLIC** (School Assistant Testing — parent-facing) | `REDACTED_JID@g.us` |
| **DEV** (James Bot Development) | `REDACTED_JID@g.us` |
| BSC Yr3 Parents 2025/26 | `REDACTED_JID@g.us` |
| BSC Junior School | `REDACTED_JID@g.us` |
| BSC Sport & ECAs | `REDACTED_JID@g.us` |
| BSC Parent Community | `REDACTED_JID@g.us` |
| WhatsApp account JID (wacli) | `REDACTED_USER@s.whatsapp.net` |

### 3.3 File layout (on the container)

All under `/data/` unless noted.

```
.ocplatform/workspace/                             ← canonical, live
├── BSC_HARD_RULES.md                              ← Year-3 gate + iCal exclusion + Channel Reply + date/day rule
├── AGENTS.md                                      ← (also has a copy under .openclaw/workspace/)
├── docs/EXTRACTION_RULES.md
├── scripts/
│   ├── bsc-data-sync.py                           ← every 45 min openclaw cron
│   ├── bsc-data-dump.py                           ← emits CACHE_AGE / NEW_SINCE_LAST_CYCLE / MESSAGES / NEWSLETTER / WEEK_AHEAD
│   ├── bsc-data-client.py
│   ├── bsc-agent-draft.py                         ← preview / revise / hold / send commands
│   ├── bsc-agent-safe-send.py                     ← final guarded delivery; items[] enforcement; KS-without-Y3 guard
│   └── bsc-agent-send-slot.py                     ← OS-cron entry-point that picks the draft and calls bsc-agent-draft.py send
├── state/
│   ├── bsc-data.db                                ← sqlite WAL+FTS5; sources, messages, attachments, documents, sync_log
│   └── bsc-agent-drafts/
│       ├── YYYY-MM-DD-<slot>.json                 ← SENT drafts
│       ├── YYYY-MM-DD-<slot>.hold                 ← HOLD reason
│       └── audit.log                              ← append-only JSONL audit
├── tmp/                                            ← agent writes draft payloads here pre-preview
├── tests/
│   ├── test_bsc_verification_gate.py              ← 11 cases
│   └── test_week_ahead_parser.py                  ← 10 cases
└── archive/openclaw-workspace-legacy-scripts/     ← prior tier, kept for reference only

.openclaw/workspace/                                ← James's bootstrap + identity
├── AGENTS.md                                       ← Channel Reply Rule (prompt-level)
├── SOUL.md, USER.md, MEMORY.md, memory/            ← per-session read by James
└── bin/
    ├── run-bsc-job.sh                              ← OS cron wrapper
    └── bsc-cron-heartbeat.sh                       ← proves OS cron is alive

.openclaw/agents/main/sessions/                     ← trajectories (JSONL per session)
.openclaw/cron/jobs.json                            ← openclaw cron payloads (managed via `openclaw cron edit`)
.openclaw/skills/                                   ← bsc-ical/ and bsc-ical.skill were deleted 2026-06-15

/root/bsc-consolidation-backups/                    ← timestamped backups for every file touched in earlier phases
```

### 3.4 BSC data layer

```
sqlite> .tables
attachments  documents  fts_content  messages  sources  sync_log
```

Current `sources` rows (5):

```
newsletter:week_ahead       newsletter      BSC Week Ahead Newsletter
wa:REDACTED_JID             whatsapp_group  BSC Parent Community
wa:REDACTED_JID             whatsapp_group  BSC Sport & ECAs
wa:REDACTED_JID             whatsapp_group  BSC Junior School
wa:REDACTED_JID             whatsapp_group  BSC Yr3 Parents 2025/26
```

iCal source / documents have been fully removed (Phase E). DB has WAL mode + FTS5.

### 3.5 The pipeline

```
[openclaw cron]                                   [OS cron]
   ↓                                                 ↓
preview prompt → agent runs bsc-data-dump        bsc-agent-send-slot.py
   ↓                                                 ↓
agent writes tmp/bsc-agent-<slot>.json (items[]) picks draft <today>-<slot>.json
   ↓                                                 ↓
bsc-agent-draft.py preview                       bsc-agent-draft.py send <draft_id>
   ↓                                                 ↓
draft stored at state/bsc-agent-drafts/          bsc-agent-safe-send.py --input … --send
   ↓                                                 ↓
DEV preview message posted                       wacli send → PUBLIC
   ↓
(DEV review window before OS-cron send time)
```

### 3.6 Two-tier cron — the actual schedule

**Layer 1 — `openclaw cron list` (12 jobs):**

| ID | Name | Schedule (tz) | Purpose |
|---|---|---|---|
| `f5f94c60…` | Tailscale Keepalive | every 5m | system |
| `f40c4bac…` | **BSC Four-Hour Agent Notice Preview** | `45 2,6,10,18,22 * * *` Asia/Colombo | 02:45/06:45/10:45/18:45/22:45 SLT — produces urgent-0300/-0700/-1100/-1900/-2300 drafts |
| `04f6495f…` | **BSC Four-Hour Agent Notice Retry** | `50 2,6,10,18,22 * * *` Asia/Colombo | retry 10 min before each public send |
| `921256dd…` | BSC Public-Send Auditor | `*/30 * * * *` UTC | watchdog |
| `99b48662…` | Gateway Outbound Health | `*/30 * * * *` UTC | system |
| `18288b03…` | BSC Data Sync | `*/45 * * * *` UTC | runs bsc-data-sync.py |
| `d835a78b…` | **BSC 6am Agent Reminder Dry-Run** | `45 5 * * 1-5` Asia/Colombo | 05:45 SLT, weekdays |
| `28e587ea…` | **BSC 6am Agent Reminder Retry** | `50 5 * * 1-5` Asia/Colombo | 05:50 SLT, weekdays |
| `55ebec1c…` | BSC System Integrity Check | `0 9 * * *` Asia/Colombo | 09:00 SLT daily |
| `7a70c601…` | **BSC 3pm Agent Reminder Dry-Run** | `45 14 * * 1-5` Asia/Colombo | 14:45 SLT |
| `406201a3…` | **BSC 3pm Agent Reminder Retry** | `50 14 * * 1-5` Asia/Colombo | 14:50 SLT |
| `99e47c9e…` | **BSC Weekly Digest** | `0 15 * * 0` Asia/Colombo | Sundays 15:00 SLT |

Edit with `openclaw cron edit <id> --message "<text>"`. There is no `--payload-merge`; you must replace the whole message.

**Layer 2 — OS root crontab (`crontab -l -u root`) — these openclaw does NOT show:**

```cron
* * * * *     /data/.openclaw/workspace/bin/bsc-cron-heartbeat.sh
*/90 * * * *  run-bsc-job.sh "BSC Data Sync" python3 bsc-data-sync.py     # invalid cron expression — */90 effectively no-ops; openclaw cron's */45 is the real sync
30 0  * * 1-5 …bsc-agent-send-slot.py --slot=6am          --target=today                                      # 06:00 SLT weekdays
30 1  * * *   …bsc-agent-send-slot.py --slot=urgent       --draft-id=$(TZ=Asia/Colombo date +%F)-urgent-0700  # 07:00 SLT
30 5  * * *   …bsc-agent-send-slot.py --slot=urgent       --draft-id=…urgent-1100                              # 11:00 SLT
30 9  * * *   …bsc-agent-send-slot.py --slot=urgent       --draft-id=…urgent-1400                              # 15:00 SLT ← BUG: name says 1400, time is 1500
30 9  * * 1-5 …bsc-agent-send-slot.py --slot=3pm          --target=tomorrow                                    # 15:00 SLT weekdays
30 13 * * *   …bsc-agent-send-slot.py --slot=urgent       --draft-id=…urgent-1900                              # 19:00 SLT
30 17 * * *   …bsc-agent-send-slot.py --slot=urgent       --draft-id=…urgent-2300                              # 23:00 SLT
30 21 * * *   …bsc-agent-send-slot.py --slot=urgent       --draft-id=…urgent-0300                              # 03:00 SLT
HOME=/data
MAILTO=""
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
SHELL=/bin/bash
```

`/etc/cron.d/bsc-openclaw` is the disabled legacy file: contains only `# Disabled 2026-06-09: BSC agent preview/exact-draft pipeline is canonical.`

### 3.7 The Year-3 verification gate (items[] schema)

Every bullet in `final_message` has to have a matching item:

```json
{
  "bullet_index": 0,
  "text": "<≤200-char snippet of the bullet>",
  "source": "newsletter:week_ahead" | "wa:<group-jid-without-@g.us>",
  "source_message_id": "<wa-msg-id>" | "newsletter:<doc-id>",
  "source_excerpt": "<≤500 chars of the EXACT source text>",
  "applies_to_year_groups": ["Year 3"] | ["all"] | ["Year 5"] | …,
  "target_audience_detected": "Year 3" | "all-junior" | "Year 5" | "ambiguous",
  "verification_status": "verified" | "ambiguous" | "rejected",
  "parent_safe": true | false,
  "rejection_reason": null | "<short reason>"
}
```

`bsc-agent-safe-send.py` blocks the send if:

- `items[]` missing or empty
- Any item with `verification_status != "verified"` or `parent_safe != true`
- Any item whose `source` starts with `ical` / `calendar` or `source_message_id` starts with `ical-`
- Any `applies_to_year_groups` that doesn't include Year 3 or all-junior
- `final_message` containing Year 4, Year 5-9, sixth form, senior school explicit strings
- Any bullet line containing KS1/KS2/whole-Junior wording without an explicit Year-3 marker on the same line
- `decision != "SEND"`, `audience` not in `("Year 3", "Year 3 parents")`, target_group != PUBLIC, empty/over-4000-char message, missing/empty `evidence`, non-empty `risk_flags`.

### 3.8 WEEK_AHEAD parser (`parse_week_ahead`)

- Regex matches uppercase month abbreviations only (e.g. `15th JUN`) to avoid colliding with prose dates ("Tuesday, 16th June") in the Notices section.
- 14 `YEAR_GROUP_PATTERNS` for Year 1–6 / KS1-2 / Nursery / Reception / Playgroup / EYFS / Junior School / Whole School.
- `_y3_relevant()` is TRUE only if: explicit "Year 3" OR "Whole School" OR "Junior School" without a competing senior year.
- Footer regex stops the parser before it slurps "CONNECT WITH" / contact info / "Tuesday 23rd June" links.

### 3.9 Verification commands (run on the container)

```bash
# Per-item Year-3 gate + parser regression
cd /data/.ocplatform/workspace
python3 -m pytest tests/ -v

# End-to-end iCal-removal verification (script lives at /tmp/final-verify.py)
python3 /tmp/final-verify.py

# Audit log
tail -40 /data/.ocplatform/workspace/state/bsc-agent-drafts/audit.log

# Cron list
openclaw cron list
openclaw cron show <id> --json | python3 -c "import sys,json; print(json.load(sys.stdin)['payload']['message'])"
```

---

## 4. Prioritized next steps

### Priority 0 — Awaiting user decision (do this first)

**P0.1 Add 2pm SLT slot to Four-Hour Preview + Retry (openclaw side).** Change both crons' hours from `2,6,10,18,22` → `2,6,10,13,18,22` and add `urgent-1400` to the slot list in both prompts. Reversible via `openclaw cron edit`. *User asked, awaiting yes/no confirmation.*

**P0.2 Fix OS cron `urgent-1400` send time (15:00 SLT → 14:00 SLT).** Change `30 9 * * *` → `30 8 * * *` in root crontab. Eliminates the weekday double-send with the `30 9 * * 1-5` 3pm send. *User asked to investigate, awaiting yes/no.*

### Priority 1 — Reliability follow-ups still on the table

**P1.1 WhatsApp routing — code-level enforcement.** The Channel Reply Rule in `AGENTS.md` is prompt-only. The proposed direction (from the plan file): inspect `/data/.openclaw/agents/main/sessions/*.trajectory.jsonl` for WhatsApp-origin turns; if final text leaks back to webchat, wrap outbound to force `wacli send`. This needs help from Donely if OpenClaw exposes no hook. Damika has a Donely contact to ask.

**P1.2 Auditor tightening.** `BSC Public-Send Auditor` runs every 30 min. Make it every 5 min so out-of-band sends are detected faster.

**P1.3 Date/day-of-week label code check.** `BSC_HARD_RULES.md` already has the "Date/Day Accuracy Rule" requiring code-verified day labels. The audit failures (Sun vs Mon for 22 Jun; Tuesday 17 June when Tuesday is the 16th) need a pre-send script-side check, not just a rule in markdown.

**P1.4 72h dump window for low-traffic groups.** `BSC Sport & ECAs` had its last message 2026-06-12 — falls out of the 72h dump on Mon afternoon. Consider widening to 168h for the dump's `MESSAGES` section, or distinguishing "recent" from "still-relevant".

### Priority 2 — Deferred until post-VPS

Per memory `project_deferred_vps.md`: FreqAI + orderflow edge layers — unrelated to James, mentioned for context only.

### Priority 3 — Out of scope for the 2-week sprint

- Personalised parent DMs (postpone per user instruction).
- New dashboard / DB table for audit (single audit.log is enough for 2 weeks).
- A confidence-threshold model (too much for a 2-week fix).
- Reorganising `bsc-data-dump.py` outputs (the data is fine; the gap was reasoning).

---

## 5. Credentials and access

> Scope note: this is internal infrastructure on the user's own machine. The file lives under `~/Documents/James-Development/` which is the user's own filesystem. None of the values below are passwords or API keys — they are addresses, IDs, paths, and well-known endpoints. SSH is key-based; no password ever passes through the chat. Treat the WhatsApp JIDs as operational identifiers — they are not secrets in the cryptographic sense, but they identify private groups, so don't share them outside this project.

### 5.1 Remote container

```
Host           : REDACTED_TAILSCALE_IP   (Tailscale)
User           : root
Auth           : ssh key (no password) — assumed to be the macOS user's default ~/.ssh/id_*
Test command   : ssh -o ConnectTimeout=10 root@REDACTED_TAILSCALE_IP "uname -a"
Gateway port   : 18789 (OpenClaw)
Container HOME : /data
TZ             : Etc/UTC
Date check     : ssh root@REDACTED_TAILSCALE_IP 'date; date -u'
```

### 5.2 OpenClaw

```
Agent id       : main
Model          : donely/default
Harness        : OpenClaw 2026.5.6 / gitSha 7c70458
Cron CLI       : openclaw cron list | show <id> --json | edit <id> --message "<text>"
Trajectories   : /data/.openclaw/agents/main/sessions/*.trajectory.jsonl
Cron JSON      : /data/.openclaw/cron/jobs.json
Skills dir     : /data/.openclaw/skills/
```

### 5.3 wacli / WhatsApp

```
Account JID    : REDACTED_USER@s.whatsapp.net
Linked         : true
FTS5           : true
Store path     : /data/.wacli/
Send command   : wacli send text --to <jid> --message "<text>"
NEVER send directly to PUBLIC (REDACTED_JID@g.us) — always route through bsc-agent-safe-send.py
```

### 5.4 Local Mac

```
User           : damikaanupama
Email          : damikaanupama@gmail.com
Home           : /Users/damikaanupama
Plans          : /Users/damikaanupama/.claude/plans/
Memory         : /Users/damikaanupama/.claude/projects/-Users-damikaanupama/memory/
Skills (gstack): /Users/damikaanupama/.claude/skills/gstack/
This file      : /Users/damikaanupama/Documents/James-Development/PROJECT_STATE.md
```

### 5.5 People (escalation paths)

| Who | What they own |
|---|---|
| Damika (user) | Implementation, day-to-day operation, sends git commits. Wants short, terse responses with no trailing summaries. |
| Charitha | BSC operational decisions. The iCal removal was at her request. |
| Donely | OpenClaw platform team. Channel for any platform-level fix (e.g. WhatsApp routing hook). |

### 5.6 Backups

```
/root/bsc-consolidation-backups/<file>.<utc-timestamp>
```
Every file edited in Phase B onward has a timestamped backup here. Add one before any further edit on the container.

---

## 6. Quick-start for a brand-new session

1. **Read this file end-to-end.**
2. **Check the user's three memory files:**
   - `~/.claude/projects/-Users-damikaanupama/memory/project_deferred_vps.md`
   - `~/.claude/projects/-Users-damikaanupama/memory/project_portfolio_improvement.md`
   - `~/.claude/projects/-Users-damikaanupama/memory/feedback_git_commits.md` *(Damika runs git commit + push; Claude only stages and drafts.)*
3. **Sanity-check the container:**
   ```bash
   ssh root@REDACTED_TAILSCALE_IP 'date; openclaw cron list | head'
   ssh root@REDACTED_TAILSCALE_IP 'tail -5 /data/.ocplatform/workspace/state/bsc-agent-drafts/audit.log'
   ssh root@REDACTED_TAILSCALE_IP 'cd /data/.ocplatform/workspace && python3 -m pytest tests/ -q'
   ```
4. **Confirm where the user wants you to pick up.** Most likely: P0.1 + P0.2 from §4 (the 2pm slot + the OS cron 15:00 → 14:00 fix). Ask before editing the OS crontab.
5. **Always**: stage changes locally + back up on the container before edits; never `wacli send` to PUBLIC directly; never amend prior commits unless asked.

---

## 7. Open questions still in flight (last asked, unanswered)

These were posed to the user at the end of the current session:

1. **Apply the openclaw preview/retry cron edit to add 13:45/13:50 SLT slots for `urgent-1400`?** (Yes / Hold off)
2. **Fix the OS cron `urgent-1400` send time from `30 9 UTC` (15:00 SLT) to `30 8 UTC` (14:00 SLT)?** (Yes / Leave alone / Investigate further first)

Pick up from those decisions.
