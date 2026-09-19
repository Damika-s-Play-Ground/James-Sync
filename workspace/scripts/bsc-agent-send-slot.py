#!/usr/bin/env python3
"""BSC agent send-slot: OS cron entry-point for exact-draft public delivery.

Dispatched hourly by scripts/bsc-send-slots-dispatch.py via Hermes cron
(job "James BSC Send Slots", wrapper /opt/data/scripts/james-bsc-send-slots.sh).
Can also be invoked manually:
    python3 bsc-agent-send-slot.py --slot=6am --target=today
    python3 bsc-agent-send-slot.py --slot=3pm --target=tomorrow
    python3 bsc-agent-send-slot.py --slot=urgent --target=today --draft-id=2026-06-13-urgent-0700

Resolves the draft-id from slot+target (or uses explicit --draft-id), then
calls bsc-agent-draft.py send on the stored exact draft.

Exit codes:
    0   — sent, already sent (SENT), or intentionally held (HOLD)
    1   — draft missing (no preview ran), validation failure, or send error
"""
from __future__ import annotations
import argparse, datetime as dt, os, pathlib, subprocess, sys
from zoneinfo import ZoneInfo

WS   = pathlib.Path(os.environ.get('BSC_WORKSPACE', '/opt/data/james-bsc-live-clean/data/.ocplatform/workspace'))
ROOT = WS / 'state' / 'bsc-agent-drafts'
DEV  = os.getenv('BSC_DEV_JID', 'REDACTED_JID')
SLT  = ZoneInfo('Asia/Colombo')

SLOT_SUFFIXES = {
    '6am':          '6am',
    '3pm':          '3pm',
    'weekly':       'weekly',
    'urgent-0700':  'urgent-0700',
    'urgent-1100':  'urgent-1100',
    'urgent-1400':  'urgent-1400',
    'urgent-1500':  'urgent-1500',
    'urgent-1900':  'urgent-1900',
    'urgent-2300':  'urgent-2300',
    'urgent-0300':  'urgent-0300',
}


def today_slt() -> dt.date:
    return dt.datetime.now(SLT).date()


def tomorrow_slt() -> dt.date:
    return today_slt() + dt.timedelta(days=1)


def resolve_draft_id(slot: str, target: str) -> str:
    """Resolve slot+target to a draft_id string like 2026-06-13-urgent-0700."""
    if target == 'today':
        d = today_slt()
    elif target == 'tomorrow':
        d = tomorrow_slt()
    else:
        d = dt.date.fromisoformat(target)

    # For generic --slot=urgent the caller must pass --draft-id explicitly,
    # but handle it gracefully by using today + slot as-is.
    suffix = SLOT_SUFFIXES.get(slot, slot)
    return f'{d.isoformat()}-{suffix}'


def wa_send_dev(text: str):
    try:
        subprocess.run(
            ['wacli', 'send', 'text', '--to', DEV, '--message', text],
            text=True, capture_output=True, timeout=30
        )
    except Exception:
        pass


def run_send(draft_id: str, force: bool = False) -> int:
    """Invoke bsc-agent-draft.py send and return its exit code."""
    cmd = [sys.executable, str(WS / 'scripts' / 'bsc-agent-draft.py'), 'send', draft_id]
    if force:
        cmd.append('--force')
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.stdout.strip():
        print(p.stdout.strip())
    if p.stderr.strip():
        print(p.stderr.strip(), file=sys.stderr)
    return p.returncode


def main():
    ap = argparse.ArgumentParser(description='BSC agent send-slot — OS cron entry-point')
    ap.add_argument('--slot',     required=True,
                    help='Slot name: 6am | 3pm | urgent | urgent-0700 | …')
    ap.add_argument('--target',   default='today',
                    help='Date target: today | tomorrow | YYYY-MM-DD')
    ap.add_argument('--draft-id', dest='draft_id', default=None,
                    help='Explicit draft_id (overrides slot+target resolution)')
    ap.add_argument('--force',    action='store_true',
                    help='Pass --force to bsc-agent-draft.py send (skip send_at check)')
    args = ap.parse_args()

    draft_id = args.draft_id or resolve_draft_id(args.slot, args.target)

    draft_file = ROOT / f'{draft_id}.json'
    hold_file  = ROOT / f'{draft_id}.hold'

    # No draft at all — preview job never ran or crashed
    if not draft_file.exists() and not hold_file.exists():
        msg = (f'SEND-SLOT SKIP — no draft found for {draft_id}\n'
               f'Preview job may not have run or may have crashed.\n'
               f'No public message sent.')
        print(msg, file=sys.stderr)
        wa_send_dev(msg)
        # Exit 0: no draft is not a hard failure (weekend/holiday expected)
        sys.exit(0)

    # .hold marker — primary ran and decided HOLD, nothing to send
    if hold_file.exists() and not draft_file.exists():
        print(f'HOLD — {draft_id} (no SEND draft, .hold marker present)')
        sys.exit(0)

    rc = run_send(draft_id, force=args.force)
    sys.exit(rc)


if __name__ == '__main__':
    main()
