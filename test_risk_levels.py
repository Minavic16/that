"""
MONTHLY BREAKDOWN + LOWER RISK TESTS
Shows worst months and tests conservative sizing
"""
import sys, os
sys.path.insert(0, '/root')
os.chdir('/root')

import importlib.util, numpy as np, time
from collections import defaultdict

spec = importlib.util.spec_from_file_location("tcc", "/root/test_combined_corr.py")
tcc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tcc)

# Test multiple risk levels
RISK_LEVELS = [3.5, 2.0, 1.0, 0.5]
ACC = 2500.0

print("="*80)
print("  MONTHLY BREAKDOWN + RISK SENSITIVITY")
print("="*80)

all_results = {}

for risk in RISK_LEVELS:
    print(f"\n--- Risk {risk}% per trade ---")
    t0 = time.time()
    
    # Monkey-patch the risk levels
    orig_mr = tcc.MR_RISK
    orig_tf = tcc.TF_RISK
    tcc.MR_RISK = risk
    tcc.TF_RISK = risk * 0.63  # Maintain same ratio (2.2/3.5 = 0.63)
    
    oos = tcc.run_sim('2025-01-01', '2026-07-19', max_conc=20, fixed_sizing=ACC)
    
    tcc.MR_RISK = orig_mr
    tcc.TF_RISK = orig_tf
    
    dt = time.time()-t0
    if not oos:
        print(f"  No results ({dt:.0f}s)")
        continue
    
    log = oos['trades_log']
    
    # Monthly P&L
    monthly = defaultdict(float)
    monthly_trades = defaultdict(int)
    monthly_wins = defaultdict(int)
    for t in log:
        month = t['ts'][:7]  # YYYY-MM
        monthly[month] += t['pnl']
        monthly_trades[month] += 1
        if t['pnl'] > 0:
            monthly_wins[month] += 1
    
    # Overall stats
    pnls = [t['pnl'] for t in log]
    total = sum(pnls)
    n_months = len(monthly)
    
    print(f"  {len(log)}t WR={oos['wr']:.1f}% PF={oos['pf']:.1f} MDD={oos['mdd']:.1f}%")
    print(f"  Final=${ACC+total:,.0f} Return={(total/ACC)*100:.1f}%")
    print(f"  AvgP&L=${np.mean(pnls):.2f}/trade")
    print(f"  ${total/n_months:,.0f}/month ({total/n_months/ACC*100:.1f}%)")
    
    # Monthly breakdown
    print(f"\n  {'Month':8s} {'Trades':>6s} {'WR':>6s} {'P&L':>10s} {'Cumul':>10s}")
    print(f"  {'-'*42}")
    cumul = 0
    worst_month = 0
    worst_month_name = ""
    losing_months = 0
    for month in sorted(monthly.keys()):
        pnl = monthly[month]
        n_t = monthly_trades[month]
        n_w = monthly_wins[month]
        wr = n_w/n_t*100 if n_t > 0 else 0
        cumul += pnl
        if pnl < worst_month:
            worst_month = pnl
            worst_month_name = month
        if pnl < 0:
            losing_months += 1
        marker = " <-- WORST" if pnl == worst_month else ""
        print(f"  {month:8s} {n_t:6d} {wr:5.1f}% ${pnl:9,.0f} ${cumul:9,.0f}{marker}")
    
    print(f"\n  Losing months: {losing_months}/{n_months}")
    print(f"  Worst month: {worst_month_name} = ${worst_month:,.0f} ({worst_month/ACC*100:.1f}%)")
    print(f"  Best month: ${max(monthly.values()):,.0f} ({max(monthly.values())/ACC*100:.1f}%)")
    
    all_results[risk] = {
        'n': len(log), 'wr': oos['wr'], 'pf': oos['pf'],
        'mdd': oos['mdd'], 'total': total, 'monthly': total/n_months,
        'worst_month': worst_month, 'losing_months': losing_months,
        'n_months': n_months
    }

# Summary table
print(f"\n{'='*80}")
print("  RISK SENSITIVITY SUMMARY")
print("="*80)
print(f"\n  {'Risk':>5s} {'Trades':>6s} {'WR':>6s} {'PF':>5s} {'MDD':>6s} {'$/mo':>8s} {'$/mo%':>7s} {'Worst':>8s} {'LosM':>5s}")
print(f"  {'-'*60}")
for risk in sorted(all_results.keys()):
    r = all_results[risk]
    print(f"  {risk:>4.1f}% {r['n']:6d} {r['wr']:5.1f}% {r['pf']:4.1f} {r['mdd']:5.1f}% ${r['monthly']:7,.0f} {r['monthly']/ACC*100:6.1f}% ${r['worst_month']:7,.0f} {r['losing_months']:>3d}/{r['n_months']}")

# Also test MR-only at 1% risk
print(f"\n{'='*80}")
print("  MR-ONLY at 1% Risk (removing losing TF)")
print("="*80)

# Temporarily disable TF entries by setting TF_RISK to 0
orig_tf = tcc.TF_RISK
tcc.TF_RISK = 0  # This will make TF sizing fail, preventing TF entries

t0 = time.time()
oos_mr = tcc.run_sim('2025-01-01', '2026-07-19', max_conc=20, fixed_sizing=ACC)
tcc.TF_RISK = orig_tf
dt = time.time()-t0

if oos_mr:
    tcc.pr(oos_mr, "MR-Only OOS (1% risk)")
    log = oos_mr['trades_log']
    pnls = [t['pnl'] for t in log]
    monthly = defaultdict(float)
    monthly_trades = defaultdict(int)
    monthly_wins = defaultdict(int)
    for t in log:
        month = t['ts'][:7]
        monthly[month] += t['pnl']
        monthly_trades[month] += 1
        if t['pnl'] > 0:
            monthly_wins[month] += 1
    
    n_months = len(monthly)
    total = sum(pnls)
    
    print(f"\n  Monthly breakdown (MR-Only):")
    print(f"  {'Month':8s} {'Trades':>6s} {'WR':>6s} {'P&L':>10s}")
    print(f"  {'-'*32}")
    for month in sorted(monthly.keys()):
        pnl = monthly[month]
        n_t = monthly_trades[month]
        n_w = monthly_wins[month]
        wr = n_w/n_t*100 if n_t > 0 else 0
        print(f"  {month:8s} {n_t:6d} {wr:5.1f}% ${pnl:9,.0f}")
    
    losing = sum(1 for v in monthly.values() if v < 0)
    worst = min(monthly.values())
    print(f"\n  Losing months: {losing}/{n_months}")
    print(f"  Worst month: ${worst:,.0f} ({worst/ACC*100:.1f}%)")
    print(f"  Average: ${total/n_months:,.0f}/mo ({total/n_months/ACC*100:.1f}%)")
