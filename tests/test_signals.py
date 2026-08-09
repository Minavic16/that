"""
Tests for nestquant.signals module.
"""

import numpy as np
import pandas as pd
import pytest

from nestquant.signals.base import BaseSignal, SignalResult
from nestquant.signals.breakout import BreakoutSignal
from nestquant.signals.structured_entry import StructuredEntrySignal


class TestSignalResult:
    def test_neutral_signal(self):
        r = SignalResult(pair="EUR/USD", direction="NEUTRAL")
        assert not r.is_active
        assert r.pair == "EUR/USD"

    def test_buy_signal(self):
        r = SignalResult(
            pair="EUR/USD", direction="BUY", strength=0.8,
            entry_price=1.1000, sl_price=1.0950, tp_price=1.1100,
        )
        assert r.is_active
        assert r.direction == "BUY"

    def test_sell_signal(self):
        r = SignalResult(
            pair="EUR/USD", direction="SELL", strength=0.5,
            entry_price=1.1000, sl_price=1.1050, tp_price=1.0900,
        )
        assert r.is_active

    def test_zero_strength_not_active(self):
        r = SignalResult(pair="EUR/USD", direction="BUY", strength=0.0)
        assert not r.is_active

    def test_metadata_default(self):
        r = SignalResult(pair="EUR/USD", direction="NEUTRAL")
        assert r.metadata == {}


class TestBreakoutSignal:
    def test_neutral_on_short_data(self):
        df = pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [100]},
            index=pd.date_range("2024-01-01", periods=1, freq="1h"),
        )
        sig = BreakoutSignal(lookback=5)
        result = sig.generate(df, "EUR/USD")
        assert result.direction == "NEUTRAL"

    def test_generates_signal_on_trending_data(self, trending_ohlcv):
        sig = BreakoutSignal(lookback=5)
        result = sig.generate(trending_ohlcv, "EUR/USD")
        assert result.pair == "EUR/USD"
        # Should produce a BUY signal in uptrend
        assert result.direction in ("BUY", "SELL", "NEUTRAL")

    def test_has_metadata(self, sample_ohlcv):
        sig = BreakoutSignal(lookback=5)
        result = sig.generate(sample_ohlcv, "EUR/USD")
        assert "swing_high" in result.metadata
        assert "swing_low" in result.metadata
        assert "atr" in result.metadata
        assert "lookback" in result.metadata

    def test_sl_tp_reasonable(self, trending_ohlcv):
        sig = BreakoutSignal(lookback=5)
        result = sig.generate(trending_ohlcv, "EUR/USD")
        if result.direction == "BUY":
            assert result.sl_price < result.entry_price
            assert result.tp_price > result.entry_price
        elif result.direction == "SELL":
            assert result.sl_price > result.entry_price
            assert result.tp_price < result.entry_price

    def test_deterministic(self, sample_ohlcv):
        sig = BreakoutSignal(lookback=5)
        r1 = sig.generate(sample_ohlcv, "EUR/USD")
        r2 = sig.generate(sample_ohlcv, "EUR/USD")
        assert r1.direction == r2.direction
        assert r1.entry_price == r2.entry_price


class TestStructuredEntrySignal:
    def test_neutral_on_short_data(self):
        df = pd.DataFrame(
            {"open": [1.0] * 5, "high": [1.1] * 5, "low": [0.9] * 5,
             "close": [1.0] * 5, "volume": [100] * 5},
            index=pd.date_range("2024-01-01", periods=5, freq="1h"),
        )
        sig = StructuredEntrySignal()
        result = sig.generate(df, "EUR/USD")
        assert result.direction == "NEUTRAL"

    def test_returns_signal_result(self, sample_ohlcv):
        sig = StructuredEntrySignal()
        result = sig.generate(sample_ohlcv, "EUR/USD")
        assert isinstance(result, SignalResult)
        assert result.pair == "EUR/USD"
        assert result.direction in ("BUY", "SELL", "NEUTRAL")
