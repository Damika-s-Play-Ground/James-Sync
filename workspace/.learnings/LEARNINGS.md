
## [LRN-20260515-001] no_speculation_in_briefings

**Logged**: 2026-05-15T02:43:00Z
**Priority**: high
**Status**: pending
**Area**: automation

### Summary
Do not include inferred or speculative items in parent-facing BSC briefings.

### Details
User corrected: "If no cancellation is mentioned for that period don't assume it's continuing. Only include if stated in a source."

### Rule
Only include events, cancellations, or action items explicitly stated in:
1. BSC iCal calendar
2. WhatsApp group messages
3. Week Ahead newsletter
Never infer future state from past state.

### Metadata
- Source: user_feedback
- Tags: bsc, briefing, speculation, accuracy

---

## [LRN-20260611-Y3-AUDIENCE] Year 3 parent audience filtering (critical)

**Logged**: 2026-06-11T16:03:00Z
**Priority**: critical
**Status**: active
**Area**: bsc-reminders

### Summary
School Assistant (Testing) WhatsApp group contains Year 3 parents only. Do not include Year 4, Year 5/6, U15, or other age-group specific content in messages to this group.

### Details
Charitha corrected a draft that included Year 4 PTS Science assessment and U15 Basketball tournament in a Year 3-only message. The audience scope is: Year 3 / Y3-B / 3B explicit items, or whole-Junior / whole-school notices that genuinely apply to Year 3. Exclude Year 4/Y4/4B, Year 5/6, U13/U15, and other age-specific items unless they explicitly include Year 3 participation.

### Suggested Action
Before finalizing any BSC message to School Assistant (Testing), review each item and remove anything that does not directly apply to Year 3 students. Whole-school reminders (photos, canteen, parking, consent forms) are fine if they apply across year groups including Year 3. Sport/ECA/event notices must explicitly include Year 3 or be Junior-wide with Year 3 participation.

### Metadata
- Source: user_feedback
- Tags: bsc, audience, year-3, filtering
- Pattern-Key: bsc.year3_only_audience

---

## [LRN-20260611-DATE-RELEVANCE] Date-range validation before inclusion (critical)

**Logged**: 2026-06-11T16:05:00Z
**Priority**: critical
**Status**: active
**Area**: bsc-reminders

### Summary
Always validate that an item's date range includes the target day before adding it to a reminder. Do not include completed, stale, or future-only items.

### Details
Charitha caught me including "Individual/sibling photos (Monday 8–Wednesday 10 June)" in a Friday 12 June message. The photo window had already closed on Wednesday 10 June, so it should not have been in a Friday reminder. I saw the item in the Week Ahead and included it without checking whether Friday 12 fell within the Monday 8–Wednesday 10 range.

### Suggested Action
Before including any date-specific item:
1. Extract the explicit date range or target day from the source
2. Check if the reminder target day falls within that range
3. Exclude items where the target day is before the event starts or after the event ends
4. Apply this gate for all notices: events, deadlines, trips, photo sessions, forms, etc.

This is the same date discipline already documented in BSC reminder regression rules — now saved as a pre-inclusion gate, not just a post-correction check.

### Metadata
- Source: user_feedback
- Tags: bsc, date-validation, reminders, accuracy
- Pattern-Key: bsc.date_relevance_gate

---
