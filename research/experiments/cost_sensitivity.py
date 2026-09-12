"""Cost sensitivity analysis per regime with Newey-West HAC inference.

Usage:
    cd /root/that && .venv/bin/python -u scripts/cost_sensitivity.py --timeframe 1h
    cd /root/that && .venv/bin/python -u scripts/cost_sensitivity.py --timeframe 4h
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


from nestquant.research.phase3_research import prepare_pair

RESULTS_DIR = Path("research/output/phase3")

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF",
    "EUR/GBP", "EUR/CHF", "EUR/CAD", "EUR/AUD", "GBP/JPY",
    "GBP/CAD", "GBP/AUD", "AUD/JPY", "AUD/CAD", "AUD/CHF",
    "NZD/USD", "NZD/JPY", "NZD/CHF", "CAD/JPY", "CAD/CHF",
]

PAIR_PIP = {
    "EUR/USD": 0.0001, "GBP/USD": 0.0001, "USD/JPY": 0.01,
    "AUD/USD": 0.0001, "USD/CHF": 0.0001, "EUR/GBP": 0.0001,
    "EUR/CHF": 0.0001, "EUR/CAD": 0.0001, "EUR/AUD": 0.0001,
    "GBP/JPY": 0.01, "GBP/CAD": 0.0001, "GBP/AUD": 0.0001,
    "AUD/JPY": 0.01, "AUD/CAD": 0.0001, "AUD/CHF": 0.0001,
    "NZD/USD": 0.0001, "NZD/JPY": 0.01, "NZD/CHF": 0.0001,
    "CAD/JPY": 0.01, "CAD/CHF": 0.0001,
}

PAIR_PV = {
    "EUR/USD": 100000, "GBP/USD": 100000, "USD/JPY": 100000,
    "AUD/USD": 100000, "USD/CHF": 100000, "EUR/GBP": 100000,
    "EUR/CHF": 100000, "EUR/CAD": 100000, "EUR/AUD": 100000,
    "GBP/JPY": 100000, "GBP/CAD": 100000, "GBP/AUD": 100000,
    "AUD/JPY": 100000, "AUD/CAD": 100000, "AUD/CHF": 100000,
    "NZD/USD": 100000, "NZD/JPY": 100000, "NZD/CHF": 100000,
    "CAD/JPY": 100000, "CAD/CHF": 100000,
}


def newey_west_hac(x: np.ndarray, max_lags: int | None = None) -> float:
    """Newey-West HAC standard error of the mean.

    Args:
        x: 1D array of returns
        max_lags: number of lags (default: int(4 * (n/100)^(2/9)))

    Returns:
        HAC-robust standard error of mean(x)
    """
    n = len(x)
    if n < 2:
        return float(np.std(x, ddof=1)) / np.sqrt(n) if n > 0 else 0.0

    mean_x = np.mean(x)
    demeaned = x - mean_x

    if max_lags is None:
        max_lags = int(4 * (n / 100) ** (2 / 9))
    max_lags = max(1, min(max_lags, n - 1))

    gamma_0 = float(np.mean(demeaned ** 2))

    variance = gamma_0
    for lag in range(1, max_lags + 1):
        gamma_lag = float(np.mean(demeaned[lag:] * demeaned[:-lag]))
        weight = 1.0 - lag / (max_lags + 1)
        variance += 2.0 * weight * gamma_lag

    return np.sqrt(max(variance, 0) / n)


def run_cost_analysis(timeframe: str = "1h", lookback: int = 20) -> dict:
    all_results = {}
    regime_agg = {}

    for i, pair in enumerate(PAIRS):
        print(f"[{i+1}/{len(PAIRS)}] {pair}...", flush=True)
        t0 = time.time()
        data = prepare_pair(pair, timeframe=timeframe, lookback=lookback)
        if data is None:
            continue

        pip = PAIR_PIP[pair]
        pv = PAIR_PV[pair]
        pair_results = {}

        for horizon in [h for h in data.horizons if h >= 60]:
            if horizon not in data.forward_returns:
                continue
            fr = data.forward_returns[horizon]

            regime_costs = {}
            for trend in ["near_ema", "weak_trend", "strong_trend"]:
                for vol in ["low_vol", "mid_vol", "high_vol"]:
                    mask = np.array([
                        t == trend and v == vol
                        for t, v in zip(data.regime_trend, data.regime_vol, strict=True)
                    ])
                    valid = mask & ~np.isnan(data.z_scores) & ~np.isnan(fr)
                    z = data.z_scores[valid]
                    returns = fr[valid]

                    extreme_mask = np.abs(z) > 2
                    n_extreme = int(np.sum(extreme_mask))
                    if n_extreme < 50:
                        continue

                    z_extreme = z[extreme_mask]
                    fr_extreme = returns[extreme_mask]
                    direction = np.where(z_extreme < 0, 1, -1)
                    return_pips = fr_extreme / pip * direction

                    # Newey-West HAC standard error
                    max_lags = min(int(4 * (n_extreme / 100) ** (2 / 9)), n_extreme - 1)
                    hac_se = newey_west_hac(return_pips, max_lags=max_lags)
                    mean_pips = float(np.mean(return_pips))

                    # Break-even cost
                    breakeven = mean_pips

                    # Cost scenarios
                    scenarios = []
                    for spread in [0.5, 1.0, 1.5, 2.0, 3.0]:
                        for slippage in [0.0, 0.3, 0.5]:
                            cost_pips = spread + slippage
                            net = return_pips - cost_pips
                            expectancy = float(np.mean(net))
                            hit_rate = float(np.mean(net > 0) * 100)

                            # z-test for expectancy > 0
                            if hac_se > 0:
                                z_stat = expectancy / hac_se
                            else:
                                z_stat = 0.0

                            scenarios.append({
                                "spread_pips": spread,
                                "slippage_pips": slippage,
                                "cost_pips": cost_pips,
                                "expectancy_pips": round(expectancy, 6),
                                "hit_rate": round(hit_rate, 2),
                                "z_stat": round(z_stat, 3),
                                "significant_5pct": abs(z_stat) > 1.96,
                            })

                    regime_key = f"{trend}×{vol}"
                    regime_costs[regime_key] = {
                        "n_extreme": n_extreme,
                        "mean_return_pips": round(mean_pips, 6),
                        "hac_se_pips": round(hac_se, 6),
                        "breakeven_cost_pips": round(breakeven, 4),
                        "scenarios": scenarios,
                    }

                    # Aggregate
                    agg_key = f"{regime_key}"
                    if agg_key not in regime_agg:
                        regime_agg[agg_key] = {
                            "returns_pips": [],
                            "n_extreme": 0,
                        }
                    regime_agg[agg_key]["returns_pips"].append(return_pips)
                    regime_agg[agg_key]["n_extreme"] += n_extreme

            pair_results[f"h{horizon}"] = regime_costs

        elapsed = time.time() - t0
        print(f"  {elapsed:.1f}s", flush=True)
        all_results[pair] = pair_results

    # Aggregate across pairs per regime
    agg_results = {}
    for regime_key, agg in regime_agg.items():
        all_ret = np.concatenate(agg["returns_pips"])
        n = len(all_ret)
        mean_pips = float(np.mean(all_ret))
        max_lags = min(int(4 * (n / 100) ** (2 / 9)), n - 1)
        hac_se = newey_west_hac(all_ret, max_lags=max_lags)

        scenarios = []
        for spread in [0.5, 1.0, 1.5, 2.0, 3.0]:
            for slippage in [0.0, 0.3, 0.5]:
                cost_pips = spread + slippage
                net = all_ret - cost_pips
                expectancy = float(np.mean(net))
                hit_rate = float(np.mean(net > 0) * 100)
                z_stat = expectancy / hac_se if hac_se > 0 else 0.0
                scenarios.append({
                    "spread_pips": spread,
                    "slippage_pips": slippage,
                    "cost_pips": cost_pips,
                    "expectancy_pips": round(expectancy, 6),
                    "hit_rate": round(hit_rate, 2),
                    "z_stat": round(z_stat, 3),
                    "significant_5pct": abs(z_stat) > 1.96,
                })

        agg_results[regime_key] = {
            "n_extreme": agg["n_extreme"],
            "mean_return_pips": round(mean_pips, 6),
            "hac_se_pips": round(hac_se, 6),
            "breakeven_cost_pips": round(mean_pips, 4),
            "scenarios": scenarios,
        }

    return {
        "timeframe": timeframe,
        "lookback": lookback,
        "pair_results": all_results,
        "aggregate": agg_results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run cost sensitivity analysis")
    parser.add_argument("--timeframe", default="1h",
                        choices=["1min", "5min", "15min", "30min", "1h", "4h"],
                        help="Data timeframe (default: 1h)")
    parser.add_argument("--lookback", type=int, default=20,
                        help="Z-score lookback in bars (default: 20)")
    args = parser.parse_args()

    t0 = time.time()
    results = run_cost_analysis(timeframe=args.timeframe, lookback=args.lookback)
    elapsed = time.time() - t0
    print(f"\nTotal: {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)

    out_path = RESULTS_DIR / f"cost_sensitivity_{args.timeframe}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved to {out_path}", flush=True)

    # Print summary
    print(f"\n=== Aggregate Cost Sensitivity ({args.timeframe}, h=60) ===")
    print(f"{'Regime':<30} {'Mean(pips)':>10} {'HAC SE':>8} {'B/E Cost':>10} {'N':>8}")
    for k, v in sorted(results["aggregate"].items(), key=lambda x: -x[1]["n_extreme"]):
        print(f"{k:<30} {v['mean_return_pips']:>+10.4f} {v['hac_se_pips']:>8.4f} "
              f"{v['breakeven_cost_pips']:>+10.4f} {v['n_extreme']:>8,}")
