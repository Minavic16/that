#!/usr/bin/env python3
"""
Check S7 shadow health — reads shadow state + last log lines, prints verdict.

Usage:
  python scripts/check_shadow_health.py
  python scripts/check_shadow_health.py --log-dir logs/shadow
  python scripts/check_shadow_health.py --json   # machine-readable

Exit codes:
  0 = HEALTHY
  1 = DEGRADED (gaps, stale)
  2 = FAILED (kill switch, integrity violation, missing logs)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Resolve repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import os

os.environ.setdefault("NESTQUANT_SKIP_LIVE_CHECK", "1")
os.environ.setdefault("NESTQUANT_SKIP_DASHBOARD_CHECK", "1")

from nestquant.execution.shadow.kill_switch import KillSwitch
from nestquant.execution.shadow.state import ShadowState


def _tail_jsonl(path: Path, n: int = 5) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    out: list[dict] = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": line[:200]})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Check shadow health")
    p.add_argument("--log-dir", default="logs/shadow")
    p.add_argument("--json", action="store_true", help="Emit JSON only")
    args = p.parse_args()

    log_dir = Path(args.log_dir)
    state_path = log_dir / "state.json"
    infra_path = log_dir / "infrastructure.jsonl"
    signals_path = log_dir / "signals.jsonl"
    bars_path = log_dir / "bars.jsonl"

    # Load state
    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception as e:
            state = {"error": f"corrupt state: {e}"}
    else:
        state = {"error": "no state file — shadow has not run"}

    kill = KillSwitch(primary_path=log_dir / "KILL")
    kill_active = kill.is_active()

    # Count log lines
    def _count(p: Path) -> int:
        if not p.exists():
            return 0
        try:
            return sum(1 for _ in p.open())
        except Exception:
            return 0

    counts = {
        "signals": _count(signals_path),
        "bars": _count(bars_path),
        "infrastructure": _count(infra_path),
    }

    # Derive status
    status = "HEALTHY"
    notes: list[str] = []
    if "error" in state:
        status = "FAILED"
        notes.append(state["error"])
    if kill_active:
        status = "FAILED"
        notes.append(f"kill switch active at {kill.path()}")
    # Inspect last infra lines for ERROR without resolution
    if infra_path.exists():
        for rec in _tail_jsonl(infra_path, 10):
            if rec.get("event_type") == "ERROR" and rec.get("impact") in ("MISSED_SIGNAL", None):
                # For historical replay, single gap ERRORs are DEGRADED not FAILED
                if status != "FAILED":
                    status = "DEGRADED"
    if counts["bars"] == 0:
        status = "FAILED" if status == "HEALTHY" else status
        notes.append("no bars logged")

    payload = {
        "status": status,
        "state": state,
        "kill_switch_active": kill_active,
        "counts": counts,
        "last_infra": _tail_jsonl(infra_path, 3),
        "checks": {
            "state_exists": state_path.exists(),
            "kill_clear": not kill_active,
            "has_bars": counts["bars"] > 0,
            "has_signals_file": signals_path.exists(),
        },
        "notes": notes,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"status={status}")
        print(f"state: {state_path} exists={state_path.exists()}")
        if state.get("run_id"):
            print(f"  run_id={state['run_id']} updated={state.get('updated_at')}")
            lb = state.get("last_bar", {})
            print(f"  last_bar pairs={len(lb)} counters={state.get('counters')}")
        print(f"kill: {kill.path()} active={kill_active}")
        print(f"counts: {counts}")
        for n in notes:
            print(f"note: {n}")
        if payload["last_infra"]:
            print("last infra:")
            for r in payload["last_infra"]:
                print(f"  {r}")

    sys.exit(0 if status == "HEALTHY" else (1 if status == "DEGRADED" else 2))


if __name__ == "__main__":
    main()
