#!/usr/bin/env python3
# risk_manager.py — Dynamic risk management for GFT prop account
# Risk scales from RISK_START_PCT (10%) down to RISK_MIN_PCT (5%)
# as drawdown progresses from 0% to MAX_DD_PCT (30%).

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config import (
    TICK_SIZES, PIP_VALUES, SLIPPAGE_BUFFER_PIPS, SL_ATR_MULTIPLIER,
    MAX_CONCURRENT_POSITIONS, FLOATING_LOSS_KILL_THRESHOLD,
    DAILY_LOSS_LIMIT, ACCOUNT_BALANCE, MAX_PROMOTION_SL_DISTANCE,
    RISK_START_PCT, RISK_MIN_PCT, MAX_DD_PCT,
)

# TICK SIZE & PIP VALIDATION
def validate_symbol_requirements(symbol):
    if symbol not in TICK_SIZES:
        raise ValueError(f"Unsupported symbol: {symbol}")
    return TICK_SIZES[symbol], PIP_VALUES[symbol]


def dynamic_risk_pct(current_dd_pct: float) -> float:
    """
    Return risk-per-trade % based on current drawdown.
    Linearly scales from RISK_START_PCT (at 0% DD) down to RISK_MIN_PCT (at MAX_DD_PCT).
    """
    if current_dd_pct <= 0.0:
        return RISK_START_PCT
    if current_dd_pct >= MAX_DD_PCT:
        return RISK_MIN_PCT
    fraction = current_dd_pct / MAX_DD_PCT
    return RISK_START_PCT - fraction * (RISK_START_PCT - RISK_MIN_PCT)


def calculate_lot_size(symbol, balance, current_dd_pct, sl_pips):
    """
    Calculate lot size using dynamic risk percentage.
    risk_$ = balance * dynamic_risk_pct(current_dd_pct)
    """
    tick_size, pip_value = validate_symbol_requirements(symbol)
    if symbol.endswith('JPY'):
        tick_size = 0.01
    risk_pct = dynamic_risk_pct(current_dd_pct)
    risk_dollars = balance * risk_pct
    lots = risk_dollars / (sl_pips * pip_value)
    return round(max(lots, 0.01), 3)


def get_effective_stop(entry_price, direction, raw_sl, symbol):
    buffer = SLIPPAGE_BUFFER_PIPS.get(symbol, 0.0003)
    if direction == 1:  # Long
        return max(entry_price - (raw_sl - buffer), 0)
    else:  # Short
        return min(entry_price + (raw_sl + buffer), 100000)


class RiskManager:
    def __init__(self):
        self.daily_pnl = 0
        self.trading_paused_until = None
        self.balance = ACCOUNT_BALANCE
        self.peak_balance = ACCOUNT_BALANCE

    @property
    def dd_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance * 100.0

    @property
    def current_risk_pct(self) -> float:
        return dynamic_risk_pct(self.dd_pct)

    def check_market_regime(self, price_data_5m):
        if len(price_data_5m) < 12:
            return True, "OK"
        returns = np.log(price_data_5m['close'] / price_data_5m['close'].shift(1))
        vol_5m = returns.rolling(12).std() * np.sqrt(252*288)
        if vol_5m.iloc[-1] > 0.50:
            vol_pct = round(vol_5m.iloc[-1]*100, 1)
            self.log_event("VOLATILITY_BLOCK", "ALL", price_data_5m['close'].iloc[-1],
                          reason=f"Annualized vol >50% ({vol_pct}%)")
            return False, "EXTREME VOLATILITY — ENTRIES BLOCKED"
        last = price_data_5m.iloc[-1]
        gap = abs(last['close'] - last['open']) / last['open']
        if gap > 0.01:
            gap_pct = round(gap*100, 2)
            self.log_event("GAP_BLOCK", last['symbol'], last['close'],
                          reason=f"Candle gap >1% ({gap_pct}%)")
            return False, "GAP DETECTED — ENTRIES BLOCKED"
        return True, "OK"

    def emergency_close_all(self, connector):
        open_positions = connector.get_open_positions()
        if not open_positions:
            return
        for pos in open_positions:
            connector.close_position(pos.id)
            self.log_event("EMERGENCY_CLOSE", pos.symbol, pos.current_price,
                          pnl=pos.unrealized_pnl,
                          reason="Floating loss kill switch")
        self.daily_pnl = -FLOATING_LOSS_KILL_THRESHOLD
        self.trading_paused_until = datetime.now() + timedelta(hours=24)
        self.log_event("KILL_SWITCH", "ALL", 0.0,
                      reason="Trading paused 24h after float kill")

    def log_event(self, event_type, symbol, price, pnl=None, reason=None):
        from logger import log_event
        log_event(event_type, symbol, price, pnl=pnl, reason=reason)