"""
Phase M1: Structural Discovery — FX Currency Momentum

This is a hypothesis falsification phase. NOT strategy development.

Tests whether cross-sectional currency momentum exists as a stable
economic phenomenon in our FX data.

No parameter optimization. No trading filters. No "best pair."
Just determine whether the structure exists.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ALL_PAIRS

DATA_DIR = Path("/root/data")
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]

FORMATION_HORIZONS = [1, 3, 5, 10, 20, 40, 60, 120]  # in days
HOLDING_HORIZONS = [1, 3, 5, 10, 20, 40]  # in days

BARS_PER_DAY = 48  # 30min bars
RNG_SEED = 42
N_BOOT = 200


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


# ═══════════════════════════════════════════════════════════════════════
# CURRENCY RETURN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

def compute_currency_returns(pair_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Extract individual currency returns from pairwise data.

    For pair BASE/QUOTE with return r_pair:
        r_BASE = +r_pair
        r_QUOTE = -r_pair

    Average across all pairs a currency appears in.
    Returns DataFrame: index=datetime, columns=currencies, values=log returns.
    """
    contributions: dict[str, list[pd.Series]] = {c: [] for c in CURRENCIES}

    for pair, df in pair_data.items():
        if "/" not in pair:
            continue
        base, quote = pair.split("/")
        if base not in CURRENCIES or quote not in CURRENCIES:
            continue

        close = df["close"]
        log_ret = np.log(close / close.shift(1))
        log_ret = log_ret.iloc[1:]  # drop first NaN

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
# MOMENTUM SPECTRUM
# ═══════════════════════════════════════════════════════════════════════

def compute_momentum_spectrum(
    currency_returns: pd.DataFrame,
    formation_horizons: list[int] = FORMATION_HORIZONS,
    holding_horizons: list[int] = HOLDING_HORIZONS,
) -> dict[str, Any]:
    """
    Compute the full momentum spectrum.

    For each (formation, holding) combination:
    1. Rank currencies by formation-period return
    2. Construct WML (top rank - bottom rank)
    3. Measure forward return of WML spread
    """
    results: dict[str, Any] = {}

    # Pre-compute all formation and forward returns (vectorized)
    formation_cache: dict[int, pd.DataFrame] = {}
    for f_horizon in formation_horizons:
        formation_cache[f_horizon] = currency_returns.rolling(f_horizon).sum()

    forward_cache: dict[int, pd.DataFrame] = {}
    for h_horizon in holding_horizons:
        forward_cache[h_horizon] = currency_returns.rolling(h_horizon).sum().shift(-h_horizon)

    for f_horizon in formation_horizons:
        f_key = f"{f_horizon}D"
        results[f_key] = {}
        form_ret = formation_cache[f_horizon]

        for h_horizon in holding_horizons:
            h_key = f"{h_horizon}D"
            fwd_ret = forward_cache[h_horizon]

            # Vectorized: drop rows with any NaN
            valid = form_ret.notna().all(axis=1) & fwd_ret.notna().all(axis=1)
            form_v = form_ret.loc[valid]
            fwd_v = fwd_ret.loc[valid]

            if len(form_v) < 50:
                results[f_key][h_key] = {
                    "n": len(form_v), "mean": 0.0, "median": 0.0,
                    "win_rate": 0.5, "t_stat": 0.0, "p_value": 1.0,
                    "deciles": {}, "decile_monotonicity": 0.0,
                }
                continue

            # Vectorized ranking: rank each row (cross-sectional rank)
            ranks = form_v.rank(axis=1, method="average")

            # Best and worst currency per row → column position indices
            col_names = list(fwd_v.columns)
            col_pos = {name: i for i, name in enumerate(col_names)}
            best_pos = ranks.idxmax(axis=1).map(col_pos).values
            worst_pos = ranks.idxmin(axis=1).map(col_pos).values

            # Vectorized WML return
            wml_returns = fwd_v.values[np.arange(len(form_v)), best_pos] - \
                          fwd_v.values[np.arange(len(form_v)), worst_pos]

            # Decile analysis: assign each currency to its rank bin
            decile_means = {}
            for d in range(1, 9):
                mask = (ranks.values == d).any(axis=1)
                if mask.sum() > 0:
                    # For rank d, collect fwd returns of currencies with that rank
                    decile_vals = []
                    for col_i in range(ranks.shape[1]):
                        col_mask = ranks.iloc[:, col_i].values == d
                        decile_vals.extend(fwd_v.values[col_mask, col_i].tolist())
                    decile_means[d] = round(float(np.mean(decile_vals)), 6) if decile_vals else 0.0
                else:
                    decile_means[d] = 0.0

            # Statistics
            mean_ret = float(np.mean(wml_returns))
            median_ret = float(np.median(wml_returns))
            win_rate = float(np.mean(wml_returns > 0))

            nw_se = newey_west_se(wml_returns, max_lag=min(20, len(wml_returns) // 10))
            t_stat = mean_ret / nw_se if nw_se > 0 else 0.0
            p_val = 2 * stats.t.sf(abs(t_stat), df=max(1, len(wml_returns) - 1))

            # Decile monotonicity
            if len(decile_means) >= 4:
                d_keys = sorted(decile_means.keys())
                d_vals = [decile_means[k] for k in d_keys]
                monotonicity = float(stats.spearmanr(d_keys, d_vals).correlation)
            else:
                monotonicity = 0.0

            results[f_key][h_key] = {
                "n": len(wml_returns),
                "mean": round(mean_ret, 6),
                "median": round(median_ret, 6),
                "win_rate": round(win_rate, 6),
                "t_stat": round(t_stat, 4),
                "p_value": round(p_val, 6),
                "deciles": decile_means,
                "decile_monotonicity": round(monotonicity, 4),
            }

    return results


def newey_west_se(residuals: np.ndarray, max_lag: int = 20) -> float:
    """Newey-West HAC standard error."""
    n = len(residuals)
    if n < max_lag + 1:
        return float(np.std(residuals) / np.sqrt(n))

    mean_r = np.mean(residuals)
    centered = residuals - mean_r

    # Auto-covariances
    gamma_0 = np.mean(centered ** 2)
    gamma_sum = 0.0
    for lag in range(1, max_lag + 1):
        weight = 1.0 - lag / (max_lag + 1)  # Bartlett kernel
        gamma_lag = np.mean(centered[lag:] * centered[:-lag])
        gamma_sum += 2 * weight * gamma_lag

    nw_var = gamma_0 + gamma_sum
    return float(np.sqrt(max(nw_var, 1e-10) / n))


# ═══════════════════════════════════════════════════════════════════════
# STABILITY TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_stability(spectrum: dict) -> dict[str, Any]:
    """
    Test whether momentum structure is stable across neighboring horizons.
    This is the KEY kill criterion.
    """
    stability = {}

    # For each formation horizon, check if neighboring holding horizons agree
    formation_keys = sorted(spectrum.keys(), key=lambda x: int(x.replace("D", "")))
    holding_keys = sorted(spectrum[formation_keys[0]].keys(), key=lambda x: int(x.replace("D", "")))

    # Horizontal stability: for each formation, do neighboring holdings agree?
    horizontal_agreement = 0
    horizontal_total = 0
    for f_key in formation_keys:
        for i in range(len(holding_keys) - 1):
            h1, h2 = holding_keys[i], holding_keys[i + 1]
            m1 = spectrum[f_key][h1]["mean"]
            m2 = spectrum[f_key][h2]["mean"]
            if abs(m1) > 0.01 and abs(m2) > 0.01:
                horizontal_total += 1
                if (m1 > 0 and m2 > 0) or (m1 < 0 and m2 < 0):
                    horizontal_agreement += 1

    # Vertical stability: for each holding horizon, do neighboring formations agree?
    vertical_agreement = 0
    vertical_total = 0
    for h_key in holding_keys:
        for i in range(len(formation_keys) - 1):
            f1, f2 = formation_keys[i], formation_keys[i + 1]
            m1 = spectrum[f1][h_key]["mean"]
            m2 = spectrum[f2][h_key]["mean"]
            if abs(m1) > 0.01 and abs(m2) > 0.01:
                vertical_total += 1
                if (m1 > 0 and m2 > 0) or (m1 < 0 and m2 < 0):
                    vertical_agreement += 1

    # Sign consistency: what fraction of cells have the same sign as the majority?
    all_means = []
    for f_key in formation_keys:
        for h_key in holding_keys:
            all_means.append(spectrum[f_key][h_key]["mean"])
    all_means = np.array(all_means)
    if len(all_means) > 0:
        majority_sign = 1 if np.sum(all_means > 0) > np.sum(all_means < 0) else -1
        sign_consistency = float(np.mean(np.sign(all_means) == majority_sign))
    else:
        sign_consistency = 0.5

    # Fraction significant at 5%
    sig_count = 0
    total_count = 0
    for f_key in formation_keys:
        for h_key in holding_keys:
            total_count += 1
            if spectrum[f_key][h_key]["p_value"] < 0.05:
                sig_count += 1

    # Average absolute t-stat
    t_stats = []
    for f_key in formation_keys:
        for h_key in holding_keys:
            t_stats.append(abs(spectrum[f_key][h_key]["t_stat"]))
    avg_abs_t = float(np.mean(t_stats)) if t_stats else 0.0

    # Decile monotonicity consistency
    mono_scores = []
    for f_key in formation_keys:
        for h_key in holding_keys:
            mono_scores.append(spectrum[f_key][h_key]["decile_monotonicity"])
    avg_monotonicity = float(np.mean(mono_scores)) if mono_scores else 0.0

    stability = {
        "horizontal_agreement_pct": round(horizontal_agreement / max(horizontal_total, 1) * 100, 1),
        "vertical_agreement_pct": round(vertical_agreement / max(vertical_total, 1) * 100, 1),
        "sign_consistency_pct": round(sign_consistency * 100, 1),
        "significant_cells_pct": round(sig_count / max(total_count, 1) * 100, 1),
        "avg_abs_t_stat": round(avg_abs_t, 4),
        "avg_decile_monotonicity": round(avg_monotonicity, 4),
        "total_cells": total_count,
        "significant_cells": sig_count,
    }

    # Kill criterion: is the structure stable?
    # Require: >60% horizontal agreement, >60% vertical agreement, >50% sign consistency
    stability["passes_kill_criterion"] = (
        stability["horizontal_agreement_pct"] > 60
        and stability["vertical_agreement_pct"] > 60
        and stability["sign_consistency_pct"] > 50
    )

    return stability


# ═══════════════════════════════════════════════════════════════════════
# PERMUTATION TEST
# ═══════════════════════════════════════════════════════════════════════

def permutation_test_wml(
    currency_returns: pd.DataFrame,
    formation_horizon: int = 20,
    holding_horizon: int = 10,
    n_perm: int = N_BOOT,
    seed: int = RNG_SEED,
) -> dict:
    """Sign permutation test for WML returns (vectorized)."""
    rng = np.random.RandomState(seed)

    form_ret = currency_returns.rolling(formation_horizon).sum()
    fwd_ret = currency_returns.rolling(holding_horizon).sum().shift(-holding_horizon)

    valid = form_ret.notna().all(axis=1) & fwd_ret.notna().all(axis=1)
    form_v = form_ret.loc[valid]
    fwd_v = fwd_ret.loc[valid]

    ranks = form_v.rank(axis=1, method="average")
    col_names = list(fwd_v.columns)
    col_pos = {name: i for i, name in enumerate(col_names)}
    best_pos = ranks.idxmax(axis=1).map(col_pos).values
    worst_pos = ranks.idxmin(axis=1).map(col_pos).values
    wml_actual = fwd_v.values[np.arange(len(form_v)), best_pos] - \
                 fwd_v.values[np.arange(len(form_v)), worst_pos]

    actual_mean = float(np.mean(wml_actual))

    # Vectorized sign permutation
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(wml_actual)))
    null_means = (wml_actual[None, :] * signs).mean(axis=1)

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
# FIGURES
# ═══════════════════════════════════════════════════════════════════════

def generate_figures(results: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    spectrum = results.get("spectrum", {})
    formation_keys = sorted(spectrum.keys(), key=lambda x: int(x.replace("D", "")))
    holding_keys = sorted(spectrum[formation_keys[0]].keys(), key=lambda x: int(x.replace("D", ""))) if formation_keys else []

    # Fig 1: Momentum spectrum heatmap
    if formation_keys and holding_keys:
        data_matrix = np.zeros((len(formation_keys), len(holding_keys)))
        for i, f_key in enumerate(formation_keys):
            for j, h_key in enumerate(holding_keys):
                data_matrix[i, j] = spectrum[f_key][h_key]["mean"]

        fig, ax = plt.subplots(figsize=(10, 7))
        im = ax.imshow(data_matrix, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(holding_keys)))
        ax.set_xticklabels(holding_keys)
        ax.set_yticks(range(len(formation_keys)))
        ax.set_yticklabels(formation_keys)
        ax.set_xlabel("Holding Period")
        ax.set_ylabel("Formation Period")
        ax.set_title("Phase M1: FX Currency Momentum Spectrum (Mean WML Return)")
        plt.colorbar(im, ax=ax, label="Mean Return (log)")
        for i in range(len(formation_keys)):
            for j in range(len(holding_keys)):
                val = data_matrix[i, j]
                ax.text(j, i, f"{val:.4f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(val) > data_matrix.max() * 0.5 else "black")
        plt.tight_layout()
        plt.savefig(fig_dir / "01_momentum_spectrum.png", dpi=150)
        plt.close()

    # Fig 2: t-stat heatmap
    if formation_keys and holding_keys:
        t_matrix = np.zeros((len(formation_keys), len(holding_keys)))
        for i, f_key in enumerate(formation_keys):
            for j, h_key in enumerate(holding_keys):
                t_matrix[i, j] = spectrum[f_key][h_key]["t_stat"]

        fig, ax = plt.subplots(figsize=(10, 7))
        im = ax.imshow(t_matrix, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(len(holding_keys)))
        ax.set_xticklabels(holding_keys)
        ax.set_yticks(range(len(formation_keys)))
        ax.set_yticklabels(formation_keys)
        ax.set_xlabel("Holding Period")
        ax.set_ylabel("Formation Period")
        ax.set_title("Phase M1: t-Statistics (Newey-West HAC)")
        plt.colorbar(im, ax=ax, label="t-stat")
        plt.tight_layout()
        plt.savefig(fig_dir / "02_tstat_spectrum.png", dpi=150)
        plt.close()

    # Fig 3: Decile monotonicity for key horizons
    if formation_keys and holding_keys:
        key_cells = []
        for f_key in ["20D", "40D", "60D"]:
            for h_key in ["5D", "10D", "20D"]:
                if f_key in spectrum and h_key in spectrum[f_key]:
                    key_cells.append((f_key, h_key))

        if key_cells:
            fig, axes = plt.subplots(1, min(3, len(key_cells)), figsize=(5 * min(3, len(key_cells)), 4))
            if len(key_cells) == 1:
                axes = [axes]
            for idx, (f_key, h_key) in enumerate(key_cells[:3]):
                ax = axes[idx]
                deciles = spectrum[f_key][h_key].get("deciles", {})
                if deciles:
                    d_keys = sorted(deciles.keys(), key=lambda x: int(x) if isinstance(x, (int, float)) else int(str(x).replace("D", "")))
                    d_vals = [deciles[k] for k in d_keys]
                    colors = ["green" if v > 0 else "red" for v in d_vals]
                    ax.bar(range(len(d_keys)), d_vals, color=colors, alpha=0.7)
                    ax.set_xticks(range(len(d_keys)))
                    ax.set_xticklabels([f"D{int(k)}" for k in d_keys])
                    ax.set_title(f"{f_key}→{h_key} (mono={spectrum[f_key][h_key]['decile_monotonicity']:.2f})")
                    ax.axhline(y=0, color="black", linewidth=0.5)
            plt.tight_layout()
            plt.savefig(fig_dir / "03_decile_monotonicity.png", dpi=150)
            plt.close()

    # Fig 4: Permutation test for 20D→10D
    perm = results.get("permutation_20D_10D", {})
    if perm and "null_distribution" in perm:
        null_dist = np.array(perm["null_distribution"])
        observed = perm["observed_mean"]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(null_dist, bins=50, alpha=0.7, density=True, label="Null (sign-flipped)")
        ax.axvline(observed, color="red", linewidth=2, label=f"Observed = {observed:.4f}")
        ax.set_xlabel("Mean WML Return")
        ax.set_ylabel("Density")
        ax.set_title(f"Phase M1: Permutation Test 20D→10D (p = {perm['p_value']:.4f})")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "04_permutation_20d_10d.png", dpi=150)
        plt.close()

    # Fig 5: Stability metrics
    stab = results.get("stability", {})
    if stab:
        metrics = {
            "Horizontal\nAgreement": stab.get("horizontal_agreement_pct", 0),
            "Vertical\nAgreement": stab.get("vertical_agreement_pct", 0),
            "Sign\nConsistency": stab.get("sign_consistency_pct", 0),
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
        ax.set_title("Phase M1: Stability Metrics")
        ax.axhline(y=60, color="green", linewidth=1, linestyle="--", label="Kill threshold (60%)")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "05_stability_metrics.png", dpi=150)
        plt.close()

    print(f"  Figures saved to {fig_dir}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase M1: Structural Discovery — FX Currency Momentum")
    print("This is hypothesis falsification, not strategy development.")
    print("=" * 70)

    # ── Load data ──────────────────────────────────────────────────────
    print("\n[1] Loading pair data...")
    pair_data = load_pair_data(ALL_PAIRS)
    print(f"  Loaded {len(pair_data)} pairs")

    # ── Compute currency returns ───────────────────────────────────────
    print("\n[2] Computing individual currency returns...")
    currency_returns = compute_currency_returns(pair_data)
    print(f"  Shape: {currency_returns.shape}")
    print(f"  Currencies: {list(currency_returns.columns)}")
    print(f"  Date range: {currency_returns.index[0]} to {currency_returns.index[-1]}")

    # ── Compute momentum spectrum ──────────────────────────────────────
    print("\n[3] Computing momentum spectrum...")
    spectrum = compute_momentum_spectrum(currency_returns)

    # Print spectrum
    print("\n  MOMENTUM SPECTRUM (Mean WML Return):")
    print(f"  {'Formation':>10}", end="")
    for h_key in sorted(spectrum[list(spectrum.keys())[0]].keys(), key=lambda x: int(x.replace("D", ""))):
        print(f"  {h_key:>8}", end="")
    print()
    for f_key in sorted(spectrum.keys(), key=lambda x: int(x.replace("D", ""))):
        print(f"  {f_key:>10}", end="")
        for h_key in sorted(spectrum[f_key].keys(), key=lambda x: int(x.replace("D", ""))):
            val = spectrum[f_key][h_key]["mean"]
            print(f"  {val:>8.4f}", end="")
        print()

    print("\n  t-STATISTICS (Newey-West HAC):")
    print(f"  {'Formation':>10}", end="")
    for h_key in sorted(spectrum[list(spectrum.keys())[0]].keys(), key=lambda x: int(x.replace("D", ""))):
        print(f"  {h_key:>8}", end="")
    print()
    for f_key in sorted(spectrum.keys(), key=lambda x: int(x.replace("D", ""))):
        print(f"  {f_key:>10}", end="")
        for h_key in sorted(spectrum[f_key].keys(), key=lambda x: int(x.replace("D", ""))):
            val = spectrum[f_key][h_key]["t_stat"]
            print(f"  {val:>8.2f}", end="")
        print()

    # ── Stability test ─────────────────────────────────────────────────
    print("\n[4] Testing stability across horizons...")
    stability = test_stability(spectrum)
    print(f"  Horizontal agreement: {stability['horizontal_agreement_pct']:.1f}%")
    print(f"  Vertical agreement: {stability['vertical_agreement_pct']:.1f}%")
    print(f"  Sign consistency: {stability['sign_consistency_pct']:.1f}%")
    print(f"  Significant cells: {stability['significant_cells_pct']:.1f}% ({stability['significant_cells']}/{stability['total_cells']})")
    print(f"  Avg |t-stat|: {stability['avg_abs_t_stat']:.4f}")
    print(f"  Avg decile monotonicity: {stability['avg_decile_monotonicity']:.4f}")
    print(f"  Passes kill criterion: {stability['passes_kill_criterion']}")

    # ── Permutation test for key cell ──────────────────────────────────
    print("\n[5] Permutation test (20D→10D)...")
    perm = permutation_test_wml(currency_returns, formation_horizon=20, holding_horizon=10)
    print(f"  Observed: {perm['observed_mean']:.4f}")
    print(f"  Null: {perm['null_mean']:.4f} ± {perm['null_std']:.4f}")
    print(f"  p-value: {perm['p_value']:.4f}")

    # ── Classification ─────────────────────────────────────────────────
    print("\n[6] Classification...")
    if stability["passes_kill_criterion"]:
        classification = "EDGE EXISTS — proceed to M2 cost screen"
    else:
        classification = "NO STABLE STRUCTURE — kill hypothesis"
    print(f"  {classification}")

    # ── Save ───────────────────────────────────────────────────────────
    results = {
        "phase": "M1",
        "title": "Structural Discovery — FX Currency Momentum",
        "formation_horizons": FORMATION_HORIZONS,
        "holding_horizons": HOLDING_HORIZONS,
        "spectrum": spectrum,
        "stability": stability,
        "permutation_20D_10D": perm,
        "classification": classification,
        "runtime_seconds": time.time() - t0,
    }

    out_dir = Path("/root/nestquant/research_data/phase_m1")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "phase_m1_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Save spectrum as CSV
    rows = []
    for f_key in spectrum:
        for h_key in spectrum[f_key]:
            cell = spectrum[f_key][h_key]
            rows.append({
                "formation": f_key, "holding": h_key,
                "n": cell["n"], "mean": cell["mean"], "median": cell["median"],
                "win_rate": cell["win_rate"], "t_stat": cell["t_stat"],
                "p_value": cell["p_value"], "decile_monotonicity": cell["decile_monotonicity"],
            })
    pd.DataFrame(rows).to_csv(out_dir / "phase_m1_spectrum.csv", index=False)

    print("\n[7] Generating figures...")
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
