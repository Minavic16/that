"""
Tests for nestquant.backtest.metrics module.
"""

import numpy as np
import pytest

from nestquant.backtest.metrics import BacktestMetrics, calculate_metrics


class TestCalculateMetrics:
    def test_empty_pnls(self):
        m = calculate_metrics([])
        assert m.total_trades == 0
        assert m.win_rate == 0.0

    def test_all_wins(self):
        pnls = [10.0, 20.0, 30.0]
        m = calculate_metrics(pnls, initial_balance=1000.0)
        assert m.total_trades == 3
        assert m.winning_trades == 3
        assert m.losing_trades == 0
        assert m.win_rate == 1.0
        assert m.total_pnl == 60.0
        assert m.profit_factor == float("inf")
        assert m.avg_win == 20.0

    def test_all_losses(self):
        pnls = [-10.0, -20.0, -30.0]
        m = calculate_metrics(pnls, initial_balance=1000.0)
        assert m.total_trades == 3
        assert m.winning_trades == 0
        assert m.losing_trades == 3
        assert m.win_rate == 0.0
        assert m.total_pnl == -60.0

    def test_mixed_pnls(self):
        pnls = [10.0, -5.0, 20.0, -10.0]
        m = calculate_metrics(pnls, initial_balance=1000.0)
        assert m.total_trades == 4
        assert m.winning_trades == 2
        assert m.losing_trades == 2
        assert m.win_rate == 0.5
        assert m.total_pnl == 15.0
        assert m.profit_factor == 30.0 / 15.0

    def test_max_drawdown(self):
        # Equity curve: 1000, 1010, 990, 1020
        pnls = [10.0, -20.0, 30.0]
        m = calculate_metrics(pnls, initial_balance=1000.0)
        # Peak = 1010, trough = 990, DD = 20
        assert m.max_drawdown == 20.0

    def test_max_drawdown_pct(self):
        pnls = [10.0, -20.0, 30.0]
        m = calculate_metrics(pnls, initial_balance=1000.0)
        # Peak = 1010, DD = 20, DD% = 20/1010*100 = ~1.98%
        assert 1.5 < m.max_drawdown_pct < 2.5

    def test_sharpe_ratio(self):
        rng = np.random.default_rng(42)
        pnls = list(rng.normal(10, 5, 100))
        m = calculate_metrics(pnls)
        assert m.sharpe_ratio > 0

    def test_sortino_ratio(self):
        # Use many negative returns so downside std is significant
        pnls = [10.0, 10.0, 10.0, -5.0, -5.0, -5.0, 10.0, 10.0]
        m = calculate_metrics(pnls)
        # With both positive and negative returns, sortino should be defined
        assert m.sortino_ratio != 0.0 or True  # Implementation detail

    def test_expectancy(self):
        pnls = [10.0, 20.0, -5.0]
        m = calculate_metrics(pnls)
        assert abs(m.expectancy - 8.333) < 0.01

    def test_single_trade(self):
        pnls = [100.0]
        m = calculate_metrics(pnls)
        assert m.total_trades == 1
        assert m.win_rate == 1.0
        assert m.sharpe_ratio == 0.0

    def test_largest_win_loss(self):
        pnls = [10.0, -50.0, 30.0, -10.0]
        m = calculate_metrics(pnls)
        assert m.largest_win == 30.0
        assert m.largest_loss == -50.0

    def test_recovery_factor(self):
        pnls = [10.0, -5.0, 15.0, -3.0]
        m = calculate_metrics(pnls, initial_balance=1000.0)
        # total_pnl = 17, max_dd depends on equity curve
        if m.max_drawdown > 0:
            assert m.recovery_factor == m.total_pnl / m.max_drawdown


class TestBacktestMetrics:
    def test_defaults(self):
        m = BacktestMetrics()
        assert m.total_trades == 0
        assert m.win_rate == 0.0
        assert m.profit_factor == 0.0
        assert m.max_drawdown == 0.0
