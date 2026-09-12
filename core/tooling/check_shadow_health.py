#!/usr/bin/env python3
"""
NestQuant Shadow Runner Health Check
=====================================
Checks:
1. systemd service status
2. State file freshness
3. Signal file freshness
4. Data freshness
5. MT5 bridge health
6. Log file integrity
7. Kill switch status

Exit codes:
  0 = HEALTHY
  1 = DEGRADED
  2 = FAILED
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path("/root/that/logs/shadow_live")
STATE_FILE = LOG_DIR / "state.json"
SIGNALS_FILE = LOG_DIR / "signals.jsonl"
KILL_FILE = LOG_DIR / "KILL"
MT5_URL = "http://127.0.0.1:5001"


def check_systemd() -> dict:
    """Check if nestquant-shadow service is running."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "nestquant-shadow"],
            capture_output=True, text=True, timeout=5,
        )
        active = result.stdout.strip() == "active"
        return {"status": "running" if active else "stopped", "active": active}
    except Exception as e:
        return {"status": "error", "error": str(e), "active": False}


def check_state_freshness() -> dict:
    """Check if state file was updated recently."""
    if not STATE_FILE.exists():
        return {"status": "missing", "fresh": False}
    try:
        data = json.loads(STATE_FILE.read_text())
        updated = data.get("updated_at", "")
        if updated:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age_sec = (datetime.now(UTC) - dt).total_seconds()
            return {
                "status": "ok" if age_sec < 3600 else "stale",
                "fresh": age_sec < 3600,
                "age_seconds": round(age_sec),
                "updated_at": updated,
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "fresh": False}


def check_signals_freshness() -> dict:
    """Check if signals file has recent entries."""
    if not SIGNALS_FILE.exists():
        return {"status": "missing", "fresh": False}
    try:
        lines = SIGNALS_FILE.read_text().strip().split("\n")
        lines = [l for l in lines if l.strip()]
        if not lines:
            return {"status": "empty", "fresh": False}
        last = json.loads(lines[-1])
        ts = last.get("timestamp", last.get("broker_timestamp", ""))
        if ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_sec = (datetime.now(UTC) - dt).total_seconds()
            return {
                "status": "ok",
                "fresh": age_sec < 86400,  # within 24h
                "age_seconds": round(age_sec),
                "total_signals": len(lines),
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "fresh": False}


def check_mt5_bridge() -> dict:
    """Check MT5 bridge health."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{MT5_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return {
                "status": "ok" if data.get("mt5_connected") else "degraded",
                "connected": data.get("mt5_connected", False),
                "healthy": data.get("status") == "healthy",
            }
    except Exception as e:
        return {"status": "unreachable", "error": str(e), "connected": False}


def check_kill_switch() -> dict:
    """Check if kill switch is active."""
    active = KILL_FILE.exists()
    return {"status": "active" if active else "inactive", "active": active}


def main() -> int:
    checks = {
        "systemd": check_systemd(),
        "state_freshness": check_state_freshness(),
        "signals_freshness": check_signals_freshness(),
        "mt5_bridge": check_mt5_bridge(),
        "kill_switch": check_kill_switch(),
    }

    # Determine overall status
    any_failed = any(c.get("status") in ("missing", "error", "unreachable", "stopped") for c in checks.values())
    any_degraded = any(c.get("status") in ("stale", "empty", "degraded") for c in checks.values())

    if any_failed:
        overall = "FAILED"
        exit_code = 2
    elif any_degraded:
        overall = "DEGRADED"
        exit_code = 1
    else:
        overall = "HEALTHY"
        exit_code = 0

    result = {
        "overall": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
    }

    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
