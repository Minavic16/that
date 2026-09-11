"""
Comprehensive Tests for NestQuant S8.6 Monitoring System
=========================================================

Tests for:
- Percentile calculations and sample-size handling
- EV stability analysis
- DD episode detection and clustering
- Circuit breaker calibration
- Slippage measurement
- Latency tracking
- Equity tracking
- Spread collection
- Research data analysis
- Dashboard data endpoints
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import UTC, datetime

import numpy as np
import pytest

NESTQUANT_ROOT = str(Path(__file__).parent.parent)
if NESTQUANT_ROOT not in os.sys.path:
    os.sys.path.insert(0, NESTQUANT_ROOT)

from monitoring.percentiles import (
    PercentileResult,
    PercentileDistribution,
    compute_percentile,
    compute_percentiles,
    classify_value,
    MIN_SAMPLES,
)
from monitoring.ev_stability import (
    EVStabilityAnalyzer,
    CoreEVMetrics,
    RollingWindow,
)
from monitoring.dd_clustering import (
    DDClusterAnalyzer,
    DDEpisode,
    DDCusteringMetrics,
)
from monitoring.circuit_breaker_analysis import (
    CircuitBreakerCalibrator,
    BreakerTriggerAnalysis,
)
from monitoring.slippage import SlippageTracker
from monitoring.equity_tracker import EquityTracker
from monitoring.health_collector import HealthCollector
from monitoring.spread_collector import SpreadCollector
from monitoring.models import (
    MarketSnapshot,
    ExecutionSnapshot,
    AccountSnapshot,
    HealthSnapshot,
    StrategySnapshot,
    LatencySnapshot,
)


# ===================================================================
# PART I: PERCENTILE FRAMEWORK
# ===================================================================


class TestPercentileComputation:
    def test_basic_computation(self):
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = compute_percentile(data, 50, compute_ci=False)
        assert result.value == pytest.approx(5.5, abs=0.1)
        assert result.sample_count == 10
        assert result.sufficient is True

    def test_insufficient_sample_detection(self):
        data = np.array([1.0, 2.0, 3.0])
        result = compute_percentile(data, 99, compute_ci=False)
        assert result.sufficient is False
        assert result.sample_count == 3
        assert result.min_required == MIN_SAMPLES["P99"]
        assert "INSUFFICIENT" in result.label

    def test_empty_data(self):
        data = np.array([])
        result = compute_percentile(data, 50, compute_ci=False)
        assert result.sufficient is False
        assert result.sample_count == 0
        assert np.isnan(result.value)

    def test_single_value(self):
        data = np.array([42.0])
        result = compute_percentile(data, 50, compute_ci=False)
        assert result.value == 42.0
        assert result.sample_count == 1

    def test_full_distribution(self):
        data = np.arange(1, 101, dtype=float)
        dist = compute_percentiles(data, compute_ci=False)
        assert dist.p50.value == pytest.approx(50.5, abs=1.0)
        assert dist.p75.value == pytest.approx(75.5, abs=1.0)
        assert dist.p90.value == pytest.approx(90.5, abs=1.0)
        assert dist.p95.value == pytest.approx(95.5, abs=1.0)
        assert dist.p99.value == pytest.approx(99.5, abs=1.0)
        assert dist.count == 100
        assert dist.mean == pytest.approx(50.5, abs=0.1)

    def test_insufficient_sample_in_distribution(self):
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        dist = compute_percentiles(data, compute_ci=False)
        assert dist.p50.sufficient is True
        assert dist.p75.sufficient is True
        assert dist.p90.sufficient is False
        assert dist.p99.sufficient is False

    def test_classification(self):
        data = np.arange(1, 101, dtype=float)
        dist = compute_percentiles(data, compute_ci=False)
        assert classify_value(50.0, dist) == "NORMAL"
        assert classify_value(80.0, dist) == "WARNING"
        assert classify_value(95.0, dist) == "ABNORMAL"
        assert classify_value(100.0, dist) == "EXTREME"

    def test_classification_insufficient_data(self):
        empty = compute_percentiles(np.array([]), compute_ci=False)
        assert classify_value(5.0, empty) == "INSUFFICIENT DATA"

    def test_percentile_result_to_dict(self):
        result = compute_percentile(np.arange(1, 51, dtype=float), 90, compute_ci=False)
        d = result.to_dict()
        assert "value" in d
        assert "percentile" in d
        assert "sample_count" in d
        assert "sufficient" in d
        assert "label" in d

    def test_distribution_to_dict(self):
        dist = compute_percentiles(np.arange(1, 51, dtype=float), compute_ci=False)
        d = dist.to_dict()
        assert "p50" in d
        assert "p99" in d
        assert "count" in d


# ===================================================================
# PART II: EV STABILITY
# ===================================================================


class TestEVStability:
    def _make_positive_returns(self, n=100):
        rng = np.random.RandomState(42)
        return rng.normal(0.5, 1.0, n)

    def _make_mixed_returns(self, n=100):
        rng = np.random.RandomState(42)
        return rng.normal(0.1, 2.0, n)

    def test_core_metrics(self):
        returns = self._make_positive_returns()
        analyzer = EVStabilityAnalyzer()
        core = analyzer.compute_core_metrics(returns)
        assert core.count == 100
        assert core.mean_return > 0
        assert core.std > 0
        assert core.win_rate > 0.4
        assert core.variance > 0

    def test_empty_returns(self):
        analyzer = EVStabilityAnalyzer()
        core = analyzer.compute_core_metrics(np.array([]))
        assert core.count == 0
        assert core.mean_return == 0

    def test_rolling_windows(self):
        returns = self._make_positive_returns(200)
        analyzer = EVStabilityAnalyzer(window_sizes=[20, 50])
        windows = analyzer.compute_rolling_windows(returns)
        assert len(windows) > 0
        for w in windows:
            assert w.trade_count == 20 or w.trade_count == 50
            assert np.isfinite(w.ev)

    def test_stability_indicators(self):
        returns = self._make_positive_returns(200)
        analyzer = EVStabilityAnalyzer(window_sizes=[30])
        result = analyzer.analyze(returns)
        assert result.stability_indicators["positive_ev_pct"] > 0.5
        assert np.isfinite(result.stability_indicators["rolling_ev_std"])

    def test_full_analysis(self):
        returns = self._make_positive_returns(200)
        analyzer = EVStabilityAnalyzer()
        result = analyzer.analyze(returns)
        assert result.core.count == 200
        assert len(result.rolling_windows) > 0
        assert result.rolling_ev_distribution is not None
        assert result.trade_return_distribution is not None
        assert "positive_ev_pct" in result.stability_indicators

    def test_to_dict(self):
        returns = self._make_positive_returns(100)
        analyzer = EVStabilityAnalyzer()
        result = analyzer.analyze(returns)
        d = result.to_dict()
        assert "core" in d
        assert "stability_indicators" in d
        assert "rolling_ev_distribution" in d

    def test_negative_returns(self):
        returns = np.array([-1.0, -2.0, -3.0, -1.5, -0.5])
        analyzer = EVStabilityAnalyzer()
        core = analyzer.compute_core_metrics(returns)
        assert core.mean_return < 0
        assert core.win_rate == 0.0

    def test_zero_returns(self):
        returns = np.zeros(50)
        analyzer = EVStabilityAnalyzer()
        core = analyzer.compute_core_metrics(returns)
        assert core.mean_return == 0.0
        assert core.std == 0.0


# ===================================================================
# PART III: DD CLUSTERING
# ===================================================================


class TestDDClustering:
    def _make_equity_with_dd(self):
        """Create equity curve with known DD episodes."""
        # Equity: 100, 110, 105 (DD1), 115, 100 (DD2), 120
        return np.array([100, 110, 105, 115, 100, 120])

    def _make_simple_dd(self):
        """Simple equity with one DD episode."""
        return np.array([100, 110, 108, 105, 110, 112])

    def test_detect_single_episode(self):
        eq = self._make_simple_dd()
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq)
        assert len(episodes) >= 1
        ep = episodes[0]
        assert ep.depth > 0
        assert ep.duration > 0

    def test_detect_no_dd(self):
        eq = np.array([100, 105, 110, 115, 120])
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq)
        assert len(episodes) == 0

    def test_detect_multiple_episodes(self):
        eq = self._make_equity_with_dd()
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq)
        assert len(episodes) >= 1

    def test_dd_depth_positive(self):
        eq = np.array([100, 110, 105, 110])
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq)
        for ep in episodes:
            assert ep.depth >= 0
            assert ep.depth_pct >= 0

    def test_unfinished_dd(self):
        eq = np.array([100, 110, 105])
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq)
        assert len(episodes) == 1
        assert episodes[0].recovery_idx is None

    def test_metrics_computation(self):
        eq = self._make_equity_with_dd()
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq)
        metrics = analyzer.compute_metrics(episodes, total_trades=5)
        assert metrics.total_episodes == len(episodes)
        assert metrics.total_trades == 5

    def test_clustering_analysis(self):
        eq = self._make_equity_with_dd()
        returns = np.array([10, -5, 5, -15, 20])
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq, returns)
        clustering = analyzer.compute_clustering_analysis(episodes, 5)
        assert "cluster_probability_50" in clustering
        assert "is_clustered" in clustering

    def test_full_analysis(self):
        eq = self._make_equity_with_dd()
        returns = np.array([10, -5, 5, -15, 20])
        analyzer = DDClusterAnalyzer(n_random_baseline=10)
        result = analyzer.analyze(eq, returns, include_baseline=True)
        assert result.episodes is not None
        assert result.metrics is not None
        assert result.clustering_analysis is not None

    def test_to_dict(self):
        eq = self._make_equity_with_dd()
        analyzer = DDClusterAnalyzer()
        result = analyzer.analyze(eq)
        d = result.to_dict()
        assert "episodes" in d
        assert "metrics" in d
        assert "clustering_analysis" in d

    def test_with_returns_for_loss_count(self):
        eq = np.array([100, 110, 105, 110])
        returns = np.array([10, -5, 5])
        analyzer = DDClusterAnalyzer()
        episodes = analyzer.detect_episodes(eq, returns)
        assert len(episodes) >= 1
        # At least some losses counted during DD
        assert episodes[0].losses_during_dd >= 0


# ===================================================================
# PART IV: CIRCUIT BREAKER CALIBRATION
# ===================================================================


class TestCircuitBreakerCalibration:
    def _make_returns(self, n=200):
        rng = np.random.RandomState(42)
        return rng.normal(0.3, 1.0, n)

    def test_win_rate_breaker(self):
        returns = self._make_returns(200)
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_win_rate_breaker(returns)
        assert result.breaker_name == "WinRateBreaker"
        assert result.total_trades == 200
        assert result.trigger_frequency >= 0

    def test_slippage_breaker(self):
        returns = self._make_returns(100)
        slippages = np.abs(np.random.RandomState(42).normal(0.3, 0.5, 100))
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_slippage_breaker(returns, slippages)
        assert result.breaker_name == "SlippageBreaker"
        assert result.total_trades == 100

    def test_drawdown_pace_breaker(self):
        returns = self._make_returns(200)
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_drawdown_pace_breaker(returns)
        assert result.breaker_name == "DrawdownPaceBreaker"
        assert result.total_trades == 200

    def test_profit_factor_breaker(self):
        returns = self._make_returns(200)
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_profit_factor_breaker(returns)
        assert result.breaker_name == "ProfitFactorBreaker"
        assert result.total_trades == 200

    def test_insufficient_data(self):
        returns = np.array([1.0, -1.0, 2.0])
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_win_rate_breaker(returns, window=20)
        assert result.trigger_count == 0
        assert result.improvement_assessment == "INSUFFICIENT DATA"

    def test_to_dict(self):
        returns = self._make_returns(100)
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_win_rate_breaker(returns)
        d = result.to_dict()
        assert "breaker_name" in d
        assert "trigger_count" in d
        assert "improvement_assessment" in d

    def test_return_impact_calculated(self):
        returns = self._make_returns(200)
        calibrator = CircuitBreakerCalibrator()
        result = calibrator.simulate_win_rate_breaker(returns)
        # Impact should be the difference
        assert result.return_impact == pytest.approx(
            result.return_with_breaker - result.return_without_breaker, abs=0.01
        )


# ===================================================================
# PART V: SLIPPAGE TRACKING
# ===================================================================


class TestSlippageTracking:
    def test_entry_slippage(self):
        tracker = SlippageTracker()
        snap = tracker.record_entry_slippage(1.1000, 1.1002, "EUR/USD")
        assert snap.measured is True
        assert snap.entry_slippage_pips == pytest.approx(2.0, abs=0.1)
        dist = tracker.get_entry_slippage_distribution()
        assert len(dist) == 1
        assert dist[0] == pytest.approx(2.0, abs=0.1)

    def test_exit_slippage(self):
        tracker = SlippageTracker()
        snap = tracker.record_exit_slippage(1.1050, 1.1048, "EUR/USD")
        assert snap.measured is True
        assert snap.exit_slippage_pips == pytest.approx(2.0, abs=0.1)
        dist = tracker.get_exit_slippage_distribution()
        assert len(dist) == 1

    def test_jpy_pip_size(self):
        tracker = SlippageTracker()
        snap = tracker.record_entry_slippage(150.000, 150.020, "USD/JPY")
        dist = tracker.get_entry_slippage_distribution()
        assert dist[0] == pytest.approx(2.0, abs=0.1)

    def test_overall_distribution(self):
        tracker = SlippageTracker()
        tracker.record_entry_slippage(1.1000, 1.1002, "EUR/USD")
        tracker.record_exit_slippage(1.1050, 1.1048, "EUR/USD")
        dist = tracker.get_overall_distribution()
        assert len(dist) == 2

    def test_percentiles(self):
        tracker = SlippageTracker()
        for i in range(50):
            tracker.record_entry_slippage(1.1000, 1.1000 + i * 0.0001, "EUR/USD")
        pcts = tracker.get_percentiles()
        assert "P50" in pcts
        assert "P95" in pcts
        assert pcts["P50"] >= 0
        assert pcts["count"] == 50


# ===================================================================
# PART VI: EQUITY TRACKING
# ===================================================================


class TestEquityTracking:
    def test_record_snapshot(self):
        tracker = EquityTracker()
        tracker.record_snapshot(equity=10000, balance=10000, floating_pnl=0, realized_pnl=0)
        dd = tracker.get_current_drawdown()
        assert dd["absolute"] == 0.0
        assert dd["pct"] == 0.0

    def test_peak_tracking(self):
        tracker = EquityTracker()
        tracker.record_snapshot(equity=10000, balance=10000, floating_pnl=0, realized_pnl=0)
        tracker.record_snapshot(equity=10500, balance=10000, floating_pnl=0, realized_pnl=0)
        tracker.record_snapshot(equity=10200, balance=10000, floating_pnl=0, realized_pnl=0)
        dd = tracker.get_current_drawdown()
        assert dd["absolute"] > 0
        assert dd["pct"] > 0

    def test_peak_to_trough(self):
        tracker = EquityTracker()
        tracker.record_snapshot(equity=10000, balance=10000, floating_pnl=0, realized_pnl=0)
        tracker.record_snapshot(equity=10500, balance=10000, floating_pnl=0, realized_pnl=0)
        tracker.record_snapshot(equity=9800, balance=10000, floating_pnl=0, realized_pnl=0)
        tracker.record_snapshot(equity=10200, balance=10000, floating_pnl=0, realized_pnl=0)
        ptt = tracker.get_peak_to_trough()
        assert ptt > 0

    def test_equity_curve(self):
        tracker = EquityTracker()
        for eq in [10000, 10100, 10050, 10200]:
            tracker.record_snapshot(equity=eq, balance=10000, floating_pnl=0, realized_pnl=0)
        curve = tracker.get_equity_curve()
        assert len(curve) == 4
        assert curve[0] == 10000

    def test_drawdown_series(self):
        tracker = EquityTracker()
        for eq in [10000, 10500, 10200, 10800]:
            tracker.record_snapshot(equity=eq, balance=10000, floating_pnl=0, realized_pnl=0)
        dd_series = tracker.get_drawdown_series()
        assert len(dd_series) == 4
        assert dd_series[0] == 0.0  # No DD at start


# ===================================================================
# PART VII: HEALTH COLLECTION
# ===================================================================


class TestHealthCollection:
    def test_health_collector_init(self):
        collector = HealthCollector()
        assert collector is not None

    def test_uptime_with_no_checks(self):
        collector = HealthCollector()
        # No checks yet, uptime should handle empty state
        assert collector.get_consecutive_failures() == 0


# ===================================================================
# PART VIII: SPREAD COLLECTION
# ===================================================================


class TestSpreadCollection:
    def test_spread_collector_init(self):
        collector = SpreadCollector()
        assert collector is not None

    def test_manual_snapshot(self):
        collector = SpreadCollector()
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC).isoformat(),
            symbol="EUR/USD",
            bid=1.10000,
            ask=1.10020,
            spread=0.00020,
            spread_pips=2.0,
        )
        collector._snapshots.append(snap)
        dist = collector.get_spread_distribution()
        assert len(dist) == 1
        assert dist[0] == 2.0


# ===================================================================
# PART IX: MODELS
# ===================================================================


class TestModels:
    def test_market_snapshot(self):
        snap = MarketSnapshot(
            timestamp="2026-01-01T00:00:00",
            symbol="EUR/USD",
            bid=1.1000,
            ask=1.1002,
            spread=0.0002,
            spread_pips=2.0,
        )
        d = snap.to_dict()
        assert d["symbol"] == "EUR/USD"
        assert d["spread_pips"] == 2.0

    def test_execution_snapshot(self):
        snap = ExecutionSnapshot(
            requested_price=1.1000,
            fill_price=1.1002,
            entry_slippage_pips=0.2,
        )
        d = snap.to_dict()
        assert d["entry_slippage_pips"] == 0.2
        assert d["measured"] is False

    def test_account_snapshot(self):
        snap = AccountSnapshot(
            timestamp="2026-01-01T00:00:00",
            balance=200000,
            equity=200000,
        )
        d = snap.to_dict()
        assert d["balance"] == 200000

    def test_health_snapshot(self):
        snap = HealthSnapshot(
            timestamp="2026-01-01T00:00:00",
            bridge_healthy=True,
            mt5_connected=True,
        )
        d = snap.to_dict()
        assert d["bridge_healthy"] is True

    def test_strategy_snapshot(self):
        snap = StrategySnapshot(total_trades=100, win_rate=0.36)
        d = snap.to_dict()
        assert d["total_trades"] == 100
        assert d["win_rate"] == 0.36

    def test_latency_snapshot(self):
        snap = LatencySnapshot(component="http", latency_ms=150.0, is_measured=True)
        d = snap.to_dict()
        assert d["latency_ms"] == 150.0
        assert d["is_measured"] is True


# ===================================================================
# PART X: RESEARCH DATA ANALYSIS
# ===================================================================


class TestResearchAnalysis:
    def test_load_s0(self):
        from analytics.research_analysis import ResearchAnalyzer
        analyzer = ResearchAnalyzer()
        s0_path = Path(NESTQUANT_ROOT) / "research_data" / "simple_strategies" / "S0_breakout_results.json"
        if s0_path.exists():
            data = analyzer.load_s0_results(str(s0_path))
            assert data is not None
            assert "original_result" in data
        else:
            pytest.skip("S0 data not available")

    def test_load_s5_5(self):
        from analytics.research_analysis import ResearchAnalyzer
        analyzer = ResearchAnalyzer()
        s55_path = Path(NESTQUANT_ROOT) / "research_data" / "simple_strategies" / "S5_5_failure_analysis.json"
        if s55_path.exists():
            data = analyzer.load_s5_5_results(str(s55_path))
            assert data is not None
            assert "monthly_stats" in data
        else:
            pytest.skip("S5_5 data not available")

    def test_analyze_monthly_stats(self):
        from analytics.research_analysis import ResearchAnalyzer
        analyzer = ResearchAnalyzer()
        s55_path = Path(NESTQUANT_ROOT) / "research_data" / "simple_strategies" / "S5_5_failure_analysis.json"
        if s55_path.exists():
            data = analyzer.load_s5_5_results(str(s55_path))
            result = analyzer.analyze_monthly_stats(data)
            assert result.n_months > 0
            assert result.pnl_dist.count > 0
            assert result.max_dd_dist.count > 0
        else:
            pytest.skip("S5_5 data not available")

    def test_analyze_consecutive_losses(self):
        from analytics.research_analysis import ResearchAnalyzer
        analyzer = ResearchAnalyzer()
        s55_path = Path(NESTQUANT_ROOT) / "research_data" / "simple_strategies" / "S5_5_failure_analysis.json"
        if s55_path.exists():
            data = analyzer.load_s5_5_results(str(s55_path))
            result = analyzer.analyze_consecutive_losses(data)
            assert result.n_months > 0
            assert result.max_consec_losses_dist.count > 0
        else:
            pytest.skip("S5_5 data not available")

    def test_analyze_risk_scaling(self):
        from analytics.research_analysis import ResearchAnalyzer
        analyzer = ResearchAnalyzer()
        s6_path = Path(NESTQUANT_ROOT) / "research_data" / "simple_strategies" / "S6_adaptive_risk_challenge.json"
        if s6_path.exists():
            data = analyzer.load_s6_results(str(s6_path))
            result = analyzer.analyze_risk_scaling(data)
            assert len(result.risk_levels) > 0
            assert len(result.max_dd_by_risk) > 0
        else:
            pytest.skip("S6 data not available")

    def test_analyze_monte_carlo(self):
        from analytics.research_analysis import ResearchAnalyzer
        analyzer = ResearchAnalyzer()
        s6_path = Path(NESTQUANT_ROOT) / "research_data" / "simple_strategies" / "S6_adaptive_risk_challenge.json"
        if s6_path.exists():
            data = analyzer.load_s6_results(str(s6_path))
            result = analyzer.analyze_monte_carlo(data)
            assert len(result.scenarios) > 0
            assert len(result.median_max_dd) > 0
        else:
            pytest.skip("S6 data not available")


# ===================================================================
# PART XI: INTEGRATION TESTS
# ===================================================================


class TestIntegration:
    def test_percentiles_feeds_into_classification(self):
        data = np.random.RandomState(42).normal(0, 1, 200)
        dist = compute_percentiles(data, compute_ci=False)
        val = float(np.percentile(data, 85))
        cls = classify_value(val, dist)
        assert cls in ("NORMAL", "WARNING", "ABNORMAL", "EXTREME")

    def test_ev_stability_feeds_into_percentiles(self):
        returns = np.random.RandomState(42).normal(0.5, 1.0, 200)
        analyzer = EVStabilityAnalyzer()
        result = analyzer.analyze(returns)
        if result.rolling_ev_distribution:
            assert result.rolling_ev_distribution.count > 0

    def test_dd_clustering_feeds_into_percentiles(self):
        # Create equity curve with DD
        equity = np.cumsum(np.concatenate([
            np.array([100.0]),
            np.random.RandomState(42).normal(0.5, 2.0, 100),
        ]))
        analyzer = DDClusterAnalyzer(n_random_baseline=10)
        result = analyzer.analyze(equity, include_baseline=False)
        assert result.metrics.total_episodes >= 0

    def test_end_to_end_monitoring_pipeline(self):
        """Test complete pipeline from data collection to analysis."""
        # 1. Collect spread data
        spread_collector = SpreadCollector()
        for i in range(50):
            snap = MarketSnapshot(
                timestamp=datetime.now(UTC).isoformat(),
                symbol="EUR/USD",
                bid=1.10000 + i * 0.00001,
                ask=1.10020 + i * 0.00001,
                spread=0.00020,
                spread_pips=2.0,
            )
            spread_collector._snapshots.append(snap)
        spread_pcts = spread_collector.get_percentiles()
        assert "P50" in spread_pcts

        # 2. Track equity
        equity_tracker = EquityTracker()
        for eq in np.linspace(10000, 10500, 50):
            equity_tracker.record_snapshot(equity=eq, balance=10000, floating_pnl=0, realized_pnl=0)
        dd = equity_tracker.get_current_drawdown()
        assert dd["absolute"] >= 0

        # 3. Analyze DD
        equity_curve = equity_tracker.get_equity_curve()
        dd_analyzer = DDClusterAnalyzer(n_random_baseline=10)
        dd_result = dd_analyzer.analyze(equity_curve, include_baseline=False)
        assert dd_result.metrics is not None

        # 4. Track slippage
        slippage_tracker = SlippageTracker()
        for i in range(30):
            slippage_tracker.record_entry_slippage(
                1.1000, 1.1000 + i * 0.0001, "EUR/USD"
            )
        slip_pcts = slippage_tracker.get_percentiles()
        assert "P50" in slip_pcts

        # 5. Analyze EV
        returns = np.random.RandomState(42).normal(0.3, 1.0, 100)
        ev_analyzer = EVStabilityAnalyzer()
        ev_result = ev_analyzer.analyze(returns)
        assert ev_result.core.count == 100
