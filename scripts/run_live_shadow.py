#!/usr/bin/env python3
"""
Run S7 read-only live shadow — polls broker 4H candles, SHADOW ONLY.

No orders are ever sent. The hard guard terminates immediately if any
order path is touched.

Usage:
  python scripts/run_live_shadow.py --log-dir logs/shadow_live --poll 60
  python scripts/run_live_shadow.py --pairs EUR/USD GBP/USD --iterations 10  # test/demo
  python scripts/run_live_shadow.py --use-mt5  # attempt MT5 read-only (falls back to stub if unavailable)

Logs: <log_dir>/bars.jsonl, signals.jsonl, infrastructure.jsonl, state.json, orders_submitted_count.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import os
os.environ.setdefault("NESTQUANT_SKIP_LIVE_CHECK", "1")
os.environ.setdefault("NESTQUANT_SKIP_DASHBOARD_CHECK", "1")

from nestquant.execution.shadow.live_adapter import MT5ReadOnlyAdapter, StubLiveAdapter, WineFlaskReadOnlyAdapter
from nestquant.execution.shadow.live_runner import LiveShadowRunner


def main() -> None:
    p = argparse.ArgumentParser(description="S7 read-only live shadow (no orders)")
    p.add_argument("--pairs", nargs="*", default=None)
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--log-dir", default="logs/shadow_live")
    p.add_argument("--state-path", default=None)
    p.add_argument("--poll", type=float, default=60.0, help="Poll interval seconds")
    p.add_argument("--iterations", type=int, default=None, help="Max poll iterations (for demo/test, default infinite)")
    p.add_argument("--history-bars", type=int, default=None, help="For stub: replay last N bars as if live (default last bar only)")
    p.add_argument("--use-mt5", action="store_true", help="Use MT5 read-only adapter if available (otherwise stub)")
    p.add_argument("--use-wine-flask", action="store_true", help="Use Wine+Flask REST adapter (sesto-dev tutorial, http://mt5:5001, $0)")
    p.add_argument("--api-url", default=None, help="Override MT5 Flask API URL (default $MT5_API_URL or http://mt5:5001)")
    args = p.parse_args()

    if args.use_wine_flask:
        adapter = WineFlaskReadOnlyAdapter(base_url=args.api_url)
    elif args.use_mt5:
        adapter = MT5ReadOnlyAdapter()
    else:
        kwargs: dict = dict(data_dir=args.data_dir, timeframe=args.timeframe, pairs=args.pairs)
        if args.history_bars is not None:
            # Start N bars before end so live replay has history to process
            kwargs["start_idx"] = -args.history_bars
        adapter = StubLiveAdapter(**kwargs)
    # Pre-connect to surface early failures
    adapter.connect()

    runner = LiveShadowRunner(
        adapter=adapter,
        pairs=args.pairs,
        timeframe=args.timeframe,
        data_dir=args.data_dir,
        log_dir=args.log_dir,
        state_path=args.state_path,
        poll_interval_sec=args.poll,
        max_iterations=args.iterations,
    )
    result = runner.run()
    print(json.dumps(result, indent=2))
    # Exit code from health
    status = (result.get("health") or {}).get("status", "HEALTHY")
    if status == "FAILED":
        sys.exit(2)
    elif status == "DEGRADED":
        sys.exit(1)


if __name__ == "__main__":
    main()
