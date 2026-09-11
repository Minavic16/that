"""
NestQuant Strategy — Trailing Stop Manager
===========================================

Forensic reproduction of the research trailing stop logic.

Research source: phase_s0_breakout_reassessment.py lines 152-155, 179-182
Verified against: phase_s5_5_failure_analysis.py lines 210-212, 256-258
                  phase_s6_adaptive_risk.py lines 220-222, 259-261

EXACT BEHAVIOR (LONG):
    new_sl = swing_low[i - 1]  (previous bar's confirmed swing low)
    if not isnan(new_sl) and new_sl > sl_price:
        sl_price = new_sl

    The trailing stop uses the PREVIOUS bar's swing level (i-1),
    not the current bar's. This avoids lookahead bias.

    The swing low is only used if it moves the SL UP (tighter).

EXACT BEHAVIOR (SHORT):
    new_sl = swing_high[i - 1]  (previous bar's confirmed swing high)
    if not isnan(new_sl) and new_sl < sl_price:
        sl_price = new_sl

    The swing high is only used if it moves the SL DOWN (tighter).

Event ordering:
    Trailing stop is evaluated AFTER:
        1. SL check (may exit)
        2. TP check (may exit)
        3. Max hold check (may exit)
    Trailing stop is evaluated BEFORE:
        4. Breakeven check

    IMPORTANT: In the research code, trailing and breakeven are in the
    SAME else-block (after SL/TP/MH checks). They execute on the same
    bar when no exit occurred. Trailing runs first, then breakeven.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TrailingStopConfig:
    """Trailing stop configuration. Matches research defaults."""
    enabled: bool = True


class TrailingStopManager:
    """
    Evaluates and applies trailing stop-loss movement.

    This is a pure function of state. No side effects.
    """

    def __init__(self, config: TrailingStopConfig | None = None):
        self.config = config or TrailingStopConfig()

    def evaluate(
        self,
        direction: int,
        current_sl: float,
        prev_swing_low: float,
        prev_swing_high: float,
    ) -> float:
        """
        Evaluate trailing stop and return updated SL price.

        Args:
            direction: 1 for LONG, -1 for SHORT
            current_sl: Current stop loss price
            prev_swing_low: Previous bar's confirmed swing low (for LONG)
            prev_swing_high: Previous bar's confirmed swing high (for SHORT)

        Returns:
            Updated SL price (unchanged if trailing not applicable)
        """
        if not self.config.enabled:
            return current_sl

        if direction == 1:  # LONG
            # Use previous bar's swing low to avoid lookahead
            if not _is_nan(prev_swing_low) and prev_swing_low > current_sl:
                return prev_swing_low
        else:  # SHORT
            # Use previous bar's swing high to avoid lookahead
            if not _is_nan(prev_swing_high) and prev_swing_high < current_sl:
                return prev_swing_high

        return current_sl


def _is_nan(value: float) -> bool:
    """Check if value is NaN (matches numpy isnan behavior)."""
    return value != value
