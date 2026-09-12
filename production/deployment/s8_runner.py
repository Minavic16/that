#!/usr/bin/env python3
"""
NestQuant S8 Runner
====================
Entry point for the S8 live trading runtime.

Usage:
    python scripts/s8_runner.py --mode dry-run [--pairs EUR/USD] [--timeframe H4]
    python scripts/s8_runner.py --mode experimental-live [--pairs EUR/USD] [--timeframe H4]

Environment:
    NESTQUANT_LOG_LEVEL: Logging level (default: INFO)
    NESTQUANT_LOG_DIR: Log directory (default: /tmp/nestquant/logs)
    NESTQUANT_EXPERIMENTAL_LIVE: Must be "true" for --mode experimental-live
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on path
if PROJECT_ROOT not in sys.path:

from nestquant.production.execution.s8_runtime import RuntimeConfig, RuntimeMode, S8Runtime


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    log_dir = os.environ.get("NESTQUANT_LOG_DIR", "/tmp/nestquant/logs")
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"{log_dir}/s8_runtime.log"),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="NestQuant S8 Live Trading Runtime",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modes:\n"
            "  dry-run             Default. No real orders placed.\n"
            "  experimental-live   Real orders. Requires NESTQUANT_EXPERIMENTAL_LIVE=true.\n"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "experimental-live"],
        default="dry-run",
        help="Execution mode (default: dry-run)",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=["EUR/USD"],
        help="Currency pairs to trade (default: EUR/USD)",
    )
    parser.add_argument(
        "--timeframe",
        default="H4",
        choices=["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
        help="Timeframe for candles (default: H4)",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=60,
        help="Poll interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("NESTQUANT_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def main(runtime_factory=None) -> int:
    """Main entry point. runtime_factory defaults to S8Runtime."""
    from nestquant.production.execution.s8_runtime import S8Runtime as _S8Runtime
    _runtime_factory = runtime_factory or _S8Runtime

    args = parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger("s8_runner")
    logger.info("=" * 60)
    logger.info("NestQuant S8 Live Trading Runtime")
    logger.info("=" * 60)

    mode = RuntimeMode(args.mode)
    logger.info(f"Mode: {mode.value}")
    logger.info(f"Pairs: {args.pairs}")
    logger.info(f"Timeframe: {args.timeframe}")
    logger.info(f"Poll interval: {args.poll}s")

    if mode == RuntimeMode.EXPERIMENTAL_LIVE:
        env_auth = os.environ.get("NESTQUANT_EXPERIMENTAL_LIVE")
        if env_auth != "true":
            logger.critical(
                "REFUSING to start experimental-live mode. "
                "Set NESTQUANT_EXPERIMENTAL_LIVE=true to authorize."
            )
            return 1
        logger.warning("EXPERIMENTAL-LIVE mode authorized. Real orders will be placed.")

    config = RuntimeConfig(
        pairs=tuple(args.pairs),
        timeframe=args.timeframe,
        poll_interval_seconds=args.poll,
        mode=mode,
    )

    runtime = _runtime_factory(config=config)

    try:
        runtime.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt - shutting down")
        runtime.stop()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1
    finally:
        runtime._restore_signals()

    logger.info("S8 runner exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
