"""Unit + integration tests for canonical OHLCV validation."""

import numpy as np
import pandas as pd

from nestquant.research.shared.data import (
    validate_4h_alignment,
    validate_duplicates,
    validate_gaps,
    validate_ohlcv,
    validate_prices,
    validate_schema,
    validate_timestamps,
    validate_volume_spread,
    validation_passed,
)
from nestquant.research.shared.data.validate import classify_gap, detect_gaps


def _frame(n=48, start="2024-01-01", freq="4h", tz="UTC", seed=7):
    """Deterministic valid 4H OHLCV frame (Monday 2024-01-01 00:00 UTC)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq, tz=tz)
    close = 1.1000 + np.cumsum(rng.normal(0, 0.0005, n))
    spread_h = np.abs(rng.normal(0.0004, 0.0001, n))
    spread_l = np.abs(rng.normal(0.0004, 0.0001, n))
    open_ = np.roll(close, 1)
    open_[0] = 1.1000
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread_h,
            "low": np.minimum(open_, close) - spread_l,
            "close": close,
            "volume": rng.uniform(100, 1000, n),
            "spread": rng.uniform(0.0001, 0.0005, n),
        },
        index=idx,
    )


class TestValidateTimestamps:
    def test_valid_utc_passes(self):
        assert validate_timestamps(_frame()).passed is True

    def test_naive_rejected(self):
        df = _frame().tz_localize(None)
        r = validate_timestamps(df)
        assert r.passed is False

    def test_non_utc_rejected(self):
        df = _frame().tz_convert("US/Eastern")
        assert validate_timestamps(df).passed is False

    def test_non_monotonic_rejected(self):
        df = _frame().iloc[::-1]
        assert validate_timestamps(df).passed is False

    def test_non_datetime_index_rejected(self):
        df = _frame().reset_index(drop=True)
        assert validate_timestamps(df).passed is False


class TestValidate4HAlignment:
    def test_valid_alignment_passes(self):
        assert validate_4h_alignment(_frame()).passed is True

    def test_1h_bars_rejected(self):
        assert validate_4h_alignment(_frame(freq="1h")).passed is False

    def test_0401_rejected(self):
        idx = pd.DatetimeIndex(
            ["2024-01-01 04:01", "2024-01-01 08:00", "2024-01-01 12:00"], tz="UTC"
        )
        assert validate_4h_alignment(pd.DataFrame({"a": [1, 2, 3]}, index=idx)).passed is False

    def test_0430_rejected(self):
        idx = pd.DatetimeIndex(
            ["2024-01-01 04:30", "2024-01-01 08:00", "2024-01-01 12:00"], tz="UTC"
        )
        assert validate_4h_alignment(pd.DataFrame({"a": [1, 2, 3]}, index=idx)).passed is False

    def test_040001_rejected(self):
        idx = pd.DatetimeIndex(
            ["2024-01-01 04:00:01", "2024-01-01 08:00", "2024-01-01 12:00"], tz="UTC"
        )
        assert validate_4h_alignment(pd.DataFrame({"a": [1, 2, 3]}, index=idx)).passed is False

    def test_microsecond_rejected(self):
        idx = pd.DatetimeIndex(["2024-01-01 08:00", "2024-01-01 12:00"], tz="UTC")
        idx = idx.insert(0, pd.Timestamp("2024-01-01 04:00", tz="UTC") + pd.Timedelta(microseconds=1))
        assert validate_4h_alignment(pd.DataFrame({"a": [1, 2, 3]}, index=idx)).passed is False


class TestValidatePrices:
    def test_valid_prices_pass(self):
        assert validate_prices(_frame()).passed is True

    def test_high_below_low_fails(self):
        df = _frame()
        df.loc[df.index[5], "high"] = df.loc[df.index[5], "low"] - 0.001
        r = validate_prices(df)
        assert r.passed is False
        assert "high < low" in r.message

    def test_non_positive_fails(self):
        df = _frame()
        df.loc[df.index[3], "close"] = 0.0
        assert validate_prices(df).passed is False

    def test_nan_close_rejected(self):
        df = _frame()
        df.loc[df.index[3], "close"] = float("nan")
        r = validate_prices(df)
        assert r.passed is False
        assert "non-finite" in r.message

    def test_pos_inf_high_rejected(self):
        df = _frame()
        df.loc[df.index[3], "high"] = float("inf")
        r = validate_prices(df)
        assert r.passed is False
        assert "non-finite" in r.message

    def test_neg_inf_low_rejected(self):
        df = _frame()
        df.loc[df.index[3], "low"] = float("-inf")
        assert validate_prices(df).passed is False


class TestValidateVolumeSpread:
    def test_valid_passes(self):
        assert validate_volume_spread(_frame()).passed is True

    def test_nan_volume_rejected(self):
        df = _frame()
        df.loc[df.index[3], "volume"] = float("nan")
        r = validate_volume_spread(df)
        assert r.passed is False
        assert "non-finite" in r.message

    def test_nan_spread_rejected(self):
        df = _frame()
        df.loc[df.index[3], "spread"] = float("nan")
        r = validate_volume_spread(df)
        assert r.passed is False
        assert "non-finite" in r.message

    def test_inf_volume_rejected(self):
        df = _frame()
        df.loc[df.index[3], "volume"] = float("inf")
        assert validate_volume_spread(df).passed is False


class TestValidateDuplicates:
    def test_no_duplicates_pass(self):
        assert validate_duplicates(_frame()).passed is True

    def test_duplicates_fail_not_validated(self):
        df = pd.concat([_frame(n=10), _frame(n=10).iloc[[0]]])
        r = validate_duplicates(df)
        assert r.passed is False
        assert "NOT_VALIDATED" in r.message


class TestValidateGaps:
    def test_no_gaps_pass(self):
        assert validate_gaps(_frame()).passed is True

    def test_runner_gap_passes_informational(self):
        df = _frame(n=48).drop(_frame(n=48).index[10])  # 8h gap
        r = validate_gaps(df)
        assert r.passed is True
        assert "1 runner" in r.message

    def test_weekend_gap_passes_informational(self):
        # Friday 2024-01-05 20:00 UTC -> Monday 2024-01-08 00:00 UTC = 52h
        df = _frame(n=200)
        fri = pd.Timestamp("2024-01-05 20:00", tz="UTC")
        mon = pd.Timestamp("2024-01-08 00:00", tz="UTC")
        assert fri in df.index and mon in df.index
        trimmed = df[(df.index <= fri) | (df.index >= mon)]
        gaps = detect_gaps(trimmed)
        assert len(gaps) == 1
        assert gaps[0]["gap_type"] == "weekend_gap"
        assert validate_gaps(trimmed).passed is True

    def test_corruption_gap_fails(self):
        df = _frame(n=200)
        trimmed = df.iloc[:20].copy()
        trimmed = pd.concat([trimmed, df.iloc[120:]])
        gaps = detect_gaps(trimmed)
        assert any(g["gap_type"] == "corruption_gap" for g in gaps)
        assert validate_gaps(trimmed).passed is False

    def test_classify_gap_boundaries(self):
        assert classify_gap(8) == "runner_gap"
        assert classify_gap(43.9) == "runner_gap"
        assert classify_gap(44) == "weekend_gap"
        assert classify_gap(76) == "weekend_gap"
        assert classify_gap(77) == "holiday_gap"
        assert classify_gap(120) == "holiday_gap"
        assert classify_gap(121) == "corruption_gap"


class TestValidateSchema:
    def test_valid_schema_passes(self):
        assert validate_schema(_frame()).passed is True

    def test_missing_column_fails(self):
        assert validate_schema(_frame().drop(columns=["close"])).passed is False

    def test_wrong_dtype_fails(self):
        df = _frame()
        df["close"] = df["close"].astype(str)
        assert validate_schema(df).passed is False


class TestValidateOHLCVComposite:
    def test_all_checks_pass_on_valid_frame(self):
        results = validate_ohlcv(_frame())
        assert len(results) == 7
        assert validation_passed(results) is True

    def test_composite_fails_on_bad_frame(self):
        df = _frame()
        df.loc[df.index[2], "low"] = df.loc[df.index[2], "high"] + 1.0
        results = validate_ohlcv(df)
        assert validation_passed(results) is False
        assert any(r.name == "prices" and not r.passed for r in results)

    def test_ohlcv_through_validation_integration(self):
        """Integration: build frame -> validate -> pass (load path covered
        in test_data_loader.py)."""
        df = _frame(n=100, seed=42)
        results = validate_ohlcv(df)
        assert validation_passed(results) is True
        assert {r.name for r in results} == {
            "timestamps",
            "4h_alignment",
            "schema",
            "duplicates",
            "prices",
            "volume_spread",
            "gaps",
        }
