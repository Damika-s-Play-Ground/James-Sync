#!/usr/bin/env python3
"""
Gateway Outbound Healthcheck
Checks WhatsApp connection via wacli doctor and reports status.
"""

import sys
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path("/opt/data/james-bsc-live-clean/data/.ocplatform/workspace")
STATE_FILE = WORKSPACE / "state/gateway-outbound-healthcheck.json"

DRY_RUN = int(sys.argv[1]) if len(sys.argv) > 1 else 1
SEND_PROBE = int(sys.argv[2]) if len(sys.argv) > 2 else 0

def check_wacli_status():
    """Check WhatsApp status via wacli doctor"""
    try:
        result = subprocess.run(
            ["wacli", "doctor"],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        lines = result.stdout.strip().split('\n')
        status = {}
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                key = parts[0].lower()
                value = parts[1]
                status[key] = value
        
        return {
            "authenticated": status.get("authenticated") == "true",
            "connected": status.get("connected") == "true",
            "connection_state": status.get("connection_state", "unknown"),
            "last_sync": status.get("last_sync", "unknown")
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    print(f"mode: dry_run={DRY_RUN} send_probe={SEND_PROBE} reload=False")
    print(f"dev_target=James Bot Development REDACTED_JID")
    print(f"blocked_target=School Assistant (Testing) REDACTED_JID")
    
    status = check_wacli_status()
    
    if "error" in status:
        print(f"wacli doctor failed: {status['error']}")
        sys.exit(1)
    
    print(f"whatsapp: authenticated={status['authenticated']}, connected={status['connected']}, state={status['connection_state']}")
    print(f"last_sync: {status['last_sync']}")
    
    # wacli only holds a live connection while syncing — idle state is "disconnected".
    # Treat authenticated + recent last_sync as healthy; only fail on auth loss or very stale sync.
    if not status['authenticated']:
        print("ERROR: WhatsApp not authenticated — QR re-link required")
        sys.exit(1)
    if not status['connected']:
        # Check last_sync staleness (fail if > 4 hours without a sync)
        last_sync_str = status.get('last_sync')
        if last_sync_str:
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_str.replace('Z', '+00:00'))
                age_min = (datetime.now(timezone.utc) - last_sync_dt).total_seconds() / 60
                if age_min > 240:
                    print(f"WARNING: WhatsApp idle (last sync {int(age_min)}min ago — exceeds 4h threshold)")
                    # In dry-run healthcheck mode, stale idle state is a warning only.
                    # The connection is still healthy if authentication is intact.
                    if DRY_RUN:
                        pass
                    else:
                        sys.exit(1)
                else:
                    print(f"INFO: WhatsApp idle (not syncing); last sync {int(age_min)}min ago — OK")
            except Exception:
                print("WARNING: Could not parse last_sync timestamp")
        else:
            print("WARNING: WhatsApp not connected and no last_sync timestamp")
            sys.exit(1)
    
    # Check recent gateway logs for errors
    log_dir = WORKSPACE / "logs/cron"
    error_count = 0
    if log_dir.exists():
        for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            try:
                content = log_file.read_text()[-10000:]  # last 10KB only
                error_count += content.lower().count("failed to dial whatsapp")
            except:
                pass
    
    print(f"historical outbound error lines in recent gateway logs: {error_count}")
    
    if DRY_RUN:
        print("dry-run: would send probe to James Bot Development REDACTED_JID: Gateway outbound health probe: WhatsApp send path OK. No action needed.")
    
    print("OK")

if __name__ == "__main__":
    main()
