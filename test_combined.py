"""
Combined Backtest - COT + Order Flow + MR
Three-layer system:
  1. COT: Weekly directional bias (institutional positioning)
  2. Order Flow: Intraday entry timing (absorption, VWAP deviation)
  3. MR: Mean reversion execution (RSI + EMA + session filter)
"""
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

# Import our signal generators
from cot_signal import COTSignal
from orderflow_signal import OrderFlowSignal


# =================== CONFIG ===================
RISK_PER_TRADE = 0.02
MAX_CONCURRENT = 10
DAILY_LOSS_LIMIT = 0.05
LEVERAGE = 100
COMMISSION_LOTS = 7.0
SLIPPAGE_PIPS = 0.5
INITIAL_CAPITAL = 2500.0

# Signal thresholds
COT_MIN_STRENGTH = 0.3  # Minimum COT strength to trade
OF_MIN_STRENGTH = 0.1   # Minimum order flow strength
HURST_MR_MIN = 0.45     # Below this = trending (don't MR)
HURST_MR_MAX = 0.60     # Above this = mean reversion (good for MR)

# MR entry filters
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
EMA_FAST = 8
EMA_SLOW = 21

# Per-pair spread model (pips)
SPREAD_MODEL = {
    'EUR/USD': 0.8, 'GBP/USD': 1.0, 'USD/JPY': 1.0, 'AUD/USD': 1.2,
    'USD/CAD': 1.2, 'USD/CHF': 1.2, 'GBP/JPY': 3.0, 'GBP/AUD': 3.5,
    'EUR/AUD': 3.0, 'EUR/JPY': 2.5, 'EUR/GBP': 1.5, 'AUD/JPY': 2.5,
    'CAD/JPY': 2.5, 'CHF/JPY': 2.5, 'EUR/NZD': 3.5, 'GBP/NZD': 4.0,
    'AUD/NZD': 2.5, 'NZD/JPY': 2.5, 'USD/SGD': 2.0, 'USD/THB': 15.0,
    'NZD/USD': 1.5,
}

# Pip values
PIP_VALUES = {
    'USD/JPY': 0.01, 'GBP/JPY': 0.01, 'AUD/JPY': 0.01, 'CAD/JPY': 0.01,
    'CHF/JPY': 0.01, 'NZD/JPY': 0.01,
}


def load_pair_data(pair_file: str, pair_name: str) -> pd.DataFrame:
    fpath = os.path.join('/root/data', f'{pair_file}.pkl')
    if not os.path.exists(fpath):
        return pd.DataFrame()
    data = pickle.load(open(fpath, 'rb'))
    df = data[pair_name].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def compute_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


class CombinedStrategy:
    """Three-layer strategy: COT + Order Flow + MR."""
    
    def __init__(self):
        self.cot = COTSignal()
        self.of = OrderFlowSignal()
        self.cot_cache = {}
        self.of_cache = {}
    
    def get_cot_signal(self, pair_name: str) -> Dict:
        if pair_name not in self.cot_cache:
            self.cot_cache[pair_name] = self.cot.get_signal(pair_name)
        return self.cot_cache[pair_name]
    
    def precompute_of_signals(self, pair_name: str, df: pd.DataFrame, step: int = 48):
        """Precompute order flow signals for entire dataset (every 24 hours = 48 bars on 30m)."""
        cache = {}
        hurst_vals = []
        
        for i in range(100, len(df), step):
            window = df.iloc[max(0, i-2000):i+1]
            of = self.of.get_trade_signal(window)
            cache[i] = of
            hurst_vals.append(of['hurst'])
        
        self.of_cache[pair_name] = cache
        
        # Store avg hurst for the pair
        avg_hurst = np.mean(hurst_vals) if hurst_vals else 0.5
        self.of_cache[f"{pair_name}_avg_hurst"] = avg_hurst
        
        return cache
    
    def get_of_signal(self, pair_name: str, idx: int) -> Dict:
        """Get nearest precomputed OF signal."""
        cache = self.of_cache.get(pair_name, {})
        if not cache:
            return {'direction': 'neutral', 'strength': 0.0, 'hurst': 0.5,
                    'vwap_deviation': 0.0, 'order_imbalance': 0.0, 'regime': 'random'}
        
        # Find nearest precomputed index
        keys = sorted(cache.keys())
        nearest = min(keys, key=lambda k: abs(k - idx))
        return cache[nearest]
    
    def check_entry(self, pair_name: str, df: pd.DataFrame, idx: int) -> str:
        """
        Check if we should enter a trade.
        Returns: 'long', 'short', or None
        """
        if idx < max(EMA_SLOW, 50):
            return None
        
        # 1. COT Filter - weekly directional bias
        cot = self.get_cot_signal(pair_name)
        if cot['strength'] < COT_MIN_STRENGTH:
            return None
        
        # 2. Order Flow Filter - intraday timing
        of = self.get_of_signal(pair_name, idx)
        
        # Hurst filter: only MR when market is mean reverting
        hurst = of['hurst']
        if hurst > HURST_MR_MAX:
            # Market is trending - don't MR
            return None
        
        # 3. MR Entry Logic
        close = df['close'].iloc[idx]
        rsi = compute_rsi(df['close'].iloc[:idx+1]).iloc[-1]
        ema_fast = compute_ema(df['close'].iloc[:idx+1], EMA_FAST).iloc[-1]
        ema_slow = compute_ema(df['close'].iloc[:idx+1], EMA_SLOW).iloc[-1]
        
        spread = SPREAD_MODEL.get(pair_name, 1.5) * PIP_VALUES.get(pair_name, 0.0001)
        
        # Check VWAP deviation for entry zone
        vwap_dev = of['vwap_deviation']
        order_imb = of['order_imbalance']
        
        # LONG conditions:
        # - COT says institutions are long
        # - Price is oversold (RSI < 30)
        # - Price below EMA (pullback)
        # - VWAP deviation negative (price below VWAP)
        # - Order imbalance positive (buying pressure)
        if (cot['direction'] == 'long' and
            rsi < RSI_OVERSOLD and
            close < ema_fast and
            vwap_dev < -0.0005 and
            order_imb > 0):
            return 'long'
        
        # SHORT conditions:
        # - COT says institutions are short
        # - Price is overbought (RSI > 70)
        # - Price above EMA (pullback)
        # - VWAP deviation positive (price above VWAP)
        # - Order imbalance negative (selling pressure)
        if (cot['direction'] == 'short' and
            rsi > RSI_OVERBOUGHT and
            close > ema_fast and
            vwap_dev > 0.0005 and
            order_imb < 0):
            return 'short'
        
        return None
    
    def check_exit(self, entry_price: float, entry_time: pd.Timestamp,
                   current_price: float, current_time: pd.Timestamp,
                   direction: str, sl_price: float) -> Tuple[bool, str]:
        """
        Check if we should exit.
        Returns: (should_exit, reason)
        """
        pnl_pct = (current_price - entry_price) / entry_price * 100
        if direction == 'short':
            pnl_pct = -pnl_pct
        
        # Session close exit (5:00 PM EST)
        hour = current_time.hour
        if hour == 17:
            return True, 'session_close'
        
        # Stop loss
        if direction == 'long' and current_price <= sl_price:
            return True, 'stop_loss'
        if direction == 'short' and current_price >= sl_price:
            return True, 'stop_loss'
        
        # Take profit
        tp_mult = 1.5
        if direction == 'long' and current_price >= entry_price + tp_mult * (entry_price - sl_price):
            return True, 'take_profit'
        if direction == 'short' and current_price <= entry_price - tp_mult * (sl_price - entry_price):
            return True, 'take_profit'
        
        return False, ''


def run_backtest(pairs: List[Tuple[str, str]], start_date: str = '2024-01-01',
                 end_date: str = '2026-07-15') -> Dict:
    """
    Run combined backtest.
    """
    strategy = CombinedStrategy()
    
    capital = INITIAL_CAPITAL
    daily_pnl = defaultdict(float)
    current_date = None
    
    all_trades = []
    open_positions = []
    equity_curve = []
    
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    
    # Preload data and precompute OF signals
    pair_data = {}
    for pair_file, pair_name in pairs:
        df = load_pair_data(pair_file, pair_name)
        if len(df) > 0:
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            pair_data[pair_name] = df
            print(f"Loaded {pair_name}: {len(df)} bars")
            
            # Precompute OF signals
            print(f"  Precomputing order flow signals...")
            strategy.precompute_of_signals(pair_name, df, step=192)  # Every 4 days
            print(f"  Done.")
    
    if not pair_data:
        print("No data loaded!")
        return {}
    
    # Get common time range
    all_times = set()
    for df in pair_data.values():
        all_times.update(df.index)
    all_times = sorted(all_times)
    
    print(f"\nBacktest period: {all_times[0]} to {all_times[-1]}")
    print(f"Total bars: {len(all_times)}")
    
    trade_count = 0
    win_count = 0
    
    for t in all_times:
        new_date = t.date()
        if current_date != new_date:
            daily_pnl = defaultdict(float)
            current_date = new_date
        
        # Check exits for open positions
        remaining = []
        for pos in open_positions:
            pair_name = pos['pair']
            if pair_name not in pair_data:
                remaining.append(pos)
                continue
            
            df = pair_data[pair_name]
            if t not in df.index:
                remaining.append(pos)
                continue
            
            current_price = df.loc[t, 'close']
            should_exit, reason = strategy.check_exit(
                pos['entry_price'], pos['entry_time'],
                current_price, t, pos['direction'], pos['sl_price']
            )
            
            if should_exit:
                # Calculate P&L
                pip_value = PIP_VALUES.get(pair_name, 0.0001)
                spread = SPREAD_MODEL.get(pair_name, 1.5) * pip_value
                
                if pos['direction'] == 'long':
                    exit_price = current_price - spread / 2
                    pnl_pips = (exit_price - pos['entry_price']) / pip_value
                else:
                    exit_price = current_price + spread / 2
                    pnl_pips = (pos['entry_price'] - exit_price) / pip_value
                
                pnl_pips -= COMMISSION_LOTS * 2 / RISK_PER_TRADE  # Commission in pips
                pnl_dollars = pnl_pips * pip_value * pos['lots'] * 100
                
                daily_pnl[new_date] += pnl_dollars
                capital += pnl_dollars
                
                if pnl_dollars > 0:
                    win_count += 1
                trade_count += 1
                
                all_trades.append({
                    'pair': pair_name,
                    'direction': pos['direction'],
                    'entry_time': pos['entry_time'],
                    'exit_time': t,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'pnl_pips': pnl_pips,
                    'pnl_dollars': pnl_dollars,
                    'reason': reason,
                })
            else:
                remaining.append(pos)
        
        open_positions = remaining
        
        # Check daily loss limit
        if daily_pnl[new_date] < -(DAILY_LOSS_LIMIT * capital):
            continue
        
        # Check concurrent limit
        if len(open_positions) >= MAX_CONCURRENT:
            continue
        
        # Check entries for each pair
        for pair_name, df in pair_data.items():
            if t not in df.index:
                continue
            
            idx = df.index.get_loc(t)
            direction = strategy.check_entry(pair_name, df, idx)
            
            if direction is None:
                continue
            
            current_price = df.loc[t, 'close']
            pip_value = PIP_VALUES.get(pair_name, 0.0001)
            spread = SPREAD_MODEL.get(pair_name, 1.5) * pip_value
            
            if direction == 'long':
                entry_price = current_price + spread / 2
                sl_price = entry_price - 20 * pip_value
            else:
                entry_price = current_price - spread / 2
                sl_price = entry_price + 20 * pip_value
            
            # Position sizing
            risk_amount = capital * RISK_PER_TRADE
            sl_distance = abs(entry_price - sl_price)
            if sl_distance == 0:
                continue
            lots = risk_amount / (sl_distance / pip_value * 100)
            lots = round(lots, 2)
            if lots < 0.01:
                continue
            
            # Check margin
            margin_required = lots * 100000 * entry_price / LEVERAGE
            if margin_required > capital * 0.95:
                continue
            
            open_positions.append({
                'pair': pair_name,
                'direction': direction,
                'entry_price': entry_price,
                'entry_time': t,
                'sl_price': sl_price,
                'lots': lots,
            })
        
        # Record equity
        equity_curve.append({'time': t, 'equity': capital})
    
    # Calculate stats
    if not all_trades:
        print("No trades!")
        return {}
    
    wins = [t for t in all_trades if t['pnl_dollars'] > 0]
    losses = [t for t in all_trades if t['pnl_dollars'] <= 0]
    
    total_pnl = sum(t['pnl_dollars'] for t in all_trades)
    win_rate = len(wins) / len(all_trades) * 100
    avg_win = np.mean([t['pnl_dollars'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl_dollars'] for t in losses])) if losses else 0
    profit_factor = sum(t['pnl_dollars'] for t in wins) / (sum(abs(t['pnl_dollars']) for t in losses) + 1e-10)
    
    # Max drawdown
    peak = INITIAL_CAPITAL
    max_dd = 0
    for eq in equity_curve:
        if eq['equity'] > peak:
            peak = eq['equity']
        dd = (peak - eq['equity']) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # Per-pair stats
    pair_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})
    for t in all_trades:
        pair_stats[t['pair']]['trades'] += 1
        pair_stats[t['pair']]['pnl'] += t['pnl_dollars']
        if t['pnl_dollars'] > 0:
            pair_stats[t['pair']]['wins'] += 1
    
    # Exit reason stats
    exit_stats = defaultdict(int)
    for t in all_trades:
        exit_stats[t['reason']] += 1
    
    return {
        'total_trades': len(all_trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'max_drawdown_pct': max_dd,
        'final_capital': capital,
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
    ]
    
    print("=" * 70)
    print("COMBINED BACKTEST: COT + Order Flow + MR")
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
        
        print(f"\nPer-pair stats:")
        for pair, stats in sorted(results['pair_stats'].items()):
            wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
            print(f"  {pair}: {stats['trades']} trades, {wr:.0f}% WR, ${stats['pnl']:.2f}")
        
        print(f"\nExit reasons:")
        for reason, count in results['exit_stats'].items():
            print(f"  {reason}: {count}")
