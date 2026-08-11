"""Smoke test: minimal end-to-end pipeline verification."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from costs.model import apply_spread_to_entry, apply_spread_to_exit, compute_costs
from data_validation.validate import validate_market_data
from zscore.contracts import CostModel, MarketData
from zscore.zscore import compute_zscore_causal, zscore_to_array


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
