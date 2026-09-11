#!/usr/bin/env python3
"""
backtest_portfolio.py — Portfolio-Aware Backtest
=================================================
Keeps the core strategy (currency strength, signals, SL/TP, promotion ladder,
trend-reversal exit) completely unchanged.

Adds a deployment layer that scores, ranks, and selects only the best signals
to fit within risk/exposure/margin budgets.

Usage:
    python backtest_portfolio.py
"""

import os, sys, pickle, random, json, gc, collections, argparse
import numpy as np
import pandas as pd

sys.path = ['/root/nestquant', '/root'] + [p for p in sys.path if p not in ('/root', '/root/nestquant')]

import config as cfg
from backtest_hybrid_opt import (
    load_and_resample, precompute_strength, precompute_signals_vectorized,
    precompute_atrs, HybridBacktest, B_TF_LADDER, logger,
)
import backtest_hybrid_opt as bho

# Root config for 28 pairs
spec = __import__('importlib').util.spec_from_file_location("root_config", "/root/config.py")
root_cfg = __import__('importlib').util.module_from_spec(spec)
sys.modules['root_config'] = root_cfg
spec.loader.exec_module(root_cfg)
ALL_PAIRS = root_cfg.ALL_PAIRS

cfg.TRADEABLE_PAIRS = ALL_PAIRS
cfg.ALL_PAIRS = ALL_PAIRS
bho.TRADEABLE_PAIRS = ALL_PAIRS
bho.ALL_PAIRS = ALL_PAIRS

# Root RiskManager
if 'risk_manager' in sys.modules:
    del sys.modules['risk_manager']
sys.path.insert(0, '/root')
import risk_manager as root_risk_manager
RootRiskManager = root_risk_manager.RiskManager

# Import PortfolioManager
sys.path.insert(0, '/root')
import portfolio_manager as pm_module
PortfolioManager = pm_module.PortfolioManager

DATA_DIR = '/root/data'


# ── Breakout Signal Generation ─────────────────────────────────────────────

def precompute_breakout_signals(pair_dfs, trade_tf='5min', lookback=5):
    """Generate swing high/low breakout signals (B/S/N byte arrays)."""
    from indicators import swing_high_series, swing_low_series
    signal_lookup = {}
    for pair, df in pair_dfs.items():
        sh = swing_high_series(df, lookback).values
        sl = swing_low_series(df, lookback).values
        closes = df['close'].values
        n = len(closes)
        signals = np.full(n, 78, dtype=np.uint8)
        for i in range(lookback * 2 + 1, n):
            if not np.isnan(sh[i]) and closes[i] > sh[i]:
                signals[i] = 66
            elif not np.isnan(sl[i]) and closes[i] < sl[i]:
                signals[i] = 83
        signal_lookup[pair] = signals
    return signal_lookup


def precompute_swing_levels(pair_dfs, trade_tf='5min', lookback=5):
    """Precompute swing levels for trailing stop exit."""
    from indicators import swing_high_series, swing_low_series
    levels = {}
    for pair, df in pair_dfs.items():
        levels[pair] = {
            'swing_high': swing_high_series(df, lookback).values,
            'swing_low': swing_low_series(df, lookback).values,
        }
    return levels


# ── Custom RiskManager that accepts per-trade risk_pct ────────────────────

class FlexibleRiskManager(RootRiskManager):
    """Like RootRiskManager but calculate_lot_size accepts custom risk_pct."""
    def calculate_lot_size(self, pair, entry_price, stop_price, risk_pct=None):
        if risk_pct is None:
            risk_pct = self.risk_pct
        from indicators import pip_size as get_pip_size
        pip = get_pip_size(pair)
        stop_pips = abs(entry_price - stop_price) / pip
        if stop_pips < 1.0:
            return 0.0
        current_dd = self.dd_pct
        effective_risk = cfg.DD_REDUCED_RISK if current_dd >= cfg.DD_REDUCE_THRESHOLD else risk_pct
        risk_amount = self.balance * effective_risk
        pip_value_per_lot = 9.09 if "JPY" in pair.upper() else 10.0
        lot_size = risk_amount / (stop_pips * pip_value_per_lot)
        lot_size = min(lot_size, 10.0)
        lot_size = round(lot_size, 2)
        return lot_size




# ── Portfolio-Integrated Backtest ─────────────────────────────────────────

def run_portfolio_backtest(all_tfs, strength, signal_lookup, atr_cache,
                           start_date, end_date,
                           pm: PortfolioManager,
                           initial_balance=1000.0, trade_tf='5min',
                           invert_signal=False, disable_trend_exit=False, adx_threshold=0.0,
                           signal_type='divergence',
                           atr_chandelier_mult=None, max_hold_bars=None,
                           enable_regime_sizing=False):
    """
    Runs the original backtest engine with PortfolioManager filtering entry signals.

    Preserves the EXACT same trade resolution, exit, promotion, and risk
    management logic.  Only the entry section is modified to use PM-based
    signal selection and risk allocation.

    trade_tf: timeframe to use for entry signals (e.g. '5min', '4h', '1D')
    """
    from backtest_hybrid_opt import (
        B_TF_LADDER, INITIAL_BALANCE, MAX_OPEN_TRADES, MAX_PER_CURRENCY_BLOCK,
        ENABLE_MACRO_FILTER, ENABLE_REGIME_FLIP, TRADEABLE_PAIRS,
        is_active_session, pip_size, COMMISSION_PER_LOT, MIN_LOT_SIZE,
    )

    # Defaults for new params
    if atr_chandelier_mult is None:
        atr_chandelier_mult = cfg.ATR_CHANDELIER_MULT
    if max_hold_bars is None:
        max_hold_bars = cfg.MAX_HOLD_DAYS * 24 * 60  # days → 1-min bars

    # ── Setup ──────────────────────────────────────────────────────────
    import gc
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    # Always iterate on 5min bars for resolution; entry/exit on trade_tf
    df_5m = next(iter(all_tfs["5min"].values()))
    all_times = df_5m.index.values
    mask = (all_times >= start.to_datetime64()) & (all_times < end.to_datetime64())
    timeline = all_times[mask]
    n_bars = len(timeline)

    logger.info(f"Portfolio backtest on {n_bars} 5M bars [{start_date} -> {end_date}) "
                f"(trade TF: {trade_tf})")

    # Signal indices
    _signal_indices = {}
    for tf in B_TF_LADDER:
        sdf = strength.get(tf)
        if sdf is not None and not sdf.empty:
            stimes = sdf.index.values
            _signal_indices[tf] = np.searchsorted(stimes, timeline) - 1
        else:
            _signal_indices[tf] = np.full(n_bars, -1, dtype=int)

    # Pre-extract pair data
    pair_data = {}
    for tf in B_TF_LADDER:
        pair_data[tf] = {}
        for pair, df in all_tfs[tf].items():
            if df is not None and not df.empty:
                pair_data[tf][pair] = {
                    "times": df.index.values,
                    "close": df["close"].values,
                    "high": df["high"].values,
                    "low": df["low"].values,
                }

    b_trades: list = []
    trade_log: list = []
    balance = initial_balance
    peak_balance = initial_balance
    max_dd = 0.0
    b_wins = b_losses = 0
    b_promotions = 0
    recovery_pnl = 0.0

    # Disable recovery for regime-sized breakout
    _no_recovery = (signal_type == 'breakout' and enable_regime_sizing)

    risk_mgr = FlexibleRiskManager(initial_balance=initial_balance)
    last_date = None

    def active_directions():
        return {t["pair"]: t["direction"] for t in b_trades}

    last_tf_bar = -1
    processed_tf = set()

    # Lookups (parameterized by trade_tf)
    _sig_tf_lookup = signal_lookup.get(trade_tf, {})
    _strength_tf = strength.get(trade_tf)
    _strength_cols_tf = list(_strength_tf.columns) if _strength_tf is not None else []
    _strength_vals_tf = _strength_tf.values if _strength_tf is not None else None

    # Swing levels for breakout mode
    _swing_levels = {}
    if signal_type == 'breakout':
        _swing_levels = precompute_swing_levels(all_tfs[trade_tf], trade_tf, lookback=5)

    # Macro and regime arrays (same as original construction)
    _macro = {}
    if ENABLE_MACRO_FILTER:
        for pair in all_tfs['5min']:
            d4 = all_tfs['4h'].get(pair)
            d5 = all_tfs['5min'].get(pair)
            if d4 is None or d4.empty or d5 is None or d5.empty:
                continue
            ema = d4["close"].ewm(span=cfg.MACRO_EMA_PERIOD, adjust=False).mean()
            macro_bull = d4["close"].values > ema.values
            d4_times = d4.index.values
            bull = np.zeros(len(d5), dtype=bool)
            for i, t in enumerate(d5.index):
                idx = np.searchsorted(d4_times, t.to_datetime64()) - 1
                if 0 <= idx < len(macro_bull):
                    bull[i] = macro_bull[idx]
            _macro[pair] = bull

    _regime_idx = {}
    if ENABLE_REGIME_FLIP:
        for pair in all_tfs['5min']:
            d4 = all_tfs['4h'].get(pair)
            d5 = all_tfs['5min'].get(pair)
            if d4 is None or d4.empty or d5 is None or d5.empty:
                continue
            from indicators import calculate_atr
            atr4 = calculate_atr(d4, 14).fillna(0)
            atr_avg = atr4.rolling(cfg.REGIME_LOOKBACK, min_periods=5).mean().fillna(0)
            crisis = (atr4 > atr_avg * cfg.REGIME_ATR_MULTIPLIER).values
            d4_times = d4.index.values
            regime = np.zeros(len(d5), dtype=bool)
            for i, t in enumerate(d5.index):
                idx = np.searchsorted(d4_times, t.to_datetime64()) - 1
                if 0 <= idx < len(crisis):
                    regime[i] = crisis[idx]
            _regime_idx[pair] = regime

    _session_check = is_active_session

    # ── Precompute ATR averages for regime scoring ─────────────────────
    _atr_avg = {}
    for pair in all_tfs[trade_tf]:
        d = all_tfs[trade_tf].get(pair)
        if d is None:
            continue
        from indicators import calculate_atr
        atr = calculate_atr(d, 14).fillna(0)
        _atr_avg[pair] = atr.rolling(20, min_periods=5).mean().fillna(0).values

    # Floating loss limit (% of balance)
    floating_loss_limit = 0.02  # 2%
    daily_loss_limit = 0.03     # 3% daily max

    # ── Precompute trade_tf ATR for chandelier trailing stop ──────────
    _atr_tf_arr = {}
    if signal_type == 'breakout':
        for pair in all_tfs[trade_tf]:
            d = all_tfs[trade_tf].get(pair)
            if d is None:
                continue
            from indicators import calculate_atr
            _atr_tf_arr[pair] = calculate_atr(d, 14).fillna(0).values

    # ── Precompute ADX for regime sizing ──────────────────────────────
    _regime_adx = {}
    if enable_regime_sizing:
        for pair in all_tfs[trade_tf]:
            d = all_tfs[trade_tf].get(pair)
            if d is None:
                continue
            from indicators import calculate_adx
            adx_arr = calculate_adx(d, 14).fillna(0).values
            _regime_adx[pair] = adx_arr

    # ── Precompute ADX for orthogonal filter ──────────────────────────
    _adx_cache = {}
    if adx_threshold > 0:
        from indicators import calculate_adx
        sdf_tf = strength.get(trade_tf)
        sdf_times = sdf_tf.index.values if sdf_tf is not None else None
        for pair in all_tfs[trade_tf]:
            d = all_tfs[trade_tf].get(pair)
            if d is None or sdf_times is None:
                continue
            adx_series = calculate_adx(d, 14).fillna(0)
            # Reindex to strength DataFrame's time axis
            adx_idx = np.searchsorted(adx_series.index.values, sdf_times) - 1
            adx_idx = np.clip(adx_idx, 0, len(adx_series) - 1)
            adx_aligned = adx_series.values[adx_idx]
            _adx_cache[pair] = adx_aligned

    # ── Main Bar Loop ──────────────────────────────────────────────────
    for bar_idx in range(n_bars):
        bar_time_np = timeline[bar_idx]
        bar_time = pd.Timestamp(bar_time_np)

        # Daily reset
        current_date = bar_time.date()
        if last_date is None or current_date != last_date:
            risk_mgr.reset_daily()
            last_date = current_date

        # Daily loss limit: skip new entries if daily loss > 3% of balance
        daily_loss_cap = daily_loss_limit * balance
        daily_loss_hit = risk_mgr.daily_gross_loss >= daily_loss_cap

        # ── TRADE RESOLUTION (identical to original) ───────────────────
        still_open = []
        for t in b_trades:
            p = t["pair"]
            tf_key = t.get("tf_key", "5min")
            pd_info = pair_data.get(tf_key, {}).get(p)
            if pd_info is None:
                still_open.append(t)
                continue

            current_tf_idx = np.searchsorted(pd_info["times"], bar_time_np)
            entry_tf_idx = t.get("_entry_tf_idx", -1)
            if current_tf_idx <= entry_tf_idx:
                still_open.append(t)
                continue

            last_tf_idx = t.get("_last_tf_idx", entry_tf_idx)
            if current_tf_idx > last_tf_idx:
                ci = max(0, min(current_tf_idx - 1, len(pd_info["low"]) - 1))
                t["_min_low"] = min(t.get("_min_low", float("inf")), float(pd_info["low"][ci]))
                t["_max_high"] = max(t.get("_max_high", float("-inf")), float(pd_info["high"][ci]))
                t["_last_tf_idx"] = current_tf_idx

            ci = max(0, min(current_tf_idx - 1, len(pd_info["close"]) - 1))
            t["_last_close"] = float(pd_info["close"][ci])

            # Floating loss check: force close if single trade > 2% of balance
            mult_f = 1 if t["direction"] == "BUY" else -1
            floating_pnl_raw = (t["_last_close"] - t["entry_price"]) * mult_f
            pip_f = pip_size(p)
            pv_f = 9.09 if "JPY" in p else 10.0
            floating_pnl_usd_f = round(floating_pnl_raw / pip_f * pv_f * t["units"] - t["commission"], 2)
            floating_loss_pct = abs(floating_pnl_usd_f) / balance if balance > 0 else 1.0
            if floating_pnl_usd_f < 0 and floating_loss_pct > floating_loss_limit:
                balance += floating_pnl_usd_f
                b_losses += 1
                if not _no_recovery:
                    recovery_pnl += abs(floating_pnl_usd_f)
                risk_mgr.record_trade(floating_pnl_usd_f)
                trade_log.append(dict(system="B", pair=p, direction=t["direction"],
                    entry=t["entry_price"], exit=t["_last_close"], pnl=floating_pnl_usd_f,
                    result="LOSS",
                    entry_time=t["entry_time"], exit_time=bar_time,
                    units=t["units"], commission=t["commission"],
                    level=t.get("level", 0), note="floating_dd"))
                continue

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
                        if not _no_recovery:
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
                # Exit logic depends on signal type
                if signal_type == 'breakout':
                    # Max hold: force exit after N days
                    bars_open = bar_idx - t.get("_entry_bar_idx", bar_idx)
                    if bars_open > max_hold_bars:
                        exit_price = current_price
                        mult = 1 if t["direction"] == "BUY" else -1
                        diff = (exit_price - t["entry_price"]) * mult
                        pip = pip_size(p)
                        pv = 9.09 if "JPY" in p else 10.0
                        pnl = round(diff / pip * pv * t["units"] - t["commission"], 2)
                        balance += pnl
                        b_losses += 1 if pnl < 0 else 0
                        b_wins += 1 if pnl > 0 else 0
                        if pnl < 0 and not _no_recovery: recovery_pnl += abs(pnl)
                        risk_mgr.record_trade(pnl)
                        trade_log.append(dict(system="B", pair=p, direction=t["direction"],
                            entry=t["entry_price"], exit=exit_price, pnl=pnl,
                            result="WIN" if pnl > 0 else "LOSS",
                            entry_time=t["entry_time"], exit_time=bar_time,
                            units=t["units"], commission=t["commission"],
                            level=t.get("level", 0), note="max_hold"))
                        continue
                    # Swing-based trailing stop (lets winners run)
                    swing = _swing_levels.get(p, {})
                    if swing:
                        if t["direction"] == "BUY":
                            sw = swing.get('swing_low', np.array([]))
                            sw_idx = _signal_indices[trade_tf][bar_idx] if bar_idx < len(_signal_indices[trade_tf]) else -1
                            if sw_idx >= 0 and sw_idx < len(sw) and not np.isnan(sw[sw_idx]):
                                new_sl = float(sw[sw_idx])
                                if new_sl > t["sl"]:
                                    t["sl"] = new_sl
                                    t["original_sl"] = new_sl
                                    t["_min_low"] = float('inf')
                        else:
                            sw = swing.get('swing_high', np.array([]))
                            sw_idx = _signal_indices[trade_tf][bar_idx] if bar_idx < len(_signal_indices[trade_tf]) else -1
                            if sw_idx >= 0 and sw_idx < len(sw) and not np.isnan(sw[sw_idx]):
                                new_sl = float(sw[sw_idx])
                                if new_sl < t["sl"]:
                                    t["sl"] = new_sl
                                    t["original_sl"] = new_sl
                                    t["_max_high"] = float('-inf')
                    still_open.append(t)
                    continue

                # Trend reversal check (optional, harmful for mean reversion)
                if disable_trend_exit:
                    still_open.append(t)
                    continue
                trend_tf = t.get("_trend_tf", "5min")
                lookup = signal_lookup.get(trend_tf, {}).get(p)
                if lookup is None or len(lookup) == 0:
                    still_open.append(t)
                    continue
                sdf_check = strength.get(trend_tf)
                idx_check = _signal_indices.get(trend_tf, np.array([]))
                if sdf_check is None or sdf_check.empty or len(idx_check) == 0:
                    still_open.append(t)
                    continue
                sig_idx = idx_check[bar_idx] if bar_idx < len(idx_check) else -1
                if sig_idx < 0 or sig_idx >= len(lookup):
                    still_open.append(t)
                    continue
                dir_byte = b'B' if t["direction"] == "BUY" else b'S'
                if lookup[sig_idx] != dir_byte:
                        close_info = pair_data.get(tf_key, {}).get(p)
                        if close_info:
                            ci_close = np.searchsorted(close_info["times"], bar_time_np) - 1
                            ci_close = max(0, min(ci_close, len(close_info["close"]) - 1))
                            exit_price = float(close_info["close"][ci_close])
                            mult = 1 if t["direction"] == "BUY" else -1
                            diff = (exit_price - t["entry_price"]) * mult
                            pip = pip_size(p)
                            pv = 9.09 if "JPY" in p else 10.0
                            pnl = round(diff / pip * pv * t["units"] - t["commission"], 2)
                            balance += pnl
                            if pnl < 0:
                                b_losses += 1
                                if not _no_recovery: recovery_pnl += abs(pnl)
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

        # ── BREAKEVEN CHECK (identical to original) ────────────────────
        for t in b_trades:
            if t.get("breakeven_done"):
                continue
            tf_key = t.get("tf_key", "5min")
            current_price = t.get("_last_close")
            if current_price is None:
                pd_info = pair_data.get(tf_key, {}).get(t["pair"])
                if pd_info is not None:
                    ci_be = np.searchsorted(pd_info["times"], bar_time_np) - 1
                    ci_be = max(0, min(ci_be, len(pd_info["close"]) - 1))
                    current_price = float(pd_info["close"][ci_be])
            risk_distance = abs(t["entry_price"] - t.get("original_sl", t["sl"]))
            breakeven_threshold = cfg.BREAKEVEN_RATIO * risk_distance
            if t["direction"] == "BUY":
                profit = current_price - t["entry_price"]
            else:
                profit = t["entry_price"] - current_price
            if profit >= breakeven_threshold:
                t["sl"] = t["entry_price"]
                t["breakeven_done"] = True

        # ── ENTRY SIGNALS (MODIFIED: Portfolio-Aware) ──────────────────
        cur_tf = _signal_indices[trade_tf][bar_idx] if bar_idx < len(_signal_indices[trade_tf]) else -1

        if cur_tf != last_tf_bar:
            last_tf_bar = cur_tf
            processed_tf = set()

        if cur_tf >= 0:
            allowed, _ = risk_mgr.can_trade()
            if allowed and not daily_loss_hit:
                # Step A: Collect all eligible signals on this bar
                raw_candidates = []

                # Compute current daily risk used
                daily_risk_used = risk_mgr.daily_gross_loss / balance if balance > 0 else 0

                for pair in TRADEABLE_PAIRS:
                    key = (pair, cur_tf)
                    if key in processed_tf:
                        continue
                    processed_tf.add(key)

                    lookup = _sig_tf_lookup.get(pair)
                    if lookup is None or cur_tf < 0 or cur_tf >= len(lookup):
                        continue
                    sig_byte = lookup[cur_tf]
                    if sig_byte == b'N':
                        continue

                    direction = "BUY" if sig_byte == b'B' else "SELL"

                    # Divergence / signal strength for PM scoring
                    if signal_type == 'breakout':
                        # Use price distance from swing level as 'divergence'
                        pd_tf = pair_data.get(trade_tf, {}).get(pair, {})
                        closes_a = pd_tf.get('close', np.array([]))
                        swing = _swing_levels.get(pair, {})
                        if len(closes_a) == 0 or cur_tf >= len(closes_a):
                            continue
                        price = float(closes_a[cur_tf])
                        if direction == 'BUY':
                            sh = swing.get('swing_high', np.array([]))
                            div = price - sh[cur_tf] if cur_tf < len(sh) and not np.isnan(sh[cur_tf]) else 0.0
                        else:
                            sl = swing.get('swing_low', np.array([]))
                            div = sl[cur_tf] - price if cur_tf < len(sl) and not np.isnan(sl[cur_tf]) else 0.0
                        if abs(div) == 0.0:
                            continue
                    else:
                        if _strength_vals_tf is not None and 0 <= cur_tf < len(_strength_vals_tf):
                            base, quote = pair.split("/")
                            if base in _strength_cols_tf and quote in _strength_cols_tf:
                                bi = _strength_cols_tf.index(base)
                                qi = _strength_cols_tf.index(quote)
                                div = _strength_vals_tf[cur_tf, bi] - _strength_vals_tf[cur_tf, qi]
                                if abs(div) < cfg.MIN_DIVERGENCE:
                                    continue
                            else:
                                continue
                        else:
                            continue

                    # Signal inversion (mean reversion mode)
                    if invert_signal:
                        direction = "SELL" if direction == "BUY" else "BUY"

                    # ADX trend-strength filter (orthogonal to divergence)
                    if adx_threshold > 0:
                        adx_arr = _adx_cache.get(pair)
                        if adx_arr is not None and cur_tf < len(adx_arr):
                            if adx_arr[cur_tf] < adx_threshold:
                                continue

                    # Regime trend flip
                    if ENABLE_REGIME_FLIP:
                        regime_arr = _regime_idx.get(pair)
                        if regime_arr is not None and 0 <= cur_tf < len(regime_arr):
                            if regime_arr[cur_tf]:
                                direction = "SELL" if direction == "BUY" else "BUY"

                    # Macro filter
                    if ENABLE_MACRO_FILTER:
                        macro_bull = _macro.get(pair)
                        if macro_bull is not None and 0 <= cur_tf < len(macro_bull):
                            if (direction == "BUY" and not macro_bull[cur_tf]) or \
                               (direction == "SELL" and macro_bull[cur_tf]):
                                continue

                    if not _session_check(bar_time):
                        continue

                    # No opposing trades (same pair)
                    directions = active_directions()
                    if pair in directions and directions[pair] != direction:
                        continue

                    # Correlation rail (currency level)
                    base_c, quote_c = pair.split("/")
                    ccounts = {}
                    for t in b_trades:
                        b, q = t["pair"].split("/")
                        ccounts[b] = ccounts.get(b, 0) + 1
                        ccounts[q] = ccounts.get(q, 0) + 1
                    if ccounts.get(base_c, 0) >= MAX_PER_CURRENCY_BLOCK or \
                       ccounts.get(quote_c, 0) >= MAX_PER_CURRENCY_BLOCK:
                        continue

                    # ATR and price info (use 5min for precision regardless of trade_tf)
                    a_arr = atr_cache["5min"].get(pair)
                    ca_arr = pair_data["5min"].get(pair, {}).get("close", np.array([]))
                    hi_arr = pair_data["5min"].get(pair, {}).get("high", np.array([]))
                    lo_arr = pair_data["5min"].get(pair, {}).get("low", np.array([]))
                    if a_arr is None or len(ca_arr) == 0:
                        continue
                    idx_5m = max(0, min(_signal_indices["5min"][bar_idx] if bar_idx < len(_signal_indices["5min"]) else 0, len(a_arr) - 1))
                    atr_val = float(a_arr[idx_5m])
                    if atr_val <= 0:
                        continue
                    mid_price = float(ca_arr[idx_5m])

                    spread_cost = pip_size(pair) * cfg.SPREAD_PIPS.get(pair, cfg.DEFAULT_SPREAD_PIPS)
                    entry_price = mid_price + spread_cost if direction == "BUY" else mid_price - spread_cost

                    # Use trade_tf ATR for SL/TP when on higher timeframe
                    if trade_tf != '5min' and signal_type == 'breakout':
                        tf_atr_arr = _atr_tf_arr.get(pair)
                        if tf_atr_arr is not None and 0 <= cur_tf < len(tf_atr_arr):
                            atr_val = float(tf_atr_arr[cur_tf])

                    atr_dist = cfg.ATR_SL_MULTIPLIER * atr_val
                    if direction == "BUY":
                        sl = mid_price - atr_dist
                        tp = mid_price + (atr_dist * cfg.RRR)
                    else:
                        sl = mid_price + atr_dist
                        tp = mid_price - (atr_dist * cfg.RRR)

                    stop_pips = abs(entry_price - sl) / pip_size(pair)
                    if stop_pips < 1.0:
                        continue

                    # Spread pips for PM scoring
                    spread_pips = cfg.SPREAD_PIPS.get(pair, cfg.DEFAULT_SPREAD_PIPS)

                    # ATR average for PM scoring
                    atr_avg_val = 0.0
                    avg_arr = _atr_avg.get(pair)
                    if avg_arr is not None and cur_tf < len(avg_arr):
                        atr_avg_val = float(avg_arr[cur_tf])
                    if atr_avg_val <= 0:
                        atr_avg_val = atr_val

                    # Regime-based risk multiplier and skip
                    regime_mult = 1.0
                    if enable_regime_sizing:
                        adx_arr = _regime_adx.get(pair)
                        if adx_arr is not None and cur_tf < len(adx_arr):
                            adx_v = adx_arr[cur_tf]
                            if adx_v < cfg.REGIME_ADX_RANGING:
                                regime_mult = cfg.REGIME_MULT_RANGING
                            elif adx_v > cfg.REGIME_ADX_TRENDING:
                                regime_mult = cfg.REGIME_MULT_TRENDING

                    cur_5m_idx = _signal_indices["5min"][bar_idx] if bar_idx < len(_signal_indices["5min"]) else -1
                    raw_candidates.append({
                        'pair': pair, 'direction': direction,
                        'divergence': div, 'atr': atr_val,
                        'atr_avg': atr_avg_val, 'spread_pips': spread_pips,
                        'signal_lookups': signal_lookup, 'trade_tf': trade_tf,
                        'cur_5m': cur_5m_idx,
                        'entry_price': entry_price, 'sl': sl, 'tp': tp,
                        'mid_price': mid_price, 'spread_cost': spread_cost,
                        'stop_pips': stop_pips, 'atr_val': atr_val,
                        'regime_mult': regime_mult,
                    })

                # Step B: Let PortfolioManager select the best signals
                # Build open positions info for scoring
                open_info = []
                for t in b_trades:
                    open_info.append({
                        'pair': t['pair'], 'direction': t['direction'],
                        'score': t.get('_pm_score', 0),
                    })

                selected = pm.select_trades(
                    raw_candidates, open_info, balance, daily_risk_used,
                )

                # Step C: Enter selected trades
                for entry_info in selected:
                    pair = entry_info['pair']
                    direction = entry_info['direction']
                    entry_price = entry_info['entry_price']
                    sl = entry_info['sl']
                    tp = entry_info['tp']
                    mid_price = entry_info['mid_price']

                    # Calculate lot size with PM-allocated risk (adjusted by regime)
                    risk_pct = entry_info['risk_pct']
                    regime_mult = entry_info.get('regime_mult', 1.0)
                    # Scale max trade risk to allow regime sizing room
                    effective_max_risk = pm.max_trade_risk_pct * max(1.0, cfg.REGIME_MULT_TRENDING)
                    risk_pct = risk_pct * regime_mult
                    if risk_pct > effective_max_risk:
                        risk_pct = effective_max_risk
                    lot_size = risk_mgr.calculate_lot_size(pair, entry_price, sl, risk_pct=risk_pct)
                    if lot_size <= 0 or lot_size < MIN_LOT_SIZE:
                        continue
                    # Hard cap at 0.5 units (50x leverage on $1k)
                    lot_size = min(lot_size, 0.5)
                    units = lot_size
                    commission = units * cfg.COMMISSION_PER_LOT

                    pair_5m_times = pair_data["5min"][pair]["times"]
                    entry_5m_idx = np.searchsorted(pair_5m_times, bar_time_np)
                    lo_arr_e = pair_data["5min"][pair].get("low", np.array([]))
                    hi_arr_e = pair_data["5min"][pair].get("high", np.array([]))
                    entry_low = float(lo_arr_e[entry_5m_idx]) if len(lo_arr_e) > entry_5m_idx else float('inf')
                    entry_high = float(hi_arr_e[entry_5m_idx]) if len(hi_arr_e) > entry_5m_idx else float('-inf')

                    b_trades.append(dict(
                        pair=pair, direction=direction, entry_time=bar_time,
                        entry_price=entry_price, sl=sl, tp=tp, units=units,
                        commission=commission, tf_key="5min", level=0,
                        original_sl=sl, original_entry=mid_price,
                        breakeven_done=False,
                        _entry_tf_idx=entry_5m_idx,
                        _entry_bar_idx=bar_idx,
                        _last_tf_idx=entry_5m_idx,
                        _min_low=entry_low, _max_high=entry_high,
                        _last_close=mid_price,
                        _pm_score=entry_info.get('score', 0),
                        _pm_risk_pct=risk_pct,
                        _trend_tf=trade_tf,
                    ))

        # ── PROMOTIONS ─────────────────────────────────────────────────
        promote_candidates = []
        for t in b_trades:
            if t.get("promoting", False):
                promote_candidates.append(t)

        for t in promote_candidates:
            if t not in b_trades:
                continue
            pair = t["pair"]
            trend_tf = t.get("_trend_tf", "5min")

            # Non-standard trade TF: take TP profit immediately, no ladder promotion
            if trend_tf != "5min":
                mult = 1 if t["direction"] == "BUY" else -1
                diff = (t["tp"] - t["entry_price"]) * mult
                pip = pip_size(pair)
                pv = 9.09 if "JPY" in pair else 10.0
                pnl = round(diff / pip * pv * t["units"] - t.get("commission", 0), 2)
                balance += pnl
                b_wins += 1
                risk_mgr.record_trade(pnl)
                trade_log.append(dict(system="B", pair=pair, direction=t["direction"],
                    entry=t["entry_price"], exit=t["tp"], pnl=pnl, result="WIN",
                    entry_time=t["entry_time"], exit_time=bar_time,
                    units=t["units"], commission=t["commission"],
                    level=0, note="tp_no_promo"))
                b_trades.remove(t)
                continue

            current_level = t.get("level", 0)
            next_level = current_level + 1

            if next_level >= len(B_TF_LADDER):
                mult = 1 if t["direction"] == "BUY" else -1
                diff = (t["tp"] - t["entry_price"]) * mult
                pip = pip_size(pair)
                pv = 9.09 if "JPY" in pair else 10.0
                pnl = round(diff / pip * pv * t["units"] - t.get("commission", 0), 2)
                balance += pnl
                b_wins += 1
                risk_mgr.record_trade(pnl)
                trade_log.append(dict(system="B", pair=pair, direction=t["direction"],
                    entry=t["entry_price"], exit=t["tp"], pnl=pnl, result="WIN",
                    entry_time=t["entry_time"], exit_time=bar_time,
                    units=t["units"], commission=t["commission"],
                    level=current_level, note="final_tp"))
                b_trades.remove(t)
                continue

            # Check trend on next TF
            next_tf = B_TF_LADDER[next_level]
            lookup_promo = signal_lookup.get(next_tf, {}).get(pair)
            if lookup_promo is not None:
                sdf_promo = strength.get(next_tf)
                if sdf_promo is not None and not sdf_promo.empty:
                    stimes_promo = sdf_promo.index.values
                    promo_idx = np.searchsorted(stimes_promo, bar_time_np) - 1
                    promo_idx = max(0, min(promo_idx, len(lookup_promo) - 1))
                    dir_byte_promo = b'B' if t["direction"] == "BUY" else b'S'
                    if promo_idx >= 0 and promo_idx < len(lookup_promo) and lookup_promo[promo_idx] != dir_byte_promo:
                        mult = 1 if t["direction"] == "BUY" else -1
                        diff = (t["tp"] - t["entry_price"]) * mult
                        pip = pip_size(pair)
                        pv = 9.09 if "JPY" in pair else 10.0
                        pnl = round(diff / pip * pv * t["units"] - t.get("commission", 0), 2)
                        balance += pnl
                        b_wins += 1
                        risk_mgr.record_trade(pnl)
                        trade_log.append(dict(system="B", pair=pair, direction=t["direction"],
                            entry=t["entry_price"], exit=t["tp"], pnl=pnl, result="WIN",
                            entry_time=t["entry_time"], exit_time=bar_time,
                            units=t["units"], commission=t["commission"],
                            level=current_level, note="trend_exit_at_tp"))
                        b_trades.remove(t)
                        continue

            # PROMOTE
            b_promotions += 1
            next_atr_arr = atr_cache.get(next_tf, {}).get(pair)
            if next_atr_arr is None or len(next_atr_arr) == 0:
                continue

            next_tf_times = pair_data[next_tf][pair]["times"]
            nidx = np.searchsorted(next_tf_times, bar_time_np)
            nidx = max(0, min(nidx, len(next_atr_arr) - 1))
            next_atr = float(next_atr_arr[nidx])
            current_price = t.get("_last_close", 0)

            t["sl"] = t.get("original_entry", t["entry_price"])
            t["breakeven_done"] = True
            t["tf_key"] = next_tf
            t["level"] = next_level
            t["promoting"] = False

            add_dist = cfg.ATR_SL_MULTIPLIER * next_atr * cfg.RRR
            if t["direction"] == "BUY":
                t["tp"] = current_price + add_dist
            else:
                t["tp"] = current_price - add_dist

            next_tf_times_orig = pair_data[next_tf][pair]["times"]
            orig_entry_idx = int(np.searchsorted(next_tf_times_orig, t["entry_time"].to_datetime64()))
            t["_entry_tf_idx"] = orig_entry_idx - 1

            next_tf_data = pair_data[next_tf][pair]
            low_arr_next = next_tf_data["low"]
            high_arr_next = next_tf_data["high"]
            for ci in range(t["_entry_tf_idx"], nidx + 1):
                ci_safe = max(0, min(ci, len(low_arr_next) - 1))
                t["_min_low"] = min(t.get("_min_low", float("inf")), float(low_arr_next[ci_safe]))
                t["_max_high"] = max(t.get("_max_high", float("-inf")), float(high_arr_next[ci_safe]))
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

    # ── Close unresolved (identical to original) ───────────────────────
    for t in b_trades:
        trade_log.append(dict(system="B", pair=t["pair"], direction=t["direction"],
            entry=t["entry_price"], exit=None, pnl=None, result="UNRESOLVED",
            entry_time=t["entry_time"], exit_time=None,
            units=t["units"], commission=t.get("commission", 0),
            level=t.get("level", 0)))

    # ── Summary ────────────────────────────────────────────────────────
    wins = sum(1 for tl in trade_log if tl.get("result") == "WIN")
    losses = sum(1 for tl in trade_log if tl.get("result") == "LOSS")
    unresolved = sum(1 for tl in trade_log if tl.get("result") == "UNRESOLVED")
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    return_pct = ((balance - initial_balance) / initial_balance) * 100

    notes = collections.Counter(tl.get("note", "") for tl in trade_log)

    result = {
        "net_pnl": round(balance - initial_balance, 2),
        "return_pct": round(return_pct, 2),
        "trades": total_closed,
        "win_rate": round(win_rate, 2),
        "max_dd_pct": round(max_dd, 2),
        "promotions": b_promotions,
        "trade_log": trade_log,
        "exit_notes": dict(notes),
    }

    logger.info(f"  Trades: {result['trades']} | WR: {result['win_rate']}%")
    logger.info(f"  Promotions: {result['promotions']}")
    logger.info(f"  Max DD: {result['max_dd_pct']}%")
    logger.info(f"  Net PnL: ${result['net_pnl']}")
    logger.info(f"  Return: {result['return_pct']}%")
    logger.info(f"  Exits: {dict(notes)}")

    return result


# ── Convenience runner ────────────────────────────────────────────────────

def run_test(max_positions=5, daily_risk_pct=0.02, max_trade_risk=0.01,
             min_trade_risk=0.002, per_curr_exposure=2,
             enable_replacement=True, window_label='2019', trade_tf='5min',
             invert_signal=False, disable_trend_exit=False, adx_threshold=0.0,
             signal_type='divergence',
             atr_chandelier_mult=None, max_hold_bars=None,
             enable_regime_sizing=False):
    """Load data and run portfolio backtest on a single 3-month window."""
    pair_dfs = {}
    for p in ALL_PAIRS:
        pk = p.replace('/', '_')
        f = f'{DATA_DIR}/{pk}.pkl'
        if not os.path.exists(f):
            continue
        with open(f, 'rb') as fh:
            d = pickle.load(fh)
        df = d.get(p)
        if df is None:
            continue
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        pair_dfs[p] = df

    rng = random.Random(42)
    ref = pair_dfs[max(pair_dfs, key=lambda p: len(pair_dfs[p]))]
    ref_y = ref[ref.index.year == int(window_label)]
    if len(ref_y) < 129600:
        logger.error(f"Not enough data in {window_label}")
        return
    si = rng.randint(0, len(ref_y) - 129600)
    st = ref_y.index[si]
    et = ref_y.index[si + 129599]

    window = {}
    for p, df in pair_dfs.items():
        dy = df[df.index.year == int(window_label)]
        m = (dy.index >= st) & (dy.index <= et)
        sliced = dy.loc[m].copy()
        if not sliced.empty:
            window[p] = sliced

    logger.info(f"Window {window_label}: {st.date()} -> {et.date()}, {len(window)} pairs")

    cfg.TRADEABLE_PAIRS = list(window.keys())
    bho.TRADEABLE_PAIRS = list(window.keys())

    all_tfs = {tf: {} for tf in B_TF_LADDER}
    for p, df in window.items():
        for tf in B_TF_LADDER:
            r = pd.DataFrame()
            r['open'] = df['open'].resample(tf).first()
            r['high'] = df['high'].resample(tf).max()
            r['low'] = df['low'].resample(tf).min()
            r['close'] = df['close'].resample(tf).last()
            r.dropna(subset=['close'], inplace=True)
            if not r.empty:
                all_tfs[tf][p] = r

    strength = precompute_strength(all_tfs, n_jobs=1)
    valid_pairs = list(window.keys())
    if signal_type == 'breakout':
        signal_lookup = {}
        signal_lookup[trade_tf] = precompute_breakout_signals(
            all_tfs[trade_tf], trade_tf, lookback=5,
        )
    else:
        signals, signal_lookup = precompute_signals_vectorized(
            strength, valid_pairs, min_div=cfg.MIN_DIVERGENCE,
            top_n=cfg.STRENGTH_TOP_N, n_jobs=1,
        )
    atr_cache = precompute_atrs(all_tfs, n_jobs=1)

    first = next((all_tfs[trade_tf][p] for p in all_tfs[trade_tf]), None)
    sd = first.index[0].strftime('%Y-%m-%d')
    ed = first.index[-1].strftime('%Y-%m-%d')

    pm = PortfolioManager(
        max_positions=max_positions,
        max_daily_risk_pct=daily_risk_pct,
        max_trade_risk_pct=max_trade_risk,
        min_trade_risk_pct=min_trade_risk,
        per_currency_exposure=per_curr_exposure,
        enable_replacement=enable_replacement,
    )

    result = run_portfolio_backtest(
        all_tfs, strength, signal_lookup, atr_cache,
        sd, ed, pm, initial_balance=1000.0, trade_tf=trade_tf,
        invert_signal=invert_signal,
        disable_trend_exit=disable_trend_exit,
        adx_threshold=adx_threshold,
        signal_type=signal_type,
        atr_chandelier_mult=atr_chandelier_mult,
        max_hold_bars=max_hold_bars,
        enable_regime_sizing=enable_regime_sizing,
    )
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Portfolio-aware backtest')
    parser.add_argument('--max-pos', type=int, default=5, help='Max positions')
    parser.add_argument('--daily-risk', type=float, default=0.02, help='Daily risk budget %')
    parser.add_argument('--trade-risk', type=float, default=0.01, help='Max risk per trade %')
    parser.add_argument('--min-risk', type=float, default=0.002, help='Min risk per trade %')
    parser.add_argument('--currency-exp', type=int, default=2, help='Max per currency side')
    parser.add_argument('--no-replace', action='store_true', help='Disable position replacement')
    parser.add_argument('--year', type=str, default='2019', help='Window year')
    parser.add_argument('--trade-tf', type=str, default='5min', choices=B_TF_LADDER,
                        help='Timeframe for entry signals (default: 5min)')
    parser.add_argument('--invert-signal', action='store_true',
                        help='Invert entry direction (mean reversion mode)')
    parser.add_argument('--disable-trend-exit', action='store_true',
                        help='Disable trend-reversal exit (SL/TP only)')
    parser.add_argument('--adx-filter', type=float, default=0.0,
                        help='Min ADX threshold for entry (0=disabled, 20-25 typical)')
    parser.add_argument('--signal', type=str, default='divergence',
                        choices=['divergence', 'breakout'],
                        help='Signal type (divergence or breakout)')
    parser.add_argument('--chandelier-mult', type=float, default=None,
                        help='ATR multiplier for chandelier trailing stop (default: 2.5)')
    parser.add_argument('--max-hold-days', type=int, default=None,
                        help='Maximum holding period in days (default: 7)')
    parser.add_argument('--regime-sizing', action='store_true',
                        help='Enable ADX-based regime sizing')
    args = parser.parse_args()

    max_hold = args.max_hold_days * 24 * 60 if args.max_hold_days else None

    result = run_test(
        max_positions=args.max_pos,
        daily_risk_pct=args.daily_risk,
        max_trade_risk=args.trade_risk,
        min_trade_risk=args.min_risk,
        per_curr_exposure=args.currency_exp,
        enable_replacement=not args.no_replace,
        window_label=args.year,
        trade_tf=args.trade_tf,
        invert_signal=args.invert_signal,
        disable_trend_exit=args.disable_trend_exit,
        adx_threshold=args.adx_filter,
        signal_type=args.signal,
        atr_chandelier_mult=args.chandelier_mult,
        max_hold_bars=max_hold,
        enable_regime_sizing=args.regime_sizing,
    )
