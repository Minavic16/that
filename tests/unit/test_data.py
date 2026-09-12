"""Tests for data validation and acquisition."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from nestquant.core.data.validation import (
    validate_data_quality,
    validate_duplicates,
    validate_gaps,
    validate_missing_values,
    validate_ohlc_integrity,
    validate_price_values,
    validate_timestamps,
    validate_timezone,
)


@pytest.fixture
def valid_ohlcv():
    """Generate valid OHLCV data."""
    n = 100
    timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0001)
    high = close + 0.0001
    low = close - 0.0001
    return pd.DataFrame(
        {"open": close + 0.00005, "high": high, "low": low, "close": close, "volume": np.random.uniform(10, 100, n)},
        index=timestamps,
    )


@pytest.fixture
def invalid_ohlcv():
    """Generate OHLCV data with issues."""
    n = 100
    timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0001)
    high = close + 0.0001
    low = close - 0.0001
    df = pd.DataFrame(
        {"open": close + 0.00005, "high": high, "low": low, "close": close, "volume": np.random.uniform(10, 100, n)},
        index=timestamps,
    )
    # Introduce issues
    df.iloc[5, df.columns.get_loc("high")] = df.iloc[5, df.columns.get_loc("low")] - 0.001  # high < low
    df.iloc[10, df.columns.get_loc("close")] = np.nan  # missing value
    return df


class TestValidateTimestamps:
    def test_ordered_timestamps(self, valid_ohlcv):
        result = validate_timestamps(valid_ohlcv)
        assert result.passed

    def test_unordered_timestamps(self):
        n = 100
        timestamps = pd.date_range("2024-01-02", periods=n, freq="1min", tz="UTC")
        # Shuffle timestamps
        shuffled = timestamps[np.random.permutation(n)]
        df = pd.DataFrame({"close": np.ones(n)}, index=shuffled)
        result = validate_timestamps(df)
        assert not result.passed


class TestValidateDuplicates:
    def test_no_duplicates(self, valid_ohlcv):
        result = validate_duplicates(valid_ohlcv)
        assert result.passed
        assert result.count == 0

    def test_with_duplicates(self):
        timestamps = pd.date_range("2024-01-02", periods=5, freq="1min", tz="UTC")
        # Duplicate one timestamp
        timestamps = timestamps.insert(2, timestamps[1])
        df = pd.DataFrame({"close": np.ones(6)}, index=timestamps)
        result = validate_duplicates(df)
        assert not result.passed
        assert result.count > 0


class TestValidateGaps:
    def test_no_gaps(self, valid_ohlcv):
        result = validate_gaps(valid_ohlcv)
        assert result.passed

    def test_with_gaps(self):
        # Create data with a large gap
        timestamps1 = pd.date_range("2024-01-02", periods=50, freq="1min", tz="UTC")
        timestamps2 = pd.date_range("2024-01-02 02:00", periods=50, freq="1min", tz="UTC")
        timestamps = timestamps1.append(timestamps2)
        df = pd.DataFrame({"close": np.ones(100)}, index=timestamps)
        result = validate_gaps(df)
        assert not result.passed


class TestValidateOHLCIntegrity:
    def test_valid_ohlc(self, valid_ohlcv):
        result = validate_ohlc_integrity(valid_ohlcv)
        assert result.passed

    def test_invalid_ohlc(self, invalid_ohlcv):
        result = validate_ohlc_integrity(invalid_ohlcv)
        assert not result.passed
        assert result.count > 0


class TestValidateMissingValues:
    def test_no_missing(self, valid_ohlcv):
        result = validate_missing_values(valid_ohlcv)
        assert result.passed

    def test_with_missing(self, invalid_ohlcv):
        result = validate_missing_values(invalid_ohlcv)
        assert not result.passed


class TestValidatePriceValues:
    def test_positive_prices(self, valid_ohlcv):
        result = validate_price_values(valid_ohlcv)
        assert result.passed

    def test_negative_prices(self):
        df = pd.DataFrame({"close": [-1.0, -2.0, -3.0]})
        result = validate_price_values(df)
        assert not result.passed


class TestValidateTimezone:
    def test_utc_timezone(self, valid_ohlcv):
        result = validate_timezone(valid_ohlcv)
        assert result.passed

    def test_naive_timestamps(self):
        timestamps = pd.date_range("2024-01-02", periods=5, freq="1min")
        df = pd.DataFrame({"close": np.ones(5)}, index=timestamps)
        result = validate_timezone(df)
        assert not result.passed


class TestValidateDataQuality:
    def test_valid_data(self, valid_ohlcv):
        report = validate_data_quality(valid_ohlcv, source="test", filename="test.csv")
        assert report.is_valid
        assert report.total_bars == 100

    def test_invalid_data(self, invalid_ohlcv):
        report = validate_data_quality(invalid_ohlcv, source="test", filename="test.csv")
        assert not report.is_valid


class TestProvenance:
    def test_provenance_record(self):
        from nestquant.core.data.acquisition import record_provenance

        prov = record_provenance(
            source="dukascopy",
            dataset_id="test-001",
            filename="test.parquet",
            date_range=("2024-01-01", "2024-01-02"),
            instruments=["EUR/USD"],
            timeframe="1min",
            timezone_str="UTC",
            checksum="abc123",
        )
        assert prov["source"] == "dukascopy"
        assert prov["checksum_sha256"] == "abc123"
        assert prov["instruments"] == ["EUR/USD"]
