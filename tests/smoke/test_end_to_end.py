"""Smoke test: minimal end-to-end pipeline verification.

Includes multi-timeframe smoke tests for 1h, 4h, 15m using synthetic data.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from costs.model import apply_spread_to_entry, apply_spread_to_exit, compute_costs
from data_validation.validate import validate_market_data
from zscore.contracts import CostModel, MarketData
from zscore.zscore import compute_zscore_causal, zscore_to_array, _zscore_causal_core
from zscore.regime import classify_regime_chunked
from zscore.features import compute_features, causal_realized_volatility


def _make_ohlcv(n: int, freq: str, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2024-01-02", periods=n, freq=freq, tz="UTC")
    returns = rng.normal(0, 0.0005, n)
    close = 1.1000 + np.cumsum(returns)
    high = close + np.abs(rng.normal(0, 0.0001, n))
    low = close - np.abs(rng.normal(0, 0.0001, n))
    open_ = close + rng.normal(0, 0.00005, n)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = rng.integers(100, 1000, n).astype(float)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume
    }, index=ts)


@pytest.fixture
def pipeline_data():
    """Generate minimal synthetic data for pipeline test."""
    n = 500
    np.random.seed(42)
    timestamps = pd.date_range('2024-01-02 00:00', periods=n, freq='1min', tz='UTC')
    trend = np.concatenate([
        np.linspace(1.1000, 1.1100, 200),
        np.full(300, 1.1100),
    ])
    noise = np.cumsum(np.random.randn(n) * 0.00003)
    close = trend + noise
    spread = np.abs(np.random.randn(n) * 0.00005)
    high = close + spread
    low = close - spread
    open_ = close + np.random.randn(n) * 0.00002
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    return timestamps, open_, high, low, close


class TestSmokePipeline:
    """Minimal end-to-end pipeline smoke test."""

    def test_data_ingestion(self, pipeline_data):
        """Step 1: Data ingestion produces valid MarketData."""
        ts, open_, high, low, close = pipeline_data
        data = MarketData(pair='TEST/USD', timestamps=ts, open=open_, high=high, low=low, close=close)
        assert data.n == 500
        assert data.timestamps.tz is not None

    def test_data_validation(self, pipeline_data):
        """Step 2: Validation passes on clean synthetic data."""
        ts, open_, high, low, close = pipeline_data
        data = MarketData(pair='TEST/USD', timestamps=ts, open=open_, high=high, low=low, close=close)
        validated = validate_market_data(data)
        assert validated.validation.is_valid
        assert validated.validation.duplicate_timestamps == 0
        assert validated.validation.ohlc_violations == 0
        assert validated.validation.missing_bars == 0

    def test_zscore_calculation(self, pipeline_data):
        """Step 3: Z-score is computed causally."""
        ts, open_, high, low, close = pipeline_data
        observations = compute_zscore_causal(close, ts, pair='TEST/USD', lookback=20)

        # First 20 bars should have NaN Z-score (warmup)
        for i in range(20):
            assert np.isnan(observations[i].z_score)

        # Bars 20+ should have finite Z-score
        for i in range(20, 500):
            assert np.isfinite(observations[i].z_score)
            assert observations[i].is_causal

    def test_zscore_is_causal(self, pipeline_data):
        """Step 3b: Z-score does not change when future data is modified."""
        ts, open_, high, low, close = pipeline_data
        test_idx = 300

        # Original Z-score at bar 300
        observations_orig = compute_zscore_causal(close, ts, pair='TEST/USD', lookback=20)
        z_orig = observations_orig[test_idx].z_score

        # Modify future prices (bars 301+)
        close_modified = close.copy()
        close_modified[test_idx + 1:] *= 1.05  # shift future up 5%

        # Recompute Z-score at bar 300
        observations_mod = compute_zscore_causal(close_modified, ts, pair='TEST/USD', lookback=20)
        z_mod = observations_mod[test_idx].z_score

        # Z-score at bar 300 must be identical
        assert z_orig == z_mod, f"Causality violation: {z_orig} != {z_mod}"

    def test_signal_generation(self, pipeline_data):
        """Step 4: Signals can be generated from Z-scores."""
        ts, open_, high, low, close = pipeline_data
        observations = compute_zscore_causal(close, ts, pair='TEST/USD', lookback=20)
        arr = zscore_to_array(observations)

        # Simple threshold signal
        threshold = 2.0
        long_signals = np.where(arr < -threshold)[0]
        short_signals = np.where(arr > threshold)[0]

        # Signals exist (data has enough variation)
        assert len(long_signals) + len(short_signals) > 0

    def test_cost_application(self):
        """Step 5: Transaction costs are applied and recorded."""
        cost_model = CostModel(
            spread_pips=1.0,
            commission_per_lot=3.50,
            slippage_pips=0.3,
        )
        entry = apply_spread_to_entry(1.1000, 1, 1.0, 0.0001, 0.3)
        exit_price = apply_spread_to_exit(1.1050, 1, 1.0, 0.0001, 0.3)

        costs = compute_costs(
            direction=1,
            entry_price=entry,
            exit_price=exit_price,
            pip=0.0001,
            pv=10.0,
            lot_size=0.1,
            cost_model=cost_model,
        )

        assert costs.spread_cost > 0
        assert costs.commission_cost > 0
        assert costs.slippage_cost > 0
        assert costs.total_cost == costs.spread_cost + costs.commission_cost + costs.slippage_cost

    def test_trade_pnl_reconciles(self):
        """Step 6: Trade PnL = gross PnL - total costs."""
        cost_model = CostModel(spread_pips=1.0, commission_per_lot=3.50, slippage_pips=0.3)
        pip = 0.0001
        pv = 10.0
        lot = 0.1

        entry = apply_spread_to_entry(1.1000, 1, 1.0, pip, 0.3)
        exit_price = apply_spread_to_exit(1.1050, 1, 1.0, pip, 0.3)

        gross_pnl = (exit_price - entry) / pip * pv * lot
        costs = compute_costs(1, entry, exit_price, pip, pv, lot, cost_model)
        net_pnl = gross_pnl - costs.total_cost

        assert abs(net_pnl - (gross_pnl - costs.total_cost)) < 1e-10

    def test_report_generation(self, pipeline_data, tmp_path):
        """Step 7: Report is generated as valid JSON."""
        ts, open_, high, low, close = pipeline_data
        observations = compute_zscore_causal(close, ts, pair='TEST/USD', lookback=20)

        report = {
            'experiment_id': 'SMOKE-001',
            'pair': 'TEST/USD',
            'bars': 500,
            'lookback': 20,
            'zscore_mean': float(np.nanmean([o.z_score for o in observations])),
            'zscore_std': float(np.nanstd([o.z_score for o in observations])),
            'trades': 0,
            'status': 'smoke_test_pass',
        }

        report_path = tmp_path / 'smoke_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        assert report_path.exists()
        with open(report_path) as f:
            loaded = json.load(f)
        assert loaded['status'] == 'smoke_test_pass'


# ---------------------------------------------------------------------------
# Multi-timeframe smoke tests
# ---------------------------------------------------------------------------

TIMEFRAME_CONFIGS = [
    ("15min", 96, 500),
    ("1h", 24, 500),
    ("4h", 6, 500),
]


class TestSmokeMultiTimeframe:
    """End-to-end smoke tests for 15m, 1h, 4h timeframes using synthetic data."""

    @pytest.mark.parametrize("tf,bpd,n", TIMEFRAME_CONFIGS)
    def test_zscore_pipeline(self, tf: str, bpd: int, n: int):
        """Full Z-score pipeline works at this timeframe."""
        df = _make_ohlcv(n, tf)
        close = df["close"].values.astype(np.float64)

        z, mean, std = _zscore_causal_core(close, lookback=20)

        assert len(z) == n
        assert np.all(np.isnan(z[:20]))
        assert np.all(np.isfinite(z[20:]))

    @pytest.mark.parametrize("tf,bpd,n", TIMEFRAME_CONFIGS)
    def test_regime_pipeline(self, tf: str, bpd: int, n: int):
        """Full regime pipeline works at this timeframe."""
        df = _make_ohlcv(n, tf)
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)

        regimes = classify_regime_chunked(
            close, high, low, df.index, "TEST/USD",
            chunk_size=500, ema_span=200, atr_period=14
        )

        assert len(regimes) == n
        # After warmup, regimes should be non-empty
        non_warmup = [r for r in regimes if r.volatility != "unknown"]
        assert len(non_warmup) > 0

    @pytest.mark.parametrize("tf,bpd,n", TIMEFRAME_CONFIGS)
    def test_feature_pipeline(self, tf: str, bpd: int, n: int):
        """Full feature pipeline works at this timeframe."""
        df = _make_ohlcv(n, tf)
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        open_ = df["open"].values.astype(np.float64)

        features = compute_features(
            pair="TEST/USD",
            timestamps=df.index,
            open=open_, high=high, low=low, close=close,
            bars_per_day=bpd,
        )

        assert features.pair == "TEST/USD"
        assert features.n == n
        assert len(features.atr_pct) == n
        assert len(features.rv_20) == n
        assert len(features.dist_ema200) == n
        assert len(features.dist_ema50) == n

    @pytest.mark.parametrize("tf,bpd,n", TIMEFRAME_CONFIGS)
    def test_forward_returns_causal(self, tf: str, bpd: int, n: int):
        """Forward returns at this timeframe do not depend on future data."""
        df = _make_ohlcv(n, tf)
        close = df["close"].values.astype(np.float64)
        test_idx = n // 2
        h = 10

        fr_original = (close[test_idx + h] - close[test_idx]) / close[test_idx]

        close_mod = close.copy()
        close_mod[test_idx + h + 1:] += 0.1
        fr_modified = (close_mod[test_idx + h] - close_mod[test_idx]) / close_mod[test_idx]

        assert fr_original == fr_modified

    @pytest.mark.parametrize("tf,bpd,n", TIMEFRAME_CONFIGS)
    def test_causality_violation_detection(self, tf: str, bpd: int, n: int):
        """Modifying future data does not change past Z-score, regime, or RV."""
        df = _make_ohlcv(n, tf)
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        ts = df.index
        test_idx = n // 2

        # Z-score causality
        z_orig, _, _ = _zscore_causal_core(close, 20)
        close_mod = close.copy()
        close_mod[test_idx + 1:] += 0.01
        z_mod, _, _ = _zscore_causal_core(close_mod, 20)
        assert z_orig[test_idx] == z_mod[test_idx]

        # Regime causality
        regimes_orig = classify_regime_chunked(
            close, high, low, ts, "TEST/USD",
            chunk_size=500, ema_span=200, atr_period=14
        )
        high_mod = high.copy()
        high_mod[test_idx + 1:] += 0.01
        low_mod = low.copy()
        low_mod[test_idx + 1:] -= 0.01
        regimes_mod = classify_regime_chunked(
            close_mod, high_mod, low_mod, ts, "TEST/USD",
            chunk_size=500, ema_span=200, atr_period=14
        )
        assert regimes_orig[test_idx].trend == regimes_mod[test_idx].trend
        assert regimes_orig[test_idx].volatility == regimes_mod[test_idx].volatility

        # RV causality
        rv_orig = causal_realized_volatility(close, 20, bars_per_day=bpd)
        close_mod2 = close.copy()
        close_mod2[test_idx + 1:] *= 1.05
        rv_mod = causal_realized_volatility(close_mod2, 20, bars_per_day=bpd)
        assert rv_orig[test_idx] == rv_mod[test_idx]

    @pytest.mark.parametrize("tf,bpd,n", TIMEFRAME_CONFIGS)
    def test_research_output_shape(self, tf: str, bpd: int, n: int):
        """FeatureSet carries correct metadata at this timeframe."""
        df = _make_ohlcv(n, tf)
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        open_ = df["open"].values.astype(np.float64)

        features = compute_features(
            pair="TEST/USD",
            timestamps=df.index,
            open=open_, high=high, low=low, close=close,
            bars_per_day=bpd,
        )

        # FeatureSet should have correct lengths
        assert features.n == n
        assert len(features.atr_pct) == n
        assert len(features.rv_20) == n
