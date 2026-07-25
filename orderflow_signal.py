"""
Order Flow Signal - Microstructure Analysis
Uses orderflowkit to compute order imbalance, VWAP deviation, and Hurst exponent
from OHLCV data. No Level 2 required.
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional

try:
    from orderflowkit import MicrostructurePipeline
    HAS_ORDERFLOWKIT = True
except ImportError:
    HAS_ORDERFLOWKIT = False


class OrderFlowSignal:
    """
    Generates signals from order flow microstructure.
    
    Uses orderflowkit to compute:
    1. Order Imbalance - buy vs sell pressure from tick rule
    2. VWAP Deviation - price vs volume-weighted average price
    3. Hurst Exponent - mean reversion vs trending detection
    4. Bulk Volume Classification - buy vs sell volume
    """
    
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
    
    def compute_signals(self, df: pd.DataFrame) -> Dict:
        """
        Compute order flow signals from OHLCV data.
        
        Args:
            df: DataFrame with columns [open, high, low, close, volume]
        
        Returns:
            dict with order flow signals
        """
        if len(df) < self.lookback:
            return self._neutral_signal()
        
        if not HAS_ORDERFLOWKIT:
            return self._fallback_signals(df)
        
        try:
            # Prepare data for orderflowkit - lowercase column names, reset index
            df_of = df[['open', 'high', 'low', 'close', 'volume']].copy()
            df_of = df_of.reset_index(drop=True)
            
            # Run pipeline
            pipeline = MicrostructurePipeline(df_of)
            pipeline.add_tick_rule()
            pipeline.add_order_imbalance(window=10)
            pipeline.add_vwap_deviation()
            pipeline.add_bvc(window=20)
            
            result = pipeline.run()
            df_result = result.metrics
            
            if len(df_result) == 0:
                return self._neutral_signal()
            
            latest = df_result.iloc[-1]
            
            # Extract signals
            order_imb = latest.get('order_imbalance_10', 0.0)
            vwap_dev = latest.get('vwap_deviation', 0.0)
            
            # Compute Hurst separately (simpler method)
            returns = df['close'].pct_change().dropna().iloc[-100:]
            hurst = self._estimate_hurst(returns)
            
            # Bulk volume classification
            buy_vol = latest.get('bvc_buy_volume', 0.0)
            sell_vol = latest.get('bvc_sell_volume', 0.0)
            if buy_vol + sell_vol > 0:
                bvc_ratio = (buy_vol - sell_vol) / (buy_vol + sell_vol)
            else:
                bvc_ratio = 0.0
            
            return {
                'order_imbalance': order_imb,
                'vwap_deviation': vwap_dev,
                'hurst': hurst,
                'bvc_ratio': bvc_ratio,
                'source': 'orderflowkit'
            }
            
        except Exception as e:
            print(f"Orderflowkit error: {e}")
            return self._fallback_signals(df)
    
    def _fallback_signals(self, df: pd.DataFrame) -> Dict:
        """Fallback to simple signals if orderflowkit fails."""
        # Simple tick rule approximation
        df['direction'] = np.where(df['close'] > df['close'].shift(1), 1, -1)
        df['tick_volume'] = df['volume'] * df['direction']
        
        # Order imbalance approximation
        order_imb = df['tick_volume'].rolling(10).sum().iloc[-1]
        order_imb_norm = order_imb / (df['volume'].rolling(10).sum().iloc[-1] + 1e-10)
        
        # VWAP deviation
        vwap = (df['close'] * df['volume']).rolling(20).sum() / df['volume'].rolling(20).sum()
        vwap_dev = ((df['close'] - vwap) / vwap).iloc[-1]
        
        # Simple Hurst approximation (R/S method)
        returns = df['close'].pct_change().dropna()
        if len(returns) > 20:
            hurst = self._estimate_hurst(returns.iloc[-100:])
        else:
            hurst = 0.5
        
        return {
            'order_imbalance': order_imb_norm,
            'vwap_deviation': vwap_dev,
            'hurst': hurst,
            'bvc_ratio': order_imb_norm,
            'source': 'fallback'
        }
    
    def _estimate_hurst(self, returns: pd.Series) -> float:
        """Estimate Hurst exponent using R/S method."""
        try:
            n = len(returns)
            if n < 20:
                return 0.5
            
            # R/S analysis
            mean = returns.mean()
            deviate = np.cumsum(returns - mean)
            
            R = np.max(deviate) - np.min(deviate)
            S = returns.std()
            
            if S == 0:
                return 0.5
            
            RS = R / S
            hurst = np.log(RS) / np.log(n)
            
            return np.clip(hurst, 0.0, 1.0)
        except:
            return 0.5
    
    def _neutral_signal(self) -> Dict:
        return {
            'order_imbalance': 0.0,
            'vwap_deviation': 0.0,
            'hurst': 0.5,
            'bvc_ratio': 0.0,
            'source': 'neutral'
        }
    
    def get_trade_signal(self, df: pd.DataFrame) -> Dict:
        """
        Generate trade signal from order flow.
        
        Returns:
            dict with:
                - direction: 'long', 'short', or 'neutral'
                - strength: 0.0 to 1.0
                - hurst: >0.5 = mean reversion, <0.5 = trending
                - entry_zone: based on VWAP deviation
        """
        signals = self.compute_signals(df)
        
        hurst = signals['hurst']
        vwap_dev = signals['vwap_deviation']
        order_imb = signals['order_imbalance']
        
        # Determine regime
        if hurst > 0.55:
            regime = 'mean_reversion'
        elif hurst < 0.45:
            regime = 'trending'
        else:
            regime = 'random'
        
        # Generate direction
        direction = 'neutral'
        strength = 0.0
        
        if regime == 'mean_reversion':
            # Mean reversion: trade against VWAP deviation
            if vwap_dev < -0.001:  # Price below VWAP
                direction = 'long'
                strength = min(abs(vwap_dev) * 500, 1.0)
            elif vwap_dev > 0.001:  # Price above VWAP
                direction = 'short'
                strength = min(abs(vwap_dev) * 500, 1.0)
            
            # Boost if order imbalance confirms
            if (direction == 'long' and order_imb > 0.1) or \
               (direction == 'short' and order_imb < -0.1):
                strength = min(strength * 1.2, 1.0)
        
        elif regime == 'trending':
            # Trending: follow order imbalance
            if order_imb > 0.2:
                direction = 'long'
                strength = min(abs(order_imb), 1.0)
            elif order_imb < -0.2:
                direction = 'short'
                strength = min(abs(order_imb), 1.0)
        
        return {
            'direction': direction,
            'strength': strength,
            'regime': regime,
            'hurst': hurst,
            'vwap_deviation': vwap_dev,
            'order_imbalance': order_imb,
            'source': signals['source']
        }


if __name__ == '__main__':
    import pickle
    import os
    
    of_signal = OrderFlowSignal()
    
    print("=" * 70)
    print("ORDER FLOW ANALYSIS")
    print("=" * 70)
    
    # Test on a few pairs
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY']
    data_dir = '/root/data'
    
    for pair in pairs:
        fpath = os.path.join(data_dir, f'{pair}_30m.pkl')
        if os.path.exists(fpath):
            df = pickle.load(open(fpath, 'rb'))
            signal = of_signal.get_trade_signal(df)
            print(f"\n{pair}:")
            print(f"  Direction: {signal['direction']}")
            print(f"  Strength: {signal['strength']:.3f}")
            print(f"  Regime: {signal['regime']}")
            print(f"  Hurst: {signal['hurst']:.3f}")
            print(f"  VWAP Dev: {signal['vwap_deviation']:.6f}")
            print(f"  Order Imbalance: {signal['order_imbalance']:.3f}")
