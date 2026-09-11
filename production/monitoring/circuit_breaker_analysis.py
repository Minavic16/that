"""
Circuit Breaker Calibration Analysis
=====================================

Evaluates whether circuit breakers improve the distribution of outcomes.

For each breaker determines:
- Trigger condition
- Historical trigger frequency
- Percentage of triggers during profitable eventual periods
- Effect on total return, max DD, recovery time, trade count
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class BreakerTriggerAnalysis:
    """Analysis of a single circuit breaker's historical behavior."""

    breaker_name: str
    trigger_condition: str
    total_trades: int
    trigger_count: int
    trigger_frequency: float
    pct_triggers_preceding_profit: float
    pct_triggers_preceding_deterioration: float
    return_with_breaker: float
    return_without_breaker: float
    return_impact: float
    max_dd_with_breaker: float
    max_dd_without_breaker: float
    dd_impact: float
    recovery_with_breaker: float
    recovery_without_breaker: float
    trade_count_with: int
    trade_count_without: int
    improvement_assessment: str

    def to_dict(self) -> dict:
        return {
            "breaker_name": self.breaker_name,
            "trigger_condition": self.trigger_condition,
            "total_trades": self.total_trades,
            "trigger_count": self.trigger_count,
            "trigger_frequency": self.trigger_frequency,
            "pct_triggers_preceding_profit": self.pct_triggers_preceding_profit,
            "pct_triggers_preceding_deterioration": self.pct_triggers_preceding_deterioration,
            "return_with_breaker": self.return_with_breaker,
            "return_without_breaker": self.return_without_breaker,
            "return_impact": self.return_impact,
            "max_dd_with_breaker": self.max_dd_with_breaker,
            "max_dd_without_breaker": self.max_dd_without_breaker,
            "dd_impact": self.dd_impact,
            "recovery_with_breaker": self.recovery_with_breaker,
            "recovery_without_breaker": self.recovery_without_breaker,
            "trade_count_with": self.trade_count_with,
            "trade_count_without": self.trade_count_without,
            "improvement_assessment": self.improvement_assessment,
        }


class CircuitBreakerCalibrator:
    """
    Analyzes circuit breaker effectiveness against historical data.

    Simulates breaker behavior on historical returns to determine
    whether breakers improve outcome distributions.
    """

    def simulate_win_rate_breaker(
        self,
        returns: np.ndarray,
        window: int = 20,
        threshold: float = 0.40,
        pause_bars: int = 5,
    ) -> BreakerTriggerAnalysis:
        """Simulate WinRateBreaker behavior."""
        arr = np.asarray(returns, dtype=float)
        n = len(arr)
        if n < window:
            return self._empty_analysis("WinRateBreaker", f"WR<{threshold} over {window} trades", n)

        # Track triggers
        triggers = []
        active = np.ones(n, dtype=bool)

        for i in range(window, n):
            window_returns = arr[i - window:i]
            wr = np.sum(window_returns > 0) / window
            if wr < threshold:
                triggers.append(i)
                # Pause for pause_bars
                for j in range(i, min(i + pause_bars, n)):
                    active[j] = False

        # Compute metrics with and without breaker
        returns_with = arr[active]
        returns_without = arr

        cumulative_with = np.cumsum(returns_with)
        cumulative_without = np.cumsum(returns_without)

        total_with = float(np.sum(returns_with))
        total_without = float(np.sum(returns_without))

        max_dd_with = self._max_dd(returns_with)
        max_dd_without = self._max_dd(returns_without)

        # Assess improvement
        improvement = self._assess_improvement(
            total_with, total_without, max_dd_with, max_dd_without
        )

        return BreakerTriggerAnalysis(
            breaker_name="WinRateBreaker",
            trigger_condition=f"WR<{threshold} over {window} trades",
            total_trades=n,
            trigger_count=len(triggers),
            trigger_frequency=len(triggers) / n if n > 0 else 0.0,
            pct_triggers_preceding_profit=0.0,  # Would need forward returns
            pct_triggers_preceding_deterioration=0.0,
            return_with_breaker=total_with,
            return_without_breaker=total_without,
            return_impact=total_with - total_without,
            max_dd_with_breaker=max_dd_with,
            max_dd_without_breaker=max_dd_without,
            dd_impact=max_dd_with - max_dd_without,
            recovery_with_breaker=0.0,
            recovery_without_breaker=0.0,
            trade_count_with=int(np.sum(active)),
            trade_count_without=n,
            improvement_assessment=improvement,
        )

    def simulate_slippage_breaker(
        self,
        returns: np.ndarray,
        slippages: np.ndarray,
        consecutive_threshold: float = 4.8,
        consecutive_count: int = 3,
        avg_threshold: float = 6.0,
        avg_window: int = 10,
        pause_bars: int = 5,
    ) -> BreakerTriggerAnalysis:
        """Simulate SlippageBreaker behavior."""
        arr = np.asarray(returns, dtype=float)
        slip = np.asarray(slippages, dtype=float)
        n = min(len(arr), len(slip))

        if n < avg_window:
            return self._empty_analysis("SlippageBreaker", f"slip>{consecutive_threshold}x{consecutive_count} or avg>{avg_threshold}", n)

        triggers = []
        active = np.ones(n, dtype=bool)
        consec = 0

        for i in range(n):
            if slip[i] > consecutive_threshold:
                consec += 1
            else:
                consec = 0

            if consec >= consecutive_count:
                triggers.append(i)
                for j in range(i, min(i + pause_bars, n)):
                    active[j] = False
                consec = 0

            # Also check rolling average
            if i >= avg_window:
                avg_slip = np.mean(slip[i - avg_window:i])
                if avg_slip > avg_threshold:
                    triggers.append(i)
                    for j in range(i, min(i + pause_bars, n)):
                        active[j] = False

        returns_with = arr[active]
        returns_without = arr[:n]

        total_with = float(np.sum(returns_with))
        total_without = float(np.sum(returns_without))
        max_dd_with = self._max_dd(returns_with)
        max_dd_without = self._max_dd(returns_without)

        return BreakerTriggerAnalysis(
            breaker_name="SlippageBreaker",
            trigger_condition=f"consecutive>{consecutive_threshold}x{consecutive_count} or avg({avg_window})>{avg_threshold}",
            total_trades=n,
            trigger_count=len(triggers),
            trigger_frequency=len(triggers) / n if n > 0 else 0.0,
            pct_triggers_preceding_profit=0.0,
            pct_triggers_preceding_deterioration=0.0,
            return_with_breaker=total_with,
            return_without_breaker=total_without,
            return_impact=total_with - total_without,
            max_dd_with_breaker=max_dd_with,
            max_dd_without_breaker=max_dd_without,
            dd_impact=max_dd_with - max_dd_without,
            recovery_with_breaker=0.0,
            recovery_without_breaker=0.0,
            trade_count_with=int(np.sum(active)),
            trade_count_without=n,
            improvement_assessment=self._assess_improvement(
                total_with, total_without, max_dd_with, max_dd_without
            ),
        )

    def simulate_drawdown_pace_breaker(
        self,
        returns: np.ndarray,
        initial_balance: float = 10000.0,
        soft_dd_pct: float = 0.06,
        soft_trades: int = 15,
        hard_dd_pct: float = 0.09,
        hard_trades: int = 25,
        pause_bars: int = 10,
    ) -> BreakerTriggerAnalysis:
        """Simulate DrawdownPaceBreaker behavior."""
        arr = np.asarray(returns, dtype=float)
        n = len(arr)

        if n < 5:
            return self._empty_analysis("DrawdownPaceBreaker", f"soft>{soft_dd_pct} in {soft_trades} or hard>{hard_dd_pct} in {hard_trades}", n)

        triggers = []
        active = np.ones(n, dtype=bool)
        equity = initial_balance
        peak = initial_balance
        dd_count = 0

        for i in range(n):
            equity += arr[i]
            if equity > peak:
                peak = equity
                dd_count = 0
            else:
                dd_count += 1

            dd_pct = (peak - equity) / peak if peak > 0 else 0.0

            if dd_pct >= hard_dd_pct and dd_count >= hard_trades:
                triggers.append(i)
                for j in range(i, min(i + pause_bars * 2, n)):
                    active[j] = False
            elif dd_pct >= soft_dd_pct and dd_count >= soft_trades:
                triggers.append(i)
                for j in range(i, min(i + pause_bars, n)):
                    active[j] = False

        returns_with = arr[active]
        returns_without = arr

        total_with = float(np.sum(returns_with))
        total_without = float(np.sum(returns_without))
        max_dd_with = self._max_dd(returns_with)
        max_dd_without = self._max_dd(returns_without)

        return BreakerTriggerAnalysis(
            breaker_name="DrawdownPaceBreaker",
            trigger_condition=f"soft>{soft_dd_pct} in {soft_trades}T or hard>{hard_dd_pct} in {hard_trades}T",
            total_trades=n,
            trigger_count=len(triggers),
            trigger_frequency=len(triggers) / n if n > 0 else 0.0,
            pct_triggers_preceding_profit=0.0,
            pct_triggers_preceding_deterioration=0.0,
            return_with_breaker=total_with,
            return_without_breaker=total_without,
            return_impact=total_with - total_without,
            max_dd_with_breaker=max_dd_with,
            max_dd_without_breaker=max_dd_without,
            dd_impact=max_dd_with - max_dd_without,
            recovery_with_breaker=0.0,
            recovery_without_breaker=0.0,
            trade_count_with=int(np.sum(active)),
            trade_count_without=n,
            improvement_assessment=self._assess_improvement(
                total_with, total_without, max_dd_with, max_dd_without
            ),
        )

    def simulate_profit_factor_breaker(
        self,
        returns: np.ndarray,
        window: int = 20,
        threshold: float = 1.0,
        pause_bars: int = 5,
    ) -> BreakerTriggerAnalysis:
        """Simulate ProfitFactorBreaker behavior."""
        arr = np.asarray(returns, dtype=float)
        n = len(arr)

        if n < window:
            return self._empty_analysis("ProfitFactorBreaker", f"PF<{threshold} over {window} trades", n)

        triggers = []
        active = np.ones(n, dtype=bool)

        for i in range(window, n):
            window_returns = arr[i - window:i]
            wins = window_returns[window_returns > 0]
            losses = window_returns[window_returns < 0]
            if len(losses) > 0 and np.sum(losses) != 0:
                pf = np.sum(wins) / abs(np.sum(losses))
                if pf < threshold:
                    triggers.append(i)
                    for j in range(i, min(i + pause_bars, n)):
                        active[j] = False

        returns_with = arr[active]
        returns_without = arr

        total_with = float(np.sum(returns_with))
        total_without = float(np.sum(returns_without))
        max_dd_with = self._max_dd(returns_with)
        max_dd_without = self._max_dd(returns_without)

        return BreakerTriggerAnalysis(
            breaker_name="ProfitFactorBreaker",
            trigger_condition=f"PF<{threshold} over {window} trades",
            total_trades=n,
            trigger_count=len(triggers),
            trigger_frequency=len(triggers) / n if n > 0 else 0.0,
            pct_triggers_preceding_profit=0.0,
            pct_triggers_preceding_deterioration=0.0,
            return_with_breaker=total_with,
            return_without_breaker=total_without,
            return_impact=total_with - total_without,
            max_dd_with_breaker=max_dd_with,
            max_dd_without_breaker=max_dd_without,
            dd_impact=max_dd_with - max_dd_without,
            recovery_with_breaker=0.0,
            recovery_without_breaker=0.0,
            trade_count_with=int(np.sum(active)),
            trade_count_without=n,
            improvement_assessment=self._assess_improvement(
                total_with, total_without, max_dd_with, max_dd_without
            ),
        )

    def _max_dd(self, returns: np.ndarray) -> float:
        """Calculate max drawdown from returns array."""
        if len(returns) == 0:
            return 0.0
        equity = np.cumsum(returns)
        peak = np.maximum.accumulate(equity)
        dd = peak - equity
        return float(np.max(dd)) if len(dd) > 0 else 0.0

    def _assess_improvement(
        self,
        total_with: float,
        total_without: float,
        dd_with: float,
        dd_without: float,
    ) -> str:
        """Assess whether breaker improves outcomes."""
        return_change = (total_with - total_without) / abs(total_without) if abs(total_without) > 0 else 0.0
        dd_change = (dd_with - dd_without) / dd_without if dd_without > 0 else 0.0

        if return_change > 0.02 and dd_change < 0.1:
            return "IMPROVES — higher return, similar or lower DD"
        elif return_change > 0.02 and dd_change >= 0.1:
            return "MIXED — higher return but higher DD"
        elif abs(return_change) <= 0.02 and dd_change < -0.05:
            return "MIXED — similar return, lower DD"
        elif return_change < -0.02 and dd_change > 0.05:
            return "DEGRADES — lower return AND higher DD"
        elif return_change < -0.02:
            return "DEGRADES — lower return"
        else:
            return "NEUTRAL — minimal impact on distribution"

    def _empty_analysis(self, name: str, condition: str, n: int) -> BreakerTriggerAnalysis:
        """Return empty analysis for insufficient data."""
        return BreakerTriggerAnalysis(
            breaker_name=name,
            trigger_condition=condition,
            total_trades=n,
            trigger_count=0,
            trigger_frequency=0.0,
            pct_triggers_preceding_profit=0.0,
            pct_triggers_preceding_deterioration=0.0,
            return_with_breaker=0.0,
            return_without_breaker=0.0,
            return_impact=0.0,
            max_dd_with_breaker=0.0,
            max_dd_without_breaker=0.0,
            dd_impact=0.0,
            recovery_with_breaker=0.0,
            recovery_without_breaker=0.0,
            trade_count_with=0,
            trade_count_without=n,
            improvement_assessment="INSUFFICIENT DATA",
        )
