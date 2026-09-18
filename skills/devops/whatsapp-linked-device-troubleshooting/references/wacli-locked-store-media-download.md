# wacli locked-store media download for WhatsApp replies

Use when a parent/group question asks the assistant to extract information from a just-forwarded WhatsApp document/image, but `wacli media download` fails because the live sync daemon holds the store lock.

## Scenario

- Group message references an adjacent forwarded document, e.g. "get the information from this and answer Umair".
- `wacli messages list --chat <group-jid> --limit N --json --full` shows the document message with `MediaType: document`, filename, `direct_path`, `media_key`, etc.
- `wacli media download ...` on the live store fails with:
  - `store is locked (another wacli is running?)`
  - `connection_state:"locked_by_other_process"`
  - live owner is often `wacli sync`.

## Safe workaround

Do not kill the live sync daemon just to download one attachment. Snapshot the store and download from the copy:

```bash
source /opt/data/james-bsc-live-clean/hermes/env.sh 2>/dev/null || true
rm -rf /opt/data/tmp/wacli-copy
mkdir -p /opt/data/tmp/wacli-copy /opt/data/tmp/media-download
cp -a "$WACLI_STORE_DIR/." /opt/data/tmp/wacli-copy/
rm -f /opt/data/tmp/wacli-copy/LOCK
wacli --store /opt/data/tmp/wacli-copy media download \
  --chat <chat_jid> \
  --id <media_msg_id> \
  --output /opt/data/tmp/media-download \
  --json
```

Then extract/read the downloaded file and reply to the original question using a quoted reply:

```bash
wacli send text \
  --to <chat_jid> \
  --reply-to <question_msg_id> \
  --reply-to-sender <question_sender_jid> \
  --mention <question_sender_jid> \
  --message '<answer>' \
  --json
```

## Notes

- This is appropriate for read/download work where a consistent-enough snapshot is acceptable. Do not use the copied store for writes that should affect the live database.
- If the attachment is a PDF and text extraction is needed, prefer deterministic extraction first (`pymupdf`, `pdftotext`, or OCR only if the PDF has no embedded text).
- Keep the answer source-bounded: if the PDF lacks a direct email/phone, say that explicitly instead of inferring private contact details.
- Preserve group context by quoting the parent’s actual question, not the forwarded document unless the document itself is the thing being answered.
