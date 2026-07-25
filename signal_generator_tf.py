"""
STRUCTURED ENTRY SIGNAL GENERATOR — TREND FOLLOWING (DONCHIAN BREAKOUT)
======================================================================
Donchian Channel Breakout on 4H bars with ADX trend filter.
Run every 30 minutes during market hours (signals check 4H breakouts).
"""

import pickle
import numpy as np
import pandas as pd
from datetime import datetime, UTC
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from indicators import calculate_adx, calculate_atr

# ── Configuration ─────────────────────────────────────────────────────────────
PAIRS = ['EUR/CHF', 'GBP/USD', 'AUD/JPY', 'EUR/USD', 'USD/CHF', 'GBP/JPY']
TIMEFRAME = '4h'
DONCHIAN_PERIOD = 20        # 20-bar channel on 4H (80 hours)
ADX_THRESHOLD = 25          # Trend strength filter
ATR_PERIOD = 14
ATR_SL_MULT = 2.0           # SL = 2x ATR from entry
ATR_TP_MULT = 3.0           # TP = 3x ATR from entry (RR = 1.5)
ATR_TRAIL_MULT = 1.5        # Trail = 1.5x ATR behind peak
RISK_PER_ENTRY = 0.0075     # 0.75% per entry
ACCOUNT_SIZE = 2500
MAX_HOLD = 30               # 30 x 4H = 5 days
LEVERAGE = 100

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
    except Exception:
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


def calculate_signals(pair, data):
    """Calculate Donchian Channel Breakout signals for a pair."""
    now = datetime.now(UTC)
    ts = pd.Timestamp(now)

    # Session filter
    if not is_good_session(ts):
        return None

    session_quality = calculate_session_quality(ts)
    if session_quality < 0.7:
        return None

    # Resample to 4H
    d = data[["open", "high", "low", "close"]].resample(TIMEFRAME).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna(subset=["close"])

    if len(d) < DONCHIAN_PERIOD + ATR_PERIOD + 10:
        return None

    # Calculate Donchian channels (shifted 1 bar to avoid lookahead)
    donchian_high = d['high'].rolling(DONCHIAN_PERIOD).max().shift(1)
    donchian_low = d['low'].rolling(DONCHIAN_PERIOD).min().shift(1)

    # Calculate ADX and ATR
    adx = calculate_adx(d, ATR_PERIOD)
    atr = calculate_atr(d, ATR_PERIOD)

    # Get current values
    c = d['close'].values[-1]
    dh = donchian_high.values[-1]
    dl = donchian_low.values[-1]
    adx_val = adx.values[-1]
    atr_val = atr.values[-1]

    if np.isnan(dh) or np.isnan(dl) or np.isnan(adx_val) or np.isnan(atr_val):
        return None

    # ADX filter — must be trending
    if adx_val < ADX_THRESHOLD:
        return None

    # Determine signal direction
    if c > dh:
        # BUY: breakout above channel
        entry1 = c
        entry2 = None  # No second entry for breakout
        sl_price = entry1 - ATR_SL_MULT * atr_val
        tp_price = entry1 + ATR_TP_MULT * atr_val
        avg_entry = entry1
        trail_stop = entry1  # Breakeven initially

        risk_amount = ACCOUNT_SIZE * RISK_PER_ENTRY
        risk_dist = avg_entry - sl_price
        units = risk_dist / risk_dist if risk_dist > 0 else 0

        return {
            'pair': pair,
            'trend': 'BULLISH',
            'strategy': 'DCB',
            'entry1': entry1,
            'entry2': entry2,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'avg_entry': avg_entry,
            'early_exit': None,
            'trail_stop': trail_stop,
            'atr_value': atr_val,
            'donchian_high': dh,
            'donchian_low': dl,
            'adx_value': adx_val,
            'units': units,
            'units_note': 'raw notional in base ccy; engine applies leverage-aware sizing',
            'risk_amount': risk_amount,
            'rr_target': ATR_TP_MULT / ATR_SL_MULT,
            'max_hold': MAX_HOLD,
            'session_quality': session_quality,
            'session': 'London/NY Overlap' if 12 <= ts.hour < 16 else 'London' if 7 <= ts.hour < 12 else 'New York',
        }

    elif c < dl:
        # SELL: breakout below channel
        entry1 = c
        entry2 = None
        sl_price = entry1 + ATR_SL_MULT * atr_val
        tp_price = entry1 - ATR_TP_MULT * atr_val
        avg_entry = entry1
        trail_stop = entry1

        risk_amount = ACCOUNT_SIZE * RISK_PER_ENTRY
        risk_dist = sl_price - avg_entry
        units = risk_dist / risk_dist if risk_dist > 0 else 0

        return {
            'pair': pair,
            'trend': 'BEARISH',
            'strategy': 'DCB',
            'entry1': entry1,
            'entry2': entry2,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'avg_entry': avg_entry,
            'early_exit': None,
            'trail_stop': trail_stop,
            'atr_value': atr_val,
            'donchian_high': dh,
            'donchian_low': dl,
            'adx_value': adx_val,
            'units': units,
            'units_note': 'raw notional in base ccy; engine applies leverage-aware sizing',
            'risk_amount': risk_amount,
            'rr_target': ATR_TP_MULT / ATR_SL_MULT,
            'max_hold': MAX_HOLD,
            'session_quality': session_quality,
            'session': 'London/NY Overlap' if 12 <= ts.hour < 16 else 'London' if 7 <= ts.hour < 12 else 'New York',
        }

    return None


def main():
    print("=" * 80)
    print("  DONCHIAN CHANNEL BREAKOUT — TREND FOLLOWING SIGNAL GENERATOR")
    print("=" * 80)
    print(f"  Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Account: ${ACCOUNT_SIZE:,.0f}")
    print(f"  Risk per Entry: {RISK_PER_ENTRY*100:.2f}%")
    print(f"  Donchian Period: {DONCHIAN_PERIOD} bars (4H)")
    print(f"  ADX Threshold: {ADX_THRESHOLD}")
    print(f"  SL: {ATR_SL_MULT}x ATR   TP: {ATR_TP_MULT}x ATR   RR: {ATR_TP_MULT/ATR_SL_MULT:.1f}")
    print(f"  Trail: {ATR_TRAIL_MULT}x ATR")
    print(f"  Max Hold: {MAX_HOLD} bars ({MAX_HOLD * 4} hours)")
    print(f"  Filters: Session + ADX + Donchian Breakout")
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
            print(f"    Entry: {signal['entry1']:.5f}")
            print(f"    Stop Loss: {signal['sl_price']:.5f}")
            print(f"    Take Profit: {signal['tp_price']:.5f}")
            print(f"    Trail Stop: {signal['trail_stop']:.5f}")
            print(f"    ATR: {signal['atr_value']:.5f}")
            print(f"    Donchian High: {signal['donchian_high']:.5f}")
            print(f"    Donchian Low: {signal['donchian_low']:.5f}")
            print(f"    ADX: {signal['adx_value']:.1f}")
            print(f"    Risk: ${signal['risk_amount']:.2f}")
            print(f"    RR: {signal['rr_target']:.1f}")
            print(f"    Session Quality: {signal['session_quality']:.1f}")
            print()

    if not signals:
        print("  No signals — waiting for breakout + ADX confirmation + session")

    # Save signals
    signals_file = f"signals_tf_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.json"

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
            'version': 'tf_v1',
            'strategy': 'DCB',
            'account_size': ACCOUNT_SIZE,
            'risk_per_entry': RISK_PER_ENTRY,
            'donchian_period': DONCHIAN_PERIOD,
            'adx_threshold': ADX_THRESHOLD,
            'atr_sl_mult': ATR_SL_MULT,
            'atr_tp_mult': ATR_TP_MULT,
            'atr_trail_mult': ATR_TRAIL_MULT,
            'rr_target': ATR_TP_MULT / ATR_SL_MULT,
            'filters': ['session', 'adx', 'donchian_breakout'],
            'pairs': PAIRS,
            'signals': _json_safe(signals)
        }, f, indent=2)

    print(f"  Signals saved to: {signals_file}")


if __name__ == "__main__":
    main()
