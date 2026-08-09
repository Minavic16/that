"""
risk_manager.py — Sizing only, no circuit breakers
===================================================
Strategy works freely. Position size scales with signal strength.
$20 account, 1:500 leverage, 0.01 micro lot minimum.
"""

from __future__ import annotations
import logging
from config import (
    RISK_PER_TRADE, INITIAL_BALANCE, MIN_LOT_SIZE, MAX_LOT_SIZE,
    MIN_DIVERGENCE, DYNAMIC_LOT_SCALING,
)

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, initial_balance: float = INITIAL_BALANCE,
                 risk_pct: float = RISK_PER_TRADE):
        self.initial_balance = initial_balance
        self.risk_pct = risk_pct
        self.balance = initial_balance
        self.peak_balance = initial_balance
        self.total_trades = 0
        self.daily_gross_loss = 0.0

    def reset_daily(self):
        self.daily_gross_loss = 0.0

    def can_trade(self):
        return True, "OK (free mode)"

    def calculate_lot_size(self, pair: str, entry_price: float,
                           stop_price: float, divergence: float = MIN_DIVERGENCE) -> float:
        base_lot = MIN_LOT_SIZE

        if DYNAMIC_LOT_SCALING and divergence > 0:
            mult = max(1.0, divergence / MIN_DIVERGENCE)
            mult = min(mult, 5.0)
            lot_size = base_lot * mult
        else:
            lot_size = base_lot

        lot_size = round(lot_size, 2)
        lot_size = max(MIN_LOT_SIZE, min(lot_size, MAX_LOT_SIZE))

        logger.debug(
            f"{pair}: div={divergence:.1f}, lots={lot_size}, "
            f"balance=${self.balance:.2f}"
        )
        return lot_size

    def record_trade(self, pnl: float):
        self.balance += pnl
        if pnl < 0:
            self.daily_gross_loss += abs(pnl)
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        self.total_trades += 1

    @property
    def dd_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance * 100

    @property
    def total_return_pct(self) -> float:
        return (self.balance / self.initial_balance - 1.0) * 100.0

    def summary(self) -> dict:
        return {
            "balance": round(self.balance, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "total_trades": self.total_trades,
        }

    def __repr__(self) -> str:
        return (
            f"RiskManager(balance=${self.balance:,.2f}, "
            f"return={self.total_return_pct:.1f}%, "
            f"trades={self.total_trades})"
        )
