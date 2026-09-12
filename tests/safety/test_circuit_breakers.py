"""
Tests for nestquant.risk.circuit_breakers module.
"""

import numpy as np
import pytest

from nestquant.production.risk.circuit_breakers import (
    BaseBreaker,
    BreakerSuite,
    CorrelationBreaker,
    DrawdownDriftBreaker,
    DrawdownPaceBreaker,
    ProfitFactorBreaker,
    SlippageBreaker,
    WinRateBreaker,
)


class TestBaseBreaker:
    def test_initial_state(self):
        b = BaseBreaker("test")
        assert not b.paused
        assert not b.hard_stopped
        assert not b.triggered
        assert b.events == []

    def test_pause(self):
        b = BaseBreaker("test")
        b.pause()
        assert b.paused
        assert b.triggered

    def test_hard_stop(self):
        b = BaseBreaker("test")
        b.hard_stop()
        assert b.hard_stopped
        assert b.paused
        assert b.triggered

    def test_reset(self):
        b = BaseBreaker("test")
        b.pause()
        b.reset()
        assert not b.paused
        assert not b.hard_stopped
        assert not b.triggered
        assert b.events == []

    def test_status(self):
        b = BaseBreaker("test")
        s = b.status()
        assert s["name"] == "test"
        assert s["paused"] is False
        assert s["hard_stopped"] is False

    def test_unpause(self):
        b = BaseBreaker("test")
        b.pause()
        b.unpause()
        assert not b.paused


class TestWinRateBreaker:
    def test_no_trigger_with_few_trades(self):
        wr = WinRateBreaker()
        for _ in range(10):
            wr.record_trade(10.0)
        assert not wr.check()

    def test_trigger_on_low_wr_20(self):
        wr = WinRateBreaker(window_20=0.40, window_30=0.45)
        # 20 losses in a row -> WR = 0%
        for _ in range(20):
            wr.record_trade(-10.0)
        assert wr.check()
        assert wr.paused

    def test_no_trigger_on_high_wr(self):
        wr = WinRateBreaker(window_20=0.40, window_30=0.45)
        for _ in range(30):
            wr.record_trade(10.0)
        assert not wr.check()
        assert not wr.paused

    def test_status_includes_wr(self):
        wr = WinRateBreaker()
        for _ in range(25):
            wr.record_trade(10.0)
        s = wr.status()
        assert s["window_20_wr"] is not None
        assert s["total_trades_recorded"] == 25


class TestSlippageBreaker:
    def test_consecutive_trigger(self):
        sb = SlippageBreaker(consecutive_threshold=4.8, consecutive_count=3)
        for _ in range(3):
            sb.record_slippage(5.0)
        assert sb.check()
        assert sb.paused

    def test_no_trigger_below_threshold(self):
        sb = SlippageBreaker(consecutive_threshold=4.8, consecutive_count=3)
        for _ in range(5):
            sb.record_slippage(3.0)
        assert not sb.check()

    def test_rolling_avg_trigger(self):
        sb = SlippageBreaker(avg_10_threshold=6.0)
        for _ in range(10):
            sb.record_slippage(7.0)
        assert sb.check()

    def test_reset_consecutive(self):
        sb = SlippageBreaker(consecutive_threshold=4.8, consecutive_count=3)
        for _ in range(2):
            sb.record_slippage(5.0)
        sb.reset_consecutive()
        assert sb._consecutive_streak == 0


class TestDrawdownPaceBreaker:
    def test_soft_pause(self):
        dp = DrawdownPaceBreaker(soft_dd=6.0, soft_trades=15)
        # Record trades that push DD to 7%
        dp.record_trade(-100, 93, 100)
        assert dp.check()
        assert dp.paused
        assert not dp.hard_stopped

    def test_hard_stop(self):
        dp = DrawdownPaceBreaker(hard_dd=9.0, hard_trades=25)
        dp.record_trade(-100, 90, 100)
        assert dp.check()
        assert dp.hard_stopped

    def test_no_trigger_low_dd(self):
        dp = DrawdownPaceBreaker(soft_dd=6.0, soft_trades=15)
        dp.record_trade(-10, 95, 100)
        assert not dp.check()
        assert not dp.paused


class TestProfitFactorBreaker:
    def test_trigger_on_low_pf(self):
        pf = ProfitFactorBreaker(threshold=1.0, window=20)
        # 20 trades: 5 wins of $10, 15 losses of $10 -> PF = 50/150 = 0.33
        for _ in range(5):
            pf.record_trade(10.0)
        for _ in range(15):
            pf.record_trade(-10.0)
        assert pf.check()
        assert pf.paused

    def test_no_trigger_on_high_pf(self):
        pf = ProfitFactorBreaker(threshold=1.0, window=20)
        for _ in range(15):
            pf.record_trade(10.0)
        for _ in range(5):
            pf.record_trade(-5.0)
        assert not pf.check()

    def test_no_trigger_insufficient_data(self):
        pf = ProfitFactorBreaker(threshold=1.0, window=20)
        for _ in range(10):
            pf.record_trade(10.0)
        assert not pf.check()


class TestCorrelationBreaker:
    def test_trigger_on_high_correlation(self):
        cb = CorrelationBreaker(threshold=0.80)
        # Create a highly correlated matrix
        corr = np.array([[1.0, 0.9, 0.85], [0.9, 1.0, 0.88], [0.85, 0.88, 1.0]])
        cb.update_matrix(corr)
        assert cb.paused

    def test_no_trigger_low_correlation(self):
        cb = CorrelationBreaker(threshold=0.80)
        corr = np.array([[1.0, 0.3, 0.2], [0.3, 1.0, 0.25], [0.2, 0.25, 1.0]])
        cb.update_matrix(corr)
        assert not cb.paused

    def test_small_matrix_ignored(self):
        cb = CorrelationBreaker(threshold=0.80)
        corr = np.array([[1.0, 0.9], [0.9, 1.0]])
        cb.update_matrix(corr)
        # 2x2 matrix should be ignored (n < 3)
        assert cb._avg_correlation is None


class TestDrawdownDriftBreaker:
    def test_trigger_on_drift(self):
        ddb = DrawdownDriftBreaker(expected_dd_pct=5.0, max_drift_pct=10.0)
        # Drift threshold = max(5*2, 10) = 10%
        ddb.record_state(balance=90, peak=100)  # DD = 10%
        assert ddb.check()
        assert ddb.hard_stopped

    def test_no_trigger_within_threshold(self):
        ddb = DrawdownDriftBreaker(expected_dd_pct=5.0, max_drift_pct=10.0)
        ddb.record_state(balance=93, peak=100)  # DD = 7%
        assert not ddb.check()

    def test_disabled_by_default(self):
        ddb = DrawdownDriftBreaker(expected_dd_pct=0.0, max_drift_pct=0.0)
        ddb.record_state(balance=50, peak=100)
        assert not ddb.check()


class TestBreakerSuite:
    def test_initial_can_trade(self):
        suite = BreakerSuite()
        can, reason = suite.can_trade
        assert can
        assert reason is None

    def test_record_trade(self):
        suite = BreakerSuite()
        suite.record_trade(pnl=10.0, equity=10100, peak=10000, slippage_pips=0.5)
        # Should not crash

    def test_check_all(self):
        suite = BreakerSuite()
        events = suite.check_all()
        assert isinstance(events, list)

    def test_status(self):
        suite = BreakerSuite()
        s = suite.status()
        assert "can_trade" in s
        assert "breakers" in s
        assert "winrate" in s["breakers"]

    def test_reset(self):
        suite = BreakerSuite()
        suite.winrate.pause()
        assert suite.winrate.paused
        suite.reset()
        assert not suite.winrate.paused

    def test_correlation_update(self):
        suite = BreakerSuite()
        corr = np.array([[1.0, 0.3], [0.3, 1.0]])
        suite.update_correlation(corr)
        # 2x2 is ignored
        assert not suite.correlation.paused

    def test_blocked_reason(self):
        suite = BreakerSuite()
        suite.winrate.pause()
        can, reason = suite.can_trade
        assert not can
        assert "winrate" in reason

    def test_custom_overrides(self):
        overrides = {"winrate": {"window_20": 0.30, "window_30": 0.35}}
        suite = BreakerSuite(breaker_overrides=overrides)
        assert suite.winrate.window_20 == 0.30
        assert suite.winrate.window_30 == 0.35
