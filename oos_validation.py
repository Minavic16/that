#!/usr/bin/env python3
"""
IS/OOS validation for the original divergence strategy.

IS: 3 years Monte Carlo (2019, 2020, 2022) — 500 sims/year.
OOS: 10 windows from 2023.

Uses original MIN_DIVERGENCE=3.0 from config.
"""

import os, sys, random, json, pickle
import numpy as np
import pandas as pd
from datetime import datetime

sys.path = ['/root/nestquant', '/root'] + [p for p in sys.path if p not in ('/root', '/root/nestquant')]
for mod in list(sys.modules.keys()):
    if 'config' in mod or 'risk_manager' in mod or 'backtest' in mod or 'currency_strength' in mod or 'indicators' in mod:
        del sys.modules[mod]

import config
from backtest_hybrid_opt import (
    load_and_resample, precompute_strength,
    precompute_signals_vectorized, precompute_atrs, HybridBacktest,
)
from backtest_gft_crisis import load_all_pairs, GFTDynamicRiskManager

DATA_DIR = '/root/data'
WINDOW_DAYS = 28
IS_YEARS = [2019, 2020, 2022]
OOS_YEARS = [2023]
IS_SIMS_PER_YEAR = 50
OOS_SIMS = 10


def get_window_data(pair_dfs, year, window_days=WINDOW_DAYS):
    ref_pair = max(pair_dfs, key=lambda p: len(pair_dfs[p]))
    ref_df = pair_dfs[ref_pair]
    ref_year = ref_df[ref_df.index.year == year]
    if ref_year.empty:
        return None
    total_1m = len(ref_year)
    bars_needed = window_days * 1440
    max_start = total_1m - bars_needed
    if max_start <= 0:
        return None
    start_idx = random.randint(0, max_start)
    start_time = ref_year.index[start_idx]
    end_time = ref_year.index[start_idx + bars_needed - 1]
    window = {}
    for pair, df in pair_dfs.items():
        df_year = df[df.index.year == year]
        if df_year.empty:
            continue
        mask = (df_year.index >= start_time) & (df_year.index <= end_time)
        sliced = df_year.loc[mask].copy()
        if not sliced.empty:
            window[pair] = sliced
    return window if len(window) >= 3 else None


def run_single_window(window_per_pair, tradeable_pairs, min_div):
    pairs_in_window = [p for p in tradeable_pairs if p in window_per_pair]
    if len(pairs_in_window) < 3:
        return None

    per_pair = {}
    for pair in pairs_in_window:
        df = window_per_pair[pair].copy()
        cols_keep = [c for c in ['open','high','low','close','volume'] if c in df.columns]
        df = df[cols_keep]
        per_pair[pair] = df

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
            if not res.empty:
                all_tfs[tf][pair] = res

    strength = precompute_strength(all_tfs, n_jobs=1)

    available_currencies = set()
    for tf in strength:
        if not strength[tf].empty:
            available_currencies.update(strength[tf].columns)
    valid_pairs = []
    for p in pairs_in_window:
        base, quote = p.split('/')
        if base in available_currencies and quote in available_currencies:
            valid_pairs.append(p)
    if len(valid_pairs) < 3:
        return None

    signals, signal_lookup = precompute_signals_vectorized(
        strength, valid_pairs,
        min_div=min_div,
        top_n=config.STRENGTH_TOP_N if hasattr(config, 'STRENGTH_TOP_N') else 5,
        n_jobs=1,
    )
    atr_cache = precompute_atrs(all_tfs, n_jobs=1)

    risk_mgr = GFTDynamicRiskManager(initial_balance=config.ACCOUNT_BALANCE)
    first_pair_5m = next((all_tfs['5min'][p] for p in all_tfs['5min'] if p in valid_pairs), None)
    if first_pair_5m is None:
        return None
    start_date = first_pair_5m.index[0].strftime('%Y-%m-%d')
    end_date = first_pair_5m.index[-1].strftime('%Y-%m-%d')

    bt = HybridBacktest(strength, signal_lookup, all_tfs, atr_cache)
    bt.b_min_div = min_div
    bt.b_atr_sl = config.SL_ATR_MULTIPLIER
    bt.b_rrr = config.TP_RRR
    result = bt.run(start_date, end_date, external_risk_mgr=risk_mgr)

    # Post-process
    events = []
    for t in result['trade_log']:
        entry = pd.to_datetime(t['entry_time'])
        events.append((entry, 1))
        exit_t = t['exit_time']
        if exit_t is not None:
            events.append((pd.to_datetime(exit_t), -1))
    events.sort(key=lambda x: x[0])
    concurrent = 0
    max_conc = 0
    for _, delta in events:
        concurrent += delta
        if concurrent > max_conc:
            max_conc = concurrent
    kill = max_conc > config.MAX_CONCURRENT_POSITIONS

    daily = pd.DataFrame(result['trade_log'])
    if not daily.empty and 'entry_time' in daily.columns:
        daily['date'] = pd.to_datetime(daily['entry_time']).dt.date
        profit_by_day = daily.groupby('date')['pnl'].sum()
        valid_days = (profit_by_day >= config.VALID_DAY_MIN_PROFIT).sum()
    else:
        valid_days = 0

    result['valid_days'] = int(valid_days)
    result['final_pnl'] = 0.0 if kill else float(result['net_pnl'])
    return result


def run_monte_carlo(pair_dfs, years, sims_per_year, min_div, pairs):
    all_results = []
    for year in years:
        for i in range(sims_per_year):
            window = get_window_data(pair_dfs, year, WINDOW_DAYS)
            if window is None:
                continue
            res = run_single_window(window, pairs, min_div)
            if res is not None:
                all_results.append(res)
    return all_results


def compute_stats(results):
    pnls = [r['final_pnl'] for r in results]
    if not pnls:
        return None
    payouts = sum(1 for r in results if r['final_pnl'] >= 150.0 and r['valid_days'] >= 3)
    return {
        'simulations': len(results),
        'avg_pnl': round(np.mean(pnls), 2),
        'median_pnl': round(np.median(pnls), 2),
        'std_pnl': round(np.std(pnls), 2),
        'worst_5pct': round(np.percentile(pnls, 5), 2),
        'best_95pct': round(np.percentile(pnls, 95), 2),
        'payout_rate': round(payouts / len(results) * 100, 2),
        'positive_rate': round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 2),
        'max_drawdown': round(max(r.get('max_dd_pct', 0) for r in results), 2),
        'avg_valid_days': round(np.mean([r['valid_days'] for r in results]), 2),
        'avg_trades': round(np.mean([r['trades'] for r in results]), 1),
        'avg_win_rate': round(np.mean([r['win_rate'] for r in results]), 1),
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--is_sims', type=int, default=IS_SIMS_PER_YEAR)
    parser.add_argument('--oos_sims', type=int, default=OOS_SIMS)
    parser.add_argument('--output', type=str, default='/root/nestquant/backtests/oos_results.json')
    args = parser.parse_args()

    pairs = config.TRADEABLE_PAIRS
    min_div = config.MIN_DIVERGENCE  # use original value
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print(f"Config: MIN_DIVERGENCE={min_div}, SL_ATR={config.SL_ATR_MULTIPLIER}, RRR={config.TP_RRR}", flush=True)
    print("Loading pair data...", flush=True)
    pair_dfs = load_all_pairs(pairs)
    print(f"Loaded {len(pair_dfs)} pairs", flush=True)

    # ───── IS ─────
    print(f"\n{'='*60}")
    print(f"IS: {IS_YEARS} — {args.is_sims} sims/year")
    print(f"{'='*60}", flush=True)

    t0 = datetime.now()
    is_results = run_monte_carlo(pair_dfs, IS_YEARS, args.is_sims, min_div, pairs)
    is_stats = compute_stats(is_results)
    elapsed = (datetime.now() - t0).total_seconds()

    if is_stats:
        print(f"  {is_stats['simulations']} sims in {elapsed:.0f}s ({elapsed/is_stats['simulations']:.1f}s/sim)", flush=True)
        print(f"  avg=${is_stats['avg_pnl']:>+.2f}  med=${is_stats['median_pnl']:>+.2f}  "
              f"p95=${is_stats['best_95pct']:>+.2f}  pay={is_stats['payout_rate']:.2f}%  "
              f"pos={is_stats['positive_rate']:.1f}%  DD={is_stats['max_drawdown']:.1f}%  "
              f"t={is_stats['avg_trades']}  wr={is_stats['avg_win_rate']}%", flush=True)

    # ───── OOS ─────
    print(f"\n{'='*60}")
    print(f"OOS: {OOS_YEARS} — {args.oos_sims} windows")
    print(f"{'='*60}", flush=True)

    oos_results = []
    for i in range(args.oos_sims):
        window = get_window_data(pair_dfs, OOS_YEARS[0], WINDOW_DAYS)
        if window is None:
            print(f"  [{i+1}/{args.oos_sims}] NO DATA", flush=True)
            continue
        res = run_single_window(window, pairs, min_div)
        if res is not None:
            oos_results.append(res)
            prom = sum(1 for t in res.get('trade_log', []) if t.get('promoting'))
            print(f"  [{i+1}/{args.oos_sims}] PnL=${res['final_pnl']:>+8.2f}  "
                  f"t={res['trades']}  wr={res['win_rate']:.1f}%  "
                  f"DD={res['max_dd_pct']:.1f}%  v={res['valid_days']}  "
                  f"prom={prom}", flush=True)
        else:
            print(f"  [{i+1}/{args.oos_sims}] NO RESULT", flush=True)

    oos_stats = compute_stats(oos_results) if oos_results else None

    # ───── REPORT ─────
    print(f"\n{'='*60}")
    print(f"IS / OOS COMPARISON (min_div={min_div})")
    print(f"{'='*60}")

    metrics = ['simulations','avg_pnl','median_pnl','std_pnl',
               'payout_rate','positive_rate','max_drawdown',
               'avg_valid_days','avg_trades','avg_win_rate']
    print(f"\n{'Metric':<20} {'IS':>15} {'OOS':>15}")
    print('-' * 50)
    for m in metrics:
        iv = is_stats.get(m, '') if is_stats else ''
        ov = oos_stats.get(m, '') if oos_stats else ''
        if isinstance(iv, float):
            print(f"{m:<20} {iv:>15.2f}  {ov:>15.2f}")
        else:
            print(f"{m:<20} {iv:>15}  {ov:>15}")

    if oos_stats:
        print(f"\nOOS windows detail:")
        for i, r in enumerate(oos_results):
            prom = sum(1 for t in r.get('trade_log', []) if t.get('promoting'))
            print(f"  [{i+1}] PnL=${r['final_pnl']:>+8.2f}  trades={r['trades']}  "
                  f"WR={r['win_rate']:.1f}%  DD={r['max_dd_pct']:.1f}%  "
                  f"valid={r['valid_days']}  prom={prom}")

    # Save
    full = {
        'params': {'min_div': min_div, 'sl_atr': config.SL_ATR_MULTIPLIER, 'rrr': config.TP_RRR},
        'in_sample': is_stats,
        'out_of_sample': oos_stats,
        'oos_windows': [{'pnl': r['final_pnl'], 'trades': r['trades'],
                         'win_rate': r['win_rate'], 'dd': r['max_dd_pct'],
                         'valid_days': r['valid_days']} for r in oos_results] if oos_results else [],
    }
    with open(args.output, 'w') as f:
        json.dump(full, f, indent=2)
    print(f"\nResults -> {args.output}")
