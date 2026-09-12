"""
Phase 11: Controlled Filter Ablation for Currency-Strength Hypothesis

Tests whether specific filters can isolate a cost-resilient subsample.
NOT optimization — each filter is a pre-registered hypothesis tested
on discovery (2016-2023) then validated on OOS (2024-2026).

Classification: OOS net expectancy sign + significance.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


from currency_strength import CurrencyStrengthRanker
from config import ALL_PAIRS, STRENGTH_LOOKBACKS, STRENGTH_TOP_N, STRENGTH_MIN_DIVERGENCE, STRENGTH_NORMALIZE_WINDOW as NORM_WINDOW

HORIZONS = {"5min": 1, "15min": 1, "30min": 1, "1h": 2, "4h": 8, "8h": 16, "1d": 48}
PRIMARY_HORIZONS = ["1h", "4h"]

COST_PIPS = 1.72  # average round-trip cost (spread + commission + slippage)

PAIR_COST_PIPS = {
    "EUR/USD": 1.2, "GBP/USD": 1.8, "USD/JPY": 1.4, "USD/CHF": 1.8,
    "USD/CAD": 2.0, "AUD/USD": 1.6, "NZD/USD": 2.4, "EUR/GBP": 1.8,
    "EUR/JPY": 2.0, "EUR/CHF": 2.2, "EUR/CAD": 2.6, "EUR/AUD": 3.2,
    "GBP/JPY": 3.0, "GBP/CHF": 3.0, "GBP/CAD": 3.4, "GBP/AUD": 3.8,
    "CHF/JPY": 2.4, "CAD/JPY": 2.2, "AUD/JPY": 2.0, "NZD/JPY": 2.8,
    "AUD/CAD": 2.8, "AUD/CHF": 2.8, "NZD/CHF": 3.2, "CAD/CHF": 3.0,
}

DISCOVERY_START = "2016-01-01"
DISCOVERY_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2026-07-31"

DATA_DIR = Path("/root/data")
RNG_SEED = 42


def load_pair_data(pairs: list[str], resample: str = "30min") -> dict[str, pd.DataFrame]:
    data = {}
    for pair in pairs:
        fp = DATA_DIR / f"{pair.replace('/', '_')}.pkl"
        if not fp.exists():
            fp = DATA_DIR / f"{pair}.pkl"
        if fp.exists():
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
            elif isinstance(raw, pd.DataFrame) and "close" in raw.columns:
                df = raw.copy()
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                if resample and resample != "1min":
                    df = df.resample(resample).agg({
                        "open": "first", "high": "max", "low": "min",
                        "close": "last", "volume": "sum",
                    }).dropna()
                data[pair] = df
    return data


def pip_factor(pair: str) -> float:
    return 100.0 if "JPY" in pair else 10000.0


def compute_forward_returns(pair_data: dict[str, pd.DataFrame]) -> dict[str, dict[str, np.ndarray]]:
    fwd = {}
    for pair, df in pair_data.items():
        close = df["close"].values.astype(np.float64)
        pf = pip_factor(pair)
        fwd[pair] = {}
        for h_name, h_bars in HORIZONS.items():
            n = len(close)
            ret_pips = np.full(n, np.nan)
            valid_end = n - h_bars
            if valid_end > 0:
                diff = close[h_bars:n] - close[:n - h_bars]
                ret_pips[:valid_end] = diff * pf
            fwd[pair][h_name] = ret_pips
    return fwd


def compute_strength_differential(
    pair_data: dict[str, pd.DataFrame],
    universe: list[str],
) -> pd.DataFrame:
    ranker = CurrencyStrengthRanker(
        lookbacks=STRENGTH_LOOKBACKS,
        top_n=STRENGTH_TOP_N,
        min_div=STRENGTH_MIN_DIVERGENCE,
        norm_window=NORM_WINDOW,
    )
    scores_df = ranker.calculate(pair_data)

    pairs_in_universe = [p for p in universe if p in pair_data]
    base_map = {p: p.split("/")[0] for p in pairs_in_universe}
    quote_map = {p: p.split("/")[1] for p in pairs_in_universe}

    diff = pd.DataFrame(index=scores_df.index, dtype=float)
    for pair in pairs_in_universe:
        base = base_map[pair]
        quote = quote_map[pair]
        if base in scores_df.columns and quote in scores_df.columns:
            diff[pair] = scores_df[base].values - scores_df[quote].values
    return diff


def align_arrays(diff: pd.DataFrame, fwd: dict, pair: str, horizon: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    d = diff[pair].values
    f = fwd[pair][horizon]
    min_len = min(len(d), len(f))
    d = d[:min_len]
    f = f[:min_len]
    valid = ~np.isnan(d) & ~np.isnan(f)
    return d, f, valid


def compute_metrics(d: np.ndarray, f: np.ndarray, valid: np.ndarray, cost: float = 0.0) -> dict[str, Any]:
    n = valid.sum()
    if n < 30:
        return {"n": int(n), "mean_return": 0.0, "win_rate": 0.5, "net_expectancy": 0.0,
                "profit_factor": 1.0, "t_statistic": 0.0, "p_value": 1.0, "break_even_cost": 0.0}
    d_v = d[valid]
    f_v = f[valid]
    mean_raw = float(np.mean(f_v))
    mean_net = mean_raw - cost
    wins = f_v > 0
    losses = f_v < 0
    win_rate = float(wins.sum() / n)
    gross_profit = float(f_v[wins].sum()) if wins.any() else 0.0
    gross_loss = float(abs(f_v[losses].sum())) if losses.any() else 1e-10
    pf = gross_profit / gross_loss if gross_loss > 0 else 999.0
    if n > 1 and np.std(f_v) > 0:
        t_stat = mean_raw / (np.std(f_v) / np.sqrt(n))
        p_val = 2 * stats.t.sf(abs(t_stat), df=n - 1)
    else:
        t_stat, p_val = 0.0, 1.0
    positive_trades = f_v[f_v > 0]
    break_even = float(np.mean(positive_trades)) if len(positive_trades) > 0 else 0.0
    return {
        "n": int(n),
        "mean_return": round(mean_raw, 6),
        "win_rate": round(win_rate, 6),
        "net_expectancy": round(mean_net, 6),
        "profit_factor": round(pf, 4),
        "t_statistic": round(t_stat, 4),
        "p_value": round(p_val, 6),
        "break_even_cost": round(break_even, 4),
    }


def compute_regime_at_decision_time(
    pair_data: dict[str, pd.DataFrame],
    pair: str,
    ema_period: int = 200,
) -> np.ndarray:
    if pair not in pair_data:
        return np.array([])
    close = pair_data[pair]["close"].values.astype(np.float64)
    ema = pd.Series(close).ewm(span=ema_period, adjust=False).mean().values
    return (close > ema).astype(float)


def compute_vol_regime(
    pair_data: dict[str, pd.DataFrame],
    pair: str,
    window: int = 480,
    n_terciles: int = 3,
) -> tuple[np.ndarray, dict]:
    if pair not in pair_data:
        return np.array({})
    close = pair_data[pair]["close"].values.astype(np.float64)
    returns = np.diff(np.log(close + 1e-10))
    vol = pd.Series(returns).rolling(window).std().values
    valid_vol = vol[~np.isnan(vol)]
    if len(valid_vol) < n_terciles * 10:
        return vol, {}
    tercile_edges = np.percentile(valid_vol, [33.33, 66.67])
    regime = np.full(len(vol), np.nan)
    regime[~np.isnan(vol)] = np.digitize(vol[~np.isnan(vol)], tercile_edges)
    labels = {0: "low", 1: "mid", 2: "high"}
    return regime, {"edges": tercile_edges.tolist(), "labels": labels}


def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase 11: Controlled Filter Ablation for Currency-Strength Hypothesis")
    print("=" * 70)

    print("\n[1] Loading pair data...")
    pair_data = load_pair_data(ALL_PAIRS)
    print(f"  Loaded {len(pair_data)} pairs")

    print("\n[2] Computing forward returns...")
    fwd = compute_forward_returns(pair_data)
    print(f"  Computed for {len(pair_data)} pairs × {len(HORIZONS)} horizons")

    print("\n[3] Computing currency strength differentials...")
    strength_diff = compute_strength_differential(pair_data, ALL_PAIRS)
    print(f"  Strength diff shape: {strength_diff.shape}")

    print("\n[4] Computing regime indicators...")
    ema200 = {}
    vol_regime = {}
    for pair in ALL_PAIRS:
        if pair in pair_data:
            ema200[pair] = compute_regime_at_decision_time(pair_data, pair, ema_period=200)
            vol_regime[pair] = compute_vol_regime(pair_data, pair, window=480)

    ts_index = strength_diff.index
    discovery_mask = (ts_index >= DISCOVERY_START) & (ts_index <= DISCOVERY_END)
    oos_mask = (ts_index >= OOS_START) & (ts_index <= OOS_END)
    print(f"  Discovery: {discovery_mask.sum()} bars, OOS: {oos_mask.sum()} bars")

    print("\n[5] Building unified observation table...")
    rows = []
    for pair in ALL_PAIRS:
        if pair not in pair_data:
            continue
        d_vals = strength_diff[pair].values
        base, quote = pair.split("/")[0], pair.split("/")[1]
        pair_idx = pair_data[pair].index
        min_len = min(len(d_vals), len(pair_idx))
        d_vals = d_vals[:min_len]
        p_idx = pair_idx[:min_len]
        hour = p_idx.hour.values
        weekday = p_idx.weekday.values
        is_jpy = "JPY" in pair
        ema_aligned = np.full(min_len, np.nan)
        if pair in ema200 and len(ema200[pair]) == min_len:
            ema_aligned = ema200[pair]
        vol_r = np.full(min_len, np.nan)
        if pair in vol_regime and isinstance(vol_regime[pair], np.ndarray) and len(vol_regime[pair]) == min_len:
            vol_r = vol_regime[pair]
        for h_name in PRIMARY_HORIZONS:
            f_vals = fwd[pair][h_name]
            f_min = min(len(f_vals), min_len)
            for i in range(f_min):
                if np.isnan(d_vals[i]) or np.isnan(f_vals[i]):
                    continue
                row = {
                    "pair": pair,
                    "horizon": h_name,
                    "gap": d_vals[i],
                    "fwd_return": f_vals[i],
                    "hour": int(hour[i]),
                    "weekday": int(weekday[i]),
                    "is_jpy": is_jpy,
                    "ema_aligned": ema_aligned[i] if i < len(ema_aligned) else np.nan,
                    "vol_regime": vol_r[i] if i < len(vol_r) else np.nan,
                    "ts": p_idx[i],
                }
                rows.append(row)
    obs = pd.DataFrame(rows)
    print(f"  Total observations: {len(obs)}")
    print(f"  Discovery: {(obs['ts'] >= DISCOVERY_START).sum()}, OOS: {(obs['ts'] >= OOS_START).sum()}")

    results: dict[str, Any] = {
        "phase": "11",
        "title": "Controlled Filter Ablation for Currency-Strength Hypothesis",
        "cost_pips": COST_PIPS,
        "discovery_period": f"{DISCOVERY_START} to {DISCOVERY_END}",
        "oos_period": f"{OOS_START} to {OOS_END}",
        "filters": {},
        "combinations": {},
    }

    def evaluate_subset(subset: pd.DataFrame, label: str, cost: float = COST_PIPS) -> dict[str, Any]:
        out = {}
        for h in PRIMARY_HORIZONS:
            sub_h = subset[subset["horizon"] == h]
            if len(sub_h) < 50:
                out[h] = compute_metrics(np.zeros(1), np.zeros(1), np.array([False]), cost)
                continue
            d = sub_h["gap"].values
            f = sub_h["fwd_return"].values
            valid = np.ones(len(d), dtype=bool)
            out[h] = compute_metrics(d, f, valid, cost)
        return out

    # --- FILTER 1: Gap Range ---
    print("\n[6] Filter 1: Gap Range (D4-D7)...")
    disc_obs = obs[(obs["ts"] >= DISCOVERY_START) & (obs["ts"] <= DISCOVERY_END)]
    gap_q40 = disc_obs["gap"].quantile(0.40)
    gap_q70 = disc_obs["gap"].quantile(0.70)
    print(f"  Discovery thresholds: D40={gap_q40:.2f}, D70={gap_q70:.2f}")
    gap_disc = disc_obs[(disc_obs["gap"] >= gap_q40) & (disc_obs["gap"] <= gap_q70)]
    gap_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]
    gap_oos_f = gap_oos[(gap_oos["gap"] >= gap_q40) & (gap_oos["gap"] <= gap_q70)]
    gap_all_disc = evaluate_subset(disc_obs, "all_discovery")
    gap_filtered_disc = evaluate_subset(gap_disc, "gap_filtered_discovery")
    gap_all_oos = evaluate_subset(gap_oos, "all_oos")
    gap_filtered_oos = evaluate_subset(gap_oos_f, "gap_filtered_oos")
    results["filters"]["gap_range"] = {
        "hypothesis": "Middle gap deciles (D40-D70) have positive gross expectancy; extremes do not",
        "discovery_thresholds": {"gap_q40": round(gap_q40, 4), "gap_q70": round(gap_q70, 4)},
        "discovery_all": gap_all_disc,
        "discovery_filtered": gap_filtered_disc,
        "oos_all": gap_all_oos,
        "oos_filtered": gap_filtered_oos,
    }
    for h in PRIMARY_HORIZONS:
        d_net = gap_filtered_disc[h]["net_expectancy"]
        o_net = gap_filtered_oos[h]["net_expectancy"]
        print(f"  {h}: disc net={d_net:+.4f}, oos net={o_net:+.4f}")

    # --- FILTER 2: JPY Crosses ---
    print("\n[7] Filter 2: JPY Crosses...")
    jpy_disc = disc_obs[disc_obs["is_jpy"] == True]
    jpy_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]
    jpy_oos_f = jpy_oos[jpy_oos["is_jpy"] == True]
    jpy_disc_eval = evaluate_subset(jpy_disc, "jpy_discovery")
    jpy_all_disc = evaluate_subset(disc_obs, "all_discovery")
    jpy_oos_eval = evaluate_subset(jpy_oos_f, "jpy_oos")
    jpy_all_oos = evaluate_subset(jpy_oos, "all_oos")
    results["filters"]["jpy_crosses"] = {
        "hypothesis": "JPY crosses are the primary source of gross edge",
        "discovery_all": jpy_all_disc,
        "discovery_filtered": jpy_disc_eval,
        "oos_all": jpy_all_oos,
        "oos_filtered": jpy_oos_eval,
    }
    for h in PRIMARY_HORIZONS:
        d_net = jpy_disc_eval[h]["net_expectancy"]
        o_net = jpy_oos_eval[h]["net_expectancy"]
        print(f"  {h}: disc net={d_net:+.4f}, oos net={o_net:+.4f}")

    # --- FILTER 3: Session (London-NY overlap 12-16 UTC) ---
    print("\n[8] Filter 3: Session (overlap 12-16 UTC)...")
    sess_disc = disc_obs[(disc_obs["hour"] >= 12) & (disc_obs["hour"] < 16)]
    sess_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]
    sess_oos_f = sess_oos[(sess_oos["hour"] >= 12) & (sess_oos["hour"] < 16)]
    sess_disc_eval = evaluate_subset(sess_disc, "session_discovery")
    sess_all_disc = evaluate_subset(disc_obs, "all_discovery")
    sess_oos_eval = evaluate_subset(sess_oos_f, "session_oos")
    sess_all_oos = evaluate_subset(sess_oos, "all_oos")
    results["filters"]["session_overlap"] = {
        "hypothesis": "London-NY overlap (12-16 UTC) has tighter spreads and stronger trends",
        "discovery_all": sess_all_disc,
        "discovery_filtered": sess_disc_eval,
        "oos_all": sess_all_oos,
        "oos_filtered": sess_oos_eval,
    }
    for h in PRIMARY_HORIZONS:
        d_net = sess_disc_eval[h]["net_expectancy"]
        o_net = sess_oos_eval[h]["net_expectancy"]
        print(f"  {h}: disc net={d_net:+.4f}, oos net={o_net:+.4f}")

    # --- FILTER 4: Trend Alignment (4H EMA200) ---
    print("\n[9] Filter 4: Trend Alignment (EMA200)...")
    trend_disc = disc_obs[disc_obs["ema_aligned"] == 1.0]
    trend_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]
    trend_oos_f = trend_oos[trend_oos["ema_aligned"] == 1.0]
    trend_disc_eval = evaluate_subset(trend_disc, "trend_discovery")
    trend_all_disc = evaluate_subset(disc_obs, "all_discovery")
    trend_oos_eval = evaluate_subset(trend_oos_f, "trend_oos")
    trend_all_oos = evaluate_subset(trend_oos, "all_oos")
    results["filters"]["trend_alignment"] = {
        "hypothesis": "Signal aligned with 4H EMA200 trend has stronger forward returns",
        "discovery_all": trend_all_disc,
        "discovery_filtered": trend_disc_eval,
        "oos_all": trend_all_oos,
        "oos_filtered": trend_oos_eval,
    }
    for h in PRIMARY_HORIZONS:
        d_net = trend_disc_eval[h]["net_expectancy"]
        o_net = trend_oos_eval[h]["net_expectancy"]
        print(f"  {h}: disc net={d_net:+.4f}, oos net={o_net:+.4f}")

    # --- FILTER 5: Volatility Regime (low vol) ---
    print("\n[10] Filter 5: Volatility Regime (low vol)...")
    vol_disc = disc_obs[disc_obs["vol_regime"] == 0.0]
    vol_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]
    vol_oos_f = vol_oos[vol_oos["vol_regime"] == 0.0]
    vol_disc_eval = evaluate_subset(vol_disc, "vol_discovery")
    vol_all_disc = evaluate_subset(disc_obs, "all_discovery")
    vol_oos_eval = evaluate_subset(vol_oos_f, "vol_oos")
    vol_all_oos = evaluate_subset(vol_oos, "all_oos")
    results["filters"]["volatility_low"] = {
        "hypothesis": "Low-volatility regime has better trend-following behavior",
        "discovery_all": vol_all_disc,
        "discovery_filtered": vol_disc_eval,
        "oos_all": vol_all_oos,
        "oos_filtered": vol_oos_eval,
    }
    for h in PRIMARY_HORIZONS:
        d_net = vol_disc_eval[h]["net_expectancy"]
        o_net = vol_oos_eval[h]["net_expectancy"]
        print(f"  {h}: disc net={d_net:+.4f}, oos net={o_net:+.4f}")

    # --- FILTER 6: Currency Structure (rank1 vs rank8) ---
    print("\n[11] Filter 6: Currency Structure (top-bottom rank)...")
    gap_abs = disc_obs["gap"].abs()
    rank_q90 = gap_abs.quantile(0.90)
    rank_disc = disc_obs[gap_abs >= rank_q90]
    rank_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]
    rank_abs_oos = rank_oos["gap"].abs()
    rank_oos_f = rank_oos[rank_abs_oos >= rank_q90]
    rank_disc_eval = evaluate_subset(rank_disc, "rank_discovery")
    rank_all_disc = evaluate_subset(disc_obs, "all_discovery")
    rank_oos_eval = evaluate_subset(rank_oos_f, "rank_oos")
    rank_all_oos = evaluate_subset(rank_oos, "all_oos")
    results["filters"]["currency_structure"] = {
        "hypothesis": "Top-bottom rank pairs (|gap| >= 90th pctile) have stronger edge",
        "discovery_thresholds": {"gap_abs_q90": round(rank_q90, 4)},
        "discovery_all": rank_all_disc,
        "discovery_filtered": rank_disc_eval,
        "oos_all": rank_all_oos,
        "oos_filtered": rank_oos_eval,
    }
    for h in PRIMARY_HORIZONS:
        d_net = rank_disc_eval[h]["net_expectancy"]
        o_net = rank_oos_eval[h]["net_expectancy"]
        print(f"  {h}: disc net={d_net:+.4f}, oos net={o_net:+.4f}")

    # --- COMBINATION TESTS ---
    print("\n[12] Combination tests (sequential additivity)...")
    combo_base_disc = disc_obs
    combo_base_oos = obs[(obs["ts"] >= OOS_START) & (obs["ts"] <= OOS_END)]

    combo1_disc = combo_base_disc[
        (combo_base_disc["gap"] >= gap_q40) & (combo_base_disc["gap"] <= gap_q70)
    ]
    combo1_oos = combo_base_oos[
        (combo_base_oos["gap"] >= gap_q40) & (combo_base_oos["gap"] <= gap_q70)
    ]
    results["combinations"]["gap_only"] = {
        "filters": ["gap_range"],
        "discovery": evaluate_subset(combo1_disc, "gap_only_disc"),
        "oos": evaluate_subset(combo1_oos, "gap_only_oos"),
    }

    combo2_disc = combo1_disc[combo1_disc["is_jpy"] == True]
    combo2_oos = combo1_oos[combo1_oos["is_jpy"] == True]
    results["combinations"]["gap_plus_jpy"] = {
        "filters": ["gap_range", "jpy_crosses"],
        "discovery": evaluate_subset(combo2_disc, "gap_jpy_disc"),
        "oos": evaluate_subset(combo2_oos, "gap_jpy_oos"),
    }

    combo3_disc = combo2_disc[(combo2_disc["hour"] >= 12) & (combo2_disc["hour"] < 16)]
    combo3_oos = combo2_oos[(combo2_oos["hour"] >= 12) & (combo2_oos["hour"] < 16)]
    results["combinations"]["gap_jpy_session"] = {
        "filters": ["gap_range", "jpy_crosses", "session_overlap"],
        "discovery": evaluate_subset(combo3_disc, "gap_jpy_sess_disc"),
        "oos": evaluate_subset(combo3_oos, "gap_jpy_sess_oos"),
    }

    combo4_disc = combo3_disc[combo3_disc["ema_aligned"] == 1.0]
    combo4_oos = combo3_oos[combo3_oos["ema_aligned"] == 1.0]
    results["combinations"]["gap_jpy_session_trend"] = {
        "filters": ["gap_range", "jpy_crosses", "session_overlap", "trend_alignment"],
        "discovery": evaluate_subset(combo4_disc, "all_disc"),
        "oos": evaluate_subset(combo4_oos, "all_oos"),
    }

    for combo_name, combo_data in results["combinations"].items():
        print(f"\n  {combo_name}:")
        for h in PRIMARY_HORIZONS:
            d_n = combo_data["discovery"][h]["n"]
            o_n = combo_data["oos"][h]["n"]
            d_net = combo_data["discovery"][h]["net_expectancy"]
            o_net = combo_data["oos"][h]["net_expectancy"]
            print(f"    {h}: disc n={d_n}, net={d_net:+.4f} | oos n={o_n}, net={o_net:+.4f}")

    # --- CLASSIFICATION ---
    print("\n[13] Classification...")
    classifications = {}
    for filter_name, filter_data in results["filters"].items():
        for h in PRIMARY_HORIZONS:
            oos = filter_data["oos_filtered"][h]
            key = f"{filter_name}_{h}"
            if oos["n"] < 100:
                classifications[key] = "D. INSUFFICIENT OOS DATA"
            elif oos["net_expectancy"] > 0 and oos["p_value"] < 0.05:
                classifications[key] = "A. OOS POSITIVE AND SIGNIFICANT"
            elif oos["net_expectancy"] > 0:
                classifications[key] = "B. OOS POSITIVE BUT NOT SIGNIFICANT"
            else:
                classifications[key] = "C. OOS NEGATIVE"
    results["classifications"] = classifications

    for combo_name, combo_data in results["combinations"].items():
        for h in PRIMARY_HORIZONS:
            oos = combo_data["oos"][h]
            key = f"combo_{combo_name}_{h}"
            if oos["n"] < 100:
                classifications[key] = "D. INSUFFICIENT OOS DATA"
            elif oos["net_expectancy"] > 0 and oos["p_value"] < 0.05:
                classifications[key] = "A. OOS POSITIVE AND SIGNIFICANT"
            elif oos["net_expectancy"] > 0:
                classifications[key] = "B. OOS POSITIVE BUT NOT SIGNIFICANT"
            else:
                classifications[key] = "C. OOS NEGATIVE"

    print("\n  Filter classifications:")
    for k, v in sorted(classifications.items()):
        print(f"    {k}: {v}")

    # --- RESEARCH DECISION ---
    any_a = any("A." in v for v in classifications.values())
    any_b = any("B." in v for v in classifications.values())
    if any_a:
        decision = "PROCEED — at least one filter shows significant OOS edge"
    elif any_b:
        decision = "CONDITIONAL — some filters show positive OOS edge but not significant"
    else:
        decision = "STOP — no filter shows positive OOS edge"
    results["research_decision"] = decision
    print(f"\n  Research decision: {decision}")

    # --- SAVE ---
    out_dir = Path("research/output/phase11_currency")
    out_dir.mkdir(parents=True, exist_ok=True)
    results["runtime_seconds"] = time.time() - t0
    with open(out_dir / "phase11_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    summary_rows = []
    for fname, fdata in results["filters"].items():
        for h in PRIMARY_HORIZONS:
            disc = fdata["discovery_filtered"][h]
            oos = fdata["oos_filtered"][h]
            disc_all = fdata["discovery_all"][h]
            oos_all = fdata["oos_all"][h]
            summary_rows.append({
                "filter": fname,
                "horizon": h,
                "disc_n": disc["n"],
                "disc_mean": disc["mean_return"],
                "disc_win_rate": disc["win_rate"],
                "disc_net": disc["net_expectancy"],
                "disc_all_net": disc_all["net_expectancy"],
                "disc_improvement": disc["net_expectancy"] - disc_all["net_expectancy"],
                "oos_n": oos["n"],
                "oos_mean": oos["mean_return"],
                "oos_win_rate": oos["win_rate"],
                "oos_net": oos["net_expectancy"],
                "oos_all_net": oos_all["net_expectancy"],
                "oos_improvement": oos["net_expectancy"] - oos_all["net_expectancy"],
                "oos_t_stat": oos["t_statistic"],
                "oos_p_value": oos["p_value"],
                "classification": classifications.get(f"{fname}_{h}", "N/A"),
            })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out_dir / "phase11_summary.csv", index=False)

    print(f"\nResults saved: {out_dir / 'phase11_results.json'}")
    print(f"Summary CSV: {out_dir / 'phase11_summary.csv'}")

    print(f"\n{'=' * 70}")
    print(f"Phase 11 complete in {time.time() - t0:.1f}s")
    print(f"Decision: {decision}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
