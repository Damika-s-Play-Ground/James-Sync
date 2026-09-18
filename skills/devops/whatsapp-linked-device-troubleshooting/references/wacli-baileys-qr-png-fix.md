# wacli / Baileys QR PNG fix

Session-derived troubleshooting note for a WhatsApp linked-device login helper using `@whiskeysockets/baileys` and `@pc_style/wacli`.

## Symptoms

- `wacli login` exits with `WhatsApp connection closed before it was ready.`
- A custom Baileys QR helper can generate terminal QR output, but the user reports no usable QR or repeated timeouts.
- The helper writes a raw QR text file but no PNG image, or the PNG path is stale from an earlier attempt.
- Session directory such as `/opt/data/.local/share/dev.pcstyle.wacli/session` remains empty after attempts.

## Debug findings

- The `wacli` executable can be a Bun bundle with shebang `#!/usr/bin/env bun`; running helper code with `node` may fail ESM dependency resolution even when the packaged CLI works.
- A helper script that does:

```js
spawnSync('python3', ['-c', `import sys, qrcode\\n...`], { input: qr });
```

can silently fail when Python package `qrcode` is missing. If the return status is ignored, the script still prints `PNG saved at: ...` even though no PNG was created.

## Fix pattern

1. Install Node QR generation dependency into a prefix reachable by the helper:

```bash
npm install --prefix /opt/data/.npm-global qrcode --no-audit --no-fund
```

2. Patch the helper imports:

```js
import qrcodeTerminal from 'qrcode-terminal';
import qrcode from 'qrcode';
```

3. Replace Python subprocess PNG generation with native Node/Bun QR generation:

```js
await writeFile(qrTxt, qr);
await qrcode.toFile(qrPng, qr, { errorCorrectionLevel: 'M', margin: 4, width: 900 });
console.log('\\nScan this QR code with WhatsApp: Settings/Linked devices -> Link a device');
console.log('PNG saved at:', qrPng, '\\n');
qrcodeTerminal.generate(qr, { small: true });
```

4. Run the helper with Bun, not Node, and keep it alive long enough for scanning:

```bash
PATH=/opt/data/bin:$PATH \\
HOME=/opt/data \\
NODE_PATH=/opt/data/.npm-global/lib/node_modules/@pc_style/wacli/node_modules:/opt/data/.npm-global/node_modules \\
WACLI_QR_TIMEOUT_MS=600000 \\
/opt/data/bin/bun /opt/data/wacli-login-qr.mjs
```

5. Verify the PNG before sending:

```bash
stat -c '%y %s %n' /opt/data/wacli-login-qr.png /opt/data/wacli-login-qr.txt
python3 - <<'PY'
from pathlib import Path
print(Path('/opt/data/wacli-login-qr.png').read_bytes()[:8])  # b'\\x89PNG\\r\\n\\x1a\\n'
PY
```

## Operational note

If QR generation succeeds but the process times out, that specific run only means the QR was not scanned before expiry. Regenerate a fresh QR immediately before asking the user to scan, send it as native media, and keep the process running while they scan.
