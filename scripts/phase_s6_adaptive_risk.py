"""
Phase S6: Volatility Quality, Adaptive Risk & Challenge Optimization

S0-S5.5 are FROZEN. This script does not modify the core signal.
The objective is risk management investigation, not optimization.
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
from indicators.pip import pip_size as get_pip_size

DATA_DIR = Path("/root/data")
RNG_SEED = 42
np.random.seed(RNG_SEED)

# Frozen from S0
LOOKBACK = 5
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
RRR = 3.5
MAX_HOLD_DAYS = 7
BREAKEVEN_RATIO = 0.8

COST_SCENARIOS = {
    "zero": {"spread_mult": 0, "slippage_pips": 0, "commission_per_lot": 0},
    "base": {"spread_mult": 1.0, "slippage_pips": 0.1, "commission_per_lot": 3.5},
    "severe": {"spread_mult": 2.0, "slippage_pips": 0.4, "commission_per_lot": 7.0},
}

SPREAD_PIPS = {
    "EUR/USD": 0.2, "GBP/USD": 0.3, "USD/JPY": 0.2, "USD/CHF": 0.3,
    "USD/CAD": 0.3, "AUD/USD": 0.3, "NZD/USD": 0.3, "EUR/GBP": 0.3,
    "EUR/JPY": 0.3, "GBP/JPY": 0.3, "AUD/NZD": 0.5, "EUR/NZD": 0.5,
    "GBP/NZD": 0.5, "AUD/CAD": 0.4, "AUD/CHF": 0.4, "AUD/JPY": 0.3,
    "CAD/JPY": 0.3, "CHF/JPY": 0.4, "CAD/CHF": 0.5, "NZD/JPY": 0.4,
    "NZD/CAD": 0.5, "NZD/CHF": 0.5, "EUR/AUD": 0.4, "EUR/CAD": 0.4,
    "EUR/CHF": 0.3, "GBP/AUD": 0.5, "GBP/CAD": 0.5, "GBP/CHF": 0.4,
}


# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════

def load_and_resample():
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


# ═══════════════════════════════════════════════════════════════════════
# FROZEN SIGNAL ENGINE (from S3)
# ═══════════════════════════════════════════════════════════════════════

def compute_rolling_swing_levels(close, high, low, lookback):
    n = len(close)
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    for i in range(lookback, n - lookback):
        wh = high[i - lookback:i + lookback + 1]
        wl = low[i - lookback:i + lookback + 1]
        if high[i] == np.max(wh):
            swing_high[i] = high[i]
        if low[i] == np.min(wl):
            swing_low[i] = low[i]
    for i in range(1, n):
        if np.isnan(swing_high[i]):
            swing_high[i] = swing_high[i - 1]
        if np.isnan(swing_low[i]):
            swing_low[i] = swing_low[i - 1]
    return swing_high, swing_low


def compute_atr_independent(high, low, close, period):
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n > period:
        atr[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def generate_signal_mechanism(df, lookback=LOOKBACK, atr_period=ATR_PERIOD):
    lookback = int(lookback)
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    open_ = df["open"].values
    swing_high, swing_low = compute_rolling_swing_levels(close, high, low, lookback)
    atr = compute_atr_independent(high, low, close, atr_period)
    n = len(close)
    signal = np.zeros(n, dtype=int)
    displacement_atr = np.zeros(n)
    warmup = lookback * 2 + atr_period + 1
    for i in range(warmup, n):
        if atr[i] <= 0:
            continue
        prev_sh = swing_high[i - 1]
        prev_sl = swing_low[i - 1]
        if np.isnan(prev_sh) or np.isnan(prev_sl):
            continue
        if close[i - 1] <= prev_sh < close[i]:
            signal[i] = 1
            displacement_atr[i] = (close[i] - prev_sh) / atr[i]
        elif close[i - 1] >= prev_sl > close[i]:
            signal[i] = -1
            displacement_atr[i] = (prev_sl - close[i]) / atr[i]
    return pd.DataFrame({
        "signal": signal, "displacement_atr": displacement_atr,
        "swing_high": swing_high, "swing_low": swing_low,
        "atr": atr, "open": open_, "high": high, "low": low, "close": close,
    }, index=df.index)


def simulate_with_risk_scaling(sig, pair, scenario, risk_mults, sl_mult=ATR_SL_MULT,
                                rrr=RRR, signal_delay_bars=0, lookback=LOOKBACK,
                                atr_period=ATR_PERIOD, max_hold_days=MAX_HOLD_DAYS,
                                breakeven_ratio=BREAKEVEN_RATIO):
    """
    Simulation with per-trade risk multipliers.
    risk_mults: array-like, same length as sig, values are risk multipliers (e.g. 0.5, 1.0).
    """
    pip = get_pip_size(pair)
    base_spread = SPREAD_PIPS.get(pair, 0.5)
    spread_pips = base_spread * scenario["spread_mult"]
    slip_pips = scenario["slippage_pips"]
    commission = scenario["commission_per_lot"]
    total_cost = ((spread_pips / 2) + slip_pips + commission / 10) * 2
    max_bars = max_hold_days * 6

    open_ = sig["open"].values
    high_ = sig["high"].values
    low_ = sig["low"].values
    close_ = sig["close"].values
    atr_ = sig["atr"].values
    sig_ = sig["signal"].values
    sl_ = sig["swing_low"].values
    sh_ = sig["swing_high"].values
    rm_ = risk_mults if risk_mults is not None else np.ones(len(sig))

    trades = []
    in_trade = False
    direction = 0
    entry_price = 0.0
    sl_price = 0.0
    entry_idx = 0
    risk_pips = 0.0
    pending_signal = 0
    pending_idx = 0

    for i in range(lookback * 2 + atr_period + 2, len(sig)):
        if pending_signal != 0 and i >= pending_idx + signal_delay_bars:
            if not in_trade and atr_[pending_idx] > 0:
                entry_price = open_[i]
                stop_dist = sl_mult * atr_[pending_idx] * rm_[pending_idx]
                if stop_dist / pip < 1.0:
                    pending_signal = 0
                    continue
                sl_price = entry_price - stop_dist if pending_signal == 1 else entry_price + stop_dist
                direction = pending_signal
                entry_idx = i
                risk_pips = stop_dist / pip
                in_trade = True
                pending_signal = 0

        if sig_[i] != 0 and not in_trade and atr_[i] > 0 and pending_signal == 0:
            pending_signal = sig_[i]
            pending_idx = i

        sig_val = sig_[i]

        if in_trade:
            bars_held = i - entry_idx
            risk = risk_pips

            if direction == 1:
                exit_price = None
                exit_reason = ""
                if low_[i] <= sl_price and risk > 0:
                    exit_price = sl_price
                    exit_reason = "SL"
                elif high_[i] >= entry_price + risk * rrr * pip and risk > 0:
                    exit_price = entry_price + risk * rrr * pip
                    exit_reason = "TP"
                elif bars_held >= max_bars and risk > 0:
                    exit_price = close_[i]
                    exit_reason = "MH"
                else:
                    new_sl = sl_[i - 1] if not np.isnan(sl_[i - 1]) else sl_price
                    if new_sl > sl_price:
                        sl_price = new_sl
                    if sl_price < entry_price and risk > 0:
                        if (close_[i] - entry_price) / pip >= breakeven_ratio * risk:
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
                        "risk_mult": rm_[entry_idx],
                        "mfe_pips": float((hi_path.max() - entry_price) / pip),
                        "mae_pips": float((entry_price - lo_path.min()) / pip),
                    })
                    in_trade = False
                    continue
            else:
                exit_price = None
                exit_reason = ""
                if high_[i] >= sl_price and risk > 0:
                    exit_price = sl_price
                    exit_reason = "SL"
                elif low_[i] <= entry_price - risk * rrr * pip and risk > 0:
                    exit_price = entry_price - risk * rrr * pip
                    exit_reason = "TP"
                elif bars_held >= max_bars and risk > 0:
                    exit_price = close_[i]
                    exit_reason = "MH"
                else:
                    new_sl = sh_[i - 1] if not np.isnan(sh_[i - 1]) else sl_price
                    if new_sl < sl_price:
                        sl_price = new_sl
                    if sl_price > entry_price and risk > 0:
                        if (entry_price - close_[i]) / pip >= breakeven_ratio * risk:
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
                        "risk_mult": rm_[entry_idx],
                        "mfe_pips": float((entry_price - lo_path.min()) / pip),
                        "mae_pips": float((hi_path.max() - entry_price) / pip),
                    })
                    in_trade = False
                    continue

        if not in_trade and sig_val != 0 and not np.isnan(atr_[i]) and atr_[i] > 0:
            entry_price = open_[i]
            stop_dist = sl_mult * atr_[i] * rm_[i]
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
            "risk_pips": risk_pips, "risk_mult": rm_[entry_idx],
            "mfe_pips": 0, "mae_pips": 0,
        })

    return trades


def sim_metrics(trades, label=""):
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
    max_dd = float(np.min(cum - np.maximum.accumulate(cum)))
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


def sim_metrics_extended(trades, label=""):
    """Extended metrics including R-based DD, streaks, monthly stats."""
    base = sim_metrics(trades, label)
    if not trades:
        base["max_dd_r"] = 0
        base["max_loss_streak"] = 0
        base["losing_months"] = 0
        base["worst_month_pnl"] = 0
        base["max_dd_duration_bars"] = 0
        return base

    rs = np.array([t["r"] for t in trades])
    avg_risk = np.mean([t["risk_pips"] for t in trades])

    # Max DD in R
    cum_r = np.cumsum(rs)
    max_dd_r = float(np.min(cum_r - np.maximum.accumulate(cum_r)))
    base["max_dd_r"] = round(abs(max_dd_r), 2)

    # Max loss streak
    max_streak = 0
    current = 0
    for r in rs:
        if r <= 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    base["max_loss_streak"] = max_streak

    # Monthly stats
    df = pd.DataFrame(trades)
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["month"] = df["exit_time"].dt.to_period("M")
    monthly = df.groupby("month")["pnl_pips"].sum()
    base["losing_months"] = int((monthly < 0).sum())
    base["worst_month_pnl"] = round(float(monthly.min()), 2)
    base["avg_monthly_pnl"] = round(float(monthly.mean()), 2)
    base["median_monthly_pnl"] = round(float(monthly.median()), 2)

    # Max DD duration
    cum_pnl = np.cumsum([t["pnl_pips"] for t in trades])
    peak = np.maximum.accumulate(cum_pnl)
    dd = cum_pnl - peak
    in_dd = dd < -0.01
    max_dur = 0
    current_dur = 0
    for v in in_dd:
        if v:
            current_dur += 1
            max_dur = max(max_dur, current_dur)
        else:
            current_dur = 0
    base["max_dd_duration_bars"] = max_dur

    return base


# ═══════════════════════════════════════════════════════════════════════
# VOLATILITY QUALITY COMPUTATION
# ═══════════════════════════════════════════════════════════════════════

def compute_vol_quality(df, atr_period=ATR_PERIOD, baseline_period=20):
    """
    Compute volatility quality ratio: current ATR / rolling baseline ATR.
    Uses expanding window for causality.
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    atr = compute_atr_independent(high, low, close, atr_period)

    n = len(atr)
    vol_quality = np.full(n, np.nan)

    for i in range(baseline_period + atr_period, n):
        baseline = np.mean(atr[i - baseline_period:i + 1])
        if baseline > 0:
            vol_quality[i] = atr[i] / baseline

    return vol_quality


def compute_vol_transition_score(df, atr_period=ATR_PERIOD, short_period=10, long_period=50):
    """
    Compute regime transition score: divergence between short and long ATR.
    High score = transitioning.
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    atr = compute_atr_independent(high, low, close, atr_period)

    n = len(atr)
    transition_score = np.full(n, np.nan)

    for i in range(long_period + atr_period, n):
        short_avg = np.mean(atr[i - short_period:i + 1])
        long_avg = np.mean(atr[i - long_period:i + 1])
        if long_avg > 0:
            transition_score[i] = abs(short_avg - long_avg) / long_avg

    return transition_score


# ═══════════════════════════════════════════════════════════════════════
# S6-A: BASELINE REPRODUCTION
# ═══════════════════════════════════════════════════════════════════════

def s6a_baseline(pair_4h):
    all_trades = []
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        trades = simulate_with_risk_scaling(sig, p, COST_SCENARIOS["base"], None)
        all_trades.extend(trades)
    return sim_metrics_extended(all_trades, "baseline"), all_trades


# ═══════════════════════════════════════════════════════════════════════
# S6-B/C: VOLATILITY QUALITY RISK SCALING
# ═══════════════════════════════════════════════════════════════════════

def s6b_vol_quality_risk_scaling(pair_4h, baseline_trades):
    """
    Test volatility quality as a risk input.
    3 predetermined variants, each tested with 2 risk levels.
    """
    baseline_metrics = sim_metrics_extended(baseline_trades, "baseline")

    variants = {
        "vq_20": {"baseline_period": 20, "label": "ATR/20-ATR"},
        "vq_50": {"baseline_period": 50, "label": "ATR/50-ATR"},
        "vq_100": {"baseline_period": 100, "label": "ATR/100-ATR"},
    }

    risk_schemes = {
        "low_quality_half": {"threshold_low": 0.8, "low_mult": 0.5, "high_mult": 1.0},
        "low_quality_07": {"threshold_low": 0.8, "low_mult": 0.7, "high_mult": 1.0},
    }

    results = {}

    for vname, vconfig in variants.items():
        results[vname] = {}
        for rname, rconfig in risk_schemes.items():
            all_trades = []
            for p, df in pair_4h.items():
                sig = generate_signal_mechanism(df)
                vq = compute_vol_quality(df, baseline_period=vconfig["baseline_period"])
                risk_mults = np.ones(len(sig))
                for i in range(len(sig)):
                    if not np.isnan(vq[i]):
                        if vq[i] < rconfig["threshold_low"]:
                            risk_mults[i] = rconfig["low_mult"]
                        else:
                            risk_mults[i] = rconfig["high_mult"]
                trades = simulate_with_risk_scaling(sig, p, COST_SCENARIOS["base"], risk_mults)
                all_trades.extend(trades)

            m = sim_metrics_extended(all_trades, f"{vname}_{rname}")
            m["retention_pct"] = round(
                m["avg_pnl_pips"] / max(baseline_metrics["avg_pnl_pips"], 1e-10) * 100, 1)
            m["dd_reduction_pct"] = round(
                (1 - abs(m["max_dd_pips"]) / max(abs(baseline_metrics["max_dd_pips"]), 1e-10)) * 100, 1)
            results[vname][rname] = m

    return results, baseline_metrics


# ═══════════════════════════════════════════════════════════════════════
# S6-D: REGIME TRANSITION CONTROL
# ═══════════════════════════════════════════════════════════════════════

def s6d_regime_transition_control(pair_4h, baseline_trades):
    baseline_metrics = sim_metrics_extended(baseline_trades, "baseline")

    variants = {
        "div_03": {"short_period": 10, "long_period": 50, "threshold": 0.3},
        "div_05": {"short_period": 10, "long_period": 50, "threshold": 0.5},
        "div_07": {"short_period": 10, "long_period": 50, "threshold": 0.7},
    }

    risk_mult = 0.5  # Reduce to 50% during transitions
    results = {}

    for vname, vconfig in variants.items():
        all_trades = []
        for p, df in pair_4h.items():
            sig = generate_signal_mechanism(df)
            ts = compute_vol_transition_score(df, short_period=vconfig["short_period"],
                                               long_period=vconfig["long_period"])
            risk_mults = np.ones(len(sig))
            for i in range(len(sig)):
                if not np.isnan(ts[i]) and ts[i] > vconfig["threshold"]:
                    risk_mults[i] = risk_mult
            trades = simulate_with_risk_scaling(sig, p, COST_SCENARIOS["base"], risk_mults)
            all_trades.extend(trades)

        m = sim_metrics_extended(all_trades, f"rt_{vname}")
        m["retention_pct"] = round(
            m["avg_pnl_pips"] / max(baseline_metrics["avg_pnl_pips"], 1e-10) * 100, 1)
        m["dd_reduction_pct"] = round(
            (1 - abs(m["max_dd_pips"]) / max(abs(baseline_metrics["max_dd_pips"]), 1e-10)) * 100, 1)
        results[vname] = m

    return results, baseline_metrics


# ═══════════════════════════════════════════════════════════════════════
# S6-E: CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════

def s6e_circuit_breaker(pair_4h, baseline_trades):
    baseline_metrics = sim_metrics_extended(baseline_trades, "baseline")

    # Sort all trades by time
    baseline_trades_sorted = sorted(baseline_trades, key=lambda t: t["exit_time"])

    def apply_circuit_breaker(trades_sorted, cb_type, cb_param):
        """Apply circuit breaker by modifying risk_mults in-place."""
        risk_mults = []
        consec_losses = 0
        in_trade = False
        entry_idx = 0

        for t in trades_sorted:
            if consec_losses >= cb_param and cb_type == "streak":
                risk_mults.append(0.5)
            elif cb_type == "dd":
                # Not implementable without equity curve in this simplified version
                risk_mults.append(1.0)
            else:
                risk_mults.append(1.0)

            if t["r"] <= 0:
                consec_losses += 1
            else:
                consec_losses = 0

        return risk_mults

    results = {}

    # CB1: After 10 consecutive losses → 50% risk
    all_trades = []
    cb1_risks = apply_circuit_breaker(baseline_trades_sorted, "streak", 10)
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        # We need to re-simulate with modified risk
        trades = simulate_with_risk_scaling(sig, p, COST_SCENARIOS["base"],
                                             np.ones(len(sig)))  # Will use per-pair
    # Actually, circuit breakers need to be applied at the portfolio level
    # Let me redo this properly

    # Re-run simulation portfolio-wide with circuit breaker logic
    def run_cb_simulation(pair_4h, cb_type, cb_param):
        all_trades = []
        for p, df in pair_4h.items():
            sig = generate_signal_mechanism(df)
            trades = simulate_with_risk_scaling(sig, p, COST_SCENARIOS["base"], None)
            all_trades.extend(trades)

        # Sort by time
        all_trades.sort(key=lambda t: t["exit_time"])

        # Apply CB
        consec_losses = 0
        for t in all_trades:
            if cb_type == "streak" and consec_losses >= cb_param:
                t["risk_mult"] = 0.5
                # Recalculate PnL with reduced risk
                t["pnl_pips"] = t["pnl_pips"] * 0.5  # Simplified: scale PnL by risk mult
                t["r"] = t["r"] * 0.5
            elif cb_type == "dd":
                pass  # DD-based CB requires running equity

            if t["r"] <= 0:
                consec_losses += 1
            else:
                consec_losses = 0

        return all_trades

    # CB1: streak 10
    cb1_trades = run_cb_simulation(pair_4h, "streak", 10)
    results["cb1_streak10"] = sim_metrics_extended(cb1_trades, "cb1_streak10")
    results["cb1_streak10"]["retention_pct"] = round(
        results["cb1_streak10"]["avg_pnl_pips"] / max(baseline_metrics["avg_pnl_pips"], 1e-10) * 100, 1)
    results["cb1_streak10"]["dd_reduction_pct"] = round(
        (1 - abs(results["cb1_streak10"]["max_dd_pips"]) / max(abs(baseline_metrics["max_dd_pips"]), 1e-10)) * 100, 1)

    # CB2: streak 15
    cb2_trades = run_cb_simulation(pair_4h, "streak", 15)
    results["cb2_streak15"] = sim_metrics_extended(cb2_trades, "cb2_streak15")
    results["cb2_streak15"]["retention_pct"] = round(
        results["cb2_streak15"]["avg_pnl_pips"] / max(baseline_metrics["avg_pnl_pips"], 1e-10) * 100, 1)
    results["cb2_streak15"]["dd_reduction_pct"] = round(
        (1 - abs(results["cb2_streak15"]["max_dd_pips"]) / max(abs(baseline_metrics["max_dd_pips"]), 1e-10)) * 100, 1)

    # CB3: streak 20
    cb3_trades = run_cb_simulation(pair_4h, "streak", 20)
    results["cb3_streak20"] = sim_metrics_extended(cb3_trades, "cb3_streak20")
    results["cb3_streak20"]["retention_pct"] = round(
        results["cb3_streak20"]["avg_pnl_pips"] / max(baseline_metrics["avg_pnl_pips"], 1e-10) * 100, 1)
    results["cb3_streak20"]["dd_reduction_pct"] = round(
        (1 - abs(results["cb3_streak20"]["max_dd_pips"]) / max(abs(baseline_metrics["max_dd_pips"]), 1e-10)) * 100, 1)

    return results, baseline_metrics


# ═══════════════════════════════════════════════════════════════════════
# S6-F: PROP-FIRM CHALLENGE SIMULATION
# ═══════════════════════════════════════════════════════════════════════

def s6f_challenge_simulation(baseline_trades):
    account = 2500
    target_pct = 0.10  # 10% target
    max_dd_pct = 0.10  # 10% max DD
    daily_dd_pct = 0.05  # 5% daily DD
    target = account * target_pct
    max_loss = account * max_dd_pct

    risk_levels = [0.0025, 0.003, 0.004, 0.005, 0.006, 0.0075, 0.01]

    # Monthly aggregation
    df = pd.DataFrame(baseline_trades)
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["month"] = df["exit_time"].dt.to_period("M")
    monthly = df.groupby("month").agg(
        total_pnl_pips=("pnl_pips", "sum"),
        n_trades=("pnl_pips", "count"),
        avg_risk_pips=("risk_pips", "mean"),
    ).reset_index()

    avg_risk_pips = df["risk_pips"].mean()

    results = {}
    for risk_pct in risk_levels:
        one_r = account * risk_pct
        # Convert pip PnL to dollar PnL: 1R = avg_risk_pips, so dollar_per_pip = one_r / avg_risk_pips
        dollar_per_pip = one_r / max(avg_risk_pips, 1)

        monthly_dollar = monthly["total_pnl_pips"] * dollar_per_pip
        cum_dollar = monthly_dollar.cumsum()
        peak = cum_dollar.cummax()
        dd_dollar = cum_dollar - peak

        # Simulate challenge
        equity = account
        reached_target = False
        violated_dd = False
        month_count = 0
        for i, row in monthly.iterrows():
            month_count += 1
            pnl_dollar = row["total_pnl_pips"] * dollar_per_pip
            equity += pnl_dollar
            if equity >= account + target:
                reached_target = True
                break
            if equity <= account - max_loss:
                violated_dd = True
                break

        # Monthly stats
        monthly_returns = monthly_dollar / account
        avg_monthly_return = float(monthly_returns.mean())
        median_monthly_return = float(monthly_returns.median())
        worst_month = float(monthly_dollar.min())
        max_dd_dollar = float(dd_dollar.min())
        max_dd_pct_actual = abs(max_dd_dollar) / account

        # Probability of exceeding DD in any month
        prob_exceed_dd = float((monthly_dollar < -max_loss).mean())

        results[f"risk_{risk_pct:.2%}"] = {
            "risk_pct": risk_pct,
            "one_r_dollar": round(one_r, 2),
            "avg_monthly_return_pct": round(avg_monthly_return * 100, 2),
            "median_monthly_return_pct": round(median_monthly_return * 100, 2),
            "worst_month_dollar": round(worst_month, 2),
            "max_dd_dollar": round(max_dd_dollar, 2),
            "max_dd_pct": round(max_dd_pct_actual * 100, 2),
            "prob_exceed_dd_monthly": round(prob_exceed_dd, 4),
            "reached_target": reached_target,
            "violated_dd": violated_dd,
            "months_to_resolution": month_count,
        }

    return results


# ═══════════════════════════════════════════════════════════════════════
# S6-G: SPEED VS SURVIVAL FRONTIER
# ═══════════════════════════════════════════════════════════════════════

def s6g_speed_survival(baseline_trades, challenge_results):
    """Compute speed vs survival frontier from challenge simulation."""
    frontier = []
    for key, cr in challenge_results.items():
        frontier.append({
            "risk_pct": cr["risk_pct"],
            "avg_monthly_return_pct": cr["avg_monthly_return_pct"],
            "max_dd_pct": cr["max_dd_pct"],
            "prob_exceed_dd": cr["prob_exceed_dd_monthly"],
            "reached_target": cr["reached_target"],
            "months_to_resolution": cr["months_to_resolution"],
            "survival_score": round(1 - cr["prob_exceed_dd_monthly"], 4),
            "speed_score": cr["avg_monthly_return_pct"],
        })
    return frontier


# ═══════════════════════════════════════════════════════════════════════
# S6-H: MONTE CARLO
# ═══════════════════════════════════════════════════════════════════════

def s6h_monte_carlo(baseline_trades, n_sims=10000, risk_levels=None):
    if risk_levels is None:
        risk_levels = [0.0025, 0.005, 0.01]

    account = 2500
    target = account * 0.10
    max_loss = account * 0.10

    rs = np.array([t["r"] for t in baseline_trades])
    avg_risk = np.mean([t["risk_pips"] for t in baseline_trades])

    # Monthly trade count
    df = pd.DataFrame(baseline_trades)
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["month"] = df["exit_time"].dt.to_period("M")
    trades_per_month = int(df.groupby("month").size().mean())

    results = {}
    for risk_pct in risk_levels:
        one_r = account * risk_pct
        dollar_per_r = one_r

        # Block bootstrap: resample months
        monthly_r = df.groupby("month")["r"].sum().values

        sim_max_dds = []
        sim_returns = []
        sim_reached_target = 0
        sim_violated_dd = 0

        for _ in range(n_sims):
            # Bootstrap monthly returns
            sampled_months = np.random.choice(monthly_r, size=len(monthly_r), replace=True)
            cum_return = np.cumsum(sampled_months * dollar_per_r)
            peak = np.maximum.accumulate(cum_return)
            dd = cum_return - peak

            max_dd = float(dd.min())
            final_return = float(cum_return[-1])

            sim_max_dds.append(abs(max_dd))
            sim_returns.append(final_return)

            # Challenge simulation
            equity = account
            reached = False
            violated = False
            for monthly_r_sample in sampled_months:
                pnl = monthly_r_sample * dollar_per_r
                equity += pnl
                if equity >= account + target:
                    reached = True
                    break
                if equity <= account - max_loss:
                    violated = True
                    break

            if reached:
                sim_reached_target += 1
            if violated:
                sim_violated_dd += 1

        sim_max_dds = np.array(sim_max_dds)
        sim_returns = np.array(sim_returns)

        results[f"risk_{risk_pct:.2%}"] = {
            "risk_pct": risk_pct,
            "median_max_dd_dollar": round(float(np.median(sim_max_dds)), 2),
            "p95_max_dd_dollar": round(float(np.percentile(sim_max_dds, 95)), 2),
            "p99_max_dd_dollar": round(float(np.percentile(sim_max_dds, 99)), 2),
            "median_return_dollar": round(float(np.median(sim_returns)), 2),
            "p5_return_dollar": round(float(np.percentile(sim_returns, 5)), 2),
            "prob_gt_5pct_dd": round(float(np.mean(sim_max_dds > account * 0.05)), 4),
            "prob_gt_8pct_dd": round(float(np.mean(sim_max_dds > account * 0.08)), 4),
            "prob_gt_10pct_dd": round(float(np.mean(sim_max_dds > account * 0.10)), 4),
            "prob_reached_target": round(sim_reached_target / n_sims, 4),
            "prob_violated_dd": round(sim_violated_dd / n_sims, 4),
            "n_sims": n_sims,
        }

    return results


# ═══════════════════════════════════════════════════════════════════════
# S6-I: COMPLEMENTARY STRATEGY CORRELATION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def s6i_correlation_analysis(pair_4h):
    """Analyze return series properties to determine complementary strategy requirements."""
    # Collect monthly returns per pair
    pair_monthly = {}
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        trades = simulate_with_risk_scaling(sig, p, COST_SCENARIOS["base"], None)
        if not trades:
            continue
        tdf = pd.DataFrame(trades)
        tdf["exit_time"] = pd.to_datetime(tdf["exit_time"])
        tdf["month"] = tdf["exit_time"].dt.to_period("M")
        monthly = tdf.groupby("month")["pnl_pips"].sum()
        pair_monthly[p] = monthly

    # Cross-pair correlation
    if len(pair_monthly) > 1:
        corr_df = pd.DataFrame(pair_monthly)
        corr_matrix = corr_df.corr()
        avg_corr = float(corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean())
    else:
        avg_corr = 0

    # Aggregate monthly returns
    all_monthly = pd.DataFrame(pair_monthly).sum(axis=1)
    autocorr_1 = float(all_monthly.autocorr(1)) if len(all_monthly) > 1 else 0
    autocorr_3 = float(all_monthly.autocorr(3)) if len(all_monthly) > 3 else 0

    # Volatility of monthly returns
    monthly_std = float(all_monthly.std())
    monthly_mean = float(all_monthly.mean())
    sharpe_monthly = monthly_mean / max(monthly_std, 1e-10)

    return {
        "avg_cross_pair_correlation": round(avg_corr, 4),
        "monthly_autocorr_lag1": round(autocorr_1, 4),
        "monthly_autocorr_lag3": round(autocorr_3, 4),
        "monthly_return_std": round(monthly_std, 2),
        "monthly_return_mean": round(monthly_mean, 2),
        "monthly_sharpe": round(sharpe_monthly, 4),
        "n_pairs": len(pair_monthly),
        "complementary_requirements": {
            "different_mechanism": "mean reversion or stat arb preferred",
            "different_failure_mode": "should not fail during vol transitions",
            "low_correlation": f"current cross-pair avg corr = {avg_corr:.2f}",
            "positive_expectancy": "required after costs",
            "different_regime_preference": "ideally profits during low-vol / ranging",
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase S6: Volatility Quality, Adaptive Risk & Challenge Optimization")
    print("=" * 70)

    out_dir = Path("/root/nestquant/research_data/simple_strategies")

    print("\n[0] Loading data...")
    pair_4h = load_and_resample()
    print(f"  {len(pair_4h)} pairs loaded")

    all_results = {}

    # S6-A: Baseline
    print("\n" + "=" * 70)
    print("S6-A: Baseline Reproduction")
    print("=" * 70)
    baseline_metrics, baseline_trades = s6a_baseline(pair_4h)
    all_results["S6A"] = baseline_metrics
    print(f"  Trades: {baseline_metrics['n']}")
    print(f"  Win rate: {baseline_metrics['win_rate']:.1%}")
    print(f"  Avg PnL: {baseline_metrics['avg_pnl_pips']:.2f} pip")
    print(f"  PF: {baseline_metrics['profit_factor']:.2f}")
    print(f"  Avg R: {baseline_metrics['avg_r']:.4f}")
    print(f"  Max DD (pips): {baseline_metrics['max_dd_pips']:.2f}")
    print(f"  Max DD (R): {baseline_metrics['max_dd_r']:.2f}")
    print(f"  Max loss streak: {baseline_metrics['max_loss_streak']}")
    print(f"  Losing months: {baseline_metrics['losing_months']}")
    print(f"  Worst month: {baseline_metrics['worst_month_pnl']:.2f} pip")
    print(f"  Avg monthly: {baseline_metrics['avg_monthly_pnl']:.2f} pip")

    # S6-B: Volatility quality risk scaling
    print("\n" + "=" * 70)
    print("S6-B/C: Volatility Quality Risk Scaling")
    print("=" * 70)
    all_results["S6B"], base_for_b = s6b_vol_quality_risk_scaling(pair_4h, baseline_trades)
    for vname, variants in all_results["S6B"].items():
        for rname, m in variants.items():
            print(f"  {vname}/{rname}: N={m['n']}, AvgPnL={m['avg_pnl_pips']:.2f}, "
                  f"PF={m['profit_factor']:.2f}, MaxDD={m['max_dd_pips']:.2f}, "
                  f"Retention={m['retention_pct']:.0f}%, DDreduction={m['dd_reduction_pct']:.0f}%")

    # S6-D: Regime transition control
    print("\n" + "=" * 70)
    print("S6-D: Regime Transition Control")
    print("=" * 70)
    all_results["S6D"], base_for_d = s6d_regime_transition_control(pair_4h, baseline_trades)
    for vname, m in all_results["S6D"].items():
        print(f"  {vname}: N={m['n']}, AvgPnL={m['avg_pnl_pips']:.2f}, "
              f"PF={m['profit_factor']:.2f}, MaxDD={m['max_dd_pips']:.2f}, "
              f"Retention={m['retention_pct']:.0f}%, DDreduction={m['dd_reduction_pct']:.0f}%")

    # S6-E: Circuit breaker
    print("\n" + "=" * 70)
    print("S6-E: Circuit Breaker")
    print("=" * 70)
    all_results["S6E"], base_for_e = s6e_circuit_breaker(pair_4h, baseline_trades)
    for vname, m in all_results["S6E"].items():
        print(f"  {vname}: N={m['n']}, AvgPnL={m['avg_pnl_pips']:.2f}, "
              f"PF={m['profit_factor']:.2f}, MaxDD={m['max_dd_pips']:.2f}, "
              f"Retention={m['retention_pct']:.0f}%, DDreduction={m['dd_reduction_pct']:.0f}%")

    # S6-F: Challenge simulation
    print("\n" + "=" * 70)
    print("S6-F: Prop-Firm Challenge Simulation")
    print("=" * 70)
    all_results["S6F"] = s6f_challenge_simulation(baseline_trades)
    for key, cr in all_results["S6F"].items():
        print(f"  {key}: Monthly={cr['avg_monthly_return_pct']:.2f}%, "
              f"MaxDD={cr['max_dd_pct']:.2f}%, "
              f"P(DD)={cr['prob_exceed_dd_monthly']:.2%}, "
              f"Target={'YES' if cr['reached_target'] else 'NO'}, "
              f"Violate={'YES' if cr['violated_dd'] else 'NO'}")

    # S6-G: Speed vs survival
    print("\n" + "=" * 70)
    print("S6-G: Speed vs Survival Frontier")
    print("=" * 70)
    all_results["S6G"] = s6g_speed_survival(baseline_trades, all_results["S6F"])
    for f in all_results["S6G"]:
        print(f"  Risk={f['risk_pct']:.2%}: Return={f['avg_monthly_return_pct']:.2f}%, "
              f"DD={f['max_dd_pct']:.2f}%, Survival={f['survival_score']:.2%}, "
              f"Speed={f['speed_score']:.2f}")

    # S6-H: Monte Carlo
    print("\n" + "=" * 70)
    print("S6-H: Monte Carlo (10,000 simulations)")
    print("=" * 70)
    all_results["S6H"] = s6h_monte_carlo(baseline_trades, n_sims=10000)
    for key, mc in all_results["S6H"].items():
        print(f"  {key}: MedianDD=${mc['median_max_dd_dollar']:.0f}, "
              f"P95DD=${mc['p95_max_dd_dollar']:.0f}, "
              f"P99DD=${mc['p99_max_dd_dollar']:.0f}, "
              f"P(>10%DD)={mc['prob_gt_10pct_dd']:.2%}, "
              f"P(Target)={mc['prob_reached_target']:.2%}, "
              f"P(Violate)={mc['prob_violated_dd']:.2%}")

    # S6-I: Correlation analysis
    print("\n" + "=" * 70)
    print("S6-I: Complementary Strategy Requirements")
    print("=" * 70)
    all_results["S6I"] = s6i_correlation_analysis(pair_4h)
    ci = all_results["S6I"]
    print(f"  Avg cross-pair correlation: {ci['avg_cross_pair_correlation']}")
    print(f"  Monthly autocorr lag-1: {ci['monthly_autocorr_lag1']}")
    print(f"  Monthly autocorr lag-3: {ci['monthly_autocorr_lag3']}")
    print(f"  Monthly Sharpe: {ci['monthly_sharpe']}")
    print(f"  Complementary requirements: {json.dumps(ci['complementary_requirements'], indent=4)}")

    # Save
    all_results["runtime_seconds"] = round(time.time() - t0, 1)
    with open(out_dir / "S6_adaptive_risk_challenge.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"S6 complete in {time.time() - t0:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
