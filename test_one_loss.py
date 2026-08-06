"""
ONE LOSS PER PAIR PER DAY — Backtest comparison
Runs OOS with and without the rule, compares results.
"""
import sys, os
sys.path.insert(0, '/root')
os.chdir('/root')

import importlib.util
spec = importlib.util.spec_from_file_location("tcc", "/root/test_combined_corr.py")
tcc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tcc)

import numpy as np

ACC = 2500.0

print("="*80)
print("  ONE LOSS PER PAIR PER DAY — OOS Comparison")
print("="*80)

# Run WITHOUT the rule (baseline)
print("\n--- BASELINE (no one-loss rule) ---")
import time
t0 = time.time()
baseline = tcc.run_sim('2025-01-01', '2026-07-19', max_conc=20, one_loss_per_pair=False)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")

# Run WITH the rule
print("\n--- WITH ONE LOSS PER PAIR PER DAY ---")
t0 = time.time()
one_loss = tcc.run_sim('2025-01-01', '2026-07-19', max_conc=20, one_loss_per_pair=True)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")

def compare(name, base, modified):
    if not base or not modified:
        print(f"\n{name}: Missing data")
        return

    b_log = base['trades_log']
    m_log = modified['trades_log']
    b_pnls = [t['pnl'] for t in b_log]
    m_pnls = [t['pnl'] for t in m_log]

    # Calculate stats
    def stats(pnls, label):
        if not pnls:
            return {'n': 0, 'wr': 0, 'pf': 0, 'avg': 0, 'total': 0}
        wins = sum(1 for p in pnls if p > 0)
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        return {
            'n': len(pnls),
            'wr': wins/len(pnls)*100,
            'pf': gross_profit/gross_loss if gross_loss > 0 else 999,
            'avg': np.mean(pnls),
            'total': sum(pnls),
        }

    b = stats(b_pnls, "baseline")
    m = stats(m_pnls, "one-loss")

    print(f"\n{name} Comparison:")
    print(f"  {'Metric':20s} {'Baseline':>12s} {'One-Loss':>12s} {'Change':>12s}")
    print(f"  {'-'*56}")

    for key, label in [('n', 'Trades'), ('wr', 'Win Rate%'), ('pf', 'Profit Factor'), ('avg', 'Avg P&L'), ('total', 'Total P&L')]:
        bv = b[key]
        mv = m[key]
        if key in ('wr', 'pf'):
            diff = f"{mv-bv:+.1f}"
            print(f"  {label:20s} {bv:11.1f} {mv:11.1f} {diff:>12s}")
        else:
            diff = f"${mv-bv:+,.0f}"
            print(f"  {label:20s} ${bv:10,.0f} ${mv:10,.0f} {diff:>12s}")

    # Show trades avoided
    trades_avoided = b['n'] - m['n']
    losing_trades_avoided = sum(1 for t in b_log if t['pnl'] < 0) - sum(1 for t in m_log if t['pnl'] < 0)
    print(f"\n  Trades avoided: {trades_avoided}")
    print(f"  Losing trades avoided: {losing_trades_avoided}")

compare("OOS (2025-2026)", baseline, one_loss)

# Also run full period
print(f"\n{'='*80}")
print("  FULL PERIOD (2022-2026)")
print("="*80)

print("\n--- BASELINE ---")
t0 = time.time()
full_base = tcc.run_sim('2022-01-01', '2026-07-19', max_conc=20, one_loss_per_pair=False)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")

print("\n--- ONE LOSS PER PAIR ---")
t0 = time.time()
full_one = tcc.run_sim('2022-01-01', '2026-07-19', max_conc=20, one_loss_per_pair=True)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")

compare("Full Period", full_base, full_one)
