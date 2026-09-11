"""NestQuant Analytics — Research Data Analysis

Analyzes S0-S6 research data to extract trade-level distributions
and drawdown statistics from the simple_strategies experiments.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from monitoring.percentiles import compute_percentiles


@dataclass
class MonthlyStatsResult:
    """Aggregated monthly statistics distributions."""
    pnl_dist: Any  # PercentileDistribution
    max_dd_dist: Any
    max_consec_losses_dist: Any
    win_rate_dist: Any
    profit_factor_dist: Any
    trade_count_dist: Any
    n_months: int


@dataclass
class DrawdownEpisode:
    """Single reconstructed drawdown episode."""
    month: str
    depth_pips: float
    peak_pnl_before: float
    trough_pnl_after: float
    recovery_pnl: float | None


@dataclass
class ConsecutiveLossResult:
    """Consecutive loss streak analysis."""
    max_consec_losses_dist: Any
    mean_consec_losses: float
    median_consec_losses: float
    n_months: int


@dataclass
class RiskScalingResult:
    """Risk-scaled drawdown analysis from S6F."""
    risk_levels: list[dict[str, Any]]
    max_dd_by_risk: list[float]
    avg_return_by_risk: list[float]
    survival_rates: list[bool]


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation percentiles from S6H."""
    scenarios: list[dict[str, Any]]
    median_max_dd: list[float]
    p95_max_dd: list[float]
    p99_max_dd: list[float]
    median_return: list[float]
    prob_violated_dd: list[float]


@dataclass
class YearByYearResult:
    """Year-by-year stats from S0."""
    years: list[str]
    yearly_data: dict[str, dict[str, Any]]
    win_rates: Any  # PercentileDistribution
    avg_pnl_pips: Any
    profit_factors: Any
    max_dd_pips: Any


class ResearchAnalyzer:
    """Analyzes S0-S6 research data for trade-level distributions and drawdown stats."""

    def load_s0_results(self, filepath: str | Path) -> dict[str, Any]:
        """Load S0_breakout_results.json."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"S0 results not found: {path}")
        with open(path) as f:
            return json.load(f)

    def load_s5_5_results(self, filepath: str | Path) -> dict[str, Any]:
        """Load S5_5_failure_analysis.json."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"S5.5 results not found: {path}")
        with open(path) as f:
            return json.load(f)

    def load_s6_results(self, filepath: str | Path) -> dict[str, Any]:
        """Load S6_adaptive_risk_challenge.json."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"S6 results not found: {path}")
        with open(path) as f:
            return json.load(f)

    def analyze_monthly_stats(self, s5_5_data: dict[str, Any]) -> MonthlyStatsResult:
        """Compute monthly PnL, max DD, consecutive losses, win rate, PF distributions."""
        monthly = s5_5_data.get("monthly_stats", [])
        if not monthly:
            return MonthlyStatsResult(
                pnl_dist=None, max_dd_dist=None, max_consec_losses_dist=None,
                win_rate_dist=None, profit_factor_dist=None, trade_count_dist=None,
                n_months=0,
            )

        pnl_arr = np.array([m["total_pnl"] for m in monthly], dtype=float)
        dd_arr = np.abs(np.array([m["max_dd"] for m in monthly], dtype=float))
        cl_arr = np.array([m["max_consec_losses"] for m in monthly], dtype=float)
        wr_arr = np.array([m["win_rate"] for m in monthly], dtype=float)
        pf_arr = np.array([m["profit_factor"] for m in monthly], dtype=float)
        tc_arr = np.array([m["n_trades"] for m in monthly], dtype=float)

        return MonthlyStatsResult(
            pnl_dist=compute_percentiles(pnl_arr),
            max_dd_dist=compute_percentiles(dd_arr),
            max_consec_losses_dist=compute_percentiles(cl_arr),
            win_rate_dist=compute_percentiles(wr_arr),
            profit_factor_dist=compute_percentiles(pf_arr),
            trade_count_dist=compute_percentiles(tc_arr),
            n_months=len(monthly),
        )

    def analyze_drawdown_episodes(self, s5_5_data: dict[str, Any]) -> list[DrawdownEpisode]:
        """Reconstruct drawdown episodes from monthly data.

        For each month, the drawdown episode is the intra-month max DD.
        """
        monthly = s5_5_data.get("monthly_stats", [])
        episodes: list[DrawdownEpisode] = []
        for m in monthly:
            depth = abs(m["max_dd"])
            episodes.append(DrawdownEpisode(
                month=m["month"],
                depth_pips=depth,
                peak_pnl_before=0.0,  # Not available in monthly summary
                trough_pnl_after=depth,
                recovery_pnl=None,
            ))
        return episodes

    def analyze_consecutive_losses(self, s5_5_data: dict[str, Any]) -> ConsecutiveLossResult:
        """Analyze max consecutive loss distribution across months."""
        monthly = s5_5_data.get("monthly_stats", [])
        if not monthly:
            return ConsecutiveLossResult(
                max_consec_losses_dist=None, mean_consec_losses=0.0,
                median_consec_losses=0.0, n_months=0,
            )

        cl_arr = np.array([m["max_consec_losses"] for m in monthly], dtype=float)
        return ConsecutiveLossResult(
            max_consec_losses_dist=compute_percentiles(cl_arr),
            mean_consec_losses=float(np.mean(cl_arr)),
            median_consec_losses=float(np.median(cl_arr)),
            n_months=len(monthly),
        )

    def analyze_risk_scaling(self, s6_data: dict[str, Any]) -> RiskScalingResult:
        """Extract risk-scaled DD from S6F section."""
        s6f = s6_data.get("S6F", {})
        if not s6f:
            return RiskScalingResult(
                risk_levels=[], max_dd_by_risk=[], avg_return_by_risk=[], survival_rates=[],
            )

        risk_levels: list[dict[str, Any]] = []
        max_dd_by_risk: list[float] = []
        avg_return_by_risk: list[float] = []
        survival_rates: list[bool] = []

        for key, val in s6f.items():
            if not isinstance(val, dict):
                continue
            risk_levels.append(val)
            max_dd_by_risk.append(val.get("max_dd_pct", float("nan")))
            avg_return_by_risk.append(val.get("avg_monthly_return_pct", float("nan")))
            survival_rates.append(val.get("reached_target", False))

        return RiskScalingResult(
            risk_levels=risk_levels,
            max_dd_by_risk=max_dd_by_risk,
            avg_return_by_risk=avg_return_by_risk,
            survival_rates=survival_rates,
        )

    def analyze_monte_carlo(self, s6_data: dict[str, Any]) -> MonteCarloResult:
        """Extract S6H Monte Carlo percentiles."""
        s6h = s6_data.get("S6H", {})
        if not s6h:
            return MonteCarloResult(
                scenarios=[], median_max_dd=[], p95_max_dd=[], p99_max_dd=[],
                median_return=[], prob_violated_dd=[],
            )

        scenarios: list[dict[str, Any]] = []
        median_max_dd: list[float] = []
        p95_max_dd: list[float] = []
        p99_max_dd: list[float] = []
        median_return: list[float] = []
        prob_violated_dd: list[float] = []

        for key, val in s6h.items():
            if not isinstance(val, dict):
                continue
            scenarios.append(val)
            median_max_dd.append(val.get("median_max_dd_dollar", float("nan")))
            p95_max_dd.append(val.get("p95_max_dd_dollar", float("nan")))
            p99_max_dd.append(val.get("p99_max_dd_dollar", float("nan")))
            median_return.append(val.get("median_return_dollar", float("nan")))
            prob_violated_dd.append(val.get("prob_violated_dd", float("nan")))

        return MonteCarloResult(
            scenarios=scenarios,
            median_max_dd=median_max_dd,
            p95_max_dd=p95_max_dd,
            p99_max_dd=p99_max_dd,
            median_return=median_return,
            prob_violated_dd=prob_violated_dd,
        )

    def analyze_year_by_year(self, s0_data: dict[str, Any]) -> YearByYearResult:
        """Extract year-by-year stats from S0."""
        yby = s0_data.get("year_by_year", {})
        if not yby:
            return YearByYearResult(
                years=[], yearly_data={}, win_rates=None,
                avg_pnl_pips=None, profit_factors=None, max_dd_pips=None,
            )

        years = sorted(yby.keys())
        yearly_data = {k: v for k, v in yby.items() if isinstance(v, dict)}

        wr_arr = np.array([yearly_data[y].get("win_rate", float("nan")) for y in years], dtype=float)
        pnl_arr = np.array([yearly_data[y].get("avg_pnl_pips", float("nan")) for y in years], dtype=float)
        pf_arr = np.array([yearly_data[y].get("profit_factor", float("nan")) for y in years], dtype=float)
        dd_arr = np.array([yearly_data[y].get("max_dd_pips", float("nan")) for y in years], dtype=float)

        return YearByYearResult(
            years=years,
            yearly_data=yearly_data,
            win_rates=compute_percentiles(wr_arr),
            avg_pnl_pips=compute_percentiles(pnl_arr),
            profit_factors=compute_percentiles(pf_arr),
            max_dd_pips=compute_percentiles(dd_arr),
        )
