#!/usr/bin/env python3
"""Run live MR+TF engine on Pepperstone demo."""
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/root/logs/live_pepperstone.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

from ctrader_connector_new import CTraderConnector
from live_engine import LiveEngine

async def main():
    connector = CTraderConnector(
        client_id=os.environ['CTRADER_CLIENT_ID'],
        client_secret=os.environ['CTRADER_CLIENT_SECRET'],
        access_token=os.environ['CTRADER_ACCESS_TOKEN'],
        refresh_token=os.environ['CTRADER_REFRESH_TOKEN'],
        account_id='47828499',
        demo=True
    )

    engine = LiveEngine(connector, initial_balance=20.0)
    if not await engine.start():
        logger.error("Failed to start engine")
        return

    logger.info(f"Balance: ${connector.get_balance():.2f}")
    logger.info(f"Open positions: {len(engine.open_positions)}")
    logger.info("Starting live engine (interval=60s)...")
    try:
        await engine.run(interval_seconds=60)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        stats = engine.get_stats()
        logger.info(f"Final stats: {stats}")
        await connector.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
