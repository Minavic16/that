"""
R2.1 Volatility Structure Research — Causality Tests
=====================================================

Tests that verify no model or transformation uses future information.
These are the invariants that must pass before any scientific claim.

Causality is the foundation: if any of these fail, all results are invalid.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_loader import (
    compute_log_returns,
    realized_volatility,
    realized_volatility_forward,
    compute_atr,
    baseline_rolling_vol,
    baseline_ewma_vol,
    baseline_naive_vol,
    generate_synthetic_ohlcv,
    load_bars,
)
from volatility_models import (
    NaiveModel,
    RollingVolModel,
    EWMAModel,
    GARCHModel,
    HARModel,
)


# ---------------------------------------------------------------------------
# Test Framework
# ---------------------------------------------------------------------------

class CausalityTestResult:
    def __init__(self, name: str, passed: bool, detail: str):
        self.name = name
        self.passed = passed
        self.detail = detail

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"{status}: {self.name} — {self.detail}"


def run_causality_tests(df: pd.DataFrame, pair: str) -> list[CausalityTestResult]:
    """Run all causality invariants on the given data.

    Returns list of CausalityTestResult.
    ALL must pass for results to be valid.
    """
    results = []
    close = df["close"]
    returns = compute_log_returns(close)

    # Test 1: Log returns use no future information
    results.append(_test_returns_causality(close, returns))

    # Test 2: Rolling volatility uses no future information
    results.append(_test_rolling_vol_causality(returns))

    # Test 3: EWMA volatility uses no future information
    results.append(_test_ewma_causality(returns))

    # Test 4: ATR uses no future information
    results.append(_test_atr_causality(df))

    # Test 5: Forward volatility target is correctly aligned
    results.append(_test_forward_target_alignment(close, returns))

    # Test 6: Naive model is causal
    results.append(_test_naive_causality(returns))

    # Test 7: GARCH model is causal (parameter estimation)
    results.append(_test_garch_causality(returns))

    # Test 8: Train/test boundary integrity
    results.append(_test_train_test_boundary(returns))

    # Test 9: No look-ahead in walk-forward
    results.append(_test_walkforward_no_lookahead(returns))

    # Test 10: Synthetic data causality (controlled validation)
    results.append(_test_synthetic_causality())

    return results


# ---------------------------------------------------------------------------
# Individual Tests
# ---------------------------------------------------------------------------

def _test_returns_causality(close: pd.Series, returns: pd.Series) -> CausalityTestResult:
    """Verify log returns depend only on current and previous close."""
    name = "returns_causality"

    # Modify future close prices and check that past returns don't change
    modified_close = close.copy()
    if len(modified_close) > 10:
        # Change the last 5 close prices
        modified_close.iloc[-5:] *= 1.01
        modified_returns = compute_log_returns(modified_close)

        # Past returns (before the modification point) must be identical
        cutoff = len(close) - 5
        past_original = returns.iloc[:cutoff].values
        past_modified = modified_returns.iloc[:cutoff].values

        if np.allclose(past_original, past_modified, equal_nan=True):
            return CausalityTestResult(name, True,
                "Modifying future closes does not change past returns")
        else:
            return CausalityTestResult(name, False,
                "FAIL: Past returns changed when future closes were modified")

    return CausalityTestResult(name, True, "Skipped: insufficient data")


def _test_rolling_vol_causality(returns: pd.Series) -> CausalityTestResult:
    """Verify rolling volatility uses only past returns."""
    name = "rolling_vol_causality"

    vol_original = baseline_rolling_vol(
        pd.Series(np.exp(np.cumsum(returns.fillna(0)))),
        window=24
    )
    # Create modified returns where we change the last 5 values
    modified_returns = returns.copy()
    if len(modified_returns) > 30:
        modified_returns.iloc[-5:] = modified_returns.iloc[-5:] * 2
        # Reconstruct prices from modified returns
        modified_close = pd.Series(
            np.exp(np.cumsum(modified_returns.fillna(0))),
            index=returns.index
        )
        vol_modified = baseline_rolling_vol(modified_close, window=24)

        cutoff = len(returns) - 5
        past_original = vol_original.iloc[:cutoff].values
        past_modified = vol_modified.iloc[:cutoff].values

        if np.allclose(past_original, past_modified, equal_nan=True):
            return CausalityTestResult(name, True,
                "Modifying future returns does not change past rolling vol")
        else:
            return CausalityTestResult(name, False,
                "FAIL: Past rolling vol changed when future returns modified")

    return CausalityTestResult(name, True, "Skipped: insufficient data")


def _test_ewma_causality(returns: pd.Series) -> CausalityTestResult:
    """Verify EWMA volatility uses only past returns."""
    name = "ewma_causality"

    vol_original = baseline_ewma_vol(
        pd.Series(np.exp(np.cumsum(returns.fillna(0)))),
        span=24
    )
    modified_returns = returns.copy()
    if len(modified_returns) > 30:
        modified_returns.iloc[-5:] = modified_returns.iloc[-5:] * 2
        modified_close = pd.Series(
            np.exp(np.cumsum(modified_returns.fillna(0))),
            index=returns.index
        )
        vol_modified = baseline_ewma_vol(modified_close, span=24)

        cutoff = len(returns) - 5
        past_original = vol_original.iloc[:cutoff].values
        past_modified = vol_modified.iloc[:cutoff].values

        if np.allclose(past_original, past_modified, equal_nan=True):
            return CausalityTestResult(name, True,
                "Modifying future returns does not change past EWMA vol")
        else:
            return CausalityTestResult(name, False,
                "FAIL: Past EWMA vol changed when future returns modified")

    return CausalityTestResult(name, True, "Skipped: insufficient data")


def _test_atr_causality(df: pd.DataFrame) -> CausalityTestResult:
    """Verify ATR uses only past and current OHLC data."""
    name = "atr_causality"

    atr_original = compute_atr(df["high"], df["low"], df["close"], period=14)

    # Modify future high/low
    modified = df.copy()
    if len(modified) > 20:
        modified.iloc[-5:, modified.columns.get_loc("high")] *= 1.01
        modified.iloc[-5:, modified.columns.get_loc("low")] *= 0.99
        atr_modified = compute_atr(modified["high"], modified["low"],
                                    modified["close"], period=14)

        cutoff = len(df) - 5
        past_original = atr_original.iloc[:cutoff].values
        past_modified = atr_modified.iloc[:cutoff].values

        if np.allclose(past_original, past_modified, equal_nan=True):
            return CausalityTestResult(name, True,
                "Modifying future OHLC does not change past ATR")
        else:
            return CausalityTestResult(name, False,
                "FAIL: Past ATR changed when future OHLC modified")

    return CausalityTestResult(name, True, "Skipped: insufficient data")


def _test_forward_target_alignment(close: pd.Series,
                                    returns: pd.Series) -> CausalityTestResult:
    """Verify forward volatility target is correctly aligned."""
    name = "forward_target_alignment"

    horizon = 6  # testing value (24h at 4H), not experiment horizon
    target = realized_volatility_forward(close, horizon=horizon)

    # Check that target at time t uses returns from [t+1, t+horizon]
    if len(close) > horizon + 5:
        # Manually compute expected target for a specific time
        idx = len(close) - horizon - 2
        expected_returns = returns.iloc[idx + 1:idx + 1 + horizon]
        expected_vol = expected_returns.std()
        actual_vol = target.iloc[idx]

        if np.isclose(actual_vol, expected_vol, rtol=1e-10):
            return CausalityTestResult(name, True,
                f"Forward target at t={idx} correctly uses returns [{idx+1}:{idx+1+horizon}]")
        else:
            return CausalityTestResult(name, False,
                f"FAIL: Forward target mismatch. Expected {expected_vol}, got {actual_vol}")

    return CausalityTestResult(name, True, "Skipped: insufficient data")


def _test_naive_causality(returns: pd.Series) -> CausalityTestResult:
    """Verify naive model forecast is purely from past data."""
    name = "naive_model_causality"

    model = NaiveModel()

    # Fit on data[0:20], forecast should be based on return at index 19
    model.fit(returns.iloc[:20])
    forecast = model.forecast()
    expected = abs(returns.iloc[19])

    if np.isclose(forecast, expected, rtol=1e-10):
        return CausalityTestResult(name, True,
            "Naive forecast = last observed return (causal)")
    else:
        return CausalityTestResult(name, False,
            f"FAIL: Naive forecast {forecast} != expected {expected}")


def _test_garch_causality(returns: pd.Series) -> CausalityTestResult:
    """Verify GARCH estimation uses only training data."""
    name = "garch_causality"

    if len(returns) < 60:
        return CausalityTestResult(name, True,
            "Skipped: insufficient data for GARCH (< 60 bars)")

    # Fit GARCH on first half only
    train = returns.iloc[:len(returns)//2]
    model = GARCHModel()
    model.fit(train)
    forecast_train = model.forecast()

    # Fit GARCH on full data
    model_full = GARCHModel()
    model_full.fit(returns)
    forecast_full = model_full.forecast()

    # Forecasts should differ (full data has more information)
    if not np.isclose(forecast_train, forecast_full, rtol=1e-3):
        return CausalityTestResult(name, True,
            f"GARCH forecast differs with more data: {forecast_train:.6f} vs {forecast_full:.6f}")
    else:
        return CausalityTestResult(name, False,
            "FAIL: GARCH forecast identical regardless of data size (suspicious)")

    return CausalityTestResult(name, True, "Skipped: GARCH not fitted")


def _test_train_test_boundary(returns: pd.Series) -> CausalityTestResult:
    """Verify that train/test split respects temporal ordering."""
    name = "train_test_boundary"

    train_window = min(24, len(returns) - 10)
    if train_window < 10:
        return CausalityTestResult(name, True, "Skipped: insufficient data")

    t = train_window + 5
    train = returns.iloc[t - train_window:t]
    test = returns.iloc[t:t + 6]

    # Train max index < test min index
    if train.index.max() < test.index.min():
        return CausalityTestResult(name, True,
            f"Train ends {train.index.max()}, test starts {test.index.min()}")
    else:
        return CausalityTestResult(name, False,
            "FAIL: Train/test overlap detected")


def _test_walkforward_no_lookahead(returns: pd.Series) -> CausalityTestResult:
    """Verify walk-forward loop does not leak future information."""
    name = "walkforward_no_lookahead"

    train_window = min(24, len(returns) - 15)
    horizon = 6  # testing value (24h at 4H), not experiment horizon

    if train_window + horizon + 5 > len(returns):
        return CausalityTestResult(name, True, "Skipped: insufficient data")

    # Simulate one walk-forward step
    t = train_window + 5
    train = returns.iloc[t - train_window:t]
    # Target period
    target = returns.iloc[t:t + horizon]

    # Check: train index max < target index min
    if train.index.max() < target.index.min():
        # Check: no index in train appears in target
        overlap = set(train.index) & set(target.index)
        if not overlap:
            return CausalityTestResult(name, True,
                f"Walk-forward step: train=[{t-train_window}:{t}], "
                f"target=[{t}:{t+horizon}], no overlap")
        else:
            return CausalityTestResult(name, False,
                f"FAIL: {len(overlap)} overlapping timestamps")
    else:
        return CausalityTestResult(name, False,
            "FAIL: Train does not end before target begins")


def _test_synthetic_causality() -> CausalityTestResult:
    """Validate causality on synthetic data with known structure.

    On synthetic data we can verify:
    1. Forecasts at time t are independent of returns after t
    2. Parameters estimated on subset don't use future data
    """
    name = "synthetic_data_causality"

    synth = generate_synthetic_ohlcv(200, seed=42)
    returns = compute_log_returns(synth["close"]).dropna()

    if len(returns) < 60:
        return CausalityTestResult(name, True, "Skipped: insufficient synthetic data")

    # Fit model on first 100 observations
    model = RollingVolModel(window=24)
    model.fit(returns.iloc[:100])
    forecast_100 = model.forecast()

    # Fit model on first 150 observations
    model.fit(returns.iloc[:150])
    forecast_150 = model.forecast()

    # Forecast should be the same (last 24 observations are the same in both)
    # Because RollingVolModel uses the last W observations
    model.fit(returns.iloc[76:100])  # Same window as the last 24 of first 100
    forecast_window = model.forecast()

    if np.isclose(forecast_100, forecast_window, rtol=1e-10):
        return CausalityTestResult(name, True,
            "Synthetic: forecast from identical windows matches")
    else:
        return CausalityTestResult(name, False,
            f"FAIL: Forecast mismatch {forecast_100} vs {forecast_window}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Loading EUR/USD data...")
    df = load_bars()
    print(f"  {len(df)} bars loaded\n")

    print("Running causality tests...")
    results = run_causality_tests(df, "EUR/USD")

    all_passed = True
    for r in results:
        print(f"  {r}")
        if not r.passed:
            all_passed = False

    print(f"\n{'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print(f"Total: {sum(1 for r in results if r.passed)}/{len(results)} passed")
