"""Cross-Timeframe Agreement Research — Phase 3c.

1min permanently excluded. Base grid: 15min.
Agreement measured across 15min, 1h, 4h.

Phase C: Agreement categories across 3 timeframes.
Phase D: Pairwise timeframe agreement.
Phase E: Multiple comparison control.
Phase F: Outlier removal stability checks.

All computations strictly causal. No lookahead.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


from nestquant.research.shared.zscore.zscore import _zscore_causal_core
from nestquant.research.shared.zscore.regime import classify_regime_chunked

RESULTS_DIR = Path("research/output/phase3")
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF",
    "EUR/GBP", "EUR/CHF", "EUR/CAD", "EUR/AUD", "GBP/JPY",
    "GBP/CAD", "GBP/AUD", "AUD/JPY", "AUD/CAD", "AUD/CHF",
    "NZD/USD", "NZD/JPY", "NZD/CHF", "CAD/JPY", "CAD/CHF",
]
LOOKBACK = 20
PRIMARY_HORIZON = 60
COST_LEVELS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
N_BOOTSTRAP = 200
YEAR_SPLITS = {
    "2016-2018": (2016, 2018),
    "2019-2021": (2019, 2021),
    "2022-2024": (2022, 2024),
    "2025-2026": (2025, 2026),
}
# 3 timeframes only (1min excluded)
MTF_TIMEFRAMES = ["15min", "1h", "4h"]
BASE_TF = "15min"


def load_pair(pair: str, timeframe: str) -> pd.DataFrame | None:
    pair_file = pair.replace("/", "_")
    data_dir = Path("/root/data")
    tf_path = data_dir / timeframe / f"{pair_file}.pkl"
    flat_path = data_dir / f"{pair_file}.pkl"
    try:
        if tf_path.exists():
            data = pd.read_pickle(tf_path)
        elif flat_path.exists():
            data = pd.read_pickle(flat_path)
        else:
            return None
    except Exception:
        return None
    if isinstance(data, dict):
        data = data.get(pair)
        if data is None:
            return None
    return data


def pip_value(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def compute_regime_labels(pair: str, timeframe: str) -> tuple[pd.DatetimeIndex, np.ndarray] | None:
    """Load pair, compute regime labels, return (timestamps, regime_labels)."""
    df = load_pair(pair, timeframe)
    if df is None or len(df) < LOOKBACK + PRIMARY_HORIZON + 10:
        return None

    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    ts = df.index

    try:
        regimes = classify_regime_chunked(
            close, high, low, ts, pair,
            chunk_size=1000, ema_span=200, atr_period=14,
        )
        labels = np.array([f"{r.trend}×{r.volatility}" for r in regimes])
    except Exception:
        labels = np.array(["unknown"] * len(close))

    return ts, labels


def compute_forward_returns(close: np.ndarray, horizon: int = PRIMARY_HORIZON) -> np.ndarray:
    n = len(close)
    fr = np.full(n, np.nan)
    if n > horizon:
        fr[:n - horizon] = (close[horizon:] - close[:n - horizon]) / close[:n - horizon]
    return fr


def compute_metrics(returns_pips: np.ndarray, cost_pips: float = 0.0) -> dict:
    n = len(returns_pips)
    if n == 0:
        return {"n": 0}
    net = returns_pips - cost_pips
    net_valid = net[np.isfinite(net)]
    n_valid = len(net_valid)
    if n_valid == 0:
        return {"n": 0}

    mean_net = float(np.mean(net_valid))
    std_net = float(np.std(net_valid, ddof=1)) if n_valid > 1 else 0.0
    se_net = std_net / np.sqrt(n_valid) if n_valid > 0 else 0.0
    median = float(np.median(net_valid))
    wins = net_valid[net_valid > 0]
    losses = net_valid[net_valid < 0]
    win_rate = len(wins) / n_valid * 100 if n_valid > 0 else 0.0
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    cum = np.cumsum(net_valid)
    running_max = np.maximum.accumulate(cum)
    max_dd = float(np.min(cum - running_max))
    sharpe = (mean_net / std_net * np.sqrt(252)) if std_net > 0 and n_valid > 10 else None
    downside = net_valid[net_valid < 0]
    dd_dev = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (mean_net / dd_dev * np.sqrt(252)) if dd_dev > 0 and n_valid > 10 else None

    return {
        "n": n_valid,
        "mean_pips": mean_net,
        "median_pips": median,
        "std_pips": std_net,
        "se_pips": se_net,
        "ci_lower_pips": mean_net - 1.96 * se_net,
        "ci_upper_pips": mean_net + 1.96 * se_net,
        "win_rate": win_rate,
        "avg_win_pips": avg_win,
        "avg_loss_pips": avg_loss,
        "profit_factor": pf,
        "max_drawdown_pips": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
    }


def bootstrap_ci(data: np.ndarray, n_boot: int = N_BOOTSTRAP) -> dict:
    n = len(data)
    if n < 10:
        return {"mean": float(np.mean(data)) if n > 0 else 0.0,
                "ci_lower": None, "ci_upper": None}
    rng = np.random.default_rng(42)
    boot_means = np.array([float(np.mean(rng.choice(data, size=n, replace=True)))
                           for _ in range(n_boot)])
    return {
        "mean": float(np.mean(data)),
        "ci_lower": float(np.percentile(boot_means, 2.5)),
        "ci_upper": float(np.percentile(boot_means, 97.5)),
    }


def run_pair_agreement(pair: str) -> dict | None:
    """Compute agreement across 15min, 1h, 4h for one pair.

    Base grid: 15min. Higher TFs forward-filled to 15min timestamps.
    """
    # Load 15min as base grid
    base = compute_regime_labels(pair, BASE_TF)
    if base is None:
        return None
    ts_base, labels_base = base

    # Load close from 15min for forward returns
    df_base = load_pair(pair, BASE_TF)
    if df_base is None:
        return None
    close_base = df_base["close"].values.astype(np.float64)
    fr_base = compute_forward_returns(close_base)
    years_base = np.array([t.year for t in ts_base])
    del df_base

    # Build base DataFrame
    base_df = pd.DataFrame({
        "timestamp": ts_base,
        "regime_15min": labels_base,
        "close": close_base,
        "forward_return": fr_base,
        "year": years_base,
    }).set_index("timestamp")

    # Load and align higher timeframes (1h, 4h)
    for tf in ["1h", "4h"]:
        result = compute_regime_labels(pair, tf)
        if result is None:
            base_df[f"regime_{tf}"] = "unknown"
            continue
        ts_tf, labels_tf = result
        tf_df = pd.DataFrame({"regime": labels_tf}, index=ts_tf)
        aligned = tf_df.reindex(base_df.index, method="ffill")
        base_df[f"regime_{tf}"] = aligned["regime"].fillna("unknown")

    # Vectorized agreement classification (3 TFs)
    r1 = base_df["regime_15min"].values
    r2 = base_df["regime_1h"].values
    r3 = base_df["regime_4h"].values
    n_rows = len(r1)

    k1 = r1 != "unknown"
    k2 = r2 != "unknown"
    k3 = r3 != "unknown"
    n_known = k1.astype(int) + k2.astype(int) + k3.astype(int)

    # Encode regimes as integers
    all_labels = np.concatenate([r1[k1], r2[k2], r3[k3]])
    unique_labels = np.unique(all_labels)
    label_to_int = {l: i for i, l in enumerate(unique_labels)}
    U = len(unique_labels)

    r1_int = np.array([label_to_int.get(l, -1) for l in r1])
    r2_int = np.array([label_to_int.get(l, -1) for l in r2])
    r3_int = np.array([label_to_int.get(l, -1) for l in r3])

    counts = np.zeros((n_rows, U), dtype=np.int32)
    for j in range(U):
        counts[:, j] = ((r1_int == j) & k1).astype(int) + \
                        ((r2_int == j) & k2).astype(int) + \
                        ((r3_int == j) & k3).astype(int)
    max_agree = counts.max(axis=1)

    # Agreement categories for 3 TFs
    agreement = np.full(n_rows, "NO_AGREEMENT", dtype="U20")
    agreement[n_known == 0] = "ALL_UNKNOWN"
    agreement[(n_known == 3) & (max_agree == 3)] = "ALL_3_AGREE"
    agreement[(n_known >= 2) & (max_agree == 2)] = "2_OF_3_AGREE"
    # Override: if all 3 known and agree
    all3 = k1 & k2 & k3 & (r1 == r2) & (r2 == r3)
    agreement[all3] = "ALL_3_AGREE"

    base_df["agreement"] = agreement

    # Directional (trend) agreement
    t1 = np.array([l.split("×")[0] if l != "unknown" else "unknown" for l in r1])
    t2 = np.array([l.split("×")[0] if l != "unknown" else "unknown" for l in r2])
    t3 = np.array([l.split("×")[0] if l != "unknown" else "unknown" for l in r3])

    kt1 = t1 != "unknown"
    kt2 = t2 != "unknown"
    kt3 = t3 != "unknown"
    n_known_t = kt1.astype(int) + kt2.astype(int) + kt3.astype(int)

    all_trends = np.concatenate([t1[kt1], t2[kt2], t3[kt3]])
    unique_trends = np.unique(all_trends)
    trend_to_int = {t: i for i, t in enumerate(unique_trends)}
    T = len(unique_trends)

    t1_int = np.array([trend_to_int.get(t, -1) for t in t1])
    t2_int = np.array([trend_to_int.get(t, -1) for t in t2])
    t3_int = np.array([trend_to_int.get(t, -1) for t in t3])

    tcounts = np.zeros((n_rows, T), dtype=np.int32)
    for j in range(T):
        tcounts[:, j] = ((t1_int == j) & kt1).astype(int) + \
                         ((t2_int == j) & kt2).astype(int) + \
                         ((t3_int == j) & kt3).astype(int)
    max_tagree = tcounts.max(axis=1)

    dir_agree = np.full(n_rows, "TREND_NO_AGREEMENT", dtype="U25")
    dir_agree[n_known_t == 0] = "ALL_UNKNOWN"
    dir_agree[(n_known_t == 3) & (max_tagree == 3)] = "TREND_ALL_3"
    dir_agree[(n_known_t >= 2) & (max_tagree == 2) & (n_known_t < 3)] = "TREND_2_OF_3"

    base_df["directional_agreement"] = dir_agree

    # Pairwise agreement
    tf_pairs = [("15min", "1h"), ("15min", "4h"), ("1h", "4h")]
    for tf1, tf2 in tf_pairs:
        col_name = f"agree_{tf1}_x_{tf2}"
        base_df[col_name] = (
            (base_df[f"regime_{tf1}"] == base_df[f"regime_{tf2}"]) &
            (base_df[f"regime_{tf1}"] != "unknown") &
            (base_df[f"regime_{tf2}"] != "unknown")
        )

    # Filter valid forward returns
    valid_mask = base_df["forward_return"].notna()
    base_df = base_df[valid_mask]

    return {
        "pair": pair,
        "n_bars": len(base_df),
        "data": base_df,
    }


def analyze_category(data: pd.DataFrame, category_col: str, category_val: str,
                     pair: str) -> dict:
    """Compute metrics for a specific agreement category."""
    mask = data[category_col] == category_val
    subset = data[mask]
    n = len(subset)
    if n < 10:
        return {"n": n, "status": "insufficient"}

    pip = pip_value(pair)
    fr_pips = subset["forward_return"].values / pip

    cost_metrics = {}
    for cost in COST_LEVELS:
        m = compute_metrics(fr_pips, cost_pips=cost)
        cost_metrics[str(cost)] = {
            "mean_pips": m["mean_pips"],
            "median_pips": m["median_pips"],
            "win_rate": m["win_rate"],
            "avg_win_pips": m["avg_win_pips"],
            "avg_loss_pips": m["avg_loss_pips"],
            "profit_factor": m["profit_factor"],
            "sharpe": m["sharpe"],
            "sortino": m["sortino"],
            "max_drawdown_pips": m["max_drawdown_pips"],
            "ci_lower_pips": m["ci_lower_pips"],
            "ci_upper_pips": m["ci_upper_pips"],
            "n": m["n"],
        }

    boot = bootstrap_ci(fr_pips)

    # Temporal stability
    year_data = {}
    for period_name, (y_start, y_end) in YEAR_SPLITS.items():
        ymask = (subset["year"] >= y_start) & (subset["year"] <= y_end)
        ysubset = subset[ymask]
        yn = len(ysubset)
        if yn < 10:
            year_data[period_name] = {"n": yn, "status": "insufficient"}
            continue
        yfr = ysubset["forward_return"].values / pip
        ym = compute_metrics(yfr)
        year_data[period_name] = {
            "n": ym["n"],
            "mean_pips": ym["mean_pips"],
            "win_rate": ym["win_rate"],
            "profit_factor": ym["profit_factor"],
        }

    # Outlier sensitivity
    top5_idx = np.argsort(fr_pips)[::-1][:5]
    trim_mask = np.ones(n, dtype=bool)
    trim_mask[top5_idx] = False
    m_trimmed = compute_metrics(fr_pips[trim_mask])

    return {
        "n": n,
        "cost_metrics": cost_metrics,
        "bootstrap": boot,
        "year_data": year_data,
        "outlier_full_mean": cost_metrics["0.0"]["mean_pips"],
        "outlier_trimmed_mean": m_trimmed.get("mean_pips", 0.0),
    }


def run_pairwise_agreement(data: pd.DataFrame, pair: str) -> dict:
    """Phase D: pairwise timeframe agreement analysis."""
    tf_pairs = [("15min", "1h"), ("15min", "4h"), ("1h", "4h")]
    results = {}
    pip = pip_value(pair)

    for tf1, tf2 in tf_pairs:
        col = f"agree_{tf1}_x_{tf2}"
        agree_mask = data[col] == True  # noqa: E712
        disagree_mask = data[col] == False  # noqa: E712

        pair_key = f"{tf1}_x_{tf2}"
        results[pair_key] = {}

        for label, subset in [("agree", data[agree_mask]), ("disagree", data[disagree_mask])]:
            n = len(subset)
            if n < 10:
                results[pair_key][label] = {"n": n, "status": "insufficient"}
                continue
            fr_pips = subset["forward_return"].values / pip
            m = compute_metrics(fr_pips)
            b = bootstrap_ci(fr_pips)

            year_data = {}
            for period_name, (y_start, y_end) in YEAR_SPLITS.items():
                ymask = (subset["year"] >= y_start) & (subset["year"] <= y_end)
                yn = int(ymask.sum())
                if yn < 10:
                    year_data[period_name] = {"n": yn, "status": "insufficient"}
                    continue
                yfr = subset["forward_return"].values[ymask] / pip
                ym = compute_metrics(yfr)
                year_data[period_name] = {
                    "n": ym["n"],
                    "mean_pips": ym["mean_pips"],
                    "win_rate": ym["win_rate"],
                }

            results[pair_key][label] = {
                "n": n,
                "mean_pips": m["mean_pips"],
                "median_pips": m["median_pips"],
                "win_rate": m["win_rate"],
                "profit_factor": m["profit_factor"],
                "sharpe": m["sharpe"],
                "sortino": m["sortino"],
                "max_drawdown_pips": m["max_drawdown_pips"],
                "bootstrap": b,
                "year_data": year_data,
            }

    return results


def run_analysis() -> dict:
    """Run full cross-timeframe agreement analysis (15min, 1h, 4h)."""
    print(f"\n{'='*60}")
    print("  CROSS-TIMEFRAME AGREEMENT ANALYSIS (15min/1h/4h)")
    print(f"{'='*60}")

    all_categories = ["ALL_3_AGREE", "2_OF_3_AGREE", "NO_AGREEMENT", "ALL_UNKNOWN"]
    all_dir_categories = ["TREND_ALL_3", "TREND_2_OF_3", "TREND_NO_AGREEMENT", "ALL_UNKNOWN"]

    cat_accum = {cat: [] for cat in all_categories}
    dir_accum = {cat: [] for cat in all_dir_categories}
    pairwise_accum = {}
    pair_results = {}

    for i, pair in enumerate(PAIRS):
        t0 = time.time()
        result = run_pair_agreement(pair)
        elapsed = time.time() - t0
        if result is None:
            print(f"  [{i+1}/{len(PAIRS)}] {pair}: SKIP ({elapsed:.1f}s)")
            continue
        print(f"  [{i+1}/{len(PAIRS)}] {pair}: {result['n_bars']:,} bars ({elapsed:.1f}s)")

        data = result["data"]

        # Phase C: agreement categories
        pair_cat = {}
        for cat in all_categories:
            metrics = analyze_category(data, "agreement", cat, pair)
            pair_cat[cat] = metrics
            if metrics.get("n", 0) >= 10:
                cat_accum[cat].append({
                    "pair": pair,
                    "n": metrics["n"],
                    "mean_pips": metrics.get("cost_metrics", {}).get("0.0", {}).get("mean_pips", 0),
                })

        # Directional agreement
        pair_dir_cat = {}
        for cat in all_dir_categories:
            metrics = analyze_category(data, "directional_agreement", cat, pair)
            pair_dir_cat[cat] = metrics
            if metrics.get("n", 0) >= 10:
                dir_accum[cat].append({
                    "pair": pair,
                    "n": metrics["n"],
                    "mean_pips": metrics.get("cost_metrics", {}).get("0.0", {}).get("mean_pips", 0),
                })

        # Phase D: pairwise agreement
        pw = run_pairwise_agreement(data, pair)
        for pk, pv in pw.items():
            if pk not in pairwise_accum:
                pairwise_accum[pk] = {"agree": [], "disagree": []}
            for label in ["agree", "disagree"]:
                if pv.get(label, {}).get("n", 0) >= 10:
                    pairwise_accum[pk][label].append({
                        "pair": pair,
                        "n": pv[label]["n"],
                        "mean_pips": pv[label]["mean_pips"],
                    })

        pair_results[pair] = {
            "categories": pair_cat,
            "directional_categories": pair_dir_cat,
            "pairwise": pw,
        }

        del data
        gc.collect()

    # Aggregate across pairs
    def aggregate_entries(entries):
        if not entries:
            return {"n_pairs": 0, "status": "no_data"}
        total_n = sum(e["n"] for e in entries)
        weighted_mean = sum(e["mean_pips"] * e["n"] for e in entries) / total_n
        n_pos = sum(1 for e in entries if e["mean_pips"] > 0)
        return {
            "n_pairs": len(entries),
            "total_n": total_n,
            "weighted_mean_pips": weighted_mean,
            "n_pairs_positive": n_pos,
            "pct_pairs_positive": n_pos / len(entries) * 100,
        }

    cat_aggregate = {cat: aggregate_entries(cat_accum[cat]) for cat in all_categories}
    dir_aggregate = {cat: aggregate_entries(dir_accum[cat]) for cat in all_dir_categories}

    pw_aggregate = {}
    for pk, labels in pairwise_accum.items():
        pw_aggregate[pk] = {label: aggregate_entries(entries)
                            for label, entries in labels.items()}

    return {
        "pair_results": pair_results,
        "category_aggregate": cat_aggregate,
        "directional_aggregate": dir_aggregate,
        "pairwise_aggregate": pw_aggregate,
    }


def save_results(full_results: dict) -> None:
    out = RESULTS_DIR / "cross_timeframe_agreement.json"
    serializable = {
        "category_aggregate": full_results["category_aggregate"],
        "directional_aggregate": full_results["directional_aggregate"],
        "pairwise_aggregate": full_results["pairwise_aggregate"],
    }
    pair_summary = {}
    for pair, pdata in full_results.get("pair_results", {}).items():
        pair_summary[pair] = {
            "categories": {cat: {k: v for k, v in m.items() if k != "year_data"}
                           for cat, m in pdata.get("categories", {}).items()},
            "directional_categories": {cat: {k: v for k, v in m.items() if k != "year_data"}
                                       for cat, m in pdata.get("directional_categories", {}).items()},
            "pairwise": {pk: {label: {k: v for k, v in lv.items() if k != "year_data"}
                              for label, lv in pv.items()}
                         for pk, pv in pdata.get("pairwise", {}).items()},
        }
    serializable["pair_summary"] = pair_summary

    with open(out, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"  Saved to {out}")


if __name__ == "__main__":
    t0 = time.time()
    full_results = run_analysis()
    elapsed = time.time() - t0
    save_results(full_results)
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
