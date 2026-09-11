import sys, os, pickle, random, numpy as np, pandas as pd
sys.path = ['/root/nestquant','/root'] + [p for p in sys.path if p not in ('/root','/root/nestquant')]
import config as cfg
spec = __import__('importlib').util.spec_from_file_location('rc','/root/config.py')
rc = __import__('importlib').util.module_from_spec(spec)
sys.modules['rc']=rc; spec.loader.exec_module(rc)
DATA_DIR='/root/data'; ALL_PAIRS=rc.ALL_PAIRS
from backtest_hybrid_opt import B_TF_LADDER, precompute_strength, precompute_signals_vectorized, precompute_atrs
from backtest_portfolio import precompute_breakout_signals, precompute_swing_levels
import backtest_hybrid_opt as bho

def load_pp(p):
    pk=p.replace('/','_'); f='%s/%s.pkl'%(DATA_DIR,pk)
    if not os.path.exists(f):return None
    with open(f,'rb') as fh: d=pickle.load(fh)
    df=d.get(p)
    if df is None:return None
    df=df.copy(); df.index=pd.to_datetime(df.index)
    if df.index.tz is not None:df.index=df.index.tz_localize(None)
    return df

pair_dfs={p:load_pp(p) for p in ALL_PAIRS}
pair_dfs={k:v for k,v in pair_dfs.items() if v is not None}
rng=random.Random(42)
ref=pair_dfs[max(pair_dfs,key=lambda p:len(pair_dfs[p]))]
ref_y=ref[ref.index.year==2018]
si=rng.randint(0,len(ref_y)-129600)
st=ref_y.index[si]; et=ref_y.index[si+129599]
window={}
for p,df in pair_dfs.items():
    dy=df[df.index.year==2018]; m=(dy.index>=st)&(dy.index<=et); sl=dy.loc[m].copy()
    if not sl.empty: window[p]=sl

bho.TRADEABLE_PAIRS=list(window.keys())
all_tfs={tf:{} for tf in B_TF_LADDER}
for p,df in window.items():
    for tf in B_TF_LADDER:
        r=pd.DataFrame()
        r['open']=df['open'].resample(tf).first()
        r['high']=df['high'].resample(tf).max()
        r['low']=df['low'].resample(tf).min()
        r['close']=df['close'].resample(tf).last()
        r.dropna(subset=['close'],inplace=True)
        if not r.empty: all_tfs[tf][p]=r

trade_tf = '4h'
strength = precompute_strength(all_tfs, n_jobs=1)

# Build signal lookup correctly for breakout
sig_lookup = {}
sig_lookup[trade_tf] = precompute_breakout_signals(all_tfs[trade_tf], trade_tf, lookback=5)

# Pre-build pair_data as done in run_portfolio_backtest
import gc
from backtest_hybrid_opt import is_active_session, pip_size, COMMISSION_PER_LOT, MIN_LOT_SIZE, ENABLE_MACRO_FILTER, ENABLE_REGIME_FLIP, TRADEABLE_PAIRS, MAX_PER_CURRENCY_BLOCK

pair_data = {}
for tf in B_TF_LADDER:
    pair_data[tf] = {}
    for pair, df in all_tfs[tf].items():
        if df is not None and not df.empty:
            pair_data[tf][pair] = {
                "times": df.index.values,
                "close": df["close"].values,
                "high": df["high"].values,
                "low": df["low"].values,
            }

atr_cache = precompute_atrs(all_tfs, n_jobs=1)

# Build signal indices (same as in run_portfolio_backtest)
timeline = list(all_tfs['5min'].values())[0].index.values
n_bars = len(timeline)
_signal_indices = {}
for tf in B_TF_LADDER:
    sdf = strength.get(tf)
    if sdf is not None and not sdf.empty:
        stimes = sdf.index.values
        _signal_indices[tf] = np.searchsorted(stimes, timeline) - 1
    else:
        _signal_indices[tf] = np.full(n_bars, -1, dtype=int)

# Check entry for a specific bar
bar_idx = 500  # Early in timeline
trade_tf = '4h'
cur_tf = _signal_indices[trade_tf][bar_idx]
cur_5m_idx = _signal_indices['5min'][bar_idx]
print(f'Bar {bar_idx}: cur_5m_idx={cur_5m_idx}, trade_tf({trade_tf})_idx={cur_tf}')

p = 'EUR/USD'
lookup = sig_lookup[trade_tf].get(p)
print(f'{p}: sig_lookup len={len(lookup) if lookup is not None else 0}')
if lookup is not None and 0 <= cur_tf < len(lookup):
    print(f'  sig_byte={lookup[cur_tf]}')

# Check price arrays
pd5 = pair_data['5min'].get(p)
if pd5:
    ca = pd5.get('close', np.array([]))
    idx = max(0, min(cur_5m_idx, len(ca)-1))
    print(f'  5min close[{idx}] = {ca[idx]}')
    print(f'  5min close array len = {len(ca)}')

pd4 = pair_data[trade_tf].get(p)
if pd4:
    ca4 = pd4.get('close', np.array([]))
    print(f'  {trade_tf} close array len = {len(ca4)}')
    print(f'  {trade_tf} close[{cur_tf}] = {ca4[cur_tf] if 0 <= cur_tf < len(ca4) else "OOB"}')

# Now check CAD/JPY
p2 = 'CAD/JPY'
pd5_2 = pair_data['5min'].get(p2)
if pd5_2:
    ca2 = pd5_2.get('close', np.array([]))
    idx2 = max(0, min(cur_5m_idx, len(ca2)-1))
    print(f'CAD/JPY 5min close[{idx2}] = {ca2[idx2]}')
    print(f'CAD/JPY 5min close array len = {len(ca2)}')
    print(f'CAD/JPY first close = {ca2[0]}')

# Check ATR cache
atr_5m = atr_cache['5min'].get(p2)
if atr_5m is not None:
    atr_idx = max(0, min(cur_5m_idx, len(atr_5m)-1))
    print(f'CAD/JPY ATR[{atr_idx}] = {atr_5m[atr_idx]}')
else:
    print('CAD/JPY ATR NOT FOUND in atr_cache[5min]')
    print('atr_cache[5min] keys:', list(atr_cache['5min'].keys())) if '5min' in atr_cache else print('No 5min in atr_cache')
