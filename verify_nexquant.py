"""
Verify NexQuant MACD(3,10,3) 4-TF 2/4 vote strategy on our data.
Adapted from: nexquant_rd_loop.py + nexquant_priceaction_loop.py
"""
import numpy as np
import pandas as pd
import pickle
import talib
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# NexQuant backtest engine (from rdagent/components/backtesting/vbt_backtest.py)
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_TXN_COST_BPS = 2.14  # 1.5 pip spread + 0.5 slippage + 0.35 commission
DEFAULT_BARS_PER_YEAR = 252 * 1440  # 1-min convention

def backtest_signal(close, signal, txn_cost_bps=DEFAULT_TXN_COST_BPS, bars_per_year=DEFAULT_BARS_PER_YEAR):
    close = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    signal = pd.to_numeric(signal, errors="coerce").reindex(close.index).fillna(0).clip(-1, 1).astype(float)
    position = signal.shift(1).fillna(0)
    bar_ret = close.pct_change().fillna(0)
    txn_cost = txn_cost_bps / 10_000.0
    position_change = position.diff().abs().fillna(position.abs())
    gross_ret = position * bar_ret
    strategy_returns = gross_ret - position_change * txn_cost

    if strategy_returns.std() > 0:
        sharpe = float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(bars_per_year))
    else:
        sharpe = 0.0

    downside = strategy_returns[strategy_returns < 0]
    if len(downside) > 1 and downside.std() > 0:
        sortino = float(strategy_returns.mean() / downside.std() * np.sqrt(bars_per_year))
    else:
        sortino = 0.0

    total_return = float((1 + strategy_returns).prod() - 1)
    equity = (1 + strategy_returns).cumprod()
    running_max = equity.cummax()
    running_max_safe = running_max.where(running_max > 0, np.nan)
    drawdown = (equity - running_max) / running_max_safe
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0)
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    if isinstance(close.index, pd.DatetimeIndex) and len(close.index) > 1:
        span_days = (close.index[-1] - close.index[0]).total_seconds() / 86400.0
        n_months = max(1.0, span_days / 30.4375)
    else:
        n_months = max(1.0, len(strategy_returns) / (bars_per_year / 12))

    monthly_return = (1 + total_return) ** (1 / n_months) - 1 if n_months > 0 and (1 + total_return) > 0 else 0.0

    # Trade counting
    position_sign = np.sign(position).astype(int)
    epoch = (position_sign != position_sign.shift(1)).cumsum()
    epoch_sign = position_sign.groupby(epoch).first()
    trade_pnl = strategy_returns.groupby(epoch).sum()
    trades = trade_pnl[epoch_sign != 0]
    n_trades = len(trades)
    wins = (trades > 0).sum()
    win_rate = wins / n_trades if n_trades > 0 else 0.0

    gross_wins = trades[trades > 0].sum()
    gross_losses = abs(trades[trades < 0].sum())
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else 999.0

    return {
        "sharpe": sharpe, "sortino": sortino,
        "total_return": total_return, "monthly_return_pct": monthly_return * 100,
        "max_drawdown": max_dd, "n_trades": n_trades,
        "win_rate": win_rate, "profit_factor": profit_factor,
        "n_months": n_months,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NexQuant MACD(3,10,3) strategy (from nexquant_priceaction_loop.py)
# ═══════════════════════════════════════════════════════════════════════════════
VOTE_THRESHOLD = 0.25

def _macd_signal(close_series, fast=3, slow=10, sig=3):
    """MACD signal: +1 when MACD > signal, -1 when MACD < signal."""
    c = close_series.values.astype(np.float64)
    mc, sc, _ = talib.MACD(c, fastperiod=fast, slowperiod=slow, signalperiod=sig)
    s = pd.Series(0, index=close_series.index)
    s[mc > sc] = 1
    s[mc < sc] = -1
    return s.fillna(0).astype(int).clip(-1, 1)


def build_macd_4tf_signal(close_1min):
    """MACD(3,10,3) on 4 timeframes with 2/4 vote majority."""
    timeframes = ["15min", "30min", "1h", "4h"]
    sigs = {}
    for tf in timeframes:
        bars = close_1min.resample(tf).last().dropna()
        sig = _macd_signal(bars, fast=3, slow=10, sig=3)
        sigs[tf] = sig.reindex(close_1min.index).ffill().fillna(0).astype(int).clip(-1, 1)
    port = pd.DataFrame(sigs).dropna()
    vote = port.mean(axis=1)
    signal = pd.Series(0, index=close_1min.index)
    signal[vote > VOTE_THRESHOLD] = 1
    signal[vote < -VOTE_THRESHOLD] = -1
    return signal


def apply_session_filter(signal, index):
    """Only trade London session (07:00-16:00 UTC Mon-Fri)."""
    hours = index.hour
    days = index.dayofweek
    in_session = (days < 5) & (hours >= 7) & (hours < 16)
    return (signal * in_session.astype(int)).astype(int).clip(-1, 1)


def apply_volatility_filter(signal, close, atr_period=14, min_atr_pct=0.0003):
    """Don't trade when ATR is too low."""
    tr = pd.DataFrame({
        'hl': close.diff().abs(),
        'hc': (close - close.shift(1)).abs(),
        'lc': (close.shift(1) - close).abs(),
    }).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    atr_pct = atr / close
    too_quiet = atr_pct < min_atr_pct
    return (signal * (~too_quiet).astype(int)).fillna(0).astype(int).clip(-1, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════════
def load_eurusd():
    """Load EUR/USD 1min data from pickle files or yfinance."""
    # Try our pickle files first
    pkls = [
        "/root/data/EUR_USD.pkl",
        "/root/data/EURUSD.pkl",
    ]
    for p in pkls:
        if Path(p).exists():
            with open(p, "rb") as f:
                raw = pickle.load(f)
            df = raw.get("EUR/USD")
            if df is None:
                df = raw.get("EURUSD")
            if df is not None and len(df) > 1000:
                idx = pd.to_datetime(df.index)
                idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
                df.index = idx
                return df["close"].sort_index()

    # Fallback: yfinance
    import yfinance as yf
    print("  Downloading EUR/USD from yfinance (this may take a moment)...")
    df = yf.download("EURUSD=X", period="2y", interval="1m", progress=False)
    if df.empty:
        df = yf.download("EURUSD=X", period="60d", interval="5m", progress=False)
    return df["Close"].dropna().sort_index()


# ═══════════════════════════════════════════════════════════════════════════════
# Main verification
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("  NexQuant MACD(3,10,3) 4-TF 2/4 Vote Strategy — VERIFICATION")
    print("=" * 70)

    close = load_eurusd()
    print(f"\n  Data: EUR/USD {len(close)} bars")
    print(f"  Period: {close.index[0]} → {close.index[-1]}")
    print(f"  Timeframe: ~{(close.index[-1]-close.index[0]).days} days")

    # Detect frequency
    median_delta = (close.index[1:] - close.index[:-1]).median()
    print(f"  Median bar: {median_delta}")

    # Adapt bars_per_year to actual frequency
    bars_per_min = median_delta.total_seconds() / 60.0
    if bars_per_min <= 1.5:
        freq_label = "1min"
        bars_per_year = 252 * 1440
    elif bars_per_min <= 5.5:
        freq_label = "5min"
        bars_per_year = 252 * 288
    elif bars_per_min <= 15.5:
        freq_label = "15min"
        bars_per_year = 252 * 96
    elif bars_per_min <= 30.5:
        freq_label = "30min"
        bars_per_year = 252 * 48
    else:
        freq_label = "1h"
        bars_per_year = 252 * 24

    print(f"  Detected freq: {freq_label} (bars_per_year={bars_per_year})")

    # Build signals
    print("\n  Building MACD(3,10,3) 4-TF signal...")
    signal_raw = build_macd_4tf_signal(close)
    signal_session = apply_session_filter(signal_raw, close.index)
    signal_filtered = apply_volatility_filter(signal_session, close)

    long_pct = (signal_raw == 1).mean() * 100
    short_pct = (signal_raw == -1).mean() * 100
    neutral_pct = (signal_raw == 0).mean() * 100
    print(f"  Raw signal: {long_pct:.1f}% long, {short_pct:.1f}% short, {neutral_pct:.1f}% neutral")

    # Run backtests
    print("\n  Running backtests...")

    results = {}
    for label, sig in [("Raw", signal_raw), ("Session Filter", signal_session), ("Session+Vol Filter", signal_filtered)]:
        r = backtest_signal(close, sig, bars_per_year=bars_per_year)
        results[label] = r
        print(f"\n  [{label}]")
        print(f"    Sharpe:     {r['sharpe']:.2f}")
        print(f"    Sortino:    {r['sortino']:.2f}")
        print(f"    Total:      {r['total_return']*100:.1f}%")
        print(f"    Monthly:    {r['monthly_return_pct']:.2f}%")
        print(f"    Max DD:     {r['max_drawdown']*100:.2f}%")
        print(f"    Trades:     {r['n_trades']}")
        print(f"    Win Rate:   {r['win_rate']*100:.1f}%")
        print(f"    PF:         {r['profit_factor']:.2f}")
        print(f"    Period:     {r['n_months']:.1f} months")

    # Also test with our existing pickle data if available
    print("\n" + "=" * 70)
    print("  TESTING ON ALL 12 PAIRS (same as our MR+TF strategy)")
    print("=" * 70)

    PAIR_FILES = {'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF',
                  'AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF',
                  'EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}

    pair_results = []
    for pair, fname in PAIR_FILES.items():
        pkl_path = f"/root/data/{fname}.pkl"
        if not Path(pkl_path).exists():
            continue
        try:
            with open(pkl_path, "rb") as f:
                raw = pickle.load(f)
            df = raw.get(pair)
            if df is None or len(df) < 5000:
                continue
            idx = pd.to_datetime(df.index)
            idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
            df.index = idx
            px = df["close"].sort_index()

            sig = build_macd_4tf_signal(px)
            sig = apply_session_filter(sig, px.index)
            sig = apply_volatility_filter(sig, px)

            median_d = (px.index[1:] - px.index[:-1]).median()
            bpd = median_d.total_seconds() / 60.0
            if bpd <= 1.5: bpy = 252*1440
            elif bpd <= 5.5: bpy = 252*288
            elif bpd <= 15.5: bpy = 252*96
            elif bpd <= 30.5: bpy = 252*48
            else: bpy = 252*24

            r = backtest_signal(px, sig, bars_per_year=bpy)
            r["pair"] = pair
            pair_results.append(r)
        except Exception as e:
            print(f"  {pair}: ERROR {e}")

    if pair_results:
        print(f"\n  {'Pair':<12} {'Sharpe':>7} {'Monthly%':>9} {'MaxDD%':>7} {'WR%':>6} {'PF':>5} {'Trades':>7}")
        print("  " + "-" * 60)
        for r in sorted(pair_results, key=lambda x: x["sharpe"], reverse=True):
            print(f"  {r['pair']:<12} {r['sharpe']:>7.2f} {r['monthly_return_pct']:>8.2f}% "
                  f"{r['max_drawdown']*100:>6.2f}% {r['win_rate']*100:>5.1f}% "
                  f"{r['profit_factor']:>5.2f} {r['n_trades']:>7}")

        # Portfolio average
        avg_sh = np.mean([r["sharpe"] for r in pair_results])
        avg_mo = np.mean([r["monthly_return_pct"] for r in pair_results])
        avg_dd = np.mean([r["max_drawdown"] for r in pair_results])
        avg_wr = np.mean([r["win_rate"] for r in pair_results])
        avg_pf = np.mean([r["profit_factor"] for r in pair_results])
        print(f"\n  AVERAGE: Sharpe={avg_sh:.2f} Monthly={avg_mo:.2f}% DD={avg_dd*100:.2f}% WR={avg_wr*100:.1f}% PF={avg_pf:.2f}")

    # Constraint check
    best = results.get("Session+Vol Filter", results.get("Raw"))
    if best:
        print("\n" + "=" * 70)
        print("  CONSTRAINT CHECK (25% monthly, <10% DD)")
        print("=" * 70)
        ok_m = "PASS" if best["monthly_return_pct"] >= 25 else "FAIL"
        ok_d = "PASS" if abs(best["max_drawdown"]) < 0.10 else "FAIL"
        ok_b = "PASS" if best["monthly_return_pct"] >= 25 and abs(best["max_drawdown"]) < 0.10 else "FAIL"
        print(f"  Monthly: {best['monthly_return_pct']:.2f}% [{ok_m}]")
        print(f"  DD:      {abs(best['max_drawdown'])*100:.2f}% [{ok_d}]")
        print(f"  BOTH:    [{ok_b}]")
