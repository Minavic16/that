"""
FILTERED OOS TEST — Uses the trade_analysis.csv from test_combined_corr.py
"""
import csv, numpy as np

CSV = '/root/logs/trade_analysis.csv'
OOS_CUT = '2025-01-01'
ACCOUNT = 2500.0

with open(CSV) as f:
    trades = list(csv.DictReader(f))

# Convert types
for t in trades:
    t['pnl'] = float(t['pnl'])
    t['bars'] = int(t['bars'])
    oos = t['ts'] >= OOS_CUT
    t['hour'] = int(t['ts'].split(' ')[1].split(':')[0]) if len(t['ts']) > 10 else 0
    t['oos'] = oos

print(f"Total trades: {len(trades)}")
print(f"IS trades: {sum(1 for t in trades if not t['oos'])}")
print(f"OOS trades: {sum(1 for t in trades if t['oos'])}")

def analyze(trades, label):
    if not trades:
        print(f"  {label:40s} | 0 trades")
        return
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    wr = len(wins)/len(trades)*100
    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
    total = sum(t['pnl'] for t in trades)
    pf = (sum(t['pnl'] for t in wins)) / abs(sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else 99
    ev = (len(wins)/len(trades))*avg_win + (len(losses)/len(trades))*avg_loss
    ev_pct = ev / ACCOUNT * 100
    print(f"  {label:40s} | {len(trades):5d}t WR={wr:5.1f}% PF={pf:5.2f} AvgWin=${avg_win:8.0f} AvgLoss=${avg_loss:8.0f} EV=${ev:7.0f} ({ev_pct:+.2f}%) Total=${total:12.0f}")

def filter_trades(trades, **kwargs):
    result = []
    for t in trades:
        if kwargs.get('oos_only') and not t['oos']:
            continue
        if kwargs.get('no_tf') and t['regime'] == 'tf':
            continue
        if kwargs.get('mr_only') and t['regime'] != 'mr':
            continue
        if kwargs.get('no_bad_hours') and t['hour'] in [11, 21, 15, 17]:
            continue
        if kwargs.get('no_bad_pairs') and t['pair'] in ['AUD/CAD', 'NZD/USD', 'AUD/JPY']:
            continue
        if kwargs.get('london_only') and t['dir'] == 'session' and 'new_york' in t.get('exit_reason', ''):
            continue
        if kwargs.get('no_early') and t['bars'] <= 5:
            continue
        if kwargs.get('min_bars') and t['bars'] < kwargs['min_bars']:
            continue
        result.append(t)
    return result

print("\n" + "="*100)
print("  OOS FILTER ANALYSIS")
print("="*100)

oos = [t for t in trades if t['oos']]

scenarios = [
    ("Baseline (all OOS)", {}),
    ("MR Only", {'mr_only': True}),
    ("MR + No Bad Hours (11,21,15,17)", {'mr_only': True, 'no_bad_hours': True}),
    ("MR + No Bad Hours + No Bad Pairs", {'mr_only': True, 'no_bad_hours': True, 'no_bad_pairs': True}),
    ("MR + No Bad Hours + No Early (bars>5)", {'mr_only': True, 'no_bad_hours': True, 'no_early': True}),
    ("MR + No Bad Hours + No Bad Pairs + No Early", {'mr_only': True, 'no_bad_hours': True, 'no_bad_pairs': True, 'no_early': True}),
    ("MR London Hours Only (8-10,22-0)", {'mr_only': True, 'min_bars': 1}),
    ("MR Best Hours Only (0,8,9,10,22,23)", {'mr_only': True}),
    ("TF Only", {}),
    ("TF + No Early", {'no_early': True}),
]

print("\n--- OOS ONLY ---")
for name, kwargs in scenarios:
    filtered = filter_trades(oos, oos_only=False, **kwargs)
    analyze(filtered, name)

print("\n--- FULL PERIOD (IS+OOS) ---")
for name, kwargs in scenarios:
    filtered = filter_trades(trades, oos_only=False, **kwargs)
    analyze(filtered, name)

# Pair-level OOS analysis
print("\n" + "="*100)
print("  OOS BY PAIR")
print("="*100)
pairs = sorted(set(t['pair'] for t in oos))
for pair in pairs:
    pt = [t for t in oos if t['pair'] == pair]
    analyze(pt, pair)

print("\n" + "="*100)
print("  OOS BY REGIME + EXIT REASON")
print("="*100)
for regime in ['mr', 'tf']:
    for reason in ['session_close', 'time_stop', 'stop_loss', 'take_profit', 'trend_reversal']:
        rt = [t for t in oos if t['regime'] == regime and t['exit_reason'] == reason]
        if rt:
            analyze(rt, f"{regime} / {reason}")
