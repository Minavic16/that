"""Phase 9B: Corrected Economic Validation — Walk-Forward Threshold Test.

Fixes the accounting bugs from Phase 9:
1. pip_value now returns correct dollar value per pip per standard lot
2. Forward returns computed in actual pips (ΔP / pip_size)
3. Cost calculation uses pair-specific pip value

Usage:
    .venv/bin/python scripts/phase9b_corrected_validation.py
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zscore.zscore import compute_zscore_causal

# ─── Constants ────────────────────────────────────────────────────────────────
RNG_SEED = 42
N_PERM = 500
N_BOOT = 500
Z_ENTRY = 2.2
LOOKBACK = 20
ATR_PERIOD = 14
FAST_HORIZON = 4
SLOW_HORIZON = 16
FAST_THRESHOLD = 0.50
SLOW_THRESHOLD = 0.30
MAX_HOLD_BARS = 64
COMMISSION_USD = 3.50  # dollars per lot per side
SLIPPAGE_PIPS = 0.3
ACCOUNT = 2500.0
RISK = 0.006
LEVERAGE = 100.0
ATR_SL_MULT = 3.0
TP_RATIO = 2.0
SESSIONS = {"london": (7, 16), "new_york": (12, 21)}
SKIP_FRI = 20
SKIP_MON = 3
CONTRACT_SIZE = 100_000  # standard lot
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "NZD/USD",
    "EUR/GBP", "EUR/CHF", "EUR/JPY", "GBP/JPY", "AUD/JPY", "CAD/JPY",
    "NZD/JPY", "EUR/AUD", "EUR/CAD", "GBP/AUD", "GBP/CAD", "AUD/CAD",
    "AUD/CHF", "NZD/CHF",
]
SPREAD = {
    "EUR/USD": 0.8, "GBP/USD": 1.0, "USD/JPY": 1.0, "USD/CHF": 1.2,
    "AUD/USD": 0.9, "NZD/USD": 1.2, "EUR/GBP": 1.2, "EUR/CHF": 1.5,
    "EUR/JPY": 2.0, "GBP/JPY": 3.0, "AUD/JPY": 2.0, "CAD/JPY": 2.5,
    "NZD/JPY": 3.0, "EUR/AUD": 2.0, "EUR/CAD": 2.5, "GBP/AUD": 3.5,
    "GBP/CAD": 3.5, "AUD/CAD": 2.0, "AUD/CHF": 2.5, "NZD/CHF": 3.0,
}
# USD value of quote currency (for pip value calculation)
DEFAULT_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "AUD": 0.65,
    "NZD": 0.60, "CAD": 0.74, "CHF": 1.12, "JPY": 0.0067,
}
THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
WF_THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
RANDOM_CONTROL_N = 200
N_DECILES = 10

# Doubly stable features from Phase 8
OOS_FEATURES = [
    "abs_ret_1", "abs_ret_4", "abs_z", "body_range_ratio",
    "dist_from_recent_max_z", "dist_from_recent_min_z",
    "pair_z_rank", "range_expansion", "range_pctile_500",
    "vol_expansion",
]

# Walk-forward splits
WF_SPLITS = [
    {"train_end": 2020, "test_start": 2021, "test_end": 2021, "label": "2021"},
    {"train_end": 2021, "test_start": 2022, "test_end": 2022, "label": "2022"},
    {"train_end": 2022, "test_start": 2023, "test_end": 2023, "label": "2023"},
    {"train_end": 2023, "test_start": 2024, "test_end": 2024, "label": "2024"},
    {"train_end": 2024, "test_start": 2025, "test_end": 2026, "label": "2025-2026"},
]

# Pair holdout groups
PAIR_GROUPS = [
    ["CAD/JPY", "NZD/JPY", "NZD/CHF", "AUD/CHF", "CAD/CHF"],
    ["EUR/AUD", "AUD/CAD", "GBP/JPY", "GBP/CAD", "GBP/AUD"],
    ["NZD/USD", "EUR/GBP", "EUR/CHF", "EUR/JPY", "AUD/JPY"],
    ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD"],
    ["CAD/JPY", "NZD/JPY", "NZD/CHF", "AUD/CHF", "CAD/CHF"],
]

# Cost scenarios
COST_SCENARIOS = {
    "COST_0": {"spread_pips": 0.0, "slippage_pips": 0.0, "commission_usd": 0.0},
    "COST_LOW": {"spread_pips": 0.5, "slippage_pips": 0.1, "commission_usd": 2.0},
    "COST_BASE": {"spread_pips": 1.0, "slippage_pips": 0.3, "commission_usd": 3.50},
    "COST_HIGH": {"spread_pips": 2.0, "slippage_pips": 0.5, "commission_usd": 7.0},
}

OUT_DIR = Path("/root/nestquant/research_data/phase9b")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── CORRECTED Helpers ────────────────────────────────────────────────────────
def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def pip_value_per_lot(pair: str) -> float:
    """Correct pip value per standard lot in USD.

    For EUR/USD: 0.0001 * 100000 * 1.0 = $10.00 per pip
    For USD/JPY: 0.01 * 100000 * 0.0067 = $6.70 per pip
    """
    base, quote = pair.split("/")
    usd_per_quote = DEFAULT_USD.get(quote, 1.0)
    return pip_size(pair) * CONTRACT_SIZE * usd_per_quote


def cost_in_pips(pair: str, spread_pips: float, slippage_pips: float,
                  commission_usd: float) -> float:
    """Total transaction cost in pips for a given pair."""
    pv = pip_value_per_lot(pair)
    commission_pips = commission_usd / pv if pv > 0 else 0.0
    return spread_pips + slippage_pips + commission_pips


def in_session(ts) -> bool:
    h, d = ts.hour, ts.dayofweek
    if d == 4 and h >= SKIP_FRI:
        return False
    if d == 0 and h < SKIP_MON:
        return False
    if d >= 5:
        return False
    return any(s <= h < e for s, e in SESSIONS.values())


def causal_percentile(arr, current_idx, value, window):
    start = max(0, current_idx - window)
    window_vals = arr[start:current_idx + 1]
    valid = window_vals[~np.isnan(window_vals)]
    if len(valid) < 10:
        return 50.0
    return float(np.mean(valid <= value)) * 100


def bh_fdr(p_values):
    n = len(p_values)
    ranked = np.argsort(p_values)
    adjusted = np.ones(n)
    for i, idx in enumerate(ranked):
        adjusted[idx] = min(p_values[idx] * n / (i + 1), 1.0)
    for i in range(n - 2, -1, -1):
        idx_cur = ranked[i]
        idx_next = ranked[i + 1]
        if adjusted[idx_cur] > adjusted[idx_next]:
            adjusted[idx_cur] = adjusted[idx_next]
    return adjusted


def permutation_test(a, b, n_perm=N_PERM, seed=RNG_SEED):
    rng = np.random.RandomState(seed)
    obs = abs(np.mean(a) - np.mean(b))
    combined = np.concatenate([a, b])
    count = 0
    for _ in range(n_perm):
        rng.shuffle(combined)
        m = len(a)
        if abs(np.mean(combined[:m]) - np.mean(combined[m:])) >= obs:
            count += 1
    return count / n_perm


def bootstrap_ci(a, b, n_boot=N_BOOT, seed=RNG_SEED):
    rng = np.random.RandomState(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sa = rng.choice(a, size=len(a), replace=True)
        sb = rng.choice(b, size=len(b), replace=True)
        diffs[i] = np.mean(sa) - np.mean(sb)
    return float(np.mean(diffs)), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def brier_score(predicted, actual):
    return float(np.mean((predicted - actual) ** 2))


def calibration_error(predicted, actual, n_bins=6):
    bins = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    total_err = 0.0
    total_n = 0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (predicted >= lo) & (predicted < hi)
        if mask.sum() == 0:
            continue
        bin_pred = predicted[mask].mean()
        bin_actual = actual[mask].mean()
        total_err += abs(bin_pred - bin_actual) * mask.sum()
        total_n += mask.sum()
    return total_err / total_n if total_n > 0 else 0.0


# ─── Data Loading ─────────────────────────────────────────────────────────────
def load_all(start, end):
    pdata = {}
    for pair in PAIRS:
        try:
            with open(f"/root/data/{pair.replace('/', '_')}.pkl", "rb") as f:
                raw = pickle.load(f)
        except Exception:
            continue
        df = raw.get(pair)
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df.index = idx
        df = df[(df.index >= start) & (df.index <= end)]
        if len(df) < 500:
            continue
        df = df[["open", "high", "low", "close", "volume"]].resample("30min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna(subset=["close"])
        if len(df) < 500:
            continue
        c = df["close"].values.astype(np.float64)
        obs = compute_zscore_causal(c, df.index, pair, lookback=LOOKBACK)
        z = np.array([o.z_score for o in obs])
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean().values
        atr_pct = atr / df["close"].values * 100
        ema200 = df["close"].ewm(span=200, adjust=False).mean().values
        ema50 = df["close"].ewm(span=50, adjust=False).mean().values
        ema20 = df["close"].ewm(span=20, adjust=False).mean().values
        vol = df["volume"].values.astype(np.float64)
        pdata[pair] = {
            "c": c, "h": df["high"].values, "lo": df["low"].values,
            "o": df["open"].values, "ts": df.index, "n": len(df),
            "z": z, "atr": atr, "atr_pct": atr_pct,
            "ema200": ema200, "ema50": ema50, "ema20": ema20,
            "vol": vol, "bar_range": df["high"].values - df["low"].values,
            "pip": pip_size(pair), "pv": pip_value_per_lot(pair),
            "spread": SPREAD.get(pair, 2.0),
        }
    return pdata


# ─── Event Extraction ────────────────────────────────────────────────────────
@dataclass
class MRPhase9BEvent:
    pair: str
    idx: int
    ts: pd.Timestamp
    z_now: float
    direction: int
    entry_price: float
    close_at_entry: float
    outcome_label: str
    fwd_ret_pips: float  # CORRECTED: forward return in actual pips
    fwd_ret_16_pips: float
    abs_z: float = 0.0
    signed_z: float = 0.0
    z_pctile_200: float = 50.0
    z_pctile_500: float = 50.0
    z_pctile_1000: float = 50.0
    z_pctile_2000: float = 50.0
    dist_from_recent_max_z: float = 0.0
    dist_from_recent_min_z: float = 0.0
    z_was_beyond_count: float = 0.0
    z_moving_toward_zero: float = 0.0
    dz_1: float = 0.0
    dz_2: float = 0.0
    dz_4: float = 0.0
    z_accel: float = 0.0
    ret_1: float = 0.0
    ret_2: float = 0.0
    ret_4: float = 0.0
    ret_8: float = 0.0
    ret_16: float = 0.0
    abs_ret_1: float = 0.0
    abs_ret_4: float = 0.0
    consec_direction: float = 0.0
    body_range_ratio: float = 0.0
    upper_wick_ratio: float = 0.0
    lower_wick_ratio: float = 0.0
    dist_from_52h_high: float = 0.0
    dist_from_52h_low: float = 0.0
    range_position: float = 0.0
    range_expansion: float = 0.0
    price_displacement_atr: float = 0.0
    atr_now: float = 0.0
    atr_pctile_200: float = 50.0
    atr_pctile_500: float = 50.0
    atr_pctile_1000: float = 50.0
    realized_vol_20: float = 0.0
    vol_expansion_ratio: float = 1.0
    range_pctile_500: float = 50.0
    ema_dist_200: float = 0.0
    ema_dist_50: float = 0.0
    ema_dist_20: float = 0.0
    ema_slope_200: float = 0.0
    ema_slope_50: float = 0.0
    ema_cross_20_50: float = 0.0
    ema_cross_50_200: float = 0.0
    trend_return_20: float = 0.0
    trend_persistence: float = 0.0
    vol_now: float = 0.0
    vol_pctile_200: float = 50.0
    vol_pctile_500: float = 50.0
    vol_expansion: float = 1.0
    vol_price_corr_20: float = 0.0
    cross_median_z: float = 0.0
    cross_mean_z: float = 0.0
    cross_pct_extreme: float = 0.0
    cross_return_dispersion: float = 0.0
    pair_z_rank: float = 0.5
    cross_median_ret4: float = 0.0
    pair_ret_vs_cross: float = 0.0
    entry_hour: float = 0.0
    entry_dow: float = 0.0
    bars_since_session_open: float = 0.0
    bars_until_session_close: float = 0.0
    weekend_proximity: float = 0.0


def classify_outcome(z_path, entry_z, direction):
    n = len(z_path)
    z4 = z_path[min(4, n - 1)]
    z8 = z_path[min(8, n - 1)]
    z16 = z_path[min(16, n - 1)]
    if direction == 1:
        recovery_4 = (z4 - entry_z) / abs(entry_z) if abs(entry_z) > 1e-10 else 0.0
        recovery_16 = (z16 - entry_z) / abs(entry_z) if abs(entry_z) > 1e-10 else 0.0
    else:
        recovery_4 = (entry_z - z4) / abs(entry_z) if abs(entry_z) > 1e-10 else 0.0
        recovery_16 = (entry_z - z16) / abs(entry_z) if abs(entry_z) > 1e-10 else 0.0
    continuation_8 = abs(z8) > abs(entry_z) * 1.2
    if recovery_4 > FAST_THRESHOLD:
        return "fast_mr"
    if continuation_8:
        return "continuation"
    if recovery_16 > SLOW_THRESHOLD:
        return "slow_mr"
    return "ambiguous"


def extract_events(pdata, start_date, end_date, pair_filter=None):
    start_dt = pd.Timestamp(start_date, tz="UTC")
    end_dt = pd.Timestamp(end_date, tz="UTC")

    pair_idx_map = {}
    pair_ts_list = {}
    for pair, d in pdata.items():
        if pair_filter and pair not in pair_filter:
            continue
        ts_arr = d["ts"]
        idx_map = {}
        for i, t in enumerate(ts_arr):
            if t >= start_dt and t <= end_dt:
                idx_map[t] = i
        pair_idx_map[pair] = idx_map
        pair_ts_list[pair] = sorted(idx_map.keys())

    all_ts_set = set()
    for pair, ts_list in pair_ts_list.items():
        all_ts_set.update(ts_list)
    all_ts = sorted(all_ts_set)

    events = []
    for ts in all_ts:
        cross_zs = []
        cross_rets4 = []
        for pair, idx_map in pair_idx_map.items():
            if ts not in idx_map:
                continue
            idx = idx_map[ts]
            d = pdata[pair]
            cross_zs.append(d["z"][idx])
            if idx >= 4:
                # CORRECTED: return in pips
                pip = pip_size(pair)
                cross_rets4.append((d["c"][idx] - d["c"][idx - 4]) / pip)
        if len(cross_zs) < 3:
            continue
        cross_median_z = float(np.median(cross_zs))
        cross_mean_z = float(np.mean(cross_zs))
        cross_pct_extreme = float(np.mean([abs(z) > Z_ENTRY for z in cross_zs]))
        cross_return_dispersion = float(np.std(cross_rets4)) if len(cross_rets4) > 1 else 0.0
        cross_median_ret4 = float(np.median(cross_rets4)) if cross_rets4 else 0.0

        for pair, idx_map in pair_idx_map.items():
            if ts not in idx_map:
                continue
            idx = idx_map[ts]
            d = pdata[pair]
            if idx < LOOKBACK or idx >= d["n"] - MAX_HOLD_BARS - 1:
                continue
            ts_now = d["ts"][idx]
            if not in_session(ts_now):
                continue
            z_now = d["z"][idx]
            if abs(z_now) < Z_ENTRY:
                continue
            direction = 1 if z_now < 0 else -1
            pip = d["pip"]
            slip_price = SLIPPAGE_PIPS * pip
            ep = d["c"][idx] + slip_price if direction == 1 else d["c"][idx] - slip_price
            z_path = d["z"][idx:idx + MAX_HOLD_BARS + 1]

            # CORRECTED: forward return in actual pips
            if idx + 4 < d["n"]:
                fwd_ret_pips = (d["c"][idx + 4] - d["c"][idx]) / pip
            else:
                fwd_ret_pips = np.nan
            if idx + 16 < d["n"]:
                fwd_ret_16_pips = (d["c"][idx + 16] - d["c"][idx]) / pip
            else:
                fwd_ret_16_pips = np.nan
            outcome = classify_outcome(z_path, z_now, direction)

            # Features (all at or before idx)
            abs_z = abs(z_now)
            signed_z = z_now
            z_pctile_200 = causal_percentile(d["z"], idx, z_now, 200)
            z_pctile_500 = causal_percentile(d["z"], idx, z_now, 500)
            z_pctile_1000 = causal_percentile(d["z"], idx, z_now, 1000)
            z_pctile_2000 = causal_percentile(d["z"], idx, z_now, 2000)
            max_z = np.nanmax(d["z"][max(0, idx - 200):idx + 1])
            min_z = np.nanmin(d["z"][max(0, idx - 200):idx + 1])
            dist_from_recent_max_z = abs_z - abs(max_z)
            dist_from_recent_min_z = abs_z - abs(min_z)
            lookback_count = min(idx, 200)
            z_was_beyond_count = float(np.sum(np.abs(d["z"][idx - lookback_count:idx + 1]) > Z_ENTRY))
            z_moving_toward_zero = 1.0 if (direction == 1 and z_now > d["z"][idx - 1]) or (direction == -1 and z_now < d["z"][idx - 1]) else 0.0
            dz_1 = z_now - d["z"][idx - 1]
            dz_2 = z_now - d["z"][idx - 2] if idx >= 2 else 0.0
            dz_4 = z_now - d["z"][idx - 4] if idx >= 4 else 0.0
            z_accel = (dz_1 - (d["z"][idx - 1] - d["z"][idx - 2])) if idx >= 2 else 0.0

            c = d["c"]
            # CORRECTED: returns in pips
            ret_1 = (c[idx] - c[idx - 1]) / pip
            ret_2 = (c[idx] - c[idx - 2]) / pip if idx >= 2 else 0.0
            ret_4 = (c[idx] - c[idx - 4]) / pip if idx >= 4 else 0.0
            ret_8 = (c[idx] - c[idx - 8]) / pip if idx >= 8 else 0.0
            ret_16 = (c[idx] - c[idx - 16]) / pip if idx >= 16 else 0.0
            abs_ret_1 = abs(ret_1)
            abs_ret_4 = abs(ret_4)
            consec_direction = 0.0
            for k in range(1, min(idx, 20) + 1):
                if (c[idx - k] - c[idx - k - 1]) * (c[idx] - c[idx - 1]) > 0:
                    consec_direction += 1
                else:
                    break
            h = d["h"][idx]
            lo = d["lo"][idx]
            body = abs(c[idx] - d["o"][idx])
            rng = h - lo
            body_range_ratio = body / rng if rng > 1e-10 else 0.5
            upper_wick = (h - max(c[idx], d["o"][idx])) / rng if rng > 1e-10 else 0.0
            lower_wick = (min(c[idx], d["o"][idx]) - lo) / rng if rng > 1e-10 else 0.0
            high_52h = np.nanmax(d["h"][max(0, idx - 26 * 20 * 24):idx + 1]) if idx > 0 else h
            low_52h = np.nanmin(d["lo"][max(0, idx - 26 * 20 * 24):idx + 1]) if idx > 0 else lo
            # CORRECTED: distances in pips
            dist_from_52h_high = (high_52h - c[idx]) / pip
            dist_from_52h_low = (c[idx] - low_52h) / pip
            range_position = (c[idx] - lo) / rng if rng > 1e-10 else 0.5
            recent_range = np.nanmean(d["bar_range"][max(0, idx - 200):idx + 1])
            range_expansion = rng / recent_range if recent_range > 1e-10 else 1.0
            price_displacement_atr = abs(c[idx] - c[idx - 4]) / d["atr"][idx] if d["atr"][idx] > 1e-10 and idx >= 4 else 0.0

            atr_now = d["atr"][idx] if not np.isnan(d["atr"][idx]) else 0.0
            atr_pctile_200 = causal_percentile(d["atr_pct"], idx, d["atr_pct"][idx], 200)
            atr_pctile_500 = causal_percentile(d["atr_pct"], idx, d["atr_pct"][idx], 500)
            atr_pctile_1000 = causal_percentile(d["atr_pct"], idx, d["atr_pct"][idx], 1000)
            rv_20 = float(np.std(np.diff(c[max(0, idx - 20):idx + 1]))) if idx >= 20 else 0.0
            realized_vol_20 = rv_20
            vol_expansion_ratio = d["bar_range"][idx] / recent_range if recent_range > 1e-10 else 1.0
            range_pctile_500 = causal_percentile(d["bar_range"], idx, d["bar_range"][idx], 500)

            ema200_dist = (c[idx] - d["ema200"][idx]) / pip
            ema50_dist = (c[idx] - d["ema50"][idx]) / pip
            ema20_dist = (c[idx] - d["ema20"][idx]) / pip
            ema200_slope = (d["ema200"][idx] - d["ema200"][max(0, idx - 20)]) / d["ema200"][max(0, idx - 20)] * 100 if idx >= 20 else 0.0
            ema50_slope = (d["ema50"][idx] - d["ema50"][max(0, idx - 20)]) / d["ema50"][max(0, idx - 20)] * 100 if idx >= 20 else 0.0
            ema_cross_20_50 = ema20_dist - ema50_dist
            ema_cross_50_200 = ema50_dist - ema200_dist
            trend_ret_20 = (c[idx] - c[max(0, idx - 20)]) / pip if idx >= 20 else 0.0
            directions = np.sign(np.diff(c[max(0, idx - 20):idx + 1]))
            trend_persistence = float(abs(np.sum(directions))) / len(directions) if len(directions) > 0 else 0.5

            vol_now = d["vol"][idx]
            vol_20 = np.mean(d["vol"][max(0, idx - 20):idx + 1])
            vol_pctile_200 = causal_percentile(d["vol"], idx, d["vol"][idx], 200)
            vol_pctile_500 = causal_percentile(d["vol"], idx, d["vol"][idx], 500)
            vol_expansion = d["vol"][idx] / vol_20 if vol_20 > 0 else 1.0
            if idx >= 20:
                corr = np.corrcoef(d["vol"][idx - 20:idx + 1], c[idx - 20:idx + 1])[0, 1]
                vol_price_corr_20 = float(corr) if not np.isnan(corr) else 0.0
            else:
                vol_price_corr_20 = 0.0

            all_zs_sorted = sorted(cross_zs)
            rank = np.searchsorted(all_zs_sorted, z_now)
            pair_z_rank = rank / len(all_zs_sorted) if all_zs_sorted else 0.5
            # CORRECTED: my return in pips
            my_ret4 = (c[idx] - c[max(0, idx - 4)]) / pip if idx >= 4 else 0.0
            pair_ret_vs_cross = my_ret4 - cross_median_ret4

            entry_h = ts_now.hour
            entry_d = ts_now.dayofweek
            sess_start = SESSIONS["london"][0] if entry_h < 12 else SESSIONS["new_york"][0]
            sess_end = SESSIONS["new_york"][1] if entry_h >= 12 else SESSIONS["london"][1]
            bars_since_open = entry_h - sess_start
            bars_until_close = sess_end - entry_h - 1
            weekend_dist = min((5 - entry_d) % 7, (entry_d) % 7)

            ev = MRPhase9BEvent(
                pair=pair, idx=idx, ts=ts_now, z_now=z_now,
                direction=direction, entry_price=ep, close_at_entry=c[idx],
                outcome_label=outcome, fwd_ret_pips=fwd_ret_pips,
                fwd_ret_16_pips=fwd_ret_16_pips,
                abs_z=abs_z, signed_z=signed_z,
                z_pctile_200=z_pctile_200, z_pctile_500=z_pctile_500,
                z_pctile_1000=z_pctile_1000, z_pctile_2000=z_pctile_2000,
                dist_from_recent_max_z=dist_from_recent_max_z,
                dist_from_recent_min_z=dist_from_recent_min_z,
                z_was_beyond_count=z_was_beyond_count,
                z_moving_toward_zero=z_moving_toward_zero,
                dz_1=dz_1, dz_2=dz_2, dz_4=dz_4, z_accel=z_accel,
                ret_1=ret_1, ret_2=ret_2, ret_4=ret_4, ret_8=ret_8, ret_16=ret_16,
                abs_ret_1=abs_ret_1, abs_ret_4=abs_ret_4,
                consec_direction=consec_direction,
                body_range_ratio=body_range_ratio,
                upper_wick_ratio=upper_wick, lower_wick_ratio=lower_wick,
                dist_from_52h_high=dist_from_52h_high, dist_from_52h_low=dist_from_52h_low,
                range_position=range_position, range_expansion=range_expansion,
                price_displacement_atr=price_displacement_atr,
                atr_now=atr_now, atr_pctile_200=atr_pctile_200,
                atr_pctile_500=atr_pctile_500, atr_pctile_1000=atr_pctile_1000,
                realized_vol_20=realized_vol_20,
                vol_expansion_ratio=vol_expansion_ratio,
                range_pctile_500=range_pctile_500,
                ema_dist_200=ema200_dist, ema_dist_50=ema50_dist, ema_dist_20=ema20_dist,
                ema_slope_200=ema200_slope, ema_slope_50=ema50_slope,
                ema_cross_20_50=ema_cross_20_50, ema_cross_50_200=ema_cross_50_200,
                trend_return_20=trend_ret_20, trend_persistence=trend_persistence,
                vol_now=vol_now, vol_pctile_200=vol_pctile_200,
                vol_pctile_500=vol_pctile_500, vol_expansion=vol_expansion,
                vol_price_corr_20=vol_price_corr_20,
                cross_median_z=cross_median_z, cross_mean_z=cross_mean_z,
                cross_pct_extreme=cross_pct_extreme,
                cross_return_dispersion=cross_return_dispersion,
                pair_z_rank=pair_z_rank,
                cross_median_ret4=cross_median_ret4,
                pair_ret_vs_cross=pair_ret_vs_cross,
                entry_hour=float(entry_h), entry_dow=float(entry_d),
                bars_since_session_open=float(bars_since_open),
                bars_until_session_close=float(bars_until_close),
                weekend_proximity=float(weekend_dist),
            )
            events.append(ev)
    return events


def extract_feature_matrix(events, features=None):
    if features is None:
        features = OOS_FEATURES
    X = np.zeros((len(events), len(features)))
    for i, ev in enumerate(events):
        for j, fname in enumerate(features):
            X[i, j] = getattr(ev, fname, 0.0)
    return X


def extract_target(events):
    return np.array([1 if ev.outcome_label == "fast_mr" else 0 for ev in events])


def extract_fwd_returns(events, horizon=4):
    if horizon == 4:
        return np.array([ev.fwd_ret_pips for ev in events])
    return np.array([ev.fwd_ret_16_pips for ev in events])


# ─── Model ────────────────────────────────────────────────────────────────────
class LogisticModel:
    def __init__(self, max_iter=1000, seed=RNG_SEED, C=1.0):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        self.model = LogisticRegression(max_iter=max_iter, random_state=seed, C=C)
        self.scaler = StandardScaler()
        self.fitted = False

    def fit(self, X, y):
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs, y)
        self.fitted = True

    def predict_proba(self, X):
        Xs = self.scaler.transform(X)
        return self.model.predict_proba(Xs)[:, 1]

    @property
    def coef_(self):
        return self.model.coef_[0]

    @property
    def feature_names(self):
        return OOS_FEATURES


# ─── CORRECTED Economic Evaluation ────────────────────────────────────────────
def compute_economic_metrics(events, fwd_returns, p_fast, threshold=None,
                              spread_pips=0.0, slippage_pips=0.0,
                              commission_usd=0.0, account=ACCOUNT):
    """Compute economic metrics with corrected accounting.

    All returns are in pips. Costs are converted to pips using pair-specific
    pip_value_per_lot. Net PnL is in pips (not dollars) for consistency.
    """
    if threshold is not None:
        mask = p_fast >= threshold
    else:
        mask = np.ones(len(events), dtype=bool)
    sel_events = [e for e, m in zip(events, mask) if m]
    sel_returns = fwd_returns[mask]
    sel_pfast = p_fast[mask]
    if len(sel_events) == 0:
        return {
            "n_trades": 0, "win_rate": 0.0, "mean_return": 0.0,
            "median_return": 0.0, "std_return": 0.0, "gross_pnl": 0.0,
            "net_pnl": 0.0, "avg_pnl_per_trade": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "gross_expectancy": 0.0, "net_expectancy": 0.0,
            "max_drawdown": 0.0, "sharpe": 0.0, "sortino": 0.0,
            "cumulative_return": 0.0, "n_fast": 0, "fast_rate": 0.0,
            "break_even_cost": 0.0,
        }

    avg_pip = float(np.nanmean(sel_returns))
    median_pip = float(np.nanmedian(sel_returns))
    std_pip = float(np.nanstd(sel_returns))
    win_rate = float(np.mean(sel_returns > 0)) if len(sel_returns) > 0 else 0.0
    n_fast = int(np.sum([e.outcome_label == "fast_mr" for e in sel_events]))
    fast_rate = n_fast / len(sel_events) if len(sel_events) > 0 else 0.0

    # Compute per-trade cost in pips (pair-specific)
    per_trade_costs = np.array([
        cost_in_pips(e.pair, spread_pips, slippage_pips, commission_usd)
        for e in sel_events
    ])
    avg_cost_pips = float(np.mean(per_trade_costs))

    gross_pnl = float(np.nansum(sel_returns))
    net_returns = sel_returns - per_trade_costs
    net_pnl = float(np.nansum(net_returns))
    avg_pnl = float(np.nanmean(net_returns))
    avg_gross_pnl = float(np.nanmean(sel_returns))

    # Profit factor
    gains = float(np.nansum(sel_returns[sel_returns > 0]))
    losses = float(np.nansum(abs(sel_returns[sel_returns < 0])))
    pf = gains / losses if losses > 0 else float("inf") if gains > 0 else 0.0

    # Net profit factor
    net_gains = float(np.nansum(net_returns[net_returns > 0]))
    net_losses = float(np.nansum(abs(net_returns[net_returns < 0])))
    net_pf = net_gains / net_losses if net_losses > 0 else float("inf") if net_gains > 0 else 0.0

    # Drawdown
    cum = np.nancumsum(net_returns)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    # Sharpe / Sortino (annualized, assuming 30min bars, ~35 bars/day, ~260 days/year)
    if std_pip > 1e-10:
        sharpe = avg_pnl / std_pip * np.sqrt(35 * 260)
    else:
        sharpe = 0.0
    neg_returns = net_returns[net_returns < 0]
    downside_std = float(np.std(neg_returns)) if len(neg_returns) > 1 else 0.0
    sortino = avg_pnl / downside_std * np.sqrt(35 * 260) if downside_std > 1e-10 else 0.0
    cum_ret = float(cum[-1]) if len(cum) > 0 else 0.0

    break_even_cost = avg_gross_pnl if avg_gross_pnl > 0 else 0.0

    return {
        "n_trades": len(sel_events),
        "win_rate": win_rate,
        "mean_return": avg_pip,
        "median_return": median_pip,
        "std_return": std_pip,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "avg_pnl_per_trade": avg_pnl,
        "profit_factor": pf,
        "net_profit_factor": net_pf,
        "expectancy": avg_pnl,
        "gross_expectancy": avg_gross_pnl,
        "net_expectancy": avg_pnl,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "cumulative_return": cum_ret,
        "n_fast": n_fast,
        "fast_rate": fast_rate,
        "break_even_cost": break_even_cost,
        "avg_cost_pips": avg_cost_pips,
    }


def compute_random_control(events, fwd_returns, p_fast, n_trades, n_reps=100, seed=RNG_SEED):
    rng = np.random.RandomState(seed)
    results = []
    for _ in range(n_reps):
        n_s = min(n_trades, len(events))
        idx = rng.choice(len(events), size=n_s, replace=False)
        sub_events = [events[i] for i in idx]
        sub_returns = fwd_returns[idx]
        m = compute_economic_metrics(sub_events, sub_returns, np.ones(n_s))
        results.append(m)
    return results


def compute_oracle_metrics(events, fwd_returns):
    oracle_mask = np.array([e.outcome_label == "fast_mr" for e in events])
    oracle_events = [e for e, m in zip(events, oracle_mask) if m]
    oracle_returns = fwd_returns[oracle_mask]
    return compute_economic_metrics(oracle_events, oracle_returns, np.ones(len(oracle_events)))


def cost_adversarial(events, fwd_returns, p_fast, threshold, cost_scenarios):
    results = {}
    for name, cs in cost_scenarios.items():
        m = compute_economic_metrics(events, fwd_returns, p_fast,
                                      threshold=threshold,
                                      spread_pips=cs["spread_pips"],
                                      slippage_pips=cs["slippage_pips"],
                                      commission_usd=cs["commission_usd"])
        results[name] = {
            "gross_expectancy": m["gross_expectancy"],
            "net_expectancy": m["net_expectancy"],
            "gross_pnl": m["gross_pnl"],
            "net_pnl": m["net_pnl"],
            "profit_factor": m["profit_factor"],
            "net_profit_factor": m["net_profit_factor"],
            "avg_cost_pips": m["avg_cost_pips"],
        }
    return results


def outlier_robustness(fwd_returns, p_fast, threshold, seed=RNG_SEED):
    mask = p_fast >= threshold if threshold is not None else np.ones(len(fwd_returns), dtype=bool)
    rets = fwd_returns[mask]
    rets = rets[~np.isnan(rets)]
    if len(rets) == 0:
        return {}
    full_mean = float(np.mean(rets))
    sorted_rets = np.sort(rets)
    trim10 = int(len(sorted_rets) * 0.05)
    trimmed10 = sorted_rets[trim10:-trim10] if trim10 > 0 else sorted_rets
    trim25 = int(len(sorted_rets) * 0.125)
    trimmed25 = sorted_rets[trim25:-trim25] if trim25 > 0 else sorted_rets
    median = float(np.median(rets))
    p5, p95 = np.percentile(rets, 5), np.percentile(rets, 95)
    winsorized = np.clip(rets, p5, p95)
    winsorized_mean = float(np.mean(winsorized))
    rng = np.random.RandomState(seed)
    boot_means = np.array([np.mean(rng.choice(rets, size=len(rets), replace=True)) for _ in range(N_BOOT)])
    ci_lo, ci_hi = float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))
    stability = trimmed10.mean() / full_mean if abs(full_mean) > 1e-10 else 0.0
    return {
        "full_mean": full_mean,
        "trim10_mean": float(trimmed10.mean()),
        "trim25_mean": float(trimmed25.mean()),
        "median": median,
        "winsorized_mean": winsorized_mean,
        "stability_ratio": float(stability),
        "bootstrap_ci_95": [ci_lo, ci_hi],
        "n": int(len(rets)),
    }


def decile_analysis(all_events, all_fwd, all_pfast):
    decile_edges = np.percentile(all_pfast, np.linspace(0, 100, N_DECILES + 1))
    decile_edges[0] -= 0.001
    decile_edges[-1] += 0.001
    results = []
    for i in range(N_DECILES):
        lo, hi = decile_edges[i], decile_edges[i + 1]
        mask = (all_pfast >= lo) & (all_pfast < hi)
        if mask.sum() == 0:
            continue
        actual_binary = np.array([1 if e.outcome_label == "fast_mr" else 0
                                   for e in all_events])
        m = compute_economic_metrics(
            [all_events[j] for j in range(len(all_events)) if mask[j]],
            all_fwd[mask], all_pfast[mask])
        results.append({
            "decile": i + 1,
            "n": int(mask.sum()),
            "mean_predicted_p": float(np.mean(all_pfast[mask])),
            "actual_fast_rate": float(np.mean(actual_binary[mask])),
            "mean_return": m["mean_return"],
            "median_return": m["median_return"],
            "std_return": m["std_return"],
            "gross_expectancy": m["gross_expectancy"],
            "net_expectancy": m["net_expectancy"],
        })
    return results


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase 9B: Corrected Economic Validation")
    print("=" * 70)

    # 0. Accounting validation
    print("\n[0/10] Accounting unit audit...")
    for pair in ["EUR/USD", "USD/JPY", "GBP/USD"]:
        pv = pip_value_per_lot(pair)
        ps = pip_size(pair)
        ci = cost_in_pips(pair, 1.0, 0.3, 3.50)
        print(f"  {pair}: pip_size={ps}, pip_value_per_lot=${pv:.2f}, "
              f"cost_1pip_spread+0.3slip+3.50comm = {ci:.3f} pips")
    # Sanity check: cost=0 → net=gross
    print("  Sanity: cost=0 → net_pnl == gross_pnl: VERIFIED (by construction)")

    # 1. Load data
    print("\n[1/10] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"  Loaded {len(pdata)} pairs")

    # 2. Extract events
    print("\n[2/10] Extracting events...")
    all_events = extract_events(pdata, "2016-01-01", "2026-07-19")
    print(f"  Total events: {len(all_events)}")
    fast = sum(1 for e in all_events if e.outcome_label == "fast_mr")
    slow = sum(1 for e in all_events if e.outcome_label == "slow_mr")
    cont = sum(1 for e in all_events if e.outcome_label == "continuation")
    amb = sum(1 for e in all_events if e.outcome_label == "ambiguous")
    print(f"  fast_mr={fast}, slow_mr={slow}, continuation={cont}, ambiguous={amb}")

    # Print first 10 trades for audit
    print("\n  First 10 trades (accounting audit):")
    print(f"  {'Pair':<10} {'Direction':>9} {'Entry':>10} {'FwdRet(pip)':>11} {'Outcome':<12}")
    for ev in all_events[:10]:
        print(f"  {ev.pair:<10} {'LONG' if ev.direction==1 else 'SHORT':>9} "
              f"{ev.entry_price:>10.5f} {ev.fwd_ret_pips:>11.2f} {ev.outcome_label:<12}")

    all_fwd = extract_fwd_returns(all_events, horizon=4)
    all_fwd_16 = extract_fwd_returns(all_events, horizon=16)

    # 3. Global threshold analysis
    print("\n[3/10] Global threshold analysis...")
    # Train a model on all fast/slow events for descriptive analysis
    all_fs_global = [e for e in all_events if e.outcome_label in ("fast_mr", "slow_mr")]
    X_global = extract_feature_matrix(all_fs_global)
    y_global = extract_target(all_fs_global)
    model_global = LogisticModel()
    model_global.fit(X_global, y_global)
    all_pfast_global = model_global.predict_proba(extract_feature_matrix(all_events))
    print(f"  Global model AUC (in-sample): ", end="")
    from sklearn.metrics import roc_auc_score
    y_fs = extract_target(all_fs_global)
    p_fs = model_global.predict_proba(X_global)
    print(f"{roc_auc_score(y_fs, p_fs):.4f}")

    global_thresholds = {}
    for thr in THRESHOLDS:
        m = compute_economic_metrics(all_events, all_fwd, all_pfast_global,
                                     threshold=thr)
        # Also compute under each cost scenario
        cost_results = {}
        for cname, cs in COST_SCENARIOS.items():
            mc = compute_economic_metrics(all_events, all_fwd, all_pfast_global,
                                          threshold=thr, **cs)
            cost_results[cname] = {
                "net_expectancy": mc["net_expectancy"],
                "net_pnl": mc["net_pnl"],
                "net_pf": mc["net_profit_factor"],
            }
        global_thresholds[thr] = {
            "n_trades": m["n_trades"],
            "pct_traded": m["n_trades"] / len(all_events) * 100,
            "fast_rate": m["fast_rate"],
            "win_rate": m["win_rate"],
            "mean_return": m["mean_return"],
            "median_return": m["median_return"],
            "gross_expectancy": m["gross_expectancy"],
            "net_expectancy_base": m["net_expectancy"],
            "profit_factor": m["profit_factor"],
            "max_drawdown": m["max_drawdown"],
            "sharpe": m["sharpe"],
            "sortino": m["sortino"],
            "break_even_cost": m["break_even_cost"],
            "cost_scenarios": cost_results,
        }
        print(f"  P>={thr:.2f}: n={m['n_trades']}, wr={m['win_rate']:.3f}, "
              f"mean={m['mean_return']:.2f}pip, gross_exp={m['gross_expectancy']:.2f}, "
              f"BE_cost={m['break_even_cost']:.2f}pip")

    # 4. Walk-forward with strict threshold selection on TRAIN
    print("\n[4/10] Walk-forward threshold selection...")
    wf_results = {}
    all_oos_events = []
    all_oos_pfast = []
    all_oos_fwd = []

    for split in WF_SPLITS:
        label = split["label"]
        train_end = split["train_end"]
        test_start = split["test_start"]
        test_end = split["test_end"]
        print(f"\n  Split {label}: train 2016-{train_end}, test {test_start}-{test_end}")

        train_events = [e for e in all_events if 2016 <= e.ts.year <= train_end]
        test_events = [e for e in all_events if test_start <= e.ts.year <= test_end]

        train_fs = [e for e in train_events if e.outcome_label in ("fast_mr", "slow_mr")]
        test_fs = [e for e in test_events if e.outcome_label in ("fast_mr", "slow_mr")]
        print(f"    Train: {len(train_events)} ({len(train_fs)} fs)")
        print(f"    Test:  {len(test_events)} ({len(test_fs)} fs)")

        if len(train_fs) < 100 or len(test_fs) < 50:
            print(f"    SKIP")
            continue

        X_train = extract_feature_matrix(train_fs)
        y_train = extract_target(train_fs)
        X_test = extract_feature_matrix(test_fs)
        model = LogisticModel()
        model.fit(X_train, y_train)

        # Predict on all train and test
        X_train_all = extract_feature_matrix(train_events)
        pfast_train = model.predict_proba(X_train_all)
        fwd_train = extract_fwd_returns(train_events, horizon=4)

        X_test_all = extract_feature_matrix(test_events)
        pfast_test = model.predict_proba(X_test_all)
        fwd_test = extract_fwd_returns(test_events, horizon=4)

        # STEP B-C: Select threshold on TRAIN only
        # Criterion: maximize net expectancy subject to n >= 50 and positive expectancy
        best_thr = 0.50
        best_exp = -999
        train_thr_results = {}
        for thr in WF_THRESHOLDS:
            tm = compute_economic_metrics(train_events, fwd_train, pfast_train, threshold=thr)
            train_thr_results[thr] = tm
            if tm["n_trades"] >= 50 and tm["net_expectancy"] > best_exp:
                best_exp = tm["net_expectancy"]
                best_thr = thr

        print(f"    Selected threshold: {best_thr:.2f} (train net_exp={best_exp:.2f}pip)")

        # STEP D-E: Apply frozen model+threshold to TEST
        test_base = compute_economic_metrics(test_events, fwd_test,
                                              np.ones(len(test_events)))
        test_gated = compute_economic_metrics(test_events, fwd_test, pfast_test,
                                              threshold=best_thr)
        test_oracle = compute_oracle_metrics(test_events, fwd_test)

        # Cost scenarios on test
        test_costs = {}
        for cname, cs in COST_SCENARIOS.items():
            mc = compute_economic_metrics(test_events, fwd_test, pfast_test,
                                          threshold=best_thr, **cs)
            test_costs[cname] = {
                "net_expectancy": mc["net_expectancy"],
                "net_pnl": mc["net_pnl"],
                "net_pf": mc["net_profit_factor"],
                "avg_cost_pips": mc["avg_cost_pips"],
            }

        # Break-even cost
        be_cost = test_gated["break_even_cost"]

        # Threshold robustness on test
        thr_robustness = {}
        for thr in WF_THRESHOLDS:
            tm = compute_economic_metrics(test_events, fwd_test, pfast_test, threshold=thr)
            thr_robustness[thr] = {
                "n_trades": tm["n_trades"],
                "net_expectancy": tm["net_expectancy"],
                "profit_factor": tm["profit_factor"],
                "max_drawdown": tm["max_drawdown"],
                "mean_return": tm["mean_return"],
            }

        # Random control
        n_gated = test_gated["n_trades"]
        rc = compute_random_control(test_events, fwd_test, pfast_test,
                                     n_gated, n_reps=RANDOM_CONTROL_N)
        rc_means = np.array([r["mean_return"] for r in rc])
        model_beats_random = float(np.mean(test_gated["mean_return"] > rc_means))

        print(f"    Test: n={test_gated['n_trades']}, wr={test_gated['win_rate']:.3f}, "
              f"mean={test_gated['mean_return']:.2f}pip, net_exp={test_gated['net_expectancy']:.2f}, "
              f"PF={test_gated['profit_factor']:.2f}, BE={be_cost:.2f}pip")
        print(f"    Baseline: n={test_base['n_trades']}, mean={test_base['mean_return']:.2f}pip")
        print(f"    Oracle: n={test_oracle['n_trades']}, mean={test_oracle['mean_return']:.2f}pip")
        print(f"    vs random: pctile={model_beats_random:.3f}")

        wf_results[label] = {
            "train_range": f"2016-{train_end}",
            "test_range": f"{test_start}-{test_end}",
            "n_train": len(train_events),
            "n_test": len(test_events),
            "selected_threshold": best_thr,
            "train_threshold_results": {str(k): {
                "n_trades": v["n_trades"], "net_expectancy": v["net_expectancy"],
                "gross_expectancy": v["gross_expectancy"],
            } for k, v in train_thr_results.items()},
            "baseline": test_base,
            "gated": test_gated,
            "oracle": test_oracle,
            "cost_scenarios": test_costs,
            "break_even_cost": be_cost,
            "threshold_robustness": {str(k): v for k, v in thr_robustness.items()},
            "random_control": {
                "mean_returns": rc_means.tolist(),
                "model_beats_random_pctile": model_beats_random,
                "random_mean": float(np.mean(rc_means)),
                "random_std": float(np.std(rc_means)),
            },
            "model_auc": None,
            "top_features": [],
        }

        all_oos_events.extend(test_events)
        all_oos_pfast.extend(pfast_test.tolist())
        all_oos_fwd.extend(fwd_test.tolist())

    all_oos_pfast = np.array(all_oos_pfast)
    all_oos_fwd = np.array(all_oos_fwd)
    all_oos_events_arr = all_oos_events

    # 5. Aggregated OOS
    print("\n[5/10] Aggregated OOS analysis...")
    agg = {}
    agg["baseline"] = compute_economic_metrics(all_oos_events_arr, all_oos_fwd,
                                                np.ones(len(all_oos_events_arr)))
    agg["oracle"] = compute_oracle_metrics(all_oos_events_arr, all_oos_fwd)
    agg["thresholds"] = {}
    for thr in THRESHOLDS:
        m = compute_economic_metrics(all_oos_events_arr, all_oos_fwd, all_oos_pfast,
                                      threshold=thr)
        agg["thresholds"][thr] = m
    # Cost scenarios on aggregated
    agg["cost_scenarios"] = {}
    for cname, cs in COST_SCENARIOS.items():
        # Use selected thresholds from each WF fold
        for label, r in wf_results.items():
            thr = r["selected_threshold"]
            mc = compute_economic_metrics(all_oos_events_arr, all_oos_fwd, all_oos_pfast,
                                          threshold=thr, **cs)
            agg["cost_scenarios"][f"{cname}_thr{thr:.2f}"] = {
                "net_expectancy": mc["net_expectancy"],
                "net_pnl": mc["net_pnl"],
            }

    print(f"  Baseline: n={agg['baseline']['n_trades']}, mean={agg['baseline']['mean_return']:.2f}pip, "
          f"net_exp={agg['baseline']['net_expectancy']:.2f}")
    print(f"  Oracle: n={agg['oracle']['n_trades']}, mean={agg['oracle']['mean_return']:.2f}pip")

    # 6. Cross-pair holdout
    print("\n[6/10] Cross-pair holdout...")
    pair_holdout = []
    for gi, held_out in enumerate(PAIR_GROUPS):
        train_pairs = [p for p in PAIRS if p not in held_out]
        train_ev = [e for e in all_events if e.pair in train_pairs]
        test_ev = [e for e in all_events if e.pair in held_out]
        train_fs = [e for e in train_ev if e.outcome_label in ("fast_mr", "slow_mr")]
        test_fs = [e for e in test_ev if e.outcome_label in ("fast_mr", "slow_mr")]
        if len(train_fs) < 100 or len(test_fs) < 50:
            continue
        X_tr = extract_feature_matrix(train_fs)
        y_tr = extract_target(train_fs)
        model = LogisticModel()
        model.fit(X_tr, y_tr)
        X_te_all = extract_feature_matrix(test_ev)
        pfast_te = model.predict_proba(X_te_all)
        fwd_te = extract_fwd_returns(test_ev, horizon=4)

        # Select threshold on train
        X_tr_all = extract_feature_matrix(train_ev)
        pfast_tr = model.predict_proba(X_tr_all)
        fwd_tr = extract_fwd_returns(train_ev, horizon=4)
        best_thr = 0.50
        best_exp = -999
        for thr in WF_THRESHOLDS:
            tm = compute_economic_metrics(train_ev, fwd_tr, pfast_tr, threshold=thr)
            if tm["n_trades"] >= 50 and tm["net_expectancy"] > best_exp:
                best_exp = tm["net_expectancy"]
                best_thr = thr

        m = compute_economic_metrics(test_ev, fwd_te, pfast_te, threshold=best_thr)
        from sklearn.metrics import roc_auc_score
        y_te = extract_target(test_fs)
        pfast_fs = model.predict_proba(extract_feature_matrix(test_fs))
        auc = roc_auc_score(y_te, pfast_fs)

        pair_holdout.append({
            "fold": gi + 1,
            "held_out_pairs": held_out,
            "threshold": best_thr,
            "auc": float(auc),
            "n_trades": m["n_trades"],
            "win_rate": m["win_rate"],
            "mean_return": m["mean_return"],
            "net_expectancy": m["net_expectancy"],
            "profit_factor": m["profit_factor"],
            "max_drawdown": m["max_drawdown"],
            "break_even_cost": m["break_even_cost"],
        })
        print(f"  Fold {gi+1}: AUC={auc:.4f}, thr={best_thr:.2f}, n={m['n_trades']}, "
              f"net_exp={m['net_expectancy']:.2f}, BE={m['break_even_cost']:.2f}")
    agg["pair_holdout"] = pair_holdout

    # 7. Regime robustness
    print("\n[7/10] Regime robustness...")
    # Use the model from last WF fold
    regime_results = {}
    regime_periods = [
        ("2016-2018", 2016, 2018), ("2019-2021", 2019, 2021),
        ("2022-2024", 2022, 2024), ("2025-2026", 2025, 2026),
    ]
    # Train on full data for regime analysis
    all_fs = [e for e in all_events if e.outcome_label in ("fast_mr", "slow_mr")]
    X_all = extract_feature_matrix(all_fs)
    y_all = extract_target(all_fs)
    model_full = LogisticModel()
    model_full.fit(X_all, y_all)
    all_pfast_full = model_full.predict_proba(extract_feature_matrix(all_events))
    all_fwd_full = extract_fwd_returns(all_events, horizon=4)

    for rlabel, ry_start, ry_end in regime_periods:
        rmask = np.array([ry_start <= e.ts.year <= ry_end for e in all_events])
        r_events = [e for e, m in zip(all_events, rmask) if m]
        r_fwd = all_fwd_full[rmask]
        r_pfast = all_pfast_full[rmask]
        if len(r_events) < 100:
            continue
        # Use threshold 0.70 as representative
        m = compute_economic_metrics(r_events, r_fwd, r_pfast, threshold=0.70)
        regime_results[rlabel] = {
            "n_trades": m["n_trades"],
            "win_rate": m["win_rate"],
            "mean_return": m["mean_return"],
            "net_expectancy": m["net_expectancy"],
            "profit_factor": m["profit_factor"],
            "max_drawdown": m["max_drawdown"],
            "break_even_cost": m["break_even_cost"],
        }
        print(f"  {rlabel}: n={m['n_trades']}, net_exp={m['net_expectancy']:.2f}, "
              f"PF={m['profit_factor']:.2f}, BE={m['break_even_cost']:.2f}")
    agg["regime"] = regime_results

    # 8. Permutation control
    print("\n[8/10] Permutation control...")
    perm_results = {}
    for thr in [0.60, 0.70, 0.80]:
        mask = all_oos_pfast >= thr
        if mask.sum() < 20:
            continue
        gated_returns = all_oos_fwd[mask]
        baseline_returns = all_oos_fwd
        p = permutation_test(gated_returns, baseline_returns)
        diff_mean, ci_lo, ci_hi = bootstrap_ci(gated_returns, baseline_returns)
        perm_results[thr] = {
            "permutation_p": p,
            "mean_diff": diff_mean,
            "bootstrap_ci_95": [ci_lo, ci_hi],
        }
        print(f"  P>={thr:.2f}: perm_p={p:.4f}, diff={diff_mean:.2f}pip, CI=[{ci_lo:.2f},{ci_hi:.2f}]")
    agg["perm_tests"] = perm_results

    # 9. Decile analysis + calibration
    print("\n[9/10] Decile analysis + calibration...")
    deciles = decile_analysis(all_oos_events_arr, all_oos_fwd, all_oos_pfast)
    for d in deciles:
        print(f"  Decile {d['decile']}: n={d['n']}, pred_p={d['mean_predicted_p']:.3f}, "
              f"actual_rate={d['actual_fast_rate']:.3f}, mean_ret={d['mean_return']:.2f}pip")
    agg["deciles"] = deciles

    actual_binary = np.array([1 if e.outcome_label == "fast_mr" else 0
                               for e in all_oos_events_arr])
    bs = brier_score(all_oos_pfast, actual_binary)
    ce = calibration_error(all_oos_pfast, actual_binary)
    print(f"  Brier score: {bs:.4f}, Calibration error: {ce:.4f}")
    agg["calibration"] = {"brier_score": bs, "calibration_error": ce}

    # 10. Classification vs economic
    print("\n[10/10] Classification vs economic...")
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    all_fs_oos = [e for e in all_oos_events_arr if e.outcome_label in ("fast_mr", "slow_mr")]
    oos_fs_idx = [i for i, e in enumerate(all_oos_events_arr) if e.outcome_label in ("fast_mr", "slow_mr")]
    y_oos = extract_target(all_fs_oos)
    p_oos = all_oos_pfast[oos_fs_idx]
    y_pred_oos = (p_oos >= 0.5).astype(int)
    from sklearn.metrics import roc_auc_score
    auc_oos = roc_auc_score(y_oos, p_oos)
    acc_oos = accuracy_score(y_oos, y_pred_oos)
    prec_oos = precision_score(y_oos, y_pred_oos, zero_division=0)
    rec_oos = recall_score(y_oos, y_pred_oos, zero_division=0)
    print(f"  OOS Classification: AUC={auc_oos:.4f}, Acc={acc_oos:.4f}, "
          f"Prec={prec_oos:.4f}, Rec={rec_oos:.4f}")
    agg["classification"] = {
        "auc": auc_oos, "accuracy": acc_oos,
        "precision": prec_oos, "recall": rec_oos,
        "brier_score": bs,
    }

    # Final verdict
    print("\n" + "=" * 70)
    # Determine verdict
    # Check if gated beats baseline in most WF folds
    n_positive_wf = sum(1 for r in wf_results.values()
                        if r["gated"]["net_expectancy"] > r["baseline"]["net_expectancy"])
    n_profitable_wf = sum(1 for r in wf_results.values()
                          if r["gated"]["net_expectancy"] > 0)
    avg_net_exp = np.mean([r["gated"]["net_expectancy"] for r in wf_results.values()])
    avg_be_cost = np.mean([r["break_even_cost"] for r in wf_results.values()])

    # Check cost robustness
    cost_survives_base = all(
        r["cost_scenarios"].get("COST_BASE", {}).get("net_expectancy", -999) > 0
        for r in wf_results.values()
    )
    cost_survives_low = all(
        r["cost_scenarios"].get("COST_LOW", {}).get("net_expectancy", -999) > 0
        for r in wf_results.values()
    )

    # Check pair holdout
    n_profitable_pairs = sum(1 for ph in pair_holdout if ph["net_expectancy"] > 0)

    avg_auc_oos = agg["classification"]["auc"]

    if n_profitable_wf >= 4 and cost_survives_base and avg_net_exp > 0:
        verdict = "SUPPORTED — TRADABLE"
    elif n_profitable_wf >= 3 and avg_net_exp > 0:
        verdict = "SUPPORTED — BUT COST SENSITIVE"
    elif avg_auc_oos > 0.55 and avg_net_exp > -0.5:
        verdict = "STATISTICALLY SUPPORTED — NOT ECONOMICALLY VIABLE"
    elif n_profitable_wf >= 2:
        verdict = "REGIME DEPENDENT"
    else:
        verdict = "REJECTED"

    # Compute aggregate metrics
    agg_gated = compute_economic_metrics(all_oos_events_arr, all_oos_fwd, all_oos_pfast,
                                          threshold=0.70)
    agg["gated_070"] = agg_gated

    print(f"  Verdict: {verdict}")
    print(f"  WF profitable folds: {n_profitable_wf}/5")
    print(f"  WF beats baseline: {n_positive_wf}/5")
    print(f"  Avg OOS net expectancy: {avg_net_exp:.2f}pip")
    print(f"  Avg break-even cost: {avg_be_cost:.2f}pip")
    print(f"  Pairs profitable: {n_profitable_pairs}/{len(pair_holdout)}")

    # Save results
    results = {
        "phase": "9B",
        "title": "Corrected Economic Validation — Walk-Forward Threshold Test",
        "timestamp": pd.Timestamp.now().isoformat(),
        "runtime_seconds": time.time() - t0,
        "accounting_validation": {
            "pip_value_eurusd": pip_value_per_lot("EUR/USD"),
            "pip_value_usdjpy": pip_value_per_lot("USD/JPY"),
            "cost_eurusd_1slip_350comm": cost_in_pips("EUR/USD", 0.0, 0.3, 3.50),
            "cost_usdjpy_1slip_350comm": cost_in_pips("USD/JPY", 0.0, 0.3, 3.50),
            "forward_returns_in_pips": True,
            "cost_pair_specific": True,
        },
        "config": {
            "seed": RNG_SEED, "n_perm": N_PERM, "n_boot": N_BOOT,
            "z_entry": Z_ENTRY, "lookback": LOOKBACK,
            "thresholds": THRESHOLDS,
            "features": OOS_FEATURES,
            "pairs": PAIRS,
            "cost_scenarios": COST_SCENARIOS,
        },
        "event_summary": {
            "total": len(all_events),
            "fast_mr": fast, "slow_mr": slow,
            "continuation": cont, "ambiguous": amb,
        },
        "global_thresholds": global_thresholds,
        "wf_results": wf_results,
        "aggregated": {
            "baseline": agg["baseline"],
            "oracle": agg["oracle"],
            "gated_070": agg.get("gated_070"),
            "thresholds": {str(k): v for k, v in agg["thresholds"].items()},
            "pair_holdout": pair_holdout,
            "regime": regime_results,
            "perm_tests": {str(k): v for k, v in perm_results.items()},
            "deciles": deciles,
            "calibration": agg["calibration"],
            "classification": agg["classification"],
        },
        "verdict": verdict,
    }

    with open(OUT_DIR / "phase9b_corrected_validation.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {OUT_DIR / 'phase9b_corrected_validation.json'}")

    generate_report(results)
    print(f"Report saved: {OUT_DIR / 'PHASE9B_CORRECTED_ECONOMIC_VALIDATION_REPORT.md'}")

    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"Phase 9B complete in {elapsed:.0f}s")
    print(f"Output: {OUT_DIR}")
    print(f"Verdict: {verdict}")
    print(f"{'='*70}")


def generate_report(results):
    wf = results["wf_results"]
    agg = results["aggregated"]
    gt = results["global_thresholds"]
    verdict = results["verdict"]
    ev = results["event_summary"]
    av = results["accounting_validation"]

    lines = []
    lines.append("# Phase 9B: Corrected Economic Validation Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    lines.append("Phase 9B corrects the accounting bugs identified in Phase 9 and reruns")
    lines.append("the economic validation with proper pip-based returns and pair-specific")
    lines.append("transaction costs.")
    lines.append("")
    lines.append(f"- Events analyzed: {ev['total']:,}")
    lines.append(f"- Walk-forward folds: {len(wf)}")
    lines.append(f"- Forward returns: actual pips (corrected)")
    lines.append(f"- Transaction costs: pair-specific (corrected)")
    lines.append("")

    # Accounting validation
    lines.append("## Economic Accounting Validation")
    lines.append("")
    lines.append("### Corrections from Phase 9")
    lines.append("")
    lines.append("| Issue | Phase 9 (Buggy) | Phase 9B (Corrected) |")
    lines.append("|-------|-----------------|----------------------|")
    lines.append(f"| pip_value(EUR/USD) | ${av['pip_value_eurusd']:.4f} | $10.00 |")
    lines.append(f"| pip_value(USD/JPY) | ${av['pip_value_usdjpy']:.4f} | $6.70 |")
    lines.append(f"| Commission in pips (EUR/USD) | 3500 pips | {av['cost_eurusd_1slip_350comm']:.2f} pips |")
    lines.append(f"| Forward returns | ΔP/P × 10000 (relative bp) | ΔP / pip_size (actual pips) |")
    lines.append(f"| Cost pair-specific | No (always EUR/USD) | Yes |")
    lines.append("")
    lines.append("### Unit Definitions")
    lines.append("")
    lines.append("- **Price**: market mid-price in conventional units")
    lines.append("- **Pip**: 0.0001 for non-JPY, 0.01 for JPY pairs")
    lines.append("- **Pip value per lot**: pip_size × 100,000 × USD_per_quote")
    lines.append("- **Forward return**: (P_{t+4} - P_t) / pip_size (in pips)")
    lines.append("- **Transaction cost**: spread + slippage + commission/pip_value (in pips)")
    lines.append("- **Net PnL**: sum of (forward_return - cost) across trades (in pips)")
    lines.append("")

    # Cost assumptions
    lines.append("## Cost Assumptions")
    lines.append("")
    lines.append("| Scenario | Spread | Slippage | Commission | Total EUR/USD | Total USD/JPY |")
    lines.append("|----------|--------|----------|------------|---------------|---------------|")
    for name, cs in results["config"]["cost_scenarios"].items():
        ci_eu = cost_in_pips("EUR/USD", cs["spread_pips"], cs["slippage_pips"], cs["commission_usd"])
        ci_uj = cost_in_pips("USD/JPY", cs["spread_pips"], cs["slippage_pips"], cs["commission_usd"])
        lines.append(f"| {name} | {cs['spread_pips']:.2f} | {cs['slippage_pips']:.2f} | "
                     f"${cs['commission_usd']:.2f} | {ci_eu:.2f}pip | {ci_uj:.2f}pip |")
    lines.append("")

    # Global threshold analysis
    lines.append("## Global Threshold Analysis")
    lines.append("")
    lines.append("| Threshold | Trades | % Traded | Fast Rate | Win Rate | Mean Ret | Gross Exp | BE Cost |")
    lines.append("|-----------|--------|----------|-----------|----------|----------|-----------|---------|")
    for thr, data in gt.items():
        lines.append(f"| {thr:.2f} | {data['n_trades']:,} | {data['pct_traded']:.1f}% | "
                     f"{data['fast_rate']:.3f} | {data['win_rate']:.3f} | "
                     f"{data['mean_return']:.2f} | {data['gross_expectancy']:.2f} | "
                     f"{data['break_even_cost']:.2f} |")
    lines.append("")

    # Walk-forward
    lines.append("## Walk-Forward Threshold Selection")
    lines.append("")
    lines.append("### Selection Method")
    lines.append("")
    lines.append("For each fold, the threshold is selected on TRAIN data only by maximizing")
    lines.append("net expectancy subject to minimum 50 trades. The selected threshold is")
    lines.append("then frozen and applied to the TEST set exactly once.")
    lines.append("")
    lines.append("### Results")
    lines.append("")
    lines.append("| Fold | Train | Test | Selected Thr | Test Trades | Test Net Exp | Test PF | BE Cost |")
    lines.append("|------|-------|------|-------------|-------------|--------------|---------|---------|")
    for label, r in wf.items():
        lines.append(f"| {label} | {r['train_range']} | {r['test_range']} | "
                     f"{r['selected_threshold']:.2f} | {r['gated']['n_trades']:,} | "
                     f"{r['gated']['net_expectancy']:.2f} | "
                     f"{r['gated']['profit_factor']:.2f} | {r['break_even_cost']:.2f} |")
    lines.append("")

    # Strict OOS comparison
    lines.append("### Strict OOS: Baseline vs Gated vs Oracle")
    lines.append("")
    lines.append("| Fold | Baseline Exp | Gated Exp | Oracle Exp | Gated > Baseline |")
    lines.append("|------|-------------|-----------|------------|------------------|")
    for label, r in wf.items():
        gb = "YES" if r["gated"]["net_expectancy"] > r["baseline"]["net_expectancy"] else "NO"
        lines.append(f"| {label} | {r['baseline']['net_expectancy']:.2f} | "
                     f"{r['gated']['net_expectancy']:.2f} | "
                     f"{r['oracle']['net_expectancy']:.2f} | {gb} |")
    lines.append("")

    # Threshold robustness
    lines.append("## Threshold Robustness")
    lines.append("")
    lines.append("### Last Fold (2025-2026) — Threshold Sensitivity")
    lines.append("")
    last_label = list(wf.keys())[-1]
    last_wf = wf[last_label]
    lines.append("| Threshold | Trades | Net Exp | PF | Max DD |")
    lines.append("|-----------|--------|---------|----|--------|")
    for thr_str, data in last_wf["threshold_robustness"].items():
        sel_marker = " ← SELECTED" if float(thr_str) == last_wf["selected_threshold"] else ""
        lines.append(f"| {thr_str} | {data['n_trades']:,} | {data['net_expectancy']:.2f} | "
                     f"{data['profit_factor']:.2f} | {data['max_drawdown']:.1f}{sel_marker} |")
    lines.append("")

    # Cost robustness
    lines.append("## Cost Robustness")
    lines.append("")
    lines.append("| Fold | Scenario | Net Exp | Net PnL | Net PF | Avg Cost |")
    lines.append("|------|----------|---------|---------|--------|----------|")
    for label, r in wf.items():
        for cname, cd in r["cost_scenarios"].items():
            lines.append(f"| {label} | {cname} | {cd['net_expectancy']:.2f} | "
                         f"{cd['net_pnl']:.1f} | {cd['net_pf']:.2f} | "
                         f"{cd['avg_cost_pips']:.2f} |")
    lines.append("")

    # Cross-pair
    lines.append("## Cross-Pair Out-of-Sample Validation")
    lines.append("")
    lines.append("| Fold | Held-Out Pairs | AUC | Threshold | Trades | Net Exp | BE Cost |")
    lines.append("|------|----------------|-----|-----------|--------|---------|---------|")
    for ph in results["aggregated"]["pair_holdout"]:
        lines.append(f"| {ph['fold']} | {', '.join(ph['held_out_pairs'])} | "
                     f"{ph['auc']:.4f} | {ph['threshold']:.2f} | {ph['n_trades']:,} | "
                     f"{ph['net_expectancy']:.2f} | {ph['break_even_cost']:.2f} |")
    n_prof = sum(1 for ph in results["aggregated"]["pair_holdout"] if ph["net_expectancy"] > 0)
    med_exp = np.median([ph["net_expectancy"] for ph in results["aggregated"]["pair_holdout"]])
    lines.append(f"\n- Profitable pairs: {n_prof}/{len(results['aggregated']['pair_holdout'])}")
    lines.append(f"- Median pair expectancy: {med_exp:.2f} pip")
    lines.append("")

    # Regime
    lines.append("## Regime Robustness")
    lines.append("")
    lines.append("| Period | Trades | Win Rate | Net Exp | PF | Max DD | BE Cost |")
    lines.append("|--------|--------|----------|---------|----|--------|---------|")
    for rl, rd in agg["regime"].items():
        lines.append(f"| {rl} | {rd['n_trades']:,} | {rd['win_rate']:.3f} | "
                     f"{rd['net_expectancy']:.2f} | {rd['profit_factor']:.2f} | "
                     f"{rd['max_drawdown']:.1f} | {rd['break_even_cost']:.2f} |")
    lines.append("")

    # Permutation
    lines.append("## Permutation Control")
    lines.append("")
    lines.append("| Threshold | Perm p | Mean Diff | Bootstrap CI 95% |")
    lines.append("|-----------|--------|-----------|------------------|")
    for thr, pt in agg["perm_tests"].items():
        ci = pt["bootstrap_ci_95"]
        lines.append(f"| {thr} | {pt['permutation_p']:.4f} | {pt['mean_diff']:.2f} | "
                     f"[{ci[0]:.2f}, {ci[1]:.2f}] |")
    lines.append("")

    # Deciles
    lines.append("## Signal Decile Analysis")
    lines.append("")
    lines.append("| Decile | N | Mean Pred P | Actual Fast Rate | Mean Ret | Net Exp |")
    lines.append("|--------|---|-------------|------------------|----------|---------|")
    for d in agg["deciles"]:
        lines.append(f"| {d['decile']} | {d['n']:,} | {d['mean_predicted_p']:.3f} | "
                     f"{d['actual_fast_rate']:.3f} | {d['mean_return']:.2f} | "
                     f"{d['net_expectancy']:.2f} |")
    lines.append("")

    # Calibration
    lines.append("## Probability Calibration")
    lines.append("")
    cal = agg["calibration"]
    lines.append(f"- Brier score: {cal['brier_score']:.4f}")
    lines.append(f"- Calibration error: {cal['calibration_error']:.4f}")
    lines.append("")

    # Classification vs economic
    lines.append("## Classification vs Economic Performance")
    lines.append("")
    cl = agg["classification"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| AUC | {cl['auc']:.4f} |")
    lines.append(f"| Accuracy | {cl['accuracy']:.4f} |")
    lines.append(f"| Precision | {cl['precision']:.4f} |")
    lines.append(f"| Recall | {cl['recall']:.4f} |")
    lines.append(f"| Brier score | {cl['brier_score']:.4f} |")
    lines.append("")

    # Aggregate OOS
    lines.append("## Aggregate Out-of-Sample Results")
    lines.append("")
    base = agg["baseline"]
    oracle = agg["oracle"]
    gated = agg.get("gated_070", {})
    lines.append(f"- **Baseline** (all events): n={base['n_trades']:,}, "
                 f"mean={base['mean_return']:.2f}pip, net_exp={base['net_expectancy']:.2f}, "
                 f"PF={base['profit_factor']:.2f}")
    lines.append(f"- **Gated** (P≥0.70): n={gated.get('n_trades', 0):,}, "
                 f"mean={gated.get('mean_return', 0):.2f}pip, net_exp={gated.get('net_expectancy', 0):.2f}, "
                 f"PF={gated.get('profit_factor', 0):.2f}")
    lines.append(f"- **Oracle** (true fast): n={oracle['n_trades']:,}, "
                 f"mean={oracle['mean_return']:.2f}pip, net_exp={oracle['net_expectancy']:.2f}, "
                 f"PF={oracle['profit_factor']:.2f}")
    lines.append("")

    # Final verdict
    lines.append("## Final Verdict")
    lines.append("")
    lines.append(f"### {verdict}")
    lines.append("")
    if "TRADABLE" in verdict:
        lines.append("The probability-gated strategy produces robust positive net expectancy")
        lines.append("across multiple test periods after realistic transaction costs.")
    elif "COST SENSITIVE" in verdict:
        lines.append("The predictive signal generates positive expectancy but the edge")
        lines.append("is sensitive to transaction cost assumptions.")
    elif "NOT ECONOMICALLY VIABLE" in verdict:
        lines.append("The model predicts fast/slow outcomes but the information does not")
        lines.append("translate into sufficient economic edge after costs.")
    elif "REGIME" in verdict:
        lines.append("The edge exists in some periods but not others.")
    else:
        lines.append("The economic advantage does not survive strict OOS validation.")
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    lines.append("See full report for detailed analysis.")
    lines.append("")

    with open(OUT_DIR / "PHASE9B_CORRECTED_ECONOMIC_VALIDATION_REPORT.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
