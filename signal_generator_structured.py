"""
STRUCTURED ENTRY SIGNAL GENERATOR v2
=====================================
RR=2.7, Daily Filter, 20 Pairs, 2.00% Risk per Entry.
Run every 30 minutes during market hours.
"""

import pickle
import numpy as np
import pandas as pd
from datetime import datetime, UTC
import json

# ── Configuration ─────────────────────────────────────────────────────────────
PAIRS = [
    'EUR/CHF', 'GBP/USD', 'AUD/JPY', 'EUR/USD', 'USD/CHF', 'GBP/JPY',
    'USD/JPY', 'AUD/USD', 'NZD/USD', 'EUR/GBP', 'CAD/JPY', 'AUD/CAD',
    'GBP/AUD', 'EUR/AUD', 'NZD/JPY', 'EUR/CAD', 'GBP/CAD', 'AUD/CHF',
    'NZD/CHF', 'CAD/CHF',
]
TIMEFRAME = '30min'
EMA_PERIOD = 200
EMA_50_PERIOD = 50
PULLBACK_PCT = 0.005  # 0.5% pullback zone
SL_BUFFER = 0.005     # 0.5% SL beyond EMA
RR_TARGET = 2.7       # Risk:Reward ratio
RISK_PER_ENTRY = 0.020  # 2.00% per entry (2 entries = 4.00% total)
ACCOUNT_SIZE = 2500   # 5ers account
MAX_HOLD = 50         # Max bars to hold (25 hours)

# Session Filter (UTC)
SESSIONS = {
    'london': (7, 16),
    'new_york': (12, 21),
    'overlap': (12, 16),
}
TRADE_SESSIONS = ['london', 'new_york']
SKIP_FRIDAY_AFTER = 20
SKIP_MONDAY_BEFORE = 3


def pip_size(pair):
    return 0.01 if "JPY" in pair else 0.0001


def load_pair(pair):
    pk = pair.replace("/", "_")
    path = f"/root/data/{pk}.pkl"
    try:
        with open(path, "rb") as f:
            raw = pickle.load(f)
        df = raw.get(pair)
        if df is None or df.empty:
            return None
        idx = pd.to_datetime(df.index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")
        df.index = idx
        return df
    except:
        return None


def is_good_session(ts):
    hour = ts.hour
    day = ts.dayofweek

    if day == 4 and hour >= SKIP_FRIDAY_AFTER:
        return False
    if day == 0 and hour < SKIP_MONDAY_BEFORE:
        return False
    if day == 6:
        return False

    for session_name in TRADE_SESSIONS:
        start, end = SESSIONS[session_name]
        if start <= hour < end:
            return True
    return False


def calculate_session_quality(ts):
    hour = ts.hour
    if 12 <= hour < 16:
        return 1.0  # London/NY overlap
    elif 7 <= hour < 12:
        return 0.8  # London only
    elif 16 <= hour < 21:
        return 0.7  # New York only
    else:
        return 0.5


def check_daily_filter(data, ts):
    """
    Check if yesterday's daily candle aligns with trade direction.
    Returns: 1 = bullish day, -1 = bearish day, 0 = no data
    """
    try:
        daily = data[["open", "high", "low", "close"]].resample('1D').agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["close"])

        d_ts = daily.index.asof(ts)
        if d_ts not in daily.index:
            return 0

        daily_open = daily.loc[d_ts, 'open']
        daily_close = daily.loc[d_ts, 'close']

        if daily_close > daily_open:
            return 1   # Bullish candle
        elif daily_close < daily_open:
            return -1  # Bearish candle
        else:
            return 0   # Doji
    except:
        return 0


def check_swing_filter(data, ts, trend, lookback=20):
    """
    Check if price recently pulled back (swing against trend).
    Returns True if pullback detected.
    """
    try:
        d30 = data[["open", "high", "low", "close"]].resample('30min').agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["close"])

        c = d30['close'].values
        h = d30['high'].values
        lo = d30['low'].values
        ts_arr = d30.index

        # Find current index
        idx = ts_arr.searchsorted(ts)
        if idx >= len(c) or idx < lookback:
            return False

        price = c[idx]

        if trend == 1:
            # For longs: price must have been higher recently (pullback from high)
            recent_high = max(h[max(0, idx - lookback):idx])
            return recent_high > price * 1.002
        else:
            # For shorts: price must have been lower recently (pullback from low)
            recent_low = min(lo[max(0, idx - lookback):idx])
            return recent_low < price * 0.998
    except:
        return False


def calculate_signals(pair, data):
    """Calculate trading signals for Structured Entry v2."""
    now = datetime.now(UTC)
    ts = pd.Timestamp(now)

    # Session filter
    if not is_good_session(ts):
        return None

    session_quality = calculate_session_quality(ts)
    if session_quality < 0.7:
        return None

    # Resample to 30min
    d = data[["open", "high", "low", "close"]].resample(TIMEFRAME).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna(subset=["close"])

    # Resample to 4H for EMAs
    d_high = data[["open", "high", "low", "close"]].resample('4h').agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna(subset=["close"])

    # Calculate EMAs
    ema_200 = d_high['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    ema_200_aligned = ema_200.reindex(d.index, method='ffill')

    ema_50 = d_high['close'].ewm(span=EMA_50_PERIOD, adjust=False).mean()
    ema_50_aligned = ema_50.reindex(d.index, method='ffill')

    # Get current values
    c = d['close'].values[-1]
    ema_val = ema_200_aligned.values[-1]
    ema_50_val = ema_50_aligned.values[-1]

    if np.isnan(ema_val) or np.isnan(ema_50_val):
        return None

    # Determine trend
    trend = 1 if c > ema_val else -1

    # Trend filter with 50 EMA
    if trend == 1 and c < ema_50_val * 0.998:
        return None
    if trend == -1 and c > ema_50_val * 1.002:
        return None

    # Daily filter: check yesterday's candle
    daily_dir = check_daily_filter(data, ts)
    if daily_dir == 0:
        return None
    if trend == 1 and daily_dir != 1:
        return None  # Only long on bullish daily
    if trend == -1 and daily_dir != -1:
        return None  # Only short on bearish daily

    # Swing filter: must have pulled back recently
    if not check_swing_filter(data, ts, trend):
        return None

    # Check for pullback zone
    if trend == 1:
        if not (c < ema_val * (1 + PULLBACK_PCT) and c > ema_val * (1 - PULLBACK_PCT)):
            return None

        # Calculate entry levels (2-entry system)
        entry1 = c
        entry2 = entry1 * (1 - PULLBACK_PCT * 0.5)

        # SL below EMA, TP = entry + RR * (entry - SL)
        sl_price = ema_val * (1 - SL_BUFFER)
        tp_price = entry1 + (entry1 - sl_price) * RR_TARGET

        # Position sizing
        risk_amount = ACCOUNT_SIZE * RISK_PER_ENTRY
        avg_entry = (entry1 + entry2) / 2
        risk_dist = avg_entry - sl_price
        units = risk_amount / risk_dist if risk_dist > 0 else 0

        return {
            'pair': pair,
            'trend': 'BULLISH',
            'entry1': entry1,
            'entry2': entry2,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'avg_entry': avg_entry,
            'units': units,            # raw base-ccy units (risk_amount / sl_distance)
            'units_note': 'raw notional in base ccy; engine applies leverage-aware sizing',
            'risk_amount': risk_amount,
            'ema_200': ema_val,
            'ema_50': ema_50_val,
            'rr_target': RR_TARGET,
            'session_quality': session_quality,
            'session': 'London/NY Overlap' if 12 <= ts.hour < 16 else 'London' if 7 <= ts.hour < 12 else 'New York',
            'daily_filter': 'Active',
            'swing_filter': 'Active',
        }

    else:  # Bearish
        if not (c > ema_val * (1 - PULLBACK_PCT) and c < ema_val * (1 + PULLBACK_PCT)):
            return None

        entry1 = c
        entry2 = entry1 * (1 + PULLBACK_PCT * 0.5)

        sl_price = ema_val * (1 + SL_BUFFER)
        tp_price = entry1 - (sl_price - entry1) * RR_TARGET

        risk_amount = ACCOUNT_SIZE * RISK_PER_ENTRY
        avg_entry = (entry1 + entry2) / 2
        risk_dist = sl_price - avg_entry
        units = risk_amount / risk_dist if risk_dist > 0 else 0

        return {
            'pair': pair,
            'trend': 'BEARISH',
            'entry1': entry1,
            'entry2': entry2,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'avg_entry': avg_entry,
            'units': units,            # raw base-ccy units (risk_amount / sl_distance)
            'units_note': 'raw notional in base ccy; engine applies leverage-aware sizing',
            'risk_amount': risk_amount,
            'ema_200': ema_val,
            'ema_50': ema_50_val,
            'rr_target': RR_TARGET,
            'session_quality': session_quality,
            'session': 'London/NY Overlap' if 12 <= ts.hour < 16 else 'London' if 7 <= ts.hour < 12 else 'New York',
            'daily_filter': 'Active',
            'swing_filter': 'Active',
        }

    return None


def main():
    print("=" * 80)
    print("  STRUCTURED ENTRY SIGNAL GENERATOR v2")
    print("=" * 80)
    print(f"  Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Account: ${ACCOUNT_SIZE:,.0f}")
    print(f"  Risk per Entry: {RISK_PER_ENTRY*100:.2f}%")
    print(f"  Total Risk (2 entries): {RISK_PER_ENTRY*2*100:.2f}%")
    print(f"  RR Target: {RR_TARGET}")
    print(f"  Filters: Session + Daily + Swing + EMA")
    print(f"  Pairs: {', '.join(PAIRS)}")
    print()

    now = datetime.now(UTC)
    ts = pd.Timestamp(now)

    if not is_good_session(ts):
        print("  WARNING: Current time is NOT in a tradable session!")
        print(f"  Trading Hours: London (07:00-16:00 UTC) + New York (12:00-21:00 UTC)")
        print()

    signals = []

    for pair in PAIRS:
        data = load_pair(pair)
        if data is None:
            print(f"  {pair}: No data")
            continue

        signal = calculate_signals(pair, data)
        if signal is not None:
            signals.append(signal)
            print(f"  {pair}: {signal['trend']} ({signal['session']})")
            print(f"    Entry 1: {signal['entry1']:.5f}")
            print(f"    Entry 2: {signal['entry2']:.5f}")
            print(f"    Stop Loss: {signal['sl_price']:.5f}")
            print(f"    Take Profit: {signal['tp_price']:.5f}")
            print(f"    Avg Entry: {signal['avg_entry']:.5f}")
            print(f"    Units: {signal['units']:.4f}")
            print(f"    Risk: ${signal['risk_amount']:.2f}")
            print(f"    RR: {signal['rr_target']}")
            print(f"    Session Quality: {signal['session_quality']:.1f}")
            print()

    if not signals:
        print("  No signals - waiting for pullback, daily alignment, or session")

    # Save signals
    signals_file = f"signals_structured_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.json"

    def _json_safe(obj):
        if isinstance(obj, dict):
            return {k: _json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [_json_safe(v) for v in obj]
        elif isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        else:
            return obj

    with open(signals_file, 'w') as f:
        json.dump({
            'date': datetime.now(UTC).isoformat(),
            'version': 'v2',
            'account_size': ACCOUNT_SIZE,
            'risk_per_entry': RISK_PER_ENTRY,
            'rr_target': RR_TARGET,
            'filters': ['session', 'daily', 'swing', 'ema'],
            'pairs': PAIRS,
            'session_filter': 'Active',
            'daily_filter': 'Active',
            'swing_filter': 'Active',
            'signals': _json_safe(signals)
        }, f, indent=2)

    print(f"  Signals saved to: {signals_file}")


if __name__ == "__main__":
    main()
