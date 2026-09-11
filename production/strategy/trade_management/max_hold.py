"""
NestQuant Strategy — Max Hold Manager
======================================

Forensic reproduction of the research max-hold logic.

Research source: phase_s0_breakout_reassessment.py lines 146-151, 173-178
Verified against: phase_s5_5_failure_analysis.py lines 206-208, 252-254
                  phase_s6_adaptive_risk.py lines 216-218, 255-257

EXACT BEHAVIOR (LONG):
    max_bars = max_hold_days * 6  (4h bars per day = 6)
    if bars_held >= max_bars and risk > 0:
        exit_price = close
        exit_reason = "MH"

EXACT BEHAVIOR (SHORT):
    max_bars = max_hold_days * 6
    if bars_held >= max_bars and risk > 0:
        exit_price = close
        exit_reason = "MH"

Event ordering:
    Max hold is evaluated AFTER:
        1. SL check (may exit)
        2. TP check (may exit)
    Max hold is evaluated BEFORE:
        3. Trailing stop update
        4. Breakeven check

Exit price: Always close of the current bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MaxHoldExitReason(Enum):
    """Reason for max-hold exit."""
    MAX_HOLD = "MH"


@dataclass(frozen=True)
class MaxHoldConfig:
    """Max hold configuration. Matches research defaults."""
    enabled: bool = True
    max_hold_days: int = 7
    bars_per_day: int = 6  # 4h timeframe = 6 bars/day

    @property
    def max_bars(self) -> int:
        return self.max_hold_days * self.bars_per_day


@dataclass
class MaxHoldResult:
    """Result of max hold evaluation."""
    should_exit: bool
    exit_price: float
    exit_reason: str


class MaxHoldManager:
    """
    Evaluates whether a position has exceeded its maximum holding period.

    This is a pure function of state. No side effects.
    """

    def __init__(self, config: MaxHoldConfig | None = None):
        self.config = config or MaxHoldConfig()

    def evaluate(
        self,
        bars_held: int,
        close: float,
        risk_pips: float,
    ) -> MaxHoldResult:
        """
        Evaluate max hold and return exit decision.

        Args:
            bars_held: Number of bars since entry
            close: Current bar close price
            risk_pips: Initial risk in pips

        Returns:
            MaxHoldResult with should_exit, exit_price, exit_reason
        """
        if not self.config.enabled:
            return MaxHoldResult(should_exit=False, exit_price=0.0, exit_reason="")

        if risk_pips <= 0:
            return MaxHoldResult(should_exit=False, exit_price=0.0, exit_reason="")

        if bars_held >= self.config.max_bars:
            return MaxHoldResult(
                should_exit=True,
                exit_price=close,
                exit_reason=MaxHoldExitReason.MAX_HOLD.value,
            )

        return MaxHoldResult(should_exit=False, exit_price=0.0, exit_reason="")
