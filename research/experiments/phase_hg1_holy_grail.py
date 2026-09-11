"""
Phase HG-1: Holy Grail / ICSA Framework Validation

Five controlled experiments testing the structural ingredients of the
Individual Currency Strength Analysis (ICSA) framework.

HG-1A: ICSA Signal Structure
HG-1B: Currency Divergence Entry
HG-1C: Price-Path Distribution (MAE/MFE) — MOST IMPORTANT
HG-1D: Timeframe Management Test
HG-1E: ATR Stop Structure
+ Critical Control: ICSA vs Trend vs Random
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ALL_PAIRS, CURRENCIES
from currency_strength import CurrencyStrengthRanker
from indicators.atr import calculate_atr
from indicators.pip import pip_size as get_pip_size

DATA_DIR = Path("/root/data")
RNG_SEED = 42
N_PERM = 1000

# Pre-registered parameters (DO NOT CHANGE after this point)
ENTRY_TF = "5min"
STRENGTH_LOOKBACKS = [(5, 0.50), (10, 0.30), (20, 0.20)]
STRENGTH_NORM_WINDOW = 100
STRENGTH_MIN_DIVERGENCE = 5.0
ATR_PERIOD = 14
SIGNAL_COOLDOWN_BARS = 288  # 1 day minimum between signals on same pair/direction


# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING & RESAMPLING
# ═══════════════════════════════════════════════════════════════════════

def load_1min_data(pairs: list[str]) -> dict[str, pd.DataFrame]:
    """Load 1-minute OHLCV data for all pairs."""
    data = {}
    for pair in pairs:
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
                    data[k] = df
    return data


def resample_ohlcv(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Resample OHLCV to target timeframe."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample(target).agg(agg).dropna()


# ═══════════════════════════════════════════════════════════════════════
# CURRENCY STRENGTH (HG-1A)
# ═══════════════════════════════════════════════════════════════════════

def compute_strength(pair_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Compute individual currency strength using rolling multi-period ROC
    with z-score normalization. Causal — no future information.

    Returns DataFrame: index=datetime, columns=currencies, values in [-100, +100].
    """
    ranker = CurrencyStrengthRanker(
        lookbacks=STRENGTH_LOOKBACKS,
        top_n=3,
        min_div=STRENGTH_MIN_DIVERGENCE,
        norm_window=STRENGTH_NORM_WINDOW,
    )
    return ranker.calculate(pair_data)


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL GENERATION (HG-1B)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ICSASignal:
    pair: str
    direction: int  # +1 = BUY, -1 = SELL
    timestamp: pd.Timestamp
    bar_idx: int  # index in the entry TF DataFrame
    base_strength: float
    quote_strength: float
    divergence: float  # base - quote (signed)
    abs_divergence: float


def generate_icsa_signals(
    strength: pd.DataFrame,
    tradeable_pairs: list[str],
) -> list[ICSASignal]:
    """
    Generate ICSA divergence signals.

    BUY A/B: A strengthening (+), B weakening (-)
    SELL A/B: A weakening (-), B strengthening (+)

    Vectorized implementation for speed.
    """
    signals = []
    # Track last signal index per pair+direction for cooldown
    last_buy: dict[str, int] = {}
    last_sell: dict[str, int] = {}

    # Vectorized: compute all pair divergences at once
    for pair in tradeable_pairs:
        if "/" not in pair:
            continue
        base, quote = pair.split("/")
        if base not in strength.columns or quote not in strength.columns:
            continue

        base_s = strength[base].values
        quote_s = strength[quote].values
        div = base_s - quote_s
        abs_div = np.abs(div)

        # Find valid divergence points
        valid_mask = abs_div >= STRENGTH_MIN_DIVERGENCE
        valid_idx = np.where(valid_mask)[0]

        if len(valid_idx) == 0:
            continue

        # Apply cooldown: keep only indices that are >= cooldown apart
        filtered_idx = [valid_idx[0]]
        for idx in valid_idx[1:]:
            if idx - filtered_idx[-1] >= SIGNAL_COOLDOWN_BARS:
                filtered_idx.append(idx)

        for i in filtered_idx:
            b_val = base_s[i]
            q_val = quote_s[i]
            if np.isnan(b_val) or np.isnan(q_val):
                continue

            ts = strength.index[i]
            d = div[i]
            ad = abs_div[i]

            if b_val > 0 and q_val < 0:
                signals.append(ICSASignal(
                    pair=pair, direction=1, timestamp=ts, bar_idx=i,
                    base_strength=float(b_val), quote_strength=float(q_val),
                    divergence=float(d), abs_divergence=float(ad),
                ))
            elif b_val < 0 and q_val > 0:
                signals.append(ICSASignal(
                    pair=pair, direction=-1, timestamp=ts, bar_idx=i,
                    base_strength=float(b_val), quote_strength=float(q_val),
                    divergence=float(d), abs_divergence=float(ad),
                ))

    return signals


# ═══════════════════════════════════════════════════════════════════════
# TRADE PATH ANALYSIS (HG-1C)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TradePath:
    signal: ICSASignal
    entry_price: float
    atr_at_entry: float
    initial_stop_distance: float  # in price units
    pip_mult: float
    # MAE/MFE in R-multiples and pips
    mae_r: float = 0.0
    mfe_r: float = 0.0
    mae_pips: float = 0.0
    mfe_pips: float = 0.0
    # Time to MAE/MFE (in bars of entry TF)
    bars_to_mae: int = 0
    bars_to_mfe: int = 0
    # R-multiple reached
    max_r_reached: float = 0.0
    # Path at various horizons (in pips from entry)
    excursion_at: dict = field(default_factory=dict)
    # Exit at various horizons
    pnl_at: dict = field(default_factory=dict)


def compute_trade_paths(
    signals: list[ICSASignal],
    pair_data_entry: dict[str, pd.DataFrame],
    atr_tf: str = "15min",
    max_lookahead_bars: int = 288,  # ~6 days of 5min data
) -> list[TradePath]:
    """
    For each ICSA signal, compute the full price path and MAE/MFE.

    Uses entry-timeframe (5min) data for paths for speed.
    Entry: next bar open after signal.
    MAE/MFE: tracked over subsequent bars in entry TF.
    """
    # Pre-compute ATR for each pair (from 15min data)
    atr_data: dict[str, pd.Series] = {}
    for pair in pair_data_entry:
        # Resample entry TF to ATR timeframe
        df = pair_data_entry[pair]
        atr_df = resample_ohlcv(df, atr_tf)
        atr_data[pair] = calculate_atr(atr_df, ATR_PERIOD)

    trade_paths = []

    for sig in signals:
        pair = sig.pair
        if pair not in pair_data_entry:
            continue
        if pair not in atr_data:
            continue

        df = pair_data_entry[pair]
        # Entry at next bar's open
        entry_bar = sig.bar_idx + 1
        if entry_bar >= len(df):
            continue

        entry_price = df["open"].iloc[entry_bar]
        if np.isnan(entry_price) or entry_price <= 0:
            continue

        # Get ATR at signal time
        atr_series = atr_data[pair]
        ts_signal = sig.timestamp
        atr_valid = atr_series[atr_series.index <= ts_signal]
        if len(atr_valid) == 0:
            continue
        atr_val = atr_valid.iloc[-1]
        if np.isnan(atr_val) or atr_val <= 0:
            continue

        # Initial stop: 3 ATR (pre-registered)
        initial_stop_distance = 3.0 * atr_val
        pip_mult = 100.0 if "JPY" in pair else 10000.0

        # Track price path
        path_end = min(entry_bar + max_lookahead_bars, len(df))
        path_slice = df.iloc[entry_bar:path_end]
        if len(path_slice) < 2:
            continue

        high_path = path_slice["high"].values
        low_path = path_slice["low"].values
        close_path = path_slice["close"].values

        if sig.direction == 1:  # BUY
            adverse = entry_price - low_path
            favorable = high_path - entry_price
        else:  # SELL
            adverse = high_path - entry_price
            favorable = entry_price - low_path

        # Convert to R-multiples
        if initial_stop_distance > 0:
            adverse_r = adverse / initial_stop_distance
            favorable_r = favorable / initial_stop_distance
        else:
            continue

        mae_r = float(np.max(adverse_r))
        mfe_r = float(np.max(favorable_r))
        mae_pips = float(np.max(adverse)) * pip_mult
        mfe_pips = float(np.max(favorable)) * pip_mult

        bars_to_mae = int(np.argmax(adverse_r)) + 1
        bars_to_mfe = int(np.argmax(favorable_r)) + 1

        max_r = mfe_r - mae_r  # net R excursion

        # Excursion at specific horizons (in pips from entry)
        bars_per_unit = {"5min": 1, "15min": 3, "30min": 6, "1h": 12, "4h": 48, "1d": 288}
        excursion_at = {}
        for h_name, h_bars in bars_per_unit.items():
            if h_bars < len(path_slice):
                if sig.direction == 1:
                    exc = (close_path[h_bars] - entry_price) * pip_mult
                else:
                    exc = (entry_price - close_path[h_bars]) * pip_mult
                excursion_at[h_name] = round(float(exc), 4)
            else:
                excursion_at[h_name] = None

        trade_paths.append(TradePath(
            signal=sig, entry_price=entry_price, atr_at_entry=atr_val,
            initial_stop_distance=initial_stop_distance, pip_mult=pip_mult,
            mae_r=mae_r, mfe_r=mfe_r, mae_pips=mae_pips, mfe_pips=mfe_pips,
            bars_to_mae=bars_to_mae, bars_to_mfe=bars_to_mfe, max_r_reached=max_r,
            excursion_at=excursion_at,
        ))

    return trade_paths


# ═══════════════════════════════════════════════════════════════════════
# TIMEFRAME MANAGEMENT TEST (HG-1D)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ManagementResult:
    name: str
    n_trades: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    median_r: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    max_dd_r: float = 0.0
    mfe_p50: float = 0.0
    mfe_p90: float = 0.0
    mfe_p99: float = 0.0
    pct_top1: float = 0.0
    pct_top5: float = 0.0
    pct_top10: float = 0.0
    largest_winner: float = 0.0
    largest_loser: float = 0.0
    avg_hold_bars: float = 0.0
    r_distribution: list = field(default_factory=list)


def simulate_management(
    trade_paths: list[TradePath],
    pair_data_entry: dict[str, pd.DataFrame],
    management_name: str,
    exit_tf_schedule: list[str],
) -> ManagementResult:
    """
    Simulate a management ladder.

    exit_tf_schedule: list of timeframes to check for exit.
    E.g., ["5min"] = M0, ["5min","15min"] = M1, etc.

    At each higher TF, check if price has reached stop or if signal reverses.
    If not, continue to next TF. Final TF uses trailing stop or fixed exit.
    """
    # For simplicity in HG-1: use fixed exit at the last TF's bar
    # The "management" is how long we hold and what we see

    results_r = []
    hold_bars = []

    for tp in trade_paths:
        pair = tp.signal.pair
        if pair not in pair_data_entry:
            continue

        df = pair_data_entry[pair]
        entry_bar = tp.signal.bar_idx + 1

        # Determine exit bar based on management schedule
        # Using 5min bars: 1h=12, 4h=48, 1d=288, 2d=576, 5d=1440
        # M4: exit at 5d (7200 bars)

        tf_exit_map = {
            "5min": 1, "15min": 3, "30min": 6,
            "1h": 12, "4h": 48, "1d": 288,
        }

        # Exit at the LAST timeframe in the schedule
        last_tf = exit_tf_schedule[-1]
        exit_bars = tf_exit_map.get(last_tf, 60)

        exit_bar = min(entry_bar + exit_bars, len(df) - 1)
        if exit_bar <= entry_bar:
            continue

        # PnL in R
        entry_price = df["open"].iloc[entry_bar]
        exit_price = df["close"].iloc[exit_bar]

        if tp.signal.direction == 1:
            pnl_pips = (exit_price - entry_price) * tp.pip_mult
        else:
            pnl_pips = (entry_price - exit_price) * tp.pip_mult

        pnl_r = pnl_pips / (tp.initial_stop_distance * tp.pip_mult) if tp.initial_stop_distance > 0 else 0

        results_r.append(pnl_r)
        hold_bars.append(exit_bar - entry_bar)

    if not results_r:
        return ManagementResult(name=management_name)

    r_arr = np.array(results_r)
    wins = r_arr[r_arr > 0]
    losses = r_arr[r_arr <= 0]

    # Max drawdown in R
    cum = np.cumsum(r_arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    # Profit factor
    gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 1e-10
    pf = gross_profit / gross_loss

    # Top percentages
    sorted_r = np.sort(r_arr)[::-1]
    n = len(sorted_r)
    top1_idx = max(1, int(n * 0.01))
    top5_idx = max(1, int(n * 0.05))
    top10_idx = max(1, int(n * 0.10))
    top1_sum = float(np.sum(sorted_r[:top1_idx]))
    top5_sum = float(np.sum(sorted_r[:top5_idx]))
    top10_sum = float(np.sum(sorted_r[:top10_idx]))
    total_sum = float(np.sum(r_arr))

    return ManagementResult(
        name=management_name,
        n_trades=n,
        win_rate=float(np.mean(r_arr > 0)),
        avg_r=float(np.mean(r_arr)),
        median_r=float(np.median(r_arr)),
        expectancy=float(np.mean(r_arr)),
        profit_factor=pf,
        max_dd_r=max_dd,
        mfe_p50=float(np.percentile(r_arr, 50)),
        mfe_p90=float(np.percentile(r_arr, 90)),
        mfe_p99=float(np.percentile(r_arr, 99)),
        pct_top1=top1_sum / total_sum * 100 if total_sum > 0 else 0,
        pct_top5=top5_sum / total_sum * 100 if total_sum > 0 else 0,
        pct_top10=top10_sum / total_sum * 100 if total_sum > 0 else 0,
        largest_winner=float(np.max(r_arr)),
        largest_loser=float(np.min(r_arr)),
        avg_hold_bars=float(np.mean(hold_bars)),
        r_distribution=r_arr.tolist(),
    )


# ═══════════════════════════════════════════════════════════════════════
# ATR STOP TEST (HG-1E)
# ═══════════════════════════════════════════════════════════════════════

def test_atr_stops(
    signals: list[ICSASignal],
    pair_data_entry: dict[str, pd.DataFrame],
    atr_multiples: list[float] = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
) -> dict[str, Any]:
    """Test different ATR stop distances."""
    results = {}

    # Pre-compute ATR
    atr_data: dict[str, pd.Series] = {}
    for pair, df in pair_data_entry.items():
        atr_df = resample_ohlcv(df, "15min")
        atr_data[pair] = calculate_atr(atr_df, ATR_PERIOD)

    for mult in atr_multiples:
        mult_key = f"{mult:.1f}ATR"
        mae_list = []
        mfe_list = []
        hit_sl = 0
        reach_1r = 0
        reach_2r = 0
        reach_5r = 0
        reach_10r = 0
        total = 0

        for sig in signals:
            pair = sig.pair
            if pair not in pair_data_entry or pair not in atr_data:
                continue

            df = pair_data_entry[pair]
            entry_bar = sig.bar_idx + 1
            if entry_bar >= len(df):
                continue

            entry_price = df["open"].iloc[entry_bar]
            if np.isnan(entry_price) or entry_price <= 0:
                continue

            atr_series = atr_data[pair]
            atr_valid = atr_series[atr_series.index <= sig.timestamp]
            if len(atr_valid) == 0:
                continue
            atr_val = atr_valid.iloc[-1]
            if np.isnan(atr_val) or atr_val <= 0:
                continue

            stop_dist = mult * atr_val
            pip_mult = 100.0 if "JPY" in pair else 10000.0

            # Track path up to 1 day (1440 bars of 1min)
            path_len = min(1440, len(df) - entry_bar)
            if path_len < 10:
                continue

            high_path = df["high"].iloc[entry_bar:entry_bar + path_len].values
            low_path = df["low"].iloc[entry_bar:entry_bar + path_len].values

            if sig.direction == 1:
                adverse = entry_price - low_path
                favorable = high_path - entry_price
            else:
                adverse = high_path - entry_price
                favorable = entry_price - low_path

            adverse_r = adverse / stop_dist if stop_dist > 0 else adverse * 0
            favorable_r = favorable / stop_dist if stop_dist > 0 else favorable * 0

            this_mae = float(np.max(adverse_r))
            this_mfe = float(np.max(favorable_r))

            mae_list.append(this_mae)
            mfe_list.append(this_mfe)
            total += 1

            if this_mae >= 1.0:
                hit_sl += 1
            if this_mfe >= 1.0:
                reach_1r += 1
            if this_mfe >= 2.0:
                reach_2r += 1
            if this_mfe >= 5.0:
                reach_5r += 1
            if this_mfe >= 10.0:
                reach_10r += 1

        if total > 0:
            mae_arr = np.array(mae_list)
            mfe_arr = np.array(mfe_list)
            results[mult_key] = {
                "n": total,
                "stop_out_pct": round(hit_sl / total * 100, 1),
                "reach_1r_pct": round(reach_1r / total * 100, 1),
                "reach_2r_pct": round(reach_2r / total * 100, 1),
                "reach_5r_pct": round(reach_5r / total * 100, 1),
                "reach_10r_pct": round(reach_10r / total * 100, 1),
                "median_mae_r": round(float(np.median(mae_arr)), 3),
                "median_mfe_r": round(float(np.median(mfe_arr)), 3),
                "avg_mae_r": round(float(np.mean(mae_arr)), 3),
                "avg_mfe_r": round(float(np.mean(mfe_arr)), 3),
            }

    return results


# ═══════════════════════════════════════════════════════════════════════
# CONTROL EXPERIMENT
# ═══════════════════════════════════════════════════════════════════════

def generate_controls(
    tradeable_pairs: list[str],
    pair_data_entry: dict[str, pd.DataFrame],
    strength: pd.DataFrame,
    seed: int = RNG_SEED,
) -> dict[str, list[ICSASignal]]:
    """Generate control signal groups."""
    rng = np.random.RandomState(seed)

    # CONTROL B: Simple trend signal (price > EMA20 → BUY, price < EMA20 → SELL)
    trend_signals = []
    for pair in tradeable_pairs:
        if pair not in pair_data_entry:
            continue
        df = pair_data_entry[pair]
        if len(df) < 50:
            continue
        ema20 = df["close"].ewm(span=20).mean()
        for i in range(50, len(df) - 1, SIGNAL_COOLDOWN_BARS):
            price = df["close"].iloc[i]
            ema_val = ema20.iloc[i]
            if np.isnan(ema_val) or np.isnan(price):
                continue
            ts = df.index[i]
            direction = 1 if price > ema_val else -1
            # Estimate strength from price-EMA distance
            strength_val = (price - ema_val) / ema_val * 10000
            trend_signals.append(ICSASignal(
                pair=pair, direction=direction, timestamp=ts, bar_idx=i,
                base_strength=strength_val if direction == 1 else -strength_val,
                quote_strength=-strength_val if direction == 1 else strength_val,
                divergence=strength_val * 2 * direction,
                abs_divergence=abs(strength_val * 2),
            ))

    # CONTROL C: Random direction
    random_signals = []
    for pair in tradeable_pairs:
        if pair not in pair_data_entry:
            continue
        df = pair_data_entry[pair]
        if len(df) < 50:
            continue
        n_signals = len(range(50, len(df) - 1, SIGNAL_COOLDOWN_BARS))
        random_dirs = rng.choice([-1, 1], size=n_signals)
        for idx, i in enumerate(range(50, len(df) - 1, SIGNAL_COOLDOWN_BARS)):
            ts = df.index[i]
            d = random_dirs[idx]
            random_signals.append(ICSASignal(
                pair=pair, direction=d, timestamp=ts, bar_idx=i,
                base_strength=0.0, quote_strength=0.0,
                divergence=0.0, abs_divergence=0.0,
            ))

    return {
        "ICSA": [],  # filled by caller
        "TREND": trend_signals,
        "RANDOM": random_signals,
    }


def run_control_comparison(
    trade_paths_icSA: list[TradePath],
    trade_paths_trend: list[TradePath],
    trade_paths_random: list[TradePath],
) -> dict[str, Any]:
    """Compare ICSA vs trend vs random controls."""
    def summarize_paths(paths: list[TradePath], name: str) -> dict:
        if not paths:
            return {"name": name, "n": 0}
        mfe_arr = np.array([p.mfe_r for p in paths])
        mae_arr = np.array([p.mae_r for p in paths])
        return {
            "name": name,
            "n": len(paths),
            "avg_mfe_r": round(float(np.mean(mfe_arr)), 3),
            "median_mfe_r": round(float(np.median(mfe_arr)), 3),
            "avg_mae_r": round(float(np.mean(mae_arr)), 3),
            "median_mae_r": round(float(np.median(mae_arr)), 3),
            "pct_reach_3r": round(float(np.mean(mfe_arr >= 3.0)) * 100, 1),
            "pct_reach_5r": round(float(np.mean(mfe_arr >= 5.0)) * 100, 1),
            "pct_reach_10r": round(float(np.mean(mfe_arr >= 10.0)) * 100, 1),
            "pct_reach_20r": round(float(np.mean(mfe_arr >= 20.0)) * 100, 1),
            "avg_mfe_pips": round(float(np.mean([p.mfe_pips for p in paths])), 2),
            "median_mfe_pips": round(float(np.median([p.mfe_pips for p in paths])), 2),
        }

    return {
        "ICSA": summarize_paths(trade_paths_icSA, "ICSA"),
        "TREND": summarize_paths(trade_paths_trend, "TREND"),
        "RANDOM": summarize_paths(trade_paths_random, "RANDOM"),
    }


# ═══════════════════════════════════════════════════════════════════════
# PERMUTATION TEST
# ═══════════════════════════════════════════════════════════════════════

def permutation_test_mfe(
    trade_paths: list[TradePath],
    n_perm: int = N_PERM,
    seed: int = RNG_SEED,
) -> dict:
    """Permutation test: shuffle ICSA direction labels, recompute MFE."""
    rng = np.random.RandomState(seed)
    actual_mfe = np.array([p.mfe_r for p in trade_paths])
    actual_mean = float(np.mean(actual_mfe))

    # For permutation, shuffle the direction label
    actual_dirs = np.array([p.signal.direction for p in trade_paths])
    null_means = np.empty(n_perm)

    for i in range(n_perm):
        shuffled_dirs = rng.permutation(actual_dirs)
        # Recompute MFE with shuffled direction
        null_mfe = np.empty(len(trade_paths))
        for j, tp in enumerate(trade_paths):
            if shuffled_dirs[j] == tp.signal.direction:
                null_mfe[j] = tp.mfe_r
            else:
                # Flip the MFE (opposite direction)
                null_mfe[j] = tp.mae_r  # approximate: MFE of opposite direction ≈ MAE
        null_means[i] = float(np.mean(null_mfe))

    p_value = float(np.mean(np.abs(null_means) >= np.abs(actual_mean)))
    return {
        "observed_mean_mfe": round(actual_mean, 4),
        "null_mean": round(float(np.mean(null_means)), 4),
        "null_std": round(float(np.std(null_means)), 4),
        "p_value": round(p_value, 6),
    }


# ═══════════════════════════════════════════════════════════════════════
# TIME STABILITY
# ═══════════════════════════════════════════════════════════════════════

def analyze_time_stability(trade_paths: list[TradePath]) -> dict:
    """Break results into time periods."""
    periods = {
        "2016-2018": ("2016-01-01", "2018-12-31"),
        "2019-2021": ("2019-01-01", "2021-12-31"),
        "2022-2024": ("2022-01-01", "2024-12-31"),
        "2025-2026": ("2025-01-01", "2026-12-31"),
    }

    period_results = {}
    for name, (start, end) in periods.items():
        subset = [tp for tp in trade_paths
                  if start <= str(tp.signal.timestamp.date()) <= end]
        if not subset:
            period_results[name] = {"n": 0}
            continue
        mfe_arr = np.array([tp.mfe_r for tp in subset])
        mae_arr = np.array([tp.mae_r for tp in subset])
        period_results[name] = {
            "n": len(subset),
            "avg_mfe_r": round(float(np.mean(mfe_arr)), 3),
            "median_mfe_r": round(float(np.median(mfe_arr)), 3),
            "avg_mae_r": round(float(np.mean(mae_arr)), 3),
            "pct_reach_5r": round(float(np.mean(mfe_arr >= 5.0)) * 100, 1),
            "pct_reach_10r": round(float(np.mean(mfe_arr >= 10.0)) * 100, 1),
        }

    # Year-by-year
    year_results = {}
    for year in range(2016, 2027):
        subset = [tp for tp in trade_paths
                  if str(tp.signal.timestamp.year) == str(year)]
        if not subset:
            year_results[str(year)] = {"n": 0}
            continue
        mfe_arr = np.array([tp.mfe_r for tp in subset])
        year_results[str(year)] = {
            "n": len(subset),
            "avg_mfe_r": round(float(np.mean(mfe_arr)), 3),
            "median_mfe_r": round(float(np.median(mfe_arr)), 3),
            "pct_reach_5r": round(float(np.mean(mfe_arr >= 5.0)) * 100, 1),
        }

    return {"periods": period_results, "year_by_year": year_results}


# ═══════════════════════════════════════════════════════════════════════
# FIGURES
# ═══════════════════════════════════════════════════════════════════════

def generate_figures(results: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    # Fig 1: MFE distribution (R-multiples)
    paths = results.get("trade_paths_summary", {})
    if "mfe_r_values" in paths:
        mfe = np.array(paths["mfe_r_values"])
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(mfe, bins=50, alpha=0.7, edgecolor="black")
        ax.axvline(x=0, color="red", linewidth=1)
        ax.set_xlabel("MFE (R-multiples)")
        ax.set_ylabel("Count")
        ax.set_title(f"HG-1: MFE Distribution (n={len(mfe)}, median={np.median(mfe):.2f}R)")
        plt.tight_layout()
        plt.savefig(fig_dir / "01_mfe_distribution.png", dpi=150)
        plt.close()

    # Fig 2: MAE vs MFE scatter
    if "mae_r_values" in paths and "mfe_r_values" in paths:
        mae = np.array(paths["mae_r_values"])
        mfe = np.array(paths["mfe_r_values"])
        # Subsample for plotting
        n_plot = min(5000, len(mfe))
        idx = np.random.RandomState(42).choice(len(mfe), n_plot, replace=False)
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.scatter(mae[idx], mfe[idx], alpha=0.3, s=10)
        ax.plot([0, 20], [0, 20], "r--", linewidth=1, label="MFE=MAE")
        ax.set_xlabel("MAE (R)")
        ax.set_ylabel("MFE (R)")
        ax.set_title("HG-1: MAE vs MFE")
        ax.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "02_mae_vs_mfe.png", dpi=150)
        plt.close()

    # Fig 3: ATR stop test
    atr_test = results.get("atr_stop_test", {})
    if atr_test:
        mults = sorted(atr_test.keys(), key=lambda x: float(x.replace("ATR", "")))
        reach_5r = [atr_test[m]["reach_5r_pct"] for m in mults]
        stop_out = [atr_test[m]["stop_out_pct"] for m in mults]
        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax2 = ax1.twinx()
        ax1.plot(range(len(mults)), reach_5r, "g-o", label="Reach +5R %")
        ax2.plot(range(len(mults)), stop_out, "r-s", label="Stop-out %")
        ax1.set_xticks(range(len(mults)))
        ax1.set_xticklabels(mults)
        ax1.set_ylabel("Reach +5R (%)", color="green")
        ax2.set_ylabel("Stop-out (%)", color="red")
        ax1.set_title("HG-1E: ATR Stop Distance Analysis")
        ax1.legend(loc="upper left")
        ax2.legend(loc="upper right")
        plt.tight_layout()
        plt.savefig(fig_dir / "03_atr_stop_analysis.png", dpi=150)
        plt.close()

    # Fig 4: Management comparison
    mgmt = results.get("management_comparison", {})
    if mgmt:
        names = list(mgmt.keys())
        avg_rs = [mgmt[n]["avg_r"] for n in names]
        wrs = [mgmt[n]["win_rate"] * 100 for n in names]
        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax2 = ax1.twinx()
        x = range(len(names))
        ax1.bar([i - 0.15 for i in x], avg_rs, 0.3, label="Avg R", color="steelblue")
        ax2.bar([i + 0.15 for i in x], wrs, 0.3, label="Win Rate %", color="coral")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(names)
        ax1.set_ylabel("Average R")
        ax2.set_ylabel("Win Rate (%)")
        ax1.set_title("HG-1D: Timeframe Management Comparison")
        ax1.legend(loc="upper left")
        ax2.legend(loc="upper right")
        plt.tight_layout()
        plt.savefig(fig_dir / "04_management_comparison.png", dpi=150)
        plt.close()

    # Fig 5: Control comparison
    ctrl = results.get("control_comparison", {})
    if ctrl:
        names = list(ctrl.keys())
        avg_mfe = [ctrl[n].get("avg_mfe_r", 0) for n in names]
        pct5r = [ctrl[n].get("pct_reach_5r", 0) for n in names]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        ax1.bar(names, avg_mfe, color=["green", "blue", "gray"])
        ax1.set_ylabel("Average MFE (R)")
        ax1.set_title("Average MFE by Signal Type")
        ax2.bar(names, pct5r, color=["green", "blue", "gray"])
        ax2.set_ylabel("% Reaching +5R")
        ax2.set_title("% Signals Reaching +5R")
        plt.suptitle("HG-1: ICSA vs Trend vs Random Control")
        plt.tight_layout()
        plt.savefig(fig_dir / "05_control_comparison.png", dpi=150)
        plt.close()

    # Fig 6: Year-by-year MFE
    ts = results.get("time_stability", {})
    yby = ts.get("year_by_year", {})
    if yby:
        years = sorted([y for y in yby.keys() if yby[y].get("n", 0) > 0])
        avg_mfes = [yby[y].get("avg_mfe_r", 0) for y in years]
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = ["green" if v > 0 else "red" for v in avg_mfes]
        ax.bar(years, avg_mfes, color=colors, alpha=0.7)
        ax.set_ylabel("Average MFE (R)")
        ax.set_title("HG-1: Year-by-Year Average MFE")
        ax.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()
        plt.savefig(fig_dir / "06_year_by_year_mfe.png", dpi=150)
        plt.close()

    print(f"  Figures saved to {fig_dir}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Phase HG-1: Holy Grail / ICSA Framework Validation")
    print("Hypothesis isolation, not strategy development.")
    print("=" * 70)

    out_dir = Path("/root/nestquant/research_data/phase_hg1")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data ──────────────────────────────────────────────────────
    print("\n[1] Loading 1-minute data...")
    pair_data_1min = load_1min_data(ALL_PAIRS)
    print(f"  Loaded {len(pair_data_1min)} pairs")

    # Resample to entry timeframe (5min)
    print("\n[2] Resampling to entry timeframe (5min)...")
    pair_data_entry = {}
    for pair, df in pair_data_1min.items():
        pair_data_entry[pair] = resample_ohlcv(df, ENTRY_TF)
    print(f"  Resampled {len(pair_data_entry)} pairs to 5min")

    # ── HG-1A: Currency Strength ───────────────────────────────────────
    print("\n[3] HG-1A: Computing currency strength...")
    strength = compute_strength(pair_data_entry)
    print(f"  Strength shape: {strength.shape}")
    print(f"  Currencies: {list(strength.columns)}")

    # ── HG-1B: ICSA Signals ────────────────────────────────────────────
    print("\n[4] HG-1B: Generating ICSA signals...")
    tradeable_pairs = [p for p in ALL_PAIRS if "/" in p]
    signals = generate_icsa_signals(strength, tradeable_pairs)
    print(f"  Generated {len(signals)} ICSA signals")

    if signals:
        buy_count = sum(1 for s in signals if s.direction == 1)
        sell_count = sum(1 for s in signals if s.direction == -1)
        print(f"  BUY: {buy_count}, SELL: {sell_count}")
        avg_div = np.mean([s.abs_divergence for s in signals])
        print(f"  Avg divergence: {avg_div:.2f}")

    # ── HG-1C: Price-Path Distribution ─────────────────────────────────
    print("\n[5] HG-1C: Computing trade paths (MAE/MFE)...")
    trade_paths = compute_trade_paths(signals, pair_data_entry)
    print(f"  Computed {len(trade_paths)} trade paths")

    if trade_paths:
        mfe_arr = np.array([tp.mfe_r for tp in trade_paths])
        mae_arr = np.array([tp.mae_r for tp in trade_paths])
        print(f"\n  MFE (R): mean={np.mean(mfe_arr):.3f}, median={np.median(mfe_arr):.3f}, "
              f"p90={np.percentile(mfe_arr, 90):.3f}, p99={np.percentile(mfe_arr, 99):.3f}")
        print(f"  MAE (R): mean={np.mean(mae_arr):.3f}, median={np.median(mae_arr):.3f}")

        # R-multiple reach probabilities
        for r_thresh in [1, 2, 3, 5, 10, 20]:
            pct = np.mean(mfe_arr >= r_thresh) * 100
            print(f"  P(MFE >= +{r_thresh}R) = {pct:.1f}%")

        # Right-tail concentration
        sorted_mfe = np.sort(mfe_arr)[::-1]
        total_profit = np.sum(mfe_arr)
        top1_n = max(1, int(len(sorted_mfe) * 0.01))
        top5_n = max(1, int(len(sorted_mfe) * 0.05))
        top10_n = max(1, int(len(sorted_mfe) * 0.10))
        print(f"\n  Top 1% of trades generate: {np.sum(sorted_mfe[:top1_n]) / total_profit * 100:.1f}% of total MFE")
        print(f"  Top 5% of trades generate: {np.sum(sorted_mfe[:top5_n]) / total_profit * 100:.1f}% of total MFE")
        print(f"  Top 10% of trades generate: {np.sum(sorted_mfe[:top10_n]) / total_profit * 100:.1f}% of total MFE")

    # ── HG-1D: Timeframe Management ────────────────────────────────────
    print("\n[6] HG-1D: Timeframe management test...")
    mgmt_schedules = {
        "M0_entry_only": ["5min"],
        "M1_to_15m": ["5min", "15min"],
        "M2_to_1h": ["5min", "15min", "1h"],
        "M3_to_4h": ["5min", "15min", "1h", "4h"],
        "M4_to_1d": ["5min", "15min", "1h", "4h", "1d"],
    }
    mgmt_results = {}
    for name, schedule in mgmt_schedules.items():
        result = simulate_management(trade_paths, pair_data_entry, name, schedule)
        mgmt_results[name] = {
            "n_trades": result.n_trades,
            "win_rate": round(result.win_rate, 4),
            "avg_r": round(result.avg_r, 4),
            "median_r": round(result.median_r, 4),
            "expectancy": round(result.expectancy, 4),
            "profit_factor": round(result.profit_factor, 4),
            "max_dd_r": round(result.max_dd_r, 4),
            "pct_top1": round(result.pct_top1, 1),
            "pct_top5": round(result.pct_top5, 1),
            "pct_top10": round(result.pct_top10, 1),
            "largest_winner": round(result.largest_winner, 4),
            "largest_loser": round(result.largest_loser, 4),
            "avg_hold_bars": round(result.avg_hold_bars, 1),
        }
        print(f"  {name}: n={result.n_trades}, WR={result.win_rate:.1%}, "
              f"AvgR={result.avg_r:.3f}, PF={result.profit_factor:.2f}")

    # ── HG-1E: ATR Stop Test ───────────────────────────────────────────
    print("\n[7] HG-1E: ATR stop test...")
    # Subsample signals for speed (every 4th signal)
    signals_subsample = signals[::4]
    print(f"  Using {len(signals_subsample)} signals (1/4 subsample)")
    atr_results = test_atr_stops(signals_subsample, pair_data_entry)
    for mult_key, data in sorted(atr_results.items()):
        print(f"  {mult_key}: n={data['n']}, SL={data['stop_out_pct']:.0f}%, "
              f"+5R={data['reach_5r_pct']:.0f}%, medMAE={data['median_mae_r']:.2f}, "
              f"medMFE={data['median_mfe_r']:.2f}")

    # ── Control Experiment ──────────────────────────────────────────────
    print("\n[8] Control experiment: ICSA vs Trend vs Random...")
    controls = generate_controls(tradeable_pairs, pair_data_entry, strength)
    # Subsample controls for speed
    controls["TREND"] = controls["TREND"][::4]
    controls["RANDOM"] = controls["RANDOM"][::4]
    # Compute trade paths for controls
    tp_trend = compute_trade_paths(controls["TREND"], pair_data_entry)
    tp_random = compute_trade_paths(controls["RANDOM"], pair_data_entry)
    control_results = run_control_comparison(trade_paths, tp_trend, tp_random)
    for name, data in control_results.items():
        print(f"  {name}: n={data.get('n', 0)}, avgMFE={data.get('avg_mfe_r', 0):.3f}, "
              f"+5R={data.get('pct_reach_5r', 0):.1f}%, "
              f"+10R={data.get('pct_reach_10r', 0):.1f}%")

    # ── Permutation Test ───────────────────────────────────────────────
    print("\n[9] Permutation test...")
    perm = permutation_test_mfe(trade_paths)
    print(f"  Observed MFE: {perm['observed_mean_mfe']:.4f}")
    print(f"  Null: {perm['null_mean']:.4f} ± {perm['null_std']:.4f}")
    print(f"  p-value: {perm['p_value']:.4f}")

    # ── Time Stability ─────────────────────────────────────────────────
    print("\n[10] Time stability analysis...")
    time_stability = analyze_time_stability(trade_paths)
    for period, data in time_stability["periods"].items():
        if data.get("n", 0) > 0:
            print(f"  {period}: n={data['n']}, avgMFE={data['avg_mfe_r']:.3f}, "
                  f"+5R={data['pct_reach_5r']:.1f}%")

    # ── Classification ─────────────────────────────────────────────────
    print("\n[11] Classification...")

    has_right_tail = False
    has_icSA_edge = False
    has_mgmt_benefit = False

    if trade_paths:
        mfe_arr = np.array([tp.mfe_r for tp in trade_paths])
        # Right tail: do at least 5% of trades reach +5R?
        pct_5r = float(np.mean(mfe_arr >= 5.0))
        has_right_tail = pct_5r >= 0.05

        # ICSA edge: does ICSA beat random control?
        if control_results.get("ICSA", {}).get("avg_mfe_r", 0) > \
           control_results.get("RANDOM", {}).get("avg_mfe_r", 0) * 1.2:
            has_icSA_edge = True

        # Management benefit: does M4 beat M0?
        m0_avg = mgmt_results.get("M0_entry_only", {}).get("avg_r", 0)
        m4_avg = mgmt_results.get("M4_to_1d", {}).get("avg_r", 0)
        if m4_avg > m0_avg * 1.1:
            has_mgmt_benefit = True

    if has_right_tail and has_icSA_edge:
        classification = "B. STRUCTURAL SUPPORT — PROCEED TO ECONOMIC VALIDATION"
    elif has_right_tail or has_icSA_edge:
        classification = "C. AMBIGUOUS — PARTIAL STRUCTURE"
    else:
        classification = "A. NO STRUCTURAL SUPPORT — KILL THE FRAMEWORK"

    print(f"  Right tail exists: {has_right_tail}")
    print(f"  ICSA beats random: {has_icSA_edge}")
    print(f"  Management helps: {has_mgmt_benefit}")
    print(f"  Classification: {classification}")

    # ── Save ───────────────────────────────────────────────────────────
    # Prepare trade path summary
    tp_summary = {}
    if trade_paths:
        mfe_arr = np.array([tp.mfe_r for tp in trade_paths])
        mae_arr = np.array([tp.mae_r for tp in trade_paths])
        tp_summary = {
            "n_trades": len(trade_paths),
            "mfe_r_values": mfe_arr.tolist()[:10000],  # cap for JSON
            "mae_r_values": mae_arr.tolist()[:10000],
            "avg_mfe_r": round(float(np.mean(mfe_arr)), 4),
            "median_mfe_r": round(float(np.median(mfe_arr)), 4),
            "avg_mae_r": round(float(np.mean(mae_arr)), 4),
            "median_mae_r": round(float(np.median(mae_arr)), 4),
            "pct_reach_1r": round(float(np.mean(mfe_arr >= 1.0)) * 100, 1),
            "pct_reach_2r": round(float(np.mean(mfe_arr >= 2.0)) * 100, 1),
            "pct_reach_3r": round(float(np.mean(mfe_arr >= 3.0)) * 100, 1),
            "pct_reach_5r": round(float(np.mean(mfe_arr >= 5.0)) * 100, 1),
            "pct_reach_10r": round(float(np.mean(mfe_arr >= 10.0)) * 100, 1),
            "pct_reach_20r": round(float(np.mean(mfe_arr >= 20.0)) * 100, 1),
            "skewness": round(float(sp_stats.skew(mfe_arr)), 4),
            "kurtosis": round(float(sp_stats.kurtosis(mfe_arr)), 4),
        }

    results = {
        "phase": "HG-1",
        "title": "Holy Grail / ICSA Framework Validation",
        "entry_tf": ENTRY_TF,
        "strength_lookbacks": STRENGTH_LOOKBACKS,
        "strength_norm_window": STRENGTH_NORM_WINDOW,
        "strength_min_divergence": STRENGTH_MIN_DIVERGENCE,
        "atr_period": ATR_PERIOD,
        "signal_cooldown_bars": SIGNAL_COOLDOWN_BARS,
        "n_signals": len(signals),
        "n_trade_paths": len(trade_paths),
        "trade_paths_summary": tp_summary,
        "management_comparison": mgmt_results,
        "atr_stop_test": atr_results,
        "control_comparison": control_results,
        "permutation": perm,
        "time_stability": time_stability,
        "has_right_tail": has_right_tail,
        "has_icSA_edge": has_icSA_edge,
        "has_mgmt_benefit": has_mgmt_benefit,
        "classification": classification,
        "runtime_seconds": time.time() - t0,
    }

    # Remove large arrays for JSON
    if "trade_paths_summary" in results and "mfe_r_values" in results["trade_paths_summary"]:
        results["trade_paths_summary"]["mfe_r_values"] = \
            results["trade_paths_summary"]["mfe_r_values"][:1000]
        results["trade_paths_summary"]["mae_r_values"] = \
            results["trade_paths_summary"]["mae_r_values"][:1000]

    with open(out_dir / "phase_hg1_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n[12] Generating figures...")
    try:
        generate_figures(results, out_dir)
    except Exception as e:
        print(f"  Figure generation failed: {e}")

    print(f"\n{'=' * 70}")
    print(f"Phase HG-1 complete in {time.time() - t0:.1f}s")
    print(f"Classification: {classification}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
