import sys, os, pickle, random, numpy as np, pandas as pd
sys.path = ['/root/that', '/root'] + [p for p in sys.path if p not in ('/root','/root/that')]
import config as cfg
from backtest_hybrid_opt import B_TF_LADDER, precompute_strength, precompute_signals_vectorized
spec = __import__('importlib').util.spec_from_file_location('rc','/root/config.py')
rc = __import__('importlib').util.module_from_spec(spec)
sys.modules['rc'] = rc; spec.loader.exec_module(rc)
DATA_DIR = '/root/data'; ALL_PAIRS = rc.ALL_PAIRS

from backtest_portfolio import PortfolioManager, run_portfolio_backtest

def load_pp(p):
    pk = p.replace('/', '_'); f = '%s/%s.pkl' % (DATA_DIR, pk)
    if not os.path.exists(f): return None
    with open(f, 'rb') as fh: d = pickle.load(fh)
    df = d.get(p)
    if df is None: return None
    df = df.copy(); df.index = pd.to_datetime(df.index)
    if df.index.tz is not None: df.index = df.index.tz_localize(None)
    return df

pair_dfs = {p: load_pp(p) for p in ALL_PAIRS}
pair_dfs = {k: v for k, v in pair_dfs.items() if v is not None}
rng = random.Random(42)
ref = pair_dfs[max(pair_dfs, key=lambda p: len(pair_dfs[p]))]
ref_y = ref[ref.index.year == 2019]
si = rng.randint(0, len(ref_y) - 129600)
st = ref_y.index[si]; et = ref_y.index[si + 129599]
window = {}
for p, df in pair_dfs.items():
    dy = df[df.index.year == 2019]
    m = (dy.index >= st) & (dy.index <= et)
    sliced = dy.loc[m].copy()
    if not sliced.empty:
        window[p] = sliced

import backtest_hybrid_opt as bho
bho.TRADEABLE_PAIRS = list(window.keys())
all_tfs = {tf: {} for tf in B_TF_LADDER}
for p, df in window.items():
    for tf in B_TF_LADDER:
        r = pd.DataFrame()
        r['open'] = df['open'].resample(tf).first()
        r['high'] = df['high'].resample(tf).max()
        r['low'] = df['low'].resample(tf).min()
        r['close'] = df['close'].resample(tf).last()
        r.dropna(subset=['close'], inplace=True)
        if not r.empty:
            all_tfs[tf][p] = r

strength = precompute_strength(all_tfs, n_jobs=1)
valid = list(window.keys())
sig, sig_lookup = precompute_signals_vectorized(
    strength, valid, min_div=cfg.MIN_DIVERGENCE,
    top_n=cfg.STRENGTH_TOP_N, n_jobs=1,
)
atr_cache = bho.precompute_atrs(all_tfs, n_jobs=1)

# Zero costs
for k in list(cfg.SPREAD_PIPS.keys()):
    cfg.SPREAD_PIPS[k] = 0.0
cfg.DEFAULT_SPREAD_PIPS = 0.0
cfg.COMMISSION_PER_LOT = 0.0

pm = PortfolioManager(
    max_positions=10, max_daily_risk_pct=0.03,
    max_trade_risk_pct=0.003, min_trade_risk_pct=0.002,
    per_currency_exposure=2, enable_replacement=True,
)
first = next((all_tfs['5min'][p] for p in all_tfs['5min']), None)
r = run_portfolio_backtest(
    all_tfs, strength, sig_lookup, atr_cache,
    str(first.index[0].date()), str(first.index[-1].date()),
    pm, initial_balance=1000.0,
)
print('Zero costs: Trades=%d WR=%.2f%% NetPnL=$%.2f Exits=%s' % (r['total_trades'], r['win_rate'], r['net_pnl'], r['exits']))
