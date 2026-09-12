"""
Phase 12: Regime-Dependency Validation for Currency-Strength Hypothesis

The frozen candidate from Phase 11:
    currency-strength gap (D40-D70)
    + JPY crosses
    + 12:00-16:00 UTC session
    + 4h horizon

Phase 12 does NOT optimize. It validates whether the Phase 11 result
represents a stable conditional economic phenomenon or is primarily
a 2024-2026 JPY regime effect.
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
from config import (
    ALL_PAIRS, STRENGTH_LOOKBACKS, STRENGTH_TOP_N,
    STRENGTH_MIN_DIVERGENCE, STRENGTH_NORMALIZE_WINDOW as NORM_WINDOW,
)

# ── Frozen candidate parameters (from Phase 11 discovery) ──────────────
FROZEN_GAP_Q40 = -24.4758
FROZEN_GAP_Q70 = 56.1954
FROZEN_SESSION_START = 12
FROZEN_SESSION_END = 16
HORIZON = "4h"
H_BARS = 8

# ── Time periods ───────────────────────────────────────────────────────
DISCOVERY_START = "2016-01-01"
DISCOVERY_END = "2022-12-31"
HOLDOUT_START = "2023-01-01"
HOLDOUT_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2026-07-31"

# ── Cost model ─────────────────────────────────────────────────────────
COST_PIPS = 1.72
PAIR_COST_PIPS = {
    "EUR/USD": 1.2, "GBP/USD": 1.8, "USD/JPY": 1.4, "USD/CHF": 1.8,
    "USD/CAD": 2.0, "AUD/USD": 1.6, "NZD/USD": 2.4, "EUR/GBP": 1.8,
    "EUR/JPY": 2.0, "EUR/CHF": 2.2, "EUR/CAD": 2.6, "EUR/AUD": 3.2,
    "GBP/JPY": 3.0, "GBP/CHF": 3.0, "GBP/CAD": 3.4, "GBP/AUD": 3.8,
    "CHF/JPY": 2.4, "CAD/JPY": 2.2, "AUD/JPY": 2.0, "NZD/JPY": 2.8,
    "AUD/CAD": 2.8, "AUD/CHF": 2.8, "NZD/CHF": 3.2, "CAD/CHF": 3.0,
}

JPY_PAIRS = ["USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY", "CHF/JPY"]
DATA_DIR = Path("/root/data")
RNG_SEED = 42
N_PERM = 200


# ═══════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE (reused from Phase 11)
# ═══════════════════════════════════════════════════════════════════════

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


def compute_forward_returns_4h(pair_data: dict[str, pd.DataFrame]) -> dict[str, np.ndarray]:
    fwd = {}
    for pair, df in pair_data.items():
        close = df["close"].values.astype(np.float64)
        pf = pip_factor(pair)
        n = len(close)
        ret_pips = np.full(n, np.nan)
        valid_end = n - H_BARS
        if valid_end > 0:
            diff = close[H_BARS:n] - close[:n - H_BARS]
            ret_pips[:valid_end] = diff * pf
        fwd[pair] = ret_pips
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


def compute_metrics(f: np.ndarray, cost: float = 0.0) -> dict[str, Any]:
    f = f[~np.isnan(f)]
    n = len(f)
    if n < 30:
        return {"n": n, "mean": 0.0, "median": 0.0, "std": 0.0, "win_rate": 0.5,
                "net": 0.0, "pf": 1.0, "t": 0.0, "p": 1.0, "be_cost": 0.0,
                "total_pnl": 0.0, "max_dd": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    mean_raw = float(np.mean(f))
    mean_net = mean_raw - cost
    wins = f > 0
    losses = f < 0
    win_rate = float(wins.sum() / n)
    gross_profit = float(f[wins].sum()) if wins.any() else 0.0
    gross_loss = float(abs(f[losses].sum())) if losses.any() else 1e-10
    pf = gross_profit / gross_loss if gross_loss > 0 else 999.0
    if n > 1 and np.std(f) > 0:
        t_stat = mean_raw / (np.std(f) / np.sqrt(n))
        p_val = 2 * stats.t.sf(abs(t_stat), df=n - 1)
    else:
        t_stat, p_val = 0.0, 1.0
    positive_trades = f[f > 0]
    be_cost = float(np.mean(positive_trades)) if len(positive_trades) > 0 else 0.0
    total_pnl = float(np.sum(f)) - cost * n
    cum = np.cumsum(f) - cost * np.arange(1, n + 1)
    running_max = np.maximum.accumulate(cum)
    dd = running_max - cum
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0
    ci_low = mean_raw - 1.96 * np.std(f) / np.sqrt(n)
    ci_high = mean_raw + 1.96 * np.std(f) / np.sqrt(n)
    return {
        "n": n, "mean": round(mean_raw, 6), "median": round(float(np.median(f)), 6),
        "std": round(float(np.std(f)), 6), "win_rate": round(win_rate, 6),
        "net": round(mean_net, 6), "pf": round(pf, 4),
        "t": round(t_stat, 4), "p": round(p_val, 6),
        "be_cost": round(be_cost, 4), "total_pnl": round(total_pnl, 2),
        "max_dd": round(max_dd, 2), "ci_low": round(ci_low, 6), "ci_high": round(ci_high, 6),
    }


def apply_frozen_candidate(obs: pd.DataFrame) -> pd.DataFrame:
    return obs[
        (obs["gap"] >= FROZEN_GAP_Q40) & (obs["gap"] <= FROZEN_GAP_Q70)
        & obs["is_jpy"]
        & (obs["hour"] >= FROZEN_SESSION_START) & (obs["hour"] < FROZEN_SESSION_END)
    ].copy()


def segment_by_year(obs: pd.DataFrame) -> dict[int, pd.DataFrame]:
    obs["year"] = obs["ts"].dt.year
    return {y: g for y, g in obs.groupby("year")}


# ═══════════════════════════════════════════════════════════════════════
# REGIME CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════

def compute_jpy_vol_regime(
    pair_data: dict[str, pd.DataFrame],
    jpy_pairs: list[str],
    window: int = 480,
) -> pd.Series:
    vols = []
    for pair in jpy_pairs:
        if pair not in pair_data:
            continue
        df = pair_data[pair]
        close = df["close"].values.astype(np.float64)
        ret = np.diff(np.log(close + 1e-10))
        ret_series = pd.Series(ret, index=df.index[1:])
        v = ret_series.rolling(window).std()
        vols.append(v)
    if not vols:
        return pd.Series(dtype=float)
    vol_df = pd.concat(vols, axis=1)
    avg_vol = vol_df.mean(axis=1)
    tercile_edges = avg_vol.quantile([0.3333, 0.6667]).values
    regime = pd.Series(np.nan, index=avg_vol.index)
    regime[avg_vol.notna()] = np.digitize(avg_vol[avg_vol.notna()], tercile_edges)
    return regime


def compute_jpy_trend_persistence(
    pair_data: dict[str, pd.DataFrame],
    jpy_pairs: list[str],
    window: int = 480,
    autocorr_lag: int = 48,
) -> pd.Series:
    diffs = []
    for pair in jpy_pairs:
        if pair not in pair_data:
            continue
        df = pair_data[pair]
        close = df["close"].values.astype(np.float64)
        ret = np.diff(np.log(close + 1e-10))
        ret_series = pd.Series(ret, index=df.index[1:])
        diffs.append(ret_series)
    if not diffs:
        return pd.Series(dtype=float)
    avg_ret = pd.concat(diffs, axis=1).mean(axis=1)
    persistence = avg_ret.rolling(window).apply(
        lambda x: x.autocorr(lag=min(autocorr_lag, len(x) - 1)) if len(x) > autocorr_lag + 1 else np.nan,
        raw=False,
    )
    tercile_edges = persistence.quantile([0.3333, 0.6667]).values
    regime = pd.Series(np.nan, index=persistence.index)
    regime[persistence.notna()] = np.digitize(persistence[persistence.notna()], tercile_edges)
    return regime


def compute_ema200_regime(pair_data: dict[str, pd.DataFrame], pair: str) -> np.ndarray:
    if pair not in pair_data:
        return np.array([])
    close = pair_data[pair]["close"].values.astype(np.float64)
    ema = pd.Series(close).ewm(span=200, adjust=False).mean().values
    return (close > ema).astype(float)


# ═══════════════════════════════════════════════════════════════════════
# PERMUTATION TEST
# ═══════════════════════════════════════════════════════════════════════

def permutation_test_regime(obs: pd.DataFrame, n_perm: int = N_PERM, seed: int = RNG_SEED) -> dict:
    rng = np.random.RandomState(seed)
    actual_returns = obs["fwd_return"].values
    actual_mean = float(np.mean(actual_returns))

    null_means = np.empty(n_perm)
    for i in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=len(actual_returns))
        perm_returns = actual_returns * signs
        null_means[i] = float(np.mean(perm_returns))

    p_value = float(np.mean(np.abs(null_means) >= np.abs(actual_mean)))
    ci_low = float(np.percentile(null_means, 2.5))
    ci_high = float(np.percentile(null_means, 97.5))
    return {
        "observed_mean": round(actual_mean, 6),
        "null_mean": round(float(np.mean(null_means)), 6),
        "null_std": round(float(np.std(null_means)), 6),
        "p_value": round(p_value, 6),
        "ci_95_low": round(ci_low, 6),
        "ci_95_high": round(ci_high, 6),
        "null_distribution": null_means.tolist(),
    }


# ═══════════════════════════════════════════════════════════════════════
# FIGURES
# ═══════════════════════════════════════════════════════════════════════

def generate_figures(results: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    # Fig 1: Year-by-year expectancy
    yby = results.get("year_by_year", {})
    if yby:
        years = sorted(yby.keys())
        means = [yby[y]["mean"] for y in years]
        nets = [yby[y]["net"] for y in years]
        colors = ["green" if m > 0 else "red" for m in nets]
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.bar(range(len(years)), nets, color=colors, alpha=0.7)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years, rotation=45)
        ax.set_ylabel("Net Expectancy (pip)")
        ax.set_title("Phase 12: Year-by-Year Net Expectancy (Frozen Candidate, 4h)")
        ax.axhline(y=0, color="black", linewidth=0.5)
        ax.axhline(y=-COST_PIPS, color="red", linewidth=0.5, linestyle="--", label=f"Cost = {COST_PIPS} pip")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "01_year_by_year.png", dpi=150)
        plt.close()

    # Fig 2: Discovery vs OOS vs Holdout
    comp = results.get("holdout_comparison", {})
    if comp:
        labels = list(comp.keys())
        means = [comp[k]["mean"] for k in labels]
        nets = [comp[k]["net"] for k in labels]
        fig, ax = plt.subplots(figsize=(8, 5))
        x = range(len(labels))
        ax.bar(x, means, alpha=0.5, label="Gross", width=0.4)
        ax.bar([i + 0.4 for i in x], nets, alpha=0.7, label="Net", width=0.4)
        ax.set_xticks([i + 0.2 for i in x])
        ax.set_xticklabels(labels)
        ax.set_ylabel("Expectancy (pip)")
        ax.set_title("Phase 12: Discovery vs Holdout vs OOS")
        ax.legend()
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "02_holdout_comparison.png", dpi=150)
        plt.close()

    # Fig 3: JPY pair comparison
    pair_res = results.get("pair_generalization", {})
    if pair_res:
        pairs = sorted(pair_res.keys())
        means = [pair_res[p]["mean"] for p in pairs]
        nets = [pair_res[p]["net"] for p in pairs]
        colors = ["green" if n > 0 else "red" for n in nets]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(range(len(pairs)), nets, color=colors, alpha=0.7)
        ax.set_xticks(range(len(pairs)))
        ax.set_xticklabels(pairs, rotation=45)
        ax.set_ylabel("Net Expectancy (pip)")
        ax.set_title("Phase 12: Per-Pair Net Expectancy (All JPY Crosses)")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "03_pair_comparison.png", dpi=150)
        plt.close()

    # Fig 4: Volatility regime expectancy
    vol_res = results.get("volatility_regime", {})
    if vol_res:
        regimes = sorted(vol_res.keys(), key=lambda x: vol_res[x].get("mean", 0))
        means = [vol_res[r]["mean"] for r in regimes]
        nets = [vol_res[r]["net"] for r in regimes]
        labels = ["LOW", "MID", "HIGH"][:len(regimes)]
        fig, ax = plt.subplots(figsize=(8, 5))
        x = range(len(regimes))
        ax.bar(x, means, alpha=0.5, label="Gross", width=0.4)
        ax.bar([i + 0.4 for i in x], nets, alpha=0.7, label="Net", width=0.4)
        ax.set_xticks([i + 0.2 for i in x])
        ax.set_xticklabels(labels[:len(regimes)])
        ax.set_ylabel("Expectancy (pip)")
        ax.set_title("Phase 12: JPY Volatility Regime Expectancy")
        ax.legend()
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "04_volatility_regime.png", dpi=150)
        plt.close()

    # Fig 5: Trend persistence regime
    pers_res = results.get("persistence_regime", {})
    if pers_res:
        regimes = sorted(pers_res.keys(), key=lambda x: pers_res[x].get("mean", 0))
        means = [pers_res[r]["mean"] for r in regimes]
        nets = [pers_res[r]["net"] for r in regimes]
        labels = ["LOW", "MID", "HIGH"][:len(regimes)]
        fig, ax = plt.subplots(figsize=(8, 5))
        x = range(len(regimes))
        ax.bar(x, means, alpha=0.5, label="Gross", width=0.4)
        ax.bar([i + 0.4 for i in x], nets, alpha=0.7, label="Net", width=0.4)
        ax.set_xticks([i + 0.2 for i in x])
        ax.set_xticklabels(labels[:len(regimes)])
        ax.set_ylabel("Expectancy (pip)")
        ax.set_title("Phase 12: JPY Trend-Persistence Regime Expectancy")
        ax.legend()
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "05_persistence_regime.png", dpi=150)
        plt.close()

    # Fig 6: Cumulative PnL by year
    if yby:
        years = sorted(yby.keys())
        cum_pnl = []
        running = 0
        for y in years:
            running += yby[y].get("total_pnl", 0)
            cum_pnl.append(running)
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(years, cum_pnl, marker="o", linewidth=2)
        ax.fill_between(years, cum_pnl, alpha=0.2)
        ax.set_ylabel("Cumulative PnL (pip)")
        ax.set_title("Phase 12: Cumulative PnL by Year")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "06_cumulative_pnl.png", dpi=150)
        plt.close()

    # Fig 7: Cost sensitivity
    cs = results.get("cost_sensitivity", {})
    if cs:
        cost_keys = [k for k in cs.keys() if k.startswith("COST_")]
        costs = sorted(cost_keys)
        nets = [cs[c]["net"] for c in costs]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(range(len(costs)), nets, alpha=0.7)
        ax.set_xticks(range(len(costs)))
        ax.set_xticklabels([f"{c}" for c in costs], rotation=45)
        ax.set_ylabel("Net Expectancy (pip)")
        ax.set_title("Phase 12: Cost Sensitivity (Full OOS)")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "07_cost_sensitivity.png", dpi=150)
        plt.close()

    # Fig 8: Permutation null distribution
    perm = results.get("permutation", {})
    if perm and "null_distribution" in perm:
        null_dist = np.array(perm["null_distribution"])
        observed = perm["observed_mean"]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(null_dist, bins=50, alpha=0.7, density=True, label="Null distribution")
        ax.axvline(observed, color="red", linewidth=2, label=f"Observed = {observed:.4f}")
        ax.set_xlabel("Mean Return (pip)")
        ax.set_ylabel("Density")
        ax.set_title(f"Phase 12: Permutation Test (p = {perm['p_value']:.4f})")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "08_permutation.png", dpi=150)
        plt.close()

    # Fig 9: Discovery/OOS magnitude comparison
    mag = results.get("magnitude_gap", {})
    if mag:
        categories = [c for c in mag.keys() if isinstance(mag[c], dict) and "discovery_mean" in mag[c]]
        disc_means = [mag[c]["discovery_mean"] for c in categories]
        oos_means = [mag[c]["oos_mean"] for c in categories]
        fig, ax = plt.subplots(figsize=(10, 5))
        x = range(len(categories))
        ax.bar(x, disc_means, alpha=0.5, label="Discovery", width=0.4)
        ax.bar([i + 0.4 for i in x], oos_means, alpha=0.7, label="OOS", width=0.4)
        ax.set_xticks([i + 0.2 for i in x])
        ax.set_xticklabels(categories, rotation=45)
        ax.set_ylabel("Mean Return (pip)")
        ax.set_title("Phase 12: Discovery vs OOS Magnitude")
        ax.legend()
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "09_magnitude_gap.png", dpi=150)
        plt.close()

    print(f"  Figures saved to {fig_dir}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase 12: Regime-Dependency Validation")
    print("Frozen candidate: gap(D40-D70) + JPY + session(12-16) @ 4h")
    print("=" * 70)

    # ── Load data ──────────────────────────────────────────────────────
    print("\n[1] Loading pair data...")
    pair_data = load_pair_data(ALL_PAIRS)
    print(f"  Loaded {len(pair_data)} pairs")

    jpy_available = [p for p in JPY_PAIRS if p in pair_data]
    print(f"  JPY pairs available: {jpy_available}")

    # ── Compute strength differentials ─────────────────────────────────
    print("\n[2] Computing currency strength differentials...")
    strength_diff = compute_strength_differential(pair_data, ALL_PAIRS)
    print(f"  Shape: {strength_diff.shape}")

    # ── Compute forward returns (4h only) ──────────────────────────────
    print("\n[3] Computing 4h forward returns...")
    fwd = compute_forward_returns_4h(pair_data)
    print(f"  Computed for {len(fwd)} pairs")

    # ── Build observation table ────────────────────────────────────────
    print("\n[4] Building observation table...")
    rows = []
    for pair in ALL_PAIRS:
        if pair not in pair_data or pair not in strength_diff.columns:
            continue
        d_vals = strength_diff[pair].values
        pair_idx = pair_data[pair].index
        min_len = min(len(d_vals), len(pair_idx))
        d_vals = d_vals[:min_len]
        p_idx = pair_idx[:min_len]
        f_vals = fwd[pair]
        f_min = min(len(f_vals), min_len)
        f_vals = f_vals[:f_min]
        p_idx = p_idx[:f_min]
        d_vals = d_vals[:f_min]
        hour = p_idx.hour.values
        is_jpy = "JPY" in pair
        for i in range(f_min):
            if np.isnan(d_vals[i]) or np.isnan(f_vals[i]):
                continue
            rows.append({
                "pair": pair, "gap": d_vals[i], "fwd_return": f_vals[i],
                "hour": int(hour[i]), "is_jpy": is_jpy, "ts": p_idx[i],
            })
    obs = pd.DataFrame(rows)
    print(f"  Total observations: {len(obs)}")

    # ── Apply frozen candidate ─────────────────────────────────────────
    print("\n[5] Applying frozen candidate...")
    candidate = apply_frozen_candidate(obs)
    print(f"  Candidate observations: {len(candidate)}")

    # ── Period masks ───────────────────────────────────────────────────
    disc = candidate[(candidate["ts"] >= DISCOVERY_START) & (candidate["ts"] <= DISCOVERY_END)]
    hold = candidate[(candidate["ts"] >= HOLDOUT_START) & (candidate["ts"] <= HOLDOUT_END)]
    oos = candidate[(candidate["ts"] >= OOS_START) & (candidate["ts"] <= OOS_END)]
    print(f"  Discovery: {len(disc)}, Holdout (2023): {len(hold)}, OOS: {len(oos)}")

    results: dict[str, Any] = {
        "phase": "12",
        "title": "Regime-Dependency Validation",
        "frozen_candidate": {
            "gap_q40": FROZEN_GAP_Q40, "gap_q70": FROZEN_GAP_Q70,
            "session": f"{FROZEN_SESSION_START}-{FROZEN_SESSION_END} UTC",
            "horizon": HORIZON,
        },
    }

    # ═══════════════════════════════════════════════════════════════════
    # 1. INDEPENDENT TEMPORAL HOLDOUT
    # ═══════════════════════════════════════════════════════════════════
    print("\n[6] Section 1: Independent Temporal Holdout...")
    holdout_comparison = {}
    for label, subset in [("discovery_2016-2022", disc), ("holdout_2023", hold), ("oos_2024-2026", oos)]:
        f = subset["fwd_return"].values
        metrics = compute_metrics(f, COST_PIPS)
        holdout_comparison[label] = metrics
        print(f"  {label}: n={metrics['n']}, gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
              f"wr={metrics['win_rate']:.4f}, pf={metrics['pf']:.4f}, p={metrics['p']:.4f}")
    results["holdout_comparison"] = holdout_comparison

    # ═══════════════════════════════════════════════════════════════════
    # 2. YEAR-BY-YEAR ANALYSIS
    # ═══════════════════════════════════════════════════════════════════
    print("\n[7] Section 2: Year-by-Year Analysis...")
    candidate_with_year = candidate.copy()
    candidate_with_year["year"] = candidate_with_year["ts"].dt.year
    year_by_year = {}
    for year, group in candidate_with_year.groupby("year"):
        f = group["fwd_return"].values
        metrics = compute_metrics(f, COST_PIPS)
        year_by_year[int(year)] = metrics
        print(f"  {year}: n={metrics['n']}, gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
              f"wr={metrics['win_rate']:.4f}, pnl={metrics['total_pnl']:.1f}, dd={metrics['max_dd']:.1f}")
    results["year_by_year"] = year_by_year

    # ═══════════════════════════════════════════════════════════════════
    # 3. JPY PAIR GENERALIZATION
    # ═══════════════════════════════════════════════════════════════════
    print("\n[8] Section 3: JPY Pair Generalization...")
    pair_generalization = {}
    for pair in JPY_PAIRS:
        pair_obs = candidate[candidate["pair"] == pair]
        if len(pair_obs) < 30:
            print(f"  {pair}: INSUFFICIENT DATA (n={len(pair_obs)})")
            pair_generalization[pair] = {"n": len(pair_obs), "mean": 0.0, "net": 0.0}
            continue
        f = pair_obs["fwd_return"].values
        cost = PAIR_COST_PIPS.get(pair, COST_PIPS)
        metrics = compute_metrics(f, cost)
        pair_generalization[pair] = metrics
        print(f"  {pair}: n={metrics['n']}, gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
              f"wr={metrics['win_rate']:.4f}, cost={cost:.1f}, p={metrics['p']:.4f}")
    results["pair_generalization"] = pair_generalization

    # ═══════════════════════════════════════════════════════════════════
    # 4. JPY VOLATILITY REGIME
    # ═══════════════════════════════════════════════════════════════════
    print("\n[9] Section 4: JPY Volatility Regime...")
    print("  Computing JPY average volatility...")
    jpy_vol_regime = compute_jpy_vol_regime(pair_data, jpy_available, window=480)

    vol_regime_results = {}
    if not jpy_vol_regime.empty:
        candidate_with_vol = candidate.copy()
        regime_ts = jpy_vol_regime.index.values.astype("int64")
        ts_vals = candidate_with_vol["ts"].values.astype("datetime64[ms]").astype("int64")
        pos = np.searchsorted(regime_ts, ts_vals, side="right") - 1
        pos = np.clip(pos, 0, len(regime_ts) - 1)
        vol_vals = jpy_vol_regime.values[pos]
        candidate_with_vol["jpy_vol_regime"] = vol_vals
        vol_labels = {0.0: "LOW", 1.0: "MID", 2.0: "HIGH"}
        for regime_val, label in vol_labels.items():
            subset = candidate_with_vol[candidate_with_vol["jpy_vol_regime"] == regime_val]
            if len(subset) < 30:
                print(f"  {label}: INSUFFICIENT DATA (n={len(subset)})")
                vol_regime_results[label] = {"n": len(subset), "mean": 0.0, "net": 0.0}
                continue
            f = subset["fwd_return"].values
            metrics = compute_metrics(f, COST_PIPS)
            vol_regime_results[label] = metrics
            print(f"  {label}: n={metrics['n']}, gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
                  f"wr={metrics['win_rate']:.4f}, pf={metrics['pf']:.4f}")
    else:
        print("  WARNING: Could not compute JPY volatility regime")
    results["volatility_regime"] = vol_regime_results

    # ═══════════════════════════════════════════════════════════════════
    # 5. JPY TREND-PERSISTENCE REGIME
    # ═══════════════════════════════════════════════════════════════════
    print("\n[10] Section 5: JPY Trend-Persistence Regime...")
    print("  Computing JPY trend persistence...")
    jpy_persistence = compute_jpy_trend_persistence(pair_data, jpy_available, window=480, autocorr_lag=48)

    persistence_results = {}
    if not jpy_persistence.empty:
        candidate_with_pers = candidate.copy()
        regime_ts = jpy_persistence.index.values.astype("int64")
        ts_vals = candidate_with_pers["ts"].values.astype("datetime64[ms]").astype("int64")
        pos = np.searchsorted(regime_ts, ts_vals, side="right") - 1
        pos = np.clip(pos, 0, len(regime_ts) - 1)
        pers_vals = jpy_persistence.values[pos]
        candidate_with_pers["jpy_persistence"] = pers_vals
        pers_labels = {0.0: "LOW", 1.0: "MID", 2.0: "HIGH"}
        for regime_val, label in pers_labels.items():
            subset = candidate_with_pers[candidate_with_pers["jpy_persistence"] == regime_val]
            if len(subset) < 30:
                print(f"  {label}: INSUFFICIENT DATA (n={len(subset)})")
                persistence_results[label] = {"n": len(subset), "mean": 0.0, "net": 0.0}
                continue
            f = subset["fwd_return"].values
            metrics = compute_metrics(f, COST_PIPS)
            persistence_results[label] = metrics
            print(f"  {label}: n={metrics['n']}, gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
                  f"wr={metrics['win_rate']:.4f}, pf={metrics['pf']:.4f}")
    else:
        print("  WARNING: Could not compute JPY persistence regime")
    results["persistence_regime"] = persistence_results

    # ═══════════════════════════════════════════════════════════════════
    # 6. MACRO / BOJ REGIME
    # ═══════════════════════════════════════════════════════════════════
    print("\n[11] Section 6: BOJ Macro Regime...")
    boj_regimes = {
        "pre_normalization (2016-2023)": ("2016-01-01", "2023-12-31"),
        "normalization_beginning (2024)": ("2024-01-01", "2024-12-31"),
        "normalization_continued (2025-2026)": ("2025-01-01", "2026-12-31"),
    }
    boj_results = {}
    for label, (start, end) in boj_regimes.items():
        subset = candidate[(candidate["ts"] >= start) & (candidate["ts"] <= end)]
        if len(subset) < 30:
            print(f"  {label}: INSUFFICIENT DATA (n={len(subset)})")
            boj_results[label] = {"n": len(subset), "mean": 0.0, "net": 0.0}
            continue
        f = subset["fwd_return"].values
        metrics = compute_metrics(f, COST_PIPS)
        boj_results[label] = metrics
        print(f"  {label}: n={metrics['n']}, gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
              f"wr={metrics['win_rate']:.4f}")
    results["boj_regime"] = boj_results

    # ═══════════════════════════════════════════════════════════════════
    # 7. PERMUTATION TEST
    # ═══════════════════════════════════════════════════════════════════
    print("\n[12] Section 7: Permutation Test...")
    if len(candidate) > 100:
        perm_results = permutation_test_regime(candidate, n_perm=N_PERM, seed=RNG_SEED)
        print(f"  Observed: {perm_results['observed_mean']:.4f} pip")
        print(f"  Null: {perm_results['null_mean']:.4f} ± {perm_results['null_std']:.4f} pip")
        print(f"  p-value: {perm_results['p_value']:.4f}")
        print(f"  95% CI: [{perm_results['ci_95_low']:.4f}, {perm_results['ci_95_high']:.4f}]")
    else:
        perm_results = {"observed_mean": 0.0, "p_value": 1.0}
        print("  INSUFFICIENT DATA for permutation test")
    results["permutation"] = perm_results

    # ═══════════════════════════════════════════════════════════════════
    # 8. DISCOVERY/OOS MAGNITUDE GAP
    # ═══════════════════════════════════════════════════════════════════
    print("\n[13] Section 8: Discovery/OOS Magnitude Gap...")
    mag_gap = {}
    for label, subset in [("overall", candidate), ("jpy_only", candidate[candidate["is_jpy"]])]:
        sub_disc = subset[(subset["ts"] >= DISCOVERY_START) & (subset["ts"] <= DISCOVERY_END)]
        sub_oos = subset[(subset["ts"] >= OOS_START) & (subset["ts"] <= OOS_END)]
        disc_mean = float(sub_disc["fwd_return"].mean()) if len(sub_disc) > 0 else 0.0
        oos_mean = float(sub_oos["fwd_return"].mean()) if len(sub_oos) > 0 else 0.0
        ratio = oos_mean / disc_mean if abs(disc_mean) > 1e-10 else float("inf")
        mag_gap[label] = {
            "discovery_mean": round(disc_mean, 6),
            "oos_mean": round(oos_mean, 6),
            "ratio": round(ratio, 2),
        }
        print(f"  {label}: disc={disc_mean:.4f}, oos={oos_mean:.4f}, ratio={ratio:.2f}x")

    pair_mag = {}
    for pair in JPY_PAIRS:
        sub = candidate[candidate["pair"] == pair]
        sub_disc = sub[(sub["ts"] >= DISCOVERY_START) & (sub["ts"] <= DISCOVERY_END)]
        sub_oos = sub[(sub["ts"] >= OOS_START) & (sub["ts"] <= OOS_END)]
        disc_mean = float(sub_disc["fwd_return"].mean()) if len(sub_disc) > 0 else 0.0
        oos_mean = float(sub_oos["fwd_return"].mean()) if len(sub_oos) > 0 else 0.0
        ratio = oos_mean / disc_mean if abs(disc_mean) > 1e-10 else float("inf")
        pair_mag[pair] = {
            "discovery_mean": round(disc_mean, 6),
            "oos_mean": round(oos_mean, 6),
            "ratio": round(ratio, 2),
        }
        print(f"  {pair}: disc={disc_mean:.4f}, oos={oos_mean:.4f}, ratio={ratio:.2f}x")
    mag_gap["by_pair"] = pair_mag
    results["magnitude_gap"] = mag_gap

    # ═══════════════════════════════════════════════════════════════════
    # 9. COST ROBUSTNESS
    # ═══════════════════════════════════════════════════════════════════
    print("\n[14] Section 9: Cost Robustness...")
    cost_levels = {
        "COST_0": 0.0,
        "COST_LOW": 0.84,
        "COST_BASE": 1.72,
        "COST_HIGH": 2.60,
    }
    cost_sensitivity = {}
    for cost_label, cost_val in cost_levels.items():
        metrics = compute_metrics(candidate["fwd_return"].values, cost_val)
        cost_sensitivity[cost_label] = metrics
        print(f"  {cost_label} ({cost_val:.2f} pip): gross={metrics['mean']:.4f}, net={metrics['net']:.4f}, "
              f"pf={metrics['pf']:.4f}")

    print("\n  Per-pair cost sensitivity (OOS only):")
    pair_cost_oos = {}
    for pair in JPY_PAIRS:
        sub = oos[oos["pair"] == pair]
        if len(sub) < 30:
            continue
        pair_cost = PAIR_COST_PIPS.get(pair, COST_PIPS)
        f = sub["fwd_return"].values
        m0 = compute_metrics(f, 0.0)
        mbase = compute_metrics(f, pair_cost)
        mhigh = compute_metrics(f, pair_cost + 1.0)
        pair_cost_oos[pair] = {
            "cost_0": m0["net"], "cost_base": mbase["net"], "cost_high": mhigh["net"],
            "pair_cost": pair_cost,
        }
        print(f"    {pair}: cost={pair_cost:.1f}, net@0={m0['net']:.4f}, "
              f"net@base={mbase['net']:.4f}, net@high={mhigh['net']:.4f}")
    cost_sensitivity["per_pair_oos"] = pair_cost_oos

    print("\n  Cost sensitivity by year:")
    cost_by_year = {}
    cand_year = candidate.copy()
    cand_year["year"] = cand_year["ts"].dt.year
    for year, group in cand_year.groupby("year"):
        year_cost = {}
        for cost_label, cost_val in cost_levels.items():
            m = compute_metrics(group["fwd_return"].values, cost_val)
            year_cost[cost_label] = m["net"]
        cost_by_year[int(year)] = year_cost
        print(f"    {year}: " + ", ".join(f"{k}={v:.4f}" for k, v in year_cost.items()))
    cost_sensitivity["by_year"] = cost_by_year
    results["cost_sensitivity"] = cost_sensitivity

    # ═══════════════════════════════════════════════════════════════════
    # 10. FINAL CLASSIFICATION
    # ═══════════════════════════════════════════════════════════════════
    print("\n[15] Section 11: Final Classification...")
    holdout_m = holdout_comparison.get("holdout_2023", {})
    oos_m = holdout_comparison.get("oos_2024-2026", {})
    disc_m = holdout_comparison.get("discovery_2016-2022", {})

    holdout_positive = holdout_m.get("net", 0) > 0
    oos_positive = oos_m.get("net", 0) > 0
    holdout_significant = holdout_m.get("p", 1) < 0.05
    oos_significant = oos_m.get("p", 1) < 0.05

    vol_pos = sum(1 for v in vol_regime_results.values() if v.get("net", 0) > 0)
    pers_pos = sum(1 for v in persistence_results.values() if v.get("net", 0) > 0)

    pair_pos = sum(1 for v in pair_generalization.values() if v.get("net", 0) > 0)
    pair_total = len(pair_generalization)

    if holdout_positive and oos_positive and holdout_significant and oos_significant:
        if vol_pos >= 2 and pair_pos >= 5:
            classification = "A. STABLE CROSS-REGIME ECONOMIC EDGE"
        else:
            classification = "B. JPY-REGIME-CONDITIONAL EDGE"
    elif holdout_positive and oos_positive:
        classification = "B. JPY-REGIME-CONDITIONAL EDGE"
    elif pair_pos >= 5 and oos_positive:
        classification = "B. JPY-REGIME-CONDITIONAL EDGE"
    elif pair_pos >= 3 and oos_positive:
        classification = "C. PAIR-SPECIFIC EDGE"
    elif oos_positive and not holdout_positive:
        classification = "D. 2024-2026 REGIME ARTIFACT"
    else:
        classification = "E. NO ROBUST EDGE"

    print(f"  Classification: {classification}")
    print(f"  Holdout positive: {holdout_positive}, OOS positive: {oos_positive}")
    print(f"  Holdout significant: {holdout_significant}, OOS significant: {oos_significant}")
    print(f"  Vol regimes positive: {vol_pos}/3, Persistence regimes positive: {pers_pos}/3")
    print(f"  JPY pairs positive: {pair_pos}/{pair_total}")
    results["classification"] = classification

    # ── Save ───────────────────────────────────────────────────────────
    out_dir = Path("research/output/phase12")
    out_dir.mkdir(parents=True, exist_ok=True)
    results["runtime_seconds"] = time.time() - t0

    with open(out_dir / "phase12_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    summary_rows = []
    for section, data in [
        ("holdout_comparison", holdout_comparison),
        ("year_by_year", year_by_year),
        ("pair_generalization", pair_generalization),
        ("volatility_regime", vol_regime_results),
        ("persistence_regime", persistence_results),
        ("boj_regime", boj_results),
    ]:
        for k, v in data.items():
            if isinstance(v, dict) and "mean" in v:
                summary_rows.append({"section": section, "key": str(k), **v})
    pd.DataFrame(summary_rows).to_csv(out_dir / "phase12_summary.csv", index=False)

    print("\n[16] Generating figures...")
    try:
        generate_figures(results, out_dir)
    except Exception as e:
        print(f"  Figure generation failed: {e}")

    print(f"\n{'=' * 70}")
    print(f"Phase 12 complete in {time.time() - t0:.1f}s")
    print(f"Classification: {classification}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
