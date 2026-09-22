"""Unit + integration tests for the canonical OHLCV data loader."""

import numpy as np
import pandas as pd
import pytest

from nestquant.research.shared.data import DataLoader, validate_ohlcv, validation_passed
from nestquant.research.shared.data.features import (
    compute_log_returns,
    realized_volatility_backward,
    realized_volatility_forward,
)


def _frame(n=48, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    close = 1.1000 + np.cumsum(rng.normal(0, 0.0005, n))
    open_ = np.roll(close, 1)
    open_[0] = 1.1000
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + np.abs(rng.normal(0.0004, 0.0001, n)),
            "low": np.minimum(open_, close) - np.abs(rng.normal(0.0004, 0.0001, n)),
            "close": close,
            "volume": rng.uniform(100, 1000, n),
            "spread": rng.uniform(0.0001, 0.0005, n),
        },
        index=idx,
    )


def _write_pickle(data_dir, pair, df, timeframe="4h"):
    tf_dir = data_dir / timeframe
    tf_dir.mkdir(parents=True, exist_ok=True)
    path = tf_dir / f"{pair.replace('/', '_')}.pkl"
    pd.to_pickle({pair: df}, path)
    return path


class TestDataLoaderSinglePair:
    def test_load_one_pair(self, tmp_path):
        expected = _frame()
        _write_pickle(tmp_path, "EUR/USD", expected)
        loader = DataLoader(data_dir=str(tmp_path))
        df = loader.load("EUR/USD", timeframe="4h")
        assert df is not None
        pd.testing.assert_frame_equal(df, expected)

    def test_load_legacy_flat_layout(self, tmp_path):
        expected = _frame()
        pd.to_pickle({"EUR/USD": expected}, tmp_path / "EUR_USD.pkl")
        loader = DataLoader(data_dir=str(tmp_path))
        df = loader.load("EUR/USD", timeframe="4h")
        assert df is not None
        pd.testing.assert_frame_equal(df, expected)


class TestDataLoaderAllPairs:
    def test_load_multiple_pairs(self, tmp_path):
        _write_pickle(tmp_path, "EUR/USD", _frame(seed=1))
        _write_pickle(tmp_path, "GBP/USD", _frame(seed=2))
        loader = DataLoader(data_dir=str(tmp_path))
        frames = loader.load_all(["EUR/USD", "GBP/USD"], timeframe="4h")
        assert set(frames) == {"EUR/USD", "GBP/USD"}
        assert len(frames["EUR/USD"]) == 48


class TestDataLoaderMissingFile:
    def test_missing_file_returns_none(self, tmp_path):
        loader = DataLoader(data_dir=str(tmp_path))
        assert loader.load("EUR/USD", timeframe="4h") is None

    def test_load_all_skips_missing(self, tmp_path):
        _write_pickle(tmp_path, "EUR/USD", _frame())
        loader = DataLoader(data_dir=str(tmp_path))
        frames = loader.load_all(["EUR/USD", "USD/JPY"], timeframe="4h")
        assert set(frames) == {"EUR/USD"}

    def test_schema_violation_returns_none(self, tmp_path):
        bad = _frame().drop(columns=["close"])
        _write_pickle(tmp_path, "EUR/USD", bad)
        loader = DataLoader(data_dir=str(tmp_path))
        assert loader.load("EUR/USD", timeframe="4h") is None


class TestDataLoaderTimezone:
    def test_naive_index_raises(self, tmp_path):
        naive = _frame().tz_localize(None)
        _write_pickle(tmp_path, "EUR/USD", naive)
        loader = DataLoader(data_dir=str(tmp_path))
        with pytest.raises(ValueError, match="timezone-naive"):
            loader.load("EUR/USD", timeframe="4h")

    def test_utc_index_succeeds(self, tmp_path):
        _write_pickle(tmp_path, "EUR/USD", _frame())
        loader = DataLoader(data_dir=str(tmp_path))
        df = loader.load("EUR/USD", timeframe="4h")
        assert df is not None
        assert str(df.index.tz) == "UTC"


class TestOHLCVWithFeatures:
    def test_ohlcv_with_features_integration(self, tmp_path):
        """Integration: load -> validate -> log returns -> forward/backward
        volatility, with hand-computed spot checks."""
        closes = pd.Series(
            [100.0, 101.0, 102.0, 100.0],
            index=pd.date_range("2024-01-01", periods=4, freq="4h", tz="UTC"),
        )
        rets = compute_log_returns(closes)
        assert np.isnan(rets.iloc[0])
        assert rets.iloc[1] == np.log(101.0 / 100.0)
        assert rets.iloc[3] == np.log(100.0 / 102.0)

        # Forward RV at h=1 reduces to |r[t+1]| (Stage 2 resolved target).
        fwd1 = realized_volatility_forward(closes, horizon=1)
        assert np.isclose(fwd1.iloc[0], abs(rets.iloc[1]))
        assert np.isclose(fwd1.iloc[2], abs(rets.iloc[3]))
        assert np.isnan(fwd1.iloc[3])

        # Forward RV at h=2: sqrt(r[t+1]^2 + r[t+2]^2).
        fwd2 = realized_volatility_forward(closes, horizon=2)
        assert np.isclose(fwd2.iloc[0], np.sqrt(rets.iloc[1] ** 2 + rets.iloc[2] ** 2))

        # Backward RV: rolling std over the window.
        back = realized_volatility_backward(rets.dropna(), window=2)
        assert np.isclose(back.iloc[1], rets.dropna().iloc[0:2].std())

        # Full path on loaded data.
        _write_pickle(tmp_path, "EUR/USD", _frame())
        loader = DataLoader(data_dir=str(tmp_path))
        df = loader.load("EUR/USD", timeframe="4h")
        assert df is not None
        assert validation_passed(validate_ohlcv(df)) is True
        loaded_rets = compute_log_returns(df["close"])
        assert len(loaded_rets.dropna()) == len(df) - 1
