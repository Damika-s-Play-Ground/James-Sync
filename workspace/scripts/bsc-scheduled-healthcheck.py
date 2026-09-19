#!/usr/bin/env python3
"""Healthcheck for BSC scheduled parent-message cron wrappers.

Prints nothing when healthy. Prints ALERT lines and exits non-zero when:
- scheduled/safe-send Python fails py_compile;
- a job log's latest completion marker is failed;
- no successful completion marker exists within the expected freshness window.
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WS = Path(os.environ.get("BSC_WORKSPACE", "/opt/data/james-bsc-live-clean/data/.ocplatform/workspace"))
LOG_DIR = WS / "logs" / "cron"
JOBS = {
    "daily-6am-summary": (LOG_DIR / "BSC_Scheduled_6am_Summary.hermes.log", timedelta(hours=26)),
    "daily-3pm-reminder": (LOG_DIR / "BSC_Scheduled_3pm_Reminder.hermes.log", timedelta(hours=26)),
    "weekly-sunday-summary": (LOG_DIR / "BSC_Scheduled_Weekly_Summary.hermes.log", timedelta(days=8)),
}
COMPLETED_RE = re.compile(r"\[(?P<ts>[^\]]+)\] completed job=(?P<job>\S+) status=(?P<status>\S+)(?: rc=(?P<rc>\d+))?")


def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def compile_check() -> list[str]:
    files = [WS / "scripts" / "bsc_scheduled_jobs.py", WS / "scripts" / "bsc-agent-safe-send.py"]
    r = subprocess.run([sys.executable, "-m", "py_compile", *map(str, files)], text=True, capture_output=True, timeout=60)
    if r.returncode == 0:
        return []
    return ["py_compile failed for scheduled send path", (r.stdout + r.stderr).strip()[-1000:]]


def latest_marker(log_path: Path, job: str):
    if not log_path.exists():
        return None
    latest = None
    for line in log_path.read_text(errors="replace").splitlines()[-500:]:
        m = COMPLETED_RE.search(line)
        if m and m.group("job") == job:
            latest = {"ts": parse_ts(m.group("ts")), "status": m.group("status"), "rc": m.group("rc"), "line": line}
    return latest


def main() -> int:
    alerts = compile_check()
    now = datetime.now(timezone.utc)
    for job, (log_path, max_age) in JOBS.items():
        marker = latest_marker(log_path, job)
        if marker is None:
            alerts.append(f"{job}: no wrapper completion marker found in {log_path}")
            continue
        age = now - marker["ts"]
        if marker["status"] != "ok":
            alerts.append(f"{job}: latest wrapper completion failed: {marker['line']}")
        elif age > max_age:
            alerts.append(f"{job}: latest ok completion stale ({age} old; max {max_age})")
    if alerts:
        print("BSC SCHEDULED CRON HEALTH ALERT")
        for a in alerts:
            if a:
                print(f"- {a}")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
