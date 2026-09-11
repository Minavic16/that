#!/usr/bin/env python3
# logger.py - Structured logging for GFT dispute evidence

import logging
import os
from datetime import datetime

LOG_DIR = '/root/nestquant/logs'
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'nestquant.log'),
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("nestquant")

def log_event(event_type, symbol, price, pnl=None, reason=None, floating_pnl=None):
    """Log every trade event for GFT payout dispute evidence"""
    msg = f"EVENT={event_type} | SYM={symbol} | PRICE={price:.5f}"
    if pnl is not None:
        msg += f" | PNL={pnl:.2f}"
    if floating_pnl is not None:
        msg += f" | FLOATING={floating_pnl:.2f}"
    if reason:
        msg += f" | REASON={reason}"
    logger.info(msg)