"""
Phase S5.5: WHY DOES THE STRATEGY LOSE?

This is a DIAGNOSTIC phase. Not optimization. Not filter creation.
We are answering one question: WHY does the frozen strategy lose?

All parameters frozen from S0/S3. No modifications.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ALL_PAIRS
from indicators.pip import pip_size as get_pip_size

DATA_DIR = Path("/root/data")

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
# DATA LOADING + SIGNAL + SIMULATION (frozen from S3)
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
    disp_ = sig["displacement_atr"].values

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
                    # Displacement at entry
                    entry_displacement = disp_[entry_idx] if not np.isnan(disp_[entry_idx]) else 0
                    entry_atr = atr_[entry_idx] if not np.isnan(atr_[entry_idx]) else 0
                    entry_vol_at_entry = atr_[i] if not np.isnan(atr_[i]) else 0
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
                        "displacement_atr": entry_displacement,
                        "atr_at_entry": entry_atr / pip,
                        "atr_at_signal": entry_atr / pip,
                        "vol_at_entry": entry_vol_at_entry / pip,
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
                    entry_displacement = disp_[entry_idx] if not np.isnan(disp_[entry_idx]) else 0
                    entry_atr = atr_[entry_idx] if not np.isnan(atr_[entry_idx]) else 0
                    entry_vol_at_entry = atr_[i] if not np.isnan(atr_[i]) else 0
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
                        "displacement_atr": entry_displacement,
                        "atr_at_entry": entry_atr / pip,
                        "atr_at_signal": entry_atr / pip,
                        "vol_at_entry": entry_vol_at_entry / pip,
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
            "displacement_atr": 0, "atr_at_entry": 0,
            "atr_at_signal": 0, "vol_at_entry": 0,
        })

    return trades


# ═══════════════════════════════════════════════════════════════════════
# REGIME CLASSIFICATION (causal — no look-ahead)
# ═══════════════════════════════════════════════════════════════════════

def classify_regime_causal(close, high, low, lookback=20, atr_period=14):
    """Classify regime at bar t using only data up to bar t. Vectorized."""
    n = len(close)
    vol_regime = np.zeros(n, dtype=int)
    trend_regime = np.zeros(n, dtype=int)

    # TR vectorized
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    tr = np.concatenate(([0], tr))

    # ATR via rolling mean then EMA
    atr_raw = np.full(n, np.nan)
    for i in range(atr_period, n):
        atr_raw[i] = np.mean(tr[i - atr_period + 1:i + 1])
    atr_ema = np.full(n, np.nan)
    if n > atr_period:
        atr_ema[atr_period] = atr_raw[atr_period]
        for i in range(atr_period + 1, n):
            if not np.isnan(atr_raw[i]):
                atr_ema[i] = (atr_ema[i - 1] * (atr_period - 1) + atr_raw[i]) / atr_period

    # Rolling average ATR (expanding, for vol ratio)
    cumsum = np.nancumsum(tr)
    count = np.cumsum(~np.isnan(tr))
    avg_atr = np.full(n, np.nan)
    for i in range(lookback * 2, n):
        start = max(0, i - lookback * 2)
        window = tr[start:i + 1]
        avg_atr[i] = np.mean(window[~np.isnan(window)])

    # Vol ratio
    vol_ratio = np.where(avg_atr > 0, atr_ema / avg_atr, 1.0)
    vol_regime[vol_ratio > 1.2] = 2
    vol_regime[(vol_ratio > 0) & (vol_ratio <= 1.2)] = 1

    # Trend: rolling direction consistency
    for i in range(lookback, n):
        window = close[i - lookback:i + 1]
        diffs = np.diff(window)
        direction_changes = np.sum(np.diff(np.sign(diffs)) != 0)
        trend_strength = 1 - direction_changes / max(lookback - 2, 1)
        trend_regime[i] = 1 if trend_strength > 0.6 else 2

    return vol_regime, trend_regime


def classify_vol_atr_buckets(atr_values, n_buckets=4):
    """Bucket ATR into quantiles (causal: use expanding window)."""
    n = len(atr_values)
    buckets = np.zeros(n, dtype=int)
    valid = ~np.isnan(atr_values) & (atr_values > 0)
    for i in range(1, n):
        if not valid[i]:
            continue
        hist = atr_values[:i + 1]
        hist_valid = hist[valid[:i + 1]]
        if len(hist_valid) < 10:
            continue
        pct = np.searchsorted(np.percentile(hist_valid, [25, 50, 75]), atr_values[i])
        buckets[i] = pct + 1  # 1-4
    return buckets


# ═══════════════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def analysis_1_losing_month_profile(trades_df):
    """ANALYSIS 1: Detailed profile of each losing month."""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")

    monthly = trades_df.groupby("month").agg(
        total_pnl=("pnl_pips", "sum"),
        n_trades=("pnl_pips", "count"),
        win_rate=("pnl_pips", lambda x: (x > 0).mean()),
        avg_pnl=("pnl_pips", "mean"),
        avg_r=("r", "mean"),
        max_dd=("pnl_pips", lambda x: float(np.min(np.cumsum(x) - np.maximum.accumulate(np.cumsum(x))))),
        avg_hold=("hold_bars", "mean"),
        median_hold=("hold_bars", "median"),
        long_trades=("direction", lambda x: (x == 1).sum()),
        short_trades=("direction", lambda x: (x == -1).sum()),
        avg_displacement=("displacement_atr", "mean"),
        avg_vol_at_entry=("vol_at_entry", "mean"),
    ).reset_index()

    # Profit factor by month
    def pf_calc(group):
        wins = group[group > 0].sum()
        losses = abs(group[group <= 0].sum())
        return wins / max(losses, 1e-10)

    monthly_pf = trades_df.groupby("month")["pnl_pips"].apply(pf_calc).reset_index()
    monthly_pf.columns = ["month", "profit_factor"]
    monthly = monthly.merge(monthly_pf, on="month")

    # Max consecutive losses by month
    def max_consec_losses(group):
        pnl = group["pnl_pips"].values
        max_streak = 0
        current = 0
        for p in pnl:
            if p <= 0:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    consec = trades_df.groupby("month").apply(max_consec_losses).reset_index()
    consec.columns = ["month", "max_consec_losses"]
    monthly = monthly.merge(consec, on="month")

    # Failed breakout rate by month (SL exits / total)
    def failed_rate(group):
        return (group["exit_reason"] == "SL").mean()

    fail_rate = trades_df.groupby("month").apply(failed_rate).reset_index()
    fail_rate.columns = ["month", "failed_breakout_rate"]
    monthly = monthly.merge(fail_rate, on="month")

    # Successful breakout rate (TP exits)
    def success_rate(group):
        return (group["exit_reason"] == "TP").mean()

    succ_rate = trades_df.groupby("month").apply(success_rate).reset_index()
    succ_rate.columns = ["month", "success_rate"]
    monthly = monthly.merge(succ_rate, on="month")

    # Instrument distribution per month
    inst_dist = {}
    for month in monthly["month"]:
        month_trades = trades_df[trades_df["month"] == month]
        inst_dist[str(month)] = dict(month_trades["pair"].value_counts())

    return monthly, inst_dist


def analysis_2_loss_concentration(trades_df):
    """ANALYSIS 2: Where do losses come from?"""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")
    losing = trades_df[trades_df["pnl_pips"] <= 0]

    # Top-N loss contribution by month
    top_n_loss = {}
    for month in trades_df["month"].unique():
        mt = trades_df[trades_df["month"] == month]
        total_loss = mt[mt["pnl_pips"] <= 0]["pnl_pips"].sum()
        if total_loss >= 0:
            top_n_loss[str(month)] = {"top_1": 0, "top_5": 0, "top_10": 0}
            continue
        sorted_losses = mt[mt["pnl_pips"] <= 0]["pnl_pips"].sort_values()
        top_n_loss[str(month)] = {
            "top_1": round(float(sorted_losses.iloc[0] / total_loss * 100), 1) if len(sorted_losses) >= 1 else 0,
            "top_5": round(float(sorted_losses.iloc[:5].sum() / total_loss * 100), 1) if len(sorted_losses) >= 5 else round(float(sorted_losses.sum() / total_loss * 100), 1),
            "top_10": round(float(sorted_losses.iloc[:10].sum() / total_loss * 100), 1) if len(sorted_losses) >= 10 else round(float(sorted_losses.sum() / total_loss * 100), 1),
        }

    # Loss by instrument
    loss_by_instrument = losing.groupby("pair")["pnl_pips"].sum().sort_values()

    # Loss by direction
    loss_by_dir = losing.groupby("direction")["pnl_pips"].sum()

    # Loss by exit reason
    loss_by_reason = losing.groupby("exit_reason")["pnl_pips"].sum()

    # Loss by vol bucket (if available)
    loss_by_vol = {}
    if "vol_bucket" in losing.columns:
        loss_by_vol = losing.groupby("vol_bucket")["pnl_pips"].sum().to_dict()

    return {
        "top_n_loss_by_month": top_n_loss,
        "loss_by_instrument": loss_by_instrument.to_dict(),
        "loss_by_direction": {str(k): v for k, v in loss_by_dir.items()},
        "loss_by_exit_reason": loss_by_reason.to_dict(),
        "loss_by_vol_bucket": loss_by_vol,
    }


def analysis_3_volatility(trades_df, all_trades_df):
    """ANALYSIS 3: Is low volatility associated with losses?"""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")

    # Monthly average volatility
    monthly_vol = trades_df.groupby("month").agg(
        avg_vol=("vol_at_entry", "mean"),
        avg_displacement=("displacement_atr", "mean"),
        avg_pnl=("pnl_pips", "sum"),
    ).reset_index()

    # Correlation between vol and PnL
    valid = monthly_vol[(monthly_vol["avg_vol"] > 0) & (monthly_vol["avg_pnl"].notna())]
    if len(valid) > 2:
        corr_vol_pnl = float(np.corrcoef(valid["avg_vol"], valid["avg_pnl"])[0, 1])
        corr_disp_pnl = float(np.corrcoef(valid["avg_displacement"], valid["avg_pnl"])[0, 1])
    else:
        corr_vol_pnl = 0
        corr_disp_pnl = 0

    # Win rate by vol bucket
    wr_by_vol = trades_df.groupby("vol_bucket").agg(
        win_rate=("pnl_pips", lambda x: (x > 0).mean()),
        avg_pnl=("pnl_pips", "mean"),
        n=("pnl_pips", "count"),
    ).to_dict("index")

    # Failed breakout rate by vol bucket
    fail_by_vol = trades_df.groupby("vol_bucket").apply(
        lambda x: (x["exit_reason"] == "SL").mean()
    ).to_dict()

    return {
        "monthly_vol_stats": monthly_vol.to_dict("records"),
        "corr_vol_pnl": round(corr_vol_pnl, 4),
        "corr_displacement_pnl": round(corr_disp_pnl, 4),
        "win_rate_by_vol_bucket": {str(k): v for k, v in wr_by_vol.items()},
        "failed_breakout_rate_by_vol": {str(k): round(v, 4) for k, v in fail_by_vol.items()},
    }


def analysis_4_failed_breakout_clustering(trades_df):
    """ANALYSIS 4: Do failed breakouts cluster?"""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")
    failed = trades_df[trades_df["exit_reason"] == "SL"].copy()

    # Failed breakout rate by month
    monthly_fail_rate = trades_df.groupby("month").apply(
        lambda x: (x["exit_reason"] == "SL").mean()
    ).reset_index()
    monthly_fail_rate.columns = ["month", "fail_rate"]

    # Compare losing vs profitable months
    monthly_pnl = trades_df.groupby("month")["pnl_pips"].sum().reset_index()
    monthly_pnl.columns = ["month", "total_pnl"]
    merged = monthly_fail_rate.merge(monthly_pnl, on="month")
    merged["is_losing"] = merged["total_pnl"] < 0

    losing_fail_rate = merged[merged["is_losing"]]["fail_rate"].mean()
    winning_fail_rate = merged[~merged["is_losing"]]["fail_rate"].mean()

    # Consecutive failed breakout streaks
    fail_streaks = []
    current_streak = 0
    for _, row in trades_df.sort_values("exit_time").iterrows():
        if row["exit_reason"] == "SL":
            current_streak += 1
        else:
            if current_streak > 0:
                fail_streaks.append(current_streak)
            current_streak = 0
    if current_streak > 0:
        fail_streaks.append(current_streak)

    # Failed breakout by instrument
    fail_by_instrument = failed.groupby("pair").size().sort_values(ascending=False)

    # Failed breakout by vol bucket
    fail_by_vol = failed.groupby("vol_bucket").size() if "vol_bucket" in failed.columns else pd.Series()

    return {
        "monthly_fail_rate": monthly_fail_rate.to_dict("records"),
        "losing_month_fail_rate": round(losing_fail_rate, 4) if not np.isnan(losing_fail_rate) else None,
        "winning_month_fail_rate": round(winning_fail_rate, 4) if not np.isnan(winning_fail_rate) else None,
        "fail_rate_ratio": round(losing_fail_rate / max(winning_fail_rate, 1e-10), 2) if not np.isnan(losing_fail_rate) and not np.isnan(winning_fail_rate) else None,
        "consec_fail_streaks": {
            "max": max(fail_streaks) if fail_streaks else 0,
            "mean": round(np.mean(fail_streaks), 1) if fail_streaks else 0,
            "median": round(np.median(fail_streaks), 1) if fail_streaks else 0,
        },
        "fail_by_instrument": fail_by_instrument.to_dict(),
        "fail_by_vol_bucket": {str(k): int(v) for k, v in fail_by_vol.items()} if len(fail_by_vol) > 0 else {},
    }


def analysis_5_regime_transition(trades_df):
    """ANALYSIS 5: Do losses cluster around regime transitions?"""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")

    # Monthly regime stats
    monthly_regime = trades_df.groupby("month").agg(
        avg_vol=("vol_at_entry", "mean"),
        total_pnl=("pnl_pips", "sum"),
        n_trades=("pnl_pips", "count"),
        high_vol_pct=("vol_bucket", lambda x: (x >= 3).mean() if "vol_bucket" in trades_df.columns else 0),
    ).reset_index()

    # Detect transitions: vol change month-over-month
    monthly_regime = monthly_regime.sort_values("month")
    monthly_regime["vol_change"] = monthly_regime["avg_vol"].pct_change()
    monthly_regime["is_transition"] = monthly_regime["vol_change"].abs() > 0.3

    # Correlation between vol transitions and PnL
    valid = monthly_regime.dropna(subset=["vol_change", "total_pnl"])
    if len(valid) > 2:
        corr_transition_pnl = float(np.corrcoef(valid["vol_change"].abs(), valid["total_pnl"])[0, 1])
    else:
        corr_transition_pnl = 0

    # Is losing month more likely to be a transition?
    if len(monthly_regime) > 0:
        losing_transition_rate = monthly_regime[monthly_regime["total_pnl"] < 0]["is_transition"].mean()
        winning_transition_rate = monthly_regime[monthly_regime["total_pnl"] >= 0]["is_transition"].mean()
    else:
        losing_transition_rate = 0
        winning_transition_rate = 0

    return {
        "monthly_regime": monthly_regime.to_dict("records"),
        "corr_vol_transition_pnl": round(corr_transition_pnl, 4),
        "losing_month_transition_rate": round(losing_transition_rate, 4) if not np.isnan(losing_transition_rate) else None,
        "winning_month_transition_rate": round(winning_transition_rate, 4) if not np.isnan(winning_transition_rate) else None,
    }


def analysis_6_instrument(trades_df):
    """ANALYSIS 6: Instrument contribution to losses."""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")

    # Per-instrument stats
    inst_stats = trades_df.groupby("pair").agg(
        n=("pnl_pips", "count"),
        total_pnl=("pnl_pips", "sum"),
        avg_pnl=("pnl_pips", "mean"),
        win_rate=("pnl_pips", lambda x: (x > 0).mean()),
        pf=("pnl_pips", lambda x: float(x[x > 0].sum()) / max(float(np.abs(x[x <= 0].sum())), 1e-10)),
    ).reset_index()

    # Percentage of total loss by instrument
    total_loss = trades_df[trades_df["pnl_pips"] <= 0]["pnl_pips"].sum()
    inst_loss = trades_df[trades_df["pnl_pips"] <= 0].groupby("pair")["pnl_pips"].sum()
    inst_loss_pct = (inst_loss / total_loss * 100).sort_values(ascending=False) if total_loss < 0 else pd.Series()

    # Do losing months have the same instrument distribution?
    losing_months = trades_df.groupby("month")["pnl_pips"].sum()
    losing_months = losing_months[losing_months < 0].index.tolist()
    winning_months = trades_df.groupby("month")["pnl_pips"].sum()
    winning_months = winning_months[winning_months >= 0].index.tolist()

    losing_inst_dist = trades_df[trades_df["month"].isin(losing_months)]["pair"].value_counts(normalize=True)
    winning_inst_dist = trades_df[trades_df["month"].isin(winning_months)]["pair"].value_counts(normalize=True)

    return {
        "instrument_stats": inst_stats.to_dict("records"),
        "loss_pct_by_instrument": inst_loss_pct.to_dict(),
        "losing_month_instrument_dist": losing_inst_dist.to_dict(),
        "winning_month_instrument_dist": winning_inst_dist.to_dict(),
    }


def analysis_7_directional(trades_df):
    """ANALYSIS 7: Long/short asymmetry."""
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")

    for direction in [1, -1]:
        dir_label = "long" if direction == 1 else "short"
        dt = trades_df[trades_df["direction"] == direction]

    # Overall directional stats
    dir_stats = {}
    for d in [1, -1]:
        label = "long" if d == 1 else "short"
        dt = trades_df[trades_df["direction"] == d]
        if len(dt) == 0:
            continue
        wins = dt[dt["pnl_pips"] > 0]["pnl_pips"]
        losses = dt[dt["pnl_pips"] <= 0]["pnl_pips"]
        dir_stats[label] = {
            "n": len(dt),
            "win_rate": round(float((dt["pnl_pips"] > 0).mean()), 4),
            "avg_pnl": round(float(dt["pnl_pips"].mean()), 4),
            "avg_r": round(float(dt["r"].mean()), 4),
            "pf": round(float(wins.sum()) / max(float(np.abs(losses.sum())), 1e-10), 4),
        }

    # Directional stats by month
    monthly_dir = {}
    for month in trades_df["month"].unique():
        mt = trades_df[trades_df["month"] == month]
        monthly_dir[str(month)] = {}
        for d in [1, -1]:
            label = "long" if d == 1 else "short"
            dt = mt[mt["direction"] == d]
            if len(dt) == 0:
                continue
            monthly_dir[str(month)][label] = {
                "n": len(dt),
                "win_rate": round(float((dt["pnl_pips"] > 0).mean()), 4),
                "avg_pnl": round(float(dt["pnl_pips"].mean()), 4),
                "total_pnl": round(float(dt["pnl_pips"].sum()), 2),
            }

    # Max losing streaks by direction
    streaks = {}
    for d in [1, -1]:
        label = "long" if d == 1 else "short"
        dt = trades_df[trades_df["direction"] == d].sort_values("exit_time")
        max_streak = 0
        current = 0
        for p in dt["pnl_pips"]:
            if p <= 0:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        streaks[label] = max_streak

    return {
        "direction_stats": dir_stats,
        "monthly_direction": monthly_dir,
        "max_losing_streaks": streaks,
    }


def analysis_8_loss_streaks(trades_df):
    """ANALYSIS 8: Loss-streak dynamics."""
    trades_df = trades_df.sort_values("exit_time").reset_index(drop=True)

    # Compute all streaks
    streaks = []
    current_streak = 0
    streak_start = 0
    for i, row in trades_df.iterrows():
        if row["pnl_pips"] <= 0:
            if current_streak == 0:
                streak_start = i
            current_streak += 1
        else:
            if current_streak > 0:
                streaks.append({
                    "length": current_streak,
                    "start_idx": streak_start,
                    "end_idx": i - 1,
                    "start_time": str(trades_df.iloc[streak_start]["exit_time"]),
                    "end_time": str(trades_df.iloc[i - 1]["exit_time"]),
                    "total_pnl": float(trades_df.iloc[streak_start:i]["pnl_pips"].sum()),
                    "avg_vol": float(trades_df.iloc[streak_start:i]["vol_at_entry"].mean()) if "vol_at_entry" in trades_df.columns else 0,
                    "avg_displacement": float(trades_df.iloc[streak_start:i]["displacement_atr"].mean()) if "displacement_atr" in trades_df.columns else 0,
                    "instruments": trades_df.iloc[streak_start:i]["pair"].nunique(),
                    "failed_breakout_pct": float((trades_df.iloc[streak_start:i]["exit_reason"] == "SL").mean()),
                })
            current_streak = 0

    # What happens after long streaks?
    post_streak = []
    for s in streaks:
        if s["length"] >= 5:
            after_idx = s["end_idx"] + 1
            if after_idx < len(trades_df):
                next_5 = trades_df.iloc[after_idx:after_idx + 5]
                post_streak.append({
                    "streak_length": s["length"],
                    "post_streak_wr": float((next_5["pnl_pips"] > 0).mean()),
                    "post_streak_avg_pnl": float(next_5["pnl_pips"].mean()),
                })

    return {
        "streak_distribution": {
            "total_streaks": len(streaks),
            "max_length": max(s["length"] for s in streaks) if streaks else 0,
            "mean_length": round(np.mean([s["length"] for s in streaks]), 1) if streaks else 0,
            "median_length": round(np.median([s["length"] for s in streaks]), 1) if streaks else 0,
            "length_3_plus": sum(1 for s in streaks if s["length"] >= 3),
            "length_5_plus": sum(1 for s in streaks if s["length"] >= 5),
            "length_10_plus": sum(1 for s in streaks if s["length"] >= 10),
        },
        "long_streaks": [s for s in streaks if s["length"] >= 5],
        "post_streak_analysis": post_streak,
        "streaks": streaks,
    }


def analysis_9_failure_classification(results):
    """ANALYSIS 9: Classify the failure mechanism."""
    # Collect evidence
    evidence = {}

    # Check A1: losing month profile
    losing_months = [r for r in results.get("monthly_stats", []) if r.get("total_pnl", 0) < 0]
    evidence["n_losing_months"] = len(losing_months)

    # Check A3: volatility
    vol_corr = results.get("volatility", {}).get("corr_vol_pnl", 0)
    evidence["vol_pnl_corr"] = vol_corr

    # Check A4: failed breakout clustering
    fail_ratio = results.get("failed_breakout", {}).get("fail_rate_ratio", 1)
    evidence["fail_rate_ratio"] = fail_ratio

    # Check A5: regime transitions
    transition_corr = results.get("regime_transition", {}).get("corr_vol_transition_pnl", 0)
    evidence["transition_pnl_corr"] = transition_corr

    # Check A6: instrument concentration
    inst_loss = results.get("instrument", {}).get("loss_pct_by_instrument", {})
    if inst_loss:
        top_3_loss = sum(list(inst_loss.values())[:3])
        evidence["top_3_instrument_loss_pct"] = top_3_loss
    else:
        evidence["top_3_instrument_loss_pct"] = 0

    # Check A2: loss concentration
    top_n = results.get("loss_concentration", {}).get("top_n_loss_by_month", {})
    avg_top1 = np.mean([v["top_1"] for v in top_n.values()]) if top_n else 0
    evidence["avg_top1_loss_contribution"] = avg_top1

    # Check A7: directional
    dir_stats = results.get("directional", {}).get("direction_stats", {})
    if "long" in dir_stats and "short" in dir_stats:
        evidence["dir_wr_diff"] = abs(dir_stats["long"]["win_rate"] - dir_stats["short"]["win_rate"])
        evidence["dir_pnl_diff"] = abs(dir_stats["long"]["avg_pnl"] - dir_stats["short"]["avg_pnl"])
    else:
        evidence["dir_wr_diff"] = 0
        evidence["dir_pnl_diff"] = 0

    # Classification
    classifications = []

    # Low volatility?
    if vol_corr < -0.3:
        classifications.append(("LOW-VOLATILITY FAILURE", "MODERATE", evidence))

    # Failed breakout clustering?
    if fail_ratio > 1.3:
        classifications.append(("FALSE-BREAKOUT FAILURE", "MODERATE" if fail_ratio > 1.5 else "WEAK", evidence))

    # Regime transition?
    if abs(transition_corr) > 0.2:
        classifications.append(("REGIME-TRANSITION FAILURE", "WEAK", evidence))

    # Instrument-specific?
    if evidence.get("top_3_instrument_loss_pct", 0) > 50:
        classifications.append(("INSTRUMENT-SPECIFIC FAILURE", "WEAK", evidence))

    # Directional?
    if evidence.get("dir_wr_diff", 0) > 0.05:
        classifications.append(("DIRECTIONAL FAILURE", "WEAK", evidence))

    # Loss clustering?
    if avg_top1 > 30:
        classifications.append(("LOSS CLUSTERING / STATISTICAL VARIANCE", "MODERATE", evidence))

    if not classifications:
        classifications.append(("NO STABLE FAILURE MECHANISM IDENTIFIED", "WEAK", evidence))

    # Rank by evidence strength
    strength_order = {"STRONG": 0, "MODERATE": 1, "WEAK": 2, "INCONCLUSIVE": 3}
    classifications.sort(key=lambda x: strength_order.get(x[1], 3))

    return {
        "evidence": evidence,
        "classifications": [{"mechanism": c[0], "strength": c[1]} for c in classifications],
        "primary": classifications[0][0] if classifications else "UNKNOWN",
        "primary_strength": classifications[0][1] if classifications else "UNKNOWN",
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase S5.5: WHY DOES THE STRATEGY LOSE?")
    print("=" * 70)

    out_dir = Path("/root/nestquant/research_data/simple_strategies")

    print("\n[0] Loading data...")
    pair_4h = load_and_resample()
    print(f"  {len(pair_4h)} pairs loaded")

    # Generate all trades
    print("\n[1] Generating all trades (base cost)...")
    all_trades = []
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        trades = simulate_realistic(sig, p, COST_SCENARIOS["base"])
        all_trades.extend(trades)

    trades_df = pd.DataFrame(all_trades)
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
    trades_df["month"] = trades_df["exit_time"].dt.to_period("M")
    print(f"  {len(trades_df)} trades")

    # Classify regimes (causal) — vectorized per pair
    print("\n[2] Classifying regimes...")
    full_vol_buckets = np.zeros(len(trades_df), dtype=int)
    full_vol_regimes = np.zeros(len(trades_df), dtype=int)
    full_trend_regimes = np.zeros(len(trades_df), dtype=int)

    for p, df in pair_4h.items():
        close_ = df["close"].values
        high_ = df["high"].values
        low_ = df["low"].values
        atr_vals = compute_atr_independent(high_, low_, close_, ATR_PERIOD)
        vol_reg, trend_reg = classify_regime_causal(close_, high_, low_)
        vol_bucket = classify_vol_atr_buckets(atr_vals)

        pair_mask = trades_df["pair"] == p
        indices = trades_df.index[pair_mask]
        entry_idxs = trades_df.loc[indices, "entry_idx"].values.astype(int)

        # Vectorized assignment
        valid_mask = entry_idxs < len(vol_bucket)
        valid_indices = indices[valid_mask]
        valid_entry = entry_idxs[valid_mask]
        full_vol_buckets[valid_indices] = vol_bucket[valid_entry]
        full_vol_regimes[valid_indices] = vol_reg[valid_entry]
        full_trend_regimes[valid_indices] = trend_reg[valid_entry]

    trades_df["vol_bucket"] = full_vol_buckets
    trades_df["vol_regime"] = full_vol_regimes
    trades_df["trend_regime"] = full_trend_regimes

    # Run all analyses
    print("\n[3] Analysis 1: Losing month profile...")
    monthly_stats, inst_dist = analysis_1_losing_month_profile(trades_df)
    losing_months = monthly_stats[monthly_stats["total_pnl"] < 0]
    winning_months = monthly_stats[monthly_stats["total_pnl"] >= 0]
    print(f"  Losing months: {len(losing_months)}, Winning months: {len(winning_months)}")

    print("\n[4] Analysis 2: Loss concentration...")
    loss_conc = analysis_2_loss_concentration(trades_df)

    print("\n[5] Analysis 3: Volatility...")
    vol_analysis = analysis_3_volatility(trades_df, trades_df)

    print("\n[6] Analysis 4: Failed breakout clustering...")
    fail_analysis = analysis_4_failed_breakout_clustering(trades_df)

    print("\n[7] Analysis 5: Regime transitions...")
    regime_analysis = analysis_5_regime_transition(trades_df)

    print("\n[8] Analysis 6: Instrument contribution...")
    inst_analysis = analysis_6_instrument(trades_df)

    print("\n[9] Analysis 7: Long/short symmetry...")
    dir_analysis = analysis_7_directional(trades_df)

    print("\n[10] Analysis 8: Loss-streak dynamics...")
    streak_analysis = analysis_8_loss_streaks(trades_df)

    # Compile results
    print("\n[11] Compiling results...")
    all_results = {
        "summary": {
            "total_trades": len(trades_df),
            "total_months": len(monthly_stats),
            "losing_months": len(losing_months),
            "winning_months": len(winning_months),
        },
        "monthly_stats": monthly_stats.to_dict("records"),
        "losing_month_details": losing_months.to_dict("records"),
        "winning_month_details": winning_months.to_dict("records"),
        "instrument_distribution_by_month": inst_dist,
        "loss_concentration": loss_conc,
        "volatility": vol_analysis,
        "failed_breakout": fail_analysis,
        "regime_transition": regime_analysis,
        "instrument": inst_analysis,
        "directional": dir_analysis,
        "loss_streaks": streak_analysis,
    }

    # Failure classification
    print("\n[12] Failure mechanism classification...")
    classification = analysis_9_failure_classification(all_results)
    all_results["failure_classification"] = classification

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nLosing months ({len(losing_months)}/{len(monthly_stats)}):")
    for _, row in losing_months.iterrows():
        print(f"  {row['month']}: PnL={row['total_pnl']:.0f}pip, N={row['n_trades']}, "
              f"WR={row['win_rate']:.1%}, PF={row['profit_factor']:.2f}, "
              f"FailedBR={row['failed_breakout_rate']:.1%}, "
              f"MaxConsecLoss={row['max_consec_losses']}")

    print(f"\nWinning month averages:")
    print(f"  Avg PnL: {winning_months['total_pnl'].mean():.0f} pip")
    print(f"  Avg WR: {winning_months['win_rate'].mean():.1%}")
    print(f"  Avg PF: {winning_months['profit_factor'].mean():.2f}")
    print(f"  Avg FailedBR: {winning_months['failed_breakout_rate'].mean():.1%}")

    print(f"\nVolatility analysis:")
    print(f"  Vol-PnL correlation: {vol_analysis['corr_vol_pnl']:.4f}")
    print(f"  Displacement-PnL correlation: {vol_analysis['corr_displacement_pnl']:.4f}")

    print(f"\nFailed breakout clustering:")
    print(f"  Losing month fail rate: {fail_analysis.get('losing_month_fail_rate', 'N/A')}")
    print(f"  Winning month fail rate: {fail_analysis.get('winning_month_fail_rate', 'N/A')}")
    print(f"  Fail rate ratio: {fail_analysis.get('fail_rate_ratio', 'N/A')}")

    print(f"\nFailure classification:")
    for c in classification["classifications"]:
        print(f"  {c['mechanism']}: {c['strength']}")

    # Save
    with open(out_dir / "S5_5_failure_analysis.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"S5.5 complete in {time.time() - t0:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
