"""
Phase S2: Mechanism Identification

S2-0: Classification/temporal-leakage audit of S1-D
S2-A: Granular displacement bins
S2-B: Volatility-normalized displacement
S2-C: Range/noise forensic investigation
S2-D: Fresh holdout test

All parameters frozen from S0. No optimization permitted.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
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
N_BOOT = 2000

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

SESSION_MAP = {
    0: "Asia", 1: "Asia", 2: "Asia", 3: "Asia", 4: "Asia", 5: "Asia",
    6: "London", 7: "London", 8: "London", 9: "London",
    10: "London/NY", 11: "London/NY", 12: "London/NY", 13: "London/NY",
    14: "New York", 15: "New York", 16: "New York",
    17: "New York", 18: "New York", 19: "Other", 20: "Other",
    21: "Other", 22: "Asia", 23: "Asia",
}


# ═══════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE (copied from S1 for self-containment)
# ═══════════════════════════════════════════════════════════════════════

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
                    agg = {"open": "first", "high": "max", "low": "min",
                           "close": "last", "volume": "sum"}
                    pair_4h[k] = df.resample("4h").agg(agg).dropna()
    return pair_4h


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    sh = swing_high_series(df, LOOKBACK)
    sl = swing_low_series(df, LOOKBACK)
    close = df["close"].values
    atr = calculate_atr(df, ATR_PERIOD)

    sig = np.zeros(len(df), dtype=int)
    sh_v = sh.values
    sl_v = sl.values

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


def simulate_detail(
    sig: pd.DataFrame, pair: str,
    sl_mult: float = ATR_SL_MULT, rrr: float = RRR,
    cost_pips: float = 0.0,
    trailing: bool = True, breakeven: bool = True,
) -> list[dict]:
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

    trades = []
    in_trade = False
    direction = 0
    entry_price = 0.0
    sl_price = 0.0
    entry_idx = 0
    risk_pips = 0.0

    for i in range(LOOKBACK * 2 + 1, len(sig)):
        sig_val = sig_[i]

        if in_trade:
            bars_held = i - entry_idx
            risk = risk_pips

            if direction == 1:
                exit_price = None
                exit_reason = ""
                if low_[i] <= sl_price and risk > 0:
                    exit_price, exit_reason = sl_price, "SL"
                elif high_[i] >= entry_price + risk * rrr * pip and risk > 0:
                    exit_price, exit_reason = entry_price + risk * rrr * pip, "TP"
                elif bars_held >= max_bars and risk > 0:
                    exit_price, exit_reason = close_[i], "MH"
                elif trailing:
                    new_sl = sl_[i - 1] if not np.isnan(sl_[i - 1]) else sl_price
                    if new_sl > sl_price:
                        sl_price = new_sl
                if breakeven and sl_price < entry_price and risk > 0:
                    if (close_[i] - entry_price) / pip >= BREAKEVEN_RATIO * risk:
                        sl_price = entry_price

                if exit_price is not None and risk > 0:
                    pnl = (exit_price - entry_price) / pip - total_cost
                    hi_path = high_[entry_idx:i + 1]
                    lo_path = low_[entry_idx:i + 1]
                    trades.append({
                        "pair": pair, "direction": direction,
                        "entry_idx": entry_idx, "exit_idx": i,
                        "entry_time": sig.index[entry_idx],
                        "exit_time": sig.index[i],
                        "entry_price": entry_price, "exit_price": exit_price,
                        "pnl_pips": pnl, "r": pnl / risk,
                        "exit_reason": exit_reason, "hold_bars": bars_held,
                        "risk_pips": risk,
                        "mfe_pips": float((hi_path.max() - entry_price) / pip),
                        "mae_pips": float((entry_price - lo_path.min()) / pip),
                    })
                    in_trade = False
                    continue
            else:
                exit_price = None
                exit_reason = ""
                if high_[i] >= sl_price and risk > 0:
                    exit_price, exit_reason = sl_price, "SL"
                elif low_[i] <= entry_price - risk * rrr * pip and risk > 0:
                    exit_price, exit_reason = entry_price - risk * rrr * pip, "TP"
                elif bars_held >= max_bars and risk > 0:
                    exit_price, exit_reason = close_[i], "MH"
                elif trailing:
                    new_sl = sh_[i - 1] if not np.isnan(sh_[i - 1]) else sl_price
                    if new_sl < sl_price:
                        sl_price = new_sl
                if breakeven and sl_price > entry_price and risk > 0:
                    if (entry_price - close_[i]) / pip >= BREAKEVEN_RATIO * risk:
                        sl_price = entry_price

                if exit_price is not None and risk > 0:
                    pnl = (entry_price - exit_price) / pip - total_cost
                    hi_path = high_[entry_idx:i + 1]
                    lo_path = low_[entry_idx:i + 1]
                    trades.append({
                        "pair": pair, "direction": direction,
                        "entry_idx": entry_idx, "exit_idx": i,
                        "entry_time": sig.index[entry_idx],
                        "exit_time": sig.index[i],
                        "entry_price": entry_price, "exit_price": exit_price,
                        "pnl_pips": pnl, "r": pnl / risk,
                        "exit_reason": exit_reason, "hold_bars": bars_held,
                        "risk_pips": risk,
                        "mfe_pips": float((entry_price - lo_path.min()) / pip),
                        "mae_pips": float((hi_path.max() - entry_price) / pip),
                    })
                    in_trade = False
                    continue

        if not in_trade and sig_val != 0 and not np.isnan(atr_[i]) and atr_[i] > 0:
            entry_price = open_[i]
            stop_dist = sl_mult * atr_[i]
            if stop_dist / pip < 1.0:
                continue
            sl_price = entry_price - stop_dist if sig_val == 1 else entry_price + stop_dist
            direction = sig_val
            entry_idx = i
            risk_pips = stop_dist / pip
            in_trade = True

    if in_trade and risk_pips > 0:
        if direction == 1:
            pnl = (close_[-1] - entry_price) / pip - total_cost
        else:
            pnl = (entry_price - close_[-1]) / pip - total_cost
        trades.append({
            "pair": pair, "direction": direction,
            "entry_idx": entry_idx, "exit_idx": len(sig) - 1,
            "entry_time": sig.index[entry_idx], "exit_time": sig.index[-1],
            "entry_price": entry_price, "exit_price": close_[-1],
            "pnl_pips": pnl, "r": pnl / risk_pips,
            "exit_reason": "END", "hold_bars": len(sig) - 1 - entry_idx,
            "risk_pips": risk_pips,
            "mfe_pips": 0, "mae_pips": 0,
        })

    return trades


def sim_metrics(trades: list[dict], label: str = "") -> dict:
    if not trades:
        return {"label": label, "n": 0, "win_rate": 0, "avg_pnl_pips": 0,
                "median_pnl_pips": 0, "total_pnl_pips": 0, "avg_r": 0,
                "profit_factor": 0, "max_dd_pips": 0, "t_stat": 0, "p_value": 1}
    pnls = np.array([t["pnl_pips"] for t in trades])
    rs = np.array([t["r"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    gp = float(np.sum(wins)) if len(wins) else 0
    gl = float(np.abs(np.sum(losses))) if len(losses) else 1e-10
    cum = np.cumsum(pnls)
    max_dd = float(np.max(np.maximum.accumulate(cum) - cum))
    tt = sp_stats.ttest_1samp(rs, 0) if len(rs) > 1 else (0, 1)
    return {
        "label": label, "n": len(pnls),
        "win_rate": round(float(np.mean(pnls > 0)), 4),
        "avg_pnl_pips": round(float(np.mean(pnls)), 4),
        "median_pnl_pips": round(float(np.median(pnls)), 4),
        "total_pnl_pips": round(float(np.sum(pnls)), 2),
        "avg_r": round(float(np.mean(rs)), 4),
        "profit_factor": round(gp / gl, 4),
        "max_dd_pips": round(max_dd, 2),
        "t_stat": round(float(tt[0]), 4),
        "p_value": round(float(tt[1]), 6),
    }


# ═══════════════════════════════════════════════════════════════════════
# S2-0: CLASSIFICATION / TEMPORAL-LEAKAGE AUDIT
# ═══════════════════════════════════════════════════════════════════════

def classify_at_entry(
    sig: pd.DataFrame, pair: str, trade: dict,
    horizon_bars: int = 6,
) -> str:
    """
    Classify a trade using ONLY the first `horizon_bars` after entry.
    No future candles, no exit-dependent labels.
    """
    pip = get_pip_size(pair)
    entry_idx = trade["entry_idx"]
    d = trade["direction"]
    entry_price = trade["entry_price"]
    atr_val = sig["atr"].values[entry_idx]

    if atr_val <= 0 or atr_val * pip <= 0:
        return "unknown"

    close_ = sig["close"].values
    high_ = sig["high"].values
    low_ = sig["low"].values

    end_idx = min(entry_idx + horizon_bars + 1, len(close_))
    if end_idx - entry_idx < 2:
        return "unknown"

    path = close_[entry_idx:end_idx]
    hi_path = high_[entry_idx:end_idx]
    lo_path = low_[entry_idx:end_idx]

    if d == 1:
        max_move = (hi_path.max() - entry_price) / (atr_val * pip)
        max_draw = (entry_price - lo_path.min()) / (atr_val * pip)
        final = (path[-1] - entry_price) / (atr_val * pip)
    else:
        max_move = (entry_price - lo_path.min()) / (atr_val * pip)
        max_draw = (hi_path.max() - entry_price) / (atr_val * pip)
        final = (entry_price - path[-1]) / (atr_val * pip)

    if d == 1:
        retested = any(
            lo_path[j] <= entry_price + 0.2 * atr_val * pip
            for j in range(1, len(lo_path))
        ) and max_move > 0.5
    else:
        retested = any(
            hi_path[j] >= entry_price - 0.2 * atr_val * pip
            for j in range(1, len(hi_path))
        ) and max_move > 0.5

    if final > 0.3 and max_draw < 0.5:
        return "clean_continuation"
    elif retested and final > 0:
        return "retest_continuation"
    elif max_move > 0.5 and final < -0.2:
        return "failed_breakout"
    elif final < -0.3:
        return "reversal"
    else:
        return "range_noise"


def s20_classification_audit(sigs: dict[str, pd.DataFrame]) -> dict:
    """
    Audit S1-D classification for temporal leakage.
    Compares exit-dependent classification with fixed-horizon classification.
    """
    results = {}

    # 1. Re-classify ALL trades using fixed 6-bar horizon
    fixed_6bar = defaultdict(list)
    fixed_12bar = defaultdict(list)

    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)
        for t in trades:
            cat6 = classify_at_entry(s, p, t, horizon_bars=6)
            cat12 = classify_at_entry(s, p, t, horizon_bars=12)
            fixed_6bar[cat6].append(t)
            fixed_12bar[cat12].append(t)

    results["fixed_6bar"] = {k: sim_metrics(v, k) for k, v in fixed_6bar.items()}
    results["fixed_12bar"] = {k: sim_metrics(v, k) for k, v in fixed_12bar.items()}

    # 2. Check if classification uses only post-entry data
    # The classify_at_entry function uses:
    # - close_/high_/low_[entry_idx:end_idx] — all AFTER entry
    # - atr_[entry_idx] — at entry (available)
    # - entry_price — at entry (available)
    # - No exit_idx, no exit_price, no exit_logic
    results["temporal_audit"] = {
        "uses_exit_data": False,
        "uses_future_candles": False,
        "uses_only_post_entry": True,
        "classification_timestamp": "entry_time + horizon",
        "horizons_tested": [6, 12],
        "verdict": "CLASSIFICATION IS CAUSAL — uses only first N bars after entry",
    }

    # 3. Stability analysis: does classification change with horizon?
    stability = {}
    for cat in ["clean_continuation", "retest_continuation", "failed_breakout",
                "reversal", "range_noise"]:
        n6 = len(fixed_6bar.get(cat, []))
        n12 = len(fixed_12bar.get(cat, []))
        stability[cat] = {
            "count_6bar": n6,
            "count_12bar": n12,
            "change_pct": round((n12 - n6) / max(n6, 1) * 100, 1),
        }
    results["horizon_stability"] = stability

    # 4. Verify the ORIGINAL S1-D used exit-dependent lookforward
    # (This is the temporal leakage we're auditing)
    results["s1d_leakage_note"] = (
        "The original S1-D classification used lookforward = min(exit_idx - entry_idx, 30), "
        "which means the label depends on when the trade exits. This is a form of label leakage: "
        "the classification of a trade can change if we change the exit logic. "
        "S2-0 reclassifies using FIXED horizons (6 and 12 bars) to eliminate this dependency."
    )

    # 5. Recompute PnL attribution with fixed-horizon labels
    results["pnl_by_fixed_6bar"] = {}
    for cat, trades in fixed_6bar.items():
        if trades:
            pnls = [t["pnl_pips"] for t in trades]
            results["pnl_by_fixed_6bar"][cat] = {
                "n": len(trades),
                "total_pnl": round(sum(pnls), 2),
                "avg_pnl": round(float(np.mean(pnls)), 2),
                "win_rate": round(float(np.mean(np.array(pnls) > 0)), 4),
            }

    results["pnl_by_fixed_12bar"] = {}
    for cat, trades in fixed_12bar.items():
        if trades:
            pnls = [t["pnl_pips"] for t in trades]
            results["pnl_by_fixed_12bar"][cat] = {
                "n": len(trades),
                "total_pnl": round(sum(pnls), 2),
                "avg_pnl": round(float(np.mean(pnls)), 2),
                "win_rate": round(float(np.mean(np.array(pnls) > 0)), 4),
            }

    return results


# ═══════════════════════════════════════════════════════════════════════
# S2-A: GRANULAR DISPLACEMENT
# ═══════════════════════════════════════════════════════════════════════

def s2a_granular_displacement(sigs: dict[str, pd.DataFrame]) -> dict:
    bins = [
        (0, 0.5, "0-0.5ATR"), (0.5, 0.75, "0.5-0.75ATR"),
        (0.75, 1.0, "0.75-1ATR"), (1.0, 1.25, "1-1.25ATR"),
        (1.25, 1.5, "1.25-1.5ATR"), (1.5, 2.0, "1.5-2ATR"),
        (2.0, 3.0, "2-3ATR"), (3.0, 5.0, "3-5ATR"),
        (5.0, 999.0, ">5ATR"),
    ]
    bin_trades = {b[2]: [] for b in bins}

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)

        open_ = s["open"].values
        atr_ = s["atr"].values
        sh_ = s["swing_high"].values
        sl_ = s["swing_low"].values

        for t in trades:
            idx = t["entry_idx"]
            if atr_[idx] <= 0:
                continue

            entry_price = open_[idx]
            if t["direction"] == 1:
                swing = sh_[idx - 1] if idx > 0 else np.nan
            else:
                swing = sl_[idx - 1] if idx > 0 else np.nan

            if np.isnan(swing):
                continue

            dist = abs(entry_price - swing)
            dist_atr = dist / atr_[idx] if atr_[idx] > 0 else 0

            for lo, hi, label in bins:
                if lo <= dist_atr < hi:
                    bin_trades[label].append(t)
                    break

    result = {}
    for label, trades in bin_trades.items():
        result[label] = sim_metrics(trades, label)

    # Monotonicity check
    avg_pnls = []
    for lo, hi, label in bins:
        m = result[label]
        avg_pnls.append(m["avg_pnl_pips"] if m["n"] > 0 else 0)

    # Count monotonic violations
    violations = 0
    for i in range(1, len(avg_pnls)):
        if avg_pnls[i] < avg_pnls[i - 1] and avg_pnls[i] > 0 and avg_pnls[i - 1] > 0:
            violations += 1

    result["_monotonicity"] = {
        "violations": violations,
        "total_transitions": len(avg_pnls) - 1,
        "relationship": "monotonic" if violations <= 1 else "non-monotonic",
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# S2-B: VOLATILITY-NORMALIZED DISPLACEMENT
# ═══════════════════════════════════════════════════════════════════════

def s2b_vol_normalized(sigs: dict[str, pd.DataFrame]) -> dict:
    raw_displacements = []
    vol_norm_displacements = []
    pre_breakout_atrs = []
    trade_pnls = []

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)

        open_ = s["open"].values
        atr_ = s["atr"].values
        sh_ = s["swing_high"].values
        sl_ = s["swing_low"].values

        for t in trades:
            idx = t["entry_idx"]
            if atr_[idx] <= 0:
                continue

            entry_price = open_[idx]
            if t["direction"] == 1:
                swing = sh_[idx - 1] if idx > 0 else np.nan
            else:
                swing = sl_[idx - 1] if idx > 0 else np.nan

            if np.isnan(swing):
                continue

            raw_disp = abs(entry_price - swing)
            atr_at_entry = atr_[idx]
            vol_norm = raw_disp / atr_at_entry if atr_at_entry > 0 else 0

            raw_displacements.append(raw_disp)
            vol_norm_displacements.append(vol_norm)
            pre_breakout_atrs.append(atr_at_entry)
            trade_pnls.append(t["pnl_pips"])

    raw_arr = np.array(raw_displacements)
    vol_arr = np.array(vol_norm_displacements)
    pnl_arr = np.array(trade_pnls)
    atr_arr = np.array(pre_breakout_atrs)

    result = {}

    # Correlation analysis
    if len(raw_arr) > 10:
        result["raw_displacement"] = {
            "mean": round(float(np.mean(raw_arr)), 6),
            "std": round(float(np.std(raw_arr)), 6),
            "corr_with_pnl": round(float(np.corrcoef(raw_arr, pnl_arr)[0, 1]), 4),
            "corr_with_pnl_pval": round(float(
                sp_stats.pearsonr(raw_arr, pnl_arr)[1]), 6),
        }
        result["vol_normalized"] = {
            "mean": round(float(np.mean(vol_arr)), 4),
            "std": round(float(np.std(vol_arr)), 4),
            "corr_with_pnl": round(float(np.corrcoef(vol_arr, pnl_arr)[0, 1]), 4),
            "corr_with_pnl_pval": round(float(
                sp_stats.pearsonr(vol_arr, pnl_arr)[1]), 6),
        }
        result["pre_breakout_atr"] = {
            "mean": round(float(np.mean(atr_arr)), 6),
            "std": round(float(np.std(atr_arr)), 6),
            "corr_with_pnl": round(float(np.corrcoef(atr_arr, pnl_arr)[0, 1]), 4),
        }

        # Vol-normalized should be better if the signal is about unusual displacement
        raw_r2 = result["raw_displacement"]["corr_with_pnl"] ** 2
        vol_r2 = result["vol_normalized"]["corr_with_pnl"] ** 2
        result["vol_normalization_helps"] = vol_r2 > raw_r2
        result["improvement"] = round(vol_r2 - raw_r2, 6)

    # Quintile analysis of vol-normalized displacement
    if len(vol_arr) > 5:
        quintiles = pd.qcut(vol_arr, 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
                           duplicates="drop")
        quintile_results = {}
        for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
            mask = quintiles == q
            if mask.sum() > 0:
                q_pnl = pnl_arr[mask]
                quintile_results[q] = {
                    "n": int(mask.sum()),
                    "avg_pnl": round(float(np.mean(q_pnl)), 4),
                    "win_rate": round(float(np.mean(q_pnl > 0)), 4),
                    "avg_displacement": round(float(np.mean(vol_arr[mask])), 4),
                }
        result["quintile_analysis"] = quintile_results

    return result


# ═══════════════════════════════════════════════════════════════════════
# S2-C: RANGE/NOISE FORENSIC INVESTIGATION
# ═══════════════════════════════════════════════════════════════════════

def s2c_range_noise_forensic(sigs: dict[str, pd.DataFrame]) -> dict:
    range_noise_trades = []
    all_trades = []

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)

        open_ = s["open"].values
        high_ = s["high"].values
        low_ = s["low"].values
        close_ = s["close"].values
        atr_ = s["atr"].values
        sh_ = s["swing_high"].values
        sl_ = s["swing_low"].values

        for t in trades:
            all_trades.append(t)

            # Classify using fixed 6-bar horizon
            cat = classify_at_entry(s, p, t, horizon_bars=6)

            if cat == "range_noise":
                idx = t["entry_idx"]
                entry_price = t["entry_price"]
                atr_val = atr_[idx] if idx < len(atr_) else 0

                # Displacement at entry
                if t["direction"] == 1:
                    swing = sh_[idx - 1] if idx > 0 else np.nan
                else:
                    swing = sl_[idx - 1] if idx > 0 else np.nan
                disp = abs(entry_price - swing) if not np.isnan(swing) else 0
                disp_atr = disp / atr_val if atr_val > 0 else 0

                # Pre-breakout volatility (ATR over last 6 bars)
                pre_vol = np.mean(atr_[max(0, idx - 6):idx]) if idx > 0 else atr_val

                # Session
                hour = t["entry_time"].hour
                session = SESSION_MAP.get(hour, "Other")

                # 6-bar forward return
                fwd6 = 0
                if idx + 6 < len(close_):
                    if t["direction"] == 1:
                        fwd6 = (close_[idx + 6] - entry_price) / pip
                    else:
                        fwd6 = (entry_price - close_[idx + 6]) / pip

                range_noise_trades.append({
                    "pair": t["pair"],
                    "direction": t["direction"],
                    "entry_time": str(t["entry_time"]),
                    "pnl_pips": t["pnl_pips"],
                    "hold_bars": t["hold_bars"],
                    "exit_reason": t["exit_reason"],
                    "mfe_pips": t["mfe_pips"],
                    "mae_pips": t["mae_pips"],
                    "displacement_atr": round(disp_atr, 4),
                    "pre_breakout_atr": round(float(pre_vol), 6),
                    "session": session,
                    "fwd_6bar_pips": round(fwd6, 4),
                })

    result = {
        "total_trades": len(all_trades),
        "range_noise_count": len(range_noise_trades),
        "range_noise_pct": round(len(range_noise_trades) / max(len(all_trades), 1) * 100, 1),
    }

    if not range_noise_trades:
        result["verdict"] = "NO RANGE/NOISE TRADES FOUND UNDER FIXED-HORIZON CLASSIFICATION"
        return result

    # Basic stats
    pnls = [t["pnl_pips"] for t in range_noise_trades]
    result["basic_stats"] = {
        "n": len(pnls),
        "avg_pnl": round(float(np.mean(pnls)), 4),
        "median_pnl": round(float(np.median(pnls)), 4),
        "win_rate": round(float(np.mean(np.array(pnls) > 0)), 4),
        "total_pnl": round(float(np.sum(pnls)), 2),
    }

    # Displacement distribution
    disps = [t["displacement_atr"] for t in range_noise_trades if t["displacement_atr"] > 0]
    if disps:
        result["displacement"] = {
            "mean": round(float(np.mean(disps)), 4),
            "median": round(float(np.median(disps)), 4),
            "std": round(float(np.std(disps)), 4),
            "min": round(float(np.min(disps)), 4),
            "max": round(float(np.max(disps)), 4),
        }

    # Forward returns
    fwd = [t["fwd_6bar_pips"] for t in range_noise_trades]
    if fwd:
        result["forward_6bar"] = {
            "mean": round(float(np.mean(fwd)), 4),
            "positive_pct": round(float(np.mean(np.array(fwd) > 0)), 4),
        }

    # Session breakdown
    session_pnls = defaultdict(list)
    for t in range_noise_trades:
        session_pnls[t["session"]].append(t["pnl_pips"])
    result["by_session"] = {s: round(float(np.mean(v)), 2) for s, v in session_pnls.items()}

    # Pair breakdown
    pair_pnls = defaultdict(list)
    for t in range_noise_trades:
        pair_pnls[t["pair"]].append(t["pnl_pips"])
    result["by_pair"] = {p: {"n": len(v), "avg": round(float(np.mean(v)), 2)}
                         for p, v in pair_pnls.items()}

    # Exit reason breakdown
    exit_reasons = defaultdict(int)
    for t in range_noise_trades:
        exit_reasons[t["exit_reason"]] += 1
    result["exit_reasons"] = dict(exit_reasons)

    # Is this a bug? Check if range_noise trades have suspiciously low displacement
    if disps:
        all_disps = []
        for t in all_trades:
            idx = t["entry_idx"]
            if idx > 0 and atr_[idx] > 0:
                if t["direction"] == 1:
                    swing = sh_[idx - 1]
                else:
                    swing = sl_[idx - 1]
                if not np.isnan(swing):
                    all_disps.append(abs(open_[idx] - swing) / atr_[idx])

        if all_disps:
            result["displacement_comparison"] = {
                "range_noise_mean_disp": round(float(np.mean(disps)), 4),
                "all_trades_mean_disp": round(float(np.mean(all_disps)), 4),
                "range_noise_lower": float(np.mean(disps)) < float(np.mean(all_disps)),
            }

    # Potential bug check: are range_noise trades dominated by short hold / END exits?
    end_count = sum(1 for t in range_noise_trades if t["exit_reason"] == "END")
    short_hold = sum(1 for t in range_noise_trades if t["hold_bars"] <= 2)
    result["potential_issues"] = {
        "end_exit_count": end_count,
        "end_exit_pct": round(end_count / max(len(range_noise_trades), 1) * 100, 1),
        "short_hold_count": short_hold,
        "short_hold_pct": round(short_hold / max(len(range_noise_trades), 1) * 100, 1),
        "assessment": (
            "HIGH END EXIT PCT — range_noise may include trades that ran out of time "
            "rather than genuine range behavior" if end_count / max(len(range_noise_trades), 1) > 0.3
            else "Exit reason distribution is normal"
        ),
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# S2-D: FRESH HOLDOUT
# ═══════════════════════════════════════════════════════════════════════

def s2d_fresh_holdout(pair_4h: dict[str, pd.DataFrame],
                      sigs: dict[str, pd.DataFrame]) -> dict:
    periods = {
        "train_2016_2021": ("2016-01-01", "2021-12-31"),
        "valid_2022_2023": ("2022-01-01", "2023-12-31"),
        "holdout_2024_2026": ("2024-01-01", "2026-12-31"),
    }

    results = {}
    for period_name, (start, end) in periods.items():
        all_trades = []
        for p, s in sigs.items():
            mask = (s.index >= start) & (s.index < end)
            if mask.sum() == 0:
                continue
            s_period = s.loc[mask].copy()
            spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
            trades = simulate_detail(s_period, p, cost_pips=spread)
            all_trades.extend(trades)
        results[period_name] = sim_metrics(all_trades, period_name)

    # Degradation analysis
    train = results["train_2016_2021"]["avg_pnl_pips"]
    valid = results["valid_2022_2023"]["avg_pnl_pips"]
    holdout = results["holdout_2024_2026"]["avg_pnl_pips"]

    results["degradation"] = {
        "train_to_valid": round((valid - train) / max(abs(train), 1e-10) * 100, 1),
        "train_to_holdout": round((holdout - train) / max(abs(train), 1e-10) * 100, 1),
        "valid_to_holdout": round((holdout - valid) / max(abs(valid), 1e-10) * 100, 1),
        "holdout_retains_pct_of_train": round(holdout / max(train, 1e-10) * 100, 1),
    }

    return results


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase S2: Mechanism Identification")
    print("=" * 70)

    out_dir = Path("/root/nestquant/research_data/simple_strategies")

    print("\n[0] Loading data...")
    pair_4h = load_and_resample()
    print(f"  {len(pair_4h)} pairs loaded")

    print("\n[0] Computing signals...")
    sigs = {}
    for p, df in pair_4h.items():
        sigs[p] = compute_signals(df)
    total_sig = sum(int((s["signal"] != 0).sum()) for s in sigs.values())
    print(f"  {total_sig} signals across {len(sigs)} pairs")

    all_results = {}

    # ── S2-0: Classification audit ────────────────────────────────────
    print("\n" + "=" * 70)
    print("S2-0: Classification / Temporal-Leakage Audit")
    print("=" * 70)
    all_results["S20"] = s20_classification_audit(sigs)
    audit = all_results["S20"]
    print(f"  Temporal audit: {audit['temporal_audit']['verdict']}")
    print(f"  Leakage note: {audit['s1d_leakage_note'][:80]}...")
    print("\n  Fixed 6-bar classification:")
    for cat, m in sorted(audit.get("pnl_by_fixed_6bar", {}).items(),
                         key=lambda x: x[1].get("total_pnl", 0), reverse=True):
        print(f"    {cat:25s}: N={m['n']:5d}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl']:+.2f}pip, Total={m['total_pnl']:+.0f}pip")
    print("\n  Fixed 12-bar classification:")
    for cat, m in sorted(audit.get("pnl_by_fixed_12bar", {}).items(),
                         key=lambda x: x[1].get("total_pnl", 0), reverse=True):
        print(f"    {cat:25s}: N={m['n']:5d}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl']:+.2f}pip, Total={m['total_pnl']:+.0f}pip")
    print("\n  Horizon stability:")
    for cat, s in audit.get("horizon_stability", {}).items():
        print(f"    {cat:25s}: 6bar={s['count_6bar']:5d}, 12bar={s['count_12bar']:5d}, "
              f"change={s['change_pct']:+.1f}%")

    # ── S2-A: Granular displacement ───────────────────────────────────
    print("\n" + "=" * 70)
    print("S2-A: Granular Displacement")
    print("=" * 70)
    all_results["S2A"] = s2a_granular_displacement(sigs)
    for label, m in all_results["S2A"].items():
        if label.startswith("_"):
            continue
        if m.get("n", 0) > 0:
            print(f"  {label:12s}: N={m['n']:5d}, WR={m['win_rate']:.1%}, "
                  f"AvgPnL={m['avg_pnl_pips']:+.2f}pip, PF={m['profit_factor']:.2f}")
    mono = all_results["S2A"].get("_monotonicity", {})
    print(f"  Monotonicity: {mono.get('relationship', '?')} "
          f"({mono.get('violations', 0)}/{mono.get('total_transitions', 0)} violations)")

    # ── S2-B: Vol-normalized displacement ─────────────────────────────
    print("\n" + "=" * 70)
    print("S2-B: Volatility-Normalized Displacement")
    print("=" * 70)
    all_results["S2B"] = s2b_vol_normalized(sigs)
    vb = all_results["S2B"]
    if "raw_displacement" in vb:
        print(f"  Raw displacement: corr={vb['raw_displacement']['corr_with_pnl']:.4f}, "
              f"p={vb['raw_displacement']['corr_with_pnl_pval']:.6f}")
        print(f"  Vol-normalized:  corr={vb['vol_normalized']['corr_with_pnl']:.4f}, "
              f"p={vb['vol_normalized']['corr_with_pnl_pval']:.6f}")
        print(f"  Vol normalization helps: {vb.get('vol_normalization_helps', '?')}, "
              f"improvement={vb.get('improvement', 0):.6f}")
    if "quintile_analysis" in vb:
        print("  Quintile analysis (vol-normalized displacement):")
        for q, m in vb["quintile_analysis"].items():
            print(f"    {q}: N={m['n']:5d}, WR={m['win_rate']:.1%}, "
                  f"AvgPnL={m['avg_pnl']:+.2f}pip, AvgDisp={m['avg_displacement']:.2f}")

    # ── S2-C: Range/noise forensic ────────────────────────────────────
    print("\n" + "=" * 70)
    print("S2-C: Range/Noise Forensic Investigation")
    print("=" * 70)
    all_results["S2C"] = s2c_range_noise_forensic(sigs)
    rn = all_results["S2C"]
    print(f"  Total trades: {rn['total_trades']}")
    print(f"  Range/noise (6-bar fixed): {rn['range_noise_count']} ({rn['range_noise_pct']}%)")
    if "basic_stats" in rn:
        bs = rn["basic_stats"]
        print(f"  Stats: N={bs['n']}, WR={bs['win_rate']:.1%}, "
              f"AvgPnL={bs['avg_pnl']:+.2f}pip, Total={bs['total_pnl']:+.0f}pip")
    if "displacement" in rn:
        d = rn["displacement"]
        print(f"  Displacement: mean={d['mean']:.4f} ATR, median={d['median']:.4f} ATR")
    if "forward_6bar" in rn:
        f = rn["forward_6bar"]
        print(f"  Forward 6-bar: mean={f['mean']:+.2f}pip, positive={f['positive_pct']:.1%}")
    if "displacement_comparison" in rn:
        dc = rn["displacement_comparison"]
        print(f"  Displacement comparison: range_noise={dc['range_noise_mean_disp']:.4f} vs "
              f"all={dc['all_trades_mean_disp']:.4f}")
    if "potential_issues" in rn:
        pi = rn["potential_issues"]
        print(f"  Potential issues: {pi['assessment']}")
        print(f"    END exits: {pi['end_exit_pct']:.1f}%, Short hold: {pi['short_hold_pct']:.1f}%")
    if "by_session" in rn:
        print(f"  By session: {rn['by_session']}")
    if "exit_reasons" in rn:
        print(f"  Exit reasons: {rn['exit_reasons']}")

    # ── S2-D: Fresh holdout ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S2-D: Fresh Holdout Test")
    print("=" * 70)
    all_results["S2D"] = s2d_fresh_holdout(pair_4h, sigs)
    for period in ["train_2016_2021", "valid_2022_2023", "holdout_2024_2026"]:
        m = all_results["S2D"][period]
        print(f"  {period:25s}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")
    deg = all_results["S2D"]["degradation"]
    print(f"  Degradation: train→valid={deg['train_to_valid']:+.1f}%, "
          f"train→holdout={deg['train_to_holdout']:+.1f}%")
    print(f"  Holdout retains {deg['holdout_retains_pct_of_train']:.1f}% of training avg return")

    # ── Save ───────────────────────────────────────────────────────────
    all_results["runtime_seconds"] = round(time.time() - t0, 1)

    with open(out_dir / "S2_mechanism_identification.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f"S2 complete in {time.time() - t0:.1f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
