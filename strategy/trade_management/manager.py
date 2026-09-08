"""
NestQuant Strategy — Trade Lifecycle Manager
=============================================

Central orchestrator for managing an open position's trade management.

Reproduces the exact event ordering from the research implementation:

    1. SL check (may exit)
    2. TP check (may exit)
    3. Max hold check (may exit)
    4. IF no exit:
       a. Trailing stop update (may move SL)
       b. Breakeven check (may move SL)
    5. Return decision

This component does NOT execute broker orders.
It returns decisions: HOLD, MOVE_STOP, EXIT.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from strategy.trade_management.breakeven import BreakevenConfig, BreakevenManager
from strategy.trade_management.max_hold import MaxHoldConfig, MaxHoldManager
from strategy.trade_management.trailing_stop import TrailingStopConfig, TrailingStopManager


class TradeAction(Enum):
    """Action returned by the trade lifecycle manager."""
    HOLD = "HOLD"
    MOVE_STOP = "MOVE_STOP"
    EXIT = "EXIT"


@dataclass(frozen=True)
class TradeState:
    """Current state of an open position."""
    direction: int  # 1 = LONG, -1 = SHORT
    entry_price: float
    current_sl: float
    take_profit: float
    risk_pips: float
    pip_size: float
    bars_held: int
    entry_idx: int


@dataclass(frozen=True)
class MarketUpdate:
    """Market data for the current bar."""
    open: float
    high: float
    low: float
    close: float
    prev_swing_low: float  # Previous bar's confirmed swing low
    prev_swing_high: float  # Previous bar's confirmed swing high


@dataclass(frozen=True)
class TradeDecision:
    """Decision returned by the trade lifecycle manager."""
    action: TradeAction
    new_sl: Optional[float] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None


class TradeLifecycleManager:
    """
    Manages the complete trade lifecycle for a single position.

    Reproduces the exact behavior of the research simulation engine.
    """

    def __init__(
        self,
        breakeven_config: BreakevenConfig | None = None,
        max_hold_config: MaxHoldConfig | None = None,
        trailing_config: TrailingStopConfig | None = None,
    ):
        self.breakeven = BreakevenManager(breakeven_config)
        self.max_hold = MaxHoldManager(max_hold_config)
        self.trailing = TrailingStopManager(trailing_config)

    def evaluate(
        self,
        trade: TradeState,
        market: MarketUpdate,
    ) -> TradeDecision:
        """
        Evaluate trade management for the current bar.

        Reproduces the EXACT event ordering from research:
            1. SL check
            2. TP check
            3. Max hold check
            4. IF no exit: trailing + breakeven

        Args:
            trade: Current trade state
            market: Current bar market data

        Returns:
            TradeDecision with action and any SL changes or exit info
        """
        pip = trade.pip_size
        entry = trade.entry_price
        sl = trade.current_sl
        risk = trade.risk_pips
        bars = trade.bars_held

        # ─── Step 1: SL check ───────────────────────────────
        if trade.direction == 1:  # LONG
            if market.low <= sl and risk > 0:
                return TradeDecision(
                    action=TradeAction.EXIT,
                    exit_price=sl,
                    exit_reason="SL",
                )
        else:  # SHORT
            if market.high >= sl and risk > 0:
                return TradeDecision(
                    action=TradeAction.EXIT,
                    exit_price=sl,
                    exit_reason="SL",
                )

        # ─── Step 2: TP check ───────────────────────────────
        if trade.direction == 1:  # LONG
            tp = entry + risk * trade.take_profit / entry * entry  # Simplified
            # Actually: tp = entry + risk * rrr * pip (from research)
            # But take_profit already encodes this. Let me use the raw TP.
            if market.high >= trade.take_profit and risk > 0:
                return TradeDecision(
                    action=TradeAction.EXIT,
                    exit_price=trade.take_profit,
                    exit_reason="TP",
                )
        else:  # SHORT
            if market.low <= trade.take_profit and risk > 0:
                return TradeDecision(
                    action=TradeAction.EXIT,
                    exit_price=trade.take_profit,
                    exit_reason="TP",
                )

        # ─── Step 3: Max hold check ─────────────────────────
        mh_result = self.max_hold.evaluate(
            bars_held=bars,
            close=market.close,
            risk_pips=risk,
        )
        if mh_result.should_exit:
            return TradeDecision(
                action=TradeAction.EXIT,
                exit_price=mh_result.exit_price,
                exit_reason=mh_result.exit_reason,
            )

        # ─── Step 4: No exit occurred — update SL ───────────
        new_sl = sl

        # Step 4a: Trailing stop (evaluated first in research code)
        new_sl = self.trailing.evaluate(
            direction=trade.direction,
            current_sl=new_sl,
            prev_swing_low=market.prev_swing_low,
            prev_swing_high=market.prev_swing_high,
        )

        # Step 4b: Breakeven (evaluated after trailing in research code)
        new_sl = self.breakeven.evaluate(
            direction=trade.direction,
            entry_price=entry,
            current_sl=new_sl,
            close=market.close,
            risk_pips=risk,
            pip_size=pip,
        )

        # ─── Return decision ────────────────────────────────
        if new_sl != sl:
            return TradeDecision(
                action=TradeAction.MOVE_STOP,
                new_sl=new_sl,
            )

        return TradeDecision(action=TradeAction.HOLD)
