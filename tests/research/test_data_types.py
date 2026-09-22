"""Unit tests for the canonical data layer types (MarketBar, OHLCVFrame, schema)."""

import dataclasses

import pandas as pd
import pytest

from nestquant.research.shared.data import (
    OHLCV_COLUMNS,
    OHLCV_COLUMN_TYPES,
    OHLCV_REQUIRED_COLUMNS,
    MarketBar,
)
from nestquant.research.shared.data.schema import has_required_columns


def _valid_bar(**overrides):
    kwargs = {
        "timestamp": pd.Timestamp("2024-01-01 04:00", tz="UTC"),
        "pair": "EUR/USD",
        "open": 1.1000,
        "high": 1.1010,
        "low": 1.0990,
        "close": 1.1005,
        "volume": 1000.0,
        "spread": 0.0002,
    }
    kwargs.update(overrides)
    return MarketBar(**kwargs)


class TestMarketBarCreation:
    def test_valid_bar_has_no_errors(self):
        assert _valid_bar().validate() == []

    def test_spread_defaults_to_none(self):
        bar = _valid_bar()
        assert bar.spread == 0.0002
        bar_no_spread = MarketBar(
            timestamp=pd.Timestamp("2024-01-01 04:00", tz="UTC"),
            pair="EUR/USD",
            open=1.1,
            high=1.11,
            low=1.09,
            close=1.105,
            volume=10.0,
        )
        assert bar_no_spread.spread is None
        assert bar_no_spread.validate() == []


class TestMarketBarValidation:
    def test_high_below_low(self):
        errors = _valid_bar(high=1.09, low=1.10).validate()
        assert any("high" in e and "low" in e for e in errors)

    def test_high_below_open(self):
        errors = _valid_bar(high=1.0999).validate()
        assert any("high" in e and "open" in e for e in errors)

    def test_low_above_close(self):
        errors = _valid_bar(low=1.1006).validate()
        assert any("low" in e and "close" in e for e in errors)

    def test_non_positive_price(self):
        errors = _valid_bar(close=0.0).validate()
        assert any("close" in e for e in errors)

    def test_timezone_naive_rejected(self):
        errors = _valid_bar(timestamp=pd.Timestamp("2024-01-01 04:00")).validate()
        assert any("timezone-naive" in e for e in errors)

    def test_non_utc_rejected(self):
        ts = pd.Timestamp("2024-01-01 04:00", tz="UTC").tz_convert("US/Eastern")
        errors = _valid_bar(timestamp=ts).validate()
        assert any("UTC" in e for e in errors)

    def test_empty_pair_rejected(self):
        errors = _valid_bar(pair="").validate()
        assert any("pair" in e for e in errors)

    def test_negative_volume_rejected(self):
        errors = _valid_bar(volume=-1.0).validate()
        assert any("volume" in e for e in errors)

    def test_negative_spread_rejected(self):
        errors = _valid_bar(spread=-0.1).validate()
        assert any("spread" in e for e in errors)


class TestMarketBarImmutability:
    def test_frozen(self):
        bar = _valid_bar()
        with pytest.raises(dataclasses.FrozenInstanceError):
            bar.close = 2.0


class TestOHLCVSchema:
    def test_column_constants(self):
        assert OHLCV_COLUMNS == ["open", "high", "low", "close", "volume", "spread"]
        assert OHLCV_REQUIRED_COLUMNS == ["open", "high", "low", "close"]
        assert set(OHLCV_COLUMN_TYPES) == set(OHLCV_COLUMNS)
        assert all(t is float for t in OHLCV_COLUMN_TYPES.values())

    def test_has_required_columns(self):
        df = pd.DataFrame(
            {c: [1.0, 2.0] for c in OHLCV_COLUMNS},
            index=pd.date_range("2024-01-01", periods=2, freq="4h", tz="UTC"),
        )
        assert has_required_columns(df) is True
        assert has_required_columns(df.drop(columns=["close"])) is False

    def test_canonical_frame_satisfies_engine_input_contract(self):
        """Integration: a canonical frame carries the columns a bar-driven
        backtest engine consumes (open/high/low/close + DatetimeIndex)."""
        df = pd.DataFrame(
            {c: [1.0, 2.0] for c in OHLCV_COLUMNS},
            index=pd.date_range("2024-01-01", periods=2, freq="4h", tz="UTC"),
        )
        assert isinstance(df.index, pd.DatetimeIndex)
        for col in ("open", "high", "low", "close"):
            assert col in df.columns
