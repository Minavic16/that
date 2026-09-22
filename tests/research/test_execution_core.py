"""Tests for the strategy-agnostic execution core (Phase 2 decoupling)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nestquant.research.shared.engines.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    Trade,
)
from nestquant.research.shared.execution import (
    BacktestConfig as ExecBacktestConfig,
    ExecutionSimulator,
    Portfolio,
    SignalIntent,
    Trade as ExecTrade,
    to_signal_intent,
)


def _session_df(n: int = 24, start: str = "2024-01-02 08:00") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    close = [1.10 + 0.0002 * i for i in range(n)]
    open_ = [c - 0.0001 for c in close]
    high = [c + 0.0005 for c in close]
    low = [c - 0.0005 for c in close]
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": [100.0] * n},
        index=idx,
    )


class DuckSignal:
    """Strategy duck-type — does not inherit production BaseSignal."""

    def __init__(self, direction: str = "BUY", strength: float = 1.0):
        self.name = "duck"
        self._direction = direction
        self._strength = strength

    def generate(self, df, pair):
        price = float(df["close"].iloc[-1])
        sl = price - 0.001 if self._direction == "BUY" else price + 0.001
        tp = price + 0.002 if self._direction == "BUY" else price - 0.002
        active = self._direction in ("BUY", "SELL") and self._strength > 0
        return type(
            "DuckResult",
            (),
            {
                "pair": pair,
                "direction": self._direction,
                "strength": self._strength,
                "entry_price": price,
                "sl_price": sl,
                "tp_price": tp,
                "metadata": {},
                "is_active": active,
            },
        )()


class TestSignalIntent:
    def test_is_active_buy(self):
        i = SignalIntent(pair="EUR/USD", direction="BUY", strength=1.0)
        assert i.is_active

    def test_is_active_neutral(self):
        i = SignalIntent(pair="EUR/USD", direction="NEUTRAL")
        assert not i.is_active

    def test_zero_strength_not_active(self):
        i = SignalIntent(pair="EUR/USD", direction="BUY", strength=0.0)
        assert not i.is_active

    def test_to_signal_intent_passthrough(self):
        i = SignalIntent(pair="EUR/USD", direction="BUY", strength=0.5, metadata={"k": 1})
        assert to_signal_intent(i) is i

    def test_to_signal_intent_from_duck(self):
        class S:
            pair = "EUR/USD"
            direction = "SELL"
            strength = 0.7
            entry_price = 1.1
            sl_price = 1.11
            tp_price = 1.09
            metadata = {"rrr": 3.5}

        i = to_signal_intent(S())
        assert i.direction == "SELL"
        assert i.metadata["rrr"] == 3.5
        assert i.is_active


class TestExecutionPackageBoundary:
    def test_no_production_imports_in_source(self):
        pkg = Path(__file__).resolve().parents[2] / "research" / "shared" / "execution"
        for py in pkg.glob("*.py"):
            src = py.read_text()
            assert "production." not in src, f"{py} imports production"
            assert "nestquant.production" not in src, f"{py} imports nestquant.production"

    def test_module_import_does_not_load_production_signals(self):
        import importlib
        import sys

        # Drop cached production signals if already loaded by other tests
        mods = [k for k in sys.modules if k.startswith("nestquant.production.signals")]
        for m in mods:
            del sys.modules[m]
        importlib.import_module("nestquant.research.shared.execution")
        assert not any(k.startswith("nestquant.production.signals") for k in sys.modules)


class TestExecutionSimulator:
    def test_open_and_exit_without_engine(self):
        cfg = BacktestConfig(initial_balance=10000.0, risk_per_trade=0.02)
        sim = ExecutionSimulator(cfg)
        intent = SignalIntent(
            pair="EUR/USD",
            direction="BUY",
            strength=1.0,
            entry_price=1.1000,
            sl_price=1.0990,
            tp_price=1.1020,
            metadata={},
        )
        ts = pd.Timestamp("2024-01-02 10:00", tz="UTC")
        trade = sim.open_trade(intent, ts)
        assert trade is not None
        assert len(sim.portfolio.open_trades) == 1
        assert sim.portfolio.trades[0] is trade

        # Bar that hits TP only (low stays above SL)
        df = _session_df(n=1)
        df.index = pd.DatetimeIndex([pd.Timestamp("2024-01-02 11:00", tz="UTC")])
        df.loc[:, "high"] = 1.11
        df.loc[:, "low"] = 1.0995
        closed = sim.check_exits("EUR/USD", df)
        assert len(closed) == 1
        assert closed[0].exit_reason == "tp"
        assert not closed[0].is_open
        assert sim.portfolio.balance != 10000.0
        results = sim.get_results()
        assert results["total_trades"] == 1

    def test_on_close_callback_order(self):
        cfg = BacktestConfig()
        sim = ExecutionSimulator(cfg)
        intent = SignalIntent(
            pair="EUR/USD",
            direction="BUY",
            strength=1.0,
            entry_price=1.10,
            sl_price=1.09,
            tp_price=1.11,
        )
        sim.open_trade(intent, pd.Timestamp("2024-01-02 10:00", tz="UTC"))
        seen = []
        df = _session_df(n=1)
        df.index = pd.DatetimeIndex([pd.Timestamp("2024-01-02 11:00", tz="UTC")])
        df.loc[:, "high"] = 1.2
        sim.check_exits(
            "EUR/USD",
            df,
            on_close=lambda pnl, bal, peak: seen.append((pnl, bal, peak)),
        )
        assert len(seen) == 1
        pnl, bal, peak = seen[0]
        assert bal == pytest.approx(10000.0 + pnl)
        assert peak >= bal

    def test_zero_sl_distance_rejects_open(self):
        cfg = BacktestConfig(spread_pips=0.0, slippage_pips=0.0)
        sim = ExecutionSimulator(cfg)
        intent = SignalIntent(
            pair="EUR/USD",
            direction="BUY",
            strength=1.0,
            entry_price=1.10,
            sl_price=1.10,
            tp_price=1.12,
        )
        assert sim.open_trade(intent, pd.Timestamp("2024-01-02 10:00", tz="UTC")) is None
        assert sim.portfolio.open_trades == []

    def test_portfolio_reset_preserves_trades(self):
        p = Portfolio(10000.0)
        t = ExecTrade(
            pair="EUR/USD",
            direction="BUY",
            entry_price=1.1,
            entry_time=pd.Timestamp("2024-01-01"),
            sl_price=1.09,
            tp_price=1.12,
            lot_size=0.1,
            exit_price=1.11,
            exit_time=pd.Timestamp("2024-01-02"),
            pnl=50.0,
        )
        p.open(t)
        p.balance = 10050.0
        p.peak_balance = 10050.0
        p.open_trades.remove(t)
        p.reset(10000.0)
        assert p.balance == 10000.0
        assert p.peak_balance == 10000.0
        assert p.trades == [t]


class TestBacktestEngineAdapter:
    def test_accepts_duck_signal_without_base_signal(self):
        engine = BacktestEngine(DuckSignal(direction="BUY"), BacktestConfig())
        engine.start()
        df = _session_df(n=48)
        for i in range(len(df) - 10):
            engine.on_bar("EUR/USD", df.iloc[i : i + 10])
        results = engine.get_results()
        assert results["total_trades"] >= 1
        assert engine._breakers is not None

    def test_reexports_compatible_types(self):
        assert ExecBacktestConfig is BacktestConfig
        assert ExecTrade is Trade

    def test_config_setter_updates_simulator(self):
        engine = BacktestEngine(DuckSignal())
        engine.config = BacktestConfig(initial_balance=5000.0, max_open_trades=3)
        assert engine._sim.config.initial_balance == 5000.0
        assert engine.config.max_open_trades == 3

    def test_start_resets_balance_not_trades(self):
        engine = BacktestEngine(DuckSignal())
        engine.start()
        df = _session_df(n=48)
        for i in range(20):
            engine.on_bar("EUR/USD", df.iloc[i : i + 10])
        n_before = len(engine._trades)
        bal_before = engine._balance
        engine.start()
        assert len(engine._trades) == n_before
        assert engine._balance == engine.config.initial_balance
        assert bal_before != engine._balance or n_before == 0
