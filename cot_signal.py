"""
COT Data Signal - Institutional Positioning
Fetches CFTC Commitments of Traders data and generates weekly signals
based on Asset Manager positioning (smart money).
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional

# Map cTrader symbols to CFTC contract names
# Supports both formats: EURUSD and EUR/USD
SYMBOL_TO_CFTC = {
    'EURUSD': 'EURO FX',
    'EUR/USD': 'EURO FX',
    'GBPUSD': 'BRITISH POUND',
    'GBP/USD': 'BRITISH POUND',
    'USDJPY': 'JAPANESE YEN',
    'USD/JPY': 'JAPANESE YEN',
    'AUDUSD': 'AUSTRALIAN DOLLAR',
    'AUD/USD': 'AUSTRALIAN DOLLAR',
    'USDCAD': 'CANADIAN DOLLAR',
    'USD/CAD': 'CANADIAN DOLLAR',
    'USDCHF': 'SWISS FRANC',
    'USD/CHF': 'SWISS FRANC',
    'GBPJPY': None,  # Cross pair - no direct COT
    'GBP/JPY': None,
    'GBPAUD': None,  # Cross pair - no direct COT
    'GBP/AUD': None,
    'EURAUD': None,  # Cross pair
    'EUR/AUD': None,
    'EURJPY': None,  # Cross pair
    'EUR/JPY': None,
    'EURGBP': None,  # Cross pair
    'EUR/GBP': None,
    'AUDJPY': None,  # Cross pair
    'AUD/JPY': None,
    'CADJPY': None,  # Cross pair
    'CAD/JPY': None,
    'CHFJPY': None,  # Cross pair
    'CHF/JPY': None,
    'EURNZD': None,  # Cross pair
    'EUR/NZD': None,
    'GBPNZD': None,  # Cross pair
    'GBP/NZD': None,
    'AUDNZD': None,  # Cross pair
    'AUD/NZD': None,
    'NZDJPY': None,  # Cross pair
    'NZD/JPY': None,
    'USDSGD': None,  # Not in CFTC
    'USD/SGD': None,
    'USDTHB': None,  # Not in CFTC
    'USD/THB': None,
    'NZDUSD': 'NEW ZEALAND DOLLAR',
    'NZD/USD': 'NEW ZEALAND DOLLAR',
}


class COTSignal:
    """
    Generates directional bias from CFTC COT data.
    
    Signal logic:
    - Asset Manager net positioning > +10% of OI = LONG bias
    - Asset Manager net positioning < -10% of OI = SHORT bias
    - Change in positioning = momentum signal
    - Leveraged Money positioning = contrarian indicator
    """
    
    def __init__(self):
        self.data_cache = {}
        self.last_fetch = None
        
    def fetch_data(self, year: int = None) -> pd.DataFrame:
        """Fetch COT data for given year."""
        if year is None:
            year = datetime.now().year
            
        if year in self.data_cache:
            return self.data_cache[year]
        
        from cftc_cot import cot_download_year
        
        try:
            df = cot_download_year(
                year,
                cot_report_type='traders_in_financial_futures_fut',
                path='/tmp/cot_data'
            )
            self.data_cache[year] = df
            return df
        except Exception as e:
            print(f"COT fetch error for {year}: {e}")
            return pd.DataFrame()
    
    def get_signal(self, symbol: str) -> Dict:
        """
        Get COT signal for a symbol.
        
        Returns:
            dict with keys:
                - direction: 'long', 'short', or 'neutral'
                - strength: 0.0 to 1.0
                - asset_mgr_net: net positioning as % of OI
                - leverage_money_net: leveraged money net %
                - momentum: change in positioning
                - report_date: date of latest report
        """
        cftc_name = SYMBOL_TO_CFTC.get(symbol)
        if cftc_name is None:
            return {
                'direction': 'neutral',
                'strength': 0.0,
                'asset_mgr_net': 0.0,
                'leverage_money_net': 0.0,
                'momentum': 0.0,
                'report_date': None,
                'source': 'cftc',
                'error': 'no_direct_cot'
            }
        
        # Fetch current year and previous year
        current_year = datetime.now().year
        df_now = self.fetch_data(current_year)
        df_prev = self.fetch_data(current_year - 1)
        
        # Combine and filter
        df = pd.concat([df_prev, df_now], ignore_index=True)
        mask = df['Market_and_Exchange_Names'].str.contains(cftc_name, na=False)
        df_fx = df[mask].copy()
        
        if len(df_fx) == 0:
            return {
                'direction': 'neutral',
                'strength': 0.0,
                'asset_mgr_net': 0.0,
                'leverage_money_net': 0.0,
                'momentum': 0.0,
                'report_date': None,
                'source': 'cftc',
                'error': 'no_data'
            }
        
        # Sort by date
        df_fx['Report_Date'] = pd.to_datetime(df_fx['Report_Date_as_YYYY-MM-DD'])
        df_fx = df_fx.sort_values('Report_Date')
        
        latest = df_fx.iloc[-1]
        
        # Calculate metrics
        oi = latest['Open_Interest_All']
        if oi == 0:
            oi = 1
        
        # Asset Manager positioning (smart money)
        am_long = latest['Asset_Mgr_Positions_Long_All']
        am_short = latest['Asset_Mgr_Positions_Short_All']
        am_net = am_long - am_short
        am_net_pct = (am_net / oi) * 100
        
        # Leveraged Money positioning (trend followers, often wrong at extremes)
        lev_long = latest['Lev_Money_Positions_Long_All']
        lev_short = latest['Lev_Money_Positions_Short_All']
        lev_net = lev_long - lev_short
        lev_net_pct = (lev_net / oi) * 100
        
        # Momentum (change from previous week)
        if len(df_fx) >= 2:
            prev = df_fx.iloc[-2]
            prev_oi = prev['Open_Interest_All']
            if prev_oi == 0:
                prev_oi = 1
            prev_am_net = prev['Asset_Mgr_Positions_Long_All'] - prev['Asset_Mgr_Positions_Short_All']
            prev_am_net_pct = (prev_am_net / prev_oi) * 100
            momentum = am_net_pct - prev_am_net_pct
        else:
            momentum = 0.0
        
        # Determine direction and strength
        if am_net_pct > 10:
            direction = 'long'
            strength = min(abs(am_net_pct) / 30, 1.0)
        elif am_net_pct < -10:
            direction = 'short'
            strength = min(abs(am_net_pct) / 30, 1.0)
        else:
            direction = 'neutral'
            strength = 0.0
        
        # Boost strength if leveraged money is on opposite side (contrarian)
        if (direction == 'long' and lev_net_pct < -5) or \
           (direction == 'short' and lev_net_pct > 5):
            strength = min(strength * 1.3, 1.0)
        
        return {
            'direction': direction,
            'strength': strength,
            'asset_mgr_net': am_net_pct,
            'leverage_money_net': lev_net_pct,
            'momentum': momentum,
            'report_date': latest['Report_Date'].strftime('%Y-%m-%d'),
            'source': 'cftc',
            'open_interest': oi
        }


def get_cot_signal_for_pair(symbol: str, cot_instance: COTSignal = None) -> float:
    """
    Get COT signal strength for a pair.
    Returns: -1.0 (strong short) to +1.0 (strong long), 0.0 = neutral
    """
    if cot_instance is None:
        cot_instance = COTSignal()
    
    signal = cot_instance.get_signal(symbol)
    
    if signal['direction'] == 'long':
        return signal['strength']
    elif signal['direction'] == 'short':
        return -signal['strength']
    else:
        return 0.0


if __name__ == '__main__':
    cot = COTSignal()
    
    print("=" * 70)
    print("COT DATA - INSTITUTIONAL POSITIONING")
    print("=" * 70)
    
    test_pairs = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CAD', 'USD/CHF']
    
    for pair in test_pairs:
        signal = cot.get_signal(pair)
        print(f"\n{pair}:")
        print(f"  Direction: {signal['direction']}")
        print(f"  Strength: {signal['strength']:.2f}")
        print(f"  Asset Manager Net: {signal['asset_mgr_net']:.1f}% of OI")
        print(f"  Leveraged Money Net: {signal['leverage_money_net']:.1f}% of OI")
        print(f"  Momentum: {signal['momentum']:.1f}%")
        print(f"  Report Date: {signal['report_date']}")
