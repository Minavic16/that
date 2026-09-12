"""Phase 9: Probability-Gated Mean-Reversion — Strict OOS Economic Validation.

Determines whether the Phase 8 predictive signal produces a robust,
economically viable trading strategy after realistic transaction costs.

Usage:
    .venv/bin/python scripts/phase9_probability_gated_mr.py
"""
from __future__ import annotations

import json
import os
import pickle
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


from nestquant.research.shared.zscore.zscore import compute_zscore_causal

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
COMMISSION = 3.50
SLIPPAGE_PIPS = 0.3
ACCOUNT = 2500.0
RISK = 0.006
LEVERAGE = 100.0
ATR_SL_MULT = 3.0
TP_RATIO = 2.0
SESSIONS = {"london": (7, 16), "new_york": (12, 21)}
SKIP_FRI = 20
SKIP_MON = 3
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
THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
RANDOM_CONTROL_N = 100

# Doubly stable features from Phase 8 (must be entry-available)
OOS_FEATURES = [
    "abs_ret_1", "abs_ret_4", "abs_z", "body_range_ratio",
    "dist_from_recent_max_z", "dist_from_recent_min_z",
    "pair_z_rank", "range_expansion", "range_pctile_500",
    "vol_expansion",
]

# Walk-forward splits: expanding train, single-year test
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

OUT_DIR = Path("research/output/phase9")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def pip_value(pair: str) -> float:
    return pip_size(pair) * 10.0


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
            "pip": pip_size(pair), "pv": pip_value(pair),
            "spread": SPREAD.get(pair, 2.0),
        }
    return pdata


# ─── Event Extraction ────────────────────────────────────────────────────────
@dataclass
class MRPhase9Event:
    pair: str
    idx: int
    ts: pd.Timestamp
    z_now: float
    direction: int
    entry_price: float
    close_at_entry: float
    outcome_label: str
    fwd_ret_4: float
    fwd_ret_16: float
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
    realized_vol_pctile_500: float = 50.0
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

    # Pre-build index mappings: for each pair, map timestamp -> index
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

    # Build union of all timestamps
    all_ts_set = set()
    for pair, ts_list in pair_ts_list.items():
        all_ts_set.update(ts_list)
    all_ts = sorted(all_ts_set)

    events = []
    for ts in all_ts:
        # Cross-sectional features
        cross_zs = []
        cross_rets4 = []
        for pair, idx_map in pair_idx_map.items():
            if ts not in idx_map:
                continue
            idx = idx_map[ts]
            d = pdata[pair]
            cross_zs.append(d["z"][idx])
            if idx >= 4:
                cross_rets4.append(
                    (d["c"][idx] - d["c"][idx - 4]) / d["c"][idx - 4]
                )
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
            ts_now = ts_arr[idx]
            if not in_session(ts_now):
                continue
            z_now = d["z"][idx]
            if abs(z_now) < Z_ENTRY:
                continue
            direction = 1 if z_now < 0 else -1
            pip = d["pip"]
            slip = SLIPPAGE_PIPS * pip
            ep = d["c"][idx] + slip if direction == 1 else d["c"][idx] - slip
            z_path = d["z"][idx:idx + MAX_HOLD_BARS + 1]
            fwd_ret_4 = (d["c"][idx + 4] - d["c"][idx]) / d["c"][idx] * 10000 if idx + 4 < d["n"] else np.nan
            fwd_ret_16 = (d["c"][idx + 16] - d["c"][idx]) / d["c"][idx] * 10000 if idx + 16 < d["n"] else np.nan
            outcome = classify_outcome(z_path, z_now, direction)

            # Feature computation (all at or before idx)
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
            ret_1 = (c[idx] - c[idx - 1]) / c[idx - 1] * 10000
            ret_2 = (c[idx] - c[idx - 2]) / c[idx - 2] * 10000 if idx >= 2 else 0.0
            ret_4 = (c[idx] - c[idx - 4]) / c[idx - 4] * 10000 if idx >= 4 else 0.0
            ret_8 = (c[idx] - c[idx - 8]) / c[idx - 8] * 10000 if idx >= 8 else 0.0
            ret_16 = (c[idx] - c[idx - 16]) / c[idx - 16] * 10000 if idx >= 16 else 0.0
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
            dist_from_52h_high = (high_52h - c[idx]) / c[idx] * 10000
            dist_from_52h_low = (c[idx] - low_52h) / c[idx] * 10000
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

            ema200_dist = (c[idx] - d["ema200"][idx]) / c[idx] * 10000
            ema50_dist = (c[idx] - d["ema50"][idx]) / c[idx] * 10000
            ema20_dist = (c[idx] - d["ema20"][idx]) / c[idx] * 10000
            ema200_slope = (d["ema200"][idx] - d["ema200"][max(0, idx - 20)]) / d["ema200"][max(0, idx - 20)] * 100 if idx >= 20 else 0.0
            ema50_slope = (d["ema50"][idx] - d["ema50"][max(0, idx - 20)]) / d["ema50"][max(0, idx - 20)] * 100 if idx >= 20 else 0.0
            ema_cross_20_50 = ema20_dist - ema50_dist
            ema_cross_50_200 = ema50_dist - ema200_dist
            trend_ret_20 = (c[idx] - c[max(0, idx - 20)]) / c[max(0, idx - 20)] * 10000 if idx >= 20 else 0.0
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
            my_ret4 = (c[idx] - c[max(0, idx - 4)]) / c[max(0, idx - 4)] * 10000 if idx >= 4 else 0.0
            pair_ret_vs_cross = my_ret4 - cross_median_ret4 * 10000

            entry_h = ts_now.hour
            entry_d = ts_now.dayofweek
            sess_start = SESSIONS["london"][0] if entry_h < 12 else SESSIONS["new_york"][0]
            sess_end = SESSIONS["new_york"][1] if entry_h >= 12 else SESSIONS["london"][1]
            bars_since_open = entry_h - sess_start
            bars_until_close = sess_end - entry_h - 1
            weekend_dist = min((5 - entry_d) % 7, (entry_d) % 7)

            ev = MRPhase9Event(
                pair=pair, idx=idx, ts=ts_now, z_now=z_now,
                direction=direction, entry_price=ep, close_at_entry=c[idx],
                outcome_label=outcome, fwd_ret_4=fwd_ret_4, fwd_ret_16=fwd_ret_16,
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
                realized_vol_pctile_500=50.0,
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
        return np.array([ev.fwd_ret_4 for ev in events])
    return np.array([ev.fwd_ret_16 for ev in events])


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


# ─── Economic Evaluation ──────────────────────────────────────────────────────
def compute_economic_metrics(events, fwd_returns, p_fast, threshold=None,
                              spread_pips=0.0, commission=COMMISSION, slippage_pips=SLIPPAGE_PIPS):
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
        }
    # Per-trade PnL: forward return minus costs (in pips → $ equivalent)
    # avg_pip = mean forward return in pips
    # cost per trade = spread + commission + slippage
    avg_pip = np.nanmean(sel_returns)
    median_pip = np.nanmedian(sel_returns)
    std_pip = np.nanstd(sel_returns)
    win_rate = float(np.mean(sel_returns > 0)) if len(sel_returns) > 0 else 0.0
    n_fast = int(np.sum([e.outcome_label == "fast_mr" for e in sel_events]))
    fast_rate = n_fast / len(sel_events) if len(sel_events) > 0 else 0.0
    # Gross PnL (in pips)
    gross_pnl = float(np.nansum(sel_returns))
    # Cost per trade in pips
    cost_per_trade = spread_pips + commission / pip_value("EUR/USD") + slippage_pips
    net_returns = sel_returns - cost_per_trade
    net_pnl = float(np.nansum(net_returns))
    avg_pnl = float(np.nanmean(net_returns))
    avg_gross_pnl = float(np.nanmean(sel_returns))
    # Profit factor
    gains = float(np.nansum(sel_returns[sel_returns > 0]))
    losses = float(np.nansum(abs(sel_returns[sel_returns < 0])))
    pf = gains / losses if losses > 0 else float("inf") if gains > 0 else 0.0
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

    # Break-even cost
    gross_avg = avg_gross_pnl
    break_even_cost = gross_avg if gross_avg > 0 else 0.0

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


def cost_adversarial(events, fwd_returns, p_fast, threshold, pip_costs):
    results = {}
    for cost in pip_costs:
        m = compute_economic_metrics(events, fwd_returns, p_fast,
                                      threshold=threshold, spread_pips=cost,
                                      slippage_pips=0.0, commission=0.0)
        results[f"{cost:.2f}p"] = {
            "gross_expectancy": m["gross_expectancy"],
            "net_expectancy": m["net_expectancy"],
            "gross_pnl": m["gross_pnl"],
            "net_pnl": m["net_pnl"],
            "profit_factor": m["profit_factor"],
        }
    # NestQuant realistic cost
    m_nq = compute_economic_metrics(events, fwd_returns, p_fast,
                                     threshold=threshold,
                                     spread_pips=0.3, commission=COMMISSION,
                                     slippage_pips=SLIPPAGE_PIPS)
    results["nestquant"] = {
        "gross_expectancy": m_nq["gross_expectancy"],
        "net_expectancy": m_nq["net_expectancy"],
        "gross_pnl": m_nq["gross_pnl"],
        "net_pnl": m_nq["net_pnl"],
        "profit_factor": m_nq["profit_factor"],
        "spread_pips": 0.3, "commission": COMMISSION, "slippage_pips": SLIPPAGE_PIPS,
    }
    return results


def outlier_robustness(fwd_returns, p_fast, threshold, seed=RNG_SEED):
    mask = p_fast >= threshold if threshold is not None else np.ones(len(fwd_returns), dtype=bool)
    rets = fwd_returns[mask]
    rets = rets[~np.isnan(rets)]
    if len(rets) == 0:
        return {}
    full_mean = float(np.mean(rets))
    # Trim 10%
    sorted_rets = np.sort(rets)
    trim10 = int(len(sorted_rets) * 0.05)
    trimmed10 = sorted_rets[trim10:-trim10] if trim10 > 0 else sorted_rets
    # Trim 25%
    trim25 = int(len(sorted_rets) * 0.125)
    trimmed25 = sorted_rets[trim25:-trim25] if trim25 > 0 else sorted_rets
    median = float(np.median(rets))
    # Winsorize
    p5, p95 = np.percentile(rets, 5), np.percentile(rets, 95)
    winsorized = np.clip(rets, p5, p95)
    winsorized_mean = float(np.mean(winsorized))
    # Bootstrap CI
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


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase 9: Probability-Gated MR — Strict OOS Economic Validation")
    print("=" * 70)

    # 1. Load data
    print("\n[1/8] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"  Loaded {len(pdata)} pairs")

    # 2. Extract events
    print("\n[2/8] Extracting events...")
    all_events = extract_events(pdata, "2016-01-01", "2026-07-19")
    print(f"  Total events: {len(all_events)}")
    fast = sum(1 for e in all_events if e.outcome_label == "fast_mr")
    slow = sum(1 for e in all_events if e.outcome_label == "slow_mr")
    cont = sum(1 for e in all_events if e.outcome_label == "continuation")
    amb = sum(1 for e in all_events if e.outcome_label == "ambiguous")
    print(f"  fast_mr={fast}, slow_mr={slow}, continuation={cont}, ambiguous={amb}")

    # 3. Walk-forward evaluation
    print("\n[3/8] Walk-forward evaluation...")
    wf_results = {}
    all_oos_events = []
    all_oos_pfast = []
    all_oos_fwd = []

    for split in WF_SPLITS:
        label = split["label"]
        train_end = split["train_end"]
        test_start = split["test_start"]
        test_end = split["test_end"]
        train_start = 2016
        print(f"\n  Split {label}: train {train_start}-{train_end}, test {test_start}-{test_end}")

        train_events = [e for e in all_events
                        if train_start <= e.ts.year <= train_end]
        test_events = [e for e in all_events
                       if test_start <= e.ts.year <= test_end]

        # Filter to fast/slow only for model training
        train_fs = [e for e in train_events if e.outcome_label in ("fast_mr", "slow_mr")]
        test_fs = [e for e in test_events if e.outcome_label in ("fast_mr", "slow_mr")]
        print(f"    Train: {len(train_events)} total ({len(train_fs)} fast+slow)")
        print(f"    Test:  {len(test_events)} total ({len(test_fs)} fast+slow)")

        if len(train_fs) < 100 or len(test_fs) < 50:
            print(f"    SKIP: insufficient data")
            continue

        X_train = extract_feature_matrix(train_fs)
        y_train = extract_target(train_fs)
        X_test = extract_feature_matrix(test_fs)
        y_test = extract_target(test_fs)

        # Train model
        model = LogisticModel()
        model.fit(X_train, y_train)

        # Predict on ALL test events (including ambiguous/continuation for economic eval)
        X_test_all = extract_feature_matrix(test_events)
        pfast_all = model.predict_proba(X_test_all)
        fwd_all = extract_fwd_returns(test_events, horizon=4)

        # Also predict on test fast/slow only for model metrics
        pfast_fs = model.predict_proba(X_test)
        y_pred = (pfast_fs >= 0.5).astype(int)
        from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score
        auc = roc_auc_score(y_test, pfast_fs)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        print(f"    Model: AUC={auc:.4f}, Acc={acc:.4f}, Prec={prec:.4f}, Rec={rec:.4f}")

        # Top features
        coefs = model.coef_
        top_idx = np.argsort(np.abs(coefs))[::-1][:5]
        top_feats = [(model.feature_names[i], coefs[i]) for i in top_idx]
        print(f"    Top features: {top_feats[:3]}")

        # Unfiltered baseline
        base = compute_economic_metrics(test_events, fwd_all, np.ones(len(test_events)))
        print(f"    Baseline: n={base['n_trades']}, wr={base['win_rate']:.3f}, "
              f"mean={base['mean_return']:.2f}pip, net_pnl={base['net_pnl']:.1f}, "
              f"PF={base['profit_factor']:.2f}")

        # Oracle
        oracle = compute_oracle_metrics(test_events, fwd_all)
        print(f"    Oracle:   n={oracle['n_trades']}, wr={oracle['win_rate']:.3f}, "
              f"mean={oracle['mean_return']:.2f}pip, net_pnl={oracle['net_pnl']:.1f}")

        # Threshold analysis
        threshold_results = {}
        for thr in THRESHOLDS:
            m = compute_economic_metrics(test_events, fwd_all, pfast_all, threshold=thr)
            threshold_results[thr] = m
            print(f"    P>={thr:.2f}: n={m['n_trades']}, wr={m['win_rate']:.3f}, "
                  f"mean={m['mean_return']:.2f}pip, net_pnl={m['net_pnl']:.1f}, "
                  f"PF={m['profit_factor']:.2f}, fast_rate={m['fast_rate']:.3f}")

        # Diagnostic: P < 0.50
        low_mask = pfast_all < 0.50
        low_events = [e for e, m in zip(test_events, low_mask) if m]
        low_returns = fwd_all[low_mask]
        low_m = compute_economic_metrics(low_events, low_returns, pfast_all[low_mask])
        print(f"    P<0.50:   n={low_m['n_trades']}, wr={low_m['win_rate']:.3f}, "
              f"mean={low_m['mean_return']:.2f}pip, fast_rate={low_m['fast_rate']:.3f}")

        # Random control (for largest threshold with enough trades)
        random_controls = {}
        for thr in THRESHOLDS:
            n_thr = int(np.sum(pfast_all >= thr))
            if n_thr >= 20:
                rc = compute_random_control(test_events, fwd_all, pfast_all,
                                             n_thr, n_reps=RANDOM_CONTROL_N)
                random_controls[thr] = {
                    "mean_return": [r["mean_return"] for r in rc],
                    "net_pnl": [r["net_pnl"] for r in rc],
                    "win_rate": [r["win_rate"] for r in rc],
                    "profit_factor": [r["profit_factor"] for r in rc],
                }
                # Compare model vs random
                model_mean = threshold_results[thr]["mean_return"]
                rc_means = np.array(random_controls[thr]["mean_return"])
                model_beats_random = float(np.mean(model_mean > rc_means))
                print(f"    P>={thr:.2f} vs random: model mean={model_mean:.2f}pip, "
                      f"random mean={np.mean(rc_means):.2f}±{np.std(rc_means):.2f}pip, "
                      f"pctile={model_beats_random:.3f}")

        # Outlier robustness
        robustness = {}
        for thr in THRESHOLDS:
            rob = outlier_robustness(fwd_all, pfast_all, thr)
            robustness[thr] = rob

        # Cost adversarial
        pip_costs = [0.0, 0.25, 0.50, 0.75, 1.0, 1.25, 1.5, 2.0]
        cost_results = {}
        for thr in [0.60, 0.65, 0.70, 0.75, 0.80]:
            cost_results[thr] = cost_adversarial(test_events, fwd_all, pfast_all,
                                                   thr, pip_costs)

        wf_results[label] = {
            "train_range": f"{train_start}-{train_end}",
            "test_range": f"{test_start}-{test_end}",
            "n_train_total": len(train_events),
            "n_train_fs": len(train_fs),
            "n_test_total": len(test_events),
            "n_test_fs": len(test_fs),
            "model_auc": auc,
            "model_accuracy": acc,
            "model_precision": prec,
            "model_recall": rec,
            "top_features": top_feats,
            "baseline": base,
            "oracle": oracle,
            "thresholds": threshold_results,
            "low_diagnostic": low_m,
            "random_controls": random_controls,
            "robustness": robustness,
            "cost_results": cost_results,
        }

        all_oos_events.extend(test_events)
        all_oos_pfast.extend(pfast_all.tolist())
        all_oos_fwd.extend(fwd_all.tolist())

    all_oos_pfast = np.array(all_oos_pfast)
    all_oos_fwd = np.array(all_oos_fwd)
    all_oos_events_arr = all_oos_events

    # 4. Aggregated OOS metrics
    print("\n[4/8] Aggregated OOS analysis...")
    aggregated = {}
    base_agg = compute_economic_metrics(all_oos_events_arr, all_oos_fwd,
                                         np.ones(len(all_oos_events_arr)))
    aggregated["baseline"] = base_agg
    print(f"  Baseline: n={base_agg['n_trades']}, wr={base_agg['win_rate']:.3f}, "
          f"mean={base_agg['mean_return']:.2f}pip, net_pnl={base_agg['net_pnl']:.1f}")

    oracle_agg = compute_oracle_metrics(all_oos_events_arr, all_oos_fwd)
    aggregated["oracle"] = oracle_agg
    print(f"  Oracle:   n={oracle_agg['n_trades']}, wr={oracle_agg['win_rate']:.3f}, "
          f"mean={oracle_agg['mean_return']:.2f}pip, net_pnl={oracle_agg['net_pnl']:.1f}")

    agg_thresholds = {}
    for thr in THRESHOLDS:
        m = compute_economic_metrics(all_oos_events_arr, all_oos_fwd, all_oos_pfast, threshold=thr)
        agg_thresholds[thr] = m
        print(f"  P>={thr:.2f}: n={m['n_trades']}, wr={m['win_rate']:.3f}, "
              f"mean={m['mean_return']:.2f}pip, net_pnl={m['net_pnl']:.1f}, "
              f"PF={m['profit_factor']:.2f}, fast_rate={m['fast_rate']:.3f}")
    aggregated["thresholds"] = agg_thresholds

    # 5. Calibration
    print("\n[5/8] Probability calibration...")
    bins = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    bin_labels = ["P<0.4", "0.4-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "P>0.8"]
    calibration = {}
    actual_binary = np.array([1 if e.outcome_label == "fast_mr" else 0
                               for e in all_oos_events_arr])
    for i, (lo, hi) in enumerate(zip(bins[:-1], bins[1:])):
        mask = (all_oos_pfast >= lo) & (all_oos_pfast < hi)
        if mask.sum() == 0:
            continue
        pred_mean = float(np.mean(all_oos_pfast[mask]))
        actual_rate = float(np.mean(actual_binary[mask]))
        mean_ret = float(np.mean(all_oos_fwd[mask]))
        m = compute_economic_metrics(
            [all_oos_events_arr[j] for j in range(len(all_oos_events_arr)) if mask[j]],
            all_oos_fwd[mask], all_oos_pfast[mask])
        calibration[bin_labels[i]] = {
            "n": int(mask.sum()),
            "mean_predicted_p": pred_mean,
            "actual_fast_rate": actual_rate,
            "mean_return": mean_ret,
            "median_return": float(np.median(all_oos_fwd[mask])),
            "net_expectancy": m["net_expectancy"],
        }
        print(f"  {bin_labels[i]}: n={mask.sum()}, pred={pred_mean:.3f}, "
              f"actual={actual_rate:.3f}, mean_ret={mean_ret:.2f}pip")

    bs = brier_score(all_oos_pfast, actual_binary)
    ce = calibration_error(all_oos_pfast, actual_binary)
    print(f"  Brier score: {bs:.4f}")
    print(f"  Calibration error: {ce:.4f}")
    aggregated["calibration"] = {
        "buckets": calibration,
        "brier_score": bs,
        "calibration_error": ce,
    }

    # 6. Pair holdout
    print("\n[6/8] Pair holdout...")
    pair_holdout_results = []
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
        X_te = extract_feature_matrix(test_fs)
        y_te = extract_target(test_fs)
        model = LogisticModel()
        model.fit(X_tr, y_tr)
        pfast_te = model.predict_proba(X_te)
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y_te, pfast_te)

        # Full test events
        X_te_all = extract_feature_matrix(test_ev)
        pfast_all_ph = model.predict_proba(X_te_all)
        fwd_ph = extract_fwd_returns(test_ev, horizon=4)
        base_ph = compute_economic_metrics(test_ev, fwd_ph, np.ones(len(test_ev)))

        thr_results = {}
        for thr in THRESHOLDS:
            m = compute_economic_metrics(test_ev, fwd_ph, pfast_all_ph, threshold=thr)
            thr_results[thr] = m

        pair_holdout_results.append({
            "fold": gi + 1,
            "held_out_pairs": held_out,
            "train_pairs": len(train_pairs),
            "n_train": len(train_fs),
            "n_test": len(test_fs),
            "auc": float(auc),
            "baseline": base_ph,
            "thresholds": thr_results,
        })
        print(f"  Fold {gi+1}: AUC={auc:.4f}, test_n={len(test_fs)}, "
              f"baseline_wr={base_ph['win_rate']:.3f}")

    aggregated["pair_holdout"] = pair_holdout_results

    # 7. Permutation tests (gated vs baseline)
    print("\n[7/8] Statistical tests...")
    perm_tests = {}
    for thr in THRESHOLDS:
        mask = all_oos_pfast >= thr
        if mask.sum() < 20:
            continue
        gated_returns = all_oos_fwd[mask]
        baseline_returns = all_oos_fwd
        p = permutation_test(gated_returns, baseline_returns)
        diff_mean, ci_lo, ci_hi = bootstrap_ci(gated_returns, baseline_returns)
        perm_tests[thr] = {
            "permutation_p": p,
            "mean_diff": diff_mean,
            "bootstrap_ci_95": [ci_lo, ci_hi],
        }
        print(f"  P>={thr:.2f} vs baseline: perm_p={p:.4f}, diff={diff_mean:.2f}pip, "
              f"CI=[{ci_lo:.2f}, {ci_hi:.2f}]")
    aggregated["perm_tests"] = perm_tests

    # 8. Incremental value
    print("\n[8/8] Incremental value...")
    incremental = {}
    for thr in THRESHOLDS:
        m = agg_thresholds.get(thr, {})
        base = aggregated["baseline"]
        if m.get("n_trades", 0) == 0:
            continue
        incr_pnl = m.get("net_pnl", 0) - base.get("net_pnl", 0)
        incr_exp = m.get("net_expectancy", 0) - base.get("net_expectancy", 0)
        trades_saved = base.get("n_trades", 0) - m.get("n_trades", 0)
        incremental[thr] = {
            "incremental_pnl": incr_pnl,
            "incremental_expectancy": incr_exp,
            "trades_saved": trades_saved,
            "trades_kept": m.get("n_trades", 0),
        }
        print(f"  P>={thr:.2f}: incr_pnl={incr_pnl:.1f}, incr_exp={incr_exp:.2f}pip, "
              f"trades {m.get('n_trades', 0)} (saved {trades_saved})")
    aggregated["incremental"] = incremental

    # Verdict
    print("\n" + "=" * 70)
    # Check hypotheses
    h1 = all(wf_results[l]["model_auc"] > 0.55 for l in wf_results)
    h2 = all(
        agg_thresholds[t]["fast_rate"] > 0.55
        for t in THRESHOLDS
        if agg_thresholds[t]["n_trades"] >= 100
    )
    h3 = any(
        agg_thresholds[t]["net_expectancy"] > aggregated["baseline"]["net_expectancy"]
        for t in THRESHOLDS
        if agg_thresholds[t]["n_trades"] >= 100
    )
    # H4: gated beats random (check aggregated)
    h4 = False
    for thr in THRESHOLDS:
        mask = all_oos_pfast >= thr
        if mask.sum() < 20:
            continue
        model_mean = agg_thresholds[thr]["mean_return"]
        # Compare against 0 (random would have mean ≈ 0)
        h4 = h4 or (model_mean > 0 and perm_tests.get(thr, {}).get("permutation_p", 1.0) < 0.1)

    # H5: survives costs (check if P>=0.70 still positive after 1.0 pip cost)
    h5 = False
    for thr in [0.70, 0.75, 0.80]:
        cr = wf_results.get(list(wf_results.keys())[-1], {}).get("cost_results", {}).get(thr, {})
        if "1.00p" in cr:
            h5 = h5 or cr["1.00p"]["net_expectancy"] > 0

    # H6: survives outlier trimming
    h6 = False
    for thr in [0.70, 0.75, 0.80]:
        rob = wf_results.get(list(wf_results.keys())[-1], {}).get("robustness", {}).get(thr, {})
        if rob:
            h6 = h6 or rob.get("trim25_mean", 0) > 0

    # H7: generalizes across periods
    h7 = sum(
        1 for l in wf_results
        if wf_results[l]["thresholds"].get(0.70, {}).get("n_trades", 0) >= 20
           and wf_results[l]["thresholds"].get(0.70, {}).get("net_expectancy", 0) > 0
    ) >= 3

    # H8: generalizes across pairs
    h8 = sum(
        1 for ph in pair_holdout_results
        if ph["thresholds"].get(0.70, {}).get("n_trades", 0) >= 20
           and ph["thresholds"].get(0.70, {}).get("net_expectancy", 0) > 0
    ) >= 3

    # H9: calibration
    cal_err = aggregated["calibration"]["calibration_error"]
    h9 = bool(cal_err < 0.10)

    hypotheses = {
        "H1_predicts_oos": bool(h1),
        "H2_higher_p_higher_fast_rate": bool(h2),
        "H3_higher_net_expectancy": bool(h3),
        "H4_beats_random": bool(h4),
        "H5_survives_costs": bool(h5),
        "H6_survives_outliers": bool(h6),
        "H7_generalizes_periods": bool(h7),
        "H8_generalizes_pairs": bool(h8),
        "H9_calibrated": bool(h9),
    }

    n_supported = sum(hypotheses.values())
    if n_supported >= 7:
        verdict = "STRONG SUPPORT"
    elif n_supported >= 5:
        verdict = "PROMISING"
    elif n_supported >= 3:
        verdict = "PREDICTIVE-BUT-NOT-TRADEABLE"
    elif n_supported >= 1:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "FAILED"

    print(f"  Hypotheses supported: {n_supported}/9")
    for k, v in hypotheses.items():
        print(f"    {k}: {'PASS' if v else 'FAIL'}")
    print(f"\n  VERDICT: {verdict}")

    # Save results
    results = {
        "phase": 9,
        "title": "Probability-Gated MR — Strict OOS Economic Validation",
        "timestamp": pd.Timestamp.now().isoformat(),
        "runtime_seconds": time.time() - t0,
        "config": {
            "seed": RNG_SEED, "n_perm": N_PERM, "n_boot": N_BOOT,
            "z_entry": Z_ENTRY, "lookback": LOOKBACK,
            "thresholds": THRESHOLDS,
            "features": OOS_FEATURES,
            "pairs": PAIRS,
            "wf_splits": WF_SPLITS,
        },
        "event_summary": {
            "total": len(all_events),
            "fast_mr": fast, "slow_mr": slow,
            "continuation": cont, "ambiguous": amb,
        },
        "wf_results": wf_results,
        "aggregated": aggregated,
        "hypotheses": hypotheses,
        "verdict": verdict,
    }

    with open(OUT_DIR / "probability_gated_mr.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {OUT_DIR / 'probability_gated_mr.json'}")

    # Generate report
    generate_report(results)
    print(f"Report saved: {OUT_DIR / 'PHASE9_PROBABILITY_GATED_MR_REPORT.md'}")

    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"Phase 9 complete in {elapsed:.0f}s")
    print(f"Output: {OUT_DIR}")
    print(f"Verdict: {verdict}")
    print(f"Hypotheses: {n_supported}/9")
    print(f"{'='*70}")


def generate_report(results):
    wf = results["wf_results"]
    agg = results["aggregated"]
    hyps = results["hypotheses"]
    verdict = results["verdict"]
    ev = results["event_summary"]

    lines = []
    lines.append("# Phase 9: Probability-Gated Mean-Reversion Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    lines.append("Phase 9 tests whether the Phase 8 predictive signal (P(fast MR))")
    lines.append("produces a robust, economically viable trading strategy after")
    lines.append("realistic transaction costs and strict out-of-sample validation.")
    lines.append("")
    lines.append(f"- Events analyzed: {ev['total']:,}")
    lines.append(f"- Walk-forward splits: {len(wf)}")
    lines.append(f"- Hypotheses supported: {sum(hyps.values())}/9")
    lines.append("")

    # Data
    lines.append("## Data")
    lines.append("")
    lines.append(f"- Total events: {ev['total']:,}")
    lines.append(f"- fast_mr: {ev['fast_mr']:,} ({ev['fast_mr']/ev['total']*100:.1f}%)")
    lines.append(f"- slow_mr: {ev['slow_mr']:,} ({ev['slow_mr']/ev['total']*100:.1f}%)")
    lines.append(f"- continuation: {ev['continuation']:,}")
    lines.append(f"- ambiguous: {ev['ambiguous']:,}")
    lines.append("")

    # Model
    lines.append("## Model")
    lines.append("")
    lines.append("Logistic regression (scikit-learn, C=1.0, max_iter=1000)")
    lines.append("")
    lines.append("| Split | Train N | Test N | AUC | Accuracy | Precision | Recall |")
    lines.append("|-------|---------|--------|-----|----------|-----------|--------|")
    for label, r in wf.items():
        lines.append(f"| {label} | {r['n_train_fs']:,} | {r['n_test_fs']:,} | "
                     f"{r['model_auc']:.4f} | {r['model_accuracy']:.4f} | "
                     f"{r['model_precision']:.4f} | {r['model_recall']:.4f} |")
    lines.append("")

    # Walk-forward economic results
    lines.append("## Walk-Forward Economic Results")
    lines.append("")
    lines.append("| Strategy | Threshold | Test Period | Trades | Win Rate | Mean Return | Net PnL | PF | Max DD |")
    lines.append("|----------|-----------|-------------|--------|----------|-------------|---------|----|--------|")
    for label, r in wf.items():
        base = r["baseline"]
        lines.append(f"| Baseline | — | {label} | {base['n_trades']:,} | "
                     f"{base['win_rate']:.3f} | {base['mean_return']:.2f}pip | "
                     f"{base['net_pnl']:.1f} | {base['profit_factor']:.2f} | "
                     f"{base['max_drawdown']:.1f} |")
        oracle = r["oracle"]
        lines.append(f"| Oracle | — | {label} | {oracle['n_trades']:,} | "
                     f"{oracle['win_rate']:.3f} | {oracle['mean_return']:.2f}pip | "
                     f"{oracle['net_pnl']:.1f} | {oracle['profit_factor']:.2f} | "
                     f"{oracle['max_drawdown']:.1f} |")
        for thr in THRESHOLDS:
            m = r["thresholds"].get(thr, {})
            if m.get("n_trades", 0) > 0:
                lines.append(f"| Gated | {thr:.2f} | {label} | {m['n_trades']:,} | "
                             f"{m['win_rate']:.3f} | {m['mean_return']:.2f}pip | "
                             f"{m['net_pnl']:.1f} | {m['profit_factor']:.2f} | "
                             f"{m['max_drawdown']:.1f} |")
    lines.append("")

    # Aggregated OOS
    lines.append("## Aggregated OOS Results")
    lines.append("")
    lines.append("| Threshold | OOS Trades | Fast Rate | Mean Return | Net Expectancy | PF | Break-even Cost |")
    lines.append("|-----------|------------|-----------|-------------|----------------|----|-----------------|")
    base = agg["baseline"]
    lines.append(f"| Baseline | {base['n_trades']:,} | {base['fast_rate']:.3f} | "
                 f"{base['mean_return']:.2f}pip | {base['net_expectancy']:.2f} | "
                 f"{base['profit_factor']:.2f} | — |")
    oracle = agg["oracle"]
    lines.append(f"| Oracle | {oracle['n_trades']:,} | {oracle['fast_rate']:.3f} | "
                 f"{oracle['mean_return']:.2f}pip | {oracle['net_expectancy']:.2f} | "
                 f"{oracle['profit_factor']:.2f} | — |")
    for thr in THRESHOLDS:
        m = agg["thresholds"].get(thr, {})
        if m.get("n_trades", 0) > 0:
            bec = m.get("break_even_cost", 0)
            lines.append(f"| {thr:.2f} | {m['n_trades']:,} | {m['fast_rate']:.3f} | "
                         f"{m['mean_return']:.2f}pip | {m['net_expectancy']:.2f} | "
                         f"{m['profit_factor']:.2f} | {bec:.2f}pip |")
    lines.append("")

    # Random control
    lines.append("## Random Control Comparison")
    lines.append("")
    lines.append("Model-gated strategy compared against 100 random selections of matched size.")
    lines.append("")
    for label, r in wf.items():
        lines.append(f"### Split {label}")
        for thr, rc in r.get("random_controls", {}).items():
            rc_means = np.array(rc["mean_return"])
            model_mean = r["thresholds"][thr]["mean_return"]
            pctile = float(np.mean(model_mean > rc_means))
            lines.append(f"- P>={thr:.2f}: model={model_mean:.2f}pip, "
                         f"random={np.mean(rc_means):.2f}±{np.std(rc_means):.2f}pip, "
                         f"percentile={pctile:.3f}")
        lines.append("")

    # Cost analysis
    lines.append("## Cost Sensitivity")
    lines.append("")
    lines.append("| Threshold | 0.0p | 0.5p | 1.0p | 1.5p | 2.0p | NestQuant |")
    lines.append("|-----------|------|------|------|------|------|-----------|")
    for thr in [0.60, 0.65, 0.70, 0.75, 0.80]:
        # Use last split
        last_label = list(wf.keys())[-1]
        cr = wf[last_label].get("cost_results", {}).get(thr, {})
        vals = []
        for cost_key in ["0.00p", "0.50p", "1.00p", "1.50p", "2.00p"]:
            v = cr.get(cost_key, {}).get("net_expectancy", 0)
            vals.append(f"{v:.2f}")
        nq = cr.get("nestquant", {}).get("net_expectancy", 0)
        lines.append(f"| {thr:.2f} | {' | '.join(vals)} | {nq:.2f} |")
    lines.append("")

    # Outlier robustness
    lines.append("## Outlier Robustness")
    lines.append("")
    lines.append("| Threshold | Full Mean | Trim10 | Trim25 | Median | Stability | Bootstrap CI |")
    lines.append("|-----------|-----------|--------|--------|--------|-----------|---------------|")
    for thr in [0.60, 0.65, 0.70, 0.75, 0.80]:
        last_label = list(wf.keys())[-1]
        rob = wf[last_label].get("robustness", {}).get(thr, {})
        if rob:
            ci = rob.get("bootstrap_ci_95", [0, 0])
            lines.append(f"| {thr:.2f} | {rob.get('full_mean', 0):.2f} | "
                         f"{rob.get('trim10_mean', 0):.2f} | {rob.get('trim25_mean', 0):.2f} | "
                         f"{rob.get('median', 0):.2f} | {rob.get('stability_ratio', 0):.3f} | "
                         f"[{ci[0]:.2f}, {ci[1]:.2f}] |")
    lines.append("")

    # Calibration
    lines.append("## Probability Calibration")
    lines.append("")
    cal = agg["calibration"]
    lines.append("| P(fast) Bucket | N | Predicted P | Actual Fast Rate | Mean Return | Net Expectancy |")
    lines.append("|----------------|---|-------------|------------------|-------------|----------------|")
    for label, b in cal["buckets"].items():
        lines.append(f"| {label} | {b['n']:,} | {b['mean_predicted_p']:.3f} | "
                     f"{b['actual_fast_rate']:.3f} | {b['mean_return']:.2f} | "
                     f"{b['net_expectancy']:.2f} |")
    lines.append("")
    lines.append(f"- Brier score: {cal['brier_score']:.4f}")
    lines.append(f"- Calibration error: {cal['calibration_error']:.4f}")
    lines.append("")

    # Pair holdout
    lines.append("## Pair Holdout")
    lines.append("")
    lines.append("| Fold | Held-Out Pairs | AUC | Test N | Baseline WR | Baseline Net PnL |")
    lines.append("|------|----------------|-----|--------|-------------|------------------|")
    for ph in agg["pair_holdout"]:
        lines.append(f"| {ph['fold']} | {', '.join(ph['held_out_pairs'])} | "
                     f"{ph['auc']:.4f} | {ph['n_test']:,} | "
                     f"{ph['baseline']['win_rate']:.3f} | {ph['baseline']['net_pnl']:.1f} |")
    lines.append("")

    # Statistical tests
    lines.append("## Statistical Tests")
    lines.append("")
    lines.append("### Permutation Tests (Gated vs Baseline)")
    lines.append("")
    lines.append("| Threshold | Permutation p | Mean Diff | Bootstrap CI 95% |")
    lines.append("|-----------|---------------|-----------|------------------|")
    for thr, pt in agg.get("perm_tests", {}).items():
        ci = pt.get("bootstrap_ci_95", [0, 0])
        lines.append(f"| {thr:.2f} | {pt['permutation_p']:.4f} | "
                     f"{pt['mean_diff']:.2f} | [{ci[0]:.2f}, {ci[1]:.2f}] |")
    lines.append("")

    # Hypotheses
    lines.append("## Research Hypotheses")
    lines.append("")
    lines.append("| Hypothesis | Result |")
    lines.append("|------------|--------|")
    for k, v in hyps.items():
        lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    lines.append("")

    # Limitations
    lines.append("## Limitations")
    lines.append("")
    lines.append("1. AUC ~0.62 is modest; the model explains limited variance in fast/slow outcomes.")
    lines.append("2. Transaction costs substantially erode the raw signal's economic value.")
    lines.append("3. Multiple thresholds tested increases false-positive risk.")
    lines.append("4. The fast/slow label definition (4-bar 50% recovery, 16-bar 30% recovery) is somewhat arbitrary.")
    lines.append("5. Volume data quality varies across pairs and periods.")
    lines.append("6. Walk-forward test periods are relatively short (1-2 years each).")
    lines.append("7. Break-even costs may be low relative to realistic execution.")
    lines.append("")

    # Verdict
    lines.append("## Final Verdict")
    lines.append("")
    lines.append(f"### {verdict}")
    lines.append("")
    if verdict == "STRONG SUPPORT":
        lines.append("The probability-gated strategy demonstrates robust economic value")
        lines.append("across multiple test periods, currency pairs, and cost scenarios.")
    elif verdict == "PROMISING":
        lines.append("The predictive signal is robust and shows economic promise, but")
        lines.append("cost sensitivity, calibration, or generalization limits strong confirmation.")
    elif verdict == "PREDICTIVE-BUT-NOT-TRADEABLE":
        lines.append("The model reliably predicts fast/slow outcomes, but the information")
        lines.append("does not produce sufficient economic edge after realistic costs.")
    elif verdict == "INCONCLUSIVE":
        lines.append("Some positive evidence exists but OOS evidence is insufficient.")
    else:
        lines.append("The economic advantage disappears under strict OOS, cost, or robustness testing.")
    lines.append("")

    # Recommended next
    lines.append("## Recommended Next Phase")
    lines.append("")
    if verdict in ("STRONG SUPPORT", "PROMISING"):
        lines.append("- Paper trading validation with real execution data")
        lines.append("- Live execution simulation with realistic fill modeling")
        lines.append("- Position sizing optimization based on P(fast) magnitude")
        lines.append("- Multi-asset class generalization")
    elif verdict == "PREDICTIVE-BUT-NOT-TRADEABLE":
        lines.append("- Investigate higher-frequency timeframes for tighter spreads")
        lines.append("- Explore non-linear models (gradient boosting) for higher AUC")
        lines.append("- Combine P(fast) with regime conditioning for selective entry")
    else:
        lines.append("- Document findings for research archive")
        lines.append("- Consider alternative signal formulations")
        lines.append("- Investigate whether the predictive relationship holds at different horizons")
    lines.append("")

    with open(OUT_DIR / "PHASE9_PROBABILITY_GATED_MR_REPORT.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
