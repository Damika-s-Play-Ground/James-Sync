# Live-clean wacli auth/watchdog troubleshooting notes

Use when a WhatsApp sync daemon or watchdog keeps restarting and `wacli sync` exits immediately.

## Diagnostic pattern

1. Do not assume the first `wacli` on `PATH` is the daemon-capable binary. Some npm/Baileys CLIs only support `login/chats/export` and return `unknown command 'sync'`.
2. Locate and source the workflow environment first, then run diagnostics with that environment:

```bash
source /opt/data/james-bsc-live-clean/hermes/env.sh
cd "$BSC_WORKSPACE"
wacli doctor --json
wacli auth status --json
```

3. If the daemon log repeats `not authenticated; run \\`wacli auth\\``, the sync process is not broken; the linked-device session is logged out and must be re-paired.
4. Check the PID in the store lock, but verify it with `ps`; stale lock owner metadata can remain even after the process has exited.
5. Very large daemon logs should be read from the end by line offset rather than loaded whole.

## Re-auth QR flow

For the daemon-capable Go `wacli`, generate a machine-readable QR without relying on terminal ASCII:

```bash
source /opt/data/james-bsc-live-clean/hermes/env.sh
timeout 600s wacli auth --qr-format text --events 2>&1 | tee /opt/data/bsc-wacli-auth.log
```

Extract the latest `qr_code` event and render it to a PNG. If Python `qrcode` is unavailable, use the globally installed Node package with `NODE_PATH`:

```bash
NODE_PATH=/opt/data/.npm-global/node_modules node - <<'JS'
const fs = require('fs');
const qrcode = require('qrcode');
const log = fs.readFileSync('/opt/data/bsc-wacli-auth.log','utf8');
let code = null;
for (const line of log.split(/\\n/)) {
  if (line.includes('"event":"qr_code"')) code = JSON.parse(line).data.code;
}
if (!code) throw new Error('no qr code found');
fs.writeFileSync('/opt/data/bsc-wacli-auth-qr.txt', code);
qrcode.toFile('/opt/data/bsc-wacli-auth-qr.png', code, {
  errorCorrectionLevel: 'M',
  margin: 4,
  width: 900,
}, (err) => {
  if (err) throw err;
  console.log('/opt/data/bsc-wacli-auth-qr.png');
});
JS
```

Send the PNG as native media immediately while the auth process is still alive, then poll the process and verify:

```bash
wacli auth status --json
wacli doctor --json
bash scripts/wacli-sync-watchdog.sh
ps -eo pid,ppid,stat,etime,cmd | grep -E '[w]acli sync|[w]acli-sync-daemon'
```

## Pitfalls

- `wacli sync --follow` may fail against the wrong binary even though the workflow's bundled `wacli` supports it.
- `wacli sync` never shows QR; use `wacli auth --qr-format text --events` for re-pairing.
- Do not report the daemon as fixed until auth is confirmed and sync remains running.
