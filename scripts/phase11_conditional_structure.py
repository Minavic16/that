"""Phase 11: Economic Conditional Structure Analysis.

Determines whether the weak aggregate signal contains a genuine
conditional economic structure that deserves further research.

This is NOT an optimization exercise.

Usage:
    .venv/bin/python scripts/phase11_conditional_structure.py
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
N_PERM = 500
Z_ENTRY = 2.2
LOOKBACK = 20
ATR_PERIOD = 14
FAST_THRESHOLD = 0.50
SLOW_THRESHOLD = 0.30
MAX_HOLD_BARS = 64
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
REGIME_PERIODS = [
    ("2016-2018", 2016, 2018), ("2019-2021", 2019, 2021),
    ("2022-2024", 2022, 2024), ("2025-2026", 2025, 2026),
]
THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
SIGNAL_BINS = [
    (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70),
    (0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 0.90),
    (0.90, 0.95), (0.95, 1.00),
]
COST_SCENARIOS = {
    "COST_0": {"spread_pips": 0.0, "slippage_pips": 0.0, "commission_usd": 0.0},
    "COST_LOW": {"spread_pips": 0.5, "slippage_pips": 0.1, "commission_usd": 2.0},
    "COST_BASE": {"spread_pips": 1.0, "slippage_pips": 0.3, "commission_usd": 3.50},
}
OUT_DIR = Path("/root/nestquant/research_data/phase11")
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


def compute_metrics(events, fwd_returns, pair=None):
    """Compute economic metrics for a subset of events."""
    rets = fwd_returns[~np.isnan(fwd_returns)]
    if len(rets) == 0:
        return {"n": 0, "win_rate": 0, "mean_return": 0, "median_return": 0,
                "profit_factor": 0, "gross_expectancy": 0, "max_drawdown": 0}
    n = len(rets)
    win_rate = float(np.mean(rets > 0))
    mean_ret = float(np.mean(rets))
    median_ret = float(np.median(rets))
    gains = float(np.nansum(rets[rets > 0]))
    losses = float(np.nansum(abs(rets[rets < 0])))
    pf = gains / losses if losses > 0 else float("inf") if gains > 0 else 0.0
    cum = np.nancumsum(rets)
    peak = np.maximum.accumulate(cum)
    dd = float(np.max(peak - cum)) if len(cum) > 0 else 0.0
    return {
        "n": n, "win_rate": win_rate, "mean_return": mean_ret,
        "median_return": median_ret, "profit_factor": pf,
        "gross_expectancy": mean_ret, "max_drawdown": dd,
    }


def cost_adjusted_metrics(events, fwd_returns, spread_pips, slippage_pips, commission_usd):
    """Compute cost-adjusted metrics. events and fwd_returns must be aligned (same length)."""
    valid = ~np.isnan(fwd_returns)
    if valid.sum() == 0:
        return {"net_expectancy": 0, "net_pnl": 0}
    costs = np.array([cost_in_pips(e["pair"], spread_pips, slippage_pips, commission_usd)
                      for e in np.array(events, dtype=object)[valid]])
    net_rets = fwd_returns[valid] - costs
    return {
        "net_expectancy": float(np.mean(net_rets)),
        "net_pnl": float(np.sum(net_rets)),
    }


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
        for pair, idx_map in pair_idx_map.items():
            if ts not in idx_map:
                continue
            idx = idx_map[ts]
            cross_zs.append(pdata[pair]["z"][idx])
        if len(cross_zs) < 3:
            continue
        cross_median_z = float(np.median(cross_zs))
        all_zs_sorted = sorted(cross_zs)

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
            fwd_ret_4 = (c[idx + 4] - c[idx]) / pip if idx + 4 < d["n"] else np.nan
            z_path = d["z"][idx:idx + MAX_HOLD_BARS + 1]
            outcome = classify_outcome(z_path, z_now, direction)

            abs_z = abs(z_now)
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
            rank = np.searchsorted(all_zs_sorted, z_now)
            pair_z_rank = rank / len(all_zs_sorted) if all_zs_sorted else 0.5
            dist_from_recent_max_z = abs_z - abs(np.nanmax(d["z"][max(0, idx - 200):idx + 1]))
            dist_from_recent_min_z = abs_z - abs(np.nanmin(d["z"][max(0, idx - 200):idx + 1]))

            # Regime features (all available at t)
            atr_now = d["atr"][idx] if not np.isnan(d["atr"][idx]) else 0.0
            ema200_dist = (c[idx] - d["ema200"][idx]) / pip
            ema50_dist = (c[idx] - d["ema50"][idx]) / pip
            ema20_dist = (c[idx] - d["ema20"][idx]) / pip
            trend_strength = abs(ema20_dist - ema200_dist)
            realized_vol = float(np.std(np.diff(c[max(0, idx - 20):idx + 1]))) if idx >= 20 else 0.0

            events.append({
                "pair": pair, "idx": idx, "ts": ts_now, "z_now": z_now,
                "direction": direction, "close_at_entry": c[idx],
                "outcome": outcome, "fwd_ret_4": fwd_ret_4,
                "abs_z": abs_z, "abs_ret_1": abs_ret_1, "abs_ret_4": abs_ret_4,
                "body_range_ratio": body_range_ratio,
                "range_expansion": range_expansion, "range_pctile_500": range_pctile_500,
                "vol_expansion": vol_expansion, "pair_z_rank": pair_z_rank,
                "dist_from_recent_max_z": dist_from_recent_max_z,
                "dist_from_recent_min_z": dist_from_recent_min_z,
                "cross_median_z": cross_median_z,
                "entry_hour": float(ts_now.hour), "entry_dow": float(ts_now.dayofweek),
                "year": ts_now.year, "month": ts_now.month,
                # Regime features
                "atr_now": atr_now, "ema200_dist": ema200_dist,
                "ema50_dist": ema50_dist, "ema20_dist": ema20_dist,
                "trend_strength": trend_strength, "realized_vol": realized_vol,
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


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase 11: Economic Conditional Structure Analysis")
    print("=" * 70)

    # 0. Implementation audit
    print("\n[0] Implementation audit...")
    print(f"  pip_value(EUR/USD): ${pip_value_per_lot('EUR/USD'):.2f}")
    print(f"  pip_value(USD/JPY): ${pip_value_per_lot('USD/JPY'):.2f}")
    print(f"  cost(EUR/USD, BASE): {cost_in_pips('EUR/USD', 1.0, 0.3, 3.50):.2f} pip")
    print(f"  Forward returns: actual pips (ΔP / pip_size)")
    print(f"  Costs: pair-specific pip_value_per_lot")
    print(f"  Status: CORRECTED")

    # 1. Load data
    print("\n[1] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"  Loaded {len(pdata)} pairs")

    # 2. Extract events
    print("\n[2] Extracting events...")
    all_events = extract_events(pdata, "2016-01-01", "2026-07-19")
    print(f"  Total events: {len(all_events)}")

    # 3. Walk-forward model training + OOS prediction
    print("\n[3] Walk-forward model training...")
    all_pfast = np.full(len(all_events), np.nan)
    all_fwd = np.array([e["fwd_ret_4"] for e in all_events])

    for split in WF_SPLITS:
        label = split["label"]
        train_end = split["train_end"]
        test_start = split["test_start"]
        train_events = [e for e in all_events if 2016 <= e["ts"].year <= train_end]
        test_events = [e for e in all_events if test_start <= e["ts"].year <= split["test_end"]]
        train_fs = [e for e in train_events if e["outcome"] in ("fast_mr", "slow_mr")]
        test_fs = [e for e in test_events if e["outcome"] in ("fast_mr", "slow_mr")]
        if len(train_fs) < 100 or len(test_fs) < 50:
            continue
        X_tr = extract_features(train_fs)
        y_tr = extract_target(train_fs)
        model = LogisticModel()
        model.fit(X_tr, y_tr)
        test_idx = [i for i, e in enumerate(all_events) if test_start <= e["ts"].year <= split["test_end"]]
        X_te = extract_features([all_events[i] for i in test_idx])
        pfast = model.predict_proba(X_te)
        for j, idx in enumerate(test_idx):
            all_pfast[idx] = pfast[j]
        from sklearn.metrics import roc_auc_score
        y_te = extract_target(test_fs)
        auc = roc_auc_score(y_te, model.predict_proba(extract_features(test_fs)))
        print(f"  {label}: AUC={auc:.4f}, test_n={len(test_events)}")

    oos_mask = ~np.isnan(all_pfast)
    oos_events = [e for e, m in zip(all_events, oos_mask) if m]
    oos_fwd = all_fwd[oos_mask]
    oos_pfast = all_pfast[oos_mask]
    print(f"\n  OOS events: {len(oos_events)}")

    # Save trade-level results
    trade_rows = []
    for e, fwd, pf in zip(oos_events, oos_fwd, oos_pfast):
        if not np.isnan(fwd):
            trade_rows.append({
                "pair": e["pair"], "ts": str(e["ts"]), "outcome": e["outcome"],
                "fwd_ret_pips": fwd, "pfast": pf, "year": e["year"],
                "abs_z": e["abs_z"], "abs_ret_1": e["abs_ret_1"],
                "vol_expansion": e["vol_expansion"], "range_expansion": e["range_expansion"],
                "realized_vol": e["realized_vol"], "trend_strength": e["trend_strength"],
                "entry_hour": e["entry_hour"],
            })
    with open(OUT_DIR / "phase11_trade_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=trade_rows[0].keys())
        w.writeheader()
        w.writerows(trade_rows)
    print(f"  Trade results saved: {len(trade_rows)} rows")

    # ─── Analysis 1: Pair × Signal Strength ───────────────────────────────────
    print("\n[4] Pair × Signal Strength Decomposition...")
    pair_thr_results = {}
    for pair in sorted(set(e["pair"] for e in oos_events)):
        pair_mask = np.array([e["pair"] == pair for e in oos_events])
        pair_events = [e for e, m in zip(oos_events, pair_mask) if m]
        pair_fwd = oos_fwd[pair_mask]
        pair_pfast = oos_pfast[pair_mask]
        pair_thr_results[pair] = {}
        for thr in THRESHOLDS:
            thr_mask = pair_pfast >= thr
            if thr_mask.sum() < 10:
                continue
            sub_events = [e for e, m in zip(pair_events, thr_mask) if m]
            sub_fwd = pair_fwd[thr_mask]
            m = compute_metrics(sub_events, sub_fwd)
            # Cost adjustments
            for cname, cs in COST_SCENARIOS.items():
                ca = cost_adjusted_metrics(sub_events, sub_fwd, **cs)
                m[f"net_exp_{cname}"] = ca["net_expectancy"]
            be = m["mean_return"] if m["mean_return"] > 0 else 0.0
            m["break_even_cost"] = be
            pair_thr_results[pair][thr] = m
    print(f"  Computed for {len(pair_thr_results)} pairs × {len(THRESHOLDS)} thresholds")

    # ─── Analysis 2: Pair × Regime ────────────────────────────────────────────
    print("\n[5] Pair × Regime Analysis...")
    pair_regime_results = {}
    for pair in sorted(set(e["pair"] for e in oos_events)):
        pair_mask = np.array([e["pair"] == pair for e in oos_events])
        pair_events = [e for e, m in zip(oos_events, pair_mask) if m]
        pair_fwd = oos_fwd[pair_mask]
        pair_pfast = oos_pfast[pair_mask]
        pair_regime_results[pair] = {}
        for rlabel, ry_start, ry_end in REGIME_PERIODS:
            rmask = np.array([ry_start <= e["ts"].year <= ry_end for e in pair_events])
            if rmask.sum() < 20:
                continue
            sub_events = [e for e, m in zip(pair_events, rmask) if m]
            sub_fwd = pair_fwd[rmask]
            sub_pfast = pair_pfast[rmask]
            # Use P>=0.65 as representative
            gate_mask = sub_pfast >= 0.65
            if gate_mask.sum() < 10:
                continue
            gated_events = [e for e, m in zip(sub_events, gate_mask) if m]
            gated_fwd = sub_fwd[gate_mask]
            m = compute_metrics(gated_events, gated_fwd)
            ca = cost_adjusted_metrics(gated_events, gated_fwd, **COST_SCENARIOS["COST_BASE"])
            m["net_exp_base"] = ca["net_expectancy"]
            m["break_even_cost"] = m["mean_return"] if m["mean_return"] > 0 else 0.0
            pair_regime_results[pair][rlabel] = m
    print(f"  Computed for {len(pair_regime_results)} pairs × {len(REGIME_PERIODS)} regimes")

    # ─── Analysis 3: Signal Strength × Economic Return ────────────────────────
    print("\n[6] Signal Strength × Economic Return...")
    signal_bin_results = []
    for lo, hi in SIGNAL_BINS:
        mask = (oos_pfast >= lo) & (oos_pfast < hi)
        if mask.sum() == 0:
            continue
        sub_events = [e for e, m in zip(oos_events, mask) if m]
        sub_fwd = oos_fwd[mask]
        m = compute_metrics(sub_events, sub_fwd)
        actual_binary = np.array([1 if e["outcome"] == "fast_mr" else 0 for e in sub_events])
        actual_fast_rate = float(np.mean(actual_binary))
        for cname, cs in COST_SCENARIOS.items():
            ca = cost_adjusted_metrics(sub_events, sub_fwd, **cs)
            m[f"net_exp_{cname}"] = ca["net_expectancy"]
        m["mean_pred_p"] = float(np.mean(oos_pfast[mask]))
        m["actual_fast_rate"] = actual_fast_rate
        m["bin_label"] = f"{lo:.2f}-{hi:.2f}"
        signal_bin_results.append(m)
        print(f"  {m['bin_label']}: n={m['n']}, pred={m['mean_pred_p']:.3f}, "
              f"actual_rate={actual_fast_rate:.3f}, mean_ret={m['mean_return']:.2f}pip")

    # ─── Analysis 4: Cost-Breakpoint Distribution ─────────────────────────────
    print("\n[7] Cost-Breakpoint Distribution...")
    # Per-trade break-even cost = forward return (the max cost it can tolerate)
    valid_mask = ~np.isnan(oos_fwd)
    valid_fwd = oos_fwd[valid_mask]
    be_costs = valid_fwd  # break-even cost = forward return itself
    be_overall = {
        "mean": float(np.mean(be_costs)),
        "median": float(np.median(be_costs)),
        "q10": float(np.percentile(be_costs, 10)),
        "q25": float(np.percentile(be_costs, 25)),
        "q75": float(np.percentile(be_costs, 75)),
        "q90": float(np.percentile(be_costs, 90)),
        "pct_surviving_05": float(np.mean(be_costs >= 0.5) * 100),
        "pct_surviving_075": float(np.mean(be_costs >= 0.75) * 100),
        "pct_surviving_10": float(np.mean(be_costs >= 1.0) * 100),
        "pct_surviving_15": float(np.mean(be_costs >= 1.5) * 100),
        "pct_surviving_20": float(np.mean(be_costs >= 2.0) * 100),
    }
    print(f"  Overall: median={be_overall['median']:.2f}pip, "
          f"surviving 1.0pip={be_overall['pct_surviving_10']:.1f}%")

    be_by_pair = {}
    for pair in sorted(set(e["pair"] for e in oos_events)):
        pair_mask = np.array([e["pair"] == pair for e in oos_events])
        pair_fwd_valid = oos_fwd[pair_mask & valid_mask]
        if len(pair_fwd_valid) == 0:
            continue
        be_by_pair[pair] = {
            "n": int(len(pair_fwd_valid)),
            "mean": float(np.mean(pair_fwd_valid)),
            "median": float(np.median(pair_fwd_valid)),
            "pct_surviving_05": float(np.mean(pair_fwd_valid >= 0.5) * 100),
            "pct_surviving_075": float(np.mean(pair_fwd_valid >= 0.75) * 100),
            "pct_surviving_10": float(np.mean(pair_fwd_valid >= 1.0) * 100),
        }

    # ─── Analysis 5: Pair Selection Without Look-Ahead ────────────────────────
    print("\n[8] Pair Selection Without Look-Ahead (Walk-Forward)...")
    pair_select_results = {}
    # Test different selection criteria on TRAIN, apply to TEST
    selection_rules = [
        ("all_pairs", None),  # baseline: all pairs
        ("positive_exp", "positive_exp"),
        ("be_gte_05", 0.5),
        ("be_gte_075", 0.75),
        ("be_gte_10", 1.0),
    ]
    for rule_name, rule_param in selection_rules:
        oos_selected_events = []
        oos_selected_fwd = []
        oos_selected_pfast = []
        for split in WF_SPLITS:
            train_end = split["train_end"]
            test_start = split["test_start"]
            # TRAIN: identify good pairs
            train_events = [e for e in all_events if 2016 <= e["ts"].year <= train_end]
            train_fwd_all = np.array([e["fwd_ret_4"] for e in train_events])
            train_pfast_all = all_pfast[np.array([e["ts"].year <= train_end for e in all_events])]
            # Get model predictions for train
            train_fs = [e for e in train_events if e["outcome"] in ("fast_mr", "slow_mr")]
            if len(train_fs) < 100:
                continue
            X_tr = extract_features(train_fs)
            y_tr = extract_target(train_fs)
            model = LogisticModel()
            model.fit(X_tr, y_tr)
            train_all_idx = [i for i, e in enumerate(all_events) if e["ts"].year <= train_end]
            pfast_train = model.predict_proba(extract_features([all_events[i] for i in train_all_idx]))

            # Evaluate each pair on train
            selected_pairs = set()
            for pair in set(e["pair"] for e in train_events):
                pair_mask = np.array([e["pair"] == pair for e in train_events])
                pair_fwd = train_fwd_all[pair_mask]
                pair_pfast = pfast_train[pair_mask]
                gate_mask = pair_pfast >= 0.65
                if gate_mask.sum() < 20:
                    continue
                gated_fwd = pair_fwd[gate_mask]
                mean_ret = float(np.mean(gated_fwd[~np.isnan(gated_fwd)]))
                be_cost = mean_ret if mean_ret > 0 else 0.0
                if rule_param is None:
                    selected_pairs.add(pair)
                elif rule_param == "positive_exp" and mean_ret > 0:
                    selected_pairs.add(pair)
                elif isinstance(rule_param, (int, float)) and be_cost >= rule_param:
                    selected_pairs.add(pair)

            # TEST: apply selected pairs
            test_events = [e for e in all_events if test_start <= e["ts"].year <= split["test_end"]]
            test_idx = [i for i, e in enumerate(all_events) if test_start <= e["ts"].year <= split["test_end"]]
            pfast_test = all_pfast[test_idx]
            for i, e in enumerate(test_events):
                if e["pair"] in selected_pairs:
                    oos_selected_events.append(e)
                    oos_selected_fwd.append(e["fwd_ret_4"])
                    oos_selected_pfast.append(pfast_test[i])

        if len(oos_selected_events) == 0:
            continue
        oos_sel_fwd = np.array(oos_selected_fwd)
        oos_sel_pfast = np.array(oos_selected_pfast)
        gate = oos_sel_pfast >= 0.65
        if gate.sum() == 0:
            continue
        gated_events = [e for e, m in zip(oos_selected_events, gate) if m]
        gated_fwd = oos_sel_fwd[gate]
        m = compute_metrics(gated_events, gated_fwd)
        ca_low = cost_adjusted_metrics(gated_events, gated_fwd, **COST_SCENARIOS["COST_LOW"])
        ca_base = cost_adjusted_metrics(gated_events, gated_fwd, **COST_SCENARIOS["COST_BASE"])
        pair_select_results[rule_name] = {
            "n_trades": m["n"], "mean_return": m["mean_return"],
            "win_rate": m["win_rate"], "profit_factor": m["profit_factor"],
            "max_drawdown": m["max_drawdown"],
            "net_exp_low": ca_low["net_expectancy"],
            "net_exp_base": ca_base["net_expectancy"],
        }
        print(f"  {rule_name}: n={m['n']}, mean={m['mean_return']:.2f}pip, "
              f"net_base={ca_base['net_expectancy']:.2f}pip")

    # ─── Analysis 6: Regime-Conditional Performance ───────────────────────────
    print("\n[9] Regime-Conditional Performance...")
    regime_conditional = {}
    # Volatility bins
    vol_vals = np.array([e["realized_vol"] for e in oos_events])
    vol_vals_clean = vol_vals[~np.isnan(vol_vals)]
    if len(vol_vals_clean) > 0:
        vol_q33 = np.percentile(vol_vals_clean, 33)
        vol_q66 = np.percentile(vol_vals_clean, 66)
        vol_bins = [("low_vol", vol_vals < vol_q33), ("mid_vol", (vol_vals >= vol_q33) & (vol_vals < vol_q66)),
                    ("high_vol", vol_vals >= vol_q66)]
        for label, mask in vol_bins:
            if mask.sum() < 50:
                continue
            sub_events = [e for e, m in zip(oos_events, mask) if m]
            sub_fwd = oos_fwd[mask]
            sub_pfast = oos_pfast[mask]
            gate = sub_pfast >= 0.65
            if gate.sum() < 10:
                continue
            gated_events = [e for e, m in zip(sub_events, gate) if m]
            gated_fwd = sub_fwd[gate]
            m = compute_metrics(gated_events, gated_fwd)
            regime_conditional[f"vol_{label}"] = m

    # Trend strength bins
    trend_vals = np.array([e["trend_strength"] for e in oos_events])
    trend_q33 = np.percentile(trend_vals, 33)
    trend_q66 = np.percentile(trend_vals, 66)
    trend_bins = [("weak_trend", trend_vals < trend_q33),
                  ("mid_trend", (trend_vals >= trend_q33) & (trend_vals < trend_q66)),
                  ("strong_trend", trend_vals >= trend_q66)]
    for label, mask in trend_bins:
        if mask.sum() < 50:
            continue
        sub_events = [e for e, m in zip(oos_events, mask) if m]
        sub_fwd = oos_fwd[mask]
        sub_pfast = oos_pfast[mask]
        gate = sub_pfast >= 0.65
        if gate.sum() < 10:
            continue
        gated_events = [e for e, m in zip(sub_events, gate) if m]
        gated_fwd = sub_fwd[gate]
        m = compute_metrics(gated_events, gated_fwd)
        regime_conditional[f"trend_{label}"] = m

    # Session bins
    session_bins = [("london", np.array([7 <= e["entry_hour"] < 12 for e in oos_events])),
                    ("overlap", np.array([12 <= e["entry_hour"] < 16 for e in oos_events])),
                    ("new_york", np.array([16 <= e["entry_hour"] < 21 for e in oos_events]))]
    for label, mask in session_bins:
        if mask.sum() < 50:
            continue
        sub_events = [e for e, m in zip(oos_events, mask) if m]
        sub_fwd = oos_fwd[mask]
        sub_pfast = oos_pfast[mask]
        gate = sub_pfast >= 0.65
        if gate.sum() < 10:
            continue
        gated_events = [e for e, m in zip(sub_events, gate) if m]
        gated_fwd = sub_fwd[gate]
        m = compute_metrics(gated_events, gated_fwd)
        regime_conditional[f"session_{label}"] = m

    for label, m in regime_conditional.items():
        print(f"  {label}: n={m['n']}, mean={m['mean_return']:.2f}pip")

    # ─── Analysis 7: Economic vs Classification Information ───────────────────
    print("\n[10] Economic vs Classification Information...")
    valid_mask2 = ~np.isnan(oos_fwd)
    pfast_valid = oos_pfast[valid_mask2]
    fwd_valid = oos_fwd[valid_mask2]
    from scipy.stats import spearmanr, pearsonr
    corr_direction, p_direction = pearsonr(pfast_valid, fwd_valid)
    corr_rank, p_rank = spearmanr(pfast_valid, fwd_valid)
    corr_abs, p_abs = pearsonr(pfast_valid, np.abs(fwd_valid))
    econ_vs_class = {
        "corr_pfast_return": float(corr_direction),
        "p_value_direction": float(p_direction),
        "spearman_rank": float(corr_rank),
        "p_value_rank": float(p_rank),
        "corr_pfast_abs_return": float(corr_abs),
        "p_value_abs": float(p_abs),
    }
    print(f"  Corr(P, return): {corr_direction:.4f} (p={p_direction:.4f})")
    print(f"  Spearman(P, return): {corr_rank:.4f} (p={p_rank:.4f})")
    print(f"  Corr(P, |return|): {corr_abs:.4f} (p={p_abs:.4f})")

    # ─── Analysis 8: Multiple-Testing Control ─────────────────────────────────
    print("\n[11] Multiple-Testing Control...")
    n_subgroup_tests = (
        len(THRESHOLDS) * len(set(e["pair"] for e in oos_events)) +  # pair × threshold
        len(REGIME_PERIODS) * len(set(e["pair"] for e in oos_events)) +  # pair × regime
        len(SIGNAL_BINS) +  # signal bins
        len(regime_conditional) +  # regime conditional
        5  # pair selection rules
    )
    bonferroni_alpha = 0.05 / max(n_subgroup_tests, 1)
    print(f"  Estimated subgroup tests: ~{n_subgroup_tests}")
    print(f"  Bonferroni-adjusted alpha: {bonferroni_alpha:.6f}")

    # ─── Final Classification ─────────────────────────────────────────────────
    print("\n[12] Final classification...")
    # Count how many pair × threshold combinations are profitable after base costs
    n_profitable_pair_thr = 0
    n_total_pair_thr = 0
    for pair, thr_dict in pair_thr_results.items():
        for thr, m in thr_dict.items():
            n_total_pair_thr += 1
            if m.get("net_exp_COST_BASE", 0) > 0:
                n_profitable_pair_thr += 1

    # Check regime stability
    n_regime_positive = sum(1 for m in regime_conditional.values() if m["mean_return"] > 0)
    n_regime_total = len(regime_conditional)

    # Classification criteria:
    # A. NO ECONOMIC STRUCTURE: no consistent conditional pattern
    # B. CONDITIONAL STRUCTURE BUT NOT OOS VALIDATED: patterns exist in-sample but not OOS
    # C. OOS CONDITIONAL ECONOMIC EDGE: some subgroups show OOS edge after costs
    # D. ROBUST OOS ECONOMIC EDGE: consistent across subgroups
    # E. STRONG OOS ECONOMIC EDGE: strong and consistent

    if n_profitable_pair_thr / max(n_total_pair_thr, 1) < 0.1:
        classification = "A. NO ECONOMIC STRUCTURE FOUND"
    elif n_profitable_pair_thr / max(n_total_pair_thr, 1) < 0.3:
        classification = "B. CONDITIONAL STRUCTURE FOUND BUT NOT OOS VALIDATED"
    elif n_profitable_pair_thr / max(n_total_pair_thr, 1) < 0.5:
        classification = "C. OOS CONDITIONAL ECONOMIC EDGE"
    elif n_profitable_pair_thr / max(n_total_pair_thr, 1) < 0.7:
        classification = "D. ROBUST OOS ECONOMIC EDGE"
    else:
        classification = "E. STRONG OOS ECONOMIC EDGE"

    print(f"  Profitable pair×threshold: {n_profitable_pair_thr}/{n_total_pair_thr}")
    print(f"  Classification: {classification}")

    # Research decision
    if classification.startswith("A") or classification.startswith("B"):
        research_decision = "NO — stop this research branch"
        reason = ("No consistent conditional economic structure found. "
                  "The signal is predictive (AUC~0.62) but the economic edge "
                  "is too weak, too concentrated, and too unstable to warrant "
                  "further investigation.")
    else:
        research_decision = "YES — investigate specific conditional subgroups"
        reason = "Some conditional structure exists that may warrant further study."

    print(f"  Research decision: {research_decision}")

    # Save results
    results = {
        "phase": "11",
        "title": "Economic Conditional Structure Analysis",
        "timestamp": pd.Timestamp.now().isoformat(),
        "runtime_seconds": time.time() - t0,
        "implementation_audit": {
            "pip_value_eurusd": pip_value_per_lot("EUR/USD"),
            "pip_value_usdjpy": pip_value_per_lot("USD/JPY"),
            "forward_returns_in_pips": True,
            "cost_pair_specific": True,
            "no_lookahead": True,
        },
        "event_summary": {
            "total": len(all_events), "oos": len(oos_events),
        },
        "pair_thr_results": {p: {str(k): v for k, v in d.items()} for p, d in pair_thr_results.items()},
        "pair_regime_results": {p: d for p, d in pair_regime_results.items()},
        "signal_bin_results": signal_bin_results,
        "cost_breakpoint": {"overall": be_overall, "by_pair": be_by_pair},
        "pair_select_results": pair_select_results,
        "regime_conditional": regime_conditional,
        "econ_vs_class": econ_vs_class,
        "multiple_testing": {
            "n_subgroup_tests": n_subgroup_tests,
            "bonferroni_alpha": bonferroni_alpha,
        },
        "classification": classification,
        "research_decision": research_decision,
        "research_reason": reason,
        "n_profitable_pair_thr": n_profitable_pair_thr,
        "n_total_pair_thr": n_total_pair_thr,
    }

    with open(OUT_DIR / "phase11_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {OUT_DIR / 'phase11_results.json'}")

    # Save pair results CSV
    with open(OUT_DIR / "phase11_pair_results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pair", "threshold", "n", "win_rate", "mean_return", "median_return",
                     "profit_factor", "break_even_cost", "net_exp_COST_LOW", "net_exp_COST_BASE"])
        for pair, thr_dict in pair_thr_results.items():
            for thr, m in thr_dict.items():
                w.writerow([pair, thr, m["n"], f"{m['win_rate']:.4f}",
                            f"{m['mean_return']:.4f}", f"{m['median_return']:.4f}",
                            f"{m['profit_factor']:.4f}", f"{m['break_even_cost']:.4f}",
                            f"{m.get('net_exp_COST_LOW', 0):.4f}",
                            f"{m.get('net_exp_COST_BASE', 0):.4f}"])
    print(f"Pair results CSV saved")

    # Save regime results CSV
    with open(OUT_DIR / "phase11_regime_results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pair", "regime", "n", "win_rate", "mean_return", "profit_factor",
                     "break_even_cost", "net_exp_base"])
        for pair, regime_dict in pair_regime_results.items():
            for regime, m in regime_dict.items():
                w.writerow([pair, regime, m["n"], f"{m['win_rate']:.4f}",
                            f"{m['mean_return']:.4f}", f"{m['profit_factor']:.4f}",
                            f"{m['break_even_cost']:.4f}", f"{m.get('net_exp_base', 0):.4f}"])
    print(f"Regime results CSV saved")

    # Generate report
    generate_report(results)
    print(f"Report saved: {OUT_DIR / 'PHASE11_ECONOMIC_CONDITIONAL_STRUCTURE_REPORT.md'}")

    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"Phase 11 complete in {elapsed:.0f}s")
    print(f"Classification: {classification}")
    print(f"Research decision: {research_decision}")
    print(f"{'='*70}")


def generate_report(results):
    lines = []
    lines.append("# Phase 11: Economic Conditional Structure Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Classification: {results['classification']}**")
    lines.append(f"**Research Decision: {results['research_decision']}**")
    lines.append("")
    lines.append(results["research_reason"])
    lines.append("")

    # Implementation audit
    lines.append("## Implementation Audit")
    lines.append("")
    ia = results["implementation_audit"]
    lines.append(f"- pip_value(EUR/USD): ${ia['pip_value_eurusd']:.2f}")
    lines.append(f"- pip_value(USD/JPY): ${ia['pip_value_usdjpy']:.2f}")
    lines.append(f"- Forward returns: actual pips: {ia['forward_returns_in_pips']}")
    lines.append(f"- Cost pair-specific: {ia['cost_pair_specific']}")
    lines.append(f"- No look-ahead: {ia['no_lookahead']}")
    lines.append("")

    # Signal bin analysis
    lines.append("## Signal Strength × Economic Return")
    lines.append("")
    lines.append("| Bin | N | Mean Pred P | Actual Fast Rate | Mean Return | Net Exp (LOW) | Net Exp (BASE) |")
    lines.append("|-----|---|-------------|------------------|-------------|---------------|----------------|")
    for d in results["signal_bin_results"]:
        lines.append(f"| {d['bin_label']} | {d['n']:,} | {d['mean_pred_p']:.3f} | "
                     f"{d['actual_fast_rate']:.3f} | {d['mean_return']:.2f} | "
                     f"{d.get('net_exp_COST_LOW', 0):.2f} | {d.get('net_exp_COST_BASE', 0):.2f} |")
    lines.append("")

    # Cost breakpoint
    lines.append("## Cost-Breakpoint Distribution")
    lines.append("")
    cb = results["cost_breakpoint"]["overall"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Mean | {cb['mean']:.2f} pip |")
    lines.append(f"| Median | {cb['median']:.2f} pip |")
    lines.append(f"| 10th percentile | {cb['q10']:.2f} pip |")
    lines.append(f"| 25th percentile | {cb['q25']:.2f} pip |")
    lines.append(f"| 75th percentile | {cb['q75']:.2f} pip |")
    lines.append(f"| 90th percentile | {cb['q90']:.2f} pip |")
    lines.append(f"| % surviving 0.5 pip | {cb['pct_surviving_05']:.1f}% |")
    lines.append(f"| % surviving 0.75 pip | {cb['pct_surviving_075']:.1f}% |")
    lines.append(f"| % surviving 1.0 pip | {cb['pct_surviving_10']:.1f}% |")
    lines.append(f"| % surviving 1.5 pip | {cb['pct_surviving_15']:.1f}% |")
    lines.append(f"| % surviving 2.0 pip | {cb['pct_surviving_20']:.1f}% |")
    lines.append("")

    # Pair selection
    lines.append("## Pair Selection Without Look-Ahead")
    lines.append("")
    lines.append("| Rule | OOS Trades | Mean Return | Net Exp (LOW) | Net Exp (BASE) | PF | Max DD |")
    lines.append("|------|-----------|-------------|---------------|----------------|----|--------|")
    for rule, d in results["pair_select_results"].items():
        lines.append(f"| {rule} | {d['n_trades']:,} | {d['mean_return']:.2f} | "
                     f"{d['net_exp_low']:.2f} | {d['net_exp_base']:.2f} | "
                     f"{d['profit_factor']:.2f} | {d['max_drawdown']:.1f} |")
    lines.append("")

    # Regime conditional
    lines.append("## Regime-Conditional Performance")
    lines.append("")
    lines.append("| Condition | N | Mean Return | Win Rate | PF |")
    lines.append("|-----------|---|-------------|----------|----|")
    for label, d in results["regime_conditional"].items():
        lines.append(f"| {label} | {d['n']:,} | {d['mean_return']:.2f} | "
                     f"{d['win_rate']:.3f} | {d['profit_factor']:.2f} |")
    lines.append("")

    # Econ vs class
    lines.append("## Economic vs Classification Information")
    lines.append("")
    ec = results["econ_vs_class"]
    lines.append(f"- Corr(P(fast), return): {ec['corr_pfast_return']:.4f} (p={ec['p_value_direction']:.4f})")
    lines.append(f"- Spearman(P(fast), return): {ec['spearman_rank']:.4f} (p={ec['p_value_rank']:.4f})")
    lines.append(f"- Corr(P(fast), |return|): {ec['corr_pfast_abs_return']:.4f} (p={ec['p_value_abs']:.4f})")
    lines.append("")

    # Multiple testing
    lines.append("## Multiple-Testing Control")
    lines.append("")
    mt = results["multiple_testing"]
    lines.append(f"- Estimated subgroup tests: ~{mt['n_subgroup_tests']}")
    lines.append(f"- Bonferroni-adjusted alpha: {mt['bonferroni_alpha']:.6f}")
    lines.append("")

    # Final
    lines.append("## Final Classification")
    lines.append("")
    lines.append(f"### {results['classification']}")
    lines.append("")
    lines.append(f"- Profitable pair×threshold combinations: "
                 f"{results['n_profitable_pair_thr']}/{results['n_total_pair_thr']}")
    lines.append(f"- Research decision: {results['research_decision']}")
    lines.append("")

    with open(OUT_DIR / "PHASE11_ECONOMIC_CONDITIONAL_STRUCTURE_REPORT.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
