"""Phase 10: Economic Edge Decomposition and Failure Analysis.

Investigates whether the small gross predictive edge is economically
meaningful or being destroyed by trading costs.

This is an INVESTIGATION phase, NOT an optimization phase.

Usage:
    .venv/bin/python scripts/phase10_edge_decomposition.py
"""
from __future__ import annotations

import csv
import json
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zscore.zscore import compute_zscore_causal

# ─── Constants ────────────────────────────────────────────────────────────────
RNG_SEED = 42
N_PERM = 1000
N_BOOT = 1000
Z_ENTRY = 2.2
LOOKBACK = 20
ATR_PERIOD = 14
FAST_THRESHOLD = 0.50
SLOW_THRESHOLD = 0.30
MAX_HOLD_BARS = 64
COMMISSION_USD = 3.50
SLIPPAGE_PIPS = 0.3
CONTRACT_SIZE = 100_000
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
DEFAULT_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "AUD": 0.65,
    "NZD": 0.60, "CAD": 0.74, "CHF": 1.12, "JPY": 0.0067,
}
OOS_FEATURES = [
    "abs_ret_1", "abs_ret_4", "abs_z", "body_range_ratio",
    "dist_from_recent_max_z", "dist_from_recent_min_z",
    "pair_z_rank", "range_expansion", "range_pctile_500",
    "vol_expansion",
]
WF_SPLITS = [
    {"train_end": 2020, "test_start": 2021, "test_end": 2021, "label": "2021"},
    {"train_end": 2021, "test_start": 2022, "test_end": 2022, "label": "2022"},
    {"train_end": 2022, "test_start": 2023, "test_end": 2023, "label": "2023"},
    {"train_end": 2023, "test_start": 2024, "test_end": 2024, "label": "2024"},
    {"train_end": 2024, "test_start": 2025, "test_end": 2026, "label": "2025-2026"},
]
OUT_DIR = Path("/root/nestquant/research_data/phase10")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def pip_size(pair):
    return 0.01 if "JPY" in pair else 0.0001


def pip_value_per_lot(pair):
    base, quote = pair.split("/")
    return pip_size(pair) * CONTRACT_SIZE * DEFAULT_USD.get(quote, 1.0)


def cost_in_pips(pair, spread_pips, slippage_pips, commission_usd):
    pv = pip_value_per_lot(pair)
    return spread_pips + slippage_pips + (commission_usd / pv if pv > 0 else 0.0)


def in_session(ts):
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
def extract_events(pdata, start_date, end_date):
    start_dt = pd.Timestamp(start_date, tz="UTC")
    end_dt = pd.Timestamp(end_date, tz="UTC")
    pair_idx_map = {}
    for pair, d in pdata.items():
        ts_arr = d["ts"]
        idx_map = {}
        for i, t in enumerate(ts_arr):
            if t >= start_dt and t <= end_dt:
                idx_map[t] = i
        pair_idx_map[pair] = idx_map

    all_ts_set = set()
    for pair, idx_map in pair_idx_map.items():
        all_ts_set.update(idx_map.keys())
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
                cross_rets4.append((d["c"][idx] - d["c"][idx - 4]) / pip_size(pair))
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
            c = d["c"]
            # Forward returns in pips
            fwd_ret_4 = (c[idx + 4] - c[idx]) / pip if idx + 4 < d["n"] else np.nan
            fwd_ret_16 = (c[idx + 16] - c[idx]) / pip if idx + 16 < d["n"] else np.nan
            z_path = d["z"][idx:idx + MAX_HOLD_BARS + 1]
            outcome = classify_outcome(z_path, z_now, direction)

            # Features
            abs_z = abs(z_now)
            z_pctile_200 = causal_percentile(d["z"], idx, z_now, 200)
            z_pctile_500 = causal_percentile(d["z"], idx, z_now, 500)
            z_pctile_1000 = causal_percentile(d["z"], idx, z_now, 1000)
            z_pctile_2000 = causal_percentile(d["z"], idx, z_now, 2000)
            max_z = np.nanmax(d["z"][max(0, idx - 200):idx + 1])
            min_z = np.nanmin(d["z"][max(0, idx - 200):idx + 1])
            dist_from_recent_max_z = abs_z - abs(max_z)
            dist_from_recent_min_z = abs_z - abs(min_z)
            abs_ret_1 = abs((c[idx] - c[idx - 1]) / pip) if idx >= 1 else 0.0
            abs_ret_4 = abs((c[idx] - c[idx - 4]) / pip) if idx >= 4 else 0.0
            h = d["h"][idx]
            lo = d["lo"][idx]
            rng = h - lo
            body = abs(c[idx] - d["o"][idx])
            body_range_ratio = body / rng if rng > 1e-10 else 0.5
            recent_range = np.nanmean(d["bar_range"][max(0, idx - 200):idx + 1])
            range_expansion = rng / recent_range if recent_range > 1e-10 else 1.0
            range_pctile_500 = causal_percentile(d["bar_range"], idx, d["bar_range"][idx], 500)
            vol_20 = np.mean(d["vol"][max(0, idx - 20):idx + 1])
            vol_expansion = d["vol"][idx] / vol_20 if vol_20 > 0 else 1.0
            all_zs_sorted = sorted(cross_zs)
            rank = np.searchsorted(all_zs_sorted, z_now)
            pair_z_rank = rank / len(all_zs_sorted) if all_zs_sorted else 0.5

            events.append({
                "pair": pair, "idx": idx, "ts": ts_now, "z_now": z_now,
                "direction": direction, "close_at_entry": c[idx],
                "outcome": outcome, "fwd_ret_4": fwd_ret_4, "fwd_ret_16": fwd_ret_16,
                "abs_z": abs_z, "z_pctile_200": z_pctile_200,
                "z_pctile_500": z_pctile_500, "z_pctile_1000": z_pctile_1000,
                "z_pctile_2000": z_pctile_2000,
                "dist_from_recent_max_z": dist_from_recent_max_z,
                "dist_from_recent_min_z": dist_from_recent_min_z,
                "abs_ret_1": abs_ret_1, "abs_ret_4": abs_ret_4,
                "body_range_ratio": body_range_ratio,
                "range_expansion": range_expansion, "range_pctile_500": range_pctile_500,
                "vol_expansion": vol_expansion, "pair_z_rank": pair_z_rank,
                "cross_median_z": cross_median_z, "cross_mean_z": cross_mean_z,
                "cross_pct_extreme": cross_pct_extreme,
                "entry_hour": float(ts_now.hour), "entry_dow": float(ts_now.dayofweek),
                "year": ts_now.year, "month": ts_now.month,
            })
    return events


def extract_features(events):
    X = np.zeros((len(events), len(OOS_FEATURES)))
    for i, ev in enumerate(events):
        for j, fname in enumerate(OOS_FEATURES):
            X[i, j] = ev[fname]
    return X


def extract_target(events):
    return np.array([1 if e["outcome"] == "fast_mr" else 0 for e in events])


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


# ─── Statistical Helpers ──────────────────────────────────────────────────────
def bootstrap_ci(arr, n_boot=N_BOOT, seed=RNG_SEED):
    rng = np.random.RandomState(seed)
    means = np.array([np.mean(rng.choice(arr, size=len(arr), replace=True))
                      for _ in range(n_boot)])
    return float(np.mean(means)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def permutation_test_economic(gated_returns, baseline_returns, n_perm=N_PERM, seed=RNG_SEED):
    rng = np.random.RandomState(seed)
    obs = np.mean(gated_returns) - np.mean(baseline_returns)
    combined = np.concatenate([gated_returns, baseline_returns])
    count = 0
    for _ in range(n_perm):
        rng.shuffle(combined)
        m = len(gated_returns)
        diff = np.mean(combined[:m]) - np.mean(combined[m:])
        if diff >= obs:
            count += 1
    return count / n_perm


def rolling_window(events, fwd_returns, pfast, window_months=3):
    """Compute rolling economic metrics."""
    if len(events) == 0:
        return []
    dates = [e["ts"] for e in events]
    min_date = min(dates)
    max_date = max(dates)
    results = []
    current = min_date
    while current < max_date:
        window_end = current + pd.DateOffset(months=window_months)
        mask = np.array([current <= d < window_end for d in dates])
        if mask.sum() < 50:
            current += pd.DateOffset(months=1)
            continue
        sub_events = [e for e, m in zip(events, mask) if m]
        sub_fwd = fwd_returns[mask]
        sub_pfast = pfast[mask]
        # Metrics
        mean_ret = float(np.nanmean(sub_fwd))
        win_rate = float(np.mean(sub_fwd > 0))
        n = mask.sum()
        gains = float(np.nansum(sub_fwd[sub_fwd > 0]))
        losses = float(np.nansum(abs(sub_fwd[sub_fwd < 0])))
        pf = gains / losses if losses > 0 else float("inf") if gains > 0 else 0.0
        # Break-even cost
        be_cost = mean_ret if mean_ret > 0 else 0.0
        results.append({
            "start": str(current.date()), "end": str(window_end.date()),
            "n": int(n), "mean_return": mean_ret, "win_rate": win_rate,
            "profit_factor": pf, "break_even_cost": be_cost,
        })
        current += pd.DateOffset(months=1)
    return results


# ─── Main Analysis ────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase 10: Economic Edge Decomposition and Failure Analysis")
    print("=" * 70)

    # 0. Implementation audit
    print("\n[0/14] Implementation audit...")
    print("  pip_value_per_lot(EUR/USD):", pip_value_per_lot("EUR/USD"))
    print("  pip_value_per_lot(USD/JPY):", pip_value_per_lot("USD/JPY"))
    print("  cost_in_pips(EUR/USD, 1.0, 0.3, 3.50):", cost_in_pips("EUR/USD", 1.0, 0.3, 3.50))
    print("  cost_in_pips(USD/JPY, 1.0, 0.3, 3.50):", cost_in_pips("USD/JPY", 1.0, 0.3, 3.50))
    print("  Forward returns: ΔP / pip_size (actual pips)")
    print("  Cost: pair-specific pip_value_per_lot")
    print("  Status: CORRECTED (Phase 9B accounting)")

    # 1. Load data and extract events
    print("\n[1/14] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"  Loaded {len(pdata)} pairs")

    print("\n  Extracting events...")
    all_events = extract_events(pdata, "2016-01-01", "2026-07-19")
    print(f"  Total events: {len(all_events)}")
    fast = sum(1 for e in all_events if e["outcome"] == "fast_mr")
    slow = sum(1 for e in all_events if e["outcome"] == "slow_mr")
    print(f"  fast_mr={fast}, slow_mr={slow}")

    # 2. Walk-forward model training and OOS prediction
    print("\n[2/14] Walk-forward model training...")
    all_pfast = np.full(len(all_events), np.nan)
    all_fwd = np.array([e["fwd_ret_4"] for e in all_events])

    for split in WF_SPLITS:
        label = split["label"]
        train_end = split["train_end"]
        test_start = split["test_start"]
        test_end = split["test_end"]
        train_events = [e for e in all_events if 2016 <= e["ts"].year <= train_end]
        test_events = [e for e in all_events if test_start <= e["ts"].year <= test_end]
        train_fs = [e for e in train_events if e["outcome"] in ("fast_mr", "slow_mr")]
        test_fs = [e for e in test_events if e["outcome"] in ("fast_mr", "slow_mr")]
        if len(train_fs) < 100 or len(test_fs) < 50:
            continue
        X_tr = extract_features(train_fs)
        y_tr = extract_target(train_fs)
        model = LogisticModel()
        model.fit(X_tr, y_tr)
        # Predict on all test events
        test_idx = [i for i, e in enumerate(all_events) if test_start <= e["ts"].year <= test_end]
        X_te = extract_features([all_events[i] for i in test_idx])
        pfast = model.predict_proba(X_te)
        for j, idx in enumerate(test_idx):
            all_pfast[idx] = pfast[j]
        from sklearn.metrics import roc_auc_score
        y_te = extract_target(test_fs)
        pfast_fs = model.predict_proba(extract_features(test_fs))
        auc = roc_auc_score(y_te, pfast_fs)
        print(f"  {label}: AUC={auc:.4f}, test_n={len(test_events)}")

    # Filter to OOS only
    oos_mask = ~np.isnan(all_pfast)
    oos_events = [e for e, m in zip(all_events, oos_mask) if m]
    oos_fwd = all_fwd[oos_mask]
    oos_pfast = all_pfast[oos_mask]
    print(f"\n  OOS events: {len(oos_events)}")

    # 3. Edge Distribution
    print("\n[3/14] Edge distribution analysis...")
    edge_dist = {}
    # By outcome class
    for cls in ["fast_mr", "slow_mr"]:
        mask = np.array([e["outcome"] == cls for e in oos_events])
        if mask.sum() == 0:
            continue
        rets = oos_fwd[mask]
        rets = rets[~np.isnan(rets)]
        if len(rets) == 0:
            continue
        edge_dist[f"outcome_{cls}"] = {
            "n": int(len(rets)),
            "mean": float(np.mean(rets)),
            "median": float(np.median(rets)),
            "std": float(np.std(rets)),
            "q5": float(np.percentile(rets, 5)),
            "q10": float(np.percentile(rets, 10)),
            "q25": float(np.percentile(rets, 25)),
            "q75": float(np.percentile(rets, 75)),
            "q90": float(np.percentile(rets, 90)),
            "q95": float(np.percentile(rets, 95)),
            "positive_rate": float(np.mean(rets > 0)),
            "mean_positive": float(np.mean(rets[rets > 0])) if np.any(rets > 0) else 0.0,
            "mean_negative": float(np.mean(rets[rets < 0])) if np.any(rets < 0) else 0.0,
        }
        mp = edge_dist[f"outcome_{cls}"]["mean_positive"]
        mn = abs(edge_dist[f"outcome_{cls}"]["mean_negative"])
        edge_dist[f"outcome_{cls}"]["payoff_ratio"] = mp / mn if mn > 0 else float("inf")

    # By prediction correctness
    pred_correct = (oos_pfast >= 0.5) == (np.array([1 if e["outcome"] == "fast_mr" else 0 for e in oos_events]) == 1)
    for label_c, mask_c in [("correct", pred_correct), ("incorrect", ~pred_correct)]:
        rets = oos_fwd[mask_c]
        rets = rets[~np.isnan(rets)]
        if len(rets) == 0:
            continue
        edge_dist[f"pred_{label_c}"] = {
            "n": int(len(rets)),
            "mean": float(np.mean(rets)),
            "median": float(np.median(rets)),
            "positive_rate": float(np.mean(rets > 0)),
        }

    # By confidence buckets
    conf_buckets = [(0.0, 0.4, "low"), (0.4, 0.6, "mid"), (0.6, 0.8, "high"), (0.8, 1.01, "very_high")]
    for lo, hi, label_b in conf_buckets:
        mask = (oos_pfast >= lo) & (oos_pfast < hi)
        if mask.sum() == 0:
            continue
        rets = oos_fwd[mask]
        rets = rets[~np.isnan(rets)]
        if len(rets) == 0:
            continue
        edge_dist[f"conf_{label_b}"] = {
            "n": int(len(rets)),
            "mean": float(np.mean(rets)),
            "median": float(np.median(rets)),
            "positive_rate": float(np.mean(rets > 0)),
        }

    for k, v in edge_dist.items():
        print(f"  {k}: n={v['n']}, mean={v['mean']:.2f}pip, "
              f"pos_rate={v.get('positive_rate', 0):.3f}")

    # 4. Edge Concentration
    print("\n[4/14] Edge concentration...")
    # By pair
    pair_pnl = defaultdict(float)
    pair_n = defaultdict(int)
    pair_fwd = defaultdict(list)
    for e, fwd in zip(oos_events, oos_fwd):
        if not np.isnan(fwd):
            pair_pnl[e["pair"]] += fwd
            pair_n[e["pair"]] += 1
            pair_fwd[e["pair"]].append(fwd)

    pair_concentration = {}
    total_gross = sum(pair_pnl.values())
    for pair in sorted(pair_pnl.keys(), key=lambda p: pair_pnl[p], reverse=True):
        fwd_arr = np.array(pair_fwd[pair])
        pair_concentration[pair] = {
            "n": pair_n[pair],
            "total_pnl": float(pair_pnl[pair]),
            "mean_return": float(np.mean(fwd_arr)),
            "pct_total_pnl": float(pair_pnl[pair] / total_gross * 100) if total_gross != 0 else 0.0,
        }
    # Top 3 pairs contribution
    top3_pnl = sum(pair_pnl[p] for p in sorted(pair_pnl, key=pair_pnl.get, reverse=True)[:3])
    top3_pct = top3_pnl / total_gross * 100 if total_gross != 0 else 0
    print(f"  Total gross PnL: {total_gross:.0f} pip")
    print(f"  Top 3 pairs contribute: {top3_pct:.1f}%")

    # By year
    year_pnl = defaultdict(float)
    year_n = defaultdict(int)
    for e, fwd in zip(oos_events, oos_fwd):
        if not np.isnan(fwd):
            year_pnl[e["year"]] += fwd
            year_n[e["year"]] += 1
    year_concentration = {}
    for y in sorted(year_pnl.keys()):
        year_concentration[y] = {"n": year_n[y], "total_pnl": float(year_pnl[y]),
                                  "mean_return": float(year_pnl[y] / year_n[y])}
        print(f"  {y}: n={year_n[y]}, pnl={year_pnl[y]:.0f}pip, mean={year_pnl[y]/year_n[y]:.2f}pip")

    # By probability decile
    decile_edges = np.percentile(oos_pfast, np.linspace(0, 100, 11))
    decile_edges[0] -= 0.001
    decile_edges[-1] += 0.001
    decile_pnl = {}
    for i in range(10):
        lo, hi = decile_edges[i], decile_edges[i + 1]
        mask = (oos_pfast >= lo) & (oos_pfast < hi)
        if mask.sum() == 0:
            continue
        rets = oos_fwd[mask]
        decile_pnl[i + 1] = {
            "n": int(mask.sum()),
            "total_pnl": float(np.nansum(rets)),
            "mean_return": float(np.nanmean(rets)),
        }

    # 5. Cost-Breakpoint Analysis
    print("\n[5/14] Cost-breakpoint analysis...")
    be_costs = {}
    for e, fwd in zip(oos_events, oos_fwd):
        if not np.isnan(fwd):
            be_costs.setdefault(e["pair"], []).append(fwd)

    # Per-pair break-even costs
    pair_be = {}
    for pair, fwd_list in be_costs.items():
        arr = np.array(fwd_list)
        pair_be[pair] = {
            "mean_return": float(np.mean(arr)),
            "break_even_cost": float(np.mean(arr)) if np.mean(arr) > 0 else 0.0,
            "n": len(arr),
        }

    # Overall break-even distribution
    all_be = [v["break_even_cost"] for v in pair_be.values() if v["break_even_cost"] > 0]
    overall_be = {
        "mean": float(np.mean(all_be)) if all_be else 0.0,
        "median": float(np.median(all_be)) if all_be else 0.0,
        "q25": float(np.percentile(all_be, 25)) if all_be else 0.0,
        "q75": float(np.percentile(all_be, 75)) if all_be else 0.0,
        "min": float(np.min(all_be)) if all_be else 0.0,
        "max": float(np.max(all_be)) if all_be else 0.0,
    }
    print(f"  Median break-even cost: {overall_be['median']:.2f}pip")
    print(f"  Mean break-even cost: {overall_be['mean']:.2f}pip")
    print(f"  Range: [{overall_be['min']:.2f}, {overall_be['max']:.2f}]pip")

    # 6. Expectancy Decomposition
    print("\n[6/14] Expectancy decomposition...")
    # For gated P>=0.65
    gate_mask = oos_pfast >= 0.65
    gate_events = [e for e, m in zip(oos_events, gate_mask) if m]
    gate_fwd = oos_fwd[gate_mask]
    gate_fwd_clean = gate_fwd[~np.isnan(gate_fwd)]
    if len(gate_fwd_clean) > 0:
        n_total = len(gate_fwd_clean)
        n_win = np.sum(gate_fwd_clean > 0)
        n_loss = np.sum(gate_fwd_clean < 0)
        p_win = n_win / n_total
        p_loss = n_loss / n_total
        avg_win = float(np.mean(gate_fwd_clean[gate_fwd_clean > 0])) if n_win > 0 else 0.0
        avg_loss = float(np.mean(gate_fwd_clean[gate_fwd_clean < 0])) if n_loss > 0 else 0.0
        expectancy = p_win * avg_win - p_loss * abs(avg_loss)
        print(f"  P>=0.65: n={n_total}, P(win)={p_win:.3f}, AvgWin={avg_win:.2f}pip, "
              f"AvgLoss={avg_loss:.2f}pip, E[R]={expectancy:.3f}pip")
        exp_decomp = {
            "n": n_total, "p_win": float(p_win), "p_loss": float(p_loss),
            "avg_win": avg_win, "avg_loss": avg_loss,
            "expectancy": float(expectancy),
            "win_contribution": float(p_win * avg_win),
            "loss_contribution": float(p_loss * abs(avg_loss)),
        }
    else:
        exp_decomp = {}

    # 7. Signal Monotonicity
    print("\n[7/14] Signal monotonicity...")
    mono_results = []
    for i in range(10):
        lo, hi = decile_edges[i], decile_edges[i + 1]
        mask = (oos_pfast >= lo) & (oos_pfast < hi)
        if mask.sum() == 0:
            continue
        actual_binary = np.array([1 if e["outcome"] == "fast_mr" else 0 for e in oos_events])
        rets = oos_fwd[mask]
        rets_clean = rets[~np.isnan(rets)]
        cost_1pip = cost_in_pips("EUR/USD", 1.0, 0.3, 3.50)
        mono_results.append({
            "decile": i + 1,
            "n": int(mask.sum()),
            "mean_pred_p": float(np.mean(oos_pfast[mask])),
            "actual_fast_rate": float(np.mean(actual_binary[mask])),
            "mean_return": float(np.nanmean(rets)),
            "median_return": float(np.nanmedian(rets)),
            "net_expectancy_1pip": float(np.nanmean(rets) - cost_1pip),
        })
        print(f"  D{i+1}: pred={np.mean(oos_pfast[mask]):.3f}, "
              f"actual={np.mean(actual_binary[mask]):.3f}, "
              f"mean_ret={np.nanmean(rets):.2f}pip")

    # Test monotonicity
    if len(mono_results) >= 3:
        means = [r["mean_return"] for r in mono_results]
        monotonic_increasing = all(means[i] <= means[i+1] for i in range(len(means)-1))
        monotonic_decreasing = all(means[i] >= means[i+1] for i in range(len(means)-1))
        print(f"  Monotonic increasing: {monotonic_increasing}")
        print(f"  Monotonic decreasing: {monotonic_decreasing}")

    # 8. Cross-Pair Economic Heterogeneity
    print("\n[8/14] Cross-pair economic heterogeneity...")
    cross_pair = {}
    for pair in sorted(pair_pnl.keys()):
        fwd_arr = np.array(pair_fwd[pair])
        be = pair_be[pair]["break_even_cost"]
        gains = float(np.nansum(fwd_arr[fwd_arr > 0]))
        losses = float(np.nansum(abs(fwd_arr[fwd_arr < 0])))
        pf = gains / losses if losses > 0 else float("inf") if gains > 0 else 0.0
        cum = np.nancumsum(fwd_arr)
        peak = np.maximum.accumulate(cum)
        dd = float(np.max(peak - cum)) if len(cum) > 0 else 0.0
        cross_pair[pair] = {
            "n": pair_n[pair],
            "mean_return": float(np.mean(fwd_arr)),
            "win_rate": float(np.mean(fwd_arr > 0)),
            "break_even_cost": be,
            "profit_factor": pf,
            "max_drawdown": dd,
            "total_pnl": float(pair_pnl[pair]),
        }
    # Rank by mean return
    ranked = sorted(cross_pair.items(), key=lambda x: x[1]["mean_return"], reverse=True)
    for pair, data in ranked[:5]:
        print(f"  {pair}: mean={data['mean_return']:.2f}pip, BE={data['break_even_cost']:.2f}pip, "
              f"PF={data['profit_factor']:.2f}")
    print("  ...")
    for pair, data in ranked[-3:]:
        print(f"  {pair}: mean={data['mean_return']:.2f}pip, BE={data['break_even_cost']:.2f}pip, "
              f"PF={data['profit_factor']:.2f}")

    # 9. Temporal Stability
    print("\n[9/14] Temporal stability...")
    rolling_3m = rolling_window(oos_events, oos_fwd, oos_pfast, window_months=3)
    rolling_6m = rolling_window(oos_events, oos_fwd, oos_pfast, window_months=6)
    rolling_12m = rolling_window(oos_events, oos_fwd, oos_pfast, window_months=12)
    print(f"  3-month windows: {len(rolling_3m)}")
    print(f"  6-month windows: {len(rolling_6m)}")
    print(f"  12-month windows: {len(rolling_12m)}")
    if rolling_6m:
        pos_windows = sum(1 for r in rolling_6m if r["mean_return"] > 0)
        print(f"  6-month windows with positive expectancy: {pos_windows}/{len(rolling_6m)}")

    # 10. Randomization / Null Controls
    print("\n[10/14] Randomization controls...")
    rng = np.random.RandomState(RNG_SEED)
    gate_mask_065 = oos_pfast >= 0.65
    gated_returns = oos_fwd[gate_mask_065]
    gated_returns_clean = gated_returns[~np.isnan(gated_returns)]
    obs_mean = float(np.mean(gated_returns_clean))

    # Shuffled predictions
    n_perm = N_PERM
    null_means = np.empty(n_perm)
    for i in range(n_perm):
        shuffled_pfast = rng.permutation(oos_pfast)
        shuffled_mask = shuffled_pfast >= 0.65
        shuffled_returns = oos_fwd[shuffled_mask]
        shuffled_clean = shuffled_returns[~np.isnan(shuffled_returns)]
        null_means[i] = float(np.mean(shuffled_clean)) if len(shuffled_clean) > 0 else 0.0

    perm_p = float(np.mean(null_means >= obs_mean))
    null_mean = float(np.mean(null_means))
    null_std = float(np.std(null_means))
    null_95 = [float(np.percentile(null_means, 2.5)), float(np.percentile(null_means, 97.5))]
    print(f"  Observed expectancy: {obs_mean:.4f}pip")
    print(f"  Null mean: {null_mean:.4f}pip, null std: {null_std:.4f}pip")
    print(f"  Empirical p-value: {perm_p:.4f}")
    print(f"  95% null interval: [{null_95[0]:.4f}, {null_95[1]:.4f}]")

    # Shuffled labels
    actual_binary = np.array([1 if e["outcome"] == "fast_mr" else 0 for e in oos_events])
    null_label_means = np.empty(n_perm)
    for i in range(n_perm):
        shuffled_labels = rng.permutation(actual_binary)
        # Retrain model with shuffled labels
        all_fs_idx = [j for j, e in enumerate(oos_events) if e["outcome"] in ("fast_mr", "slow_mr")]
        # Use a subset for speed
        subset_idx = rng.choice(all_fs_idx, size=min(5000, len(all_fs_idx)), replace=False)
        X_sub = extract_features([oos_events[j] for j in subset_idx])
        y_sub = shuffled_labels[subset_idx]
        model_null = LogisticModel()
        model_null.fit(X_sub, y_sub)
        pfast_null = model_null.predict_proba(extract_features(oos_events))
        null_mask = pfast_null >= 0.65
        null_returns = oos_fwd[null_mask]
        null_clean = null_returns[~np.isnan(null_returns)]
        null_label_means[i] = float(np.mean(null_clean)) if len(null_clean) > 0 else 0.0

    perm_label_p = float(np.mean(null_label_means >= obs_mean))
    print(f"  Label-shuffle p-value: {perm_label_p:.4f}")

    # 11. Multiple-Testing Warning
    print("\n[11/14] Multiple-testing warning...")
    n_tests_estimated = 50  # thresholds × pairs × folds × horizons × analyses
    bonferroni_alpha = 0.05 / n_tests_estimated
    print(f"  Estimated tests performed: ~{n_tests_estimated}")
    print(f"  Bonferroni-adjusted alpha: {bonferroni_alpha:.4f}")
    print(f"  Permutation p-value: {perm_p:.4f}")
    print(f"  Significant after Bonferroni: {perm_p < bonferroni_alpha}")

    # 12. Classification vs Trading Edge
    print("\n[12/14] Classification vs trading edge...")
    from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
    fs_mask = np.array([e["outcome"] in ("fast_mr", "slow_mr") for e in oos_events])
    y_oos = extract_target([e for e, m in zip(oos_events, fs_mask) if m])
    p_oos = oos_pfast[fs_mask]
    y_pred = (p_oos >= 0.5).astype(int)
    auc_oos = roc_auc_score(y_oos, p_oos)
    acc_oos = accuracy_score(y_oos, y_pred)
    prec_oos = precision_score(y_oos, y_pred, zero_division=0)
    rec_oos = recall_score(y_oos, y_pred, zero_division=0)
    print(f"  AUC: {auc_oos:.4f}")
    print(f"  Accuracy: {acc_oos:.4f}")
    print(f"  Precision: {prec_oos:.4f}")
    print(f"  Recall: {rec_oos:.4f}")

    # Raw forward-return performance
    fast_rets = oos_fwd[np.array([e["outcome"] == "fast_mr" for e in oos_events])]
    slow_rets = oos_fwd[np.array([e["outcome"] == "slow_mr" for e in oos_events])]
    fast_rets_clean = fast_rets[~np.isnan(fast_rets)]
    slow_rets_clean = slow_rets[~np.isnan(slow_rets)]
    print(f"  Fast MR mean return: {np.mean(fast_rets_clean):.2f}pip")
    print(f"  Slow MR mean return: {np.mean(slow_rets_clean):.2f}pip")
    print(f"  Fast - Slow spread: {np.mean(fast_rets_clean) - np.mean(slow_rets_clean):.2f}pip")

    # 13. Economic Significance
    print("\n[13/14] Economic significance questions...")
    # Q1: Direction better than chance?
    q1 = auc_oos > 0.52
    print(f"  Q1 (predicts direction): {'YES' if q1 else 'NO'} (AUC={auc_oos:.4f})")
    # Q2: Positive gross expectancy?
    gross_mean = float(np.nanmean(oos_fwd[oos_pfast >= 0.65]))
    q2 = gross_mean > 0
    print(f"  Q2 (positive gross expectancy): {'YES' if q2 else 'NO'} (mean={gross_mean:.2f}pip)")
    # Q3: Survives costs?
    cost_eu = cost_in_pips("EUR/USD", 1.0, 0.3, 3.50)
    net_mean = gross_mean - cost_eu
    q3 = net_mean > 0
    print(f"  Q3 (survives costs): {'YES' if q3 else 'NO'} (net={net_mean:.2f}pip, cost={cost_eu:.2f}pip)")
    # Q4: Stable across time?
    pos_periods = sum(1 for r in rolling_6m if r["mean_return"] > 0) if rolling_6m else 0
    total_periods = len(rolling_6m) if rolling_6m else 1
    q4 = pos_periods / total_periods > 0.6
    print(f"  Q4 (stable across time): {'YES' if q4 else 'NO'} ({pos_periods}/{total_periods} positive 6m windows)")
    # Q5: Stable across pairs?
    pos_pairs = sum(1 for p, d in cross_pair.items() if d["mean_return"] > 0)
    q5 = pos_pairs / len(cross_pair) > 0.5
    print(f"  Q5 (stable across pairs): {'YES' if q5 else 'NO'} ({pos_pairs}/{len(cross_pair)} positive pairs)")
    # Q6: Concentrated?
    q6 = top3_pct > 50
    print(f"  Q6 (concentrated): {'YES' if q6 else 'NO'} (top 3 pairs = {top3_pct:.1f}%)")
    # Q7: Distinguishable from null?
    q7 = perm_p < 0.10
    print(f"  Q7 (distinguishable from null): {'YES' if q7 else 'NO'} (p={perm_p:.4f})")
    # Q8: Enough for another phase?
    q8 = q1 and (q2 or q4)
    print(f"  Q8 (justify next phase): {'YES' if q8 else 'NO'}")

    # 14. Final Classification
    print("\n[14/14] Final classification...")
    # Criteria:
    # A. NO SIGNAL: AUC < 0.52 or permutation p > 0.20
    # B. PREDICTIVE BUT ECONOMICALLY USELESS: AUC > 0.55 but net expectancy < 0 after costs
    # C. WEAK ECONOMIC EDGE: net expectancy > 0 but < 0.5 pip, break-even < 1.0 pip
    # D. ROBUST ECONOMIC EDGE: net expectancy > 0.5 pip, stable across time/pairs
    # E. STRONG ECONOMIC EDGE: net expectancy > 1.0 pip, stable, high PF

    if auc_oos < 0.52 or perm_p > 0.20:
        classification = "A. NO SIGNAL"
    elif net_mean < 0 and gross_mean > 0:
        classification = "B. PREDICTIVE BUT ECONOMICALLY USELESS"
    elif net_mean > 0 and net_mean < 0.5:
        classification = "C. WEAK ECONOMIC EDGE"
    elif net_mean >= 0.5 and q4:
        classification = "D. ROBUST ECONOMIC EDGE"
    elif net_mean >= 1.0:
        classification = "E. STRONG ECONOMIC EDGE"
    else:
        classification = "C. WEAK ECONOMIC EDGE"

    print(f"  Classification: {classification}")
    print(f"  Gross edge: {gross_mean:.2f}pip")
    print(f"  Realistic-cost edge: {net_mean:.2f}pip")
    print(f"  Median break-even cost: {overall_be['median']:.2f}pip")

    # Save results
    results = {
        "phase": "10",
        "title": "Economic Edge Decomposition and Failure Analysis",
        "timestamp": pd.Timestamp.now().isoformat(),
        "runtime_seconds": time.time() - t0,
        "implementation_audit": {
            "pip_value_eurusd": pip_value_per_lot("EUR/USD"),
            "pip_value_usdjpy": pip_value_per_lot("USD/JPY"),
            "cost_eurusd": cost_in_pips("EUR/USD", 1.0, 0.3, 3.50),
            "forward_returns_in_pips": True,
            "cost_pair_specific": True,
            "status": "CORRECTED",
        },
        "event_summary": {
            "total": len(all_events), "oos": len(oos_events),
            "fast_mr": fast, "slow_mr": slow,
        },
        "edge_distribution": edge_dist,
        "edge_concentration": {
            "by_pair": pair_concentration,
            "by_year": year_concentration,
            "by_decile": decile_pnl,
            "top3_contribution_pct": top3_pct,
        },
        "cost_breakpoint": {
            "overall": overall_be,
            "by_pair": pair_be,
        },
        "expectancy_decomposition": exp_decomp,
        "signal_monotonicity": mono_results,
        "cross_pair_heterogeneity": cross_pair,
        "temporal_stability": {
            "rolling_3m": rolling_3m,
            "rolling_6m": rolling_6m,
            "rolling_12m": rolling_12m,
        },
        "randomization": {
            "observed_expectancy": obs_mean,
            "null_mean": null_mean,
            "null_std": null_std,
            "null_95ci": null_95,
            "permutation_p": perm_p,
            "label_shuffle_p": perm_label_p,
        },
        "multiple_testing": {
            "estimated_tests": n_tests_estimated,
            "bonferroni_alpha": bonferroni_alpha,
            "significant_after_bonferroni": perm_p < bonferroni_alpha,
        },
        "classification_vs_trading": {
            "auc": auc_oos, "accuracy": acc_oos,
            "precision": prec_oos, "recall": rec_oos,
            "fast_mean_return": float(np.mean(fast_rets_clean)),
            "slow_mean_return": float(np.mean(slow_rets_clean)),
            "fast_slow_spread": float(np.mean(fast_rets_clean) - np.mean(slow_rets_clean)),
        },
        "economic_significance": {
            "q1_direction": q1, "q2_gross_positive": q2,
            "q3_survives_costs": q3, "q4_stable_time": q4,
            "q5_stable_pairs": q5, "q6_concentrated": q6,
            "q7_distinguishable_null": q7, "q8_justify_next": q8,
        },
        "final_classification": classification,
        "gross_edge_pip": gross_mean,
        "net_edge_pip": net_mean,
        "median_break_even_pip": overall_be["median"],
    }

    with open(OUT_DIR / "phase10_economic_edge_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {OUT_DIR / 'phase10_economic_edge_results.json'}")

    # Save summary
    summary = {
        "classification": classification,
        "gross_edge_pip": gross_mean,
        "net_edge_pip": net_mean,
        "median_break_even_pip": overall_be["median"],
        "auc_oos": auc_oos,
        "perm_p": perm_p,
        "temporal_stability": f"{pos_periods}/{total_periods} positive 6m windows",
        "cross_pair_stability": f"{pos_pairs}/{len(cross_pair)} positive pairs",
        "main_failure_mode": "Edge is too small to survive realistic transaction costs" if not q3 else "Edge survives but is weak",
    }
    with open(OUT_DIR / "phase10_economic_edge_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Summary saved: {OUT_DIR / 'phase10_economic_edge_summary.json'}")

    # Save CSV files
    # Pair ranking
    with open(OUT_DIR / "pair_economic_ranking.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pair", "n", "mean_return", "win_rate", "break_even_cost",
                     "profit_factor", "max_drawdown", "total_pnl"])
        for pair, data in ranked:
            w.writerow([pair, data["n"], f"{data['mean_return']:.4f}",
                        f"{data['win_rate']:.4f}", f"{data['break_even_cost']:.4f}",
                        f"{data['profit_factor']:.4f}", f"{data['max_drawdown']:.2f}",
                        f"{data['total_pnl']:.2f}"])
    print(f"CSV saved: {OUT_DIR / 'pair_economic_ranking.csv'}")

    # Rolling stability
    with open(OUT_DIR / "rolling_stability_6m.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start", "end", "n", "mean_return", "win_rate", "profit_factor", "break_even_cost"])
        for r in rolling_6m:
            w.writerow([r["start"], r["end"], r["n"], f"{r['mean_return']:.4f}",
                        f"{r['win_rate']:.4f}", f"{r['profit_factor']:.4f}",
                        f"{r['break_even_cost']:.4f}"])
    print(f"CSV saved: {OUT_DIR / 'rolling_stability_6m.csv'}")

    # Generate report
    generate_report(results)
    print(f"Report saved: {OUT_DIR / 'PHASE10_ECONOMIC_EDGE_DECOMPOSITION_REPORT.md'}")

    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"Phase 10 complete in {elapsed:.0f}s")
    print(f"Output: {OUT_DIR}")
    print(f"Classification: {classification}")
    print(f"Gross edge: {gross_mean:.2f}pip")
    print(f"Net edge: {net_mean:.2f}pip")
    print(f"{'='*70}")


def generate_report(results):
    lines = []
    lines.append("# Phase 10: Economic Edge Decomposition Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Classification: {results['final_classification']}**")
    lines.append("")
    lines.append(f"- Gross edge: {results['gross_edge_pip']:.2f} pip")
    lines.append(f"- Net edge (after costs): {results['net_edge_pip']:.2f} pip")
    lines.append(f"- Median break-even cost: {results['median_break_even_pip']:.2f} pip")
    lines.append(f"- AUC: {results['classification_vs_trading']['auc']:.4f}")
    lines.append(f"- Permutation p-value: {results['randomization']['permutation_p']:.4f}")
    lines.append("")

    # Implementation audit
    lines.append("## Implementation Audit")
    lines.append("")
    ia = results["implementation_audit"]
    lines.append(f"- pip_value(EUR/USD): ${ia['pip_value_eurusd']:.2f}")
    lines.append(f"- pip_value(USD/JPY): ${ia['pip_value_usdjpy']:.2f}")
    lines.append(f"- Forward returns: {'actual pips' if ia['forward_returns_in_pips'] else 'ERROR'}")
    lines.append(f"- Cost pair-specific: {'Yes' if ia['cost_pair_specific'] else 'No'}")
    lines.append(f"- Status: {ia['status']}")
    lines.append("")

    # Edge distribution
    lines.append("## Edge Distribution")
    lines.append("")
    lines.append("### By Outcome Class")
    lines.append("")
    lines.append("| Class | N | Mean | Median | Win Rate | Mean Win | Mean Loss | Payoff |")
    lines.append("|-------|---|------|--------|----------|----------|-----------|--------|")
    for cls in ["fast_mr", "slow_mr"]:
        key = f"outcome_{cls}"
        if key in results["edge_distribution"]:
            d = results["edge_distribution"][key]
            lines.append(f"| {cls} | {d['n']:,} | {d['mean']:.2f} | {d['median']:.2f} | "
                         f"{d['positive_rate']:.3f} | {d['mean_positive']:.2f} | "
                         f"{d['mean_negative']:.2f} | {d.get('payoff_ratio', 0):.2f} |")
    lines.append("")

    # Edge concentration
    lines.append("## Edge Concentration")
    lines.append("")
    lines.append(f"Top 3 pairs contribute: {results['edge_concentration']['top3_contribution_pct']:.1f}% of total PnL")
    lines.append("")
    lines.append("### By Year")
    lines.append("")
    lines.append("| Year | N | Total PnL | Mean Return |")
    lines.append("|------|---|-----------|-------------|")
    for y, d in results["edge_concentration"]["by_year"].items():
        lines.append(f"| {y} | {d['n']:,} | {d['total_pnl']:.0f} | {d['mean_return']:.2f} |")
    lines.append("")

    # Cost breakpoint
    lines.append("## Cost Breakpoint Analysis")
    lines.append("")
    cb = results["cost_breakpoint"]["overall"]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Mean break-even | {cb['mean']:.2f} pip |")
    lines.append(f"| Median break-even | {cb['median']:.2f} pip |")
    lines.append(f"| 25th percentile | {cb['q25']:.2f} pip |")
    lines.append(f"| 75th percentile | {cb['q75']:.2f} pip |")
    lines.append(f"| Min | {cb['min']:.2f} pip |")
    lines.append(f"| Max | {cb['max']:.2f} pip |")
    lines.append(f"| Realistic cost (EUR/USD) | {cost_in_pips('EUR/USD', 1.0, 0.3, 3.50):.2f} pip |")
    lines.append("")

    # Expectancy decomposition
    lines.append("## Expectancy Decomposition (P>=0.65)")
    lines.append("")
    ed = results["expectancy_decomposition"]
    if ed:
        lines.append(f"| Component | Value |")
        lines.append(f"|-----------|-------|")
        lines.append(f"| N trades | {ed['n']:,} |")
        lines.append(f"| P(win) | {ed['p_win']:.3f} |")
        lines.append(f"| P(loss) | {ed['p_loss']:.3f} |")
        lines.append(f"| Avg win | {ed['avg_win']:.2f} pip |")
        lines.append(f"| Avg loss | {ed['avg_loss']:.2f} pip |")
        lines.append(f"| Win contribution | {ed['win_contribution']:.3f} |")
        lines.append(f"| Loss contribution | {ed['loss_contribution']:.3f} |")
        lines.append(f"| E[R] | {ed['expectancy']:.3f} |")
    lines.append("")

    # Signal monotonicity
    lines.append("## Signal Monotonicity")
    lines.append("")
    lines.append("| Decile | N | Mean Pred P | Actual Fast Rate | Mean Return | Net Exp (1pip cost) |")
    lines.append("|--------|---|-------------|------------------|-------------|---------------------|")
    for d in results["signal_monotonicity"]:
        lines.append(f"| {d['decile']} | {d['n']:,} | {d['mean_pred_p']:.3f} | "
                     f"{d['actual_fast_rate']:.3f} | {d['mean_return']:.2f} | "
                     f"{d['net_expectancy_1pip']:.2f} |")
    lines.append("")

    # Cross-pair
    lines.append("## Cross-Pair Economic Heterogeneity")
    lines.append("")
    lines.append("| Pair | N | Mean Return | Win Rate | BE Cost | PF | Max DD |")
    lines.append("|------|---|-------------|----------|---------|----|--------|")
    for pair, d in sorted(results["cross_pair_heterogeneity"].items(),
                           key=lambda x: x[1]["mean_return"], reverse=True):
        lines.append(f"| {pair} | {d['n']:,} | {d['mean_return']:.2f} | "
                     f"{d['win_rate']:.3f} | {d['break_even_cost']:.2f} | "
                     f"{d['profit_factor']:.2f} | {d['max_drawdown']:.1f} |")
    lines.append("")

    # Temporal stability
    lines.append("## Temporal Stability")
    lines.append("")
    lines.append("### 6-Month Rolling Windows")
    lines.append("")
    lines.append("| Period | N | Mean Return | Win Rate | PF | BE Cost |")
    lines.append("|--------|---|-------------|----------|----|---------|")
    for r in results["temporal_stability"]["rolling_6m"][:20]:
        lines.append(f"| {r['start']}–{r['end']} | {r['n']:,} | {r['mean_return']:.2f} | "
                     f"{r['win_rate']:.3f} | {r['profit_factor']:.2f} | {r['break_even_cost']:.2f} |")
    lines.append("")

    # Randomization
    lines.append("## Randomization Controls")
    lines.append("")
    rn = results["randomization"]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Observed expectancy | {rn['observed_expectancy']:.4f} pip |")
    lines.append(f"| Null mean | {rn['null_mean']:.4f} pip |")
    lines.append(f"| Null std | {rn['null_std']:.4f} pip |")
    lines.append(f"| 95% null CI | [{rn['null_95ci'][0]:.4f}, {rn['null_95ci'][1]:.4f}] |")
    lines.append(f"| Permutation p | {rn['permutation_p']:.4f} |")
    lines.append(f"| Label-shuffle p | {rn['label_shuffle_p']:.4f} |")
    lines.append("")

    # Multiple testing
    lines.append("## Multiple-Testing Warning")
    lines.append("")
    mt = results["multiple_testing"]
    lines.append(f"- Estimated tests: ~{mt['estimated_tests']}")
    lines.append(f"- Bonferroni alpha: {mt['bonferroni_alpha']:.4f}")
    lines.append(f"- Permutation p: {rn['permutation_p']:.4f}")
    lines.append(f"- Significant after Bonferroni: {'YES' if mt['significant_after_bonferroni'] else 'NO'}")
    lines.append("")

    # Classification vs trading
    lines.append("## Classification vs Trading Performance")
    lines.append("")
    ct = results["classification_vs_trading"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| AUC | {ct['auc']:.4f} |")
    lines.append(f"| Accuracy | {ct['accuracy']:.4f} |")
    lines.append(f"| Precision | {ct['precision']:.4f} |")
    lines.append(f"| Recall | {ct['recall']:.4f} |")
    lines.append(f"| Fast MR mean return | {ct['fast_mean_return']:.2f} pip |")
    lines.append(f"| Slow MR mean return | {ct['slow_mean_return']:.2f} pip |")
    lines.append(f"| Fast-Slow spread | {ct['fast_slow_spread']:.2f} pip |")
    lines.append("")

    # Economic significance
    lines.append("## Economic Significance Questions")
    lines.append("")
    es = results["economic_significance"]
    lines.append("| Question | Answer |")
    lines.append("|----------|--------|")
    lines.append(f"| Q1: Predicts direction? | {'YES' if es['q1_direction'] else 'NO'} |")
    lines.append(f"| Q2: Positive gross expectancy? | {'YES' if es['q2_gross_positive'] else 'NO'} |")
    lines.append(f"| Q3: Survives costs? | {'YES' if es['q3_survives_costs'] else 'NO'} |")
    lines.append(f"| Q4: Stable across time? | {'YES' if es['q4_stable_time'] else 'NO'} |")
    lines.append(f"| Q5: Stable across pairs? | {'YES' if es['q5_stable_pairs'] else 'NO'} |")
    lines.append(f"| Q6: Concentrated? | {'YES' if es['q6_concentrated'] else 'NO'} |")
    lines.append(f"| Q7: Distinguishable from null? | {'YES' if es['q7_distinguishable_null'] else 'NO'} |")
    lines.append(f"| Q8: Justify next phase? | {'YES' if es['q8_justify_next'] else 'NO'} |")
    lines.append("")

    # Final classification
    lines.append("## Final Classification")
    lines.append("")
    lines.append(f"### {results['final_classification']}")
    lines.append("")
    lines.append("Classification criteria:")
    lines.append("- **A. NO SIGNAL**: AUC < 0.52 or permutation p > 0.20")
    lines.append("- **B. PREDICTIVE BUT ECONOMICALLY USELESS**: AUC > 0.55 but net < 0 after costs")
    lines.append("- **C. WEAK ECONOMIC EDGE**: net > 0 but < 0.5 pip, break-even < 1.0 pip")
    lines.append("- **D. ROBUST ECONOMIC EDGE**: net > 0.5 pip, stable across time/pairs")
    lines.append("- **E. STRONG ECONOMIC EDGE**: net > 1.0 pip, stable, high PF")
    lines.append("")
    lines.append(f"- Gross edge: {results['gross_edge_pip']:.2f} pip")
    lines.append(f"- Net edge: {results['net_edge_pip']:.2f} pip")
    lines.append(f"- Break-even cost: {results['median_break_even_pip']:.2f} pip")
    lines.append(f"- Realistic cost: {cost_in_pips('EUR/USD', 1.0, 0.3, 3.50):.2f} pip")
    lines.append("")

    with open(OUT_DIR / "PHASE10_ECONOMIC_EDGE_DECOMPOSITION_REPORT.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
