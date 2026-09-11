#!/usr/bin/env python3
"""NestQuant Live Executor — Entry point for signal→order pipeline."""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("live_executor")

from execution.shadow.wine_flask_adapter import WineFlaskExecutionAdapter
from execution.shadow.live_executor import LiveExecutionRunner

ALL_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD",
    "AUD/USD", "NZD/USD", "EUR/GBP", "EUR/JPY", "EUR/CHF",
    "EUR/CAD", "EUR/AUD", "EUR/NZD", "GBP/JPY", "GBP/CHF",
    "GBP/CAD", "GBP/AUD", "GBP/NZD", "CHF/JPY", "CAD/JPY",
]


def main():
    parser = argparse.ArgumentParser(description="NestQuant Live Executor")
    parser.add_argument("--pairs", type=int, default=20, help="Number of pairs to trade")
    parser.add_argument("--poll", type=int, default=5, help="Poll interval in seconds")
    parser.add_argument("--log-dir", default="logs/shadow_live", help="Log directory")
    parser.add_argument("--risk", type=float, default=0.003, help="Risk per trade (fraction)")
    parser.add_argument("--iterations", type=int, default=None, help="Max iterations (None=forever)")
    parser.add_argument("--live", action="store_true", help="Enable live execution (REAL ORDERS)")
    args = parser.parse_args()

    enable_execution = args.live or os.environ.get("NESTQUANT_LIVE_MODE", "0") == "1"
    api_url = os.environ.get("MT5_API_URL", "http://127.0.0.1:5001")

    pairs = ALL_PAIRS[:args.pairs]

    logger.info(f"Live Executor starting")
    logger.info(f"  Mode: {'LIVE EXECUTION' if enable_execution else 'SHADOW'}")
    logger.info(f"  Pairs: {len(pairs)}")
    logger.info(f"  API: {api_url}")
    logger.info(f"  Risk: {args.risk*100:.1f}%")
    logger.info(f"  Poll: {args.poll}s")

    adapter = WineFlaskExecutionAdapter(base_url=api_url)
    if not adapter.connect():
        logger.error("Cannot connect to MT5 bridge. Aborting.")
        sys.exit(1)

    logger.info("Connected to MT5 bridge")

    runner = LiveExecutionRunner(
        adapter=adapter,
        pairs=pairs,
        poll_interval=args.poll,
        log_dir=args.log_dir,
        risk_per_trade=args.risk,
        enable_execution=enable_execution,
    )

    result = runner.run(iterations=args.iterations)

    logger.info(f"Executor finished: {result}")


if __name__ == "__main__":
    main()
