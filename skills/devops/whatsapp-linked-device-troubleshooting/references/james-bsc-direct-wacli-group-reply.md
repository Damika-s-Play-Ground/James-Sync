# James/BSC direct wacli group reply recovery

Use when a user asks for a one-off reply/send into the School Assistant Testing group or another James/BSC WhatsApp group and the generic messaging bridge target is ambiguous, errors, or risks misrouting.

## Durable lesson

For James/BSC parent/school group replies, the workflow-bundled Go `wacli` is the authoritative sender because it knows the live-clean store, group JIDs, quoting flags, and send receipts. Generic `send_message` targets can list bare numeric WhatsApp groups and may not preserve the `@g.us` group JID correctly; if there is any ambiguity, switch to direct `wacli send text` rather than retrying the same failing bridge send.

## Known-good sequence

1. Load `/opt/data/james-bsc-live-clean/hermes/env.sh` to get the live store and centralized JIDs:
   - `BSC_PUBLIC_JID=REDACTED_JID@g.us`
   - `BSC_DEV_JID=REDACTED_JID@g.us`
2. Use the workflow binary after sourcing env (`/opt/data/james-bsc-live-clean/bin/wacli` via PATH), not the npm/Baileys `/opt/data/bin/wacli`.
3. Read the relevant group history with read-only message search/list and identify the target question's message ID plus sender JID.
4. Send a quoted reply with:
   - `wacli send text --to "$BSC_PUBLIC_JID"`
   - `--reply-to <message-id>`
   - `--reply-to-sender <sender-jid>` for group replies
   - `--mention <sender-jid>` when the reply is directed to a named parent
   - `--json --timeout 60s`
5. Verify success from the returned JSON (`success:true`, `sent:true`, `to:<group-jid>`, message `id`) and stop. Do not build retry loops.

## Pitfalls

- If `send_message` returns a WhatsApp bridge/JID decode error for a group target, do not retry identical arguments.
- If adding `@g.us` to a `send_message` target causes delivery to a home/DM channel, treat it as misrouting and immediately switch to direct `wacli`.
- Do not report success until the group JID in the sender output matches the intended group.
- Keep the final status terse for Damika; parent-trust incidents need action first, not explanation.
