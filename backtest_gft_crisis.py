#!/usr/bin/env python3
"""
backtest_gft_crisis.py — Crisis-year Monte-Carlo backtest for GFT dynamic risk
  • 6 major pairs only
  • Max 1 concurrent position
  • Dynamic risk: 10% → 5% as DD goes 0% → 30%
  • 28-day rolling window, 5000 simulations per crisis year
"""

import os
import random
import json
import pickle
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone

import sys
_root_path = '/root'
_nestquant_path = '/root/nestquant'
# nestquant must be found before root so GFT config takes priority
for p in [_root_path, _nestquant_path]:
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

import config
from backtest_hybrid_opt import (
    load_and_resample,
    precompute_strength,
    precompute_signals_vectorized,
    precompute_atrs,
    HybridBacktest,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_DIR = '/root/data'
TEST_YEARS = [2019, 2020, 2022, 2023, 2026]
SIMS_PER_YEAR = 5000
WINDOW_DAYS = 28

# ---------------------------------------------------------------------------
# Pair data loader
# ---------------------------------------------------------------------------

def load_pair_pickle(pair):
    pair_key_underscore = pair.replace('/', '_')
    pkl_path = os.path.join(DATA_DIR, f"{pair_key_underscore}.pkl")
    if not os.path.exists(pkl_path):
        return None
    with open(pkl_path, 'rb') as f:
        data = pickle.load(f)
    df = data.get(pair)
    if df is None:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def load_all_pairs(pairs):
    result = {}
    for pair in pairs:
        df = load_pair_pickle(pair)
        if df is not None:
            result[pair] = df
    return result


# ---------------------------------------------------------------------------
# Window sampler
# ---------------------------------------------------------------------------

def get_year_window_data(pair_dfs, year, window_days=WINDOW_DAYS):
    # Use first pair's index as the time reference for slicing.
    # All pairs should share the same index, so we pick the pair with the most data.
    ref_pair = max(pair_dfs, key=lambda p: len(pair_dfs[p]))
    ref_df = pair_dfs[ref_pair]
    ref_year = ref_df[ref_df.index.year == year]
    if ref_year.empty:
        return None
    total_1m_bars = len(ref_year)
    bars_needed = window_days * 1440
    max_start = total_1m_bars - bars_needed
    if max_start <= 0:
        return None
    start_idx = random.randint(0, max_start)
    start_time = ref_year.index[start_idx]
    end_time = ref_year.index[start_idx + bars_needed - 1]

    dfs = []
    for pair, df in pair_dfs.items():
        df_year = df[df.index.year == year]
        if df_year.empty:
            continue
        df_year = df_year.copy()
        mask = (df_year.index >= start_time) & (df_year.index <= end_time)
        sliced = df_year.loc[mask]
        if sliced.empty:
            continue
        sliced['pair'] = pair
        dfs.append(sliced)
    if not dfs:
        return None
    combined = pd.concat(dfs)
    combined.sort_index(inplace=True)
    return combined


# ---------------------------------------------------------------------------
# GFT Dynamic Risk Manager
# ---------------------------------------------------------------------------

class GFTDynamicRiskManager:
    def __init__(self, initial_balance: float):
        self.balance = initial_balance
        self.peak_balance = initial_balance

    @property
    def dd_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.balance) / self.peak_balance * 100.0

    def can_trade(self):
        if self.balance <= 0:
            return False, "Account bust"
        return True, "OK"

    def calculate_lot_size(self, pair: str, entry_price: float, stop_price: float) -> float:
        from risk_manager import calculate_lot_size as gft_calc_lot
        sl_pips = abs(entry_price - stop_price) / config.TICK_SIZES.get(pair, 0.0001)
        if sl_pips < 1.0:
            return 0.0
        return gft_calc_lot(pair, self.balance, self.dd_pct, sl_pips)

    def record_trade(self, pnl: float):
        self.balance += pnl
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance

    def reset_daily(self):
        pass


# ---------------------------------------------------------------------------
# Single window simulation
# ---------------------------------------------------------------------------

def run_single_window(window_df, tradeable_pairs):
    per_pair = {}
    for pair in tradeable_pairs:
        df_pair = window_df[window_df['pair'] == pair].drop(columns='pair')
        if not df_pair.empty:
            per_pair[pair] = df_pair

    all_tfs = {}
    for tf in ["5min", "15min", "4h", "1D"]:
        all_tfs[tf] = {}
        for pair, df in per_pair.items():
            res = pd.DataFrame()
            res["open"] = df["open"].resample(tf).first()
            res["high"] = df["high"].resample(tf).max()
            res["low"] = df["low"].resample(tf).min()
            res["close"] = df["close"].resample(tf).last()
            res.dropna(subset=["close"], inplace=True)
            all_tfs[tf][pair] = res

    strength = precompute_strength(all_tfs, n_jobs=1)
    signals, signal_lookup = precompute_signals_vectorized(
        strength, tradeable_pairs,
        min_div=config.MIN_DIVERGENCE if hasattr(config, 'MIN_DIVERGENCE') else 5.0,
        top_n=config.STRENGTH_TOP_N if hasattr(config, 'STRENGTH_TOP_N') else 5,
        n_jobs=1,
    )
    atr_cache = precompute_atrs(all_tfs, n_jobs=1)

    gft_risk_mgr = GFTDynamicRiskManager(initial_balance=config.ACCOUNT_BALANCE)

    start_date = window_df.index.min().strftime('%Y-%m-%d')
    end_date = window_df.index.max().strftime('%Y-%m-%d')
    bt = HybridBacktest(strength, signal_lookup, all_tfs, atr_cache)
    bt.b_atr_sl = config.SL_ATR_MULTIPLIER
    bt.b_rrr = config.TP_RRR
    bt.b_min_div = config.MIN_DIVERGENCE if hasattr(config, 'MIN_DIVERGENCE') else 5.0
    result = bt.run(start_date, end_date, external_risk_mgr=gft_risk_mgr)

    events = []
    for t in result['trade_log']:
        entry = pd.to_datetime(t['entry_time'])
        events.append((entry, 1))
        exit_t = t['exit_time']
        if exit_t is not None:
            events.append((pd.to_datetime(exit_t), -1))
    events.sort(key=lambda x: x[0])
    concurrent = 0
    max_concurrent = 0
    for _, delta in events:
        concurrent += delta
        if concurrent > max_concurrent:
            max_concurrent = concurrent
    if max_concurrent > config.MAX_CONCURRENT_POSITIONS:
        result['net_pnl'] = 0.0
        result['valid_days'] = 0
        result['kill_switch_triggered'] = True

    daily = pd.DataFrame(result['trade_log'])
    if not daily.empty:
        daily['date'] = pd.to_datetime(daily['entry_time']).dt.date
        profit_by_day = daily.groupby('date')['pnl'].sum()
        valid_days = (profit_by_day >= config.VALID_DAY_MIN_PROFIT).sum()
    else:
        valid_days = 0
    result['valid_days'] = int(valid_days)
    result['final_pnl'] = float(result['net_pnl'])
    return result


# ---------------------------------------------------------------------------
# Monte-Carlo driver
# ---------------------------------------------------------------------------

def run_crisis_backtest(pairs, test_years=None, sims_per_year=None):
    if test_years is None:
        test_years = TEST_YEARS
    if sims_per_year is None:
        sims_per_year = SIMS_PER_YEAR

    print(f"Loading data for {len(pairs)} pairs...")
    pair_dfs = load_all_pairs(pairs)
    print(f"Loaded {len(pair_dfs)}/{len(pairs)} pairs")

    all_year_stats = []
    for year in test_years:
        print(f"\nYear {year}: running {sims_per_year} simulations...")
        year_results = []
        t0 = datetime.now()
        for i in range(sims_per_year):
            window = get_year_window_data(pair_dfs, year)
            if window is None:
                continue
            res = run_single_window(window, pairs)
            year_results.append(res)
            if (i + 1) % 500 == 0:
                elapsed = (datetime.now() - t0).total_seconds()
                print(f"  {i+1}/{sims_per_year} ({elapsed:.0f}s)")

        if not year_results:
            print(f"  No data for year {year}, skipping.")
            continue

        final_pnls = [r['final_pnl'] for r in year_results]
        payouts = sum(1 for r in year_results if r['final_pnl'] >= 150.0 and r['valid_days'] >= 3)
        stats = {
            "year": year,
            "simulations": len(year_results),
            "payout_rate": round(payouts / len(year_results) * 100.0, 2),
            "avg_pnl": round(np.mean(final_pnls), 2),
            "median_pnl": round(np.median(final_pnls), 2),
            "worst_5_percent": round(np.percentile(final_pnls, 5), 2),
            "best_95_percent": round(np.percentile(final_pnls, 95), 2),
            "max_drawdown": round(max(r.get('max_dd_pct', 0) for r in year_results), 2),
            "kill_switch_triggers": sum(1 for r in year_results if r.get('kill_switch_triggered')),
            "avg_valid_days": round(np.mean([r['valid_days'] for r in year_results]), 2),
            "positive_sims": sum(1 for p in final_pnls if p > 0),
            "positive_rate": round(sum(1 for p in final_pnls if p > 0) / len(final_pnls) * 100, 2),
        }
        all_year_stats.append(stats)
        print(f"  Done: avg_pnl=${stats['avg_pnl']:.2f}, "
              f"payout_rate={stats['payout_rate']}%, "
              f"positive={stats['positive_rate']}%")

    return all_year_stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sims', type=int, default=SIMS_PER_YEAR)
    parser.add_argument('--years', type=int, nargs='+', default=TEST_YEARS)
    args = parser.parse_args()

    output_path = '/root/nestquant/backtests/crisis_years_results.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    stats = run_crisis_backtest(config.TRADEABLE_PAIRS, test_years=args.years, sims_per_year=args.sims)

    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\nBacktest completed. Results written to {output_path}")

    # Summary table
    print(f"\n{'Year':<6} {'Sims':<6} {'Avg PnL':>10} {'Med PnL':>10} {'Worst5%':>10} {'Best95%':>10} {'Payout%':>8} {'Pos%':>6} {'MaxDD':>7}")
    print('-' * 75)
    for s in stats:
        print(f"{s['year']:<6} {s['simulations']:<6} ${s['avg_pnl']:>7.2f} ${s['median_pnl']:>7.2f} ${s['worst_5_percent']:>7.2f} ${s['best_95_percent']:>7.2f} {s['payout_rate']:>7.2f}% {s['positive_rate']:>5.1f}% {s['max_drawdown']:>6.2f}%")


if __name__ == '__main__':
    main()
