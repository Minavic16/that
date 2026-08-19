"""
Phase S0: Archived Breakout Reassessment — Vectorized 4h Engine

Uses 4h OHLC for both signals and execution (no 1min loop).
Signal computation vectorized. Simulation remains sequential but cached.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ALL_PAIRS
from indicators.atr import calculate_atr
from indicators.swing import swing_high_series, swing_low_series
from indicators.pip import pip_size as get_pip_size

DATA_DIR = Path("/root/data")
RNG_SEED = 42
N_PERM = 500

LOOKBACK = 5
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
RRR = 3.5
MAX_HOLD_DAYS = 7
BREAKEVEN_RATIO = 0.8
SLIPPAGE_PIPS = 0.1

SPREAD_PIPS = {
    "EUR/USD": 0.2, "GBP/USD": 0.3, "USD/JPY": 0.2, "USD/CHF": 0.3,
    "USD/CAD": 0.3, "AUD/USD": 0.3, "NZD/USD": 0.3, "EUR/GBP": 0.3,
    "EUR/JPY": 0.3, "GBP/JPY": 0.3, "AUD/NZD": 0.5, "EUR/NZD": 0.5,
    "GBP/NZD": 0.5, "AUD/CAD": 0.4, "AUD/CHF": 0.4, "AUD/JPY": 0.3,
    "CAD/JPY": 0.3, "CHF/JPY": 0.4, "CAD/CHF": 0.5, "NZD/JPY": 0.4,
    "NZD/CAD": 0.5, "NZD/CHF": 0.5, "EUR/AUD": 0.4, "EUR/CAD": 0.4,
    "EUR/CHF": 0.3, "GBP/AUD": 0.5, "GBP/CAD": 0.5, "GBP/CHF": 0.4,
}


def load_and_resample() -> dict[str, pd.DataFrame]:
    pair_4h = {}
    for pair in ALL_PAIRS:
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
                    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
                    pair_4h[k] = df.resample("4h").agg(agg).dropna()
    return pair_4h


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    sh = swing_high_series(df, LOOKBACK)
    sl = swing_low_series(df, LOOKBACK)
    close = df["close"].values
    atr = calculate_atr(df, ATR_PERIOD)

    sh_v = sh.values
    sl_v = sl.values
    sig = np.zeros(len(df), dtype=int)

    for i in range(LOOKBACK * 2 + 1, len(df)):
        if not np.isnan(sh_v[i - 1]) and close[i - 1] <= sh_v[i - 1] < close[i]:
            sig[i] = 1
        elif not np.isnan(sl_v[i - 1]) and close[i - 1] >= sl_v[i - 1] > close[i]:
            sig[i] = -1

    return pd.DataFrame({
        "signal": sig, "swing_high": sh_v, "swing_low": sl_v,
        "atr": atr.values,
        "open": df["open"].values, "high": df["high"].values,
        "low": df["low"].values, "close": df["close"].values,
    }, index=df.index)


def simulate(
    sig: pd.DataFrame, pair: str,
    sl_mult: float, rrr: float, cost_pips: float,
    trailing: bool = True, breakeven: bool = True,
    direction_override: int = None,
    rng: np.random.RandomState = None,
) -> tuple[list[float], list[float]]:
    pip = get_pip_size(pair)
    total_cost = cost_pips
    max_bars = MAX_HOLD_DAYS * 6

    open_ = sig["open"].values
    high_ = sig["high"].values
    low_ = sig["low"].values
    close_ = sig["close"].values
    atr_ = sig["atr"].values
    sig_ = sig["signal"].values
    sh_ = sig["swing_high"].values
    sl_ = sig["swing_low"].values

    pnls = []
    rs = []
    entry_indices = []

    in_trade = False
    direction = 0
    entry_price = 0.0
    sl_price = 0.0
    entry_idx = 0

    for i in range(LOOKBACK * 2 + 1, len(sig)):
        sig_val = sig_[i]

        if rng is not None:
            sig_val = rng.choice([-1, 0, 1], p=[0.4, 0.2, 0.4])
        if direction_override is not None:
            sig_val = direction_override

        if in_trade:
            bars_held = i - entry_idx
            risk = abs(entry_price - sl_price) / pip

            if direction == 1:
                if low_[i] <= sl_price and risk > 0:
                    pnl = (sl_price - entry_price) / pip - total_cost
                    pnls.append(pnl)
                    rs.append(pnl / risk)
                    in_trade = False
                    continue
                tp = entry_price + risk * rrr * pip
                if high_[i] >= tp and risk > 0:
                    pnl = (tp - entry_price) / pip - total_cost
                    pnls.append(pnl)
                    rs.append(pnl / risk)
                    in_trade = False
                    continue
                if bars_held >= max_bars and risk > 0:
                    pnl = (close_[i] - entry_price) / pip - total_cost
                    pnls.append(pnl)
                    rs.append(pnl / risk)
                    in_trade = False
                    continue
                if trailing:
                    new_sl = sl_[i - 1] if not np.isnan(sl_[i - 1]) else sl_price
                    if new_sl > sl_price:
                        sl_price = new_sl
                if breakeven and sl_price < entry_price and risk > 0:
                    if (close_[i] - entry_price) / pip >= BREAKEVEN_RATIO * risk:
                        sl_price = entry_price
            else:
                if high_[i] >= sl_price and risk > 0:
                    pnl = (entry_price - sl_price) / pip - total_cost
                    pnls.append(pnl)
                    rs.append(pnl / risk)
                    in_trade = False
                    continue
                tp = entry_price - risk * rrr * pip
                if low_[i] <= tp and risk > 0:
                    pnl = (entry_price - tp) / pip - total_cost
                    pnls.append(pnl)
                    rs.append(pnl / risk)
                    in_trade = False
                    continue
                if bars_held >= max_bars and risk > 0:
                    pnl = (entry_price - close_[i]) / pip - total_cost
                    pnls.append(pnl)
                    rs.append(pnl / risk)
                    in_trade = False
                    continue
                if trailing:
                    new_sl = sh_[i - 1] if not np.isnan(sh_[i - 1]) else sl_price
                    if new_sl < sl_price:
                        sl_price = new_sl
                if breakeven and sl_price > entry_price and risk > 0:
                    if (entry_price - close_[i]) / pip >= BREAKEVEN_RATIO * risk:
                        sl_price = entry_price

        if not in_trade and sig_val != 0 and not np.isnan(atr_[i]) and atr_[i] > 0:
            entry_price = open_[i]
            stop_dist = sl_mult * atr_[i]
            if stop_dist / pip < 1.0:
                continue
            sl_price = entry_price - stop_dist if sig_val == 1 else entry_price + stop_dist
            direction = sig_val
            entry_idx = i
            in_trade = True
            entry_indices.append(i)

    if in_trade:
        risk = abs(entry_price - sl_price) / pip
        if risk > 0:
            if direction == 1:
                pnl = (close_[-1] - entry_price) / pip - total_cost
            else:
                pnl = (entry_price - close_[-1]) / pip - total_cost
            pnls.append(pnl)
            rs.append(pnl / risk)

    return pnls, rs, entry_indices


def metrics(pnls: list[float], rs: list[float], label: str = "") -> dict:
    if not pnls:
        return {"label": label, "n": 0}
    p = np.array(pnls)
    r = np.array(rs)
    wins = p[p > 0]
    losses = p[p <= 0]
    gp = float(np.sum(wins)) if len(wins) else 0
    gl = float(np.abs(np.sum(losses))) if len(losses) else 1e-10
    cum = np.cumsum(p)
    max_dd = float(np.max(np.maximum.accumulate(cum) - cum))
    tt = sp_stats.ttest_1samp(r, 0)
    return {
        "label": label, "n": len(p),
        "win_rate": round(float(np.mean(p > 0)), 4),
        "avg_pnl_pips": round(float(np.mean(p)), 4),
        "median_pnl_pips": round(float(np.median(p)), 4),
        "total_pnl_pips": round(float(np.sum(p)), 2),
        "avg_r": round(float(np.mean(r)), 4),
        "median_r": round(float(np.median(r)), 4),
        "profit_factor": round(gp / gl, 4),
        "max_dd_pips": round(max_dd, 2),
        "skewness": round(float(sp_stats.skew(r)), 4),
        "kurtosis": round(float(sp_stats.kurtosis(r)), 4),
        "t_stat": round(float(tt.statistic), 4),
        "p_value": round(float(tt.pvalue), 6),
    }


def merge(all_pnls: list[list[float]], all_rs: list[list[float]]) -> tuple[list[float], list[float]]:
    flat_p = [x for sub in all_pnls for x in sub]
    flat_r = [x for sub in all_rs for x in sub]
    return flat_p, flat_r


def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase S0: Archived Breakout Reassessment (4h)")
    print("=" * 70)

    out_dir = Path("/root/nestquant/research_data/simple_strategies")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data ──────────────────────────────────────────────────────
    print("\n[1] Loading & resampling...")
    pair_4h = load_and_resample()
    print(f"  {len(pair_4h)} pairs loaded")

    # ── Compute signals (cached) ───────────────────────────────────────
    print("\n[2] Computing signals...")
    sigs = {}
    total = 0
    for p, df in pair_4h.items():
        sigs[p] = compute_signals(df)
        total += int((sigs[p]["signal"] != 0).sum())
    print(f"  {total} signals total")

    pair_names = list(sigs.keys())
    print(f"  Pairs: {pair_names}")

    # ── EXP 1: Original (zero cost) ────────────────────────────────────
    print("\n[3] EXP 1: Original breakout...")
    all_pnls = {}
    all_rs = {}
    for p in pair_names:
        pnls, rs, _ = simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=0.0)
        all_pnls[p] = pnls
        all_rs[p] = rs
    fp, fr = merge(list(all_pnls.values()), list(all_rs.values()))
    m_orig = metrics(fp, fr, "Original")
    print(f"  N={m_orig['n']}, WR={m_orig['win_rate']:.1%}, AvgPnL={m_orig['avg_pnl_pips']:.2f}pip, "
          f"PF={m_orig['profit_factor']:.2f}, MaxDD={m_orig['max_dd_pips']:.1f}pip, "
          f"t={m_orig['t_stat']:.2f}, p={m_orig['p_value']:.4f}")

    # ── EXP 2: With costs ─────────────────────────────────────────────
    print("\n[4] EXP 2: With realistic costs...")
    all_pnls_c = {}
    all_rs_c = {}
    for p in pair_names:
        spread = SPREAD_PIPS.get(p, 0.5)
        pnls, rs, _ = simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR,
                            cost_pips=spread + SLIPPAGE_PIPS)
        all_pnls_c[p] = pnls
        all_rs_c[p] = rs
    fp_c, fr_c = merge(list(all_pnls_c.values()), list(all_rs_c.values()))
    m_cost = metrics(fp_c, fr_c, "Original+Costs")
    avg_spread = np.mean([SPREAD_PIPS.get(p, 0.5) for p in pair_names])
    print(f"  Avg spread={avg_spread:.2f}pip + {SLIPPAGE_PIPS}pip slippage")
    print(f"  N={m_cost['n']}, WR={m_cost['win_rate']:.1%}, AvgPnL={m_cost['avg_pnl_pips']:.2f}pip, "
          f"PF={m_cost['profit_factor']:.2f}")

    # ── EXP 3: Controls ────────────────────────────────────────────────
    print("\n[5] EXP 3: Controls...")

    # Random direction
    all_pnls_r = {}
    all_rs_r = {}
    for p in pair_names:
        pnls, rs, _ = simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR,
                            cost_pips=SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS,
                            rng=np.random.RandomState(RNG_SEED))
        all_pnls_r[p] = pnls
        all_rs_r[p] = rs
    fp_r, fr_r = merge(list(all_pnls_r.values()), list(all_rs_r.values()))
    m_rand = metrics(fp_r, fr_r, "Random")
    print(f"  Random: N={m_rand['n']}, WR={m_rand['win_rate']:.1%}, AvgPnL={m_rand['avg_pnl_pips']:.2f}pip, "
          f"PF={m_rand['profit_factor']:.2f}")

    # Always BUY
    all_pnls_b = {}
    all_rs_b = {}
    for p in pair_names:
        pnls, rs, _ = simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR,
                            cost_pips=SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS,
                            direction_override=1)
        all_pnls_b[p] = pnls
        all_rs_b[p] = rs
    fp_b, fr_b = merge(list(all_pnls_b.values()), list(all_rs_b.values()))
    m_buy = metrics(fp_b, fr_b, "Always BUY")
    print(f"  Always BUY: N={m_buy['n']}, WR={m_buy['win_rate']:.1%}, AvgPnL={m_buy['avg_pnl_pips']:.2f}pip")

    # Always SELL
    all_pnls_s = {}
    all_rs_s = {}
    for p in pair_names:
        pnls, rs, _ = simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR,
                            cost_pips=SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS,
                            direction_override=-1)
        all_pnls_s[p] = pnls
        all_rs_s[p] = rs
    fp_s, fr_s = merge(list(all_pnls_s.values()), list(all_rs_s.values()))
    m_sell = metrics(fp_s, fr_s, "Always SELL")
    print(f"  Always SELL: N={m_sell['n']}, WR={m_sell['win_rate']:.1%}, AvgPnL={m_sell['avg_pnl_pips']:.2f}pip")

    # ── EXP 4: Parameter perturbation ──────────────────────────────────
    print("\n[6] EXP 4: Parameter perturbation...")
    param_variants = {}
    for sl in [1.5, 2.0, 2.5]:
        for rr in [2.5, 3.5, 4.5]:
            key = f"SL={sl}_RRR={rr}"
            ap = {}; ar = {}
            for p in pair_names:
                pnls, rs, _ = simulate(sigs[p], p, sl_mult=sl, rrr=rr,
                                    cost_pips=SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS)
                ap[p] = pnls; ar[p] = rs
            fpv, frv = merge(list(ap.values()), list(ar.values()))
            m = metrics(fpv, frv, key)
            param_variants[key] = m
            print(f"  {key}: N={m['n']}, WR={m['win_rate']:.1%}, "
                  f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── EXP 5: Year-by-year ───────────────────────────────────────────
    print("\n[7] EXP 5: Year-by-year...")
    # Re-run cost sim to get entry indices
    trade_ts = []
    trade_pnl = []
    trade_r = []
    for p in pair_names:
        spread = SPREAD_PIPS.get(p, 0.5)
        pnls, rs, eidx = simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR,
                                   cost_pips=spread + SLIPPAGE_PIPS)
        for j in range(len(pnls)):
            if j < len(eidx):
                trade_ts.append(sigs[p].index[eidx[j]])
                trade_pnl.append(pnls[j])
                trade_r.append(rs[j])

    yby = {}
    for ts, p, r in zip(trade_ts, trade_pnl, trade_r):
        y = str(ts.year)
        yby.setdefault(y, {"pnls": [], "rs": []})
        yby[y]["pnls"].append(p)
        yby[y]["rs"].append(r)

    yby_m = {}
    for y in sorted(yby.keys()):
        m = metrics(yby[y]["pnls"], yby[y]["rs"], y)
        yby_m[y] = m
        if m["n"] > 0:
            print(f"  {y}: N={m['n']}, WR={m['win_rate']:.1%}, "
                  f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── EXP 6: Permutation test ────────────────────────────────────────
    print("\n[8] EXP 6: Permutation test...")
    rng = np.random.RandomState(RNG_SEED)
    actual = np.array(fp_c)
    actual_mean = float(np.mean(actual))
    null = np.empty(N_PERM)
    for i in range(N_PERM):
        signs = rng.choice([-1, 1], size=len(actual))
        null[i] = float(np.mean(actual * signs))
    p_val_perm = float(np.mean(np.abs(null) >= np.abs(actual_mean)))
    perm = {
        "observed_mean_pips": round(actual_mean, 4),
        "null_mean": round(float(np.mean(null)), 4),
        "null_std": round(float(np.std(null)), 4),
        "p_value": round(p_val_perm, 6),
    }
    print(f"  Observed: {perm['observed_mean_pips']:.2f} pip")
    print(f"  Null: {perm['null_mean']:.2f} ± {perm['null_std']:.2f} pip")
    print(f"  p-value: {perm['p_value']:.4f}")

    # ── Classification ─────────────────────────────────────────────────
    print("\n[9] Classification...")
    has_gross = m_orig.get("avg_pnl_pips", 0) > 0 and m_orig.get("profit_factor", 0) > 1.0
    has_net = m_cost.get("avg_pnl_pips", 0) > 0 and m_cost.get("profit_factor", 0) > 1.0
    beats_random = m_cost.get("avg_pnl_pips", 0) > m_rand.get("avg_pnl_pips", 0)
    sig_pval = m_cost.get("p_value", 1.0) < 0.05
    param_robust = sum(1 for v in param_variants.values() if v.get("avg_pnl_pips", 0) > 0) / len(param_variants)
    pos_years = sum(1 for y, m in yby_m.items() if m.get("avg_pnl_pips", 0) > 0 and m["n"] > 0)
    tot_years = sum(1 for y, m in yby_m.items() if m["n"] > 0)

    if has_net and beats_random and sig_pval and param_robust >= 0.5:
        classification = "B. STRUCTURAL SUPPORT — PROMOTE"
    elif has_gross and not has_net:
        classification = "C. GROSS STRUCTURE EXISTS BUT ECONOMICALLY WEAK"
    elif has_gross and beats_random:
        classification = "D. REGIME/CONDITION SPECIFIC — CONDITIONAL PROMOTION"
    else:
        classification = "A. NO STRUCTURAL SUPPORT — KILL"

    print(f"  Gross edge: {has_gross}")
    print(f"  Net edge: {has_net}")
    print(f"  Beats random: {beats_random}")
    print(f"  Significant (p<0.05): {sig_pval}")
    print(f"  Param robust: {param_robust:.0%}")
    print(f"  Positive years: {pos_years}/{tot_years}")
    print(f"  Classification: {classification}")

    # ── Save ───────────────────────────────────────────────────────────
    results = {
        "phase": "S0", "title": "Archived Breakout Reassessment",
        "original_params": {
            "lookback": LOOKBACK, "atr_sl_mult": ATR_SL_MULT, "rrr": RRR,
            "max_hold_days": MAX_HOLD_DAYS, "breakeven_ratio": BREAKEVEN_RATIO,
        },
        "original_result": m_orig,
        "with_costs": m_cost,
        "controls": {"random": m_rand, "always_buy": m_buy, "always_sell": m_sell},
        "param_variants": param_variants,
        "year_by_year": yby_m,
        "permutation": perm,
        "classification": classification,
        "runtime_seconds": round(time.time() - t0, 1),
    }

    with open(out_dir / "S0_breakout_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f"S0 complete in {time.time()-t0:.1f}s")
    print(f"Classification: {classification}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
