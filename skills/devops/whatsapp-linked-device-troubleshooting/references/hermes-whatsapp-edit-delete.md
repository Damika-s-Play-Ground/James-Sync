# Hermes WhatsApp edit/delete for bot-sent messages

Use when enabling, debugging, or extending Hermes's ability to edit or delete WhatsApp messages *it sent*.

## Split of responsibility

- Python adapter: `/opt/hermes/gateway/platforms/whatsapp.py`
  - `edit_message` → `POST http://127.0.0.1:{bridge_port}/edit` `{ chatId, messageId, message }`
  - `delete_message` → `POST …/delete` `{ chatId, messageId }`
- Live Node bridge (the one actually running): path from `platforms.whatsapp.extra.bridge_script` in config — currently `/opt/data/platforms/whatsapp/bridge/bridge.js` on port 3000.
- Upstream copy (do **not** overwrite live with this): `/opt/hermes/scripts/whatsapp-bridge/bridge.js`

If Python already has those methods and `/edit` works but delete 404s, the gap is the **live bridge**, not the adapter.

## Live vs upstream bridge

`diff` the two before copying anything. The live bridge has local gates the upstream copy dropped:

- Track `fromMe` IDs so later quotes count as reply-to-bot (`quotedFromBot`).
- Allowlist gates **DMs only**; groups are forwarded and gated in Python (`require_mention` / reply-to-bot / `free_response_chats`).

Port only the missing `/delete` (and key-store) pieces. Never wholesale-replace the live file.

## Baileys payloads

```js
await sock.sendMessage(chatId, { text, edit: key });   // edit
await sock.sendMessage(chatId, { delete: key });       // delete-for-everyone
```

`key` must be a WAMessageKey: `{ id, fromMe: true, remoteJid }`. Prefer the **stored** key from the original `sendMessage` result (includes participant / LID fields). Keep a `Map` of recent sent keys, not IDs alone.

WhatsApp only lets the sender edit/delete their own messages, within WhatsApp's time window.

## After a bridge.js change

The running `node bridge.js` process does not reload. Do **not** restart the gateway from inside the same WhatsApp chat (kills the in-flight session). Tell the user to send `/restart`.

## Cleanup of progress bubbles

Gateway auto-deletes tool-progress / busy bubbles after the final reply when:

```
display.platforms.whatsapp.cleanup_progress: true
```

Set with `hermes config set display.platforms.whatsapp.cleanup_progress true` (config.yaml is write-protected). Still needs `/restart` to take effect. Independent of `/edit` — this is `delete_message` after success.

## Verify

```bash
node --check /opt/data/platforms/whatsapp/bridge/bridge.js
curl -s -X POST http://127.0.0.1:3000/delete \
  -H 'Content-Type: application/json' -d '{}'
# Before restart: 404 Cannot POST /delete
# After /restart, missing fields: 400 chatId and messageId are required
```
