"""
Tests for nestquant.engines module.
"""

import numpy as np
import pandas as pd
import pytest

from nestquant.research.shared.engines.backtest_engine import BacktestConfig, BacktestEngine, Trade
from nestquant.research.shared.engines.base_engine import BaseEngine, EngineState
from nestquant.research.shared.engines.regime_backtest_engine import RegimeBacktestConfig, RegimeBacktestEngine
from nestquant.production.signals.base import BaseSignal, SignalResult


class StubSignal(BaseSignal):
    """A deterministic stub signal for testing."""

    def __init__(self, direction="BUY", strength=0.8):
        super().__init__("stub")
        self._direction = direction
        self._strength = strength

    def generate(self, df, pair):
        if len(df) < 2:
            return SignalResult(pair=pair, direction="NEUTRAL")
        price = df["close"].iloc[-1]
        atr = (df["high"].iloc[-1] - df["low"].iloc[-1]) * 2
        if atr <= 0:
            atr = 0.001
        return SignalResult(
            pair=pair,
            direction=self._direction,
            strength=self._strength,
            entry_price=price,
            sl_price=price - atr if self._direction == "BUY" else price + atr,
            tp_price=price + atr * 2 if self._direction == "BUY" else price - atr * 2,
        )


class NeverSignal(BaseSignal):
    """Signal that never fires."""

    def __init__(self):
        super().__init__("never")

    def generate(self, df, pair):
        return SignalResult(pair=pair, direction="NEUTRAL")


class AlwaysLoseSignal(BaseSignal):
    """Signal that always generates BUY but will hit SL."""

    def __init__(self):
        super().__init__("always_lose")

    def generate(self, df, pair):
        price = df["close"].iloc[-1]
        return SignalResult(
            pair=pair,
            direction="BUY",
            strength=1.0,
            entry_price=price,
            sl_price=price - 0.0001,  # Very tight SL
            tp_price=price + 0.1,  # Very wide TP
        )


class TestEngineState:
    def test_initial_state(self):
        s = EngineState()
        assert not s.running
        assert s.balance == 0.0
        assert s.win_rate == 0.0

    def test_win_rate(self):
        s = EngineState(total_trades=10, winning_trades=6)
        assert s.win_rate == 0.6

    def test_profit_factor(self):
        s = EngineState(balance=1000, total_pnl=50)
        pf = s.profit_factor
        assert pf > 0


class TestBacktestEngine:
    def test_start_stop(self, sample_ohlcv):
        signal = NeverSignal()
        engine = BacktestEngine(signal)
        engine.start()
        assert engine._state.running
        engine.stop()
        assert not engine._state.running

    def test_no_trades_without_session(self, sample_ohlcv):
        signal = StubSignal()
        engine = BacktestEngine(signal)
        engine.start()
        # Saturday session should be filtered
        saturday = pd.Timestamp("2024-01-06 12:00", tz="UTC")
        df = sample_ohlcv.copy()
        df.index = pd.date_range("2024-01-01", periods=len(df), freq="1h", tz="UTC")
        # Override last bar to Saturday
        df.index = df.index[:len(df) - 1].append(pd.DatetimeIndex([saturday]))
        engine.on_bar("EUR/USD", df)
        assert engine._state.total_trades == 0

    def test_never_signal_no_trades(self, sample_ohlcv):
        signal = NeverSignal()
        engine = BacktestEngine(signal)
        engine.start()
        # Feed some bars during session hours (weekday 10am UTC)
        for i in range(50):
            idx = pd.Timestamp(f"2024-01-02 08:00:00+00:00") + pd.Timedelta(hours=i)
            df = sample_ohlcv.iloc[i:i+20].copy()
            df.index = pd.date_range(idx, periods=len(df), freq="1h", tz="UTC")
            engine.on_bar("EUR/USD", df)
        assert engine._state.total_trades == 0

    def test_get_results_empty(self, sample_ohlcv):
        signal = NeverSignal()
        engine = BacktestEngine(signal)
        results = engine.get_results()
        assert results["total_trades"] == 0

    def test_results_structure(self, sample_ohlcv):
        signal = NeverSignal()
        engine = BacktestEngine(signal)
        results = engine.get_results()
        assert "total_trades" in results
        assert "win_rate" in results
        assert "profit_factor" in results
        assert "total_pnl" in results
        assert "max_drawdown" in results
        assert "sharpe_ratio" in results

    def test_backtest_config_defaults(self):
        cfg = BacktestConfig()
        assert cfg.initial_balance == 10000.0
        assert cfg.risk_per_trade == 0.02
        assert cfg.max_open_trades == 1
        assert cfg.commission_per_lot == 6.0
        assert cfg.spread_pips == 1.0
        assert cfg.slippage_pips == 0.1

    def test_trade_dataclass(self):
        t = Trade(
            pair="EUR/USD", direction="BUY",
            entry_price=1.1, entry_time=pd.Timestamp("2024-01-01"),
            sl_price=1.09, tp_price=1.12, lot_size=0.1,
        )
        assert t.is_open
        assert t.duration is None

        t.exit_price = 1.11
        t.exit_time = pd.Timestamp("2024-01-02")
        assert not t.is_open
        assert t.duration == pd.Timedelta(days=1)


class TestRegimeBacktestEngine:
    def test_instantiation(self, sample_ohlcv):
        signal = NeverSignal()
        engine = RegimeBacktestEngine(signal)
        assert isinstance(engine, BacktestEngine)
        assert engine._regime_detector is not None

    def test_custom_config(self, sample_ohlcv):
        signal = NeverSignal()
        cfg = RegimeBacktestConfig(
            use_regime_sizing=True,
            regime_method="adx",
            regime_risk_mult=0.8,
        )
        engine = RegimeBacktestEngine(signal, config=cfg)
        assert engine.config.regime_risk_mult == 0.8

    def test_get_results_empty(self, sample_ohlcv):
        signal = NeverSignal()
        engine = RegimeBacktestEngine(signal)
        results = engine.get_results()
        assert results["total_trades"] == 0

    def test_regime_summary_empty(self, sample_ohlcv):
        signal = NeverSignal()
        engine = RegimeBacktestEngine(signal)
        summary = engine.get_regime_summary()
        assert "error" in summary

    def test_regime_blocks_high_vol(self, sample_ohlcv):
        """HIGH_VOL regime should block new entries."""
        from nestquant.research.shared.regime.labels import RegimeLabel

        signal = StubSignal(direction="BUY", strength=1.0)
        engine = RegimeBacktestEngine(signal)
        # Manually set regime to HIGH_VOL
        from nestquant.research.shared.regime.base import RegimePrediction

        engine._current_regime = RegimePrediction(
            regime=RegimeLabel.HIGH_VOL,
            confidence=0.9,
            scores={RegimeLabel.HIGH_VOL: 0.9},
            features_used=["adx"],
            model_version="test",
        )
        assert not engine._can_trade_in_regime()
