"""
Phase S4: Walk-Forward Validation + Parameter Sensitivity

S4-A: Walk-forward rolling out-of-sample windows
S4-B: Parameter neighborhood sensitivity (±20% on each parameter)
S4-C: Regime-conditioned holdout (trending vs ranging markets)
S4-D: Stress scenario testing (crisis periods)

All parameters frozen from S0 unless explicitly varied.
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
from indicators.pip import pip_size as get_pip_size

DATA_DIR = Path("/root/data")
RNG_SEED = 42

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
    "conservative": {"spread_mult": 1.5, "slippage_pips": 0.2, "commission_per_lot": 5.0},
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


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL + SIMULATION (copied from S3 for independence)
# ═══════════════════════════════════════════════════════════════════════

def compute_rolling_swing_levels(close, high, low, lookback):
    n = len(close)
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    for i in range(lookback, n - lookback):
        window_high = high[i - lookback:i + lookback + 1]
        window_low = low[i - lookback:i + lookback + 1]
        if high[i] == np.max(window_high):
            swing_high[i] = high[i]
        if low[i] == np.min(window_low):
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


def simulate_realistic(sig, pair, scenario, sl_mult=ATR_SL_MULT, rrr=RRR,
                       signal_delay_bars=0, lookback=LOOKBACK, atr_period=ATR_PERIOD,
                       max_hold_days=MAX_HOLD_DAYS, breakeven_ratio=BREAKEVEN_RATIO):
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
                stop_dist = sl_mult * atr_[pending_idx]
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
            "risk_pips": risk_pips, "mfe_pips": 0, "mae_pips": 0,
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
# S4-A: WALK-FORWARD ROLLING OUT-OF-SAMPLE
# ═══════════════════════════════════════════════════════════════════════

def s4a_walk_forward(pair_4h):
    """
    Rolling windows: 2-year train, 6-month test, rolling forward by 6 months.
    Uses base cost scenario.
    """
    windows = []
    start_year = 2016
    train_years = 2
    test_months = 6
    roll_months = 6

    current_start = pd.Timestamp(f"{start_year}-01-01")
    data_end = pd.Timestamp("2026-12-31")

    while True:
        train_end = current_start + pd.DateOffset(years=train_years)
        test_start = train_end
        test_end = test_start + pd.DateOffset(months=test_months)

        if test_end > data_end:
            break

        windows.append({
            "train_start": current_start.strftime("%Y-%m-%d"),
            "train_end": (train_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end": (test_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        })
        current_start += pd.DateOffset(months=roll_months)

    window_results = []
    for w in windows:
        train_trades = []
        test_trades = []

        for p, df in pair_4h.items():
            sig = generate_signal_mechanism(df)

            # Train window
            mask_train = (sig.index >= w["train_start"]) & (sig.index <= w["train_end"])
            if mask_train.sum() > 0:
                sig_train = sig.loc[mask_train].copy()
                trades = simulate_realistic(sig_train, p, COST_SCENARIOS["base"])
                train_trades.extend(trades)

            # Test window
            mask_test = (sig.index >= w["test_start"]) & (sig.index <= w["test_end"])
            if mask_test.sum() > 0:
                sig_test = sig.loc[mask_test].copy()
                trades = simulate_realistic(sig_test, p, COST_SCENARIOS["base"])
                test_trades.extend(trades)

        train_m = sim_metrics(train_trades, "train")
        test_m = sim_metrics(test_trades, "test")

        retention = (test_m["avg_pnl_pips"] / max(train_m["avg_pnl_pips"], 1e-10) * 100
                     if train_m["avg_pnl_pips"] > 0 else 0)

        window_results.append({
            "window": w,
            "train": train_m,
            "test": test_m,
            "retention_pct": round(retention, 1),
        })

    # Aggregate statistics
    test_pnls = [w["test"]["avg_pnl_pips"] for w in window_results if w["test"]["n"] > 0]
    test_wrs = [w["test"]["win_rate"] for w in window_results if w["test"]["n"] > 0]
    positive_windows = sum(1 for p in test_pnls if p > 0)

    results = {
        "windows": window_results,
        "summary": {
            "total_windows": len(window_results),
            "positive_windows": positive_windows,
            "positive_pct": round(positive_windows / max(len(window_results), 1) * 100, 1),
            "avg_test_pnl": round(float(np.mean(test_pnls)), 4) if test_pnls else 0,
            "median_test_pnl": round(float(np.median(test_pnls)), 4) if test_pnls else 0,
            "std_test_pnl": round(float(np.std(test_pnls)), 4) if test_pnls else 0,
            "avg_test_wr": round(float(np.mean(test_wrs)), 4) if test_wrs else 0,
            "min_test_pnl": round(float(np.min(test_pnls)), 4) if test_pnls else 0,
            "max_test_pnl": round(float(np.max(test_pnls)), 4) if test_pnls else 0,
            "avg_retention_pct": round(float(np.mean([w["retention_pct"] for w in window_results
                                                       if w["test"]["n"] > 0])), 1),
        },
    }

    return results


# ═══════════════════════════════════════════════════════════════════════
# S4-B: PARAMETER NEIGHBORHOOD SENSITIVITY
# ═══════════════════════════════════════════════════════════════════════

def s4b_parameter_sensitivity(pair_4h):
    """
    Test each parameter at ±20% and ±40% from frozen value.
    Hold other parameters constant.
    """
    base_params = {
        "lookback": LOOKBACK,
        "sl_mult": ATR_SL_MULT,
        "rrr": RRR,
        "max_hold_days": MAX_HOLD_DAYS,
        "breakeven_ratio": BREAKEVEN_RATIO,
    }

    results = {}
    param_perturbations = {
        "lookback": [0.6, 0.8, 1.0, 1.2, 1.4],
        "sl_mult": [0.6, 0.8, 1.0, 1.2, 1.4],
        "rrr": [0.6, 0.8, 1.0, 1.2, 1.4],
        "max_hold_days": [0.6, 0.8, 1.0, 1.2, 1.4],
        "breakeven_ratio": [0.6, 0.8, 1.0, 1.2, 1.4],
    }

    for param_name, multipliers in param_perturbations.items():
        param_results = []
        for mult in multipliers:
            all_trades = []
            # Set parameter
            params = base_params.copy()
            params[param_name] = round(base_params[param_name] * mult, 2)

            for p, df in pair_4h.items():
                sig = generate_signal_mechanism(df, lookback=int(params["lookback"]))
                trades = simulate_realistic(
                    sig, p, COST_SCENARIOS["base"],
                    sl_mult=params["sl_mult"], rrr=params["rrr"],
                    max_hold_days=params["max_hold_days"],
                    breakeven_ratio=params["breakeven_ratio"],
                )
                all_trades.extend(trades)

            m = sim_metrics(all_trades, f"{param_name}={params[param_name]}")
            m["multiplier"] = mult
            m["param_value"] = params[param_name]
            param_results.append(m)

        results[param_name] = param_results

    # Stability analysis: coefficient of variation across parameter values
    stability = {}
    for param_name, prs in results.items():
        pnls = [r["avg_pnl_pips"] for r in prs if r["n"] > 0]
        if pnls:
            mean_pnl = np.mean(pnls)
            std_pnl = np.std(pnls)
            cv = std_pnl / max(abs(mean_pnl), 1e-10)
            positive_count = sum(1 for p in pnls if p > 0)
            stability[param_name] = {
                "mean_pnl": round(float(mean_pnl), 4),
                "std_pnl": round(float(std_pnl), 4),
                "cv": round(float(cv), 4),
                "positive_variants": positive_count,
                "total_variants": len(pnls),
                "robust": cv < 0.5 and positive_count >= len(prs) * 0.6,
            }
        else:
            stability[param_name] = {"robust": False}

    results["stability"] = stability
    return results


# ═══════════════════════════════════════════════════════════════════════
# S4-C: REGIME-CONDITIONED HOLDOUT
# ═══════════════════════════════════════════════════════════════════════

def classify_regime_causal(close, high, low, lookback=20, atr_period=14):
    """
    Classify market regime at bar t using only data up to bar t.
    No future information.
    """
    n = len(close)
    regime = np.zeros(n, dtype=int)  # 0=unknown, 1=trending, 2=ranging
    volatility = np.zeros(n)  # 0=low, 1=high

    for i in range(max(lookback, atr_period) + 1, n):
        # Trend: simple direction consistency over lookback
        window = close[i - lookback:i + 1]
        direction_changes = np.sum(np.diff(np.sign(np.diff(window))) != 0)
        trend_strength = 1 - direction_changes / max(lookback - 2, 1)

        # ATR for volatility
        tr_vals = []
        for j in range(max(i - atr_period + 1, 1), i + 1):
            tr_vals.append(max(high[j] - low[j],
                              abs(high[j] - close[j - 1]),
                              abs(low[j] - close[j - 1])))
        atr_val = np.mean(tr_vals) if tr_vals else 0

        # Use historical ATR for normalization (avoid future)
        hist_atrs = []
        for j in range(max(i - lookback * 2, atr_period + 1), i + 1):
            tr_h = []
            for k in range(max(j - atr_period + 1, 1), j + 1):
                tr_h.append(max(high[k] - low[k],
                               abs(high[k] - close[k - 1]),
                               abs(low[k] - close[k - 1])))
            if tr_h:
                hist_atrs.append(np.mean(tr_h))

        avg_atr = np.mean(hist_atrs) if hist_atrs else atr_val
        vol_ratio = atr_val / max(avg_atr, 1e-10)

        regime[i] = 1 if trend_strength > 0.6 else 2
        volatility[i] = 1 if vol_ratio > 1.2 else 0

    return regime, volatility


def s4c_regime_holdout(pair_4h):
    """
    Classify regimes, then test strategy performance in each regime.
    """
    regime_results = {"trending": [], "ranging": [], "high_vol": [], "low_vol": []}
    regime_counts = {"trending": 0, "ranging": 0, "high_vol": 0, "low_vol": 0}

    for p, df in pair_4h.items():
        close_ = df["close"].values
        high_ = df["high"].values
        low_ = df["low"].values

        regime, vol = classify_regime_causal(close_, high_, low_)

        sig = generate_signal_mechanism(df)

        # Run full simulation to get trade bar indices
        trades = simulate_realistic(sig, p, COST_SCENARIOS["base"])

        for t in trades:
            entry_bar = t["entry_idx"]
            if entry_bar < len(regime):
                r = regime[entry_bar]
                v = vol[entry_bar]
                if r == 1:
                    regime_results["trending"].append(t)
                    regime_counts["trending"] += 1
                elif r == 2:
                    regime_results["ranging"].append(t)
                    regime_counts["ranging"] += 1
                if v == 1:
                    regime_results["high_vol"].append(t)
                    regime_counts["high_vol"] += 1
                else:
                    regime_results["low_vol"].append(t)
                    regime_counts["low_vol"] += 1

    results = {"regime_trade_counts": regime_counts}
    for regime_name, trades in regime_results.items():
        results[regime_name] = sim_metrics(trades, regime_name)

    return results


# ═══════════════════════════════════════════════════════════════════════
# S4-D: STRESS SCENARIO TESTING
# ═══════════════════════════════════════════════════════════════════════

def s4d_stress_scenarios(pair_4h):
    """
    Test performance during known stress periods.
    """
    stress_periods = {
        "covid_crash_2020": ("2020-02-20", "2020-04-30"),
        "rate_hike_2022": ("2022-03-01", "2022-12-31"),
        "banking_crisis_2023": ("2023-03-01", "2023-05-31"),
        "volatility_h1_2024": ("2024-01-01", "2024-06-30"),
        "stable_2019": ("2019-01-01", "2019-12-31"),
        "low_vol_2017": ("2017-01-01", "2017-12-31"),
    }

    results = {}
    for period_name, (start, end) in stress_periods.items():
        all_trades = []
        for p, df in pair_4h.items():
            sig = generate_signal_mechanism(df)
            mask = (sig.index >= start) & (sig.index <= end)
            if mask.sum() == 0:
                continue
            sig_period = sig.loc[mask].copy()
            trades = simulate_realistic(sig_period, p, COST_SCENARIOS["base"])
            all_trades.extend(trades)
        results[period_name] = sim_metrics(all_trades, period_name)

    # Also test worst-case cost scenario during stress
    worst_period = "covid_crash_2020"
    worst_start, worst_end = stress_periods[worst_period]
    worst_trades = []
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        mask = (sig.index >= worst_start) & (sig.index <= worst_end)
        if mask.sum() == 0:
            continue
        sig_period = sig.loc[mask].copy()
        trades = simulate_realistic(sig_period, p, COST_SCENARIOS["severe"])
        worst_trades.extend(trades)
    results["covid_crash_2020_severe_cost"] = sim_metrics(worst_trades, "covid_crash_2020_severe")

    return results


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase S4: Walk-Forward Validation + Parameter Sensitivity")
    print("=" * 70)

    out_dir = Path("/root/nestquant/research_data/simple_strategies")

    print("\n[0] Loading data...")
    pair_4h = load_and_resample()
    print(f"  {len(pair_4h)} pairs loaded")

    all_results = {}

    # ── S4-A: Walk-forward ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S4-A: Walk-Forward Rolling Out-of-Sample")
    print("=" * 70)
    all_results["S4A"] = s4a_walk_forward(pair_4h)
    s = all_results["S4A"]["summary"]
    print(f"  Windows: {s['total_windows']}, Positive: {s['positive_windows']}/{s['total_windows']} "
          f"({s['positive_pct']:.0f}%)")
    print(f"  Avg test PnL: {s['avg_test_pnl']:.2f} pip, Std: {s['std_test_pnl']:.2f} pip")
    print(f"  Min test PnL: {s['min_test_pnl']:.2f} pip, Max: {s['max_test_pnl']:.2f} pip")
    print(f"  Avg retention: {s['avg_retention_pct']:.1f}%")
    for i, w in enumerate(all_results["S4A"]["windows"]):
        print(f"    Window {i+1}: {w['window']['test_start']}..{w['window']['test_end']} "
              f"| train={w['train']['avg_pnl_pips']:.2f} test={w['test']['avg_pnl_pips']:.2f} "
              f"retention={w['retention_pct']:.0f}%")

    # ── S4-B: Parameter sensitivity ────────────────────────────────────
    print("\n" + "=" * 70)
    print("S4-B: Parameter Neighborhood Sensitivity")
    print("=" * 70)
    all_results["S4B"] = s4b_parameter_sensitivity(pair_4h)
    for param_name in ["lookback", "sl_mult", "rrr", "max_hold_days", "breakeven_ratio"]:
        prs = all_results["S4B"][param_name]
        stab = all_results["S4B"]["stability"][param_name]
        print(f"  {param_name:16s}: CV={stab['cv']:.3f}, "
              f"positive={stab['positive_variants']}/{stab['total_variants']}, "
              f"robust={'YES' if stab['robust'] else 'NO'}")
        for r in prs:
            print(f"    {r['param_value']:6.2f} (x{r['multiplier']:.1f}): "
                  f"N={r['n']}, WR={r['win_rate']:.1%}, "
                  f"AvgPnL={r['avg_pnl_pips']:.2f}pip, PF={r['profit_factor']:.2f}")

    # ── S4-C: Regime-conditioned holdout ───────────────────────────────
    print("\n" + "=" * 70)
    print("S4-C: Regime-Conditioned Holdout")
    print("=" * 70)
    all_results["S4C"] = s4c_regime_holdout(pair_4h)
    c = all_results["S4C"]
    print(f"  Trade counts: {c['regime_trade_counts']}")
    for regime in ["trending", "ranging", "high_vol", "low_vol"]:
        m = c[regime]
        print(f"  {regime:12s}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── S4-D: Stress scenarios ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("S4-D: Stress Scenario Testing")
    print("=" * 70)
    all_results["S4D"] = s4d_stress_scenarios(pair_4h)
    for period_name, m in all_results["S4D"].items():
        print(f"  {period_name:30s}: N={m['n']}, WR={m['win_rate']:.1%}, "
              f"AvgPnL={m['avg_pnl_pips']:.2f}pip, PF={m['profit_factor']:.2f}")

    # ── Save ───────────────────────────────────────────────────────────
    all_results["runtime_seconds"] = round(time.time() - t0, 1)
    with open(out_dir / "S4_walk_forward_sensitivity.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f"S4 complete in {time.time() - t0:.1f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
