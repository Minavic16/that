"""
Phase S1: Archived Breakout Structural Interrogation

Thirteen sub-experiments (S1-A through S1-M) probing whether the S0
breakout edge is genuine or an artifact.

All parameters are frozen from S0. No optimization permitted.
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
N_PERM = 500
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
# INFRASTRUCTURE
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
    direction_override: int = None,
    rng: np.random.RandomState = None,
    exit_mode: str = "original",
    date_mask: pd.DatetimeIndex = None,
) -> list[dict]:
    """
    Full trade simulation returning detailed records.
    exit_mode: "original", "fixed_1R", "fixed_2R", "fixed_3R", "time_only", "atr_trail_only"
    """
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
        if rng is not None:
            sig_val = rng.choice([-1, 0, 1], p=[0.4, 0.2, 0.4])
        if direction_override is not None:
            sig_val = direction_override

        if in_trade:
            bars_held = i - entry_idx
            risk = risk_pips

            if direction == 1:
                exit_price = None
                exit_reason = ""

                if exit_mode == "original":
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

                elif exit_mode == "fixed_1R":
                    if low_[i] <= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif high_[i] >= entry_price + risk * pip and risk > 0:
                        exit_price, exit_reason = entry_price + risk * pip, "TP"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "fixed_2R":
                    if low_[i] <= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif high_[i] >= entry_price + 2 * risk * pip and risk > 0:
                        exit_price, exit_reason = entry_price + 2 * risk * pip, "TP"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "fixed_3R":
                    if low_[i] <= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif high_[i] >= entry_price + 3 * risk * pip and risk > 0:
                        exit_price, exit_reason = entry_price + 3 * risk * pip, "TP"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "time_only":
                    if bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "atr_trail_only":
                    if low_[i] <= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"
                    elif trailing:
                        new_sl = sl_[i - 1] if not np.isnan(sl_[i - 1]) else sl_price
                        if new_sl > sl_price:
                            sl_price = new_sl

                if exit_price is not None and risk > 0:
                    pnl = (exit_price - entry_price) / pip - total_cost
                    trades.append({
                        "pair": pair, "direction": direction,
                        "entry_idx": entry_idx, "exit_idx": i,
                        "entry_time": sig.index[entry_idx],
                        "exit_time": sig.index[i],
                        "entry_price": entry_price, "exit_price": exit_price,
                        "pnl_pips": pnl, "r": pnl / risk,
                        "exit_reason": exit_reason, "hold_bars": bars_held,
                        "risk_pips": risk,
                        "mfe_pips": max(0, (high_[entry_idx:i + 1].max() - entry_price) / pip),
                        "mae_pips": max(0, (entry_price - low_[entry_idx:i + 1].min()) / pip),
                    })
                    in_trade = False
                    continue

            else:
                exit_price = None
                exit_reason = ""

                if exit_mode == "original":
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

                elif exit_mode == "fixed_1R":
                    if high_[i] >= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif low_[i] <= entry_price - risk * pip and risk > 0:
                        exit_price, exit_reason = entry_price - risk * pip, "TP"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "fixed_2R":
                    if high_[i] >= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif low_[i] <= entry_price - 2 * risk * pip and risk > 0:
                        exit_price, exit_reason = entry_price - 2 * risk * pip, "TP"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "fixed_3R":
                    if high_[i] >= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif low_[i] <= entry_price - 3 * risk * pip and risk > 0:
                        exit_price, exit_reason = entry_price - 3 * risk * pip, "TP"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "time_only":
                    if bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"

                elif exit_mode == "atr_trail_only":
                    if high_[i] >= sl_price and risk > 0:
                        exit_price, exit_reason = sl_price, "SL"
                    elif bars_held >= max_bars:
                        exit_price, exit_reason = close_[i], "MH"
                    elif trailing:
                        new_sl = sh_[i - 1] if not np.isnan(sh_[i - 1]) else sl_price
                        if new_sl < sl_price:
                            sl_price = new_sl

                if exit_price is not None and risk > 0:
                    pnl = (entry_price - exit_price) / pip - total_cost
                    trades.append({
                        "pair": pair, "direction": direction,
                        "entry_idx": entry_idx, "exit_idx": i,
                        "entry_time": sig.index[entry_idx],
                        "exit_time": sig.index[i],
                        "entry_price": entry_price, "exit_price": exit_price,
                        "pnl_pips": pnl, "r": pnl / risk,
                        "exit_reason": exit_reason, "hold_bars": bars_held,
                        "risk_pips": risk,
                        "mfe_pips": max(0, (entry_price - low_[entry_idx:i + 1].min()) / pip),
                        "mae_pips": max(0, (high_[entry_idx:i + 1].max() - entry_price) / pip),
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
        return {"label": label, "n": 0}
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
# S1-A: PAIR-LEVEL GENERALIZATION
# ═══════════════════════════════════════════════════════════════════════

def s1a_pair_level(sigs: dict[str, pd.DataFrame]) -> dict:
    pair_results = {}
    all_trades = []
    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5)
        trades = simulate_detail(s, p, cost_pips=spread + SLIPPAGE_PIPS)
        m = sim_metrics(trades, p)
        pair_results[p] = m
        all_trades.extend(trades)

    agg = sim_metrics(all_trades, "Aggregate")

    profitable = sum(1 for m in pair_results.values() if m.get("avg_pnl_pips", 0) > 0 and m["n"] > 0)

    sorted_pairs = sorted(pair_results.items(), key=lambda x: x[1].get("avg_pnl_pips", 0), reverse=True)

    top_n = [3, 5]
    removal_results = {}
    for n in top_n:
        top_pairs = [p for p, _ in sorted_pairs[:n]]
        filtered = [t for t in all_trades if t["pair"] not in top_pairs]
        removal_results[f"remove_top_{n}"] = sim_metrics(filtered, f"remove_top_{n}")

    for n in [1, 2, 3]:
        bottom_pairs = [p for p, _ in sorted_pairs[-n:]]
        filtered = [t for t in all_trades if t["pair"] not in bottom_pairs]
        removal_results[f"remove_bottom_{n}"] = sim_metrics(filtered, f"remove_bottom_{n}")

    return {
        "pair_results": pair_results,
        "aggregate": agg,
        "profitable_pairs": profitable,
        "total_pairs": len(pair_results),
        "sorted_by_pnl": [(p, m["avg_pnl_pips"]) for p, m in sorted_pairs],
        "removal_analysis": removal_results,
    }


# ═══════════════════════════════════════════════════════════════════════
# S1-B: DIRECTIONAL BIAS CONTROL
# ═══════════════════════════════════════════════════════════════════════

def s1b_directional_bias(sigs: dict[str, pd.DataFrame]) -> dict:
    results = {}

    breakout_all = []
    breakout_buys = []
    breakout_sells = []
    random_all = []
    random_buys = []
    random_sells = []
    rng = np.random.RandomState(RNG_SEED)

    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS

        bt = simulate_detail(s, p, cost_pips=spread)
        breakout_all.extend(bt)
        breakout_buys.extend([t for t in bt if t["direction"] == 1])
        breakout_sells.extend([t for t in bt if t["direction"] == -1])

        rt = simulate_detail(s, p, cost_pips=spread,
                             rng=np.random.RandomState(RNG_SEED))
        random_all.extend(rt)

        rb = simulate_detail(s, p, cost_pips=spread,
                             rng=np.random.RandomState(RNG_SEED + 1))
        random_buys.extend(rb)

        rs = simulate_detail(s, p, cost_pips=spread,
                             rng=np.random.RandomState(RNG_SEED + 2))
        random_sells.extend(rs)

    results["breakout"] = sim_metrics(breakout_all, "Breakout")
    results["random"] = sim_metrics(random_all, "Random")
    results["breakout_buys"] = sim_metrics(breakout_buys, "Breakout BUYs")
    results["breakout_sells"] = sim_metrics(breakout_sells, "Breakout SELLs")
    results["random_buys"] = sim_metrics(random_buys, "Random BUYs")
    results["random_sells"] = sim_metrics(random_sells, "Random SELLs")

    results["incremental_vs_random"] = round(
        results["breakout"]["avg_pnl_pips"] - results["random"]["avg_pnl_pips"], 4)
    results["incremental_vs_random_buy"] = round(
        results["breakout_buys"]["avg_pnl_pips"] - results["random_buys"]["avg_pnl_pips"], 4)
    results["incremental_vs_random_sell"] = round(
        results["breakout_sells"]["avg_pnl_pips"] - results["random_sells"]["avg_pnl_pips"], 4)

    return results


# ═══════════════════════════════════════════════════════════════════════
# S1-C: ENTRY-THRESHOLD / DISTANCE TEST
# ═══════════════════════════════════════════════════════════════════════

def s1c_entry_distance(sigs: dict[str, pd.DataFrame]) -> dict:
    bins = [(0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 999.0)]
    bin_labels = ["0-0.1ATR", "0.1-0.25ATR", "0.25-0.5ATR", "0.5-1ATR", ">1ATR"]

    bin_trades = {bl: [] for bl in bin_labels}

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)

        open_ = s["open"].values
        atr_ = s["atr"].values
        sh_ = s["swing_high"].values
        sl_ = s["swing_low"].values
        sig_ = s["signal"].values

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

            dist_atr = abs(entry_price - swing) / (atr_[idx] * pip) if atr_[idx] * pip > 0 else 0

            for (lo, hi), label in zip(bins, bin_labels):
                if lo <= dist_atr < hi:
                    bin_trades[label].append(t)
                    break

    result = {}
    for label in bin_labels:
        trades = bin_trades[label]
        result[label] = sim_metrics(trades, label)

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-D: FALSE-BREAK / RETEST STRUCTURE
# ═══════════════════════════════════════════════════════════════════════

def s1d_false_break(sigs: dict[str, pd.DataFrame]) -> dict:
    categories = {
        "clean_continuation": [],
        "retest_continuation": [],
        "failed_breakout": [],
        "reversal": [],
        "range_noise": [],
    }

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)

        close_ = s["close"].values
        high_ = s["high"].values
        low_ = s["low"].values
        open_ = s["open"].values
        atr_ = s["atr"].values

        for t in trades:
            entry_idx = t["entry_idx"]
            exit_idx = t["exit_idx"]
            d = t["direction"]
            atr_val = atr_[entry_idx]
            if atr_val <= 0 or entry_idx >= len(close_) - 1:
                continue

            entry_price = t["entry_price"]
            lookforward = min(exit_idx - entry_idx, 30)
            if lookforward < 2:
                categories["range_noise"].append(t)
                continue

            path = close_[entry_idx:entry_idx + lookforward + 1]
            hi_path = high_[entry_idx:entry_idx + lookforward + 1]
            lo_path = low_[entry_idx:entry_idx + lookforward + 1]

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
                categories["clean_continuation"].append(t)
            elif retested and final > 0:
                categories["retest_continuation"].append(t)
            elif max_move > 0.5 and final < -0.2:
                categories["failed_breakout"].append(t)
            elif final < -0.3:
                categories["reversal"].append(t)
            else:
                categories["range_noise"].append(t)

    result = {}
    for cat, trades in categories.items():
        result[cat] = sim_metrics(trades, cat)
        result[cat]["count"] = len(trades)

    total = sum(len(v) for v in categories.values())
    for cat in result:
        result[cat]["pct_of_total"] = round(result[cat]["count"] / max(total, 1) * 100, 1)

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-E: TIME-OF-DAY / SESSION DEPENDENCE
# ═══════════════════════════════════════════════════════════════════════

def s1e_session(sigs: dict[str, pd.DataFrame]) -> dict:
    session_trades = defaultdict(list)

    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)
        for t in trades:
            hour = t["entry_time"].hour
            session = SESSION_MAP.get(hour, "Other")
            session_trades[session].append(t)

    result = {}
    for session, trades in session_trades.items():
        result[session] = sim_metrics(trades, session)

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-F: VOLATILITY REGIME
# ═══════════════════════════════════════════════════════════════════════

def s1f_volatility_regime(sigs: dict[str, pd.DataFrame]) -> dict:
    all_trades = []
    all_atr_percentiles = []

    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)
        atr_ = s["atr"].values

        for t in trades:
            idx = t["entry_idx"]
            if idx < len(atr_) and atr_[idx] > 0:
                all_atr_percentiles.append(atr_[idx])
            all_trades.append(t)

    if not all_atr_percentiles:
        return {}

    atr_arr = np.array(all_atr_percentiles)
    p20, p40, p60, p80 = np.percentile(atr_arr, [20, 40, 60, 80])

    vol_bins = {
        "LOW": (0, p20),
        "LOW-MEDIUM": (p20, p40),
        "MEDIUM": (p40, p60),
        "MEDIUM-HIGH": (p60, p80),
        "HIGH": (p80, np.inf),
    }

    bin_trades = {k: [] for k in vol_bins}
    for t in all_trades:
        idx = t["entry_idx"]
        atr_val = sigs[t["pair"]]["atr"].values[idx] if idx < len(sigs[t["pair"]]["atr"].values) else 0
        if atr_val <= 0:
            continue
        for label, (lo, hi) in vol_bins.items():
            if lo <= atr_val < hi:
                bin_trades[label].append(t)
                break

    result = {}
    for label in vol_bins:
        result[label] = sim_metrics(bin_trades[label], label)

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-G: TREND / RANGE REGIME
# ═══════════════════════════════════════════════════════════════════════

def s1g_trend_regime(sigs: dict[str, pd.DataFrame]) -> dict:
    regime_trades = {"trending": [], "ranging": [], "expanding": [], "contracting": []}

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)
        close_ = s["close"].values
        high_ = s["high"].values
        low_ = s["low"].values
        atr_ = s["atr"].values

        ema50 = pd.Series(close_).ewm(span=50, adjust=False).mean().values
        ema200 = pd.Series(close_).ewm(span=200, adjust=False).mean().values

        atr_s = pd.Series(atr_)
        atr_ma = atr_s.rolling(50).mean().values
        atr_std = atr_s.rolling(50).std().values

        for t in trades:
            idx = t["entry_idx"]
            if idx >= len(close_) or atr_[idx] <= 0 or idx < 50:
                continue

            # Trending: price clearly above/below EMA50 and EMA50 > EMA200 (or vice versa)
            above_50 = close_[idx] > ema50[idx]
            ema_bullish = ema50[idx] > ema200[idx]
            price_vs_ema = abs(close_[idx] - ema50[idx]) / (atr_[idx] * pip) if atr_[idx] * pip > 0 else 0

            if price_vs_ema > 0.5 and above_50 == ema_bullish:
                regime_trades["trending"].append(t)
            else:
                regime_trades["ranging"].append(t)

            # Volatility expansion/contraction
            if not np.isnan(atr_ma[idx]) and atr_std[idx] > 0:
                if atr_[idx] > atr_ma[idx] + atr_std[idx]:
                    regime_trades["expanding"].append(t)
                elif atr_[idx] < atr_ma[idx] - atr_std[idx]:
                    regime_trades["contracting"].append(t)

    result = {}
    for regime, trades in regime_trades.items():
        result[regime] = sim_metrics(trades, regime)

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-H: HOLDING PERIOD / EXIT INDEPENDENCE
# ═══════════════════════════════════════════════════════════════════════

def s1h_forward_returns(sigs: dict[str, pd.DataFrame]) -> dict:
    all_forward = {h: [] for h in [1, 2, 3, 6, 12, 24, 42]}
    all_mfe = []
    all_mae = []
    all_mfe_r = []
    all_mae_r = []

    for p, s in sigs.items():
        pip = get_pip_size(p)
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        trades = simulate_detail(s, p, cost_pips=spread)

        close_ = s["close"].values
        high_ = s["high"].values
        low_ = s["low"].values
        atr_ = s["atr"].values

        for t in trades:
            idx = t["entry_idx"]
            risk = t["risk_pips"]
            d = t["direction"]

            hi_path = high_[idx:]
            lo_path = low_[idx:]
            cl_path = close_[idx:]

            if d == 1:
                mfe = float((hi_path.max() - t["entry_price"]) / pip) if len(hi_path) > 0 else 0
                mae = float((t["entry_price"] - lo_path.min()) / pip) if len(lo_path) > 0 else 0
            else:
                mfe = float((t["entry_price"] - lo_path.min()) / pip) if len(lo_path) > 0 else 0
                mae = float((hi_path.max() - t["entry_price"]) / pip) if len(hi_path) > 0 else 0

            all_mfe.append(mfe)
            all_mae.append(mae)
            if risk > 0:
                all_mfe_r.append(mfe / risk)
                all_mae_r.append(mae / risk)

            for h in [1, 2, 3, 6, 12, 24, 42]:
                if idx + h < len(close_):
                    fwd = cl_path[h] if h < len(cl_path) else cl_path[-1]
                    if d == 1:
                        fwd_pips = (fwd - t["entry_price"]) / pip
                    else:
                        fwd_pips = (t["entry_price"] - fwd) / pip
                    all_forward[h].append(fwd_pips)

    result = {
        "mfe_pips": round(float(np.mean(all_mfe)), 2) if all_mfe else 0,
        "mae_pips": round(float(np.mean(all_mae)), 2) if all_mae else 0,
        "mfe_r": round(float(np.mean(all_mfe_r)), 4) if all_mfe_r else 0,
        "mae_r": round(float(np.mean(all_mae_r)), 4) if all_mae_r else 0,
        "mfe_median_pips": round(float(np.median(all_mfe)), 2) if all_mfe else 0,
        "mae_median_pips": round(float(np.median(all_mae)), 2) if all_mae else 0,
    }

    for h in [1, 2, 3, 6, 12, 24, 42]:
        fwd = all_forward[h]
        if fwd:
            result[f"fwd_{h}bar_pips"] = round(float(np.mean(fwd)), 4)
            result[f"fwd_{h}bar_positive_pct"] = round(float(np.mean(np.array(fwd) > 0)), 4)
            result[f"fwd_{h}bar_tstat"] = round(float(sp_stats.ttest_1samp(fwd, 0).statistic), 4) if len(fwd) > 1 else 0
            result[f"fwd_{h}bar_pval"] = round(float(sp_stats.ttest_1samp(fwd, 0).pvalue), 6) if len(fwd) > 1 else 1

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-I: EXIT CONTROL COMPARISON
# ═══════════════════════════════════════════════════════════════════════

def s1i_exit_controls(sigs: dict[str, pd.DataFrame]) -> dict:
    exit_modes = ["original", "fixed_1R", "fixed_2R", "fixed_3R", "time_only", "atr_trail_only"]
    results = {}

    for mode in exit_modes:
        all_trades = []
        for p, s in sigs.items():
            spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
            trades = simulate_detail(s, p, cost_pips=spread, exit_mode=mode)
            all_trades.extend(trades)
        results[mode] = sim_metrics(all_trades, mode)

    return results


# ═══════════════════════════════════════════════════════════════════════
# S1-J: WALK-FORWARD / TEMPORAL GENERALIZATION
# ═══════════════════════════════════════════════════════════════════════

def s1j_walk_forward(pair_4h: dict[str, pd.DataFrame],
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

    return results


# ═══════════════════════════════════════════════════════════════════════
# S1-K: PAIR-REMOVAL ROBUSTNESS
# ═══════════════════════════════════════════════════════════════════════

def s1k_pair_removal(sigs: dict[str, pd.DataFrame]) -> dict:
    all_trades = {}
    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        all_trades[p] = simulate_detail(s, p, cost_pips=spread)

    flat = [t for trades in all_trades.values() for t in trades]
    agg = sim_metrics(flat, "all_pairs")

    pair_pnl = {}
    for p, trades in all_trades.items():
        if trades:
            pair_pnl[p] = np.mean([t["pnl_pips"] for t in trades])
        else:
            pair_pnl[p] = 0

    sorted_pairs = sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)

    results = {"all_pairs": agg}

    for n in [1, 2, 3]:
        top_n = [p for p, _ in sorted_pairs[:n]]
        filtered = [t for t in flat if t["pair"] not in top_n]
        results[f"remove_top_{n}"] = sim_metrics(filtered, f"remove_top_{n}")

    for n in [1, 2]:
        bot_n = [p for p, _ in sorted_pairs[-n:]]
        filtered = [t for t in flat if t["pair"] not in bot_n]
        results[f"remove_bottom_{n}"] = sim_metrics(filtered, f"remove_bottom_{n}")

    results["pair_ranking"] = [(p, round(v, 4)) for p, v in sorted_pairs]

    return results


# ═══════════════════════════════════════════════════════════════════════
# S1-L: BOOTSTRAP CONFIDENCE
# ═══════════════════════════════════════════════════════════════════════

def s1l_bootstrap(sigs: dict[str, pd.DataFrame]) -> dict:
    all_trades = []
    for p, s in sigs.items():
        spread = SPREAD_PIPS.get(p, 0.5) + SLIPPAGE_PIPS
        all_trades.extend(simulate_detail(s, p, cost_pips=spread))

    pnls = np.array([t["pnl_pips"] for t in all_trades])
    rs = np.array([t["r"] for t in all_trades])

    if len(pnls) == 0:
        return {}

    rng = np.random.RandomState(RNG_SEED)

    boot_means = np.empty(N_BOOT)
    boot_medians = np.empty(N_BOOT)
    boot_wr = np.empty(N_BOOT)
    boot_pf = np.empty(N_BOOT)

    for i in range(N_BOOT):
        idx = rng.choice(len(pnls), size=len(pnls), replace=True)
        s = pnls[idx]
        r = rs[idx]
        boot_means[i] = np.mean(s)
        boot_medians[i] = np.median(s)
        boot_wr[i] = np.mean(s > 0)
        gp = np.sum(s[s > 0]) if np.sum(s > 0) > 0 else 0
        gl = np.abs(np.sum(s[s <= 0])) if np.sum(s <= 0) > 0 else 1e-10
        boot_pf[i] = gp / gl

    result = {
        "n_trades": len(pnls),
        "mean_return": {
            "point": round(float(np.mean(pnls)), 4),
            "ci_95_lo": round(float(np.percentile(boot_means, 2.5)), 4),
            "ci_95_hi": round(float(np.percentile(boot_means, 97.5)), 4),
        },
        "median_return": {
            "point": round(float(np.median(pnls)), 4),
            "ci_95_lo": round(float(np.percentile(boot_medians, 2.5)), 4),
            "ci_95_hi": round(float(np.percentile(boot_medians, 97.5)), 4),
        },
        "win_rate": {
            "point": round(float(np.mean(pnls > 0)), 4),
            "ci_95_lo": round(float(np.percentile(boot_wr, 2.5)), 4),
            "ci_95_hi": round(float(np.percentile(boot_wr, 97.5)), 4),
        },
        "profit_factor": {
            "point": round(float(boot_pf.mean()), 4),
            "ci_95_lo": round(float(np.percentile(boot_pf, 2.5)), 4),
            "ci_95_hi": round(float(np.percentile(boot_pf, 97.5)), 4),
        },
        "prob_mean_le_zero": round(float(np.mean(boot_means <= 0)), 6),
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# S1-M: MULTIPLE-TESTING / DATA-MINING AUDIT
# ═══════════════════════════════════════════════════════════════════════

def s1m_data_mining_audit() -> dict:
    frozen_params = {
        "lookback": {"value": LOOKBACK, "frozen_before_s0": False,
                     "note": "From original archived strategy, but may have been tuned historically"},
        "atr_sl_mult": {"value": ATR_SL_MULT, "frozen_before_s0": False,
                        "note": "From original archived strategy"},
        "rrr": {"value": RRR, "frozen_before_s0": False,
                "note": "From TECHNICAL_REPORT.md (RRR=3.5), may reflect prior optimization"},
        "breakeven_ratio": {"value": BREAKEVEN_RATIO, "frozen_before_s0": False,
                            "note": "From original code, but 0.8R is a specific choice"},
        "max_hold_days": {"value": MAX_HOLD_DAYS, "frozen_before_s0": False,
                          "note": "From original strategy"},
        "swing_lookback": {"value": LOOKBACK, "frozen_before_s0": False,
                           "note": "Same as lookback"},
        "universe": {"value": "20 FX pairs", "frozen_before_s0": True,
                     "note": "All available pairs from data directory"},
        "timeframe": {"value": "4h", "frozen_before_s0": True,
                      "note": "From original strategy specification"},
        "trailing_stop": {"value": "swing-based", "frozen_before_s0": False,
                          "note": "Specific trailing implementation"},
        "signal_definition": {"value": "confirmed swing break", "frozen_before_s0": True,
                              "note": "Standard breakout definition"},
    }

    degrees_of_freedom = sum(1 for v in frozen_params.values() if not v["frozen_before_s0"])

    total_tests_in_s0 = 1 + 1 + 3 + 9 + 11 + 1  # orig + costs + controls + param + yby + perm

    result = {
        "frozen_parameters": frozen_params,
        "total_tunable_parameters": degrees_of_freedom,
        "total_tests_run_in_s0": total_tests_in_s0,
        "assessment": (
            f"S0 ran {total_tests_in_s0} tests with {degrees_of_freedom} tunable parameters. "
            "The key frozen parameters (lookback=5, ATR mult=2.0, RRR=3.5, breakeven=0.8R) "
            "were inherited from the archived strategy and not optimized in S0. "
            "However, these parameters may represent prior selection by the original developer. "
            "The parameter perturbation test (9 variants) all showed positive edge, "
            "reducing concern about specific parameter sensitivity."
        ),
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase S1: Archived Breakout Structural Interrogation")
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

    # ── S1-A: Pair-level ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-A: Pair-Level Generalization")
    print("=" * 70)
    all_results["S1A"] = s1a_pair_level(sigs)
    agg = all_results["S1A"]["aggregate"]
    print(f"  Aggregate: N={agg['n']}, WR={agg['win_rate']:.1%}, "
          f"AvgPnL={agg['avg_pnl_pips']:.2f}pip, PF={agg['profit_factor']:.2f}")
    print(f"  Profitable pairs: {all_results['S1A']['profitable_pairs']}/{all_results['S1A']['total_pairs']}")
    print("  Pair ranking:")
    for p, v in all_results["S1A"]["sorted_by_pnl"][:5]:
        print(f"    {p}: {v:+.2f} pip/trade")
    print("  ...")
    for p, v in all_results["S1A"]["sorted_by_pnl"][-3:]:
        print(f"    {p}: {v:+.2f} pip/trade")
    print("  Removal analysis:")
    for k, v in all_results["S1A"]["removal_analysis"].items():
        print(f"    {k}: N={v['n']}, AvgPnL={v.get('avg_pnl_pips', 0):.2f}pip, PF={v.get('profit_factor', 0):.2f}")

    # ── S1-B: Directional bias ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-B: Directional Bias Control")
    print("=" * 70)
    all_results["S1B"] = s1b_directional_bias(sigs)
    b = all_results["S1B"]
    print(f"  Breakout: N={b['breakout']['n']}, WR={b['breakout']['win_rate']:.1%}, "
          f"AvgPnL={b['breakout']['avg_pnl_pips']:.2f}pip")
    print(f"  Random:   N={b['random']['n']}, WR={b['random']['win_rate']:.1%}, "
          f"AvgPnL={b['random']['avg_pnl_pips']:.2f}pip")
    print(f"  Incremental vs random: {b['incremental_vs_random']:+.2f} pip")
    print(f"  Incremental vs random BUYs: {b['incremental_vs_random_buy']:+.2f} pip")
    print(f"  Incremental vs random SELLs: {b['incremental_vs_random_sell']:+.2f} pip")
    print(f"  Breakout BUYs:  N={b['breakout_buys']['n']}, WR={b['breakout_buys']['win_rate']:.1%}, "
          f"AvgPnL={b['breakout_buys']['avg_pnl_pips']:.2f}pip")
    print(f"  Breakout SELLs: N={b['breakout_sells']['n']}, WR={b['breakout_sells']['win_rate']:.1%}, "
          f"AvgPnL={b['breakout_sells']['avg_pnl_pips']:.2f}pip")

    # ── S1-C: Entry distance ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-C: Entry-Threshold / Distance Test")
    print("=" * 70)
    all_results["S1C"] = s1c_entry_distance(sigs)
    for label, m in all_results["S1C"].items():
        print(f"  {label}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── S1-D: False break / retest ────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-D: Breakout Path Classification")
    print("=" * 70)
    all_results["S1D"] = s1d_false_break(sigs)
    for cat, m in all_results["S1D"].items():
        if isinstance(m, dict) and "n" in m:
            print(f"  {cat}: N={m['n']} ({m.get('pct_of_total', 0)}%), "
                  f"WR={m['win_rate']:.1%}, AvgPnL={m['avg_pnl_pips']:.2f}pip")

    # ── S1-E: Session ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-E: Time-of-Day / Session Dependence")
    print("=" * 70)
    all_results["S1E"] = s1e_session(sigs)
    for session, m in all_results["S1E"].items():
        print(f"  {session}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── S1-F: Volatility regime ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-F: Volatility Regime")
    print("=" * 70)
    all_results["S1F"] = s1f_volatility_regime(sigs)
    for regime, m in all_results["S1F"].items():
        print(f"  {regime}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── S1-G: Trend regime ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-G: Trend / Range Regime")
    print("=" * 70)
    all_results["S1G"] = s1g_trend_regime(sigs)
    for regime, m in all_results["S1G"].items():
        if m.get("n", 0) > 0:
            print(f"  {regime}: N={m['n']}, WR={m['win_rate']:.1%}, "
                  f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")
        else:
            print(f"  {regime}: N=0")

    # ── S1-H: Forward returns ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-H: Holding Period / Exit Independence")
    print("=" * 70)
    all_results["S1H"] = s1h_forward_returns(sigs)
    h = all_results["S1H"]
    print(f"  MFE: {h['mfe_pips']:.1f} pip (median {h['mfe_median_pips']:.1f}), "
          f"MAE: {h['mae_pips']:.1f} pip (median {h['mae_median_pips']:.1f})")
    print(f"  MFE in R: {h['mfe_r']:.2f}, MAE in R: {h['mae_r']:.2f}")
    for bar_h in [1, 2, 3, 6, 12, 24, 42]:
        k_mean = f"fwd_{bar_h}bar_pips"
        k_pos = f"fwd_{bar_h}bar_positive_pct"
        k_pval = f"fwd_{bar_h}bar_pval"
        if k_mean in h:
            print(f"  Fwd {bar_h:2d} bars: {h[k_mean]:+.2f} pip, "
                  f"positive={h[k_pos]:.1%}, p={h[k_pval]:.4f}")

    # ── S1-I: Exit controls ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-I: Exit Control Comparison")
    print("=" * 70)
    all_results["S1I"] = s1i_exit_controls(sigs)
    for mode, m in all_results["S1I"].items():
        print(f"  {mode:15s}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── S1-J: Walk-forward ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-J: Walk-Forward / Temporal Generalization")
    print("=" * 70)
    all_results["S1J"] = s1j_walk_forward(pair_4h, sigs)
    for period, m in all_results["S1J"].items():
        print(f"  {period:25s}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── S1-K: Pair removal ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-K: Pair-Removal Robustness")
    print("=" * 70)
    all_results["S1K"] = s1k_pair_removal(sigs)
    for k, m in all_results["S1K"].items():
        if k != "pair_ranking" and isinstance(m, dict) and "n" in m:
            print(f"  {k:25s}: N={m['n']}, AvgPnL={m.get('avg_pnl_pips', 0):.2f}pip, "
                  f"PF={m.get('profit_factor', 0):.2f}")
    print("  Pair ranking:")
    for p, v in all_results["S1K"]["pair_ranking"]:
        print(f"    {p}: {v:+.2f}")

    # ── S1-L: Bootstrap ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-L: Bootstrap Confidence Intervals")
    print("=" * 70)
    all_results["S1L"] = s1l_bootstrap(sigs)
    boot = all_results["S1L"]
    print(f"  Trades: {boot.get('n_trades', 0)}")
    m = boot.get("mean_return", {})
    print(f"  Mean: {m.get('point', 0):.2f} pip [{m.get('ci_95_lo', 0):.2f}, {m.get('ci_95_hi', 0):.2f}]")
    m = boot.get("median_return", {})
    print(f"  Median: {m.get('point', 0):.2f} pip [{m.get('ci_95_lo', 0):.2f}, {m.get('ci_95_hi', 0):.2f}]")
    m = boot.get("win_rate", {})
    print(f"  Win rate: {m.get('point', 0):.1%} [{m.get('ci_95_lo', 0):.1%}, {m.get('ci_95_hi', 0):.1%}]")
    m = boot.get("profit_factor", {})
    print(f"  PF: {m.get('point', 0):.2f} [{m.get('ci_95_lo', 0):.2f}, {m.get('ci_95_hi', 0):.2f}]")
    print(f"  P(mean <= 0): {boot.get('prob_mean_le_zero', 0):.6f}")

    # ── S1-M: Data mining audit ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1-M: Multiple-Testing / Data-Mining Audit")
    print("=" * 70)
    all_results["S1M"] = s1m_data_mining_audit()
    print(f"  Tunable parameters: {all_results['S1M']['total_tunable_parameters']}")
    print(f"  Tests in S0: {all_results['S1M']['total_tests_run_in_s0']}")
    print(f"  Assessment: {all_results['S1M']['assessment']}")

    # ── CLASSIFICATION ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S1 CLASSIFICATION")
    print("=" * 70)

    j = all_results["S1J"]
    holdout = j.get("holdout_2024_2026", {})
    valid = j.get("valid_2022_2023", {})
    train = j.get("train_2016_2021", {})

    k = all_results["S1K"]
    remove_top1 = k.get("remove_top_1", {})

    i = all_results["S1I"]
    fixed_2r = i.get("fixed_2R", {})
    time_only = i.get("time_only", {})
    atr_trail = i.get("atr_trail_only", {})

    h = all_results["S1H"]
    fwd_6 = h.get("fwd_6bar_pips", 0)
    fwd_24 = h.get("fwd_24bar_pips", 0)

    b = all_results["S1B"]
    incr = b.get("incremental_vs_random", 0)

    boot_p = boot.get("prob_mean_le_zero", 1)

    checks = {
        "edge_positive_after_costs": all_results["S1A"]["aggregate"].get("avg_pnl_pips", 0) > 0,
        "beats_random": incr > 0,
        "holdout_positive": holdout.get("avg_pnl_pips", 0) > 0,
        "valid_positive": valid.get("avg_pnl_pips", 0) > 0,
        "edge_survives_top1_removal": remove_top1.get("avg_pnl_pips", 0) > 0,
        "forward_6bar_positive": fwd_6 > 0,
        "forward_24bar_positive": fwd_24 > 0,
        "exit_independent": (fixed_2r.get("avg_pnl_pips", 0) > 0 and
                             atr_trail.get("avg_pnl_pips", 0) > 0),
        "bootstrap_prob_positive": boot_p < 0.05,
        "majority_profitable_pairs": (all_results["S1A"]["profitable_pairs"] >
                                     all_results["S1A"]["total_pairs"] / 2),
    }

    print("  Checks:")
    for check, result in checks.items():
        print(f"    {check}: {'PASS' if result else 'FAIL'}")

    n_pass = sum(checks.values())
    n_total = len(checks)

    if n_pass >= 9:
        classification = "A. STRUCTURAL EDGE CONFIRMED"
    elif n_pass >= 7:
        classification = "B. STRUCTURAL EDGE PROBABLY REAL BUT NEEDS FURTHER VALIDATION"
    elif n_pass >= 5:
        classification = "C. EDGE EXISTS BUT IS HIGHLY CONDITIONAL"
    elif n_pass >= 3:
        classification = "D. EDGE ATTRIBUTABLE PRIMARILY TO EXIT/DRIFT/OTHER ARTIFACT"
    else:
        classification = "E. HYPOTHESIS KILLED"

    print(f"\n  Passed: {n_pass}/{n_total}")
    print(f"  Classification: {classification}")

    # ── Save ───────────────────────────────────────────────────────────
    all_results["classification"] = classification
    all_results["checks"] = checks
    all_results["runtime_seconds"] = round(time.time() - t0, 1)

    with open(out_dir / "S1_structural_interrogation.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f"S1 complete in {time.time() - t0:.1f}s")
    print(f"Classification: {classification}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
