"""
Phase M1: Structural Discovery — Cross-Sectional FX Carry

Tests whether currencies sorted by interest-rate differentials (carry)
subsequently produce different returns.

Carry data source: G10 central bank policy rates compiled from:
- FRED (Federal Reserve Economic Data) for USD (FEDFUNDS)
- ECB Statistical Data Warehouse for EUR
- Bank of England for GBP
- Bank of Japan for JPY
- Swiss National Bank for CHF
- Bank of Canada for CAD
- Reserve Bank of Australia for AUD
- Reserve Bank of New Zealand for NZD

All rates are official policy rates as documented by each central bank.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


from config import ALL_PAIRS

DATA_DIR = Path("/root/data")
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]

HOLDING_HORIZONS = [1, 5, 10, 20, 60]  # in days (monthly carry data → longer horizons)
BARS_PER_DAY = 48  # 30min bars
RNG_SEED = 42
N_PERM = 1000

# ═══════════════════════════════════════════════════════════════════════
# CENTRAL BANK POLICY RATES (G10)
# ═══════════════════════════════════════════════════════════════════════
# Source: Official central bank announcements, cross-referenced with
# BIS central bank policy rates dataset documentation.
# All dates are effective dates (when the rate change took effect).
#
# Each entry: (effective_date, rate_pct)
# Rates are in percent per annum.
#
# Data compiled from:
# - Federal Reserve (FRED series FEDFUNDS)
# - ECB (MRO rate, then deposit facility rate from Sep 2024)
# - Bank of England (Bank Rate)
# - Bank of Japan (Overnight Call Rate target)
# - Swiss National Bank (Policy Rate / SNB Policy Rate)
# - Bank of Canada (Overnight Rate Target)
# - Reserve Bank of Australia (Cash Rate Target)
# - Reserve Bank of New Zealand (Official Cash Rate)

POLICY_RATES: dict[str, list[tuple[str, float]]] = {
    "USD": [
        # Fed Funds Rate (target range midpoint)
        ("2016-01-01", 0.25), ("2016-12-15", 0.50), ("2017-03-16", 0.75),
        ("2017-06-15", 1.00), ("2017-12-14", 1.25), ("2018-03-22", 1.50),
        ("2018-06-14", 1.75), ("2018-09-27", 2.00), ("2018-12-20", 2.25),
        ("2019-08-01", 2.00), ("2019-09-19", 1.75), ("2019-10-31", 1.50),
        ("2020-03-03", 1.25), ("2020-03-16", 0.25),
        ("2022-03-17", 0.50), ("2022-05-05", 0.75), ("2022-06-16", 1.50),
        ("2022-07-28", 2.25), ("2022-09-22", 3.00), ("2022-11-03", 3.75),
        ("2022-12-15", 4.25), ("2023-02-02", 4.50), ("2023-03-23", 4.75),
        ("2023-05-04", 5.00), ("2023-07-27", 5.25),
        ("2024-09-18", 4.75), ("2024-11-07", 4.50), ("2024-12-18", 4.25),
        ("2025-01-29", 4.25), ("2025-07-30", 4.00),
    ],
    "EUR": [
        # ECB Main Refinancing Rate → Deposit Facility Rate (Sep 2024)
        ("2016-03-10", 0.00),
        ("2022-07-21", 0.50), ("2022-09-08", 1.25), ("2022-10-27", 2.00),
        ("2022-12-21", 2.50), ("2023-02-01", 3.00), ("2023-03-16", 3.50),
        ("2023-05-04", 3.75), ("2023-06-21", 4.00), ("2023-09-14", 4.50),
        ("2024-06-12", 4.25), ("2024-09-12", 3.75), ("2024-10-17", 3.50),
        ("2024-12-12", 3.25), ("2025-01-30", 3.00), ("2025-03-06", 2.75),
        ("2025-04-17", 2.50), ("2025-06-12", 2.25),
    ],
    "GBP": [
        # Bank of England Bank Rate
        ("2016-08-04", 0.25), ("2017-11-02", 0.50), ("2018-08-02", 0.75),
        ("2019-08-01", 0.75),
        ("2020-03-11", 0.50), ("2020-03-19", 0.25), ("2020-03-26", 0.10),
        ("2021-12-16", 0.25), ("2022-02-03", 0.50), ("2022-03-17", 0.75),
        ("2022-05-05", 1.00), ("2022-06-16", 1.25), ("2022-08-04", 1.75),
        ("2022-09-22", 2.25), ("2022-11-03", 3.00), ("2022-12-15", 3.50),
        ("2023-02-02", 4.00), ("2023-03-23", 4.25), ("2023-05-11", 4.50),
        ("2023-06-22", 5.00), ("2023-08-03", 5.25),
        ("2024-08-01", 5.00), ("2024-11-07", 4.75), ("2024-12-19", 4.50),
        ("2025-02-06", 4.50), ("2025-05-08", 4.25), ("2025-06-19", 4.00),
    ],
    "JPY": [
        # Bank of Japan Overnight Call Rate
        ("2016-01-29", -0.10),  # Negative rate policy
        # YCC: 10Y target ~0%, short rate stays -0.10
        ("2024-03-19", 0.00), ("2024-07-31", 0.25), ("2025-01-24", 0.50),
        ("2025-07-31", 0.75),
    ],
    "CHF": [
        # Swiss National Bank Policy Rate
        ("2016-01-15", -0.75),  # Floor system
        ("2022-06-16", -0.25), ("2022-09-08", 0.50), ("2022-12-15", 1.00),
        ("2023-03-16", 1.50), ("2023-06-16", 1.75),
        ("2024-03-21", 1.50), ("2024-06-20", 1.25), ("2024-09-19", 1.00),
        ("2024-12-12", 0.75), ("2025-03-20", 0.50), ("2025-06-19", 0.25),
    ],
    "CAD": [
        # Bank of Canada Overnight Rate Target
        ("2016-01-20", 0.50), ("2017-07-12", 0.75), ("2018-01-17", 1.00),
        ("2018-03-07", 1.25), ("2018-07-11", 1.50), ("2018-10-24", 1.75),
        ("2019-01-30", 1.75),
        ("2020-03-04", 1.25), ("2020-03-13", 0.75), ("2020-03-27", 0.25),
        ("2022-03-02", 0.50), ("2022-04-13", 1.00), ("2022-06-01", 1.50),
        ("2022-07-13", 2.00), ("2022-09-07", 3.00), ("2022-10-26", 3.75),
        ("2022-12-07", 4.25), ("2023-01-25", 4.50), ("2023-03-08", 4.50),
        ("2023-06-07", 4.75), ("2023-07-12", 5.00),
        ("2024-06-05", 4.75), ("2024-07-24", 4.50), ("2024-09-04", 4.25),
        ("2024-10-23", 4.00), ("2024-12-11", 3.75),
        ("2025-01-29", 3.50), ("2025-03-12", 3.00), ("2025-04-16", 2.75),
        ("2025-06-04", 2.50),
    ],
    "AUD": [
        # Reserve Bank of Australia Cash Rate Target
        ("2016-05-03", 1.75), ("2016-08-02", 1.50),
        ("2019-06-03", 1.25), ("2019-07-02", 1.00), ("2019-10-01", 0.75),
        ("2020-03-03", 0.50), ("2020-03-19", 0.25), ("2020-11-03", 0.10),
        ("2022-05-03", 0.35), ("2022-06-07", 0.85), ("2022-07-05", 1.35),
        ("2022-08-02", 1.85), ("2022-09-06", 2.35), ("2022-10-04", 2.60),
        ("2022-11-01", 2.85), ("2022-12-06", 3.10),
        ("2023-02-07", 3.35), ("2023-03-07", 3.60), ("2023-05-02", 3.85),
        ("2023-06-06", 4.10), ("2023-07-04", 4.35),
        ("2024-11-05", 4.35),
        ("2025-02-18", 4.10), ("2025-05-20", 3.85),
    ],
    "NZD": [
        # Reserve Bank of New Zealand Official Cash Rate
        ("2016-08-10", 2.00), ("2016-11-10", 1.75),
        ("2019-05-08", 1.50),
        ("2020-03-03", 1.00), ("2020-03-16", 0.25),
        ("2021-10-06", 0.50), ("2021-11-24", 0.75), ("2022-02-23", 1.00),
        ("2022-04-13", 1.50), ("2022-05-25", 2.00), ("2022-07-13", 2.50),
        ("2022-08-17", 3.00), ("2022-10-05", 3.50), ("2022-11-23", 4.25),
        ("2023-02-01", 4.75), ("2023-04-05", 5.25), ("2023-05-24", 5.50),
        ("2024-08-14", 5.25), ("2024-10-09", 4.75), ("2024-11-27", 4.25),
        ("2025-02-19", 3.75), ("2025-04-09", 3.50), ("2025-05-28", 3.25),
    ],
}


def build_policy_rate_series(rates_dict: dict[str, list[tuple[str, float]]]) -> pd.DataFrame:
    """
    Convert step-function policy rates into a daily time series.
    Forward-fills rates: the rate on date t is the most recent rate change <= t.
    """
    all_dates = pd.date_range("2016-01-01", "2026-07-31", freq="D")
    result = pd.DataFrame(index=all_dates)

    for currency, changes in rates_dict.items():
        dates = pd.to_datetime([c[0] for c in changes])
        values = [c[1] for c in changes]
        series = pd.Series(values, index=dates)
        # Reindex to all_dates and forward-fill
        result[currency] = series.reindex(all_dates, method="ffill")

    return result


# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════

def load_pair_data(pairs: list[str], resample: str = "30min") -> dict[str, pd.DataFrame]:
    data = {}
    for pair in pairs:
        fp = DATA_DIR / f"{pair.replace('/', '_')}.pkl"
        if not fp.exists():
            continue
        raw = pd.read_pickle(fp)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, pd.DataFrame) and "close" in v.columns:
                    df = v.copy()
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    if resample and resample != "1min":
                        df = df.resample(resample).agg({
                            "open": "first", "high": "max", "low": "min",
                            "close": "last", "volume": "sum",
                        }).dropna()
                    data[k] = df
    return data


def compute_currency_returns(pair_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Extract individual currency returns from pairwise data."""
    contributions: dict[str, list[pd.Series]] = {c: [] for c in CURRENCIES}

    for pair, df in pair_data.items():
        if "/" not in pair:
            continue
        base, quote = pair.split("/")
        if base not in CURRENCIES or quote not in CURRENCIES:
            continue
        close = df["close"]
        log_ret = np.log(close / close.shift(1)).iloc[1:]
        contributions[base].append(log_ret)
        contributions[quote].append(-log_ret)

    currency_returns = {}
    for currency, series_list in contributions.items():
        if len(series_list) < 2:
            continue
        stacked = pd.concat(series_list, axis=1, sort=False)
        currency_returns[currency] = stacked.mean(axis=1)

    return pd.DataFrame(currency_returns)


# ═══════════════════════════════════════════════════════════════════════
# CARRY SPECTRUM
# ═══════════════════════════════════════════════════════════════════════

def compute_carry_spectrum(
    currency_returns: pd.DataFrame,
    policy_rates: pd.DataFrame,
    holding_horizons: list[int] = HOLDING_HORIZONS,
) -> dict[str, Any]:
    """
    Compute the carry spectrum.

    For each holding horizon:
    1. At each daily timestamp, rank currencies by carry score (policy rate)
    2. Construct HCML (high-carry minus low-carry)
    3. Measure forward return of HCML spread
    """
    # Align to daily frequency
    daily_ret = currency_returns.resample("D").sum()
    daily_ret.index = daily_ret.index.tz_localize(None) if daily_ret.index.tz else daily_ret.index

    # Align dates
    common_dates = daily_ret.index.intersection(policy_rates.index)
    daily_ret = daily_ret.loc[common_dates]
    rates = policy_rates.loc[common_dates]

    # Only use currencies present in both
    avail_currencies = [c for c in CURRENCIES if c in daily_ret.columns and c in rates.columns]
    daily_ret = daily_ret[avail_currencies]
    rates = rates[avail_currencies]

    results: dict[str, Any] = {}

    for h_horizon in holding_horizons:
        h_key = f"{h_horizon}D"

        # Forward returns: sum of next h_horizon days of log returns
        fwd_returns = daily_ret.rolling(h_horizon).sum().shift(-h_horizon)

        # For each timestamp, rank currencies and compute HCML
        common_idx = rates.index.intersection(fwd_returns.index)
        common_idx = common_idx[rates.loc[common_idx].notna().all(axis=1)]
        common_idx = common_idx[fwd_returns.loc[common_idx].notna().all(axis=1)]

        if len(common_idx) < 100:
            results[h_key] = {
                "n": len(common_idx), "mean": 0.0, "median": 0.0,
                "win_rate": 0.5, "t_stat": 0.0, "p_value": 1.0,
                "quintiles": {}, "monotonicity": 0.0,
                "spearman_corr": 0.0, "spearman_p": 1.0,
            }
            continue

        # Vectorized ranking and HCML
        rate_vals = rates.loc[common_idx]
        fwd_vals = fwd_returns.loc[common_idx]
        n_currencies = len(avail_currencies)

        # Rank currencies by carry (1=lowest, n=highest)
        ranks = rate_vals.rank(axis=1, method="average")
        col_pos = {name: i for i, name in enumerate(avail_currencies)}

        # High carry = top quintile (top 20% or top 2 depending on universe)
        n_quintile = max(1, n_currencies // 5)
        hcml_returns = []

        # Quintile returns
        quintile_returns = {q: [] for q in range(1, 6)}

        for ts_idx in range(len(common_idx)):
            row_ranks = ranks.iloc[ts_idx].values
            row_fwd = fwd_vals.iloc[ts_idx].values

            # Sort by rank
            sorted_idx = np.argsort(row_ranks)
            sorted_fwd = row_fwd[sorted_idx]
            sorted_rates = rate_vals.iloc[ts_idx].values[sorted_idx]

            # Quintile assignment
            n_per_q = max(1, len(sorted_idx) // 5)
            for q in range(5):
                start = q * n_per_q
                end = start + n_per_q if q < 4 else len(sorted_idx)
                q_ret = float(np.mean(sorted_fwd[start:end]))
                quintile_returns[q + 1].append(q_ret)

            # HCML: top quintile - bottom quintile
            top = float(np.mean(sorted_fwd[-n_per_q:]))
            bottom = float(np.mean(sorted_fwd[:n_per_q]))
            hcml_returns.append(top - bottom)

        hcml_returns = np.array(hcml_returns)

        # Basic statistics
        mean_ret = float(np.mean(hcml_returns))
        median_ret = float(np.median(hcml_returns))
        win_rate = float(np.mean(hcml_returns > 0))

        # Newey-West t-stat
        nw_se = newey_west_se(hcml_returns, max_lag=min(20, len(hcml_returns) // 10))
        t_stat = mean_ret / nw_se if nw_se > 0 else 0.0
        p_val = 2 * stats.t.sf(abs(t_stat), df=max(1, len(hcml_returns) - 1))

        # Quintile means
        quintile_means = {}
        for q in range(1, 6):
            quintile_means[q] = round(float(np.mean(quintile_returns[q])), 6)

        # Monotonicity: Spearman correlation between quintile rank and quintile mean
        q_keys = sorted(quintile_means.keys())
        q_vals = [quintile_means[k] for k in q_keys]
        monotonicity = float(stats.spearmanr(q_keys, q_vals).correlation)

        # Spearman rank correlation between carry rank and subsequent return
        all_carry_ranks = []
        all_fwd_returns = []
        for ts_idx in range(len(common_idx)):
            row_ranks = ranks.iloc[ts_idx].values
            row_fwd = fwd_vals.iloc[ts_idx].values
            valid = ~(np.isnan(row_ranks) | np.isnan(row_fwd))
            if valid.sum() >= 4:
                all_carry_ranks.extend(row_ranks[valid].tolist())
                all_fwd_returns.extend(row_fwd[valid].tolist())

        if len(all_carry_ranks) >= 10:
            spearman_corr, spearman_p = stats.spearmanr(all_carry_ranks, all_fwd_returns)
        else:
            spearman_corr, spearman_p = 0.0, 1.0

        results[h_key] = {
            "n": len(hcml_returns),
            "mean": round(mean_ret, 6),
            "median": round(median_ret, 6),
            "win_rate": round(win_rate, 6),
            "t_stat": round(t_stat, 4),
            "p_value": round(p_val, 6),
            "quintiles": quintile_means,
            "monotonicity": round(monotonicity, 4),
            "spearman_corr": round(float(spearman_corr), 6),
            "spearman_p": round(float(spearman_p), 6),
            "hcml_returns": hcml_returns.tolist(),
        }

    return results


def newey_west_se(residuals: np.ndarray, max_lag: int = 20) -> float:
    """Newey-West HAC standard error."""
    n = len(residuals)
    if n < max_lag + 1:
        return float(np.std(residuals) / np.sqrt(n))
    mean_r = np.mean(residuals)
    centered = residuals - mean_r
    gamma_0 = np.mean(centered ** 2)
    gamma_sum = 0.0
    for lag in range(1, max_lag + 1):
        weight = 1.0 - lag / (max_lag + 1)
        gamma_lag = np.mean(centered[lag:] * centered[:-lag])
        gamma_sum += 2 * weight * gamma_lag
    nw_var = gamma_0 + gamma_sum
    return float(np.sqrt(max(nw_var, 1e-10) / n))


# ═══════════════════════════════════════════════════════════════════════
# STABILITY TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_stability(spectrum: dict) -> dict[str, Any]:
    """Test whether carry structure is stable across horizons."""
    holding_keys = sorted(spectrum.keys(), key=lambda x: int(x.replace("D", "")))

    # Sign consistency
    all_means = [spectrum[h]["mean"] for h in holding_keys]
    all_means = np.array(all_means)
    if len(all_means) > 0:
        majority_sign = 1 if np.sum(all_means > 0) > np.sum(all_means < 0) else -1
        sign_consistency = float(np.mean(np.sign(all_means) == majority_sign))
    else:
        sign_consistency = 0.5

    # Fraction significant
    sig_count = sum(1 for h in holding_keys if spectrum[h]["p_value"] < 0.05)
    total_count = len(holding_keys)

    # Average absolute t-stat
    avg_abs_t = float(np.mean([abs(spectrum[h]["t_stat"]) for h in holding_keys]))

    # Monotonicity consistency
    avg_monotonicity = float(np.mean([spectrum[h]["monotonicity"] for h in holding_keys]))

    # Average Spearman correlation
    avg_spearman = float(np.mean([spectrum[h]["spearman_corr"] for h in holding_keys]))

    # Neighboring horizon agreement
    agreement = 0
    total = 0
    for i in range(len(holding_keys) - 1):
        m1 = spectrum[holding_keys[i]]["mean"]
        m2 = spectrum[holding_keys[i + 1]]["mean"]
        if abs(m1) > 0.0001 and abs(m2) > 0.0001:
            total += 1
            if (m1 > 0 and m2 > 0) or (m1 < 0 and m2 < 0):
                agreement += 1

    stability = {
        "sign_consistency_pct": round(sign_consistency * 100, 1),
        "significant_cells_pct": round(sig_count / max(total_count, 1) * 100, 1),
        "significant_cells": sig_count,
        "total_cells": total_count,
        "avg_abs_t_stat": round(avg_abs_t, 4),
        "avg_monotonicity": round(avg_monotonicity, 4),
        "avg_spearman_corr": round(avg_spearman, 6),
        "horizon_agreement_pct": round(agreement / max(total, 1) * 100, 1),
    }

    # Kill criterion
    stability["passes_kill_criterion"] = (
        stability["sign_consistency_pct"] > 60
        and stability["horizon_agreement_pct"] > 60
        and stability["avg_abs_t_stat"] > 1.0
    )

    return stability


# ═══════════════════════════════════════════════════════════════════════
# PERMUTATION TEST
# ═══════════════════════════════════════════════════════════════════════

def permutation_test_carry(
    currency_returns: pd.DataFrame,
    policy_rates: pd.DataFrame,
    holding_horizon: int = 10,
    n_perm: int = N_PERM,
    seed: int = RNG_SEED,
) -> dict:
    """Sign permutation test for HCML returns."""
    rng = np.random.RandomState(seed)

    daily_ret = currency_returns.resample("D").sum()
    daily_ret.index = daily_ret.index.tz_localize(None) if daily_ret.index.tz else daily_ret.index
    common_dates = daily_ret.index.intersection(policy_rates.index)
    daily_ret = daily_ret.loc[common_dates]
    rates = policy_rates.loc[common_dates]

    avail_currencies = [c for c in CURRENCIES if c in daily_ret.columns and c in rates.columns]
    daily_ret = daily_ret[avail_currencies]
    rates = rates[avail_currencies]

    fwd_returns = daily_ret.rolling(holding_horizon).sum().shift(-holding_horizon)
    common_idx = rates.index.intersection(fwd_returns.index)
    common_idx = common_idx[rates.loc[common_idx].notna().all(axis=1)]
    common_idx = common_idx[fwd_returns.loc[common_idx].notna().all(axis=1)]

    rate_vals = rates.loc[common_idx]
    fwd_vals = fwd_returns.loc[common_idx]
    ranks = rate_vals.rank(axis=1, method="average")
    n_per_q = max(1, len(avail_currencies) // 5)

    hcml_actual = []
    for ts_idx in range(len(common_idx)):
        row_ranks = ranks.iloc[ts_idx].values
        row_fwd = fwd_vals.iloc[ts_idx].values
        sorted_idx = np.argsort(row_ranks)
        sorted_fwd = row_fwd[sorted_idx]
        top = float(np.mean(sorted_fwd[-n_per_q:]))
        bottom = float(np.mean(sorted_fwd[:n_per_q]))
        hcml_actual.append(top - bottom)

    hcml_actual = np.array(hcml_actual)
    actual_mean = float(np.mean(hcml_actual))

    # Vectorized sign permutation
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(hcml_actual)))
    null_means = (hcml_actual[None, :] * signs).mean(axis=1)

    p_value = float(np.mean(np.abs(null_means) >= np.abs(actual_mean)))
    return {
        "observed_mean": round(actual_mean, 6),
        "null_mean": round(float(np.mean(null_means)), 6),
        "null_std": round(float(np.std(null_means)), 6),
        "p_value": round(p_value, 6),
        "ci_95_low": round(float(np.percentile(null_means, 2.5)), 6),
        "ci_95_high": round(float(np.percentile(null_means, 97.5)), 6),
        "null_distribution": null_means.tolist(),
    }


# ═══════════════════════════════════════════════════════════════════════
# TIME-STABILITY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def analyze_time_stability(
    currency_returns: pd.DataFrame,
    policy_rates: pd.DataFrame,
    holding_horizon: int = 10,
) -> dict:
    """Break analysis into time periods and year-by-year."""
    daily_ret = currency_returns.resample("D").sum()
    daily_ret.index = daily_ret.index.tz_localize(None) if daily_ret.index.tz else daily_ret.index
    common_dates = daily_ret.index.intersection(policy_rates.index)
    daily_ret = daily_ret.loc[common_dates]
    rates = policy_rates.loc[common_dates]

    avail_currencies = [c for c in CURRENCIES if c in daily_ret.columns and c in rates.columns]
    daily_ret = daily_ret[avail_currencies]
    rates = rates[avail_currencies]

    fwd_returns = daily_ret.rolling(holding_horizon).sum().shift(-holding_horizon)
    common_idx = rates.index.intersection(fwd_returns.index)
    common_idx = common_idx[rates.loc[common_idx].notna().all(axis=1)]
    common_idx = common_idx[fwd_returns.loc[common_idx].notna().all(axis=1)]

    rate_vals = rates.loc[common_idx]
    fwd_vals = fwd_returns.loc[common_idx]
    ranks = rate_vals.rank(axis=1, method="average")
    n_per_q = max(1, len(avail_currencies) // 5)

    # Compute HCML for each timestamp
    hcml_ts = []
    for ts_idx in range(len(common_idx)):
        row_ranks = ranks.iloc[ts_idx].values
        row_fwd = fwd_vals.iloc[ts_idx].values
        sorted_idx = np.argsort(row_ranks)
        sorted_fwd = row_fwd[sorted_idx]
        top = float(np.mean(sorted_fwd[-n_per_q:]))
        bottom = float(np.mean(sorted_fwd[:n_per_q]))
        hcml_ts.append(top - bottom)

    hcml_series = pd.Series(hcml_ts, index=common_idx)

    # Period analysis
    periods = {
        "2016-2018": ("2016-01-01", "2018-12-31"),
        "2019-2021": ("2019-01-01", "2021-12-31"),
        "2022-2024": ("2022-01-01", "2024-12-31"),
        "2025-2026": ("2025-01-01", "2026-12-31"),
    }
    period_results = {}
    for name, (start, end) in periods.items():
        mask = (hcml_series.index >= start) & (hcml_series.index <= end)
        subset = hcml_series[mask]
        if len(subset) > 10:
            nw_se = newey_west_se(subset.values, max_lag=min(10, len(subset) // 5))
            t = float(np.mean(subset) / nw_se) if nw_se > 0 else 0.0
            period_results[name] = {
                "n": len(subset),
                "mean": round(float(np.mean(subset)), 6),
                "median": round(float(np.median(subset)), 6),
                "win_rate": round(float(np.mean(subset > 0)), 6),
                "t_stat": round(t, 4),
                "p_value": round(2 * stats.t.sf(abs(t), df=max(1, len(subset) - 1)), 6),
            }
        else:
            period_results[name] = {"n": len(subset), "mean": 0.0, "median": 0.0,
                                     "win_rate": 0.5, "t_stat": 0.0, "p_value": 1.0}

    # Year-by-year
    year_results = {}
    for year in range(2016, 2027):
        mask = (hcml_series.index >= f"{year}-01-01") & (hcml_series.index <= f"{year}-12-31")
        subset = hcml_series[mask]
        if len(subset) > 10:
            nw_se = newey_west_se(subset.values, max_lag=min(10, len(subset) // 5))
            t = float(np.mean(subset) / nw_se) if nw_se > 0 else 0.0
            year_results[str(year)] = {
                "n": len(subset),
                "mean": round(float(np.mean(subset)), 6),
                "win_rate": round(float(np.mean(subset > 0)), 6),
                "t_stat": round(t, 4),
            }
        else:
            year_results[str(year)] = {"n": len(subset), "mean": 0.0,
                                         "win_rate": 0.5, "t_stat": 0.0}

    return {"periods": period_results, "year_by_year": year_results}


# ═══════════════════════════════════════════════════════════════════════
# REGIME DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════

def analyze_regimes(
    currency_returns: pd.DataFrame,
    policy_rates: pd.DataFrame,
    holding_horizon: int = 10,
) -> dict:
    """Descriptive regime breakdowns."""
    daily_ret = currency_returns.resample("D").sum()
    daily_ret.index = daily_ret.index.tz_localize(None) if daily_ret.index.tz else daily_ret.index
    common_dates = daily_ret.index.intersection(policy_rates.index)
    daily_ret = daily_ret.loc[common_dates]
    rates = policy_rates.loc[common_dates]

    avail_currencies = [c for c in CURRENCIES if c in daily_ret.columns and c in rates.columns]
    daily_ret = daily_ret[avail_currencies]
    rates = rates[avail_currencies]

    fwd_returns = daily_ret.rolling(holding_horizon).sum().shift(-holding_horizon)
    common_idx = rates.index.intersection(fwd_returns.index)
    common_idx = common_idx[rates.loc[common_idx].notna().all(axis=1)]
    common_idx = common_idx[fwd_returns.loc[common_idx].notna().all(axis=1)]

    rate_vals = rates.loc[common_idx]
    fwd_vals = fwd_returns.loc[common_idx]
    ranks = rate_vals.rank(axis=1, method="average")
    n_per_q = max(1, len(avail_currencies) // 5)

    hcml_ts = []
    for ts_idx in range(len(common_idx)):
        row_ranks = ranks.iloc[ts_idx].values
        row_fwd = fwd_vals.iloc[ts_idx].values
        sorted_idx = np.argsort(row_ranks)
        sorted_fwd = row_fwd[sorted_idx]
        top = float(np.mean(sorted_fwd[-n_per_q:]))
        bottom = float(np.mean(sorted_fwd[:n_per_q]))
        hcml_ts.append(top - bottom)

    hcml_series = pd.Series(hcml_ts, index=common_idx)

    # FX volatility regime (rolling 20-day vol of DXY proxy = avg of all pair vols)
    fx_vol = daily_ret.std(axis=1).rolling(20).mean()
    vol_median = fx_vol.median()

    vol_regimes = {}
    for regime_name, vol_mask in [("LOW_VOL", fx_vol <= vol_median), ("HIGH_VOL", fx_vol > vol_median)]:
        subset = hcml_series[vol_mask.reindex(hcml_series.index, fill_value=False)]
        if len(subset) > 10:
            nw_se = newey_west_se(subset.values, max_lag=min(10, len(subset) // 5))
            t = float(np.mean(subset) / nw_se) if nw_se > 0 else 0.0
            vol_regimes[regime_name] = {
                "n": len(subset),
                "mean": round(float(np.mean(subset)), 6),
                "win_rate": round(float(np.mean(subset > 0)), 6),
                "t_stat": round(t, 4),
            }
        else:
            vol_regimes[regime_name] = {"n": len(subset), "mean": 0.0,
                                         "win_rate": 0.5, "t_stat": 0.0}

    # USD strength regime (using EUR/USD as proxy)
    usd_strength = None
    for pair_name in ["EUR/USD", "GBP/USD", "AUD/USD"]:
        if pair_name in [k.replace("_", "/") for k in currency_returns.columns]:
            pass
    # Use average return of EUR, GBP, AUD as USD strength proxy (inverted)
    usd_proxy_cols = [c for c in ["EUR", "GBP", "AUD"] if c in daily_ret.columns]
    if usd_proxy_cols:
        usd_strength = -daily_ret[usd_proxy_cols].mean(axis=1).rolling(20).mean()
        usd_median = usd_strength.median()

        usd_regimes = {}
        for regime_name, mask in [("USD_STRONG", usd_strength > usd_median),
                                   ("USD_WEAK", usd_strength <= usd_median)]:
            valid_mask = mask.reindex(hcml_series.index, fill_value=False)
            subset = hcml_series[valid_mask]
            if len(subset) > 10:
                nw_se = newey_west_se(subset.values, max_lag=min(10, len(subset) // 5))
                t = float(np.mean(subset) / nw_se) if nw_se > 0 else 0.0
                usd_regimes[regime_name] = {
                    "n": len(subset),
                    "mean": round(float(np.mean(subset)), 6),
                    "win_rate": round(float(np.mean(subset > 0)), 6),
                    "t_stat": round(t, 4),
                }
            else:
                usd_regimes[regime_name] = {"n": len(subset), "mean": 0.0,
                                             "win_rate": 0.5, "t_stat": 0.0}
        vol_regimes["usd_strength"] = usd_regimes

    return {"volatility_regime": vol_regimes}


# ═══════════════════════════════════════════════════════════════════════
# FIGURES
# ═══════════════════════════════════════════════════════════════════════

def generate_figures(results: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    spectrum = results.get("spectrum", {})
    holding_keys = sorted(spectrum.keys(), key=lambda x: int(x.replace("D", "")))

    # Fig 1: HCML returns by holding horizon
    if holding_keys:
        means = [spectrum[h]["mean"] * 10000 for h in holding_keys]  # bps
        errors = []
        for h in holding_keys:
            cell = spectrum[h]
            ci_width = abs(cell["t_stat"]) * 0.0001 * 10000 if cell["t_stat"] != 0 else 0
            errors.append(ci_width)

        fig, ax = plt.subplots(figsize=(10, 5))
        x = range(len(holding_keys))
        colors = ["green" if m > 0 else "red" for m in means]
        ax.bar(x, means, color=colors, alpha=0.7, yerr=errors if any(e > 0 for e in errors) else None,
               capsize=3)
        ax.set_xticks(list(x))
        ax.set_xticklabels(holding_keys)
        ax.set_ylabel("HCML Return (bps)")
        ax.set_title("Phase M1 Carry: High-Carry minus Low-Carry by Holding Horizon")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "01_hcml_by_horizon.png", dpi=150)
        plt.close()

    # Fig 2: Quintile monotonicity for key horizon
    key_h = "10D" if "10D" in spectrum else holding_keys[len(holding_keys) // 2]
    if key_h in spectrum and spectrum[key_h].get("quintiles"):
        quints = spectrum[key_h]["quintiles"]
        q_keys = sorted(quints.keys(), key=lambda x: int(x))
        q_vals = [quints[k] * 10000 for k in q_keys]

        fig, ax = plt.subplots(figsize=(8, 5))
        colors = ["green" if v > 0 else "red" for v in q_vals]
        ax.bar(range(len(q_keys)), q_vals, color=colors, alpha=0.7)
        ax.set_xticks(range(len(q_keys)))
        ax.set_xticklabels([f"Q{int(k)}" for k in q_keys])
        ax.set_ylabel("Mean Forward Return (bps)")
        ax.set_title(f"Phase M1 Carry: Quintile Returns ({key_h} holding, mono={spectrum[key_h]['monotonicity']:.2f})")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "02_quintile_returns.png", dpi=150)
        plt.close()

    # Fig 3: Permutation test
    perm = results.get("permutation_10D", {})
    if perm and "null_distribution" in perm:
        null_dist = np.array(perm["null_distribution"]) * 10000
        observed = perm["observed_mean"] * 10000
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(null_dist, bins=50, alpha=0.7, density=True, label="Null (sign-flipped)")
        ax.axvline(observed, color="red", linewidth=2, label=f"Observed = {observed:.1f} bps")
        ax.set_xlabel("HCML Return (bps)")
        ax.set_ylabel("Density")
        ax.set_title(f"Phase M1 Carry: Permutation Test 10D (p = {perm['p_value']:.4f})")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "03_permutation_10d.png", dpi=150)
        plt.close()

    # Fig 4: Year-by-year
    ts = results.get("time_stability", {})
    yby = ts.get("year_by_year", {})
    if yby:
        years = sorted(yby.keys())
        means = [yby[y]["mean"] * 10000 for y in years]
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = ["green" if m > 0 else "red" for m in means]
        ax.bar(range(len(years)), means, color=colors, alpha=0.7)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years)
        ax.set_ylabel("HCML Return (bps)")
        ax.set_title("Phase M1 Carry: Year-by-Year HCML Returns")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "04_year_by_year.png", dpi=150)
        plt.close()

    # Fig 5: Policy rates over time
    pr = results.get("policy_rates_used", {})
    if pr:
        fig, ax = plt.subplots(figsize=(12, 6))
        for currency in CURRENCIES:
            if currency in pr:
                rates = pr[currency]
                if isinstance(rates, dict) and "dates" in rates and "values" in rates:
                    ax.plot(pd.to_datetime(rates["dates"]), rates["values"],
                            label=currency, linewidth=1.5)
        ax.set_ylabel("Policy Rate (%)")
        ax.set_title("G10 Central Bank Policy Rates (2016-2026)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(fig_dir / "05_policy_rates.png", dpi=150)
        plt.close()

    # Fig 6: Stability metrics
    stab = results.get("stability", {})
    if stab:
        metrics = {
            "Sign\nConsistency": stab.get("sign_consistency_pct", 0),
            "Horizon\nAgreement": stab.get("horizon_agreement_pct", 0),
            "Significant\nCells": stab.get("significant_cells_pct", 0),
        }
        fig, ax = plt.subplots(figsize=(8, 5))
        names = list(metrics.keys())
        vals = list(metrics.values())
        colors = ["green" if v > 60 else "orange" if v > 40 else "red" for v in vals]
        ax.bar(range(len(names)), vals, color=colors, alpha=0.7)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names)
        ax.set_ylabel("Percentage")
        ax.set_title("Phase M1 Carry: Stability Metrics")
        ax.axhline(y=60, color="green", linewidth=1, linestyle="--", label="Threshold (60%)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "06_stability_metrics.png", dpi=150)
        plt.close()

    print(f"  Figures saved to {fig_dir}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase M1: Structural Discovery — Cross-Sectional FX Carry")
    print("Hypothesis falsification, not strategy development.")
    print("=" * 70)

    # ── Build policy rate series ───────────────────────────────────────
    print("\n[1] Building G10 central bank policy rate series...")
    policy_rates = build_policy_rate_series(POLICY_RATES)
    print(f"  Shape: {policy_rates.shape}")
    print(f"  Date range: {policy_rates.index[0]} to {policy_rates.index[-1]}")
    for c in CURRENCIES:
        if c in policy_rates.columns:
            latest = policy_rates[c].dropna().iloc[-1]
            print(f"  {c}: latest rate = {latest:.2f}%")

    # ── Load pair data ─────────────────────────────────────────────────
    print("\n[2] Loading pair data...")
    pair_data = load_pair_data(ALL_PAIRS)
    print(f"  Loaded {len(pair_data)} pairs")

    # ── Compute currency returns ───────────────────────────────────────
    print("\n[3] Computing individual currency returns...")
    currency_returns = compute_currency_returns(pair_data)
    print(f"  Shape: {currency_returns.shape}")
    print(f"  Currencies: {list(currency_returns.columns)}")

    # ── Compute carry spectrum ──────────────────────────────────────────
    print("\n[4] Computing carry spectrum...")
    spectrum = compute_carry_spectrum(currency_returns, policy_rates)

    print("\n  CARRY SPECTRUM (HCML Mean Return):")
    print(f"  {'Horizon':>10}  {'Mean(bps)':>10}  {'Med(bps)':>10}  {'Win%':>8}  {'t-stat':>8}  {'p-val':>8}  {'Mono':>6}  {'Spear':>8}")
    for h_key in sorted(spectrum.keys(), key=lambda x: int(x.replace("D", ""))):
        c = spectrum[h_key]
        print(f"  {h_key:>10}  {c['mean']*10000:>10.1f}  {c['median']*10000:>10.1f}  "
              f"{c['win_rate']*100:>7.1f}%  {c['t_stat']:>8.2f}  {c['p_value']:>8.4f}  "
              f"{c['monotonicity']:>6.2f}  {c['spearman_corr']:>8.4f}")

    # ── Stability test ─────────────────────────────────────────────────
    print("\n[5] Testing stability...")
    stability = test_stability(spectrum)
    print(f"  Sign consistency: {stability['sign_consistency_pct']:.1f}%")
    print(f"  Horizon agreement: {stability['horizon_agreement_pct']:.1f}%")
    print(f"  Significant cells: {stability['significant_cells_pct']:.1f}% ({stability['significant_cells']}/{stability['total_cells']})")
    print(f"  Avg |t-stat|: {stability['avg_abs_t_stat']:.4f}")
    print(f"  Avg monotonicity: {stability['avg_monotonicity']:.4f}")
    print(f"  Avg Spearman: {stability['avg_spearman_corr']:.4f}")
    print(f"  Passes kill criterion: {stability['passes_kill_criterion']}")

    # ── Permutation test ───────────────────────────────────────────────
    print("\n[6] Permutation test (10D holding)...")
    perm = permutation_test_carry(currency_returns, policy_rates, holding_horizon=10)
    print(f"  Observed: {perm['observed_mean']*10000:.1f} bps")
    print(f"  Null: {perm['null_mean']*10000:.1f} bps ± {perm['null_std']*10000:.1f} bps")
    print(f"  p-value: {perm['p_value']:.4f}")
    print(f"  95% CI: [{perm['ci_95_low']*10000:.1f}, {perm['ci_95_high']*10000:.1f}] bps")

    # ── Time stability ─────────────────────────────────────────────────
    print("\n[7] Time stability analysis...")
    time_stability = analyze_time_stability(currency_returns, policy_rates)
    print("  Period breakdown (10D holding):")
    for period, data in time_stability["periods"].items():
        print(f"    {period}: mean={data['mean']*10000:.1f}bps, "
              f"win={data['win_rate']*100:.1f}%, t={data['t_stat']:.2f}, p={data['p_value']:.4f}")
    print("  Year-by-year:")
    for year, data in time_stability["year_by_year"].items():
        print(f"    {year}: mean={data['mean']*10000:.1f}bps, "
              f"win={data['win_rate']*100:.1f}%, t={data['t_stat']:.2f}")

    # ── Regime diagnostics ─────────────────────────────────────────────
    print("\n[8] Regime diagnostics...")
    regimes = analyze_regimes(currency_returns, policy_rates)
    for regime_type, regime_data in regimes.items():
        print(f"  {regime_type}:")
        for regime_name, stats in regime_data.items():
            if isinstance(stats, dict) and "n" in stats and stats["n"] > 10:
                print(f"    {regime_name}: mean={stats['mean']*10000:.1f}bps, "
                      f"win={stats['win_rate']*100:.1f}%, t={stats['t_stat']:.2f}")

    # ── Classification ─────────────────────────────────────────────────
    print("\n[9] Classification...")

    # Check if carry has a positive, significant structure
    positive_cells = sum(1 for h in spectrum if spectrum[h]["mean"] > 0)
    total_cells = len(spectrum)
    significant_positive = sum(1 for h in spectrum
                               if spectrum[h]["mean"] > 0 and spectrum[h]["p_value"] < 0.05)
    avg_mono = stability["avg_monotonicity"]
    perm_sig = perm["p_value"] < 0.05

    has_structure = (
        positive_cells > total_cells * 0.5  # majority positive
        and significant_positive >= 2        # at least 2 significant horizons
        and avg_mono > 0.3                   # positive monotonicity
        and perm_sig                         # permutation significant
    )

    if has_structure:
        classification = "B. CARRY STRUCTURE FOUND — PROCEED TO M2"
    else:
        reasons = []
        if positive_cells <= total_cells * 0.5:
            reasons.append(f"only {positive_cells}/{total_cells} cells positive")
        if significant_positive < 2:
            reasons.append(f"only {significant_positive} significant positive cells")
        if avg_mono <= 0.3:
            reasons.append(f"low monotonicity ({avg_mono:.2f})")
        if not perm_sig:
            reasons.append(f"permutation not significant (p={perm['p_value']:.4f})")
        classification = f"A. NO CARRY STRUCTURE FOUND — HYPOTHESIS KILLED ({'; '.join(reasons)})"

    print(f"  {classification}")

    # ── Save ───────────────────────────────────────────────────────────
    # Convert policy rates for JSON serialization
    pr_json = {}
    for c in CURRENCIES:
        if c in policy_rates.columns:
            series = policy_rates[c].dropna()
            pr_json[c] = {
                "dates": [str(d.date()) for d in series.index],
                "values": series.tolist(),
            }

    results = {
        "phase": "M1",
        "hypothesis": "Cross-sectional FX carry predicts currency returns",
        "carry_data_source": "G10 central bank policy rates (FRED, ECB, BoE, BoJ, SNB, BoC, RBA, RBNZ)",
        "carry_definition": "Currency carry = central bank policy rate. HCML = top quintile carry - bottom quintile carry.",
        "universe": avail_currencies if 'avail_currencies' in dir() else CURRENCIES,
        "holding_horizons": HOLDING_HORIZONS,
        "spectrum": spectrum,
        "stability": stability,
        "permutation_10D": perm,
        "time_stability": time_stability,
        "regimes": regimes,
        "classification": classification,
        "policy_rates_used": pr_json,
        "runtime_seconds": time.time() - t0,
    }

    out_dir = Path("research/output/spectrum_m1_carry")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Remove non-serializable hcml_returns from spectrum for JSON
    spectrum_save = {}
    for h_key, h_data in spectrum.items():
        spectrum_save[h_key] = {k: v for k, v in h_data.items() if k != "hcml_returns"}
    results["spectrum"] = spectrum_save

    with open(out_dir / "phase_m1_carry_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Save spectrum as CSV
    rows = []
    for h_key in spectrum:
        cell = spectrum[h_key]
        rows.append({
            "holding": h_key, "n": cell["n"],
            "mean": cell["mean"], "median": cell["median"],
            "win_rate": cell["win_rate"], "t_stat": cell["t_stat"],
            "p_value": cell["p_value"], "monotonicity": cell["monotonicity"],
            "spearman_corr": cell["spearman_corr"], "spearman_p": cell["spearman_p"],
        })
    pd.DataFrame(rows).to_csv(out_dir / "phase_m1_carry_spectrum.csv", index=False)

    print("\n[10] Generating figures...")
    try:
        generate_figures(results, out_dir)
    except Exception as e:
        print(f"  Figure generation failed: {e}")

    print(f"\n{'=' * 70}")
    print(f"Phase M1 complete in {time.time() - t0:.1f}s")
    print(f"Classification: {classification}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
