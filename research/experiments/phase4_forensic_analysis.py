"""MR Phase 4 Forensic Analysis — Falsification / Validation.

Phase 4A: Session labeling audit (entry vs exit session)
Phase 4B: Timestamp alignment audit
Phase 4C: Low/mid-vol × year matrix
Phase 4D: Winner fingerprint
Phase 4E: Exit mechanism audit
Phase 4F: Holding-time counterfactual
Phase 4G: Pair decomposition for problem pairs
Phase 4H: Statistical dependence (block bootstrap)
Phase 4I: Cost stress for conditional edge
"""
import pickle, json, sys, os, time, warnings, copy
import numpy as np
import pandas as pd
from collections import defaultdict
from dataclasses import dataclass, field
warnings.filterwarnings('ignore')
import position_sizing as ps

# ═══════════════════════════════════════════════════════════════
# CONSTANTS (DO NOT MODIFY)
# ═══════════════════════════════════════════════════════════════
PAIRS=['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD','GBP/AUD','EUR/AUD','NZD/JPY','EUR/CAD','GBP/CAD','AUD/CHF','NZD/CHF','CAD/CHF']
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
LEV=100; ACC=2500; RISK=0.020
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'GBP/JPY':3.0,'AUD/JPY':2.0,'CAD/JPY':2.5,'NZD/JPY':3.0,'EUR/AUD':2.0,'EUR/CAD':2.5,'GBP/AUD':3.5,'GBP/CAD':3.5,'AUD/CAD':2.0,'AUD/CHF':2.5,'NZD/CHF':3.0,'CAD/CHF':3.0}

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

def get_session(ts):
    h=ts.hour; il=7<=h<16; iny=12<=h<21
    if il and iny: return 'overlap'
    if il: return 'london_only'
    if iny: return 'ny_only'
    return 'none'

def get_entry_session(entry_ts):
    """Classify session based on ENTRY timestamp."""
    return get_session(entry_ts)

# ═══════════════════════════════════════════════════════════════
# DATA LOADING WITH TIMESTAMP ALIGNMENT
# ═══════════════════════════════════════════════════════════════

def load_pair_data_raw(start, end):
    """Load raw 30min data for each pair WITHOUT alignment. Returns dict of DataFrames."""
    raw_data = {}
    for pair in PAIRS:
        pk = pair.replace('/', '_')
        try:
            with open(f'/root/data/{pk}.pkl', 'rb') as f:
                raw = pickle.load(f)
        except FileNotFoundError:
            continue
        df = raw.get(pair)
        if df is None:
            continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index = idx
        df = df[df.index >= start]
        df = df[df.index <= end]
        if len(df) < 500:
            continue
        pip = ps.pip_size_for_pair(pair)
        pv = ps.pip_value_per_lot(pair, SNAP)
        d30 = df[['open', 'high', 'low', 'close']].resample('30min').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna(subset=['close'])
        d4h = df[['open', 'high', 'low', 'close']].resample('4h').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna(subset=['close'])
        daily = df[['open', 'high', 'low', 'close']].resample('1D').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna(subset=['close'])
        e200 = d4h['close'].ewm(span=200, adjust=False).mean()
        e50 = d4h['close'].ewm(span=50, adjust=False).mean()
        tr_s = pd.concat([
            d30['high'] - d30['low'],
            (d30['high'] - d30['close'].shift(1)).abs(),
            (d30['low'] - d30['close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_14 = tr_s.rolling(14).mean()
        atr_pct = atr_14 / d30['close'] * 100
        ret_30m = d30['close'].pct_change()
        rv_20 = ret_30m.rolling(20).std() * np.sqrt(48)
        raw_data[pair] = {
            'd30': d30, 'd4h': d4h, 'daily': daily,
            'e200': e200, 'e50': e50,
            'atr_pct': atr_pct, 'rv_20': rv_20,
            'pip': pip, 'pv': pv, 'spread': SPREAD.get(pair, 2.0),
            'df': df,
        }
    return raw_data


def load_pair_data_aligned(start, end):
    """Load pair data ALIGNED to reference pair's timestamps."""
    raw_data = load_pair_data_raw(start, end)
    if not raw_data:
        return {}
    # Choose reference pair
    ref_pair = max(raw_data.keys(), key=lambda p: len(raw_data[p]['d30']))
    ref_ts = raw_data[ref_pair]['d30'].index
    pdata = {}
    for pair, rd in raw_data.items():
        d30 = rd['d30']
        # Align to reference timestamps using merge_asof
        ref_df = pd.DataFrame({'ref_ts': ref_ts})
        pair_df = pd.DataFrame({
            'open': d30['open'], 'high': d30['high'],
            'low': d30['low'], 'close': d30['close']
        }, index=d30.index)
        pair_df.index.name = 'ts'
        pair_df = pair_df.reset_index()
        aligned = pd.merge_asof(
            ref_df, pair_df, left_on='ref_ts', right_on='ts',
            tolerance=pd.Timedelta('29min'), direction='nearest'
        )
        aligned.index = aligned['ref_ts']
        aligned = aligned.drop(columns=['ref_ts', 'ts'], errors='ignore')
        aligned = aligned.dropna(subset=['close'])
        if len(aligned) < 500:
            continue
        n = len(aligned)
        # Also align indicators
        e200_aligned = rd['e200'].reindex(aligned.index, method='ffill').values
        e50_aligned = rd['e50'].reindex(aligned.index, method='ffill').values
        atr_aligned = rd['atr_pct'].reindex(aligned.index, method='ffill').values
        rv_aligned = rd['rv_20'].reindex(aligned.index, method='ffill').values
        daily_aligned = rd['daily']
        pdata[pair] = {
            'c': aligned['close'].values,
            'h': aligned['high'].values,
            'lo': aligned['low'].values,
            'o': aligned['open'].values,
            'ts': aligned.index, 'n': n,
            'e200': e200_aligned, 'e50': e50_aligned,
            'daily': daily_aligned,
            'pip': rd['pip'], 'pv': rd['pv'], 'spread': rd['spread'],
            'atr_pct': atr_aligned, 'rv_20': rv_aligned,
            'raw_df': rd['df'],
        }
    return pdata


def load_pair_data_unaligned(start, end):
    """Load pair data WITHOUT alignment (for before/after audit)."""
    raw_data = load_pair_data_raw(start, end)
    if not raw_data:
        return {}
    ref_pair = max(raw_data.keys(), key=lambda p: len(raw_data[p]['d30']))
    ref_n = len(raw_data[ref_pair]['d30'])
    pdata = {}
    for pair, rd in raw_data.items():
        d30 = rd['d30']
        if len(d30) < 500:
            continue
        pdata[pair] = {
            'c': d30['close'].values,
            'h': d30['high'].values,
            'lo': d30['low'].values,
            'o': d30['open'].values,
            'ts': d30.index, 'n': len(d30),
            'e200': rd['e200'].reindex(d30.index, method='ffill').values,
            'e50': rd['e50'].reindex(d30.index, method='ffill').values,
            'daily': rd['daily'],
            'pip': rd['pip'], 'pv': rd['pv'], 'spread': rd['spread'],
            'atr_pct': rd['atr_pct'].reindex(d30.index, method='ffill').values,
            'rv_20': rd['rv_20'].reindex(d30.index, method='ffill').values,
            'raw_df': rd['df'],
        }
    return pdata

# ═══════════════════════════════════════════════════════════════
# TRADE DATA CLASS (WITH entry_session AND exit_session)
# ═══════════════════════════════════════════════════════════════

@dataclass
class Trade:
    pair: str; trend: int; entry: float; sl: float; tp: float
    lot: float; pip: float; pv: float; spread: float
    entry_bar: int; entry_ts: object
    exit_price: float = 0.0; exit_ts: object = None
    pnl: float = 0.0; gross_pnl: float = 0.0; cost: float = 0.0
    commission: float = 0.0; exit_reason: str = ''; is_win: bool = False
    entry_session: str = ''; exit_session: str = ''
    entry_hour: int = 0; entry_dow: int = 0
    year: int = 0; month: str = ''
    regime: dict = field(default_factory=dict)
    day_of_week: int = 0
    holding_bars: int = 0
    max_adverse_pips: float = 0.0; max_favorable_pips: float = 0.0
    # Pre-entry fingerprint fields
    atr_pct_at_entry: float = 0.0; rv_at_entry: float = 0.0
    dist_ema200: float = 0.0; dist_ema50: float = 0.0
    trend_regime: str = ''; vol_regime: str = ''

# ═══════════════════════════════════════════════════════════════
# SIMULATION ENGINE (FIXED: entry_session + timestamp alignment)
# ═══════════════════════════════════════════════════════════════

def run_sim(pdata, friction='realistic', commission_override=None, slippage_override=None,
            max_conc=10, rr=2.7, risk=RISK, session_filter=True):
    if friction == 'ideal':
        spread_m = 0; slp_side = slippage_override if slippage_override is not None else 0.5
    elif friction == 'realistic':
        spread_m = 1; slp_side = slippage_override if slippage_override is not None else 0.3
    else:
        spread_m = 2; slp_side = slippage_override if slippage_override is not None else 1.0
    commission = commission_override if commission_override is not None else 3.50
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref = pdata[ref_pair]; n_bars = ref['n']
    bal = ACC; peak = ACC; mdd = 0; open_pos = []; trades = []
    daily_sb = ACC; daily_d = None
    def _igs(ts): return True if not session_filter else igs(ts)
    for i in range(250, n_bars - 1):
        ts_now = ref['ts'][i]; today = ts_now.date()
        if daily_d != today:
            daily_d = today; daily_sb = bal
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos['pair'])
                if pd_ is None or i >= pd_['n']: continue
                ep = pd_['c'][i] - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if pos['trend'] == 1 else pd_['c'][i] + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                gross = (ep - pos['entry']) * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost; bal += pnl
                es = get_entry_session(pos['entry_ts'])
                xs = get_session(ts_now)
                trades.append(Trade(pair=pos['pair'], trend=pos['trend'], entry=pos['entry'], sl=pos['sl'], tp=pos['tp'],
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=ep, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot'] * commission, exit_reason='DL', is_win=(pnl > 0),
                    entry_session=es, exit_session=xs,
                    entry_hour=pos['entry_ts'].hour, entry_dow=pos['entry_ts'].dayofweek,
                    year=pos['entry_ts'].year, month=pos['entry_ts'].strftime('%Y-%m'),
                    day_of_week=pos['entry_ts'].dayofweek, holding_bars=i - pos['bar']))
            open_pos.clear(); continue
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos['pair'])
            if pd_ is None or i >= pd_['n']: remaining.append(pos); continue
            bar_lo = pd_['lo'][i]; bar_hi = pd_['h'][i]; bar_cl = pd_['c'][i]
            tr = pos['trend']; sl = pos['sl']; tp = pos['tp']; closed = False
            def _close(reason, exit_p):
                nonlocal closed, bal
                if tr == 1: gross = (exit_p - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot']
                else: gross = (pos['entry'] - exit_p) / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost; bal += pnl; closed = True
                es = get_entry_session(pos['entry_ts'])
                xs = get_session(ts_now)
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=exit_p, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot'] * commission, exit_reason=reason, is_win=(pnl > 0),
                    entry_session=es, exit_session=xs,
                    entry_hour=pos['entry_ts'].hour, entry_dow=pos['entry_ts'].dayofweek,
                    year=pos['entry_ts'].year, month=pos['entry_ts'].strftime('%Y-%m'),
                    day_of_week=pos['entry_ts'].dayofweek, holding_bars=i - pos['bar']))
            if not closed and tr == 1 and bar_lo <= sl: _close('SL', sl)
            elif not closed and tr == -1 and bar_hi >= sl: _close('SL', sl)
            if not closed and tr == 1 and bar_hi >= tp: _close('TP', tp)
            elif not closed and tr == -1 and bar_lo <= tp: _close('TP', tp)
            if not closed and not _igs(ref['ts'][i]):
                ep = bar_cl - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if tr == 1 else bar_cl + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                _close('SC', ep)
            if not closed and (i - pos['bar']) >= 50:
                ep = bar_cl - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if tr == 1 else bar_cl + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                _close('MH', ep)
            if not closed: remaining.append(pos)
        open_pos = remaining
        bal = max(bal, 1.0)
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd
        if not _igs(ts_now) or len(open_pos) >= max_conc: continue
        for pair in PAIRS:
            if len(open_pos) >= max_conc: break
            if any(p['pair'] == pair for p in open_pos): continue
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_['n']: continue
            c_val = pd_['c'][i]; ev = pd_['e200'][i]; e5 = pd_['e50'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            tr = 1 if c_val > ev else -1
            if tr == 1 and c_val < e5 * 0.998: continue
            if tr == -1 and c_val > e5 * 1.002: continue
            if tr == 1:
                if not (c_val < ev * 1.005 and c_val > ev * 0.995): continue
                if max(pd_['h'][max(0, i - 20):i]) <= c_val * 1.002: continue
            else:
                if not (c_val > ev * 0.995 and c_val < ev * 1.005): continue
                if min(pd_['lo'][max(0, i - 20):i]) >= c_val * 0.998: continue
            d_ts = pd_['daily'].index.asof(ts_now)
            if d_ts not in pd_['daily'].index: continue
            dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
            if tr == 1 and not dg: continue
            if tr == -1 and dg: continue
            pip = pd_['pip']; sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
            sl_dist = abs(c_val - sl)
            if sl_dist < 2 * pip: continue
            tp = c_val + sl_dist * rr if tr == 1 else c_val - sl_dist * rr
            ef = c_val + (pd_['spread'] * 0.5 * spread_m + slp_side) * pip if tr == 1 else c_val - (pd_['spread'] * 0.5 * spread_m + slp_side) * pip
            # Pre-entry fingerprint
            atr_val = pd_['atr_pct'][i] if not np.isnan(pd_['atr_pct'][i]) else 0
            rv_val = pd_['rv_20'][i] if not np.isnan(pd_['rv_20'][i]) else 0
            dist200 = (c_val - ev) / ev * 100 if ev != 0 else 0
            dist50 = (c_val - e5) / e5 * 100 if e5 != 0 else 0
            vr = classify_vol_regime(pd_['atr_pct'], i)
            tr_r = classify_trend_regime(c_val, ev)
            sz = ps.compute_position_size(pair=pair, side='BUY' if tr == 1 else 'SELL',
                entry_price=ef, sl_price=sl, account_balance_usd=bal, risk_pct=risk,
                leverage=LEV, margin_safety=0.5, snap=SNAP, lot_step=0.01, min_lot=0.01,
                max_lot=10.0, existing_margin_used=0.0)
            if not sz.ok: continue
            open_pos.append({
                'pair': pair, 'trend': tr, 'entry': ef, 'sl': sl, 'tp': tp,
                'lot': sz.lot_size, 'bar': i, 'pip': pip, 'pv': pd_['pv'],
                'spread': pd_['spread'], 'entry_ts': ts_now,
                'atr_pct': atr_val, 'rv': rv_val,
                'dist_ema200': dist200, 'dist_ema50': dist50,
                'vol_regime': vr, 'trend_regime': tr_r,
            })
    return trades, mdd, bal


def classify_vol_regime(atr_pct_arr, bar_idx):
    if bar_idx >= len(atr_pct_arr): return 'unknown'
    atr = atr_pct_arr[bar_idx]
    if np.isnan(atr): return 'unknown'
    valid = atr_pct_arr[~np.isnan(atr_pct_arr)]
    if len(valid) == 0: return 'unknown'
    p25 = np.percentile(valid, 25); p75 = np.percentile(valid, 75); p95 = np.percentile(valid, 95)
    if atr <= p25: return 'low_vol'
    elif atr >= p95: return 'extreme_vol'
    elif atr >= p75: return 'high_vol'
    else: return 'mid_vol'


def classify_trend_regime(c, e200):
    if np.isnan(e200) or e200 == 0: return 'unknown'
    d = abs(c - e200) / e200 * 100
    if d < 0.1: return 'near_ema200'
    elif d < 0.3: return 'weak_trend'
    else: return 'strong_trend'


def add_regimes_and_mfe_mae(trades, pdata):
    for t in trades:
        pd_ = pdata.get(t.pair)
        if pd_ is None:
            t.regime = {'vol_regime': 'unknown', 'trend_regime': 'unknown'}
            t.vol_regime = 'unknown'; t.trend_regime = 'unknown'
            continue
        bi = np.searchsorted(pd_['ts'], t.entry_ts)
        if bi >= len(pd_['ts']): bi = len(pd_['ts']) - 1
        t.vol_regime = classify_vol_regime(pd_['atr_pct'], bi)
        t.trend_regime = classify_trend_regime(pd_['c'][bi], pd_['e200'][bi])
        t.regime = {'vol_regime': t.vol_regime, 'trend_regime': t.trend_regime}
        raw = pd_.get('raw_df')
        if raw is not None and t.exit_ts is not None:
            mask = (raw.index >= t.entry_ts) & (raw.index <= t.exit_ts)
            seg = raw[mask]
            if len(seg) >= 2:
                if t.trend == 1:
                    t.max_favorable_pips = (seg['high'].max() - t.entry) / t.pip
                    t.max_adverse_pips = (t.entry - seg['low'].min()) / t.pip
                else:
                    t.max_favorable_pips = (t.entry - seg['low'].min()) / t.pip
                    t.max_adverse_pips = (seg['high'].max() - t.entry) / t.pip
    return trades

# ═══════════════════════════════════════════════════════════════
# METRICS COMPUTATION
# ═══════════════════════════════════════════════════════════════

def m():
    def _m(trades, lbl=''):
        if not trades: return None
        pnls = np.array([t.pnl for t in trades])
        w = int(np.sum(pnls > 0)); l_ = int(np.sum(pnls <= 0))
        gw = float(np.sum(pnls[pnls > 0])); gl = float(np.abs(np.sum(pnls[pnls <= 0])))
        md = defaultdict(lambda: {'pnl': 0.0, 'trades': 0, 'wins': 0})
        for t in trades:
            md[t.month]['pnl'] += t.pnl; md[t.month]['trades'] += 1
            if t.pnl > 0: md[t.month]['wins'] += 1
        mk = sorted(md.keys()); mrets = []; prev = ACC; pk = ACC; neg = 0
        for k in mk:
            r = md[k]['pnl'] / prev * 100 if prev > 0 else 0; prev += md[k]['pnl']
            if prev > pk: pk = prev
            mrets.append(r)
            if r < 0: neg += 1
        mrets = np.array(mrets) if mrets else np.array([0])
        eq = [ACC]
        for t in trades: eq.append(eq[-1] + t.pnl)
        ea = np.array(eq); rpk = np.maximum.accumulate(ea)
        dd = np.where(rpk > 0, (rpk - ea) / rpk, 0)
        hold = np.array([t.holding_bars for t in trades]) if trades else np.array([0])
        ex = defaultdict(int)
        for t in trades: ex[t.exit_reason] += 1
        r = {'label': lbl, 'trades': len(trades), 'wins': w, 'losses': l_,
             'win_rate': round(w / (w + l_) * 100, 2) if (w + l_) > 0 else 0,
             'profit_factor': round(gw / gl, 2) if gl > 0 else 99,
             'net_pnl': round(float(np.sum(pnls)), 2),
             'avg_pnl': round(float(np.mean(pnls)), 2),
             'expectancy': round(float(np.mean(pnls)), 2),
             'median_pnl': round(float(np.median(pnls)), 2),
             'std_pnl': round(float(np.std(pnls, ddof=1)), 2) if len(pnls) > 1 else 0,
             'mdd_pct': round(float(np.max(dd)) * 100, 2),
             'n_negative_months': neg, 'n_months': len(mrets),
             'avg_holding_bars': round(float(np.mean(hold)), 1),
             'exits': {k: v for k, v in ex.items()},
             'sc_pct': round(ex.get('SC', 0) / len(trades) * 100, 1) if trades else 0,
             'sl_pct': round(ex.get('SL', 0) / len(trades) * 100, 1) if trades else 0,
             'tp_pct': round(ex.get('TP', 0) / len(trades) * 100, 1) if trades else 0}
        # MAE/MFE
        mae = np.array([t.max_adverse_pips for t in trades if t.max_adverse_pips > 0])
        mfe = np.array([t.max_favorable_pips for t in trades if t.max_favorable_pips > 0])
        if len(mae) > 0:
            r['mae_mean'] = round(float(np.mean(mae)), 2)
            r['mae_median'] = round(float(np.median(mae)), 2)
            r['mae_p95'] = round(float(np.percentile(mae, 95)), 2)
        if len(mfe) > 0:
            r['mfe_mean'] = round(float(np.mean(mfe)), 2)
            r['mfe_median'] = round(float(np.median(mfe)), 2)
            r['mfe_p95'] = round(float(np.percentile(mfe, 95)), 2)
        return r
    return _m

_compute = m()

# ═══════════════════════════════════════════════════════════════
# PHASE 4A: SESSION LABELING AUDIT
# ═══════════════════════════════════════════════════════════════

def phase4a_session_audit(trades):
    """Compare entry_session vs exit_session analysis."""
    # By entry session
    by_es = defaultdict(list)
    for t in trades: by_es[t.entry_session].append(t)
    sess_entry = {k: _compute(v, f'entry:{k}') for k, v in by_es.items()}
    # By exit session
    by_xs = defaultdict(list)
    for t in trades: by_xs[t.exit_session].append(t)
    sess_exit = {k: _compute(v, f'exit:{k}') for k, v in by_xs.items()}
    # Entry session × year
    es_yr = defaultdict(lambda: defaultdict(list))
    for t in trades: es_yr[t.entry_session][t.year].append(t)
    es_yearly = {}
    for sess in sorted(es_yr.keys()):
        es_yearly[sess] = {yr: _compute(ts, f'{sess}_{yr}') for yr, ts in sorted(es_yr[sess].items())}
    # Entry session × vol regime
    es_vol = defaultdict(lambda: defaultdict(list))
    for t in trades:
        vr = t.vol_regime or (t.regime or {}).get('vol_regime', 'unknown')
        es_vol[t.entry_session][vr].append(t)
    es_vol_matrix = {}
    for sess in sorted(es_vol.keys()):
        es_vol_matrix[sess] = {vr: _compute(ts, f'{sess}|{vr}') for vr, ts in sorted(es_vol[sess].items())}
    # IS vs OOS by entry session
    is_t = [t for t in trades if t.year <= 2022]
    oos_t = [t for t in trades if t.year >= 2023]
    es_is = {}; es_oos = {}
    for sess in set(t.entry_session for t in trades):
        is_st = [t for t in is_t if t.entry_session == sess]
        oos_st = [t for t in oos_t if t.entry_session == sess]
        es_is[sess] = _compute(is_st, f'is_entry:{sess}')
        es_oos[sess] = _compute(oos_st, f'oos_entry:{sess}')
    # Mismatch analysis
    mismatch = defaultdict(int)
    for t in trades:
        if t.entry_session != t.exit_session:
            mismatch[f'{t.entry_session}->{t.exit_session}'] += 1
    return {
        'by_entry_session': sess_entry,
        'by_exit_session': sess_exit,
        'entry_session_x_year': es_yearly,
        'entry_session_x_vol': es_vol_matrix,
        'is_by_entry_session': es_is,
        'oos_by_entry_session': es_oos,
        'session_mismatch': dict(mismatch),
        'total_mismatches': sum(mismatch.values()),
        'mismatch_pct': round(sum(mismatch.values()) / len(trades) * 100, 1) if trades else 0,
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 4B: TIMESTAMP ALIGNMENT AUDIT
# ═══════════════════════════════════════════════════════════════

def phase4b_alignment_audit(pdata_aligned, pdata_unaligned):
    """Compare aligned vs unaligned simulation results."""
    ts_a, mdd_a, bal_a = run_sim(pdata_aligned, friction='realistic')
    ts_u, mdd_u, bal_u = run_sim(pdata_unaligned, friction='realistic')
    m_a = _compute(ts_a, 'aligned')
    m_u = _compute(ts_u, 'unaligned')
    # Count timestamp mismatches
    ref_pair = max(pdata_unaligned.keys(), key=lambda p: pdata_unaligned[p]['n'])
    ref_ts = pdata_unaligned[ref_pair]['ts']
    mismatch_count = 0
    total_checks = 0
    for pair in pdata_unaligned:
        if pair == ref_pair: continue
        pd_u = pdata_unaligned[pair]
        n_check = min(len(ref_ts), pd_u['n'])
        for i in range(250, n_check):
            total_checks += 1
            if pd_u['ts'][i] != ref_ts[i]:
                mismatch_count += 1
    return {
        'aligned': m_a, 'unaligned': m_u,
        'diff': {
            'trades': (m_a['trades'] if m_a else 0) - (m_u['trades'] if m_u else 0),
            'pf': round((m_a['profit_factor'] if m_a else 0) - (m_u['profit_factor'] if m_u else 0), 2),
            'wr': round((m_a['win_rate'] if m_a else 0) - (m_u['win_rate'] if m_u else 0), 2),
            'pnl': round((m_a['net_pnl'] if m_a else 0) - (m_u['net_pnl'] if m_u else 0), 2),
        },
        'timestamp_mismatches': mismatch_count,
        'total_checks': total_checks,
        'mismatch_pct': round(mismatch_count / total_checks * 100, 2) if total_checks > 0 else 0,
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 4C: LOW/MID-VOL × YEAR MATRIX
# ═══════════════════════════════════════════════════════════════

def phase4c_vol_year_matrix(trades):
    """Explicit regime × year matrix for PF, WR, expectancy, trade count."""
    vol_yr = defaultdict(lambda: defaultdict(list))
    for t in trades:
        vr = t.vol_regime or (t.regime or {}).get('vol_regime', 'unknown')
        vol_yr[vr][t.year].append(t)
    matrix = {}
    for vr in sorted(vol_yr.keys()):
        matrix[vr] = {}
        for yr in sorted(vol_yr[vr].keys()):
            r = _compute(vol_yr[vr][yr], f'{vr}_{yr}')
            matrix[vr][yr] = {
                'pf': r['profit_factor'] if r else None,
                'wr': r['win_rate'] if r else None,
                'expectancy': r['expectancy'] if r else None,
                'trades': r['trades'] if r else 0,
                'pnl': r['net_pnl'] if r else 0,
            } if r else {'pf': None, 'wr': None, 'expectancy': None, 'trades': 0, 'pnl': 0}
    return matrix

# ═══════════════════════════════════════════════════════════════
# PHASE 4D: WINNER FINGERPRINT
# ═══════════════════════════════════════════════════════════════

def phase4d_winner_fingerprint(trades):
    """Entry-time characteristics of top trades vs rest."""
    pnls = np.array([t.pnl for t in trades])
    n = len(pnls)
    thresholds = {
        'top_1pct': int(n * 0.01),
        'top_5pct': int(n * 0.05),
        'top_10pct': int(n * 0.10),
        'middle_80pct': (int(n * 0.10), int(n * 0.90)),
        'bottom_10pct': int(n * 0.10),
    }
    sorted_idx = np.argsort(pnls)[::-1]
    groups = {}
    # Top 1%, 5%, 10%
    for label, k in [('top_1pct', thresholds['top_1pct']),
                      ('top_5pct', thresholds['top_5pct']),
                      ('top_10pct', thresholds['top_10pct'])]:
        idx = sorted_idx[:k]
        group_trades = [trades[i] for i in idx]
        groups[label] = _fingerprint(group_trades, label)
    # Middle 80%
    mid_start = thresholds['middle_80pct'][0]
    mid_end = thresholds['middle_80pct'][1]
    mid_idx = sorted_idx[mid_start:mid_end]
    groups['middle_80pct'] = _fingerprint([trades[i] for i in mid_idx], 'middle_80pct')
    # Bottom 10%
    bot_k = thresholds['bottom_10pct']
    bot_idx = sorted_idx[-bot_k:]
    groups['bottom_10pct'] = _fingerprint([trades[i] for i in bot_idx], 'bottom_10pct')
    return groups


def _fingerprint(trades, label):
    if not trades: return None
    def _safe(arr):
        if len(arr) == 0: return {'mean': 0, 'median': 0, 'std': 0, 'p25': 0, 'p75': 0}
        a = np.array(arr)
        return {
            'mean': round(float(np.mean(a)), 4),
            'median': round(float(np.median(a)), 4),
            'std': round(float(np.std(a, ddof=1)), 4) if len(a) > 1 else 0,
            'p25': round(float(np.percentile(a, 25)), 4),
            'p75': round(float(np.percentile(a, 75)), 4),
        }
    atr_vals = [t.atr_pct_at_entry for t in trades if t.atr_pct_at_entry > 0]
    rv_vals = [t.rv_at_entry for t in trades if t.rv_at_entry > 0]
    dist200 = [t.dist_ema200 for t in trades]
    dist50 = [t.dist_ema50 for t in trades]
    hours = [t.entry_hour for t in trades]
    dows = [t.entry_dow for t in trades]
    pairs = defaultdict(int)
    for t in trades: pairs[t.pair] += 1
    sessions = defaultdict(int)
    for t in trades: sessions[t.entry_session] += 1
    # Regime distribution
    vol_dist = defaultdict(int)
    for t in trades:
        vr = t.vol_regime or (t.regime or {}).get('vol_regime', 'unknown')
        vol_dist[vr] += 1
    trend_dist = defaultdict(int)
    for t in trades:
        tr = t.trend_regime or (t.regime or {}).get('trend_regime', 'unknown')
        trend_dist[tr] += 1
    return {
        'n': len(trades),
        'atr_pct': _safe(atr_vals),
        'rv_20': _safe(rv_vals),
        'dist_ema200': _safe(dist200),
        'dist_ema50': _safe(dist50),
        'entry_hour': _safe(hours),
        'entry_dow': _safe(dows),
        'top_pairs': dict(sorted(pairs.items(), key=lambda x: -x[1])[:5]),
        'session_dist': dict(sessions),
        'vol_regime_dist': dict(vol_dist),
        'trend_regime_dist': dict(trend_dist),
        'avg_pnl': round(float(np.mean([t.pnl for t in trades])), 2),
        'avg_holding': round(float(np.mean([t.holding_bars for t in trades])), 1),
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 4E: EXIT MECHANISM AUDIT
# ═══════════════════════════════════════════════════════════════

def phase4e_exit_audit(trades):
    """Exit reason analysis with MFE/MAE."""
    # Exit reason by year
    ex_yr = defaultdict(lambda: defaultdict(int))
    for t in trades: ex_yr[t.year][t.exit_reason] += 1
    # Exit reason by vol regime
    ex_vol = defaultdict(lambda: defaultdict(int))
    for t in trades:
        vr = t.vol_regime or (t.regime or {}).get('vol_regime', 'unknown')
        ex_vol[vr][t.exit_reason] += 1
    # MFE/MAE by exit reason
    mfe_by_reason = defaultdict(list)
    mae_by_reason = defaultdict(list)
    for t in trades:
        if t.max_favorable_pips > 0:
            mfe_by_reason[t.exit_reason].append(t.max_favorable_pips)
        if t.max_adverse_pips > 0:
            mae_by_reason[t.exit_reason].append(t.max_adverse_pips)
    mfe_stats = {}
    for reason, vals in mfe_by_reason.items():
        a = np.array(vals)
        mfe_stats[reason] = {
            'mean': round(float(np.mean(a)), 2),
            'median': round(float(np.median(a)), 2),
            'p25': round(float(np.percentile(a, 25)), 2),
            'p75': round(float(np.percentile(a, 75)), 2),
            'p95': round(float(np.percentile(a, 95)), 2),
            'n': len(a),
        }
    mae_stats = {}
    for reason, vals in mae_by_reason.items():
        a = np.array(vals)
        mae_stats[reason] = {
            'mean': round(float(np.mean(a)), 2),
            'median': round(float(np.median(a)), 2),
            'p25': round(float(np.percentile(a, 25)), 2),
            'p75': round(float(np.percentile(a, 75)), 2),
            'p95': round(float(np.percentile(a, 95)), 2),
            'n': len(a),
        }
    # MFE of winning vs losing trades
    win_mfe = [t.max_favorable_pips for t in trades if t.is_win and t.max_favorable_pips > 0]
    loss_mfe = [t.max_favorable_pips for t in trades if not t.is_win and t.max_favorable_pips > 0]
    win_mfe_s = _safe_list(win_mfe)
    loss_mfe_s = _safe_list(loss_mfe)
    # R-multiple analysis: percentage reaching +0.5R, +1R, +1.5R, +2R, +2.7R
    r_multiples = {}
    for t in trades:
        if t.max_favorable_pips > 0 and t.max_adverse_pips > 0:
            rr_achieved = t.max_favorable_pips / t.max_adverse_pips if t.max_adverse_pips > 0 else 0
            # This is MFE/MAE ratio, not true R-multiple
    # Use absolute MFE relative to SL distance
    for threshold_name, threshold in [('0.5R', 0.5), ('1R', 1.0), ('1.5R', 1.5), ('2R', 2.0), ('2.7R', 2.7)]:
        count = 0
        for t in trades:
            if t.max_favorable_pips <= 0: continue
            sl_dist = abs(t.entry - t.sl) / t.pip if t.pip > 0 else 0
            if sl_dist > 0 and t.max_favorable_pips >= threshold * sl_dist:
                count += 1
        r_multiples[threshold_name] = {
            'count': count,
            'pct': round(count / len(trades) * 100, 1) if trades else 0,
        }
    return {
        'exit_reason_by_year': {yr: dict(v) for yr, v in sorted(ex_yr.items())},
        'exit_reason_by_vol': {vr: dict(v) for vr, v in sorted(ex_vol.items())},
        'mfe_by_reason': mfe_stats,
        'mae_by_reason': mae_stats,
        'mfe_winning': win_mfe_s,
        'mfe_losing': loss_mfe_s,
        'r_multiples': r_multiples,
    }


def _safe_list(arr):
    if not arr: return {'mean': 0, 'median': 0, 'std': 0, 'p25': 0, 'p75': 0, 'p95': 0}
    a = np.array(arr)
    return {
        'mean': round(float(np.mean(a)), 2),
        'median': round(float(np.median(a)), 2),
        'std': round(float(np.std(a, ddof=1)), 2) if len(a) > 1 else 0,
        'p25': round(float(np.percentile(a, 25)), 2),
        'p75': round(float(np.percentile(a, 75)), 2),
        'p95': round(float(np.percentile(a, 95)), 2),
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 4F: HOLDING-TIME COUNTERFACTUAL
# ═══════════════════════════════════════════════════════════════

def phase4f_holding_counterfactual(pdata):
    """Run sim with fixed max holding periods."""
    max_holds = [10, 15, 20, 25, 30, 40, 50]
    results = {}
    for mh in max_holds:
        ts, mdd, bal = run_sim_holding(pdata, max_holding=mh)
        if ts:
            r = _compute(ts, f'hold_{mh}')
            if r:
                # Yearly breakdown
                by_yr = defaultdict(list)
                for t in ts: by_yr[t.year].append(t)
                yr_data = {yr: _compute(yrs, f'{mh}_{yr}') for yr, yrs in sorted(by_yr.items())}
                r['yearly'] = yr_data
                results[mh] = r
    # Also run baseline (no max hold)
    ts_base, mdd_base, bal_base = run_sim(pdata, friction='realistic')
    r_base = _compute(ts_base, 'baseline')
    if r_base:
        by_yr = defaultdict(list)
        for t in ts_base: by_yr[t.year].append(t)
        r_base['yearly'] = {yr: _compute(yrs, f'base_{yr}') for yr, yrs in sorted(by_yr.items())}
    results['baseline'] = r_base
    return results


def run_sim_holding(pdata, max_holding=50, friction='realistic', rr=2.7, risk=RISK, session_filter=True):
    """Run sim with a fixed max holding period override."""
    spread_m = 1; slp_side = 0.3; commission = 3.50
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref = pdata[ref_pair]; n_bars = ref['n']
    bal = ACC; peak = ACC; mdd = 0; open_pos = []; trades = []
    daily_sb = ACC; daily_d = None
    def _igs(ts): return True if not session_filter else igs(ts)
    for i in range(250, n_bars - 1):
        ts_now = ref['ts'][i]; today = ts_now.date()
        if daily_d != today:
            daily_d = today; daily_sb = bal
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos['pair'])
                if pd_ is None or i >= pd_['n']: continue
                ep = pd_['c'][i] - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if pos['trend'] == 1 else pd_['c'][i] + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                gross = (ep - pos['entry']) * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost; bal += pnl
                es = get_entry_session(pos['entry_ts']); xs = get_session(ts_now)
                trades.append(Trade(pair=pos['pair'], trend=pos['trend'], entry=pos['entry'], sl=pos['sl'], tp=pos['tp'],
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=ep, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot'] * commission, exit_reason='DL', is_win=(pnl > 0),
                    entry_session=es, exit_session=xs,
                    entry_hour=pos['entry_ts'].hour, entry_dow=pos['entry_ts'].dayofweek,
                    year=pos['entry_ts'].year, month=pos['entry_ts'].strftime('%Y-%m'),
                    day_of_week=pos['entry_ts'].dayofweek, holding_bars=i - pos['bar']))
            open_pos.clear(); continue
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos['pair'])
            if pd_ is None or i >= pd_['n']: remaining.append(pos); continue
            bar_lo = pd_['lo'][i]; bar_hi = pd_['h'][i]; bar_cl = pd_['c'][i]
            tr = pos['trend']; sl = pos['sl']; tp = pos['tp']; closed = False
            def _close(reason, exit_p):
                nonlocal closed, bal
                if tr == 1: gross = (exit_p - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot']
                else: gross = (pos['entry'] - exit_p) / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost; bal += pnl; closed = True
                es = get_entry_session(pos['entry_ts']); xs = get_session(ts_now)
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=exit_p, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot'] * commission, exit_reason=reason, is_win=(pnl > 0),
                    entry_session=es, exit_session=xs,
                    entry_hour=pos['entry_ts'].hour, entry_dow=pos['entry_ts'].dayofweek,
                    year=pos['entry_ts'].year, month=pos['entry_ts'].strftime('%Y-%m'),
                    day_of_week=pos['entry_ts'].dayofweek, holding_bars=i - pos['bar']))
            if not closed and tr == 1 and bar_lo <= sl: _close('SL', sl)
            elif not closed and tr == -1 and bar_hi >= sl: _close('SL', sl)
            if not closed and tr == 1 and bar_hi >= tp: _close('TP', tp)
            elif not closed and tr == -1 and bar_lo <= tp: _close('TP', tp)
            if not closed and not _igs(ref['ts'][i]):
                ep = bar_cl - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if tr == 1 else bar_cl + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                _close('SC', ep)
            if not closed and (i - pos['bar']) >= max_holding:
                ep = bar_cl - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if tr == 1 else bar_cl + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                _close('MH', ep)
            if not closed: remaining.append(pos)
        open_pos = remaining
        bal = max(bal, 1.0)
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd
        if not _igs(ts_now) or len(open_pos) >= 10: continue
        for pair in PAIRS:
            if len(open_pos) >= 10: break
            if any(p['pair'] == pair for p in open_pos): continue
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_['n']: continue
            c_val = pd_['c'][i]; ev = pd_['e200'][i]; e5 = pd_['e50'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            tr = 1 if c_val > ev else -1
            if tr == 1 and c_val < e5 * 0.998: continue
            if tr == -1 and c_val > e5 * 1.002: continue
            if tr == 1:
                if not (c_val < ev * 1.005 and c_val > ev * 0.995): continue
                if max(pd_['h'][max(0, i - 20):i]) <= c_val * 1.002: continue
            else:
                if not (c_val > ev * 0.995 and c_val < ev * 1.005): continue
                if min(pd_['lo'][max(0, i - 20):i]) >= c_val * 0.998: continue
            d_ts = pd_['daily'].index.asof(ts_now)
            if d_ts not in pd_['daily'].index: continue
            dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
            if tr == 1 and not dg: continue
            if tr == -1 and dg: continue
            pip = pd_['pip']; sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
            sl_dist = abs(c_val - sl)
            if sl_dist < 2 * pip: continue
            tp = c_val + sl_dist * rr if tr == 1 else c_val - sl_dist * rr
            ef = c_val + (pd_['spread'] * 0.5 * spread_m + slp_side) * pip if tr == 1 else c_val - (pd_['spread'] * 0.5 * spread_m + slp_side) * pip
            sz = ps.compute_position_size(pair=pair, side='BUY' if tr == 1 else 'SELL',
                entry_price=ef, sl_price=sl, account_balance_usd=bal, risk_pct=risk,
                leverage=LEV, margin_safety=0.5, snap=SNAP, lot_step=0.01, min_lot=0.01,
                max_lot=10.0, existing_margin_used=0.0)
            if not sz.ok: continue
            open_pos.append({
                'pair': pair, 'trend': tr, 'entry': ef, 'sl': sl, 'tp': tp,
                'lot': sz.lot_size, 'bar': i, 'pip': pip, 'pv': pd_['pv'],
                'spread': pd_['spread'], 'entry_ts': ts_now,
            })
    return trades, mdd, bal

# ═══════════════════════════════════════════════════════════════
# PHASE 4G: PAIR DECOMPOSITION
# ═══════════════════════════════════════════════════════════════

def phase4g_pair_decomposition(trades):
    """Chronological pair-level results for problem pairs vs rest."""
    problem_pairs = ['GBP/AUD', 'GBP/CAD', 'NZD/JPY', 'CAD/CHF', 'EUR/CHF', 'NZD/CHF', 'AUD/CHF']
    by_pair = defaultdict(lambda: defaultdict(list))
    for t in trades: by_pair[t.pair][t.year].append(t)
    results = {}
    for pair in sorted(by_pair.keys()):
        is_problem = pair in problem_pairs
        pair_yearly = {}
        for yr in sorted(by_pair[pair].keys()):
            r = _compute(by_pair[pair][yr], f'{pair}_{yr}')
            pair_yearly[yr] = {
                'pf': r['profit_factor'] if r else None,
                'wr': r['win_rate'] if r else None,
                'expectancy': r['expectancy'] if r else None,
                'trades': r['trades'] if r else 0,
                'pnl': r['net_pnl'] if r else 0,
            } if r else None
        full = _compute(sum((by_pair[pair][y] for y in by_pair[pair]), []), pair)
        results[pair] = {
            'is_problem': is_problem,
            'full_period': {
                'pf': full['profit_factor'] if full else None,
                'wr': full['win_rate'] if full else None,
                'expectancy': full['expectancy'] if full else None,
                'trades': full['trades'] if full else 0,
                'pnl': full['net_pnl'] if full else 0,
            } if full else None,
            'yearly': pair_yearly,
        }
    # Summary: problem vs non-problem
    problem_trades = [t for t in trades if t.pair in problem_pairs]
    non_problem_trades = [t for t in trades if t.pair not in problem_pairs]
    results['_summary'] = {
        'problem_pairs': _compute(problem_trades, 'problem_pairs'),
        'non_problem_pairs': _compute(non_problem_trades, 'non_problem_pairs'),
    }
    return results

# ═══════════════════════════════════════════════════════════════
# PHASE 4H: STATISTICAL DEPENDENCE (BLOCK BOOTSTRAP)
# ═══════════════════════════════════════════════════════════════

def phase4h_statistical_dependence(trades):
    """Block bootstrap for CIs accounting for temporal correlation."""
    pnls = np.array([t.pnl for t in trades])
    n = len(pnls)
    n_boot = 5000
    # Assign each trade to a date block
    dates = np.array([t.entry_ts.date() if hasattr(t.entry_ts, 'date') else t.entry_ts for t in trades])
    unique_dates = np.sort(np.unique(dates))
    date_to_idx = {d: i for i, d in enumerate(unique_dates)}
    date_blocks = np.array([date_to_idx[d] for d in dates])
    # Daily block bootstrap
    daily_wr = []; daily_mt = []; daily_pf = []
    for _ in range(n_boot):
        n_blocks = int(np.ceil(n / 10))  # ~10 trades per day
        block_starts = np.random.choice(len(unique_dates), size=n_blocks, replace=True)
        sampled_pnls = []
        for bs in block_starts:
            mask = date_blocks == bs
            block_pnls = pnls[mask]
            sampled_pnls.extend(np.random.choice(block_pnls, size=len(block_pnls), replace=True))
        sampled_pnls = np.array(sampled_pnls[:n])
        daily_wr.append(float(np.sum(sampled_pnls > 0) / len(sampled_pnls) * 100))
        daily_mt.append(float(np.mean(sampled_pnls)))
        gw = float(np.sum(sampled_pnls[sampled_pnls > 0])) if np.any(sampled_pnls > 0) else 0
        gl = float(np.abs(np.sum(sampled_pnls[sampled_pnls <= 0]))) if np.any(sampled_pnls <= 0) else 1
        daily_pf.append(gw / gl if gl > 0 else 99)
    # Weekly block bootstrap
    weeks = np.array([t.entry_ts.isocalendar()[1] if hasattr(t.entry_ts, 'isocalendar') else 0 for t in trades])
    unique_weeks = np.sort(np.unique(weeks))
    week_to_idx = {w: i for i, w in enumerate(unique_weeks)}
    week_blocks = np.array([week_to_idx[w] for w in weeks])
    weekly_wr = []; weekly_mt = []; weekly_pf = []
    for _ in range(n_boot):
        n_blocks = int(np.ceil(n / 50))  # ~50 trades per week
        block_starts = np.random.choice(len(unique_weeks), size=n_blocks, replace=True)
        sampled_pnls = []
        for bs in block_starts:
            mask = week_blocks == bs
            block_pnls = pnls[mask]
            sampled_pnls.extend(np.random.choice(block_pnls, size=len(block_pnls), replace=True))
        sampled_pnls = np.array(sampled_pnls[:n])
        weekly_wr.append(float(np.sum(sampled_pnls > 0) / len(sampled_pnls) * 100))
        weekly_mt.append(float(np.mean(sampled_pnls)))
        gw = float(np.sum(sampled_pnls[sampled_pnls > 0])) if np.any(sampled_pnls > 0) else 0
        gl = float(np.abs(np.sum(sampled_pnls[sampled_pnls <= 0]))) if np.any(sampled_pnls <= 0) else 1
        weekly_pf.append(gw / gl if gl > 0 else 99)
    # Independent bootstrap (for comparison)
    ind_wr = []; ind_mt = []; ind_pf = []
    for _ in range(n_boot):
        s = np.random.choice(pnls, size=n, replace=True)
        ind_wr.append(float(np.sum(s > 0) / n * 100))
        ind_mt.append(float(np.mean(s)))
        gw = float(np.sum(s[s > 0])) if np.any(s > 0) else 0
        gl = float(np.abs(np.sum(s[s <= 0]))) if np.any(s <= 0) else 1
        ind_pf.append(gw / gl if gl > 0 else 99)
    def ci(arr):
        p = np.percentile(arr, [2.5, 97.5])
        return {'mean': round(float(np.mean(arr)), 4), 'ci_lower': round(float(p[0]), 4), 'ci_upper': round(float(p[1]), 4)}
    return {
        'daily_block_bootstrap': {'win_rate': ci(daily_wr), 'mean_trade': ci(daily_mt), 'pf': ci(daily_pf)},
        'weekly_block_bootstrap': {'win_rate': ci(weekly_wr), 'mean_trade': ci(weekly_mt), 'pf': ci(weekly_pf)},
        'independent_bootstrap': {'win_rate': ci(ind_wr), 'mean_trade': ci(ind_mt), 'pf': ci(ind_pf)},
        'n_bootstrap': n_boot,
        'note': 'Block bootstrap accounts for temporal correlation. If block CIs are wider than independent CIs, trades are correlated.',
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 4I: COST STRESS FOR CONDITIONAL EDGE
# ═══════════════════════════════════════════════════════════════

def phase4i_cost_stress_conditional(pdata):
    """Test low+mid vol under increasing costs."""
    slippages = [0.1, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
    results = {}
    for slp in slippages:
        ts, mdd, bal = run_sim(pdata, friction='realistic', commission_override=3.50, slippage_override=slp)
        if not ts: continue
        ts = add_regimes_and_mfe_mae(ts, pdata)
        low_mid = [t for t in ts if (t.vol_regime or (t.regime or {}).get('vol_regime', '')) in ('low_vol', 'mid_vol')]
        all_r = _compute(ts, f'all_slp{slp}')
        lm_r = _compute(low_mid, f'lowmid_slp{slp}')
        results[slp] = {
            'all_trades': all_r,
            'low_mid_vol': lm_r,
        }
    ts_base, mdd_base, bal_base = run_sim(pdata, friction='realistic')
    ts_base = add_regimes_and_mfe_mae(ts_base, pdata)
    low_mid_base = [t for t in ts_base if (t.vol_regime or (t.regime or {}).get('vol_regime', '')) in ('low_vol', 'mid_vol')]
    results['baseline'] = {
        'all_trades': _compute(ts_base, 'baseline_all'),
        'low_mid_vol': _compute(low_mid_base, 'baseline_lowmid'),
    }
    return results

# ═══════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    t0 = time.time()
    print("=" * 80)
    print("  MR PHASE 4 FORENSIC ANALYSIS — FALSIFICATION / VALIDATION")
    print("=" * 80)

    print("\n[0] Loading data (ALIGNED)...")
    pdata_aligned = load_pair_data_aligned('2018-01-01', '2026-07-19')
    print(f"    {len(pdata_aligned)} pairs (aligned)")

    print("\n[0b] Loading data (UNALIGNED for audit)...")
    pdata_unaligned = load_pair_data_unaligned('2018-01-01', '2026-07-19')
    print(f"    {len(pdata_unaligned)} pairs (unaligned)")

    print("\n[B] Baseline simulation (ALIGNED)...")
    trades, mdd, bal = run_sim(pdata_aligned, friction='realistic')
    print(f"    Trades={len(trades)} MDD={mdd * 100:.2f}%")
    trades = add_regimes_and_mfe_mae(trades, pdata_aligned)

    R = {}

    print("\n[4A] Session labeling audit...")
    R['session_audit'] = phase4a_session_audit(trades)

    print("[4B] Timestamp alignment audit...")
    R['alignment_audit'] = phase4b_alignment_audit(pdata_aligned, pdata_unaligned)

    print("[4C] Vol × year matrix...")
    R['vol_year_matrix'] = phase4c_vol_year_matrix(trades)

    print("[4D] Winner fingerprint...")
    R['winner_fingerprint'] = phase4d_winner_fingerprint(trades)

    print("[4E] Exit mechanism audit...")
    R['exit_audit'] = phase4e_exit_audit(trades)

    print("[4F] Holding-time counterfactual...")
    R['holding_counterfactual'] = phase4f_holding_counterfactual(pdata_aligned)

    print("[4G] Pair decomposition...")
    R['pair_decomposition'] = phase4g_pair_decomposition(trades)

    print("[4H] Statistical dependence (block bootstrap)...")
    R['statistical_dependence'] = phase4h_statistical_dependence(trades)

    print("[4I] Cost stress for conditional edge...")
    R['cost_stress_conditional'] = phase4i_cost_stress_conditional(pdata_aligned)

    R['baseline'] = _compute(trades, 'baseline_full')

    os.makedirs('/root/that/logs', exist_ok=True)
    with open('/root/that/logs/mr_phase4_metrics.json', 'w') as f:
        json.dump(R, f, indent=2, default=str)
    print(f"\n  Saved /root/that/logs/mr_phase4_metrics.json")
    print(f"\n[DONE] {time.time() - t0:.1f}s")
