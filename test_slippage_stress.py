"""
SLIPPAGE STRESS TEST
Tests how the strategy degrades with worse-than-assumed execution costs.
"""
import sys, os, numpy as np
sys.path.insert(0, '/root')
os.chdir('/root')

import importlib.util
spec = importlib.util.spec_from_file_location("tcc", "/root/test_combined_corr.py")
tcc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tcc)

import position_sizing as ps

ACC = 2500.0

# Run OOS baseline first (0.3 slippage, $3.50 commission as built-in)
print("Running OOS baseline...")
oos = tcc.run_sim('2025-01-01', '2026-07-19', max_conc=20)
log = oos['trades_log']
print(f"Baseline: {len(log)} trades\n")

# The backtest already charges: spread/2 + 0.3 pips on entry + exit
# Each trade's entry and exit both have: (spread*0.5+0.3)*pip cost
# Let's calculate what each trade currently pays vs what we'd pay at worse slippage

print("="*80)
print("  CURRENT COST STRUCTURE (built into backtest)")
print("="*80)
print(f"  Entry cost: (spread/2 + 0.3) pips each side")
print(f"  Commission: $3.50/lot/trade")
print(f"  Total per trade: ~1 round-trip = spread + 0.6 pips + $3.50")

# Current spread assumptions
SPREAD = {'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,
          'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,
          'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}

print(f"\n  Current spread assumptions:")
for p, s in sorted(SPREAD.items()):
    print(f"    {p:10s}: {s:.1f} pips")

# Stress test: increase slippage AND spread
print("\n" + "="*80)
print("  STRESS TEST: Extra slippage on top of built-in costs")
print("="*80)
print(f"  (Extra slippage = additional pips charged on entry AND exit)")

SLIPPAGE_LEVELS = [0, 0.5, 1.0, 2.0, 3.0, 5.0]

results = []

for extra_slip in SLIPPAGE_LEVELS:
    # Adjust P&L for extra slippage
    adjusted_pnls = []
    for t in log:
        pip = ps.pip_size_for_pair(t['pair'])
        pv = ps.pip_value_per_lot(t['pair'])
        lot = t['lot']
        extra_cost = extra_slip * pip * pv * lot * 2  # entry + exit
        adjusted_pnls.append(t['pnl'] - extra_cost)
    
    n = len(adjusted_pnls)
    wins = [p for p in adjusted_pnls if p > 0]
    losses = [p for p in adjusted_pnls if p <= 0]
    nw = len(wins)
    nl = len(losses)
    wr = nw/n*100
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    pf = sum(wins)/abs(sum(losses)) if losses and sum(losses) != 0 else 99
    ev = (nw/n)*avg_win + (nl/n)*avg_loss
    
    # Monthly
    monthly = {}
    for i, t in enumerate(log):
        month = t['ts'][:7]
        monthly.setdefault(month, 0)
        monthly[month] += adjusted_pnls[i]
    
    losing = sum(1 for v in monthly.values() if v < 0)
    worst = min(monthly.values()) if monthly else 0
    best = max(monthly.values()) if monthly else 0
    
    results.append({
        'slip': extra_slip, 'n': n, 'wr': wr, 'pf': pf,
        'ev': ev, 'ev_pct': ev/ACC*100,
        'losing': losing, 'worst': worst, 'best': best,
        'total': sum(adjusted_pnls), 'avg_win': avg_win, 'avg_loss': avg_loss
    })
    
    print(f"\n  +{extra_slip:.1f} pips slippage:")
    print(f"    {n}t WR={wr:.1f}% PF={pf:.1f} EV=${ev:.0f} ({ev/ACC*100:.2f}%)")
    print(f"    Losing months: {losing}/19  Worst: ${worst:,.0f}  Best: ${best:,.0f}")
    print(f"    Total P&L: ${sum(adjusted_pnls):,.0f}")

# Summary table
print("\n" + "="*80)
print("  STRESS TEST SUMMARY")
print("="*80)
print(f"\n  {'Extra Slip':>10s} {'WR':>6s} {'PF':>5s} {'EV/Trade':>9s} {'EV%':>7s} {'$/mo':>8s} {'LosM':>5s} {'Worst':>9s}")
print(f"  {'-'*60}")
for r in results:
    monthly_avg = r['total'] / 19
    print(f"  +{r['slip']:.1f} pips   {r['wr']:5.1f}% {r['pf']:4.1f}  ${r['ev']:7.0f}  {r['ev_pct']:5.2f}% ${monthly_avg:7,.0f}  {r['losing']:>2d}/19 ${r['worst']:8,.0f}")

# Also test spread widening (multiply all spreads)
print("\n" + "="*80)
print("  SPREAD WIDENING TEST (all spreads multiplied)")
print("="*80)

# The backtest uses fixed spreads. Real spreads can widen 2-5x during news.
# Current avg spread ~1.5 pips. During news: 3-7.5 pips.
# This means each trade pays 1.5-7.5 pips instead of 1.5 pips.
# Extra cost = (real_spread - assumed_spread) + extra_slippage

# Average assumed spread across all pairs
avg_spread = np.mean(list(SPREAD.values()))
print(f"  Average assumed spread: {avg_spread:.2f} pips")
print(f"  If real spreads are 2x: avg {avg_spread*2:.2f} pips (extra {avg_spread:.2f} pips per side)")
print(f"  If real spreads are 3x: avg {avg_spread*3:.2f} pips (extra {avg_spread*2:.2f} pips per side)")

# Test spread multipliers
for mult in [1.0, 1.5, 2.0, 3.0]:
    extra_per_pip = avg_spread * (mult - 1)  # extra spread on entry
    # Plus same on exit
    total_extra = extra_per_pip * 2
    
    adjusted_pnls = []
    for t in log:
        pip = ps.pip_size_for_pair(t['pair'])
        pv = ps.pip_value_per_lot(t['pair'])
        lot = t['lot']
        extra_cost = total_extra * pv * lot
        adjusted_pnls.append(t['pnl'] - extra_cost)
    
    n = len(adjusted_pnls)
    wins = [p for p in adjusted_pnls if p > 0]
    losses = [p for p in adjusted_pnls if p <= 0]
    wr = len(wins)/n*100
    pf = sum(wins)/abs(sum(losses)) if losses and sum(losses) != 0 else 99
    ev = np.mean(adjusted_pnls)
    total = sum(adjusted_pnls)
    monthly_avg = total / 19
    
    monthly = {}
    for i, t in enumerate(log):
        month = t['ts'][:7]
        monthly.setdefault(month, 0)
        monthly[month] += adjusted_pnls[i]
    losing = sum(1 for v in monthly.values() if v < 0)
    worst = min(monthly.values()) if monthly else 0
    
    print(f"\n  {mult:.1f}x spreads (extra {total_extra:.2f} pips/trade):")
    print(f"    WR={wr:.1f}% PF={pf:.1f} EV=${ev:.0f} ${monthly_avg:,.0f}/mo LosM={losing}/19 Worst=${worst:,.0f}")

# Combined worst case: 2x spread + 2 pips slippage
print("\n" + "="*80)
print("  WORST REALISTIC CASE: 2x spread + 2 pips slippage")
print("="*80)
combined_extra = avg_spread * 2 + 2.0  # extra spread + slippage, both sides
adjusted_pnls = []
for t in log:
    pip = ps.pip_size_for_pair(t['pair'])
    pv = ps.pip_value_per_lot(t['pair'])
    lot = t['lot']
    extra_cost = combined_extra * pv * lot
    adjusted_pnls.append(t['pnl'] - extra_cost)

n = len(adjusted_pnls)
wins = [p for p in adjusted_pnls if p > 0]
losses = [p for p in adjusted_pnls if p <= 0]
wr = len(wins)/n*100
pf = sum(wins)/abs(sum(losses)) if losses and sum(losses) != 0 else 99
ev = np.mean(adjusted_pnls)
total = sum(adjusted_pnls)

monthly = {}
for i, t in enumerate(log):
    month = t['ts'][:7]
    monthly.setdefault(month, 0)
    monthly[month] += adjusted_pnls[i]
losing = sum(1 for v in monthly.values() if v < 0)
worst = min(monthly.values()) if monthly else 0

print(f"  Extra cost: {combined_extra:.2f} pips per side")
print(f"  WR={wr:.1f}% PF={pf:.1f} EV=${ev:.0f}")
print(f"  Total: ${total:,.0f}  ${total/19:,.0f}/mo")
print(f"  Losing months: {losing}/19  Worst: ${worst:,.0f}")
