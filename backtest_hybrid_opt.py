"""
backtest_hybrid_opt.py — Optimized System B Backtest
======================================================
Optimizations vs original:
  1. Pre-compute TF indices per 1M bar (eliminates np.searchsorted in main loop)
  2. Running min/max per trade for SL/TP (eliminates array slicing)
  3. Cached pair data lookups

Usage: same as backtest_hybrid.py
"""

import argparse
import logging
import os
import pickle
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np
import pandas as pd

from config import (
    TRADEABLE_PAIRS, ALL_PAIRS, MT5_DATA_CACHE, INITIAL_BALANCE,
    MAX_OPEN_TRADES, MAX_PER_CURRENCY_BLOCK,
    STRENGTH_LOOKBACKS, STRENGTH_TOP_N, STRENGTH_NORMALIZE_WINDOW,
    BACKTEST_N_JOBS, QUICK_TEST_PAIRS, QUICK_TEST_BARS,
    RISK_PER_TRADE, COMMISSION_PER_LOT,
    MIN_LOT_SIZE, MAX_LOT_SIZE,
    SPREAD_PIPS, DEFAULT_SPREAD_PIPS, SLIPPAGE_PIPS,
    ATR_SL_MULTIPLIER, RRR, MIN_DIVERGENCE, BREAKEVEN_RATIO,
    ENABLE_MACRO_FILTER, MACRO_EMA_PERIOD,
    SESSION_CLOSE_UTC, MAX_ENTRY_HOUR, SCALE_SL_AT_SESSION_CLOSE,
    SESSION_CLOSE_MINUTES_BEFORE, BLOCK_SAME_DIRECTION_REENTRY,
    CORRELATION_ENABLED, CORRELATION_WINDOW, CORRELATION_THRESHOLD,
    ENABLE_REGIME_FLIP, REGIME_ATR_MULTIPLIER, REGIME_LOOKBACK,
)
from currency_strength import CurrencyStrengthRanker
from indicators import is_active_session, calculate_atr, pip_size
from risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("hybrid_opt")

B_TF_LADDER = ["1min", "5min", "15min", "4h", "1D"]
B_TF_LABELS = ["1M", "5M", "15M", "4H", "1D"]

FOLDS = [
    {"train": ("2026-02-23", "2026-03-15"), "test": ("2026-03-16", "2026-04-05")},
    {"train": ("2026-02-23", "2026-04-05"), "test": ("2026-04-06", "2026-04-25")},
    {"train": ("2026-02-23", "2026-04-25"), "test": ("2026-04-26", "2026-05-30")},
]


def load_and_resample(quick: bool = False, pairs: List[str] = None) -> Dict[str, Dict[str, pd.DataFrame]]:
    """Load 1M data from individual pair pickles, resample to all TFs.
    Only one pair's data is in memory at a time, drastically reducing peak memory.
    Returns {tf: {pair: df}}."""
    import gc
    from download_dukascopy import MT5_DATA_CACHE as _cache_path
    data_dir = os.path.dirname(_cache_path)
    if pairs is None:
        from config import ALL_PAIRS as _all_pairs
        pairs = _all_pairs
    all_tfs: Dict[str, Dict[str, pd.DataFrame]] = {tf: {} for tf in B_TF_LADDER}
    logger.info(f"Loading & resampling from {data_dir}/<pair>.pkl ...")
    for pair in pairs:
        pair_key = pair.replace("/", "_")
        pair_path = os.path.join(data_dir, f"{pair_key}.pkl")
        if not os.path.exists(pair_path):
            logger.warning(f"  {pair}: no pickle at {pair_path}, skipping")
            continue
        with open(pair_path, "rb") as f:
            raw = pickle.load(f)
        df = raw.get(pair)
        if df is None or df.empty:
            continue
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        if quick and len(df) > QUICK_TEST_BARS:
            df = df.iloc[-QUICK_TEST_BARS:]
        all_tfs["1min"][pair] = df
        for tf in ["5min", "15min", "4h", "1D"]:
            resampled = pd.DataFrame()
            resampled["open"] = df["open"].resample(tf).first()
            resampled["high"] = df["high"].resample(tf).max()
            resampled["low"] = df["low"].resample(tf).min()
            resampled["close"] = df["close"].resample(tf).last()
            resampled.dropna(subset=["close"], inplace=True)
            all_tfs[tf][pair] = resampled
        del raw, df
        gc.collect()
    logger.info(f"Resampled {len(all_tfs['1min'])} pairs to TFs: {B_TF_LADDER}")
    return all_tfs


def precompute_strength(all_tfs: Dict[str, Dict[str, pd.DataFrame]], n_jobs: int = 1) -> Dict[str, pd.DataFrame]:
    strength: Dict[str, pd.DataFrame] = {}
    for tf, pair_data in all_tfs.items():
        logger.info(f"Computing strength for {tf}...")
        ranker = CurrencyStrengthRanker(
            lookbacks=STRENGTH_LOOKBACKS, top_n=STRENGTH_TOP_N,
            min_div=5.0, norm_window=STRENGTH_NORMALIZE_WINDOW,
        )
        sdf = ranker.calculate(pair_data)
        strength[tf] = sdf
    return strength


def precompute_signals_vectorized(
    strength: Dict[str, pd.DataFrame],
    tradeable_pairs: List[str],
    min_div: float,
    top_n: int,
    n_jobs: int = 1,
) -> tuple[Dict[str, pd.DataFrame], Dict[str, Dict[str, np.ndarray]]]:
    signals: Dict[str, pd.DataFrame] = {}
    signal_lookup: Dict[str, Dict[str, np.ndarray]] = {}
    currencies = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
    curr_to_idx = {c: i for i, c in enumerate(currencies)}
    bottom_threshold = len(currencies) - top_n
    for tf, sdf in strength.items():
        if tf == "1min":
            continue
        logger.info(f"Vectorizing signals for {tf} ({len(sdf)} bars)...")
        values = sdf.values
        ranks = np.argsort(np.argsort(-values, axis=1), axis=1)
        rows: list = []
        tf_lookup: Dict[str, np.ndarray] = {}
        for pair in tradeable_pairs:
            base, quote = pair.split("/")
            if base not in curr_to_idx or quote not in curr_to_idx:
                continue
            bi = curr_to_idx[base]; qi = curr_to_idx[quote]
            base_r = ranks[:, bi]; quote_r = ranks[:, qi]
            div = values[:, bi] - values[:, qi]
            buy_mask = (base_r < top_n) & (quote_r >= bottom_threshold) & (div >= min_div)
            sell_mask = (base_r >= bottom_threshold) & (quote_r < top_n) & (div <= -min_div)
            lookup = np.full(len(sdf), 'N', dtype='S1')
            lookup[buy_mask] = b'B'; lookup[sell_mask] = b'S'
            tf_lookup[pair] = lookup
            for idx in np.where(buy_mask)[0]:
                rows.append({"bar_idx": idx, "time": sdf.index[idx], "pair": pair, "signal": "BUY", "divergence": abs(round(float(div[idx]), 2))})
            for idx in np.where(sell_mask)[0]:
                rows.append({"bar_idx": idx, "time": sdf.index[idx], "pair": pair, "signal": "SELL", "divergence": abs(round(float(div[idx]), 2))})
        signal_lookup[tf] = tf_lookup
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("time").reset_index(drop=True)
        signals[tf] = df
    return signals, signal_lookup


def precompute_atrs(all_tfs: Dict[str, Dict[str, pd.DataFrame]], n_jobs: int = 1) -> Dict[str, Dict[str, np.ndarray]]:
    atr_cache: Dict[str, Dict[str, np.ndarray]] = {}
    def _atr_for_pair(tf_pair):
        tf, pair = tf_pair
        df = all_tfs[tf].get(pair)
        if df is None or df.empty:
            return (tf, pair, np.array([]))
        return (tf, pair, calculate_atr(df, 14).fillna(0).values)
    tasks = [(tf, pair) for tf in B_TF_LADDER for pair in all_tfs[tf]]
    if n_jobs <= 1 or len(tasks) < 10:
        results = [_atr_for_pair(t) for t in tasks]
    else:
        try:
            from joblib import Parallel, delayed
            results = Parallel(n_jobs=n_jobs, verbose=5)(delayed(_atr_for_pair)(t) for t in tasks)
        except Exception:
            results = [_atr_for_pair(t) for t in tasks]
    for tf in B_TF_LADDER:
        atr_cache[tf] = {}
    for tf, pair, arr in results:
        atr_cache[tf][pair] = arr
    return atr_cache


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMIZED HybridBacktest
# ══════════════════════════════════════════════════════════════════════════════

class HybridBacktest:
    """
    Optimized System B trend-follow scaling backtest.
    
    Key optimizations:
    - Pre-computed TF indices eliminate np.searchsorted in main loop
    - Running min/max per trade eliminates array slicing for SL/TP
    - Cached pair data lookups
    """

    def __init__(self, strength, signal_lookup, all_tfs, atr_cache):
        self.strength = strength
        self.signal_lookup = signal_lookup
        self.all_tfs = all_tfs
        self.atr_cache = atr_cache

        self.b_min_div = MIN_DIVERGENCE
        self.b_atr_sl = ATR_SL_MULTIPLIER
        self.b_rrr = RRR
        self.breakeven_ratio = BREAKEVEN_RATIO

        # Pre-compute pair data
        self.pair_data: Dict[str, Dict[str, dict]] = {}
        for tf in B_TF_LADDER:
            self.pair_data[tf] = {}
            for pair, df in all_tfs[tf].items():
                if df is not None and not df.empty:
                    self.pair_data[tf][pair] = {
                        "times": df.index.values,
                        "close": df["close"].values,
                        "high": df["high"].values,
                        "low": df["low"].values,
                    }

        # Macro filter
        self.macro_bullish_5m: Dict[str, np.ndarray] = {}
        if ENABLE_MACRO_FILTER:
            self._precompute_macro()

        # Regime flip
        self.enable_regime_flip = ENABLE_REGIME_FLIP
        self.regime_atr_multiplier = REGIME_ATR_MULTIPLIER
        self.regime_index: Dict[str, np.ndarray] = {}
        if self.enable_regime_flip:
            self._precompute_regime()

        # Dynamic correlation guard
        self._corr_lookup: Dict[pd.Timestamp, pd.DataFrame] = {}
        if CORRELATION_ENABLED:
            self._precompute_correlations()

    def _precompute_macro(self):
        for pair in TRADEABLE_PAIRS:
            d4 = self.all_tfs["4h"].get(pair)
            d5 = self.all_tfs["5min"].get(pair)
            if d4 is None or d4.empty or d5 is None or d5.empty:
                self.macro_bullish_5m[pair] = np.array([], dtype=bool)
                continue
            ema = d4["close"].ewm(span=MACRO_EMA_PERIOD, adjust=False).mean()
            macro_bull = d4["close"].values > ema.values
            d4_times = d4.index.values
            bull = np.zeros(len(d5), dtype=bool)
            for i, t in enumerate(d5.index):
                idx = np.searchsorted(d4_times, t.to_datetime64()) - 1
                if 0 <= idx < len(macro_bull):
                    bull[i] = macro_bull[idx]
            self.macro_bullish_5m[pair] = bull

    def _precompute_regime(self):
        for pair in TRADEABLE_PAIRS:
            d4 = self.all_tfs["4h"].get(pair)
            d5 = self.all_tfs["5min"].get(pair)
            if d4 is None or d4.empty or d5 is None or d5.empty:
                self.regime_index[pair] = np.array([], dtype=bool)
                continue
            atr4 = calculate_atr(d4, 14).fillna(0)
            atr_avg = atr4.rolling(REGIME_LOOKBACK, min_periods=5).mean().fillna(0)
            crisis = (atr4 > atr_avg * self.regime_atr_multiplier).values
            d4_times = d4.index.values
            regime = np.zeros(len(d5), dtype=bool)
            for i, t in enumerate(d5.index):
                idx = np.searchsorted(d4_times, t.to_datetime64()) - 1
                if 0 <= idx < len(crisis):
                    regime[i] = crisis[idx]
            self.regime_index[pair] = regime

    def _precompute_correlations(self):
        """Build rolling correlation lookup for tradeable pairs using daily returns.
        Stores {daily_timestamp: pd.DataFrame(corr_matrix)} for CORRELATION_WINDOW-day lookback."""
        self._corr_lookup: Dict[pd.Timestamp, pd.DataFrame] = {}
        daily_data = {}
        for pair in TRADEABLE_PAIRS:
            d = self.all_tfs.get("1D", {}).get(pair)
            if d is not None and not d.empty and len(d) >= CORRELATION_WINDOW:
                daily_data[pair] = d["close"]
        if len(daily_data) < 2:
            logger.warning("Correlation guard: <2 pairs with daily data — disabled")
            return
        df = pd.DataFrame(daily_data)
        returns = df.pct_change().dropna()
        for i in range(CORRELATION_WINDOW, len(returns)):
            date = returns.index[i]
            window = returns.iloc[i - CORRELATION_WINDOW : i]
            self._corr_lookup[date] = window.corr()
        logger.info(f"Correlation lookup built: {len(self._corr_lookup)} daily matrices")

    def _spread_cost(self, pair):
        sp = SPREAD_PIPS.get(pair, DEFAULT_SPREAD_PIPS)
        return (sp / 2.0 + SLIPPAGE_PIPS) * pip_size(pair)

    def _trend_intact(self, tf, pair, direction, bar_idx):
        lookup = self.signal_lookup.get(tf, {}).get(pair)
        if lookup is None or len(lookup) == 0:
            return False
        sdf = self.strength.get(tf)
        if sdf is None or sdf.empty:
            return False
        idx = self._signal_indices[tf][bar_idx]
        if idx < 0 or idx >= len(lookup):
            return False
        sig_byte = lookup[idx]
        return sig_byte == (b'B' if direction == "BUY" else b'S')

    def _get_pair_data(self, tf, pair):
        return self.pair_data.get(tf, {}).get(pair)

    def run(self, start_date: str, end_date: str) -> Dict:
        import gc
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)

        df_1m = next(iter(self.all_tfs["1min"].values()))
        all_times = df_1m.index.values
        mask = (all_times >= start.to_datetime64()) & (all_times < end.to_datetime64())
        timeline = all_times[mask]
        n_bars = len(timeline)

        # Free 1min data immediately (4.7 GB) — only needed for timeline above
        self.all_tfs["1min"] = {}
        del df_1m, all_times
        gc.collect()

        logger.info(f"Running backtest on {n_bars} 1M bars [{start_date} -> {end_date})")

        # ── PRECOMPUTE: Signal indices (aligned to strength DataFrame index) ──
        self._signal_indices: Dict[str, np.ndarray] = {"1min": np.arange(n_bars)}
        for tf in B_TF_LADDER:
            if tf == "1min":
                continue
            sdf = self.strength.get(tf)
            if sdf is not None and not sdf.empty:
                stimes = sdf.index.values
                self._signal_indices[tf] = np.searchsorted(stimes, timeline) - 1
            else:
                self._signal_indices[tf] = np.full(n_bars, -1, dtype=int)

        b_trades: List[dict] = []
        trade_log: List[Dict] = []
        balance = INITIAL_BALANCE
        peak_balance = INITIAL_BALANCE
        max_dd = 0.0
        b_wins = b_losses = 0
        b_promotions = 0
        recovery_pnl = 0.0

        risk_mgr = RiskManager(initial_balance=INITIAL_BALANCE)
        last_date = None

        def active_directions():
            return {t["pair"]: t["direction"] for t in b_trades}

        last_5m_bar = -1
        processed_5m = set()

        # Pre-extract pair data arrays for fast lookup during entry
        _sig_5m_lookup = self.signal_lookup.get("5min", {})
        _strength_5m = self.strength.get("5min")
        _strength_cols_5m = list(_strength_5m.columns) if _strength_5m is not None else []
        _strength_vals_5m = _strength_5m.values if _strength_5m is not None else None

        # Macro filter arrays
        _macro = self.macro_bullish_5m if ENABLE_MACRO_FILTER else {}
        # Regime flip arrays
        _regime_idx = self.regime_index if self.enable_regime_flip else {}
        _session_check = is_active_session

        for bar_idx in range(n_bars):
            bar_time_np = timeline[bar_idx]
            bar_time = pd.Timestamp(bar_time_np)

            # ── Daily reset ──
            current_date = bar_time.date()
            if last_date is None or current_date != last_date:
                risk_mgr.reset_daily()
                last_date = current_date

            # ── RESOLVE TRADES (optimized) ──
            still_open = []
            for t in b_trades:
                p = t["pair"]
                tf_key = t.get("tf_key", "5min")
                pd_info = self.pair_data.get(tf_key, {}).get(p)
                if pd_info is None:
                    still_open.append(t)
                    continue

                current_tf_idx = np.searchsorted(pd_info["times"], bar_time_np)
                entry_tf_idx = t.get("_entry_tf_idx", -1)
                if current_tf_idx <= entry_tf_idx:
                    still_open.append(t)
                    continue

                # Update running min/max if on a new TF bar
                last_tf_idx = t.get("_last_tf_idx", entry_tf_idx)
                if current_tf_idx > last_tf_idx:
                    ci = max(0, min(current_tf_idx - 1, len(pd_info["low"]) - 1))
                    t["_min_low"] = min(t.get("_min_low", float("inf")), float(pd_info["low"][ci]))
                    t["_max_high"] = max(t.get("_max_high", float("-inf")), float(pd_info["high"][ci]))
                    t["_last_tf_idx"] = current_tf_idx

                # Update _last_close on every bar using current TF bar close
                ci = max(0, min(current_tf_idx - 1, len(pd_info["close"]) - 1))
                t["_last_close"] = float(pd_info["close"][ci])

                hit_sl = False
                hit_tp = False
                if t["direction"] == "BUY":
                    if t.get("_min_low", float("inf")) <= t["sl"]:
                        hit_sl = True
                    if t.get("_max_high", float("-inf")) >= t["tp"]:
                        hit_tp = True
                else:
                    if t.get("_max_high", float("-inf")) >= t["sl"]:
                        hit_sl = True
                    if t.get("_min_low", float("inf")) <= t["tp"]:
                        hit_tp = True

                # Recovery check
                if not hit_sl and not hit_tp and recovery_pnl > 0:
                    current_price = t.get("_last_close")
                    if current_price is not None:
                        mult = 1 if t["direction"] == "BUY" else -1
                        floating_pnl = (current_price - t["entry_price"]) * mult
                        pip = pip_size(p)
                        pv = 9.09 if "JPY" in p else 10.0
                        floating_pnl_usd = round(floating_pnl / pip * pv * t["units"] - t["commission"], 2)
                        if floating_pnl_usd >= 0 and floating_pnl_usd >= recovery_pnl * 0.5:
                            balance += floating_pnl_usd
                            b_wins += 1 if floating_pnl_usd > 0 else 0
                            b_losses += 1 if floating_pnl_usd <= 0 else 0
                            recovery_pnl = max(0.0, recovery_pnl - floating_pnl_usd)
                            risk_mgr.record_trade(floating_pnl_usd)
                            trade_log.append(dict(system="B", pair=p, direction=t["direction"],
                                entry=t["entry_price"], exit=current_price, pnl=floating_pnl_usd,
                                result="WIN" if floating_pnl_usd > 0 else "LOSS",
                                entry_time=t["entry_time"], exit_time=bar_time,
                                units=t["units"], commission=t["commission"],
                                level=t.get("level", 0), note="recovery_exit"))
                            continue

                if hit_sl or hit_tp:
                    if hit_tp and not hit_sl:
                        t["promoting"] = True
                        still_open.append(t)
                    else:
                        exit_price = t["sl"] if hit_sl else t["tp"]
                        mult = 1 if t["direction"] == "BUY" else -1
                        diff = (exit_price - t["entry_price"]) * mult
                        pip = pip_size(p)
                        pv = 9.09 if "JPY" in p else 10.0
                        pnl = round(diff / pip * pv * t["units"] - t["commission"], 2)
                        balance += pnl
                        if pnl < 0:
                            b_losses += 1
                            recovery_pnl += abs(pnl)
                        else:
                            b_wins += 1
                        risk_mgr.record_trade(pnl)
                        trade_log.append(dict(system="B", pair=p, direction=t["direction"],
                            entry=t["entry_price"], exit=exit_price, pnl=pnl,
                            result="WIN" if pnl > 0 else "LOSS",
                            entry_time=t["entry_time"], exit_time=bar_time,
                            units=t["units"], commission=t["commission"],
                            level=t.get("level", 0)))
                else:
                    # Trend reversal check (level >= 1)
                    if t.get("level", 0) >= 1:
                        active_tf = B_TF_LADDER[t["level"] + 1] if t["level"] + 1 < len(B_TF_LADDER) else B_TF_LADDER[-1]
                        if not self._trend_intact(active_tf, p, t["direction"], bar_idx):
                            close_info = self.pair_data.get(tf_key, {}).get(p)
                            if close_info:
                                ci = np.searchsorted(close_info["times"], bar_time_np) - 1
                                ci = max(0, min(ci, len(close_info["close"]) - 1))
                                exit_price = float(close_info["close"][ci])
                                mult = 1 if t["direction"] == "BUY" else -1
                                diff = (exit_price - t["entry_price"]) * mult
                                pip = pip_size(p)
                                pv = 9.09 if "JPY" in p else 10.0
                                pnl = round(diff / pip * pv * t["units"] - t["commission"], 2)
                                balance += pnl
                                if pnl < 0:
                                    b_losses += 1
                                    recovery_pnl += abs(pnl)
                                else:
                                    b_wins += 1
                                risk_mgr.record_trade(pnl)
                                trade_log.append(dict(system="B", pair=p, direction=t["direction"],
                                    entry=t["entry_price"], exit=exit_price, pnl=pnl,
                                    result="WIN" if pnl > 0 else "LOSS",
                                    entry_time=t["entry_time"], exit_time=bar_time,
                                    units=t["units"], commission=t["commission"],
                                    level=t.get("level", 0), note="trend_reversal"))
                                continue
                    still_open.append(t)
            b_trades[:] = still_open

            # ── BREAKEVEN CHECK (optimized) ──
            for t in b_trades:
                if t.get("breakeven_done"):
                    continue
                tf_key = t.get("tf_key", "5min")
                current_price = t.get("_last_close")
                if current_price is None:
                    pd_info = self.pair_data.get(tf_key, {}).get(t["pair"])
                    if pd_info is not None:
                        ci = np.searchsorted(pd_info["times"], bar_time_np) - 1
                        ci = max(0, min(ci, len(pd_info["close"]) - 1))
                        current_price = float(pd_info["close"][ci])
                risk_distance = abs(t["entry_price"] - t["original_sl"])
                breakeven_threshold = self.breakeven_ratio * risk_distance
                if t["direction"] == "BUY":
                    profit = current_price - t["entry_price"]
                else:
                    profit = t["entry_price"] - current_price
                if profit >= breakeven_threshold:
                    t["sl"] = t["entry_price"]
                    t["breakeven_done"] = True

            # ── SCALING SL AT SESSION CLOSE (gap protection) ──
            if SCALE_SL_AT_SESSION_CLOSE and b_trades:
                close_hour = SESSION_CLOSE_UTC - 1
                close_min = 60 - SESSION_CLOSE_MINUTES_BEFORE
                if bar_time.hour >= close_hour and bar_time.minute >= close_min:
                    for t in b_trades:
                        if not t.get("sl_scaled") and t.get("entry_price") is not None:
                            t["sl"] = t["entry_price"]
                            t["sl_scaled"] = True
                            logger.debug(
                                f"Session close: {t['pair']} SL moved to breakeven "
                                f"(${t['entry_price']})"
                            )

            # ── ENTRY SIGNALS (optimized) ──
            cur_5m = self._signal_indices["5min"][bar_idx]

            if cur_5m != last_5m_bar:
                last_5m_bar = cur_5m
                processed_5m = set()

            # ── PROMOTIONS (optimized) ──

            if cur_5m >= 0:
                allowed, _ = risk_mgr.can_trade()
                if allowed:
                    for pair in TRADEABLE_PAIRS:
                        key = (pair, cur_5m)
                        if key in processed_5m:
                            continue
                        processed_5m.add(key)

                        lookup = _sig_5m_lookup.get(pair)
                        if lookup is None or cur_5m < 0 or cur_5m >= len(lookup):
                            continue
                        sig_byte = lookup[cur_5m]
                        if sig_byte == b'N':
                            continue

                        # Divergence check
                        if _strength_vals_5m is not None and 0 <= cur_5m < len(_strength_vals_5m):
                            base, quote = pair.split("/")
                            if base in _strength_cols_5m and quote in _strength_cols_5m:
                                bi = _strength_cols_5m.index(base)
                                qi = _strength_cols_5m.index(quote)
                                div = _strength_vals_5m[cur_5m, bi] - _strength_vals_5m[cur_5m, qi]
                                if abs(div) < self.b_min_div:
                                    continue
                            else:
                                continue
                        else:
                            continue

                        direction = "BUY" if sig_byte == b'B' else "SELL"
                        _divergence = abs(div)

                        # Regime trend flip
                        if self.enable_regime_flip:
                            regime_arr = _regime_idx.get(pair)
                            if regime_arr is not None and 0 <= cur_5m < len(regime_arr):
                                if regime_arr[cur_5m]:
                                    direction = "SELL" if direction == "BUY" else "BUY"

                        # Macro filter
                        if ENABLE_MACRO_FILTER:
                            macro_bull = _macro.get(pair)
                            if macro_bull is not None and 0 <= cur_5m < len(macro_bull):
                                if (direction == "BUY" and not macro_bull[cur_5m]) or \
                                   (direction == "SELL" and macro_bull[cur_5m]):
                                    continue
                        if not _session_check(bar_time):
                            continue
                        if bar_time.hour >= MAX_ENTRY_HOUR:
                            continue
                        if len(b_trades) >= MAX_OPEN_TRADES:
                            continue

                        # Opposing trades check
                        directions = active_directions()
                        if pair in directions:
                            if directions[pair] != direction:
                                continue  # opposing direction on same pair
                            if BLOCK_SAME_DIRECTION_REENTRY:
                                continue  # same-direction stacking blocked

                        # Dynamic correlation guard (direction-aware)
                        if CORRELATION_ENABLED and self._corr_lookup and b_trades:
                            current_date = bar_time.normalize()
                            corr_dates = [d for d in self._corr_lookup if d <= current_date]
                            if corr_dates:
                                nearest = max(corr_dates)
                                corr_matrix = self._corr_lookup[nearest]
                                too_correlated = False
                                for t in b_trades:
                                    p1, p2 = pair, t["pair"]
                                    if p1 in corr_matrix.index and p2 in corr_matrix.columns:
                                        r = corr_matrix.loc[p1, p2]
                                        # Block if |r| > threshold AND same direction (same-side bet)
                                        if abs(r) > CORRELATION_THRESHOLD and direction == t["direction"]:
                                            too_correlated = True
                                            break
                                if too_correlated:
                                    continue

                        # Correlation rail (secondary safety — currency-level block)
                        base_c, quote_c = pair.split("/")
                        ccounts = {}
                        for t in b_trades:
                            b, q = t["pair"].split("/")
                            ccounts[b] = ccounts.get(b, 0) + 1
                            ccounts[q] = ccounts.get(q, 0) + 1
                        if ccounts.get(base_c, 0) >= MAX_PER_CURRENCY_BLOCK or \
                           ccounts.get(quote_c, 0) >= MAX_PER_CURRENCY_BLOCK:
                            continue

                        # ATR and entry
                        a_arr = self.atr_cache["5min"].get(pair)
                        ca_arr = self.pair_data["5min"].get(pair, {}).get("close", np.array([]))
                        hi_arr = self.pair_data["5min"].get(pair, {}).get("high", np.array([]))
                        lo_arr = self.pair_data["5min"].get(pair, {}).get("low", np.array([]))
                        if a_arr is None or len(ca_arr) == 0:
                            continue
                        idx = max(0, min(cur_5m, len(a_arr) - 1))
                        atr_val = float(a_arr[idx])
                        if atr_val <= 0:
                            continue
                        mid_price = float(ca_arr[idx])

                        spread_cost = self._spread_cost(pair)
                        entry_price = mid_price + spread_cost if direction == "BUY" else mid_price - spread_cost

                        atr_dist = self.b_atr_sl * atr_val
                        if direction == "BUY":
                            sl = mid_price - atr_dist
                            tp = mid_price + (atr_dist * self.b_rrr)
                        else:
                            sl = mid_price + atr_dist
                            tp = mid_price - (atr_dist * self.b_rrr)

                        stop_pips = abs(entry_price - sl) / pip_size(pair)
                        if stop_pips < 1.0:
                            continue

                        lot_size = risk_mgr.calculate_lot_size(pair, entry_price, sl, divergence=_divergence)
                        if lot_size <= 0 or lot_size < MIN_LOT_SIZE:
                            continue
                        units = lot_size
                        commission = units * COMMISSION_PER_LOT

                        pair_5m_times = self.pair_data["5min"][pair]["times"]
                        entry_5m_idx = np.searchsorted(pair_5m_times, bar_time_np)
                        entry_low = float(lo_arr[entry_5m_idx]) if lo_arr is not None and entry_5m_idx < len(lo_arr) else float('inf')
                        entry_high = float(hi_arr[entry_5m_idx]) if hi_arr is not None and entry_5m_idx < len(hi_arr) else float('-inf')
                        b_trades.append(dict(
                            pair=pair, direction=direction, entry_time=bar_time,
                            entry_price=entry_price, sl=sl, tp=tp, units=units,
                            commission=commission, tf_key="5min", level=1,
                            original_sl=sl, original_entry=mid_price,
                            breakeven_done=False,
                            _entry_tf_idx=entry_5m_idx,
                            _last_tf_idx=entry_5m_idx,
                            _min_low=entry_low,
                            _max_high=entry_high,
                            _last_close=mid_price,
                        ))

            # ── PROMOTIONS (optimized) ──
            for t in b_trades[:]:
                hit_tp = t.get("promoting", False)
                if not hit_tp:
                    tf_key = t.get("tf_key", "5min")
                    pd_info = self.pair_data.get(tf_key, {}).get(t["pair"])
                    if pd_info is not None:
                        ci = np.searchsorted(pd_info["times"], bar_time_np) - 1
                        ci = max(0, min(ci, len(pd_info["close"]) - 1))
                        current_close = float(pd_info["close"][ci])
                    else:
                        current_close = t.get("_last_close", 0)
                    if t["direction"] == "BUY":
                        hit_tp = current_close >= t["tp"]
                    else:
                        hit_tp = current_close <= t["tp"]

                if not hit_tp:
                    continue

                current_level = t.get("level", 0)
                next_level = current_level + 1

                if next_level >= len(B_TF_LADDER):
                    mult = 1 if t["direction"] == "BUY" else -1
                    diff = (t["tp"] - t["entry_price"]) * mult
                    pip = pip_size(t["pair"])
                    pv = 9.09 if "JPY" in t["pair"] else 10.0
                    pnl = round(diff / pip * pv * t["units"] - t["commission"], 2)
                    balance += pnl
                    b_wins += 1
                    risk_mgr.record_trade(pnl)
                    trade_log.append(dict(system="B", pair=t["pair"], direction=t["direction"],
                        entry=t["entry_price"], exit=t["tp"], pnl=pnl, result="WIN",
                        entry_time=t["entry_time"], exit_time=bar_time,
                        units=t["units"], commission=t["commission"],
                        level=current_level, note="final_tp"))
                    b_trades.remove(t)
                    continue

                # Check trend on next TF
                next_tf = B_TF_LADDER[next_level]
                if not self._trend_intact(next_tf, t["pair"], t["direction"], bar_idx):
                    mult = 1 if t["direction"] == "BUY" else -1
                    diff = (t["tp"] - t["entry_price"]) * mult
                    pip = pip_size(t["pair"])
                    pv = 9.09 if "JPY" in t["pair"] else 10.0
                    pnl = round(diff / pip * pv * t["units"] - t["commission"], 2)
                    balance += pnl
                    b_wins += 1
                    risk_mgr.record_trade(pnl)
                    trade_log.append(dict(system="B", pair=t["pair"], direction=t["direction"],
                        entry=t["entry_price"], exit=t["tp"], pnl=pnl, result="WIN",
                        entry_time=t["entry_time"], exit_time=bar_time,
                        units=t["units"], commission=t["commission"],
                        level=current_level, note="trend_exit_at_tp"))
                    b_trades.remove(t)
                    continue

                # PROMOTE
                b_promotions += 1
                next_atr_arr = self.atr_cache.get(next_tf, {}).get(t["pair"])
                if next_atr_arr is None or len(next_atr_arr) == 0:
                    continue

                next_tf_times = self.pair_data[next_tf][t["pair"]]["times"]
                nidx = np.searchsorted(next_tf_times, bar_time_np)
                nidx = max(0, min(nidx, len(next_atr_arr) - 1))
                next_atr = float(next_atr_arr[nidx])
                current_price = t.get("_last_close", 0)

                t["sl"] = t["original_entry"]
                t["breakeven_done"] = True
                t["tf_key"] = next_tf
                t["level"] = next_level
                t["promoting"] = False

                add_dist = self.b_atr_sl * next_atr * self.b_rrr
                if t["direction"] == "BUY":
                    t["tp"] = current_price + add_dist
                else:
                    t["tp"] = current_price - add_dist

                # Set _entry_tf_idx based on ORIGINAL entry time (matching original engine)
                next_tf_times = self.pair_data[next_tf][t["pair"]]["times"]
                orig_entry_idx = int(np.searchsorted(next_tf_times, t["entry_time"].to_datetime64()))
                t["_entry_tf_idx"] = orig_entry_idx - 1  # convert to our convention

                # Prefill running min/max with all bars from _entry_tf_idx+1 to current bar
                next_tf_data = self.pair_data[next_tf][t["pair"]]
                low_arr = next_tf_data["low"]
                high_arr = next_tf_data["high"]
                for ci in range(t["_entry_tf_idx"], nidx + 1):
                    ci_safe = max(0, min(ci, len(low_arr) - 1))
                    t["_min_low"] = min(t.get("_min_low", float("inf")), float(low_arr[ci_safe]))
                    t["_max_high"] = max(t.get("_max_high", float("-inf")), float(high_arr[ci_safe]))
                    t["_last_tf_idx"] = ci
                t["_last_close"] = current_price

            # Clear promotion flags
            for t in b_trades:
                t.pop("promoting", None)

            # Track peak and DD
            if balance > peak_balance:
                peak_balance = balance
            dd = (peak_balance - balance) / peak_balance * 100
            if dd > max_dd:
                max_dd = dd

        # Close unresolved
        for t in b_trades:
            trade_log.append(dict(system="B", pair=t["pair"], direction=t["direction"],
                entry=t["entry_price"], exit=None, pnl=None, result="UNRESOLVED",
                entry_time=t["entry_time"], exit_time=None,
                units=t["units"], commission=t["commission"],
                level=t.get("level", 0)))

        b_resolved = b_wins + b_losses
        b_wr = (b_wins / b_resolved * 100) if b_resolved > 0 else 0
        total_pnl = round(balance - INITIAL_BALANCE, 2)

        # Compute streaks
        resolved_trades = [t for t in trade_log if t["result"] in ("WIN", "LOSS")]
        max_win_streak = max_loss_streak = current_win = current_loss = 0
        for t in resolved_trades:
            if t["result"] == "WIN":
                current_win += 1; current_loss = 0
                max_win_streak = max(max_win_streak, current_win)
            elif t["result"] == "LOSS":
                current_loss += 1; current_win = 0
                max_loss_streak = max(max_loss_streak, current_loss)

        # Profit factor
        gross_profit = sum(t["pnl"] for t in resolved_trades if t["result"] == "WIN" and t["pnl"] is not None)
        gross_loss = abs(sum(t["pnl"] for t in resolved_trades if t["result"] == "LOSS" and t["pnl"] is not None))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float('inf')

        avg_win = round(gross_profit / b_wins, 2) if b_wins > 0 else 0
        avg_loss = round(gross_loss / b_losses, 2) if b_losses > 0 else 0

        return {
            "start": start_date, "end": end_date,
            "trades": b_resolved, "wins": b_wins, "losses": b_losses,
            "win_rate": round(b_wr, 2), "promotions": b_promotions,
            "net_pnl": total_pnl,
            "return_pct": round(total_pnl / INITIAL_BALANCE * 100, 2),
            "max_dd_pct": round(max_dd, 2),
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "trade_log": trade_log,
            "unresolved": len(b_trades),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  WALK-FORWARD & SINGLE RUN (same interface as original)
# ══════════════════════════════════════════════════════════════════════════════

def grid_search_b_params(bt: HybridBacktest, start_date: str, end_date: str) -> dict:
    best = None
    best_score = -999
    for div in [10.0, 20.0, 30.0]:
        for atr_sl in [2.0, 3.0, 4.0]:
            for rrr in [1.5, 2.0, 2.5]:
                bt.b_min_div = div
                bt.b_atr_sl = atr_sl; bt.b_rrr = rrr
                result = bt.run(start_date, end_date)
                total_pnl = result["net_pnl"]
                b_trades = result["trades"]
                b_wr = result["win_rate"]
                b_dd = result["max_dd_pct"]
                if b_trades < 10:
                    continue
                dd_penalty = max(0, (b_dd - 6.0) / 10.0)
                score = total_pnl * (1.0 - dd_penalty)
                if b_wr > 1 / (1 + rrr) * 100:
                    score *= 1.5
                if score > best_score:
                    best_score = score
                    best = {"min_div": div, "atr_sl": atr_sl, "rrr": rrr,
                            "pnl": total_pnl, "trades": b_trades, "wr": b_wr, "dd": b_dd}
    return best


def run_walk_forward(strength, signal_lookup, all_tfs, atr_cache, quick=False):
    logger.info("\n" + "=" * 70)
    logger.info("WALK-FORWARD VALIDATION" + (" (fixed params)" if quick else " (3 folds)"))
    logger.info("=" * 70)
    fold_results = []
    all_oos_trades = []
    for fold_idx, fold in enumerate(FOLDS):
        logger.info(f"\nFOLD {fold_idx + 1}")
        if quick:
            best_b = {"min_div": 20.0, "atr_sl": 3.0, "rrr": 2.0}
        else:
            bt_train = HybridBacktest(strength, signal_lookup, all_tfs, atr_cache)
            best_b = grid_search_b_params(bt_train, fold["train"][0], fold["train"][1])
            if best_b is None:
                continue
        bt_test = HybridBacktest(strength, signal_lookup, all_tfs, atr_cache)
        bt_test.b_min_div = best_b["min_div"]
        bt_test.b_atr_sl = best_b["atr_sl"]
        bt_test.b_rrr = best_b["rrr"]
        oos = bt_test.run(fold["test"][0], fold["test"][1])
        oos["fold"] = fold_idx + 1
        oos["best_b_params"] = best_b
        fold_results.append(oos)
        all_oos_trades.extend(oos["trade_log"])
    if not fold_results:
        logger.error("No valid OOS results!")
        return
    pd.DataFrame(all_oos_trades).to_csv("hybrid_oos_trades.csv", index=False)
    return fold_results


def _safe_save_csv(df, path):
    import io
    buf = io.StringIO()
    df.to_csv(buf)
    buf.seek(0)
    try:
        with open(path, "w", newline="") as f:
            f.write(buf.getvalue())
    except PermissionError:
        alt = f"{os.path.splitext(path)[0]}_{os.getpid()}.csv"
        with open(alt, "w", newline="") as f:
            f.write(buf.getvalue())


def generate_period_report(trade_log: list, period: str = "ME", output_prefix: str = "report",
                           initial_balance: float = 10000.0):
    """Generate a period-based report (monthly='ME', yearly='YE')."""
    if not trade_log:
        return
    df = pd.DataFrame(trade_log)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    freq = "M" if period == "ME" else "Y"
    df["period"] = df["entry_time"].dt.to_period(freq).astype(str)

    grouped = df.groupby("period")
    stats = grouped.agg(
        trades=("pnl", "count"),
        wins=("result", lambda x: (x == "WIN").sum()),
        losses=("result", lambda x: (x == "LOSS").sum()),
        total_pnl=("pnl", "sum"),
    )
    stats["win_rate"] = (stats["wins"] / stats["trades"] * 100).round(1)
    stats["avg_pnl"] = (stats["total_pnl"] / stats["trades"]).round(2)

    # Build full equity curve and derive period stats
    eq_df = df[df["result"].isin(["WIN", "LOSS"])].copy()
    eq_df["cum_pnl"] = eq_df["pnl"].cumsum()
    eq_df["equity"] = initial_balance + eq_df["cum_pnl"]
    eq_df["period"] = eq_df["entry_time"].dt.to_period(freq).astype(str)
    eq_df = eq_df.set_index("entry_time")

    # Period equity: first → last equity within each period
    period_eq = eq_df.groupby("period")["equity"].agg(["first", "last"])
    stats["net_return_pct"] = ((period_eq["last"] / period_eq["first"] - 1) * 100).round(2)

    # Period max DD: daily resample, cummax within period
    daily_eq = eq_df["equity"].resample("D").last().ffill()
    daily_period = daily_eq.index.to_period(freq).astype(str)
    for p in stats.index:
        m = daily_period == p
        if not m.any():
            continue
        series = daily_eq[m]
        if len(series) < 2:
            continue
        peak = series.cummax()
        dd = ((peak - series) / peak * 100).max()
        stats.at[p, "max_dd_pct"] = round(dd, 2)

    _safe_save_csv(stats, f"{output_prefix}_{'monthly' if period == 'ME' else 'yearly'}.csv")
    logger.info(f"Saved {output_prefix}_{'monthly' if period == 'ME' else 'yearly'}.csv")

def generate_monthly_report(trade_log: list, output_prefix: str = "report_monthly",
                            initial_balance: float = 10000.0):
    generate_period_report(trade_log, period="ME", output_prefix=output_prefix,
                          initial_balance=initial_balance)


def run_single(strength, signal_lookup, all_tfs, atr_cache,
               start_date: str = None, end_date: str = None):
    if start_date is None:
        start_date = "2016-01-01"
    if end_date is None:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(f"\nSYSTEM B BACKTEST: {start_date} -> {end_date}")
    bt = HybridBacktest(strength, signal_lookup, all_tfs, atr_cache)
    result = bt.run(start_date, end_date)

    logger.info(f"  Trades: {result['trades']} | WR: {result['win_rate']}%")
    logger.info(f"  Promotions: {result['promotions']}")
    logger.info(f"  Max DD: {result['max_dd_pct']}%")
    logger.info(f"  Net PnL: ${result['net_pnl']}")
    logger.info(f"  Return: {result['return_pct']}%")

    if result["trade_log"]:
        pd.DataFrame(result["trade_log"]).to_csv("hybrid_trades.csv", index=False)
        generate_monthly_report(result["trade_log"])
    import json
    serializable = {k: v for k, v in result.items() if k != "trade_log"}
    with open("backtest_summary.json", "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NestQuant System B Optimized Backtest")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--start", type=str, default="2016-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--n-jobs", type=int, default=None)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--walk-quick", action="store_true")
    args = parser.parse_args()

    n_jobs = args.n_jobs if args.n_jobs is not None else BACKTEST_N_JOBS
    load_pairs = QUICK_TEST_PAIRS if args.quick else ALL_PAIRS
    all_tfs = load_and_resample(quick=args.quick, pairs=list(load_pairs))
    strength = precompute_strength(all_tfs, n_jobs=n_jobs)
    signals, signal_lookup = precompute_signals_vectorized(
        strength, TRADEABLE_PAIRS, min_div=MIN_DIVERGENCE, top_n=STRENGTH_TOP_N, n_jobs=n_jobs,
    )
    atr_cache = precompute_atrs(all_tfs, n_jobs=n_jobs)

    if args.walk_forward:
        run_walk_forward(strength, signal_lookup, all_tfs, atr_cache)
    elif args.walk_quick:
        run_walk_forward(strength, signal_lookup, all_tfs, atr_cache, quick=True)
    else:
        run_single(strength, signal_lookup, all_tfs, atr_cache,
                   start_date=args.start, end_date=args.end)
