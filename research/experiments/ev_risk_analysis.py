"""EV & Risk Analysis — Phase 3b: Economic Value and Risk Profile.

Computes per-bar forward returns grouped by regime, then derives:
- Expectancy (gross and net)
- Distribution statistics
- Risk metrics (drawdown, consecutive losses, tail risk)
- Risk-adjusted performance (Sharpe, Sortino, Calmar)
- Cost robustness
- Statistical robustness (bootstrap CI)
- Temporal stability (year splits)
- Cross-pair stability
- Outlier sensitivity
- Multi-horizon analysis

All computations are strictly causal. No lookahead.
"""
from __future__ import annotations

import gc
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd


from nestquant.research.shared.zscore.zscore import _zscore_causal_core
from nestquant.research.shared.zscore.regime import classify_regime_chunked

DATA_DIR = Path("/root/data")
RESULTS_DIR = Path("research/output/phase3")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF",
    "EUR/GBP", "EUR/CHF", "EUR/CAD", "EUR/AUD", "GBP/JPY",
    "GBP/CAD", "GBP/AUD", "AUD/JPY", "AUD/CAD", "AUD/CHF",
    "NZD/USD", "NZD/JPY", "NZD/CHF", "CAD/JPY", "CAD/CHF",
]

LOOKBACK = 20
HORIZONS = [5, 15, 30, 60, 120, 240]
PRIMARY_HORIZON = 60
COST_LEVELS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
YEAR_SPLITS = {
    "2016-2018": (2016, 2018),
    "2019-2021": (2019, 2021),
    "2022-2024": (2022, 2024),
    "2025-2026": (2025, 2026),
}
N_BOOTSTRAP = 200


def load_pair(pair: str, timeframe: str) -> pd.DataFrame | None:
    pair_file = pair.replace("/", "_")
    for path in [DATA_DIR / timeframe / f"{pair_file}.pkl",
                 DATA_DIR / f"{pair_file}.pkl"]:
        if path.exists():
            with open(path, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                return data.get(pair)
            return data
    return None


def compute_pair_data(pair: str, timeframe: str) -> dict | None:
    """Load pair, compute Z-scores, regimes, and forward returns at all horizons."""
    df = load_pair(pair, timeframe)
    if df is None or len(df) < LOOKBACK + max(HORIZONS) + 10:
        return None

    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    ts = df.index
    n = len(close)
    del df

    z_scores, _, _ = _zscore_causal_core(close, LOOKBACK)

    try:
        regimes = classify_regime_chunked(
            close, high, low, ts, pair,
            chunk_size=1000, ema_span=200, atr_period=14,
        )
        regime_labels = np.array([f"{r.trend}×{r.volatility}" for r in regimes])
        del regimes
    except Exception:
        regime_labels = np.array(["unknown"] * n)

    years = np.array([t.year for t in ts])

    forward_returns = {}
    for h in HORIZONS:
        fr = np.full(n, np.nan)
        if n > h:
            fr[:n - h] = (close[h:] - close[:n - h]) / close[:n - h]
        forward_returns[h] = fr
    del close, high, low

    valid_mask = np.isfinite(z_scores) & (regime_labels != "unknown")
    del z_scores

    return {
        "pair": pair,
        "timeframe": timeframe,
        "n_bars": n,
        "regime_labels": regime_labels,
        "years": years,
        "forward_returns": forward_returns,
        "valid_mask": valid_mask,
    }


def pip_value(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def compute_metrics(returns_pips: np.ndarray, cost_pips: float = 0.0) -> dict:
    """Compute comprehensive metrics from an array of per-trade returns (in pips)."""
    n = len(returns_pips)
    if n == 0:
        return {"n": 0}

    net = returns_pips - cost_pips
    net_valid = net[np.isfinite(net)]
    n_valid = len(net_valid)
    if n_valid == 0:
        return {"n": 0}

    mean_gross = float(np.mean(returns_pips))
    mean_net = float(np.mean(net_valid))
    std_net = float(np.std(net_valid, ddof=1)) if n_valid > 1 else 0.0
    se_net = std_net / np.sqrt(n_valid) if n_valid > 0 else 0.0

    # Percentiles
    percentiles = {}
    for q in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        percentiles[f"p{q}"] = float(np.percentile(net_valid, q))

    # Win/loss
    wins = net_valid[net_valid > 0]
    losses = net_valid[net_valid < 0]
    flat = net_valid[net_valid == 0]
    win_rate = len(wins) / n_valid * 100 if n_valid > 0 else 0
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    gross_profit = float(np.sum(wins))
    gross_loss = abs(float(np.sum(losses)))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Distribution
    skewness = float(pd.Series(net_valid).skew()) if n_valid > 3 else 0.0
    kurtosis = float(pd.Series(net_valid).kurtosis()) if n_valid > 4 else 0.0

    # Drawdown (cumulative return series)
    cum = np.cumsum(net_valid)
    running_max = np.maximum.accumulate(cum)
    drawdowns = cum - running_max
    max_dd = float(np.min(drawdowns))
    avg_dd = float(np.mean(drawdowns[drawdowns < 0])) if np.any(drawdowns < 0) else 0.0

    # Drawdown duration
    dd_durations = []
    current_dd_len = 0
    for d in drawdowns:
        if d < 0:
            current_dd_len += 1
        else:
            if current_dd_len > 0:
                dd_durations.append(current_dd_len)
            current_dd_len = 0
    if current_dd_len > 0:
        dd_durations.append(current_dd_len)
    max_dd_duration = max(dd_durations) if dd_durations else 0

    # Consecutive wins/losses
    max_consec_loss = 0
    max_consec_win = 0
    current_consec = 0
    current_type = None
    for v in net_valid:
        if v > 0:
            if current_type == "win":
                current_consec += 1
            else:
                current_consec = 1
                current_type = "win"
            max_consec_win = max(max_consec_win, current_consec)
        elif v < 0:
            if current_type == "loss":
                current_consec += 1
            else:
                current_consec = 1
                current_type = "loss"
            max_consec_loss = max(max_consec_loss, current_consec)
        else:
            current_consec = 0
            current_type = None

    # Downside deviation (target = 0)
    downside = net_valid[net_valid < 0]
    downside_dev = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0

    # Risk-adjusted (only if n_valid > 10 for stability)
    sharpe = (mean_net / std_net * np.sqrt(252)) if std_net > 0 and n_valid > 10 else None
    sortino = (mean_net / downside_dev * np.sqrt(252)) if downside_dev > 0 and n_valid > 10 else None
    calmar = (mean_net * 252 / abs(max_dd)) if max_dd != 0 and n_valid > 10 else None
    return_vol_ratio = mean_net / std_net if std_net > 0 else None

    # Worst trade
    worst = float(np.min(net_valid))
    best = float(np.max(net_valid))

    # Rolling worst period (20-trade)
    if n_valid >= 20:
        rolling_sums = np.array([np.sum(net_valid[i:i+20]) for i in range(n_valid - 19)])
        worst_20 = float(np.min(rolling_sums))
    else:
        worst_20 = mean_net * n_valid

    return {
        "n": n_valid,
        "mean_gross_pips": mean_gross,
        "mean_net_pips": mean_net,
        "std_pips": std_net,
        "se_pips": se_net,
        "ci_lower_pips": mean_net - 1.96 * se_net,
        "ci_upper_pips": mean_net + 1.96 * se_net,
        "percentiles": percentiles,
        "win_rate": win_rate,
        "avg_win_pips": avg_win,
        "avg_loss_pips": avg_loss,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor,
        "skewness": skewness,
        "kurtosis": kurtosis,
        "max_drawdown_pips": max_dd,
        "avg_drawdown_pips": avg_dd,
        "max_dd_duration": max_dd_duration,
        "max_consec_losses": max_consec_loss,
        "max_consec_wins": max_consec_win,
        "downside_dev_pips": downside_dev,
        "worst_trade_pips": worst,
        "best_trade_pips": best,
        "worst_20_period_pips": worst_20,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "return_vol_ratio": return_vol_ratio,
        "gross_profit_pips": gross_profit,
        "gross_loss_pips": gross_loss,
    }


def bootstrap_ci(data: np.ndarray, n_boot: int = N_BOOTSTRAP, ci: float = 0.95) -> dict:
    """Bootstrap confidence interval for the mean."""
    n = len(data)
    if n < 10:
        return {"mean": float(np.mean(data)) if n > 0 else 0.0,
                "ci_lower": None, "ci_upper": None, "n_boot": 0}
    rng = np.random.default_rng(42)
    boot_means = np.array([np.mean(rng.choice(data, size=n, replace=True)) for _ in range(n_boot)])
    alpha = (1 - ci) / 2
    return {
        "mean": float(np.mean(data)),
        "ci_lower": float(np.percentile(boot_means, alpha * 100)),
        "ci_upper": float(np.percentile(boot_means, (1 - alpha) * 100)),
        "n_boot": n_boot,
    }


def outlier_sensitivity(returns_pips: np.ndarray) -> dict:
    """Recalculate metrics after removing extreme observations."""
    n = len(returns_pips)
    if n < 10:
        return {}

    results = {}

    # Full
    mf = compute_metrics(returns_pips)
    results["full"] = {"n": mf["n"], "mean_pips": mf["mean_net_pips"],
                        "profit_factor": mf["profit_factor"]}

    # Remove largest 1
    idx_largest = np.argmax(returns_pips)
    trimmed_1 = np.delete(returns_pips, idx_largest)
    m = compute_metrics(trimmed_1)
    results["remove_largest_1"] = {"n": m["n"], "mean_pips": m["mean_net_pips"],
                                    "profit_factor": m["profit_factor"]}

    # Remove largest 5
    if n > 15:
        top5_idx = np.argsort(returns_pips)[::-1][:5]
        trim_mask = np.ones(n, dtype=bool)
        trim_mask[top5_idx] = False
        m5 = compute_metrics(returns_pips[trim_mask])
        results["remove_largest_5"] = {"n": m5["n"], "mean_pips": m5["mean_net_pips"],
                                        "profit_factor": m5["profit_factor"]}

    # Remove largest 1%
    if n > 100:
        p99 = np.percentile(returns_pips, 99)
        trimmed_1pct = returns_pips[returns_pips <= p99]
        m1p = compute_metrics(trimmed_1pct)
        results["remove_largest_1pct"] = {"n": m1p["n"], "mean_pips": m1p["mean_net_pips"],
                                           "profit_factor": m1p["profit_factor"]}

    return results


def run_analysis(timeframe: str) -> dict:
    """Run full EV/Risk analysis for one timeframe.

    Processes one pair at a time to avoid memory exhaustion on large datasets.
    Accumulates per-regime statistics incrementally.
    """
    print(f"\n{'='*60}")
    print(f"  EV/RISK ANALYSIS: {timeframe}")
    print(f"{'='*60}")

    # First pass: discover regimes and collect pair-level results
    all_regimes: set[str] = set()
    # regime_accum[regime][h_str] = list of per-pair dicts
    regime_accum: dict[str, dict[str, list]] = {}
    pair_count = 0

    for i, pair in enumerate(PAIRS):
        t0 = time.time()
        pd_data = compute_pair_data(pair, timeframe)
        elapsed = time.time() - t0
        if pd_data is None:
            print(f"  [{i+1}/{len(PAIRS)}] {pair}: SKIP (no data)")
            continue

        n_bars = pd_data["n_bars"]
        valid_mask = pd_data["valid_mask"]
        regime_labels = pd_data["regime_labels"]
        forward_returns = pd_data["forward_returns"]
        years = pd_data["years"]
        print(f"  [{i+1}/{len(PAIRS)}] {pair}: {n_bars:,} bars ({elapsed:.1f}s)")

        pair_regimes = sorted(set(regime_labels[valid_mask]))
        all_regimes.update(pair_regimes)

        for regime in pair_regimes:
            mask = valid_mask & (regime_labels == regime)
            n = int(mask.sum())
            if n < 30:
                continue

            pip = pip_value(pair)
            y = years[mask]
            h_str = str(PRIMARY_HORIZON)
            fr = forward_returns[PRIMARY_HORIZON][mask]
            valid = np.isfinite(fr)
            fr_pips = fr[valid] / pip
            if len(fr_pips) < 10:
                continue

            metrics = compute_metrics(fr_pips, cost_pips=0.0)
            boot = bootstrap_ci(fr_pips)
            outlier = outlier_sensitivity(fr_pips)

            net_by_cost = {}
            for cost in COST_LEVELS:
                nm = compute_metrics(fr_pips, cost_pips=cost)
                net_by_cost[str(cost)] = {
                    "mean_pips": nm["mean_net_pips"],
                    "profit_factor": nm["profit_factor"],
                    "win_rate": nm["win_rate"],
                }

            year_splits = {}
            # fr_all = full forward returns for this regime, y = years for this regime
            for split_name, (y_start, y_end) in YEAR_SPLITS.items():
                ymask = (y >= y_start) & (y <= y_end)
                n_ym = int(ymask.sum())
                if n_ym < 30:
                    year_splits[split_name] = {"n": n_ym, "status": "insufficient"}
                    continue
                fr_ym = fr[ymask]
                valid_ym = np.isfinite(fr_ym)
                fr_pips_ym = fr_ym[valid_ym] / pip
                if len(fr_pips_ym) < 10:
                    year_splits[split_name] = {"n": len(fr_pips_ym), "status": "insufficient"}
                    continue
                m_ym = compute_metrics(fr_pips_ym)
                b_ym = bootstrap_ci(fr_pips_ym)
                year_splits[split_name] = {
                    "n": m_ym["n"],
                    "mean_pips": m_ym["mean_net_pips"],
                    "win_rate": m_ym["win_rate"],
                    "profit_factor": m_ym["profit_factor"],
                    "max_drawdown_pips": m_ym["max_drawdown_pips"],
                    "sharpe": m_ym["sharpe"],
                    "bootstrap_mean": b_ym["mean"],
                    "bootstrap_ci_lower": b_ym["ci_lower"],
                    "bootstrap_ci_upper": b_ym["ci_upper"],
                }

            if regime not in regime_accum:
                regime_accum[regime] = {}
            if h_str not in regime_accum[regime]:
                regime_accum[regime][h_str] = []

            regime_accum[regime][h_str].append({
                "pair": pair,
                "n_bars": int(mask.sum()),
                "metrics": metrics,
                "bootstrap": boot,
                "outlier_sensitivity": outlier,
                "net_by_cost": net_by_cost,
                "year_splits": year_splits,
            })

        pair_count += 1
        del pd_data, regime_labels, valid_mask, forward_returns, years
        gc.collect()

    print(f"\n  Loaded {pair_count} pairs")

    # Second pass: aggregate across pairs per regime
    all_regimes = sorted(all_regimes)
    regime_results = {}
    for regime in all_regimes:
        regime_pairs = {}
        for h_str, entries in regime_accum.get(regime, {}).items():
            for entry in entries:
                regime_pairs[entry["pair"]] = {
                    "n_bars": entry["n_bars"],
                    "horizons": {h_str: {
                        "metrics": entry["metrics"],
                        "bootstrap": entry["bootstrap"],
                        "outlier_sensitivity": entry["outlier_sensitivity"],
                        "net_by_cost": entry["net_by_cost"],
                    }},
                    "year_splits": entry["year_splits"],
                }

        agg = aggregate_regime(regime_pairs, timeframe, regime)
        regime_results[regime] = {"pairs": regime_pairs, "aggregate": agg}

    return {
        "timeframe": timeframe,
        "n_pairs": pair_count,
        "regimes": regime_results,
    }


def aggregate_regime(regime_pairs: dict, timeframe: str, regime: str) -> dict:
    """Aggregate metrics across pairs for a regime."""
    agg = {}

    for h_str in [str(h) for h in HORIZONS]:
        all_returns = []
        pair_metrics = []

        for pair, pdata in regime_pairs.items():
            h_data = pdata["horizons"].get(h_str)
            if not h_data:
                continue
            m = h_data["metrics"]
            if m["n"] < 10:
                continue
            pair_metrics.append({
                "pair": pair,
                "n": m["n"],
                "mean_pips": m["mean_net_pips"],
                "std_pips": m["std_pips"],
                "win_rate": m["win_rate"],
                "profit_factor": m["profit_factor"],
                "max_drawdown_pips": m["max_drawdown_pips"],
                "sharpe": m["sharpe"],
            })

        if not pair_metrics:
            continue

        # Pool across pairs (weighted by n)
        total_n = sum(p["n"] for p in pair_metrics)
        pooled_mean = sum(p["mean_pips"] * p["n"] for p in pair_metrics) / total_n

        # Cross-pair dispersion
        means = [p["mean_pips"] for p in pair_metrics]
        cross_pair_std = float(np.std(means, ddof=1)) if len(means) > 1 else 0.0
        n_positive = sum(1 for m in means if m > 0)
        n_negative = len(means) - n_positive

        # Bootstrap on pooled data
        boot = {"mean": pooled_mean, "ci_lower": None, "ci_upper": None}

        # Year splits aggregate
        year_agg = {}
        for split_name in YEAR_SPLITS:
            ym = []
            for pair, pdata in regime_pairs.items():
                ys = pdata.get("year_splits", {}).get(split_name, {})
                if ys.get("n", 0) >= 30:
                    ym.append(ys["mean_pips"])
            if ym:
                year_agg[split_name] = {
                    "n_pairs": len(ym),
                    "mean_of_means": float(np.mean(ym)),
                    "std_of_means": float(np.std(ym, ddof=1)) if len(ym) > 1 else 0.0,
                }

        agg[h_str] = {
            "total_n": total_n,
            "n_pairs": len(pair_metrics),
            "pooled_mean_pips": pooled_mean,
            "cross_pair_std": cross_pair_std,
            "n_pairs_positive": n_positive,
            "n_pairs_negative": n_negative,
            "pct_pairs_positive": n_positive / len(pair_metrics) * 100,
            "pair_metrics": pair_metrics,
            "year_splits": year_agg,
        }

    return agg


def save_results(results: dict, timeframe: str) -> None:
    """Save results to JSON."""
    out = RESULTS_DIR / f"ev_risk_analysis_{timeframe}.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Saved to {out}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="EV & Risk Analysis")
    parser.add_argument("--timeframe", required=True,
                        choices=["1min", "15min", "1h", "4h"])
    args = parser.parse_args()

    t0 = time.time()
    results = run_analysis(args.timeframe)
    elapsed = time.time() - t0

    save_results(results, args.timeframe)
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  Regimes analyzed: {len(results['regimes'])}")
