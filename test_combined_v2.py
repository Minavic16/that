"""
Combined Backtest v2 - COT + Order Flow (lightweight) + MR
Three-layer system:
  1. COT: Weekly directional bias (institutional positioning)
  2. Order Flow: Lightweight tick rule imbalance + VWAP deviation
  3. MR: Mean reversion execution (RSI + EMA + session filter)
"""
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

from cot_signal import COTSignal

# =================== CONFIG ===================
RISK_PER_TRADE = 0.02
MAX_CONCURRENT = 10
DAILY_LOSS_LIMIT = 0.05
LEVERAGE = 100
COMMISSION_LOTS = 7.0
INITIAL_CAPITAL = 2500.0

COT_MIN_STRENGTH = 0.3
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
EMA_FAST = 8
EMA_SLOW = 21

SPREAD_MODEL = {
    'EUR/USD': 0.8, 'GBP/USD': 1.0, 'USD/JPY': 1.0, 'AUD/USD': 1.2,
    'USD/CAD': 1.2, 'USD/CHF': 1.2, 'GBP/JPY': 3.0, 'EUR/JPY': 2.5,
    'AUD/JPY': 2.5, 'NZD/USD': 1.5,
}

# Pip size and dollar value per pip per standard lot (100k units)
def pip_info(pair_name):
    if 'JPY' in pair_name:
        pip_size = 0.01
    else:
        pip_size = 0.0001
    # Dollar value per pip per standard lot
    pip_value_per_lot = 10.0
    return pip_size, pip_value_per_lot


def load_pair_data(pair_file, pair_name):
    fpath = os.path.join('/root/data', f'{pair_file}.pkl')
    if not os.path.exists(fpath):
        return pd.DataFrame()
    data = pickle.load(open(fpath, 'rb'))
    df = data[pair_name].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    
    # Resample to 30m bars if data is 1-minute
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


def precompute_lightweight_of(df, step=48):
    """Precompute lightweight order flow metrics (tick rule imbalance + VWAP dev)."""
    n = len(df)
    
    # Tick direction
    close = df['close'].values
    tick_sign = np.zeros(n)
    for i in range(1, n):
        if close[i] > close[i-1]:
            tick_sign[i] = 1.0
        elif close[i] < close[i-1]:
            tick_sign[i] = -1.0
        else:
            tick_sign[i] = tick_sign[i-1] if i > 0 else 0
    
    # Signed volume
    vol = df['volume'].values
    signed_vol = tick_sign * vol
    
    # Rolling order imbalance (10-bar)
    order_imb = np.zeros(n)
    for i in range(10, n):
        order_imb[i] = np.sum(signed_vol[i-10:i]) / (np.sum(vol[i-10:i]) + 1e-10)
    
    # VWAP
    cum_vol = np.cumsum(vol)
    cum_pv = np.cumsum(close * vol)
    vwap = cum_pv / (cum_vol + 1e-10)
    
    # VWAP deviation
    vwap_dev = (close - vwap) / (vwap + 1e-10)
    
    # Simple momentum (5-bar return)
    momentum = np.zeros(n)
    for i in range(5, n):
        momentum[i] = (close[i] - close[i-5]) / (close[i-5] + 1e-10)
    
    return {
        'order_imbalance': order_imb,
        'vwap_deviation': vwap_dev,
        'momentum': momentum,
        'tick_sign': tick_sign,
    }


def run_backtest(pairs, start_date='2025-01-01', end_date='2026-07-15'):
    cot = COTSignal()
    
    capital = INITIAL_CAPITAL
    daily_pnl = defaultdict(float)
    current_date = None
    open_positions = []
    all_trades = []
    equity_curve = []
    
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    
    # Preload data + precompute OF
    pair_data = {}
    pair_of = {}
    for pair_file, pair_name in pairs:
        df = load_pair_data(pair_file, pair_name)
        if len(df) > 0:
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            pair_data[pair_name] = df
            print(f"Loaded {pair_name}: {len(df)} bars")
            pair_of[pair_name] = precompute_lightweight_of(df, step=48)
    
    if not pair_data:
        print("No data loaded!")
        return {}
    
    # Precompute RSI + EMA for all pairs
    pair_indicators = {}
    for pair_name, df in pair_data.items():
        rsi = compute_rsi(df['close'])
        ema_f = compute_ema(df['close'], EMA_FAST)
        ema_s = compute_ema(df['close'], EMA_SLOW)
        pair_indicators[pair_name] = {
            'rsi': rsi,
            'ema_fast': ema_f,
            'ema_slow': ema_s,
        }
    
    # Get common times
    all_times = set()
    for df in pair_data.values():
        all_times.update(df.index)
    all_times = sorted(all_times)
    
    print(f"\nBacktest: {all_times[0]} to {all_times[-1]}, {len(all_times)} bars")
    
    cot_signals = {}
    for pair_name in pair_data.keys():
        cot_signals[pair_name] = cot.get_signal(pair_name)
        print(f"  COT {pair_name}: {cot_signals[pair_name]['direction']} ({cot_signals[pair_name]['strength']:.2f})")
    
    trade_count = 0
    win_count = 0
    
    for t in all_times:
        new_date = t.date()
        if current_date != new_date:
            daily_pnl = defaultdict(float)
            current_date = new_date
        
        # --- EXITS ---
        remaining = []
        for pos in open_positions:
            pn = pos['pair']
            df = pair_data.get(pn)
            if df is None or t not in df.index:
                remaining.append(pos)
                continue
            
            price = df.loc[t, 'close']
            
            # Session close
            if t.hour == 17:
                should_exit = True
                reason = 'session_close'
            elif pos['direction'] == 'long' and price <= pos['sl']:
                should_exit = True
                reason = 'stop_loss'
            elif pos['direction'] == 'short' and price >= pos['sl']:
                should_exit = True
                reason = 'stop_loss'
            else:
                should_exit = False
                reason = ''
            
            if should_exit:
                pip_size, pip_val_dollar = pip_info(pn)
                spread = SPREAD_MODEL.get(pn, 1.5) * pip_size
                
                if pos['direction'] == 'long':
                    exit_p = price - spread / 2
                    pnl_pips = (exit_p - pos["entry"]) / pip_size
                else:
                    exit_p = price + spread / 2
                    pnl_pips = (pos["entry"] - exit_p) / pip_size
                
                pnl_pips -= 1.4  # commission in pips
                pnl_dollars = pnl_pips * pip_val_dollar * pos["lots"]
                
                daily_pnl[new_date] += pnl_dollars
                capital += pnl_dollars
                if pnl_dollars > 0:
                    win_count += 1
                trade_count += 1
                
                all_trades.append({
                    'pair': pn, 'dir': pos['direction'],
                    'entry_time': pos['entry_time'], 'exit_time': t,
                    'entry': pos['entry'], 'exit': exit_p,
                    'pnl_pips': pnl_pips, 'pnl$:': pnl_dollars,
                    'reason': reason,
                })
            else:
                remaining.append(pos)
        
        open_positions = remaining
        
        # Daily loss limit
        if daily_pnl[new_date] < -(DAILY_LOSS_LIMIT * capital):
            continue
        if len(open_positions) >= MAX_CONCURRENT:
            continue
        
        # --- ENTRIES ---
        for pn, df in pair_data.items():
            if t not in df.index:
                continue
            
            idx = df.index.get_loc(t)
            if idx < 50:
                continue
            
            cot_s = cot_signals[pn]
            if cot_s['strength'] < COT_MIN_STRENGTH:
                continue
            
            rsi_val = pair_indicators[pn]['rsi'].iloc[idx]
            ema_f = pair_indicators[pn]['ema_fast'].iloc[idx]
            price = df.loc[t, 'close']
            
            of = pair_of[pn]
            order_imb = of['order_imbalance'][idx]
            vwap_dev = of['vwap_deviation'][idx]
            momentum = of['momentum'][idx]
            
            pip_size, pip_val_dollar = pip_info(pn)
            spread = SPREAD_MODEL.get(pn, 1.5) * pip_size
            
            # LONG: COT long + RSI oversold + price below EMA + VWAP dev negative + buying pressure
            if (cot_s['direction'] == 'long' and
                rsi_val < RSI_OVERSOLD and
                price < ema_f and
                vwap_dev < -0.0003 and
                order_imb > 0.05):
                
                entry_p = price + spread / 2
                sl = entry_p - 20 * pip_size
                risk_amt = capital * RISK_PER_TRADE
                sl_dist = abs(entry_p - sl)
                lots = round(risk_amt / (sl_dist / pip_size * pip_val_dollar), 2)
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
            
            # SHORT: COT short + RSI overbought + price above EMA + VWAP dev positive + selling pressure
            elif (cot_s['direction'] == 'short' and
                  rsi_val > RSI_OVERBOUGHT and
                  price > ema_f and
                  vwap_dev > 0.0003 and
                  order_imb < -0.05):
                
                entry_p = price - spread / 2
                sl = entry_p + 20 * pip_size
                risk_amt = capital * RISK_PER_TRADE
                sl_dist = abs(sl - entry_p)
                lots = round(risk_amt / (sl_dist / pip_size * pip_val_dollar), 2)
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
        
        peak = max([e['equity'] for e in equity_curve] + [INITIAL_CAPITAL])
        equity_curve.append({'time': t, 'equity': capital})
    
    if not all_trades:
        print("No trades!")
        return {}
    
    wins = [t for t in all_trades if t['pnl$:'] > 0]
    losses = [t for t in all_trades if t['pnl$:'] <= 0]
    
    total_pnl = sum(t['pnl$:'] for t in all_trades)
    wr = len(wins) / len(all_trades) * 100
    avg_win = np.mean([t['pnl$:'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl$:'] for t in losses])) if losses else 0
    pf = sum(t['pnl$:'] for t in wins) / (sum(abs(t['pnl$:']) for t in losses) + 1e-10)
    
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
        pair_stats[t['pair']]['pnl'] += t['pnl$:']
        if t['pnl$:'] > 0:
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
        'equity_curve': equity_curve,
        'pair_stats': dict(pair_stats),
        'exit_stats': dict(exit_stats),
    }


if __name__ == '__main__':
    pairs = [
        ('EUR_USD', 'EUR/USD'),
        ('GBP_USD', 'GBP/USD'),
        ('USD_JPY', 'USD/JPY'),
        ('AUD_USD', 'AUD/USD'),
        ('USD_CAD', 'USD/CAD'),
        ('USD_CHF', 'USD/CHF'),
        ('GBP_JPY', 'GBP/JPY'),
        ('EUR_JPY', 'EUR/JPY'),
        ('AUD_JPY', 'AUD/JPY'),
        ('NZD_USD', 'NZD/USD'),
    ]
    
    print("=" * 70)
    print("COMBINED BACKTEST v2: COT + Order Flow + MR")
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
