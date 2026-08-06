"""
Verify proven MR strategy on resampled 1min->30min data.
This should match test_final_scalper.py results.
"""
import pandas as pd
import numpy as np
import pickle
import os
from collections import defaultdict

RISK_PER_TRADE = 0.02
MAX_CONCURRENT = 10
DAILY_LOSS_LIMIT = 0.05
LEVERAGE = 100
INITIAL_CAPITAL = 2500.0

SPREAD_MODEL = {
    'EUR/USD': 0.8, 'GBP/USD': 1.0, 'USD/JPY': 1.0, 'AUD/USD': 1.2,
    'USD/CAD': 1.2, 'USD/CHF': 1.2, 'GBP/JPY': 3.0, 'EUR/JPY': 2.5,
    'AUD/JPY': 2.5, 'NZD/USD': 1.5,
}

SESSION_CLOSE_HOUR = 17


def pip_info(pair_name):
    pip_size = 0.01 if 'JPY' in pair_name else 0.0001
    return pip_size, 10.0


def load_pair_data(pair_file, pair_name):
    fpath = os.path.join('/root/data', f'{pair_file}.pkl')
    if not os.path.exists(fpath):
        return pd.DataFrame()
    data = pickle.load(open(fpath, 'rb'))
    df = data[pair_name].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    if len(df) > 100000:
        df = df.resample('30min').agg({
            'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'volume': 'sum'
        }).dropna()
    return df


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def compute_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()


def run_backtest(pairs, start_date='2025-01-01', end_date='2026-07-15'):
    capital = INITIAL_CAPITAL
    daily_pnl = defaultdict(float)
    current_date = None
    open_positions = []
    all_trades = []
    equity_curve = []

    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)

    pair_data = {}
    pair_ind = {}

    for pair_file, pair_name in pairs:
        df = load_pair_data(pair_file, pair_name)
        if len(df) == 0:
            continue
        df = df[(df.index >= start_dt) & (df.index <= end_dt)]
        if len(df) == 0:
            continue
        pair_data[pair_name] = df
        print(f"Loaded {pair_name}: {len(df)} bars")

        pair_ind[pair_name] = {
            'rsi': compute_rsi(df['close']),
            'ema_fast': compute_ema(df['close'], 8),
            'ema_slow': compute_ema(df['close'], 21),
        }

    if not pair_data:
        print("No data!")
        return {}

    all_times = sorted(set().union(*[set(df.index) for df in pair_data.values()]))
    print(f"\nBacktest: {all_times[0]} to {all_times[-1]}, {len(all_times)} bars\n")

    for t in all_times:
        td = t.date()
        if current_date != td:
            daily_pnl = defaultdict(float)
            current_date = td

        # --- EXITS ---
        remaining = []
        for pos in open_positions:
            pn = pos['pair']
            df = pair_data.get(pn)
            if df is None or t not in df.index:
                remaining.append(pos)
                continue
            price = df.loc[t, 'close']
            pip_size, pip_dollar = pip_info(pn)

            if t.hour == SESSION_CLOSE_HOUR:
                should_exit, reason = True, 'session_close'
            elif pos['direction'] == 'long' and price <= pos['sl']:
                should_exit, reason = True, 'stop_loss'
            elif pos['direction'] == 'short' and price >= pos['sl']:
                should_exit, reason = True, 'stop_loss'
            else:
                should_exit = False

            if should_exit:
                spread = SPREAD_MODEL.get(pn, 1.5) * pip_size
                if pos['direction'] == 'long':
                    exit_p = price - spread / 2
                    pnl_pips = (exit_p - pos['entry']) / pip_size
                else:
                    exit_p = price + spread / 2
                    pnl_pips = (pos['entry'] - exit_p) / pip_size
                pnl_pips -= 1.4
                pnl_dollars = pnl_pips * pip_dollar * pos['lots']

                daily_pnl[td] += pnl_dollars
                capital += pnl_dollars
                all_trades.append({
                    'pair': pn, 'dir': pos['direction'],
                    'entry_time': pos['entry_time'], 'exit_time': t,
                    'pnl_pips': pnl_pips, 'pnl$': pnl_dollars, 'reason': reason,
                })
            else:
                remaining.append(pos)
        open_positions = remaining

        if daily_pnl[td] < -(DAILY_LOSS_LIMIT * capital):
            continue
        if len(open_positions) >= MAX_CONCURRENT:
            continue

        # --- ENTRIES (Pure MR, no order flow) ---
        for pn, df in pair_data.items():
            if t not in df.index:
                continue
            idx = df.index.get_loc(t)
            if idx < 50:
                continue

            price = df.loc[t, 'close']
            pip_size, pip_dollar = pip_info(pn)
            spread = SPREAD_MODEL.get(pn, 1.5) * pip_size

            rsi_val = pair_ind[pn]['rsi'].iloc[idx]
            ema_f = pair_ind[pn]['ema_fast'].iloc[idx]
            ema_s = pair_ind[pn]['ema_slow'].iloc[idx]

            # LONG: RSI oversold + price below EMAs
            if rsi_val < 30 and price < ema_f and price < ema_s:
                entry_p = price + spread / 2
                sl = entry_p - 20 * pip_size

                risk_amt = capital * RISK_PER_TRADE
                sl_dist = abs(entry_p - sl)
                if sl_dist == 0:
                    continue
                lots = round(risk_amt / (sl_dist / pip_size * pip_dollar), 2)
                if lots < 0.01:
                    continue
                margin = lots * 100000 * entry_p / LEVERAGE
                if margin > capital * 0.95:
                    continue

                open_positions.append({
                    'pair': pn, 'direction': 'long',
                    'entry': entry_p, 'entry_time': t,
                    'sl': sl, 'lots': lots,
                })

            # SHORT: RSI overbought + price above EMAs
            elif rsi_val > 70 and price > ema_f and price > ema_s:
                entry_p = price - spread / 2
                sl = entry_p + 20 * pip_size

                risk_amt = capital * RISK_PER_TRADE
                sl_dist = abs(sl - entry_p)
                if sl_dist == 0:
                    continue
                lots = round(risk_amt / (sl_dist / pip_size * pip_dollar), 2)
                if lots < 0.01:
                    continue
                margin = lots * 100000 * entry_p / LEVERAGE
                if margin > capital * 0.95:
                    continue

                open_positions.append({
                    'pair': pn, 'direction': 'short',
                    'entry': entry_p, 'entry_time': t,
                    'sl': sl, 'lots': lots,
                })

        equity_curve.append({'time': t, 'equity': capital})

    if not all_trades:
        print("No trades!")
        return {}

    wins = [t for t in all_trades if t['pnl$'] > 0]
    losses = [t for t in all_trades if t['pnl$'] <= 0]
    total_pnl = sum(t['pnl$'] for t in all_trades)
    wr = len(wins) / len(all_trades) * 100
    avg_win = np.mean([t['pnl$'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl$'] for t in losses])) if losses else 0
    pf = sum(t['pnl$'] for t in wins) / (sum(abs(t['pnl$']) for t in losses) + 1e-10)

    peak_eq = INITIAL_CAPITAL
    max_dd = 0
    for eq in equity_curve:
        if eq['equity'] > peak_eq:
            peak_eq = eq['equity']
        dd = (peak_eq - eq['equity']) / peak_eq * 100
        if dd > max_dd:
            max_dd = dd

    pair_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
    for t in all_trades:
        pair_stats[t['pair']]['trades'] += 1
        pair_stats[t['pair']]['pnl'] += t['pnl$']
        if t['pnl$'] > 0:
            pair_stats[t['pair']]['wins'] += 1

    exit_stats = defaultdict(int)
    for t in all_trades:
        exit_stats[t['reason']] += 1

    months = (all_times[-1] - all_times[0]).days / 30.0
    cagr = ((capital / INITIAL_CAPITAL) ** (12 / months) - 1) * 100 if months > 0 else 0

    return {
        'total_trades': len(all_trades),
        'win_rate': wr,
        'total_pnl': total_pnl,
        'profit_factor': pf,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'max_drawdown_pct': max_dd,
        'final_capital': capital,
        'cagr_monthly': cagr,
        'trades': all_trades,
        'pair_stats': dict(pair_stats),
        'exit_stats': dict(exit_stats),
    }


if __name__ == '__main__':
    pairs = [
        ('EUR_USD', 'EUR/USD'), ('GBP_USD', 'GBP/USD'),
        ('USD_JPY', 'USD/JPY'), ('AUD_USD', 'AUD/USD'),
        ('USD_CAD', 'USD/CAD'), ('USD_CHF', 'USD/CHF'),
        ('GBP_JPY', 'GBP/JPY'), ('EUR_JPY', 'EUR/JPY'),
        ('AUD_JPY', 'AUD/JPY'), ('NZD_USD', 'NZD/USD'),
    ]

    print("=" * 70)
    print("PROVEN MR STRATEGY VERIFICATION")
    print("=" * 70)

    results = run_backtest(pairs, start_date='2025-01-01', end_date='2026-07-15')

    if results:
        print(f"\n{'='*70}")
        print("RESULTS")
        print(f"{'='*70}")
        print(f"Total trades: {results['total_trades']}")
        print(f"Win rate: {results['win_rate']:.1f}%")
        print(f"Total P&L: ${results['total_pnl']:.2f}")
        print(f"Profit factor: {results['profit_factor']:.2f}")
        print(f"Avg win: ${results['avg_win']:.2f}")
        print(f"Avg loss: ${results['avg_loss']:.2f}")
        print(f"Max drawdown: {results['max_drawdown_pct']:.1f}%")
        print(f"Final capital: ${results['final_capital']:.2f}")
        print(f"CAGR (monthly): {results['cagr_monthly']:.1f}%")

        print(f"\nPer-pair stats:")
        for pair, stats in sorted(results['pair_stats'].items()):
            wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
            print(f"  {pair}: {stats['trades']}T, {wr:.0f}% WR, ${stats['pnl']:.2f}")

        print(f"\nExit reasons:")
        for reason, count in sorted(results['exit_stats'].items()):
            print(f"  {reason}: {count}")
