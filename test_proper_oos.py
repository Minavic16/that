"""
FIXED SIZING OOS — Uses modified run_sim with fixed_sizing=$2,500
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
print("  FIXED SIZING OOS — $2,500 Balance")
print("="*80)

# Run OOS with fixed sizing
import time
t0 = time.time()
oos = tcc.run_sim('2025-01-01', '2026-07-19', max_conc=20, fixed_sizing=ACC)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")

if oos:
    tcc.pr(oos, "OOS Fixed $2,500")
    
    # MDD analysis
    log = oos['trades_log']
    pnls = [t['pnl'] for t in log]
    peak = ACC; mdd = 0; bal = ACC
    for p in pnls:
        bal += p
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd
    print(f"    MDD (recalc): {mdd*100:.1f}%")
    print(f"    Final: ${bal:,.0f} (return: {(bal/ACC-1)*100:.1f}%)")
    print(f"    $/month: ${oos['n']/18 * np.mean(pnls):,.0f}")
    
    # By regime
    print(f"\n  BY REGIME:")
    for regime in ['mr', 'tf']:
        rt = [t for t in log if t['regime'] == regime]
        if rt:
            rp = [t['pnl'] for t in rt]
            rw = sum(1 for p in rp if p > 0)
            print(f"    {regime.upper()}: {len(rt)}t WR={rw/len(rt)*100:.1f}% AvgP&L=${np.mean(rp):.0f} Total=${sum(rp):,.0f}")
    
    # By exit reason
    print(f"\n  BY EXIT REASON:")
    for reason in ['session_close', 'time_stop', 'stop_loss', 'take_profit', 'trend_reversal']:
        rt = [t for t in log if t['exit_reason'] == reason]
        if rt:
            rp = [t['pnl'] for t in rt]
            rw = sum(1 for p in rp if p > 0)
            print(f"    {reason:20s}: {len(rt):4d}t WR={rw/len(rt)*100:5.1f}% AvgP&L=${np.mean(rp):8.0f}")
    
    # By pair
    print(f"\n  BY PAIR:")
    pairs = sorted(set(t['pair'] for t in log))
    for pair in pairs:
        pt = [t for t in log if t['pair'] == pair]
        pp = [t['pnl'] for t in pt]
        pw = sum(1 for p in pp if p > 0)
        print(f"    {pair:10s}: {len(pt):3d}t WR={pw/len(pt)*100:5.1f}% AvgP&L=${np.mean(pp):8.0f} Total=${sum(pp):10.0f}")

# Also run IS for comparison
print(f"\n{'='*80}")
print("  FIXED SIZING IS — $2,500 Balance")
print("="*80)
t0 = time.time()
is_r = tcc.run_sim('2022-01-01', '2024-12-31', max_conc=20, fixed_sizing=ACC)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")
if is_r:
    tcc.pr(is_r, "IS Fixed $2,500")

# Full period
print(f"\n{'='*80}")
print("  FIXED SIZING FULL — $2,500 Balance")
print("="*80)
t0 = time.time()
full = tcc.run_sim('2022-01-01', '2026-07-19', max_conc=20, fixed_sizing=ACC)
dt = time.time()-t0
print(f"Done in {dt:.0f}s")
if full:
    tcc.pr(full, "FULL Fixed $2,500")
