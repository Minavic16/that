#!/usr/bin/env python3
"""
Run S7 shadow mode — historical replay over 4h bars, SHADOW ONLY.

No broker orders are ever sent. Intended orders are logged to JSONL
for fidelity/latency analysis.

Usage:
  python scripts/run_shadow.py                          # full 20-pair replay
  python scripts/run_shadow.py --pairs EUR/USD GBP/USD  # subset
  python scripts/run_shadow.py --limit-bars 500         # smoke test (last N bars per pair)
  python scripts/run_shadow.py --log-dir /tmp/shadow    # alternate output
  python scripts/run_shadow.py --data-dir /root/data    # override data root

Logs:
  <log_dir>/signals.jsonl, bars.jsonl, infrastructure.jsonl,
  intended_orders.jsonl, lifecycle.jsonl, state.json, KILL (sentinel)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure `nestquant` import works when invoked as `python scripts/run_shadow.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Shadow imports require NESTQUANT_SKIP checks not to fail on missing secrets
import os

os.environ.setdefault("NESTQUANT_SKIP_LIVE_CHECK", "1")
os.environ.setdefault("NESTQUANT_SKIP_DASHBOARD_CHECK", "1")

from nestquant.execution.shadow.runner import ShadowRunner


def main() -> None:
    p = argparse.ArgumentParser(description="S7 shadow replay (no live orders)")
    p.add_argument("--pairs", nargs="*", default=None, help="Subset of pairs, e.g. EUR/USD GBP/USD")
    p.add_argument("--timeframe", default="4h", help="Timeframe (default 4h)")
    p.add_argument("--data-dir", default=None, help="Data root (default from config)")
    p.add_argument("--log-dir", default="logs/shadow", help="Output directory for JSONL logs")
    p.add_argument("--state-path", default=None, help="State file path (default <log_dir>/state.json)")
    p.add_argument("--limit-bars", type=int, default=None, help="Cap bars per pair (smoke test)")
    p.add_argument("--no-lifecycle", action="store_true", help="Disable shadow lifecycle exits")
    args = p.parse_args()

    runner = ShadowRunner(
        pairs=args.pairs,
        timeframe=args.timeframe,
        data_dir=args.data_dir,
        log_dir=args.log_dir,
        state_path=args.state_path,
        limit_bars=args.limit_bars,
        enable_lifecycle=not args.no_lifecycle,
    )

    # Guard: never allow live adapter to be imported in this process
    for mod in list(sys.modules):
        if "MetaTrader5" in mod or "mt5" in mod.lower():
            raise RuntimeError(f"Broker module loaded in shadow process: {mod}")

    summary = runner.run()

    # Print summary as JSON for scripting
    print(json.dumps(
        {
            "run_id": summary.run_id,
            "pairs": summary.pairs,
            "bars_processed": summary.bars_processed,
            "signals_emitted": summary.signals_emitted,
            "shadow_positions_opened": summary.shadow_positions_opened,
            "shadow_positions_closed": summary.shadow_positions_closed,
            "elapsed_seconds": round(summary.elapsed_seconds, 2),
            "health_status": summary.health["status"] if summary.health else None,
            "state_path": summary.state_path,
            "log_dir": summary.log_dir,
        },
        indent=2,
    ))

    # Exit code reflects health (CI-friendly)
    status = (summary.health or {}).get("status", "HEALTHY")
    if status == "FAILED":
        sys.exit(2)
    elif status == "DEGRADED":
        sys.exit(1)


if __name__ == "__main__":
    main()
