"""Phase 8 — Fast vs Slow Mean-Reversion Discovery.

Research hypothesis (H8):
At the moment an extreme Z-score displacement occurs, information available
at that moment contains statistically significant information that
distinguishes FAST mean reversion from SLOW mean reversion.

This script:
1. Extracts extreme-Z events with entry-available features only
2. Creates outcome labels using future Z behavior
3. Tests whether entry features discriminate FAST vs SLOW outcomes
4. Applies adversarial validation (permutation, FDR, temporal, cross-pair)

Usage: cd /root/nestquant && .venv/bin/python -u scripts/phase8_fast_slow_discovery.py
"""
from __future__ import annotations

import json, pickle, sys, time, warnings, hashlib
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from zscore.zscore import compute_zscore_causal

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════
Z_ENTRY = 2.2
LOOKBACK = 20
ATR_PERIOD = 14
ATR_SL_MULT = 3.0
MAX_HOLD_BARS = 64
COMMISSION = 3.50
SLIPPAGE_PIPS = 0.3
SESSIONS = {"london": (7, 16), "new_york": (12, 21)}
SKIP_FRI = 20
SKIP_MON = 3
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "NZD/USD",
    "EUR/GBP", "EUR/CHF", "EUR/JPY", "AUD/JPY", "EUR/AUD", "AUD/CAD",
    "GBP/JPY", "GBP/CAD", "GBP/AUD", "CAD/JPY", "NZD/JPY", "NZD/CHF",
    "AUD/CHF", "CAD/CHF",
]
SPREAD = {
    "EUR/USD": 0.8, "GBP/USD": 1.0, "USD/JPY": 1.0, "USD/CHF": 1.2,
    "AUD/USD": 0.9, "NZD/USD": 1.2, "EUR/GBP": 1.2, "EUR/CHF": 1.5,
    "EUR/JPY": 2.0, "GBP/JPY": 3.0, "AUD/JPY": 2.0, "CAD/JPY": 2.5,
    "NZD/JPY": 3.0, "EUR/AUD": 2.0, "EUR/CAD": 2.5, "GBP/AUD": 3.5,
    "GBP/CAD": 3.5, "AUD/CAD": 2.0, "AUD/CHF": 2.5, "NZD/CHF": 3.0,
    "CAD/CHF": 3.0,
}
DEFAULT_USD = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.26, "JPY": 0.0067,
    "CHF": 0.88, "AUD": 0.65, "CAD": 0.74, "NZD": 0.60,
}

OUT = Path("/root/nestquant/research_data/phase8")
OUT.mkdir(parents=True, exist_ok=True)

# Permutation seed for reproducibility
RNG_SEED = 42
N_PERM = 500
N_BOOT = 500

# Outcome label horizons
FAST_HORIZON = 4  # bars
SLOW_HORIZON = 16  # bars
FAST_THRESHOLD = 0.50  # 50% recovery
SLOW_THRESHOLD = 0.30  # 30% recovery

# Held-out pairs for cross-pair validation
HELDOUT_GROUPS = [
    ["CAD/JPY", "NZD/JPY", "NZD/CHF", "AUD/CHF", "CAD/CHF"],
    ["EUR/AUD", "AUD/CAD", "GBP/JPY", "GBP/CAD", "GBP/AUD"],
    ["NZD/USD", "EUR/GBP", "EUR/CHF", "EUR/JPY", "AUD/JPY"],
    ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD"],
    ["CAD/JPY", "NZD/JPY", "NZD/CHF", "AUD/CHF", "CAD/CHF"],
]

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def in_session(ts):
    h, d = ts.hour, ts.dayofweek
    if d == 4 and h >= SKIP_FRI:
        return False
    if d == 0 and h < SKIP_MON:
        return False
    if d >= 5:
        return False
    return any(s <= h < e for s, e in SESSIONS.values())


def get_session(ts):
    h, d = ts.hour, ts.dayofweek
    if d >= 5 or (d == 4 and h >= SKIP_FRI) or (d == 0 and h < SKIP_MON):
        return "none"
    in_london = 7 <= h < 16
    in_ny = 12 <= h < 21
    if in_london and in_ny:
        return "overlap"
    if in_london:
        return "london_only"
    if in_ny:
        return "ny_only"
    return "none"


def pip_size(pair):
    return 0.01 if "JPY" in pair else 0.0001


def pip_value(pair):
    base, quote = pair.split("/")
    return pip_size(pair) * 100000 * DEFAULT_USD.get(quote, 1.0)


def causal_percentile(arr, current_idx, value, window):
    """Percentile of value within arr[current_idx-window:current_idx+1]."""
    start = max(0, current_idx - window)
    window_vals = arr[start:current_idx + 1]
    valid = window_vals[~np.isnan(window_vals)]
    if len(valid) < 10:
        return 50.0
    return float(np.mean(valid <= value)) * 100


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_all(start, end):
    """Load and preprocess all pairs. Returns dict of pair data."""
    pdata = {}
    for pair in PAIRS:
        try:
            with open(f"/root/data/{pair.replace('/', '_')}.pkl", "rb") as f:
                raw = pickle.load(f)
        except Exception:
            continue
        df = raw.get(pair)
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df.index = idx
        df = df[(df.index >= start) & (df.index <= end)]
        if len(df) < 500:
            continue
        df = df[["open", "high", "low", "close", "volume"]].resample("30min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna(subset=["close"])
        if len(df) < 500:
            continue
        c = df["close"].values.astype(np.float64)
        obs = compute_zscore_causal(c, df.index, pair, lookback=LOOKBACK)
        z = np.array([o.z_score for o in obs])
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean().values
        atr_pct = atr / df["close"].values * 100
        ema200 = df["close"].ewm(span=200, adjust=False).mean().values
        ema50 = df["close"].ewm(span=50, adjust=False).mean().values
        ema20 = df["close"].ewm(span=20, adjust=False).mean().values
        vol = df["volume"].values.astype(np.float64)
        pdata[pair] = {
            "c": c, "h": df["high"].values, "lo": df["low"].values,
            "o": df["open"].values, "ts": df.index, "n": len(df),
            "z": z, "atr": atr, "atr_pct": atr_pct,
            "ema200": ema200, "ema50": ema50, "ema20": ema20,
            "vol": vol, "bar_range": df["high"].values - df["low"].values,
            "pip": pip_size(pair), "pv": pip_value(pair),
            "spread": SPREAD.get(pair, 2.0),
        }
    return pdata


# ═══════════════════════════════════════════════════════════════
# EVENT EXTRACTION + FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════

@dataclass
class Phase8Event:
    """A single extreme-Z event with entry-available features and outcome label."""
    pair: str
    direction: int  # 1=long, -1=short
    entry_price: float
    entry_z: float
    abs_z: float
    entry_ts: pd.Timestamp
    entry_bar: int
    year: int
    month: str
    entry_hour: int
    entry_dow: int
    session: str

    # Outcome labels (FUTURE-BASED, never used as features)
    outcome: str  # fast_mr, slow_mr, continuation, ambiguous
    z_at_4: float
    z_at_8: float
    z_at_16: float
    fwd_return_4: float  # pip-based forward return at 4 bars

    # ── Family A: Z / Extremeness (entry-available) ──
    signed_z: float
    z_pctile_200: float  # percentile within last 200 bars
    z_pctile_500: float
    z_pctile_1000: float
    z_pctile_2000: float
    dist_from_recent_max_z: float  # distance from max |Z| in last 50 bars
    dist_from_recent_min_z: float
    z_was_beyond_count: int  # bars where |Z| was higher in last 20 bars
    z_moving_toward_zero: int  # 1 if dz_1 moves toward 0
    dz_1: float  # Z change over 1 bar
    dz_2: float  # Z change over 2 bars
    dz_4: float  # Z change over 4 bars
    z_accel: float  # acceleration (second difference)

    # ── Family B: Price / Return Structure ──
    ret_1: float  # 1-bar return
    ret_2: float  # 2-bar return
    ret_4: float  # 4-bar return
    ret_8: float  # 8-bar return
    ret_16: float  # 16-bar return
    abs_ret_1: float
    abs_ret_4: float
    consec_direction: int  # consecutive bars in same direction
    body_range_ratio: float  # body / range
    upper_wick_ratio: float  # upper wick / range
    lower_wick_ratio: float  # lower wick / range
    dist_from_52h_high: float  # distance from 52-bar high (in pips)
    dist_from_52h_low: float
    range_position: float  # (close - low_20) / (high_20 - low_20)
    range_expansion: float  # current bar range / avg range last 20
    price_displacement_atr: float  # (close - ema200) / ATR

    # ── Family C: Volatility ──
    atr_now: float
    atr_pctile_200: float
    atr_pctile_500: float
    atr_pctile_1000: float
    realized_vol_20: float  # 20-bar realized vol
    realized_vol_pctile_500: float
    vol_expansion_ratio: float  # short-term vol / long-term vol
    range_pctile_500: float  # bar range percentile

    # ── Family D: Trend / Market Structure ──
    ema_dist_200: float  # (close - ema200) / ema200 * 100
    ema_dist_50: float
    ema_dist_20: float
    ema_slope_200: float  # slope of ema200 over 10 bars
    ema_slope_50: float
    ema_cross_20_50: float  # 1 if ema20 > ema50, -1 otherwise
    ema_cross_50_200: float
    trend_return_20: float  # return over last 20 bars
    trend_persistence: float  # fraction of last 20 bars in trend direction
    adx_approx: float  # approximate ADX (directional strength)

    # ── Family E: Volume / Activity ──
    vol_now: float
    vol_pctile_200: float
    vol_pctile_500: float
    vol_expansion: float  # vol_now / avg_vol_20
    vol_price_corr_20: float  # correlation of volume with |return| over 20 bars

    # ── Family F: Cross-Pair / Market-Wide ──
    cross_median_z: float  # median |Z| across all pairs at this timestamp
    cross_mean_z: float
    cross_pct_extreme: float  # % of pairs with |Z| > 2.2
    cross_return_dispersion: float  # std of 4-bar returns across pairs
    pair_z_rank: float  # rank of this pair's |Z| among all pairs
    cross_median_ret4: float  # median 4-bar return across pairs
    pair_ret_vs_cross: float  # pair's 4-bar return minus cross median

    # ── Family G: Liquidity / Session Context ──
    bars_since_session_open: int
    bars_until_session_close: int
    weekend_proximity: float  # hours until Friday close or since Monday open


def classify_outcome(z_path, entry_z, direction):
    """Classify event outcome using future Z trajectory.
    
    Labels are FUTURE-BASED and must never be used as features.
    
    FAST_MR: Z moves back toward zero by >50% within 4 bars.
    SLOW_MR: Z does not qualify as FAST_MR but subsequently moves
              back toward zero by >30% within 16 bars.
    CONTINUATION: Z moves materially farther from zero (>120% of entry |Z| at bar 8).
    AMBIGUOUS: None of the above.
    """
    n = len(z_path)
    if n < 5:
        return "ambiguous", 0.0, 0.0, 0.0

    z4 = z_path[min(4, n - 1)]
    z8 = z_path[min(8, n - 1)]
    z16 = z_path[min(16, n - 1)]

    if direction == 1:  # long: z was negative, reverts toward 0
        recovery_4 = (z4 - entry_z) / abs(entry_z) if abs(entry_z) > 1e-10 else 0
        recovery_16 = (z16 - entry_z) / abs(entry_z) if abs(entry_z) > 1e-10 else 0
        continuation_8 = abs(z8) > abs(entry_z) * 1.2
    else:  # short: z was positive, reverts toward 0
        recovery_4 = (entry_z - z4) / abs(entry_z) if abs(entry_z) > 1e-10 else 0
        recovery_16 = (entry_z - z16) / abs(entry_z) if abs(entry_z) > 1e-10 else 0
        continuation_8 = abs(z8) > abs(entry_z) * 1.2

    if recovery_4 > FAST_THRESHOLD:
        return "fast_mr", z4, z8, z16
    if continuation_8:
        return "continuation", z4, z8, z16
    if recovery_16 > SLOW_THRESHOLD:
        return "slow_mr", z4, z8, z16
    return "ambiguous", z4, z8, z16


def compute_forward_return(entry_price, direction, pip, price_path, bars=4):
    """Compute pip-based forward return at given horizon."""
    n = min(bars, len(price_path))
    if n < 2:
        return 0.0
    return (price_path[n - 1] - entry_price) * direction / pip


def extract_events(pdata):
    """Single-pass event extraction with entry-available features + outcome labels."""
    # Use longest pair as reference timeline
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]["n"])
    ref = pdata[ref_pair]
    n_ref = ref["n"]

    # Precompute cross-sectional Z and returns for all pairs
    # (These are computed causally — only past data used at each timestamp)
    all_pairs = sorted(pdata.keys())

    events = []
    for i in range(LOOKBACK + ATR_PERIOD + 52, n_ref - MAX_HOLD_BARS):
        ts = ref["ts"][i]
        if not in_session(ts):
            continue

        # ── Cross-sectional features (entry-available) ──
        cross_z_list = []
        cross_ret4_list = []
        for pair in all_pairs:
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_["n"]:
                continue
            z_val = pd_["z"][i]
            if not np.isnan(z_val):
                cross_z_list.append(abs(z_val))
            # 4-bar return (causal: we use price at i-4 and i)
            if i >= 4 and not np.isnan(pd_["c"][i]) and not np.isnan(pd_["c"][i - 4]):
                ret4 = (pd_["c"][i] - pd_["c"][i - 4]) / pd_["c"][i - 4] * 10000  # pips-ish
                cross_ret4_list.append(ret4)

        cross_z_arr = np.array(cross_z_list) if cross_z_list else np.array([0.0])
        cross_ret4_arr = np.array(cross_ret4_list) if cross_ret4_list else np.array([0.0])

        cross_median_z = float(np.median(cross_z_arr))
        cross_mean_z = float(np.mean(cross_z_arr))
        cross_pct_extreme = float(np.mean(cross_z_arr > Z_ENTRY)) * 100
        cross_return_dispersion = float(np.std(cross_ret4_arr)) if len(cross_ret4_arr) > 1 else 0.0
        cross_median_ret4 = float(np.median(cross_ret4_arr))

        # Process each pair
        for pair in all_pairs:
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_["n"]:
                continue
            z_now = pd_["z"][i]
            if np.isnan(z_now) or abs(z_now) < Z_ENTRY:
                continue
            atr_now = pd_["atr"][i]
            if np.isnan(atr_now) or atr_now <= 0:
                continue

            direction = 1 if z_now < 0 else -1
            pip = pd_["pip"]
            pv = pd_["pv"]
            ep = pd_["c"][i] + SLIPPAGE_PIPS * pip if direction == 1 else pd_["c"][i] - SLIPPAGE_PIPS * pip
            sl_dist = atr_now * ATR_SL_MULT

            # Outcome label (uses future data — never used as feature)
            path_n = min(MAX_HOLD_BARS, pd_["n"] - i)
            price_path = [float(pd_["c"][i + j]) for j in range(path_n)]
            z_path = [float(pd_["z"][i + j]) if not np.isnan(pd_["z"][i + j]) else 0.0
                      for j in range(path_n)]
            high_path = [float(pd_["h"][i + j]) for j in range(path_n)]
            low_path = [float(pd_["lo"][i + j]) for j in range(path_n)]

            outcome, z4, z8, z16 = classify_outcome(z_path, z_now, direction)
            fwd_ret_4 = compute_forward_return(ep, direction, pip, price_path, 4)

            # ═══════════════════════════════════════════════
            # ENTRY-AVAILABLE FEATURES
            # ═══════════════════════════════════════════════

            c = pd_["c"]
            h = pd_["h"]
            lo = pd_["lo"]
            o = pd_["o"]
            z = pd_["z"]
            atr_arr = pd_["atr"]
            atr_pct = pd_["atr_pct"]
            ema200 = pd_["ema200"]
            ema50 = pd_["ema50"]
            ema20 = pd_["ema20"]
            vol = pd_["vol"]
            bar_range = pd_["bar_range"]

            # ── Family A: Z / Extremeness ──
            signed_z = z_now
            z_abs_vals = np.abs(z[max(0, i - 200):i + 1])
            z_abs_valid = z_abs_vals[~np.isnan(z_abs_vals)]
            z_pctile_200 = float(np.mean(z_abs_valid <= abs(z_now)) * 100) if len(z_abs_valid) > 10 else 50.0
            z_pctile_500 = causal_percentile(np.abs(z), i, abs(z_now), 500)
            z_pctile_1000 = causal_percentile(np.abs(z), i, abs(z_now), 1000)
            z_pctile_2000 = causal_percentile(np.abs(z), i, abs(z_now), 2000)

            # Distance from recent Z extremes (last 50 bars)
            recent_z = np.abs(z[max(0, i - 50):i + 1])
            recent_z_valid = recent_z[~np.isnan(recent_z)]
            recent_max_z = float(np.max(recent_z_valid)) if len(recent_z_valid) > 0 else abs(z_now)
            recent_min_z = float(np.min(recent_z_valid)) if len(recent_z_valid) > 0 else abs(z_now)
            dist_from_recent_max_z = abs(z_now) - recent_max_z
            dist_from_recent_min_z = abs(z_now) - recent_min_z

            # Bars where |Z| was higher in last 20 bars
            lookback_z = np.abs(z[max(0, i - 20):i])
            lookback_valid = lookback_z[~np.isnan(lookback_z)]
            z_was_beyond_count = int(np.sum(lookback_valid > abs(z_now))) if len(lookback_valid) > 0 else 0

            # Z dynamics
            z_prev1 = z[i - 1] if i > 0 and not np.isnan(z[i - 1]) else z_now
            z_prev2 = z[i - 2] if i > 1 and not np.isnan(z[i - 2]) else z_prev1
            z_prev4 = z[i - 4] if i > 3 and not np.isnan(z[i - 4]) else z_prev2
            dz_1 = z_now - z_prev1
            dz_2 = z_now - z_prev2
            dz_4 = z_now - z_prev4
            z_moving_toward_zero = 1 if (z_now > 0 and dz_1 < 0) or (z_now < 0 and dz_1 > 0) else 0
            z_accel = dz_1 - (z_prev1 - z_prev2) if i > 1 else 0.0

            # ── Family B: Price / Return Structure ──
            ret_1 = (c[i] - c[i - 1]) / c[i - 1] * 10000 if i > 0 and c[i - 1] != 0 else 0.0
            ret_2 = (c[i] - c[i - 2]) / c[i - 2] * 10000 if i > 1 and c[i - 2] != 0 else 0.0
            ret_4 = (c[i] - c[i - 4]) / c[i - 4] * 10000 if i > 3 and c[i - 4] != 0 else 0.0
            ret_8 = (c[i] - c[i - 8]) / c[i - 8] * 10000 if i > 7 and c[i - 8] != 0 else 0.0
            ret_16 = (c[i] - c[i - 16]) / c[i - 16] * 10000 if i > 15 and c[i - 16] != 0 else 0.0
            abs_ret_1 = abs(ret_1)
            abs_ret_4 = abs(ret_4)

            # Consecutive directional bars
            consec = 0
            for k in range(1, min(21, i + 1)):
                if i - k < 0:
                    break
                if c[i - k + 1] > c[i - k]:
                    if consec >= 0:
                        consec += 1
                    else:
                        break
                elif c[i - k + 1] < c[i - k]:
                    if consec <= 0:
                        consec -= 1
                    else:
                        break
                else:
                    break
            consec_direction = consec

            # Candle body/range ratio
            body = abs(c[i] - o[i])
            rng = bar_range[i] if bar_range[i] > 0 else 1e-10
            body_range_ratio = body / rng

            # Wick ratios
            upper_wick = (h[i] - max(c[i], o[i])) / rng if rng > 0 else 0.0
            lower_wick = (min(c[i], o[i]) - lo[i]) / rng if rng > 0 else 0.0

            # Distance from 52-bar (26-hour) high/low
            high_52 = float(np.max(h[max(0, i - 52):i + 1]))
            low_52 = float(np.min(lo[max(0, i - 52):i + 1]))
            dist_from_52h_high = (c[i] - high_52) / pip
            dist_from_52h_low = (c[i] - low_52) / pip

            # Range position (close within last 20-bar range)
            high_20 = float(np.max(h[max(0, i - 20):i + 1]))
            low_20 = float(np.min(lo[max(0, i - 20):i + 1]))
            rng_20 = high_20 - low_20
            range_position = (c[i] - low_20) / rng_20 if rng_20 > 0 else 0.5

            # Range expansion
            avg_range_20 = float(np.mean(bar_range[max(0, i - 20):i + 1]))
            range_expansion = bar_range[i] / avg_range_20 if avg_range_20 > 0 else 1.0

            # Price displacement relative to ATR
            price_displacement_atr = (c[i] - ema200[i]) / atr_now if atr_now > 0 else 0.0

            # ── Family C: Volatility ──
            atr_pctile_200 = causal_percentile(atr_pct, i, atr_pct[i], 200)
            atr_pctile_500 = causal_percentile(atr_pct, i, atr_pct[i], 500)
            atr_pctile_1000 = causal_percentile(atr_pct, i, atr_pct[i], 1000)

            # Realized volatility (20-bar)
            if i >= 20:
                ret_series = np.diff(np.log(c[i - 20:i + 1]))
                ret_valid = ret_series[~np.isnan(ret_series)]
                realized_vol_20 = float(np.std(ret_valid) * np.sqrt(252 * 48)) if len(ret_valid) > 5 else 0.0
            else:
                realized_vol_20 = 0.0
            realized_vol_pctile_500 = causal_percentile(
                np.array([0.0]), i, realized_vol_20, 500  # placeholder
            )

            # Vol expansion ratio (short/long)
            if i >= 50:
                short_vol = float(np.std(np.diff(np.log(c[i - 10:i + 1]))) * np.sqrt(252 * 48))
                long_vol = float(np.std(np.diff(np.log(c[i - 50:i + 1]))) * np.sqrt(252 * 48))
                vol_expansion_ratio = short_vol / long_vol if long_vol > 0 else 1.0
            else:
                vol_expansion_ratio = 1.0

            range_pctile_500 = causal_percentile(bar_range, i, bar_range[i], 500)

            # ── Family D: Trend / Market Structure ──
            ema_dist_200 = (c[i] - ema200[i]) / ema200[i] * 100 if ema200[i] != 0 else 0.0
            ema_dist_50 = (c[i] - ema50[i]) / ema50[i] * 100 if ema50[i] != 0 else 0.0
            ema_dist_20 = (c[i] - ema20[i]) / ema20[i] * 100 if ema20[i] != 0 else 0.0

            ema_slope_200 = (ema200[i] - ema200[max(0, i - 10)]) / ema200[max(0, i - 10)] * 10000 if ema200[max(0, i - 10)] != 0 else 0.0
            ema_slope_50 = (ema50[i] - ema50[max(0, i - 10)]) / ema50[max(0, i - 10)] * 10000 if ema50[max(0, i - 10)] != 0 else 0.0

            ema_cross_20_50 = 1.0 if ema20[i] > ema50[i] else -1.0
            ema_cross_50_200 = 1.0 if ema50[i] > ema200[i] else -1.0

            trend_return_20 = (c[i] - c[max(0, i - 20)]) / c[max(0, i - 20)] * 10000 if c[max(0, i - 20)] != 0 else 0.0

            # Trend persistence: fraction of last 20 bars in same direction as current
            if i >= 20:
                recent_returns = np.diff(c[i - 20:i + 1])
                current_dir = np.sign(c[i] - c[i - 1]) if c[i] != c[i - 1] else 0
                trend_persistence = float(np.mean(np.sign(recent_returns) == current_dir)) if current_dir != 0 else 0.5
            else:
                trend_persistence = 0.5

            # Approximate ADX (directional strength)
            if i >= 20:
                ups = np.maximum(0, np.diff(h[i - 20:i + 1]))
                downs = np.maximum(0, -np.diff(lo[i - 20:i + 1]))
                plus_dm = ups - downs
                minus_dm = downs - ups
                tr_vals = np.maximum(h[i - 20:i] - lo[i - 20:i],
                                     np.maximum(abs(h[i - 20:i] - c[i - 21:i - 1]),
                                                abs(lo[i - 20:i] - c[i - 21:i - 1])))
                plus_di = float(np.mean(plus_dm)) / float(np.mean(tr_vals)) * 100 if np.mean(tr_vals) > 0 else 0
                minus_di = float(np.mean(minus_dm)) / float(np.mean(tr_vals)) * 100 if np.mean(tr_vals) > 0 else 0
                dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
                adx_approx = dx
            else:
                adx_approx = 0.0

            # ── Family E: Volume / Activity ──
            vol_now = vol[i]
            vol_pctile_200 = causal_percentile(vol, i, vol_now, 200)
            vol_pctile_500 = causal_percentile(vol, i, vol_now, 500)
            avg_vol_20 = float(np.mean(vol[max(0, i - 20):i + 1]))
            vol_expansion = vol_now / avg_vol_20 if avg_vol_20 > 0 else 1.0

            # Volume-price correlation
            if i >= 20:
                vol_20 = vol[i - 20:i + 1]
                ret_20_abs = np.abs(np.diff(c[i - 20:i + 1]))[:20]
                if len(vol_20) > 1 and len(ret_20_abs) > 1:
                    min_len = min(len(vol_20), len(ret_20_abs))
                    corr = float(np.corrcoef(vol_20[:min_len], ret_20_abs[:min_len])[0, 1])
                    vol_price_corr_20 = corr if not np.isnan(corr) else 0.0
                else:
                    vol_price_corr_20 = 0.0
            else:
                vol_price_corr_20 = 0.0

            # ── Family F: Cross-Pair (already computed above) ──
            pair_z_rank = float(np.mean(cross_z_arr <= abs(z_now))) * 100
            pair_ret_vs_cross = ret_4 - cross_median_ret4

            # ── Family G: Liquidity / Session Context ──
            session_name = get_session(ts)
            bars_since_open = 0
            bars_until_close = 0
            if session_name == "overlap":
                bars_since_open = i - max(
                    next((j for j in range(i, -1, -1) if not (7 <= ref["ts"][j].hour < 12)), i), 0
                )
                bars_until_close = max(0, 21 - ref["ts"][i].hour) * 2
            elif session_name == "london_only":
                bars_since_open = i - max(
                    next((j for j in range(i, -1, -1) if ref["ts"][j].hour < 7 or ref["ts"][j].hour >= 16), i), 0
                )
                bars_until_close = max(0, 16 - ref["ts"][i].hour) * 2
            elif session_name == "ny_only":
                bars_since_open = i - max(
                    next((j for j in range(i, -1, -1) if ref["ts"][j].hour < 12 or ref["ts"][j].hour >= 21), i), 0
                )
                bars_until_close = max(0, 21 - ref["ts"][i].hour) * 2

            weekend_proximity = 0.0
            if ts.dayofweek == 4:  # Friday
                weekend_proximity = max(0, 21 - ts.hour) * 30  # minutes until close
            elif ts.dayofweek == 0:  # Monday
                weekend_proximity = -(ts.hour - 7) * 30  # negative = since open

            # ── Outcome Label ──
            # Get forward Z trajectory
            z_path = [float(z[i + j]) if i + j < pd_["n"] and not np.isnan(z[i + j]) else z_now
                      for j in range(MAX_HOLD_BARS)]
            price_path = [float(c[i + j]) if i + j < pd_["n"] else c[i]
                          for j in range(MAX_HOLD_BARS)]

            outcome, z4, z8, z16 = classify_outcome(z_path, z_now, direction)
            fwd_ret_4 = compute_forward_return(ep, direction, pip, price_path, 4)

            events.append(Phase8Event(
                pair=pair, direction=direction, entry_price=ep,
                entry_z=z_now, abs_z=abs(z_now), entry_ts=ts, entry_bar=i,
                year=ts.year, month=ts.strftime("%Y-%m"),
                entry_hour=ts.hour, entry_dow=ts.dayofweek, session=session_name,
                outcome=outcome, z_at_4=z4, z_at_8=z8, z_at_16=z16,
                fwd_return_4=fwd_ret_4,
                signed_z=signed_z,
                z_pctile_200=z_pctile_200, z_pctile_500=z_pctile_500,
                z_pctile_1000=z_pctile_1000, z_pctile_2000=z_pctile_2000,
                dist_from_recent_max_z=dist_from_recent_max_z,
                dist_from_recent_min_z=dist_from_recent_min_z,
                z_was_beyond_count=z_was_beyond_count,
                z_moving_toward_zero=z_moving_toward_zero,
                dz_1=dz_1, dz_2=dz_2, dz_4=dz_4, z_accel=z_accel,
                ret_1=ret_1, ret_2=ret_2, ret_4=ret_4, ret_8=ret_8, ret_16=ret_16,
                abs_ret_1=abs_ret_1, abs_ret_4=abs_ret_4,
                consec_direction=consec_direction,
                body_range_ratio=body_range_ratio,
                upper_wick_ratio=upper_wick, lower_wick_ratio=lower_wick,
                dist_from_52h_high=dist_from_52h_high, dist_from_52h_low=dist_from_52h_low,
                range_position=range_position, range_expansion=range_expansion,
                price_displacement_atr=price_displacement_atr,
                atr_now=atr_now,
                atr_pctile_200=atr_pctile_200, atr_pctile_500=atr_pctile_500,
                atr_pctile_1000=atr_pctile_1000,
                realized_vol_20=realized_vol_20,
                realized_vol_pctile_500=realized_vol_pctile_500,
                vol_expansion_ratio=vol_expansion_ratio,
                range_pctile_500=range_pctile_500,
                ema_dist_200=ema_dist_200, ema_dist_50=ema_dist_50, ema_dist_20=ema_dist_20,
                ema_slope_200=ema_slope_200, ema_slope_50=ema_slope_50,
                ema_cross_20_50=ema_cross_20_50, ema_cross_50_200=ema_cross_50_200,
                trend_return_20=trend_return_20, trend_persistence=trend_persistence,
                adx_approx=adx_approx,
                vol_now=vol_now,
                vol_pctile_200=vol_pctile_200, vol_pctile_500=vol_pctile_500,
                vol_expansion=vol_expansion, vol_price_corr_20=vol_price_corr_20,
                cross_median_z=cross_median_z, cross_mean_z=cross_mean_z,
                cross_pct_extreme=cross_pct_extreme,
                cross_return_dispersion=cross_return_dispersion,
                pair_z_rank=pair_z_rank, cross_median_ret4=cross_median_ret4,
                pair_ret_vs_cross=pair_ret_vs_cross,
                bars_since_session_open=bars_since_open,
                bars_until_session_close=bars_until_close,
                weekend_proximity=weekend_proximity,
            ))

    return events


# ═══════════════════════════════════════════════════════════════
# STATISTICAL TESTING
# ═══════════════════════════════════════════════════════════════

# All feature names organized by family
FEATURE_FAMILIES = {
    "A_Z_extremeness": [
        "abs_z", "signed_z", "z_pctile_200", "z_pctile_500",
        "z_pctile_1000", "z_pctile_2000", "dist_from_recent_max_z",
        "dist_from_recent_min_z", "z_was_beyond_count", "z_moving_toward_zero",
        "dz_1", "dz_2", "dz_4", "z_accel",
    ],
    "B_price_structure": [
        "ret_1", "ret_2", "ret_4", "ret_8", "ret_16",
        "abs_ret_1", "abs_ret_4", "consec_direction",
        "body_range_ratio", "upper_wick_ratio", "lower_wick_ratio",
        "dist_from_52h_high", "dist_from_52h_low",
        "range_position", "range_expansion", "price_displacement_atr",
    ],
    "C_volatility": [
        "atr_now", "atr_pctile_200", "atr_pctile_500", "atr_pctile_1000",
        "realized_vol_20", "realized_vol_pctile_500",
        "vol_expansion_ratio", "range_pctile_500",
    ],
    "D_trend_structure": [
        "ema_dist_200", "ema_dist_50", "ema_dist_20",
        "ema_slope_200", "ema_slope_50",
        "ema_cross_20_50", "ema_cross_50_200",
        "trend_return_20", "trend_persistence", "adx_approx",
    ],
    "E_volume_activity": [
        "vol_now", "vol_pctile_200", "vol_pctile_500",
        "vol_expansion", "vol_price_corr_20",
    ],
    "F_cross_pair": [
        "cross_median_z", "cross_mean_z", "cross_pct_extreme",
        "cross_return_dispersion", "pair_z_rank",
        "cross_median_ret4", "pair_ret_vs_cross",
    ],
    "G_session_context": [
        "entry_hour", "entry_dow", "bars_since_session_open",
        "bars_until_session_close", "weekend_proximity",
    ],
}

ALL_FEATURES = []
for fam_feats in FEATURE_FAMILIES.values():
    ALL_FEATURES.extend(fam_feats)


def extract_feature_array(events, feature_names):
    """Extract feature values as 2D numpy array."""
    rows = []
    for ev in events:
        row = []
        for fname in feature_names:
            val = getattr(ev, fname, np.nan)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                row.append(0.0)
            else:
                row.append(float(val))
        rows.append(row)
    return np.array(rows)


def mann_whitney_test(fast_vals, slow_vals):
    """Mann-Whitney U test: does feature discriminate FAST from SLOW?"""
    if len(fast_vals) < 10 or len(slow_vals) < 10:
        return 1.0, 0.0
    stat, pval = sp_stats.mannwhitneyu(fast_vals, slow_vals, alternative="two-sided")
    # Effect size: rank-biserial correlation
    n1, n2 = len(fast_vals), len(slow_vals)
    effect_size = 1 - 2 * stat / (n1 * n2)
    return float(pval), float(effect_size)


def permutation_test_discrimination(fast_vals, slow_vals, n_perm=N_PERM, seed=RNG_SEED):
    """Permutation test: is observed difference between FAST and SLOW real?"""
    rng = np.random.RandomState(seed)
    combined = np.concatenate([fast_vals, slow_vals])
    n_fast = len(fast_vals)
    actual_diff = abs(np.mean(fast_vals) - np.mean(slow_vals))
    count = 0
    for _ in range(n_perm):
        rng.shuffle(combined)
        perm_fast = combined[:n_fast]
        perm_slow = combined[n_fast:]
        perm_diff = abs(np.mean(perm_fast) - np.mean(perm_slow))
        if perm_diff >= actual_diff:
            count += 1
    return count / n_perm


def bootstrap_ci_diff(fast_vals, slow_vals, n_boot=N_BOOT, seed=RNG_SEED):
    """Bootstrap CI for difference in means (FAST - SLOW)."""
    rng = np.random.RandomState(seed)
    diffs = []
    for _ in range(n_boot):
        f_sample = rng.choice(fast_vals, size=len(fast_vals), replace=True)
        s_sample = rng.choice(slow_vals, size=len(slow_vals), replace=True)
        diffs.append(float(np.mean(f_sample) - np.mean(s_sample)))
    diffs = np.array(diffs)
    return float(np.mean(diffs)), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def bh_fdr(p_values):
    """Benjamini-Hochberg FDR correction."""
    n = len(p_values)
    ranked = np.argsort(p_values)
    adjusted = np.zeros(n)
    for i, idx in enumerate(ranked):
        adjusted[idx] = p_values[idx] * n / (i + 1)
    return np.minimum(adjusted, 1.0)


# ═══════════════════════════════════════════════════════════════
# MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════

def run_analysis():
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 8 — FAST vs SLOW MEAN-REVERSION DISCOVERY")
    print("=" * 80)

    # ── Step 1: Load data ──
    print("\n[1] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"    {len(pdata)} pairs loaded")

    # ── Step 2: Extract events ──
    print("\n[2] Extracting events with entry-available features...")
    events = extract_events(pdata)
    print(f"    {len(events)} events extracted")

    # ── Step 3: Class distribution ──
    print("\n[3] Outcome distribution:")
    class_counts = defaultdict(int)
    for ev in events:
        class_counts[ev.outcome] += 1
    for cls in ["fast_mr", "slow_mr", "continuation", "ambiguous"]:
        n = class_counts.get(cls, 0)
        print(f"    {cls}: {n} ({n / len(events) * 100:.1f}%)")

    fast = [ev for ev in events if ev.outcome == "fast_mr"]
    slow = [ev for ev in events if ev.outcome == "slow_mr"]
    print(f"\n    Key comparison: FAST_MR (n={len(fast)}) vs SLOW_MR (n={len(slow)})")

    # ── Step 4: Feature discrimination (FAST vs SLOW) ──
    print("\n[4] Feature Discrimination: FAST vs SLOW")
    print("-" * 80)

    results = []
    for family, features in FEATURE_FAMILIES.items():
        for fname in features:
            fast_vals = np.array([getattr(ev, fname, 0.0) for ev in fast], dtype=float)
            slow_vals = np.array([getattr(ev, fname, 0.0) for ev in slow], dtype=float)

            # Skip if all values are the same
            if np.std(fast_vals) < 1e-12 and np.std(slow_vals) < 1e-12:
                continue

            pval, effect_size = mann_whitney_test(fast_vals, slow_vals)
            perm_p = permutation_test_discrimination(fast_vals, slow_vals)
            diff_mean, ci_lo, ci_hi = bootstrap_ci_diff(fast_vals, slow_vals)

            results.append({
                "feature": fname,
                "family": family,
                "n_fast": len(fast),
                "n_slow": len(slow),
                "fast_mean": round(float(np.mean(fast_vals)), 4),
                "fast_median": round(float(np.median(fast_vals)), 4),
                "slow_mean": round(float(np.mean(slow_vals)), 4),
                "slow_median": round(float(np.median(slow_vals)), 4),
                "effect_size": round(effect_size, 4),
                "diff_mean": round(diff_mean, 4),
                "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
                "raw_p": round(pval, 6),
                "perm_p": round(perm_p, 6),
            })

    # ── Step 5: FDR correction ──
    print("\n[5] Multiple Comparison Control (Benjamini-Hochberg FDR)")
    raw_pvals = np.array([r["raw_p"] for r in results])
    fdr_adjusted = bh_fdr(raw_pvals)
    for i, r in enumerate(results):
        r["fdr_p"] = round(float(fdr_adjusted[i]), 6)
        r["significant_after_fdr"] = bool(fdr_adjusted[i] < 0.05)

    # Sort by raw p-value
    results.sort(key=lambda r: r["raw_p"])

    # Print top results
    print(f"\n    {'Feature':<30} {'Family':<20} {'Raw p':<10} {'FDR p':<10} {'Perm p':<10} {'Effect':<8} {'Sig?'}")
    print("    " + "-" * 100)
    for r in results[:40]:
        sig = "***" if r["significant_after_fdr"] else ""
        print(f"    {r['feature']:<30} {r['family']:<20} {r['raw_p']:<10.4f} {r['fdr_p']:<10.4f} {r['perm_p']:<10.4f} {r['effect_size']:<8.4f} {sig}")

    n_sig = sum(1 for r in results if r["significant_after_fdr"])
    print(f"\n    {n_sig}/{len(results)} features significant after FDR correction")

    # ── Step 6: Temporal stability for significant features ──
    sig_features = [r["feature"] for r in results if r["significant_after_fdr"]]
    if not sig_features:
        print("\n[6] No significant features after FDR. Checking top-5 raw-p features...")
        sig_features = [r["feature"] for r in results[:5]]

    print(f"\n[6] Temporal Stability (top {len(sig_features)} features)")
    print("-" * 80)
    periods = [("2016-2018", 2016, 2018), ("2019-2021", 2019, 2021),
               ("2022-2024", 2022, 2024), ("2025-2026", 2025, 2026)]
    temporal_results = {}
    for fname in sig_features:
        pr = {}
        for label, y1, y2 in periods:
            fast_p = [getattr(ev, fname, 0.0) for ev in fast if y1 <= ev.year <= y2]
            slow_p = [getattr(ev, fname, 0.0) for ev in slow if y1 <= ev.year <= y2]
            if len(fast_p) < 10 or len(slow_p) < 10:
                pr[label] = {"n_fast": len(fast_p), "n_slow": len(slow_p), "p": 1.0}
                continue
            pval, eff = mann_whitney_test(np.array(fast_p), np.array(slow_p))
            pr[label] = {
                "n_fast": len(fast_p), "n_slow": len(slow_p),
                "fast_mean": round(float(np.mean(fast_p)), 4),
                "slow_mean": round(float(np.mean(slow_p)), 4),
                "p": round(pval, 4), "effect": round(eff, 4),
                "direction": "fast>slow" if np.mean(fast_p) > np.mean(slow_p) else "slow>fast",
            }
        consistent = sum(1 for p in pr.values() if p.get("p", 1) < 0.10 and p.get("direction") == "fast>slow")
        temporal_results[fname] = {"periods": pr, "consistent_direction": consistent, "n_periods": 4}
        dir_str = " / ".join(f"{p.get('direction','?')}" for p in pr.values())
        print(f"    {fname:<30} consistency={consistent}/4  directions=[{dir_str}]")

    # ── Step 7: Cross-pair stability for significant features ──
    print(f"\n[7] Cross-Pair Stability (top {len(sig_features)} features)")
    print("-" * 80)
    pair_results = {}
    for fname in sig_features:
        pair_effects = {}
        for pair in sorted(set(ev.pair for ev in events)):
            fp = [getattr(ev, fname, 0.0) for ev in fast if ev.pair == pair]
            sp = [getattr(ev, fname, 0.0) for ev in slow if ev.pair == pair]
            if len(fp) < 5 or len(sp) < 5:
                continue
            pval, eff = mann_whitney_test(np.array(fp), np.array(sp))
            pair_effects[pair] = {
                "n_fast": len(fp), "n_slow": len(sp),
                "effect": round(eff, 4), "p": round(pval, 4),
                "direction": "fast>slow" if np.mean(fp) > np.mean(sp) else "slow>fast",
            }
        n_pairs = len(pair_effects)
        n_same_dir = sum(1 for p in pair_effects.values() if p.get("direction") == "fast>slow")
        n_sig_pairs = sum(1 for p in pair_effects.values() if p.get("p", 1) < 0.10)
        pair_results[fname] = {
            "n_pairs": n_pairs, "n_same_direction": n_same_dir,
            "n_sig_pairs": n_sig_pairs,
            "pct_same_direction": round(n_same_dir / n_pairs * 100, 1) if n_pairs > 0 else 0,
        }
        print(f"    {fname:<30} pairs={n_pairs} same_dir={n_same_dir}/{n_pairs} ({n_same_dir/n_pairs*100:.0f}%) sig={n_sig_pairs}")

    # ═══════════════════════════════════════════════════════════
    # STEP 8: OOS VALIDATION (Walk-Forward + Pair Holdout)
    # ═══════════════════════════════════════════════════════════
    print("\n[8] Out-of-Sample Validation (Walk-Forward)")
    print("-" * 80)

    # Compute doubly stable features (4/4 temporal + 19/19 cross-pair)
    combined = set(k for k, v in temporal_results.items() if v["consistent_direction"] == 4) & \
               set(k for k, v in pair_results.items() if v["n_same_direction"] == 19)
    print(f"    Doubly stable features: {len(combined)}")

    # Use the top stable features for OOS
    oos_features = sorted(combined)
    if len(oos_features) > 10:
        oos_features = oos_features[:10]  # Top 10 by effect size

    print(f"    Using {len(oos_features)} features: {oos_features}")

    # Walk-forward: train on 2016-Y, test on Y+1..2026
    wf_splits = [
        ("2016-2020", 2016, 2020, 2021, 2026),
        ("2016-2021", 2016, 2021, 2022, 2026),
        ("2016-2022", 2016, 2022, 2023, 2026),
        ("2016-2023", 2016, 2023, 2024, 2026),
        ("2016-2024", 2016, 2024, 2025, 2026),
    ]

    wf_results = {}
    for label, train_y1, train_y2, test_y1, test_y2 in wf_splits:
        train_events = [ev for ev in events if train_y1 <= ev.year <= train_y2]
        test_events = [ev for ev in events if test_y1 <= ev.year <= test_y2]

        train_fast = [ev for ev in train_events if ev.outcome == "fast_mr"]
        train_slow = [ev for ev in train_events if ev.outcome == "slow_mr"]
        test_fast = [ev for ev in test_events if ev.outcome == "fast_mr"]
        test_slow = [ev for ev in test_events if ev.outcome == "slow_mr"]

        if len(train_fast) < 50 or len(train_slow) < 50 or len(test_fast) < 50 or len(test_slow) < 50:
            wf_results[label] = {"skipped": True}
            continue

        # Compute feature means in training period
        train_means_fast = {f: np.mean([getattr(ev, f, 0) for ev in train_fast]) for f in oos_features}
        train_means_slow = {f: np.mean([getattr(ev, f, 0) for ev in train_slow]) for f in oos_features}

        # Compute effect sizes in test period
        test_effects = {}
        for f in oos_features:
            tf = np.array([getattr(ev, f, 0) for ev in test_fast], dtype=float)
            ts_ = np.array([getattr(ev, f, 0) for ev in test_slow], dtype=float)
            if np.std(tf) < 1e-12 and np.std(ts_) < 1e-12:
                test_effects[f] = {"effect": 0.0, "direction_match": True}
                continue
            _, eff = mann_whitney_test(tf, ts_)
            # Direction should match training
            train_dir = np.sign(train_means_fast[f] - train_means_slow[f])
            test_dir = np.sign(np.mean(tf) - np.mean(ts_))
            test_effects[f] = {
                "effect": round(eff, 4),
                "direction_match": bool(train_dir == test_dir) if train_dir != 0 else True,
            }

        n_match = sum(1 for v in test_effects.values() if v.get("direction_match", False))
        wf_results[label] = {
            "train_n": len(train_events), "test_n": len(test_events),
            "direction_match": n_match, "n_features": len(oos_features),
            "features": test_effects,
        }
        print(f"    {label}: test_n={len(test_events):>6} direction_match={n_match}/{len(oos_features)}")

    # Pair holdout
    print("\n[9] Cross-Pair Holdout Validation")
    print("-" * 80)
    ph_results = {}
    for fi, held_out in enumerate(HELDOUT_GROUPS):
        train_events = [ev for ev in events if ev.pair not in held_out]
        test_events = [ev for ev in events if ev.pair in held_out]
        train_fast = [ev for ev in train_events if ev.outcome == "fast_mr"]
        train_slow = [ev for ev in train_events if ev.outcome == "slow_mr"]
        test_fast = [ev for ev in test_events if ev.outcome == "fast_mr"]
        test_slow = [ev for ev in test_events if ev.outcome == "slow_mr"]

        if len(train_fast) < 50 or len(train_slow) < 50 or len(test_fast) < 50 or len(test_slow) < 50:
            continue

        train_means_fast = {f: np.mean([getattr(ev, f, 0) for ev in train_fast]) for f in oos_features}
        train_means_slow = {f: np.mean([getattr(ev, f, 0) for ev in train_slow]) for f in oos_features}

        test_effects = {}
        for f in oos_features:
            tf = np.array([getattr(ev, f, 0) for ev in test_fast], dtype=float)
            ts_ = np.array([getattr(ev, f, 0) for ev in test_slow], dtype=float)
            if np.std(tf) < 1e-12 and np.std(ts_) < 1e-12:
                test_effects[f] = {"effect": 0.0, "direction_match": True}
                continue
            _, eff = mann_whitney_test(tf, ts_)
            train_dir = np.sign(train_means_fast[f] - train_means_slow[f])
            test_dir = np.sign(np.mean(tf) - np.mean(ts_))
            test_effects[f] = {
                "effect": round(eff, 4),
                "direction_match": bool(train_dir == test_dir) if train_dir != 0 else True,
            }

        n_match = sum(1 for v in test_effects.values() if v.get("direction_match", False))
        ph_results[f"fold_{fi+1}"] = {
            "held_out": held_out, "train_n": len(train_events), "test_n": len(test_events),
            "direction_match": n_match, "n_features": len(oos_features),
        }
        print(f"    Fold {fi+1}: held_out={held_out[:2]}... test_n={len(test_events):>6} direction_match={n_match}/{len(oos_features)}")

    # Aggregate pair holdout
    all_match = sum(v.get("direction_match", 0) for v in ph_results.values())
    all_features = sum(v.get("n_features", 0) for v in ph_results.values())
    print(f"    Aggregate: {all_match}/{all_features} direction matches across all folds")

    # ═══════════════════════════════════════════════════════════
    # STEP 10: PREDICTIVE MODEL (Logistic Regression)
    # ═══════════════════════════════════════════════════════════
    print("\n[10] Predictive Model (Logistic Regression)")
    print("-" * 80)

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score, classification_report, confusion_matrix
        from sklearn.preprocessing import StandardScaler

        # Prepare data: FAST=1, SLOW=0 (exclude ambiguous/continuation)
        model_events = [ev for ev in events if ev.outcome in ("fast_mr", "slow_mr")]
        X = extract_feature_array(model_events, oos_features)
        y = np.array([1 if ev.outcome == "fast_mr" else 0 for ev in model_events])

        # Remove any NaN/inf rows
        valid = np.all(np.isfinite(X), axis=1)
        X, y = X[valid], y[valid]
        model_events = [ev for ev, v in zip(model_events, valid) if v]

        print(f"    Dataset: {len(y)} events ({int(y.sum())} fast, {len(y)-int(y.sum())} slow)")

        # Walk-forward model evaluation
        print("\n    Walk-Forward Model Evaluation:")
        model_wf_results = []
        for label, train_y1, train_y2, test_y1, test_y2 in wf_splits:
            train_idx = np.array([train_y1 <= ev.year <= train_y2 for ev in model_events])
            test_idx = np.array([test_y1 <= ev.year <= test_y2 for ev in model_events])

            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]

            if len(y_train) < 100 or len(y_test) < 50:
                continue

            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)

            model = LogisticRegression(max_iter=1000, random_state=42, C=1.0)
            model.fit(X_train_s, y_train)

            y_pred_proba = model.predict_proba(X_test_s)[:, 1]
            y_pred = model.predict(X_test_s)

            auc = roc_auc_score(y_test, y_pred_proba) if len(np.unique(y_test)) > 1 else 0.5
            accuracy = np.mean(y_pred == y_test)
            report = classification_report(y_test, y_pred, output_dict=True)

            # Feature importance (absolute coefficients)
            coefs = np.abs(model.coef_[0])
            top_feat_idx = np.argsort(coefs)[::-1]
            top_features = [(oos_features[i], round(float(coefs[i]), 4)) for i in top_feat_idx[:5]]

            model_wf_results.append({
                "period": label, "test_n": len(y_test),
                "auc": round(auc, 4), "accuracy": round(accuracy, 4),
                "precision_fast": round(report.get("1", {}).get("precision", 0), 4),
                "recall_fast": round(report.get("1", {}).get("recall", 0), 4),
                "top_features": top_features,
            })
            print(f"    {label}: AUC={auc:.4f} Acc={accuracy:.4f} test_n={len(y_test)}")

        # Overall model metrics
        if model_wf_results:
            avg_auc = np.mean([r["auc"] for r in model_wf_results])
            avg_acc = np.mean([r["accuracy"] for r in model_wf_results])
            print(f"\n    Average: AUC={avg_auc:.4f} Acc={avg_acc:.4f}")
            print(f"    Baseline (always predict majority): {max(y.mean(), 1-y.mean()):.4f}")

            # Feature importance across all folds
            all_importances = defaultdict(list)
            for r in model_wf_results:
                for fname, imp in r["top_features"]:
                    all_importances[fname].append(imp)
            print("\n    Feature Importance (avg across folds):")
            for fname in sorted(all_importances, key=lambda x: -np.mean(all_importances[x]))[:10]:
                avg_imp = np.mean(all_importances[fname])
                print(f"    {fname:<30} {avg_imp:.4f}")

        # ═══════════════════════════════════════════════════════════
        # STEP 11: ECONOMIC EVALUATION (Probability Buckets)
        # ═══════════════════════════════════════════════════════════
        print("\n[11] Economic Evaluation (Probability Buckets)")
        print("-" * 80)

        # Train on full dataset, evaluate probability buckets
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        full_model = LogisticRegression(max_iter=1000, random_state=42, C=1.0)
        full_model.fit(X_scaled, y)
        probs = full_model.predict_proba(X_scaled)[:, 1]

        buckets = [
            ("P < 0.4", probs < 0.4),
            ("0.4-0.5", (probs >= 0.4) & (probs < 0.5)),
            ("0.5-0.6", (probs >= 0.5) & (probs < 0.6)),
            ("0.6-0.7", (probs >= 0.6) & (probs < 0.7)),
            ("0.7-0.8", (probs >= 0.7) & (probs < 0.8)),
            ("P > 0.8", probs >= 0.8),
        ]

        econ_results = {}
        for bname, mask in buckets:
            bucket_events = [ev for ev, m in zip(model_events, mask) if m]
            if len(bucket_events) < 10:
                continue
            fast_in_bucket = sum(1 for ev in bucket_events if ev.outcome == "fast_mr")
            total_in_bucket = len(bucket_events)
            fast_rate = fast_in_bucket / total_in_bucket
            avg_fwd = np.mean([ev.fwd_return_4 for ev in bucket_events])
            econ_results[bname] = {
                "n": total_in_bucket,
                "fast_rate": round(fast_rate, 4),
                "avg_fwd_return_4": round(avg_fwd, 4),
            }
            print(f"    {bname:<12} n={total_in_bucket:>6} fast_rate={fast_rate:.4f} avg_fwd4={avg_fwd:.4f}p")

        has_economic_value = False
        if econ_results:
            rates = [v["fast_rate"] for v in econ_results.values()]
            if max(rates) - min(rates) > 0.05:
                has_economic_value = True
                print(f"\n    Spread: {max(rates)-min(rates):.4f} — economic differentiation EXISTS")
            else:
                print(f"\n    Spread: {max(rates)-min(rates):.4f} — minimal economic differentiation")

        model_available = True
    except ImportError:
        print("    sklearn not available — skipping predictive model")
        model_available = False
        model_wf_results = []
        econ_results = {}

    # ═══════════════════════════════════════════════════════════
    # STEP 12: FINAL VERDICT
    # ═══════════════════════════════════════════════════════════
    print("\n[12] Final Verdict")
    print("-" * 80)

    # Criteria for SUPPORTED:
    # 1. Features survive FDR correction
    # 2. Features survive permutation tests
    # 3. Features are temporally stable (4/4 periods)
    # 4. Features are cross-pair stable (19/19 pairs)
    # 5. OOS walk-forward preserves direction
    # 6. Predictive model AUC > 0.55

    n_fdr = sum(1 for r in results if r["significant_after_fdr"])
    n_perm = sum(1 for r in results if r["perm_p"] < 0.05)
    n_temporal = len(combined)  # features with 4/4 temporal + 19/19 cross-pair

    # Walk-forward direction preservation
    wf_direction_match = 0
    wf_total = 0
    for v in wf_results.values():
        if isinstance(v, dict) and "direction_match" in v:
            wf_direction_match += v["direction_match"]
            wf_total += v["n_features"]
    wf_match_rate = wf_direction_match / wf_total if wf_total > 0 else 0

    print(f"    Features FDR-significant:     {n_fdr}/{len(results)}")
    print(f"    Features perm-significant:    {n_perm}/{len(results)}")
    print(f"    Features doubly stable:       {n_temporal} (4/4 temporal + 19/19 cross-pair)")
    print(f"    OOS direction match rate:     {wf_match_rate:.4f} ({wf_direction_match}/{wf_total})")
    if model_available and model_wf_results:
        print(f"    Model avg AUC:                {np.mean([r['auc'] for r in model_wf_results]):.4f}")

    # Decision criteria
    verdict = "REJECTED"
    if (n_fdr >= 10 and n_perm >= 10 and n_temporal >= 5 and wf_match_rate > 0.7):
        verdict = "SUPPORTED"
    elif (n_fdr >= 5 and n_temporal >= 3 and wf_match_rate > 0.6):
        verdict = "INCONCLUSIVE"

    print(f"\n    VERDICT: {verdict}")

    # ── Step 13: Save complete results ──
    output = {
        "class_distribution": dict(class_counts),
        "n_fast": len(fast), "n_slow": len(slow),
        "feature_results": results,
        "temporal_stability": temporal_results,
        "cross_pair_stability": pair_results,
        "combined_stable_features": sorted(combined),
        "oos_features_used": oos_features,
        "walk_forward": wf_results,
        "pair_holdout": ph_results,
        "n_features_tested": len(results),
        "n_significant_after_fdr": n_fdr,
        "n_permutation_significant": n_perm,
        "n_doubly_stable": n_temporal,
        "wf_direction_match_rate": round(wf_match_rate, 4),
        "verdict": verdict,
    }
    if model_available:
        output["model_wf_results"] = model_wf_results
        output["economic_evaluation"] = econ_results

    with open(OUT / "fast_slow_discovery.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Saved {OUT / 'fast_slow_discovery.json'}")

    print(f"\n[DONE] {time.time() - t0:.1f}s")
    return output


if __name__ == "__main__":
    run_analysis()
