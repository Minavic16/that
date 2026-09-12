"""
NestQuant Strategy — Trade Management
======================================

Forensic reproduction of research trade management logic.

Components:
- BreakevenManager: evaluates breakeven SL movement
- MaxHoldManager: evaluates maximum holding period exits
- TrailingStopManager: evaluates trailing stop SL movement
- TradeLifecycleManager: orchestrates all trade management

Event ordering (matches research):
1. SL check (may exit)
2. TP check (may exit)
3. Max hold check (may exit)
4. IF no exit: trailing → breakeven (may move SL)
"""

from nestquant.production.strategy.trade_management.breakeven import BreakevenConfig, BreakevenManager
from nestquant.production.strategy.trade_management.max_hold import MaxHoldConfig, MaxHoldManager, MaxHoldResult
from nestquant.production.strategy.trade_management.trailing_stop import TrailingStopConfig, TrailingStopManager
from nestquant.production.strategy.trade_management.manager import (
    TradeAction,
    TradeState,
    MarketUpdate,
    TradeDecision,
    TradeLifecycleManager,
)

__all__ = [
    "BreakevenConfig",
    "BreakevenManager",
    "MaxHoldConfig",
    "MaxHoldManager",
    "MaxHoldResult",
    "TrailingStopConfig",
    "TrailingStopManager",
    "TradeAction",
    "TradeState",
    "MarketUpdate",
    "TradeDecision",
    "TradeLifecycleManager",
]
