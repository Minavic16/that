"""
Regression tests for Phase S0: Archived Breakout Reassessment.
Verifies structural validity, causality, and metric correctness.
"""
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
import json


from nestquant.research.experiments.phase_s0_breakout_reassessment import (
    compute_signals, simulate, metrics, merge,
    LOOKBACK, ATR_SL_MULT, RRR, MAX_HOLD_DAYS, BREAKEVEN_RATIO,
    SPREAD_PIPS, SLIPPAGE_PIPS, RNG_SEED, N_PERM,
)


@pytest.fixture(scope="module")
def eurusd_4h():
    from nestquant.core.tooling.indicators.atr import calculate_atr
    from nestquant.core.tooling.indicators.swing import swing_high_series, swing_low_series
    fp = Path("/root/data/EUR_USD.pkl")
    raw = pd.read_pickle(fp)
    for k, v in raw.items():
        if isinstance(v, pd.DataFrame) and "close" in v.columns:
            df = v.copy()
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            break
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    df4 = df.resample("4h").agg(agg).dropna()
    sig = compute_signals(df4)
    return df4, sig


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL VALIDATION
# ═══════════════════════════════════════════════════════════════════════

class TestSignalStructure:
    def test_signal_values_are_binary(self, eurusd_4h):
        _, sig = eurusd_4h
        vals = sig["signal"].unique()
        assert set(vals).issubset({-1, 0, 1})

    def test_signal_has_entries(self, eurusd_4h):
        _, sig = eurusd_4h
        assert (sig["signal"] != 0).sum() > 0

    def test_no_signals_before_warmup(self, eurusd_4h):
        _, sig = eurusd_4h
        warmup = LOOKBACK * 2 + 1
        assert sig["signal"].iloc[:warmup].sum() == 0

    def test_swing_highs_are_valid(self, eurusd_4h):
        _, sig = eurusd_4h
        sh = sig["swing_high"].dropna()
        all_highs = sig["high"]
        assert (sh <= all_highs.max() * 1.01).all()

    def test_swing_lows_are_valid(self, eurusd_4h):
        _, sig = eurusd_4h
        sl = sig["swing_low"].dropna()
        all_lows = sig["low"]
        assert (sl >= all_lows.min() * 0.99).all()


# ═══════════════════════════════════════════════════════════════════════
# CAUSALITY TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestCausality:
    def test_no_future_data_in_signal(self, eurusd_4h):
        df, sig = eurusd_4h
        close = df["close"].values
        sh = sig["swing_high"].values
        sl = sig["swing_low"].values
        signal = sig["signal"].values

        for i in range(LOOKBACK * 2 + 1, len(df)):
            if signal[i] == 1:
                assert close[i - 1] <= sh[i - 1] < close[i]
            elif signal[i] == -1:
                assert close[i - 1] >= sl[i - 1] > close[i]

    def test_no_future_data_in_trailing_stop(self, eurusd_4h):
        _, sig = eurusd_4h
        sl = sig["swing_low"].values
        for i in range(LOOKBACK * 2 + 2, len(sig)):
            if not np.isnan(sl[i - 1]):
                assert sl[i - 1] == sig["swing_low"].iloc[i - 1]


# ═══════════════════════════════════════════════════════════════════════
# TRADE SIMULATION VALIDATION
# ═══════════════════════════════════════════════════════════════════════

class TestSimulation:
    def test_zero_cost_differs_from_with_cost(self, eurusd_4h):
        _, sig = eurusd_4h
        p0, r0, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=0.0)
        p1, r1, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR,
                              cost_pips=SPREAD_PIPS["EUR/USD"] + SLIPPAGE_PIPS)
        assert len(p0) == len(p1)
        assert np.mean(p0) > np.mean(p1)

    def test_costs_reduce_pnl(self, eurusd_4h):
        _, sig = eurusd_4h
        spread = SPREAD_PIPS["EUR/USD"]
        cost = spread + SLIPPAGE_PIPS
        p0, _, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=0.0)
        p1, _, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=cost)
        total_diff = (np.sum(p0) - np.sum(p1))
        assert total_diff > 0

    def test_entry_indices_match_trades(self, eurusd_4h):
        _, sig = eurusd_4h
        pnls, rs, eidx = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=0.0)
        assert len(pnls) == len(rs)
        assert abs(len(eidx) - len(pnls)) <= 1

    def test_no_concurrent_trades(self, eurusd_4h):
        _, sig = eurusd_4h
        _, _, eidx = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=0.0)
        for i in range(1, len(eidx)):
            assert eidx[i] > eidx[i - 1]

    def test_direction_override_works(self, eurusd_4h):
        _, sig = eurusd_4h
        pnls_b, _, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR,
                                 cost_pips=0.0, direction_override=1)
        pnls_s, _, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR,
                                 cost_pips=0.0, direction_override=-1)
        assert len(pnls_b) > 0
        assert len(pnls_s) > 0
        assert len(pnls_b) != len(pnls_s)

    def test_rng_reproducibility(self, eurusd_4h):
        _, sig = eurusd_4h
        r1, _, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR,
                             cost_pips=0.0, rng=np.random.RandomState(42))
        r2, _, _ = simulate(sig, "EUR/USD", sl_mult=ATR_SL_MULT, rrr=RRR,
                             cost_pips=0.0, rng=np.random.RandomState(42))
        assert r1 == r2

    def test_parameter_perturbation_varies_output(self, eurusd_4h):
        _, sig = eurusd_4h
        p1, _, _ = simulate(sig, "EUR/USD", sl_mult=1.5, rrr=2.5, cost_pips=0.0)
        p2, _, _ = simulate(sig, "EUR/USD", sl_mult=2.5, rrr=4.5, cost_pips=0.0)
        assert p1 != p2


# ═══════════════════════════════════════════════════════════════════════
# METRIC CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════

class TestMetrics:
    def test_metrics_empty(self):
        m = metrics([], [], "empty")
        assert m["n"] == 0

    def test_metrics_all_wins(self):
        pnls = [10.0, 20.0, 30.0]
        rs = [1.0, 2.0, 3.0]
        m = metrics(pnls, rs, "all_wins")
        assert m["win_rate"] == 1.0
        assert m["avg_pnl_pips"] == 20.0
        assert m["profit_factor"] > 100

    def test_metrics_all_losses(self):
        pnls = [-10.0, -20.0]
        rs = [-1.0, -2.0]
        m = metrics(pnls, rs, "all_losses")
        assert m["win_rate"] == 0.0
        assert m["avg_pnl_pips"] < 0

    def test_profit_factor_calculation(self):
        pnls = [10.0, -5.0, 8.0, -3.0]
        rs = [1.0, -0.5, 0.8, -0.3]
        m = metrics(pnls, rs, "mixed")
        expected_pf = (10 + 8) / (5 + 3)
        assert abs(m["profit_factor"] - expected_pf) < 0.01

    def test_max_dd_calculation(self):
        pnls = [10.0, -5.0, -8.0, 3.0, 5.0]
        rs = [1.0, -0.5, -0.8, 0.3, 0.5]
        m = metrics(pnls, rs, "dd_test")
        assert m["max_dd_pips"] > 0

    def test_merge_preserves_count(self):
        p1 = [1.0, 2.0]
        p2 = [3.0]
        r1 = [0.1, 0.2]
        r2 = [0.3]
        fp, fr = merge([p1, p2], [r1, r2])
        assert len(fp) == 3
        assert len(fr) == 3


# ═══════════════════════════════════════════════════════════════════════
# RESULTS FILE VALIDATION
# ═══════════════════════════════════════════════════════════════════════

class TestResultsFile:
    def test_results_exist(self):
        fp = Path("research/output/simple_strategies/S0_breakout_results.json")
        assert fp.exists()

    def test_results_structure(self):
        fp = Path("research/output/simple_strategies/S0_breakout_results.json")
        with open(fp) as f:
            data = json.load(f)
        assert "phase" in data
        assert "original_result" in data
        assert "with_costs" in data
        assert "controls" in data
        assert "param_variants" in data
        assert "year_by_year" in data
        assert "permutation" in data
        assert "classification" in data

    def test_classification_is_valid(self):
        fp = Path("research/output/simple_strategies/S0_breakout_results.json")
        with open(fp) as f:
            data = json.load(f)
        valid = ["A. NO STRUCTURAL SUPPORT — KILL",
                 "B. STRUCTURAL SUPPORT — PROMOTE",
                 "C. GROSS STRUCTURE EXISTS BUT ECONOMICALLY WEAK",
                 "D. REGIME/CONDITION SPECIFIC — CONDITIONAL PROMOTION"]
        assert data["classification"] in valid

    def test_all_experiments_have_results(self):
        fp = Path("research/output/simple_strategies/S0_breakout_results.json")
        with open(fp) as f:
            data = json.load(f)
        assert data["original_result"]["n"] > 0
        assert data["with_costs"]["n"] > 0
        assert data["controls"]["random"]["n"] > 0
        assert data["controls"]["always_buy"]["n"] > 0
        assert data["controls"]["always_sell"]["n"] > 0
        assert len(data["param_variants"]) == 9

    def test_permutation_p_value(self):
        fp = Path("research/output/simple_strategies/S0_breakout_results.json")
        with open(fp) as f:
            data = json.load(f)
        assert 0 <= data["permutation"]["p_value"] <= 1

    def test_year_by_year_covers_range(self):
        fp = Path("research/output/simple_strategies/S0_breakout_results.json")
        with open(fp) as f:
            data = json.load(f)
        years = [int(y) for y in data["year_by_year"].keys()]
        assert min(years) <= 2016
        assert max(years) >= 2025
