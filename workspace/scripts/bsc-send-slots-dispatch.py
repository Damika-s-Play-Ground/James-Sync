#!/usr/bin/env python3
"""bsc-send-slots-dispatch.py — hourly dispatcher for BSC public send slots.

Replaces the old-VM OS crontab entries. Runs every hour at :30 UTC (= :00
Asia/Colombo) via Hermes cron. Maps current Colombo time to scheduled slots,
pre-checks that a draft (.json or .hold) actually exists for slot+date, and
only then invokes bsc-agent-send-slot.py.

Why pre-check: send-slot alerts the DEV group when NO draft exists. Calling
it blindly every hour would spam DEV. This dispatcher stays silent when there
is nothing to send.

Slot map (Asia/Colombo):
    06:00  6am           target=today
    15:00  3pm           target=tomorrow
    15:00  urgent-1500   target=today   (may coexist with 3pm)
    03:00  urgent-0300   target=today
    07:00  urgent-0700   target=today
    11:00  urgent-1100   target=today
    14:00  urgent-1400   target=today
    19:00  urgent-1900   target=today
    23:00  urgent-2300   target=today

A slot fires if current time is within [slot_time, slot_time+15min) —
tolerates scheduler delay; hourly cadence prevents double-fire.
Exit code is always 0 (dispatch failures are logged, never fatal).
"""
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WS = pathlib.Path(os.environ.get(
    "BSC_WORKSPACE",
    "/opt/data/james-bsc-live-clean/data/.ocplatform/workspace",
))
ROOT = WS / "state" / "bsc-agent-drafts"
SLT = ZoneInfo("Asia/Colombo")
WINDOW_MIN = 15

# (hour, minute) -> list of (slot, target)
SCHEDULE = {
    (3, 0):  [("urgent-0300", "today")],
    (6, 0):  [("6am", "today")],
    (7, 0):  [("urgent-0700", "today")],
    (11, 0): [("urgent-1100", "today")],
    (14, 0): [("urgent-1400", "today")],
    (15, 0): [("3pm", "tomorrow"), ("urgent-1500", "today")],
    (19, 0): [("urgent-1900", "today")],
    (23, 0): [("urgent-2300", "today")],
}


def log(msg: str):
    print(f"{datetime.now(SLT).isoformat()} {msg}", flush=True)


def resolve_draft_id(slot: str, target: str, today) -> str:
    d = today if target == "today" else today + timedelta(days=1)
    return f"{d.isoformat()}-{slot}"


def main():
    now = datetime.now(SLT)
    today = now.date()
    fired_any = False

    for (h, m), slots in sorted(SCHEDULE.items()):
        slot_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if not (slot_dt <= now < slot_dt + timedelta(minutes=WINDOW_MIN)):
            continue
        for slot, target in slots:
            draft_id = resolve_draft_id(slot, target, today)
            has_json = (ROOT / f"{draft_id}.json").exists()
            has_hold = (ROOT / f"{draft_id}.hold").exists()
            if not (has_json or has_hold):
                continue  # silent skip — no DEV spam
            log(f"firing slot={slot} target={target} draft={draft_id} "
                f"({'json' if has_json else 'hold'})")
            r = subprocess.run(
                [sys.executable, str(WS / "scripts" / "bsc-agent-send-slot.py"),
                 "--slot", slot, "--target", target],
                text=True, capture_output=True, timeout=300,
            )
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if out:
                log(f"  stdout: {out[:500]}")
            if err:
                log(f"  stderr: {err[:500]}")
            log(f"  exit={r.returncode}")
            fired_any = True

    if not fired_any:
        log("no eligible slots this tick")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never fail loudly from the scheduler's POV
        log(f"DISPATCH ERROR: {e}")
    sys.exit(0)
