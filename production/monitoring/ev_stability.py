"""
EV Stability Analyzer
=====================

Measures whether positive expected value is stable over time.

Provides:
- Core EV metrics (mean, median, variance, std, downside deviation)
- Rolling EV windows with configurable window sizes
- EV stability indicators
- Percentile distributions of trade returns
- Coefficient of variation analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from nestquant.production.monitoring.percentiles import (
    PercentileDistribution,
    compute_percentiles,
)


@dataclass
class CoreEVMetrics:
    """Core expected value metrics for a set of trade returns."""

    mean_return: float
    median_return: float
    variance: float
    std: float
    downside_deviation: float
    coefficient_of_variation: float
    skewness: float
    kurtosis: float
    count: int
    positive_count: int
    negative_count: int
    win_rate: float
    expectancy_r: float

    def to_dict(self) -> dict:
        return {
            "mean_return": self.mean_return,
            "median_return": self.median_return,
            "variance": self.variance,
            "std": self.std,
            "downside_deviation": self.downside_deviation,
            "coefficient_of_variation": self.coefficient_of_variation,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "count": self.count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "win_rate": self.win_rate,
            "expectancy_r": self.expectancy_r,
        }


@dataclass
class RollingWindow:
    """A single rolling window result."""

    window_start: int
    window_end: int
    ev: float
    variance: float
    std: float
    win_rate: float
    profit_factor: float
    trade_count: int

    def to_dict(self) -> dict:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "ev": self.ev,
            "variance": self.variance,
            "std": self.std,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "trade_count": self.trade_count,
        }


@dataclass
class EVStabilityResult:
    """Complete EV stability analysis result."""

    core: CoreEVMetrics
    rolling_windows: list[RollingWindow]
    rolling_ev_values: list[float]
    rolling_ev_distribution: Optional[PercentileDistribution]
    stability_indicators: dict[str, float]
    trade_return_distribution: Optional[PercentileDistribution]
    windows_used: list[int]

    def to_dict(self) -> dict:
        return {
            "core": self.core.to_dict(),
            "rolling_windows": [w.to_dict() for w in self.rolling_windows],
            "rolling_ev_distribution": (
                self.rolling_ev_distribution.to_dict()
                if self.rolling_ev_distribution else None
            ),
            "stability_indicators": self.stability_indicators,
            "trade_return_distribution": (
                self.trade_return_distribution.to_dict()
                if self.trade_return_distribution else None
            ),
            "windows_used": self.windows_used,
        }


class EVStabilityAnalyzer:
    """
    Analyzes the stability of expected value over time.

    Uses rolling windows to detect whether EV is consistent,
    degrading, or improving.
    """

    def __init__(
        self,
        window_sizes: Optional[list[int]] = None,
        min_window_trades: int = 20,
    ):
        """
        Args:
            window_sizes: List of window sizes (in trades) to analyze.
                          Default: [20, 30, 50, 100]
            min_window_trades: Minimum trades in a window for valid analysis
        """
        self.window_sizes = window_sizes or [20, 30, 50, 100]
        self.min_window_trades = min_window_trades

    def compute_core_metrics(self, returns: np.ndarray) -> CoreEVMetrics:
        """Compute core EV metrics from trade returns."""
        arr = np.asarray(returns, dtype=float)
        arr = arr[np.isfinite(arr)]

        if len(arr) == 0:
            return CoreEVMetrics(
                mean_return=0, median_return=0, variance=0, std=0,
                downside_deviation=0, coefficient_of_variation=0,
                skewness=0, kurtosis=0, count=0,
                positive_count=0, negative_count=0, win_rate=0,
                expectancy_r=0,
            )

        mean_ret = float(np.mean(arr))
        median_ret = float(np.median(arr))
        var = float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0
        std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0

        # Downside deviation (semi-deviation)
        downside = arr[arr < 0]
        downside_dev = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0

        # Coefficient of variation
        cv = std / abs(mean_ret) if abs(mean_ret) > 1e-10 else float("inf")

        # Higher moments
        if len(arr) > 2:
            m3 = float(np.mean(((arr - mean_ret) / std) ** 3)) if std > 0 else 0.0
            m4 = float(np.mean(((arr - mean_ret) / std) ** 4)) if std > 0 else 0.0
        else:
            m3, m4 = 0.0, 0.0

        positive = int(np.sum(arr > 0))
        negative = int(np.sum(arr < 0))
        win_rate = positive / len(arr) if len(arr) > 0 else 0.0

        # Expectancy in R-multiples (normalized by average loss)
        avg_loss = float(np.mean(np.abs(downside))) if len(downside) > 0 else 1.0
        expectancy_r = mean_ret / avg_loss if avg_loss > 0 else 0.0

        return CoreEVMetrics(
            mean_return=mean_ret,
            median_return=median_ret,
            variance=var,
            std=std,
            downside_deviation=downside_dev,
            coefficient_of_variation=cv,
            skewness=m3,
            kurtosis=m4 - 3.0,  # excess kurtosis
            count=len(arr),
            positive_count=positive,
            negative_count=negative,
            win_rate=win_rate,
            expectancy_r=expectancy_r,
        )

    def compute_rolling_windows(
        self,
        returns: np.ndarray,
    ) -> list[RollingWindow]:
        """Compute rolling EV windows."""
        arr = np.asarray(returns, dtype=float)
        windows = []

        for ws in self.window_sizes:
            if ws > len(arr):
                continue
            for start in range(0, len(arr) - ws + 1, max(1, ws // 2)):
                end = start + ws
                if end > len(arr):
                    break
                chunk = arr[start:end]
                ev = float(np.mean(chunk))
                var = float(np.var(chunk, ddof=1)) if len(chunk) > 1 else 0.0
                std = float(np.std(chunk, ddof=1)) if len(chunk) > 1 else 0.0
                wr = float(np.sum(chunk > 0) / len(chunk))
                wins = chunk[chunk > 0]
                losses = chunk[chunk < 0]
                pf = (
                    float(np.sum(wins) / abs(np.sum(losses)))
                    if len(losses) > 0 and np.sum(losses) != 0
                    else float("inf")
                )
                windows.append(RollingWindow(
                    window_start=start,
                    window_end=end,
                    ev=ev,
                    variance=var,
                    std=std,
                    win_rate=wr,
                    profit_factor=pf,
                    trade_count=len(chunk),
                ))
        return windows

    def compute_stability_indicators(
        self,
        rolling_evs: np.ndarray,
        core: CoreEVMetrics,
    ) -> dict[str, float]:
        """Compute stability indicators from rolling EV values."""
        if len(rolling_evs) == 0:
            return {
                "positive_ev_pct": 0.0,
                "negative_ev_pct": 0.0,
                "median_rolling_ev": 0.0,
                "rolling_ev_std": 0.0,
                "ev_to_rolling_ev_std": 0.0,
                "degradation_from_baseline": 0.0,
                "min_rolling_ev": 0.0,
                "max_rolling_ev": 0.0,
            }

        positive_pct = float(np.sum(rolling_evs > 0) / len(rolling_evs))
        negative_pct = float(np.sum(rolling_evs <= 0) / len(rolling_evs))
        median_rolling = float(np.median(rolling_evs))
        rolling_std = float(np.std(rolling_evs, ddof=1)) if len(rolling_evs) > 1 else 0.0
        ev_vs_std = (
            core.mean_return / rolling_std
            if rolling_std > 0 else float("inf")
        )

        # Degradation: how much the most recent windows differ from baseline
        if len(rolling_evs) >= 4:
            recent = rolling_evs[-len(rolling_evs) // 4:]
            baseline = rolling_evs[:len(rolling_evs) // 4]
            degradation = float(np.mean(baseline) - np.mean(recent))
        else:
            degradation = 0.0

        return {
            "positive_ev_pct": positive_pct,
            "negative_ev_pct": negative_pct,
            "median_rolling_ev": median_rolling,
            "rolling_ev_std": rolling_std,
            "ev_to_rolling_ev_std": ev_vs_std,
            "degradation_from_baseline": degradation,
            "min_rolling_ev": float(np.min(rolling_evs)),
            "max_rolling_ev": float(np.max(rolling_evs)),
        }

    def analyze(self, returns: np.ndarray) -> EVStabilityResult:
        """
        Perform full EV stability analysis.

        Args:
            returns: Array of trade returns (can be in pips, R-multiples, or dollars)

        Returns:
            EVStabilityResult with all metrics
        """
        arr = np.asarray(returns, dtype=float)
        arr = arr[np.isfinite(arr)]

        # Core metrics
        core = self.compute_core_metrics(arr)

        # Rolling windows
        windows = self.compute_rolling_windows(arr)
        rolling_evs = np.array([w.ev for w in windows]) if windows else np.array([])

        # Rolling EV distribution
        rolling_dist = None
        if len(rolling_evs) >= 10:
            rolling_dist = compute_percentiles(rolling_evs, compute_ci=True)

        # Stability indicators
        stability = self.compute_stability_indicators(rolling_evs, core)

        # Trade return distribution
        trade_dist = None
        if len(arr) >= 10:
            trade_dist = compute_percentiles(arr, compute_ci=True)

        return EVStabilityResult(
            core=core,
            rolling_windows=windows,
            rolling_ev_values=rolling_evs.tolist(),
            rolling_ev_distribution=rolling_dist,
            stability_indicators=stability,
            trade_return_distribution=trade_dist,
            windows_used=self.window_sizes,
        )
