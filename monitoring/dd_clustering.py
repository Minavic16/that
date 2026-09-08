"""
Drawdown Clustering Analyzer
=============================

Detects and analyzes drawdown episodes from equity/return time series.

Provides:
- DD episode detection (start, trough, recovery)
- DD depth, duration, recovery time
- Clustering analysis (episodes per N trades, spacing, probability)
- Statistical comparison with random baseline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from monitoring.percentiles import (
    PercentileDistribution,
    compute_percentiles,
)


@dataclass
class DDEpisode:
    """A single drawdown episode."""

    start_idx: int
    trough_idx: int
    recovery_idx: Optional[int]
    peak_equity: float
    trough_equity: float
    depth: float
    depth_pct: float
    duration: int
    recovery_time: Optional[int]
    trades_during_dd: int
    losses_during_dd: int

    def to_dict(self) -> dict:
        return {
            "start_idx": self.start_idx,
            "trough_idx": self.trough_idx,
            "recovery_idx": self.recovery_idx,
            "peak_equity": self.peak_equity,
            "trough_equity": self.trough_equity,
            "depth": self.depth,
            "depth_pct": self.depth_pct,
            "duration": self.duration,
            "recovery_time": self.recovery_time,
            "trades_during_dd": self.trades_during_dd,
            "losses_during_dd": self.losses_during_dd,
        }


@dataclass
class DDCusteringMetrics:
    """Aggregated drawdown clustering metrics."""

    episodes_per_100_trades: float
    avg_depth: float
    median_depth: float
    p75_depth: Optional[float]
    p90_depth: Optional[float]
    p95_depth: Optional[float]
    p99_depth: Optional[float]
    depth_distribution: Optional[PercentileDistribution]
    avg_duration: float
    median_duration: float
    p75_duration: Optional[float]
    p90_duration: Optional[float]
    p95_duration: Optional[float]
    duration_distribution: Optional[PercentileDistribution]
    avg_recovery: float
    median_recovery: float
    p75_recovery: Optional[float]
    p90_recovery: Optional[float]
    recovery_distribution: Optional[PercentileDistribution]
    min_spacing: float
    median_spacing: float
    spacing_distribution: Optional[PercentileDistribution]
    max_clustered_in_window: int
    window_size: int
    total_episodes: int
    total_trades: int

    def to_dict(self) -> dict:
        return {
            "episodes_per_100_trades": self.episodes_per_100_trades,
            "total_episodes": self.total_episodes,
            "total_trades": self.total_trades,
            "depth": {
                "avg": self.avg_depth,
                "median": self.median_depth,
                "p75": self.p75_depth,
                "p90": self.p90_depth,
                "p95": self.p95_depth,
                "p99": self.p99_depth,
                "distribution": self.depth_distribution.to_dict() if self.depth_distribution else None,
            },
            "duration": {
                "avg": self.avg_duration,
                "median": self.median_duration,
                "p75": self.p75_duration,
                "p90": self.p90_duration,
                "p95": self.p95_duration,
                "distribution": self.duration_distribution.to_dict() if self.duration_distribution else None,
            },
            "recovery": {
                "avg": self.avg_recovery,
                "median": self.median_recovery,
                "p75": self.p75_recovery,
                "p90": self.p90_recovery,
                "distribution": self.recovery_distribution.to_dict() if self.recovery_distribution else None,
            },
            "spacing": {
                "min": self.min_spacing,
                "median": self.median_spacing,
                "distribution": self.spacing_distribution.to_dict() if self.spacing_distribution else None,
            },
            "max_clustered_in_window": self.max_clustered_in_window,
            "window_size": self.window_size,
        }


@dataclass
class DDClusterResult:
    """Complete drawdown clustering analysis result."""

    episodes: list[DDEpisode]
    metrics: DDCusteringMetrics
    clustering_analysis: dict[str, float]
    random_baseline: Optional[dict[str, float]] = None

    def to_dict(self) -> dict:
        return {
            "episodes": [e.to_dict() for e in self.episodes],
            "metrics": self.metrics.to_dict(),
            "clustering_analysis": self.clustering_analysis,
            "random_baseline": self.random_baseline,
        }


class DDClusterAnalyzer:
    """
    Detects and analyzes drawdown episodes and their clustering.

    A drawdown episode begins when equity falls below its previous
    running peak and ends when the previous peak is recovered.
    """

    def __init__(
        self,
        window_sizes: Optional[list[int]] = None,
        n_random_baseline: int = 1000,
    ):
        """
        Args:
            window_sizes: Window sizes for clustering analysis (in trades)
            n_random_baseline: Number of random shuffles for baseline comparison
        """
        self.window_sizes = window_sizes or [50, 100, 200]
        self.n_random_baseline = n_random_baseline

    def detect_episodes(
        self,
        equity_curve: np.ndarray,
        returns: Optional[np.ndarray] = None,
    ) -> list[DDEpisode]:
        """
        Detect drawdown episodes from an equity curve.

        Args:
            equity_curve: Array of equity values over time
            returns: Optional array of per-trade returns (for counting losses during DD)

        Returns:
            List of DDEpisode objects
        """
        eq = np.asarray(equity_curve, dtype=float)
        if len(eq) < 2:
            return []

        episodes = []
        peak = eq[0]
        peak_idx = 0
        in_dd = False
        trough_val = eq[0]
        trough_idx = 0

        for i in range(1, len(eq)):
            if eq[i] > peak:
                if in_dd:
                    # Recovery
                    depth = peak - trough_val
                    depth_pct = depth / peak if peak > 0 else 0.0
                    duration = i - peak_idx
                    recovery_time = i - trough_idx

                    # Count trades and losses during DD
                    trades_during = duration
                    losses_during = 0
                    if returns is not None:
                        dd_returns = returns[peak_idx:i]
                        losses_during = int(np.sum(dd_returns < 0))

                    episodes.append(DDEpisode(
                        start_idx=peak_idx,
                        trough_idx=trough_idx,
                        recovery_idx=i,
                        peak_equity=float(peak),
                        trough_equity=float(trough_val),
                        depth=float(depth),
                        depth_pct=float(depth_pct),
                        duration=duration,
                        recovery_time=recovery_time,
                        trades_during_dd=trades_during,
                        losses_during_dd=losses_during,
                    ))
                    in_dd = False

                peak = eq[i]
                peak_idx = i
            elif eq[i] < peak:
                if not in_dd:
                    in_dd = True
                    trough_val = eq[i]
                    trough_idx = i
                elif eq[i] < trough_val:
                    trough_val = eq[i]
                    trough_idx = i

        # Handle unfinished DD at end
        if in_dd:
            depth = peak - trough_val
            depth_pct = depth / peak if peak > 0 else 0.0
            duration = len(eq) - peak_idx
            trades_during = duration
            losses_during = 0
            if returns is not None:
                dd_returns = returns[peak_idx:]
                losses_during = int(np.sum(dd_returns < 0))

            episodes.append(DDEpisode(
                start_idx=peak_idx,
                trough_idx=trough_idx,
                recovery_idx=None,
                peak_equity=float(peak),
                trough_equity=float(trough_val),
                depth=float(depth),
                depth_pct=float(depth_pct),
                duration=duration,
                recovery_time=None,
                trades_during_dd=trades_during,
                losses_during_dd=losses_during,
            ))

        return episodes

    def compute_metrics(
        self,
        episodes: list[DDEpisode],
        total_trades: int,
        window_size: int = 100,
    ) -> DDCusteringMetrics:
        """Compute aggregated clustering metrics from episodes."""
        if not episodes:
            empty_dist = compute_percentiles(np.array([0.0]), compute_ci=False)
            return DDCusteringMetrics(
                episodes_per_100_trades=0.0,
                avg_depth=0.0, median_depth=0.0,
                p75_depth=None, p90_depth=None, p95_depth=None, p99_depth=None,
                depth_distribution=empty_dist,
                avg_duration=0.0, median_duration=0.0,
                p75_duration=None, p90_duration=None, p95_duration=None,
                duration_distribution=empty_dist,
                avg_recovery=0.0, median_recovery=0.0,
                p75_recovery=None, p90_recovery=None,
                recovery_distribution=empty_dist,
                min_spacing=0.0, median_spacing=0.0,
                spacing_distribution=empty_dist,
                max_clustered_in_window=0,
                window_size=window_size,
                total_episodes=0,
                total_trades=total_trades,
            )

        depths = np.array([e.depth for e in episodes])
        depths_pct = np.array([e.depth_pct for e in episodes])
        durations = np.array([e.duration for e in episodes])
        recoveries = np.array([e.recovery_time for e in episodes if e.recovery_time is not None])

        # Spacing between episodes
        starts = sorted([e.start_idx for e in episodes])
        spacings = np.diff(starts) if len(starts) > 1 else np.array([0.0])

        # Depth distribution
        depth_dist = compute_percentiles(depths_pct, compute_ci=True) if len(depths_pct) >= 5 else None

        # Duration distribution
        dur_dist = compute_percentiles(durations.astype(float), compute_ci=True) if len(durations) >= 5 else None

        # Recovery distribution
        rec_dist = compute_percentiles(recoveries.astype(float), compute_ci=True) if len(recoveries) >= 5 else None

        # Spacing distribution
        spac_dist = compute_percentiles(spacings.astype(float), compute_ci=True) if len(spacings) >= 5 else None

        # Max clustered in rolling window
        max_clustered = 0
        for ws in self.window_sizes:
            for i in range(len(starts) - ws + 1):
                count = sum(1 for s in starts if starts[i] <= s < starts[i] + ws)
                max_clustered = max(max_clustered, count)

        return DDCusteringMetrics(
            episodes_per_100_trades=len(episodes) / total_trades * 100 if total_trades > 0 else 0.0,
            avg_depth=float(np.mean(depths_pct)),
            median_depth=float(np.median(depths_pct)),
            p75_depth=float(np.percentile(depths_pct, 75)) if len(depths_pct) >= 4 else None,
            p90_depth=float(np.percentile(depths_pct, 90)) if len(depths_pct) >= 10 else None,
            p95_depth=float(np.percentile(depths_pct, 95)) if len(depths_pct) >= 20 else None,
            p99_depth=float(np.percentile(depths_pct, 99)) if len(depths_pct) >= 100 else None,
            depth_distribution=depth_dist,
            avg_duration=float(np.mean(durations)),
            median_duration=float(np.median(durations)),
            p75_duration=float(np.percentile(durations, 75)) if len(durations) >= 4 else None,
            p90_duration=float(np.percentile(durations, 90)) if len(durations) >= 10 else None,
            p95_duration=float(np.percentile(durations, 95)) if len(durations) >= 20 else None,
            duration_distribution=dur_dist,
            avg_recovery=float(np.mean(recoveries)) if len(recoveries) > 0 else 0.0,
            median_recovery=float(np.median(recoveries)) if len(recoveries) > 0 else 0.0,
            p75_recovery=float(np.percentile(recoveries, 75)) if len(recoveries) >= 4 else None,
            p90_recovery=float(np.percentile(recoveries, 90)) if len(recoveries) >= 10 else None,
            recovery_distribution=rec_dist,
            min_spacing=float(np.min(spacings)) if len(spacings) > 0 else 0.0,
            median_spacing=float(np.median(spacings)) if len(spacings) > 0 else 0.0,
            spacing_distribution=spac_dist,
            max_clustered_in_window=max_clustered,
            window_size=window_size,
            total_episodes=len(episodes),
            total_trades=total_trades,
        )

    def compute_clustering_analysis(
        self,
        episodes: list[DDEpisode],
        total_trades: int,
    ) -> dict[str, float]:
        """Compute clustering-specific analysis."""
        if not episodes or total_trades == 0:
            return {
                "cluster_probability_50": 0.0,
                "cluster_probability_100": 0.0,
                "mean_spacing": 0.0,
                "spacing_cv": 0.0,
                "is_clustered": False,
            }

        starts = sorted([e.start_idx for e in episodes])
        spacings = np.diff(starts) if len(starts) > 1 else np.array([total_trades])

        # Probability of another DD within N trades after a DD
        def prob_within_n(n):
            if len(spacings) == 0:
                return 0.0
            return float(np.sum(spacings <= n) / len(spacings))

        mean_spacing = float(np.mean(spacings))
        std_spacing = float(np.std(spacings, ddof=1)) if len(spacings) > 1 else 0.0
        cv = std_spacing / mean_spacing if mean_spacing > 0 else 0.0

        # Clustering test: CV of spacing > 1 suggests clustering
        # (random events have CV ≈ 1 for exponential spacing)
        return {
            "cluster_probability_50": prob_within_n(50),
            "cluster_probability_100": prob_within_n(100),
            "mean_spacing": mean_spacing,
            "spacing_cv": cv,
            "is_clustered": cv > 1.2,  # Heuristic: CV > 1.2 suggests clustering
        }

    def compute_random_baseline(
        self,
        equity_curve: np.ndarray,
        returns: np.ndarray,
        n_sims: int = 1000,
    ) -> dict[str, float]:
        """
        Compute random baseline for comparison.

        Shuffles trade returns and recomputes DD metrics to establish
        what random variation looks like.
        """
        rng = np.random.RandomState(42)
        all_depths = []
        all_counts = []
        all_durations = []

        initial = equity_curve[0] if len(equity_curve) > 0 else 0.0

        for _ in range(n_sims):
            shuffled = rng.permutation(returns)
            eq = np.cumsum(shuffled) + initial
            eps = self.detect_episodes(eq, shuffled)
            if eps:
                all_depths.extend([e.depth_pct for e in eps])
                all_counts.append(len(eps))
                all_durations.extend([e.duration for e in eps])

        if not all_depths:
            return {
                "avg_depth": 0.0,
                "p95_depth": 0.0,
                "avg_count": 0.0,
                "p95_count": 0.0,
                "avg_duration": 0.0,
                "p95_duration": 0.0,
            }

        return {
            "avg_depth": float(np.mean(all_depths)),
            "p95_depth": float(np.percentile(all_depths, 95)),
            "avg_count": float(np.mean(all_counts)),
            "p95_count": float(np.percentile(all_counts, 95)),
            "avg_duration": float(np.mean(all_durations)),
            "p95_duration": float(np.percentile(all_durations, 95)),
        }

    def analyze(
        self,
        equity_curve: np.ndarray,
        returns: Optional[np.ndarray] = None,
        include_baseline: bool = True,
    ) -> DDClusterResult:
        """
        Full drawdown clustering analysis.

        Args:
            equity_curve: Array of equity values
            returns: Optional per-trade returns
            include_baseline: Whether to compute random baseline

        Returns:
            DDClusterResult with all analysis
        """
        eq = np.asarray(equity_curve, dtype=float)
        ret = np.asarray(returns, dtype=float) if returns is not None else None

        # Detect episodes
        episodes = self.detect_episodes(eq, ret)

        total_trades = len(eq) - 1 if len(eq) > 1 else 0

        # Compute metrics
        metrics = self.compute_metrics(episodes, total_trades)

        # Clustering analysis
        clustering = self.compute_clustering_analysis(episodes, total_trades)

        # Random baseline
        baseline = None
        if include_baseline and ret is not None and len(ret) >= 20:
            baseline = self.compute_random_baseline(eq, ret)

        return DDClusterResult(
            episodes=episodes,
            metrics=metrics,
            clustering_analysis=clustering,
            random_baseline=baseline,
        )
