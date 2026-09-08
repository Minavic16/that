"""
NestQuant Strategy — Breakeven Manager
=======================================

Forensic reproduction of the research breakeven logic.

Research source: phase_s0_breakout_reassessment.py lines 156-158
Verified against: phase_s5_5_failure_analysis.py lines 213-215
                  phase_s6_adaptive_risk.py lines 223-225

EXACT BEHAVIOR (LONG):
    if sl_price < entry_price and risk > 0:
        if (close - entry_price) / pip >= breakeven_ratio * risk:
            sl_price = entry_price

EXACT BEHAVIOR (SHORT):
    if sl_price > entry_price and risk > 0:
        if (entry_price - close) / pip >= breakeven_ratio * risk:
            sl_price = entry_price

Event ordering:
    Breakeven is evaluated AFTER:
        1. SL check (may exit)
        2. TP check (may exit)
        3. Max hold check (may exit)
        4. Trailing stop update (may move SL)
    Breakeven only executes when NO exit occurred on this bar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakevenConfig:
    """Breakeven configuration. Matches research defaults."""
    enabled: bool = True
    trigger_r: float = 0.8  # BREAKEVEN_RATIO from research


class BreakevenManager:
    """
    Evaluates and applies breakeven stop-loss movement.

    This is a pure function of state. No side effects.
    """

    def __init__(self, config: BreakevenConfig | None = None):
        self.config = config or BreakevenConfig()

    def evaluate(
        self,
        direction: int,
        entry_price: float,
        current_sl: float,
        close: float,
        risk_pips: float,
        pip_size: float,
    ) -> float:
        """
        Evaluate breakeven and return updated SL price.

        Args:
            direction: 1 for LONG, -1 for SHORT
            entry_price: Trade entry price
            current_sl: Current stop loss price
            close: Current bar close price
            risk_pips: Initial risk in pips (|entry - SL| / pip)
            pip_size: Pip size for the pair

        Returns:
            Updated SL price (unchanged if breakeven not triggered)
        """
        if not self.config.enabled:
            return current_sl

        if risk_pips <= 0:
            return current_sl

        if direction == 1:  # LONG
            # Condition 1: SL must still be below entry (not already at BE)
            if current_sl < entry_price:
                # Condition 2: Profit must exceed trigger_r * risk
                profit_pips = (close - entry_price) / pip_size
                if profit_pips >= self.config.trigger_r * risk_pips:
                    return entry_price
        else:  # SHORT
            # Condition 1: SL must still be above entry
            if current_sl > entry_price:
                # Condition 2: Profit must exceed trigger_r * risk
                profit_pips = (entry_price - close) / pip_size
                if profit_pips >= self.config.trigger_r * risk_pips:
                    return entry_price

        return current_sl
