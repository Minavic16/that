"""
Extract actual equity curve, monthly P&L, and drawdown statistics
from the S3 base-cost simulation for financial planning.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


from config import ALL_PAIRS
from nestquant.core.tooling.indicators.pip import pip_size as get_pip_size

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
# SIGNAL + SIMULATION (same as S3/S4)
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


# ═══════════════════════════════════════════════════════════════════════
# EQUITY CURVE + DRAWDOWN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

def compute_equity_curve(trades):
    """Compute equity curve from trade list, sorted by exit time."""
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df = df.sort_values("exit_time").reset_index(drop=True)
    df["cum_pnl"] = df["pnl_pips"].cumsum()

    # Drawdown from equity high
    equity_high = df["cum_pnl"].cummax()
    df["drawdown_pips"] = df["cum_pnl"] - equity_high

    return df


def compute_monthly_stats(trades):
    """Compute monthly PnL and trade count."""
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["month"] = df["exit_time"].dt.to_period("M")

    monthly = df.groupby("month").agg(
        trades=("pnl_pips", "count"),
        total_pnl=("pnl_pips", "sum"),
        avg_pnl=("pnl_pips", "mean"),
        win_rate=("pnl_pips", lambda x: (x > 0).mean()),
        max_trade=("pnl_pips", "max"),
        min_trade=("pnl_pips", "min"),
    ).reset_index()

    monthly["cum_pnl"] = monthly["total_pnl"].cumsum()
    monthly["equity_high"] = monthly["cum_pnl"].cummax()
    monthly["drawdown"] = monthly["cum_pnl"] - monthly["equity_high"]

    return monthly


def compute_drawdown_stats(trades):
    """Compute detailed drawdown statistics."""
    eq = compute_equity_curve(trades)
    if eq.empty:
        return {}

    dd = eq["drawdown_pips"].values
    max_dd = float(dd.min())  # negative

    # Drawdown duration: consecutive bars in drawdown
    in_dd = dd < 0
    dd_durations = []
    current_duration = 0
    for v in in_dd:
        if v:
            current_duration += 1
        else:
            if current_duration > 0:
                dd_durations.append(current_duration)
            current_duration = 0
    if current_duration > 0:
        dd_durations.append(current_duration)

    max_dd_duration = max(dd_durations) if dd_durations else 0
    avg_dd_duration = np.mean(dd_durations) if dd_durations else 0

    # R-multiple distribution
    rs = np.array([t["r"] for t in trades])

    # Win/loss streaks
    wins = eq["pnl_pips"].values > 0
    streaks_w, streaks_l = [], []
    current_streak = 0
    is_win = None
    for w in wins:
        if is_win is None:
            is_win = w
            current_streak = 1
        elif w == is_win:
            current_streak += 1
        else:
            (streaks_w if is_win else streaks_l).append(current_streak)
            is_win = w
            current_streak = 1
    if current_streak > 0:
        (streaks_w if is_win else streaks_l).append(current_streak)

    return {
        "max_drawdown_pips": round(max_dd, 2),
        "max_drawdown_duration_bars": max_dd_duration,
        "avg_drawdown_duration_bars": round(avg_dd_duration, 1),
        "max_win_streak": max(streaks_w) if streaks_w else 0,
        "max_loss_streak": max(streaks_l) if streaks_l else 0,
        "r_mean": round(float(np.mean(rs)), 4),
        "r_std": round(float(np.std(rs)), 4),
        "r_median": round(float(np.median(rs)), 4),
        "r_5th": round(float(np.percentile(rs, 5)), 4),
        "r_25th": round(float(np.percentile(rs, 25)), 4),
        "r_75th": round(float(np.percentile(rs, 75)), 4),
        "r_95th": round(float(np.percentile(rs, 95)), 4),
    }


def compute_financial_numbers(trades, account_balance=2500, risk_pct=0.01):
    """
    Compute financial planning numbers for The5ers $2.5K account.
    """
    if not trades:
        return {}

    pnls = np.array([t["pnl_pips"] for t in trades])
    rs = np.array([t["r"] for t in trades])

    # Monthly aggregation
    monthly = compute_monthly_stats(trades)

    # Drawdown
    dd_stats = compute_drawdown_stats(trades)

    # Trade frequency
    exit_times = pd.to_datetime([t["exit_time"] for t in trades])
    total_days = (exit_times.max() - exit_times.min()).days
    trades_per_month = len(trades) / max(total_days / 30.44, 1)

    # Risk sizing
    # pip_value depends on lot size and pair
    # For a rough estimate, assume 1 pip ≈ $10 per standard lot
    # But we need per-pair pip values
    avg_r_pips = np.mean([t["risk_pips"] for t in trades])

    # Conservative planning: use avg R
    # 1R = risk_pct × account
    one_r_dollar = account_balance * risk_pct

    # Monthly EV in R
    avg_r = float(np.mean(rs))
    monthly_r_ev = avg_r * trades_per_month

    # Monthly EV in pips (average)
    avg_pnl_pips = float(np.mean(pnls))
    monthly_pip_ev = avg_pnl_pips * trades_per_month

    # Monthly EV in dollars (at risk_pct)
    monthly_dollar_ev = monthly_r_ev * one_r_dollar

    # Max DD in R
    max_dd_pips = dd_stats.get("max_drawdown_pips", 0)
    avg_risk_pips = np.mean([t["risk_pips"] for t in trades])
    max_dd_r = abs(max_dd_pips) / avg_risk_pips if avg_risk_pips > 0 else 0

    # Max DD in dollars
    max_dd_dollar = max_dd_r * one_r_dollar

    # Probability of hitting The5ers limits
    # 10% loss = $250 = 250/one_r_dollar R
    r_limit_10pct = (account_balance * 0.10) / one_r_dollar
    # Monthly: probability that monthly DD exceeds limit
    monthly_dd = monthly["drawdown"].values
    monthly_dd_r = np.abs(monthly_dd) / avg_risk_pips if avg_risk_pips > 0 else np.abs(monthly_dd)
    prob_exceed_10pct_monthly = float(np.mean(monthly_dd_r > r_limit_10pct)) if len(monthly_dd_r) > 0 else 0

    # Losing month frequency
    losing_months = (monthly["total_pnl"] < 0).sum()
    total_months = len(monthly)
    losing_month_freq = losing_months / max(total_months, 1)

    return {
        "account_balance": account_balance,
        "risk_pct": risk_pct,
        "one_r_dollar": round(one_r_dollar, 2),

        "total_trades": len(trades),
        "total_days": total_days,
        "trades_per_month": round(trades_per_month, 1),

        "avg_pnl_pips": round(avg_pnl_pips, 4),
        "avg_r": round(avg_r, 4),
        "win_rate": round(float(np.mean(pnls > 0)), 4),
        "profit_factor": round(
            float(np.sum(pnls[pnls > 0])) / max(float(np.abs(np.sum(pnls[pnls <= 0]))), 1e-10), 4),

        "monthly_pip_ev": round(monthly_pip_ev, 1),
        "monthly_r_ev": round(monthly_r_ev, 2),
        "monthly_dollar_ev": round(monthly_dollar_ev, 2),

        "max_dd_pips": dd_stats.get("max_drawdown_pips", 0),
        "max_dd_r": round(max_dd_r, 2),
        "max_dd_dollar": round(max_dd_dollar, 2),
        "max_dd_duration_bars": dd_stats.get("max_drawdown_duration_bars", 0),

        "avg_trade_risk_pips": round(avg_risk_pips, 2),

        "monthly_stats": {
            "n_months": total_months,
            "avg_monthly_pnl": round(float(monthly["total_pnl"].mean()), 2),
            "median_monthly_pnl": round(float(monthly["total_pnl"].median()), 2),
            "std_monthly_pnl": round(float(monthly["total_pnl"].std()), 2),
            "best_month_pnl": round(float(monthly["total_pnl"].max()), 2),
            "worst_month_pnl": round(float(monthly["total_pnl"].min()), 2),
            "losing_months": int(losing_months),
            "losing_month_freq": round(losing_month_freq, 4),
            "avg_trades_per_month": round(float(monthly["trades"].mean()), 1),
        },

        "r_distribution": dd_stats,

        "prob_exceed_10pct_monthly": round(prob_exceed_10pct_monthly, 4),
        "r_limit_10pct_account": round(r_limit_10pct, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    import time
    t0 = time.time()
    print("=" * 70)
    print("Financial Planning Extraction")
    print("=" * 70)

    out_dir = Path("research/output/simple_strategies")

    print("\n[0] Loading data...")
    pair_4h = load_and_resample()
    print(f"  {len(pair_4h)} pairs loaded")

    # Run S3 base-cost simulation
    print("\n[1] Running S3 base-cost simulation...")
    all_trades = []
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        trades = simulate_realistic(sig, p, COST_SCENARIOS["base"])
        all_trades.extend(trades)
    print(f"  {len(all_trades)} trades collected")

    # Also run zero-cost and severe-cost
    print("\n[2] Running cost scenarios...")
    zero_trades = []
    severe_trades = []
    for p, df in pair_4h.items():
        sig = generate_signal_mechanism(df)
        zero_trades.extend(simulate_realistic(sig, p, COST_SCENARIOS["zero"]))
        severe_trades.extend(simulate_realistic(sig, p, COST_SCENARIOS["severe"]))

    # Compute financial numbers for each scenario
    results = {}
    for scenario_name, trades in [("zero", zero_trades), ("base", all_trades), ("severe", severe_trades)]:
        print(f"\n[3] Computing financial numbers for {scenario_name}...")
        fin = compute_financial_numbers(trades, account_balance=2500, risk_pct=0.01)
        results[scenario_name] = fin

        print(f"\n{'='*60}")
        print(f"  SCENARIO: {scenario_name.upper()}")
        print(f"{'='*60}")
        print(f"  Total trades: {fin['total_trades']}")
        print(f"  Win rate: {fin['win_rate']:.1%}")
        print(f"  Avg PnL: {fin['avg_pnl_pips']:.2f} pip")
        print(f"  Avg R: {fin['avg_r']:.4f}")
        print(f"  Profit factor: {fin['profit_factor']:.2f}")
        print(f"  Trades/month: {fin['trades_per_month']:.1f}")
        print(f"  Avg risk per trade: {fin['avg_trade_risk_pips']:.2f} pip")
        print()
        print(f"  Monthly EV (pips): {fin['monthly_pip_ev']:.1f}")
        print(f"  Monthly EV (R): {fin['monthly_r_ev']:.2f}")
        print(f"  Monthly EV ($2.5K, 1% risk): ${fin['monthly_dollar_ev']:.2f}")
        print()
        print(f"  Max DD (pips): {fin['max_dd_pips']:.2f}")
        print(f"  Max DD (R): {fin['max_dd_r']:.2f}")
        print(f"  Max DD ($2.5K, 1% risk): ${fin['max_dd_dollar']:.2f}")
        print(f"  Max DD duration: {fin['max_dd_duration_bars']} bars ({fin['max_dd_duration_bars']*4/24:.1f} days)")
        print()
        ms = fin["monthly_stats"]
        print(f"  Monthly stats:")
        print(f"    Months: {ms['n_months']}")
        print(f"    Avg monthly PnL: {ms['avg_monthly_pnl']:.2f} pip")
        print(f"    Median monthly PnL: {ms['median_monthly_pnl']:.2f} pip")
        print(f"    Std monthly PnL: {ms['std_monthly_pnl']:.2f} pip")
        print(f"    Best month: {ms['best_month_pnl']:.2f} pip")
        print(f"    Worst month: {ms['worst_month_pnl']:.2f} pip")
        print(f"    Losing months: {ms['losing_months']}/{ms['n_months']} ({ms['losing_month_freq']:.1%})")
        print()
        rd = fin["r_distribution"]
        print(f"  R distribution:")
        print(f"    Mean: {rd['r_mean']:.4f}")
        print(f"    Std: {rd['r_std']:.4f}")
        print(f"    Median: {rd['r_median']:.4f}")
        print(f"    5th percentile: {rd['r_5th']:.4f}")
        print(f"    25th percentile: {rd['r_25th']:.4f}")
        print(f"    75th percentile: {rd['r_75th']:.4f}")
        print(f"    95th percentile: {rd['r_95th']:.4f}")
        print(f"    Max win streak: {rd['max_win_streak']}")
        print(f"    Max loss streak: {rd['max_loss_streak']}")
        print()
        print(f"  The5ers compatibility ($2.5K, 5% daily / 10% overall):")
        print(f"    1R = ${fin['one_r_dollar']:.2f}")
        print(f"    Max DD in 1R units: {fin['max_dd_r']:.2f}R")
        print(f"    Max DD as % of account: {fin['max_dd_dollar']/2500*100:.2f}%")
        print(f"    10% limit = {fin['r_limit_10pct_account']:.1f}R")
        print(f"    Prob exceed 10% in any month: {fin['prob_exceed_10pct_monthly']:.2%}")

    # Save
    with open(out_dir / "S5_financial_planning.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Complete in {time.time() - t0:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
