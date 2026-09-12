"""MR Phase 5 Forensic Analysis — Causal Regime Classification.

Phase 5 extends Phase 4 with:
- Causal vol regime classification (expanding window, no look-ahead)
- vol_mode parameter ('causal' vs 'fullsample') in simulation
- MAJORS set for major-pair filtering
- min_history=200 bars before allowing regime classification
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
MAJORS={'EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
LEV=100; ACC=2500; RISK=0.020
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'GBP/JPY':3.0,'AUD/JPY':2.0,'CAD/JPY':2.5,'NZD/JPY':3.0,'EUR/AUD':2.0,'EUR/CAD':2.5,'GBP/AUD':3.5,'GBP/CAD':3.5,'AUD/CAD':2.0,'AUD/CHF':2.5,'NZD/CHF':3.0,'CAD/CHF':3.0}
MIN_HISTORY=200

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
    ref_pair = max(raw_data.keys(), key=lambda p: len(raw_data[p]['d30']))
    ref_ts = raw_data[ref_pair]['d30'].index
    pdata = {}
    for pair, rd in raw_data.items():
        d30 = rd['d30']
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

# ═══════════════════════════════════════════════════════════════
# TRADE DATA CLASS
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
    atr_pct_at_entry: float = 0.0; rv_at_entry: float = 0.0
    dist_ema200: float = 0.0; dist_ema50: float = 0.0
    trend_regime: str = ''; vol_regime: str = ''

# ═══════════════════════════════════════════════════════════════
# VOL REGIME CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classify_vol_regime_causal(atr_pct_arr, bar_idx, min_history=MIN_HISTORY):
    """Causal vol regime: uses ONLY data up to bar_idx (expanding window).
    Returns 'unknown' if fewer than min_history bars available."""
    if bar_idx >= len(atr_pct_arr): return 'unknown'
    atr = atr_pct_arr[bar_idx]
    if np.isnan(atr): return 'unknown'
    history = atr_pct_arr[:bar_idx]
    valid = history[~np.isnan(history)]
    if len(valid) < min_history: return 'unknown'
    p25 = np.percentile(valid, 25)
    p75 = np.percentile(valid, 75)
    p95 = np.percentile(valid, 95)
    if atr <= p25: return 'low_vol'
    elif atr >= p95: return 'extreme_vol'
    elif atr >= p75: return 'high_vol'
    else: return 'mid_vol'


def classify_vol_regime_fullsample(atr_pct_arr, bar_idx):
    """Full-sample vol regime: uses ALL data (look-ahead bias). For comparison only."""
    if bar_idx >= len(atr_pct_arr): return 'unknown'
    atr = atr_pct_arr[bar_idx]
    if np.isnan(atr): return 'unknown'
    valid = atr_pct_arr[~np.isnan(atr_pct_arr)]
    if len(valid) == 0: return 'unknown'
    p25 = np.percentile(valid, 25)
    p75 = np.percentile(valid, 75)
    p95 = np.percentile(valid, 95)
    if atr <= p25: return 'low_vol'
    elif atr >= p95: return 'extreme_vol'
    elif atr >= p75: return 'high_vol'
    else: return 'mid_vol'

# ═══════════════════════════════════════════════════════════════
# TREND REGIME CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classify_trend_regime(c, e200):
    if np.isnan(e200) or e200 == 0: return 'unknown'
    d = abs(c - e200) / e200 * 100
    if d < 0.1: return 'near_ema200'
    elif d < 0.3: return 'weak_trend'
    else: return 'strong_trend'

# ═══════════════════════════════════════════════════════════════
# SIMULATION ENGINE (WITH vol_mode PARAMETER)
# ═══════════════════════════════════════════════════════════════

def run_sim(pdata, friction='realistic', commission_override=None, slippage_override=None,
            max_conc=10, rr=2.7, risk=RISK, session_filter=True, vol_mode='causal'):
    """Run simulation engine.

    vol_mode:
        'causal'     - vol regime classified using expanding window (no look-ahead)
        'fullsample' - vol regime classified using full sample (has look-ahead bias)
    """
    if vol_mode == 'causal':
        _classify_vol = classify_vol_regime_causal
    else:
        _classify_vol = classify_vol_regime_fullsample

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
                    day_of_week=pos['entry_ts'].dayofweek, holding_bars=i - pos['bar'],
                    atr_pct_at_entry=pos.get('atr_pct', 0.0), rv_at_entry=pos.get('rv', 0.0),
                    vol_regime=pos.get('vol_regime', ''), trend_regime=pos.get('trend_regime', '')))
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
                    day_of_week=pos['entry_ts'].dayofweek, holding_bars=i - pos['bar'],
                    atr_pct_at_entry=pos.get('atr_pct', 0.0), rv_at_entry=pos.get('rv', 0.0),
                    vol_regime=pos.get('vol_regime', ''), trend_regime=pos.get('trend_regime', '')))
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
            d_idx = pd_['daily'].index.get_loc(d_ts)
            if d_idx == 0: continue
            prev_ts = pd_['daily'].index[d_idx - 1]
            dg = pd_['daily'].loc[prev_ts, 'close'] > pd_['daily'].loc[prev_ts, 'open']
            if tr == 1 and not dg: continue
            if tr == -1 and dg: continue
            pip = pd_['pip']; sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
            sl_dist = abs(c_val - sl)
            if sl_dist < 2 * pip: continue
            tp = c_val + sl_dist * rr if tr == 1 else c_val - sl_dist * rr
            ef = c_val + (pd_['spread'] * 0.5 * spread_m + slp_side) * pip if tr == 1 else c_val - (pd_['spread'] * 0.5 * spread_m + slp_side) * pip
            atr_val = pd_['atr_pct'][i] if not np.isnan(pd_['atr_pct'][i]) else 0
            rv_val = pd_['rv_20'][i] if not np.isnan(pd_['rv_20'][i]) else 0
            dist200 = (c_val - ev) / ev * 100 if ev != 0 else 0
            dist50 = (c_val - e5) / e5 * 100 if e5 != 0 else 0
            vr = _classify_vol(pd_['atr_pct'], i)
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

# ═══════════════════════════════════════════════════════════════
# MFE / MAE COMPUTATION
# ═══════════════════════════════════════════════════════════════

def add_mfe_mae(trades, pdata):
    """Add max_favorable_pips and max_adverse_pips to each trade from raw data."""
    for t in trades:
        pd_ = pdata.get(t.pair)
        if pd_ is None or t.exit_ts is None:
            continue
        raw = pd_.get('raw_df')
        if raw is None:
            continue
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
# PHASE 5a — REGIME COMPARISON (CAUSAL vs FULLSAMPLE)
# ═══════════════════════════════════════════════════════════════

def phase5a_regime_comparison(pdata):
    print("\n[5a] Running causal vs fullsample regime comparison...")
    trades_causal, mdd_c, bal_c = run_sim(pdata, vol_mode='causal')
    add_mfe_mae(trades_causal, pdata)
    trades_full, mdd_f, bal_f = run_sim(pdata, vol_mode='fullsample')
    add_mfe_mae(trades_full, pdata)
    mc = _compute(trades_causal, 'causal')
    mf = _compute(trades_full, 'fullsample')
    regime_dist_c = defaultdict(int)
    regime_dist_f = defaultdict(int)
    for t in trades_causal:
        regime_dist_c[t.vol_regime] += 1
    for t in trades_full:
        regime_dist_f[t.vol_regime] += 1
    regime_dist_c = {k: v for k, v in sorted(regime_dist_c.items())}
    regime_dist_f = {k: v for k, v in sorted(regime_dist_f.items())}
    ry_c = defaultdict(lambda: defaultdict(int))
    ry_f = defaultdict(lambda: defaultdict(int))
    for t in trades_causal:
        ry_c[t.vol_regime][t.year] += 1
    for t in trades_full:
        ry_f[t.vol_regime][t.year] += 1
    ry_c = {r: {y: c for y, c in sorted(d.items())} for r, d in sorted(ry_c.items())}
    ry_f = {r: {y: c for y, c in sorted(d.items())} for r, d in sorted(ry_f.items())}
    sv_c = defaultdict(lambda: defaultdict(int))
    sv_f = defaultdict(lambda: defaultdict(int))
    for t in trades_causal:
        sv_c[t.entry_session][t.vol_regime] += 1
    for t in trades_full:
        sv_f[t.entry_session][t.vol_regime] += 1
    sv_c = {s: {v: c for v, c in sorted(d.items())} for s, d in sorted(sv_c.items())}
    sv_f = {s: {v: c for v, c in sorted(d.items())} for s, d in sorted(sv_f.items())}
    result = {
        'causal': mc, 'fullsample': mf,
        'causal_trades_count': len(trades_causal),
        'fullsample_trades_count': len(trades_full),
        'causal_final_bal': round(bal_c, 2), 'fullsample_final_bal': round(bal_f, 2),
        'causal_mdd': round(mdd_c * 100, 2), 'fullsample_mdd': round(mdd_f * 100, 2),
        'regime_dist_causal': regime_dist_c, 'regime_dist_fullsample': regime_dist_f,
        'regime_x_year_causal': ry_c, 'regime_x_year_fullsample': ry_f,
        'session_x_vol_causal': sv_c, 'session_x_vol_fullsample': sv_f,
    }
    print(f"  Causal: {len(trades_causal)} trades, PF={mc['profit_factor']}, WR={mc['win_rate']}%, PnL={mc['net_pnl']}")
    print(f"  Fullsample: {len(trades_full)} trades, PF={mf['profit_factor']}, WR={mf['win_rate']}%, PnL={mf['net_pnl']}")
    return trades_causal, result


# ═══════════════════════════════════════════════════════════════
# PHASE 5b — TEMPORAL PROFILE (MTM at multiple horizons)
# ═══════════════════════════════════════════════════════════════

def phase5b_temporal_profile(trades, pdata):
    print("\n[5b] Computing temporal profile (mark-to-market at horizons)...")
    horizons = [1, 2, 3, 5, 10, 15, 20, 25, 30]
    groups = {
        'london': lambda t: t.entry_session == 'london_only',
        'overlap': lambda t: t.entry_session == 'overlap',
        'ny': lambda t: t.entry_session == 'ny_only',
        'major': lambda t: t.pair in MAJORS,
        'cross': lambda t: t.pair not in MAJORS,
        'strong_trend': lambda t: t.trend_regime == 'strong_trend',
        'weak_trend': lambda t: t.trend_regime == 'weak_trend',
        'low_vol': lambda t: t.vol_regime == 'low_vol',
        'mid_vol': lambda t: t.vol_regime == 'mid_vol',
        'high_vol': lambda t: t.vol_regime == 'high_vol',
    }
    def compute_mtm(subset, h):
        if not subset:
            return None
        mtms = []
        for t in subset:
            pd_ = pdata.get(t.pair)
            if pd_ is None:
                continue
            entry_bar = t.entry_bar
            future_bar = entry_bar + h
            if future_bar >= pd_['n']:
                continue
            future_c = pd_['c'][future_bar]
            if t.trend == 1:
                mtm_pips = (future_c - t.entry) / t.pip
            else:
                mtm_pips = (t.entry - future_c) / t.pip
            mtm_usd = mtm_pips * t.pv * t.lot - t.spread * 0.5 * t.pv * t.lot
            mtms.append(mtm_usd)
        if not mtms:
            return None
        mtms = np.array(mtms)
        w = int(np.sum(mtms > 0)); l_ = int(np.sum(mtms <= 0))
        gw = float(np.sum(mtms[mtms > 0])) if w > 0 else 0
        gl = float(np.abs(np.sum(mtms[mtms <= 0]))) if l_ > 0 else 0
        return {
            'n': len(mtms), 'mean': round(float(np.mean(mtms)), 2),
            'median': round(float(np.median(mtms)), 2),
            'wr': round(w / len(mtms) * 100, 2) if mtms.size > 0 else 0,
            'pf': round(gw / gl, 2) if gl > 0 else 99.0,
            'p25': round(float(np.percentile(mtms, 25)), 2),
            'p75': round(float(np.percentile(mtms, 75)), 2),
        }
    result = {'horizons': horizons, 'all_trades': {}, 'by_group': {}}
    for h in horizons:
        result['all_trades'][str(h)] = compute_mtm(trades, h)
    for gname, gfilter in groups.items():
        subset = [t for t in trades if gfilter(t)]
        result['by_group'][gname] = {}
        for h in horizons:
            result['by_group'][gname][str(h)] = compute_mtm(subset, h)
    print(f"  Computed MTM for {len(horizons)} horizons across {len(groups) + 1} segments")
    return result


# ═══════════════════════════════════════════════════════════════
# PHASE 5c — EXIT INVESTIGATION (SC truncation, MFE timing)
# ═══════════════════════════════════════════════════════════════

def phase5c_exit_investigation(trades, pdata):
    print("\n[5c] Investigating exit mechanics...")
    sc_trades = [t for t in trades if t.exit_reason == 'SC']
    horizons_before = [5, 10, 15, 20, 25, 30]
    sc_mtm = {}
    for h in horizons_before:
        mtms = []
        for t in sc_trades:
            pd_ = pdata.get(t.pair)
            if pd_ is None:
                continue
            bar_before = t.entry_bar + t.holding_bars - h
            if bar_before < t.entry_bar or bar_before >= pd_['n']:
                continue
            c_before = pd_['c'][bar_before]
            if t.trend == 1:
                mtm_pips = (c_before - t.entry) / t.pip
            else:
                mtm_pips = (t.entry - c_before) / t.pip
            mtm_usd = mtm_pips * t.pv * t.lot
            mtms.append(mtm_usd)
        if mtms:
            mtms = np.array(mtms)
            w = int(np.sum(mtms > 0)); l_ = int(np.sum(mtms <= 0))
            gw = float(np.sum(mtms[mtms > 0])) if w > 0 else 0
            gl = float(np.abs(np.sum(mtms[mtms <= 0]))) if l_ > 0 else 0
            sc_mtm[str(h)] = {
                'n': len(mtms), 'mean': round(float(np.mean(mtms)), 2),
                'median': round(float(np.median(mtms)), 2),
                'wr': round(w / len(mtms) * 100, 2),
                'pf': round(gw / gl, 2) if gl > 0 else 99.0,
            }
        else:
            sc_mtm[str(h)] = None
    mfe_timing = []
    still_favorable = 0
    still_favorable_total = 0
    for t in trades:
        pd_ = pdata.get(t.pair)
        if pd_ is None or t.holding_bars < 2:
            continue
        entry_bar = t.entry_bar
        exit_bar = entry_bar + t.holding_bars
        if exit_bar >= pd_['n']:
            continue
        if t.trend == 1:
            favorable = pd_['h'][entry_bar + 1:exit_bar + 1] - t.entry
            adverse = t.entry - pd_['lo'][entry_bar + 1:exit_bar + 1]
        else:
            favorable = t.entry - pd_['lo'][entry_bar + 1:exit_bar + 1]
            adverse = pd_['h'][entry_bar + 1:exit_bar + 1] - t.entry
        if len(favorable) == 0:
            continue
        favorable_pips = favorable / t.pip
        adverse_pips = adverse / t.pip
        if t.trend == 1:
            mfe_bar = np.argmax(favorable_pips) + 1
            mae_bar = np.argmax(adverse_pips) + 1
        else:
            mfe_bar = np.argmax(favorable_pips) + 1
            mae_bar = np.argmax(adverse_pips) + 1
        mfe_timing.append(mfe_bar / t.holding_bars * 100)
        if t.exit_reason == 'SC':
            still_favorable_total += 1
            exit_bar_idx = entry_bar + t.holding_bars
            if exit_bar_idx >= 2:
                if t.trend == 1:
                    price_at_exit = pd_['c'][exit_bar_idx - 1]
                    if price_at_exit > t.entry:
                        still_favorable += 1
                else:
                    price_at_exit = pd_['c'][exit_bar_idx - 1]
                    if price_at_exit < t.entry:
                        still_favorable += 1
    mfe_timing = np.array(mfe_timing) if mfe_timing else np.array([0])
    result = {
        'sc_trades_count': len(sc_trades),
        'sc_exit_mtm_by_horizon': sc_mtm,
        'mfe_timing_pct': {
            'mean': round(float(np.mean(mfe_timing)), 2),
            'median': round(float(np.median(mfe_timing)), 2),
            'p25': round(float(np.percentile(mfe_timing, 25)), 2),
            'p75': round(float(np.percentile(mfe_timing, 75)), 2),
        },
        'still_favorable_at_sc': {
            'count': still_favorable,
            'total': still_favorable_total,
            'pct': round(still_favorable / still_favorable_total * 100, 2) if still_favorable_total > 0 else 0,
        },
    }
    print(f"  SC trades: {len(sc_trades)}")
    print(f"  Still favorable at SC exit: {result['still_favorable_at_sc']['pct']}%")
    print(f"  MFE timing (median): {result['mfe_timing_pct']['median']}% of holding period")
    return result


# ═══════════════════════════════════════════════════════════════
# PHASE 5d — WINNER FINGERPRINT (H1 hypothesis testing)
# ═══════════════════════════════════════════════════════════════

def phase5d_winner_fingerprint(trades, pdata):
    print("\n[5d] Winner fingerprint analysis (H1 hypothesis testing)...")
    FINGERPRINT_PAIRS = {'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD', 'NZD/USD'}
    def is_fingerprint(t):
        return (7 <= t.entry_hour <= 8 and
                t.pair in FINGERPRINT_PAIRS and
                t.trend_regime == 'strong_trend')
    discovery = [t for t in trades if 2018 <= t.year <= 2022]
    validation = [t for t in trades if 2023 <= t.year <= 2024]
    untouched = [t for t in trades if 2025 <= t.year <= 2026]
    def eval_group(group, label):
        fp = [t for t in group if is_fingerprint(t)]
        non_fp = [t for t in group if not is_fingerprint(t)]
        def summarize(subset):
            if not subset:
                return None
            pnls = np.array([t.pnl for t in subset])
            w = int(np.sum(pnls > 0)); l_ = int(np.sum(pnls <= 0))
            gw = float(np.sum(pnls[pnls > 0])) if w > 0 else 0
            gl = float(np.abs(np.sum(pnls[pnls <= 0]))) if l_ > 0 else 0
            return {
                'trades': len(subset), 'wins': w, 'losses': l_,
                'wr': round(w / len(subset) * 100, 2) if subset else 0,
                'pf': round(gw / gl, 2) if gl > 0 else 99.0,
                'expectancy': round(float(np.mean(pnls)), 2),
                'pnl': round(float(np.sum(pnls)), 2),
            }
        return {
            'fingerprint': summarize(fp),
            'non_fingerprint': summarize(non_fp),
            'fingerprint_count': len(fp),
            'non_fingerprint_count': len(non_fp),
        }
    result = {
        'hypothesis': 'Early-London (hour 7-8) major-pair entries in strong_trend conditions have higher forward expectancy.',
        'fingerprint_pairs': sorted(FINGERPRINT_PAIRS),
        'discovery_2018_2022': eval_group(discovery, 'discovery'),
        'validation_2023_2024': eval_group(validation, 'validation'),
        'untouched_2025_2026': eval_group(untouched, 'untouched'),
    }
    for period, data in [('discovery', result['discovery_2018_2022']),
                          ('validation', result['validation_2023_2024']),
                          ('untouched', result['untouched_2025_2026'])]:
        fp = data['fingerprint']
        nfp = data['non_fingerprint']
        if fp and nfp:
            print(f"  {period}: FP={fp['trades']}t PF={fp['pf']} WR={fp['wr']}% | Non-FP={nfp['trades']}t PF={nfp['pf']} WR={nfp['wr']}%")
        else:
            print(f"  {period}: FP={fp['trades'] if fp else 0}t | Non-FP={nfp['trades'] if nfp else 0}t")
    return result


# ═══════════════════════════════════════════════════════════════
# PHASE 5e — PAIR STABILITY (yearly per-pair metrics)
# ═══════════════════════════════════════════════════════════════

def phase5e_pair_stability(trades):
    print("\n[5e] Pair stability analysis...")
    FOCUS_PAIRS = ['GBP/AUD', 'GBP/CAD', 'NZD/JPY', 'CAD/CHF', 'EUR/CHF', 'NZD/CHF', 'AUD/CHF']
    pair_year = defaultdict(lambda: defaultdict(list))
    for t in trades:
        pair_year[t.pair][t.year].append(t)
    def summarize(subset):
        if not subset:
            return None
        pnls = np.array([t.pnl for t in subset])
        w = int(np.sum(pnls > 0)); l_ = int(np.sum(pnls <= 0))
        gw = float(np.sum(pnls[pnls > 0])) if w > 0 else 0
        gl = float(np.abs(np.sum(pnls[pnls <= 0]))) if l_ > 0 else 0
        return {
            'trades': len(subset), 'wr': round(w / len(subset) * 100, 2) if subset else 0,
            'pf': round(gw / gl, 2) if gl > 0 else 99.0,
            'expectancy': round(float(np.mean(pnls)), 2),
            'pnl': round(float(np.sum(pnls)), 2),
        }
    result = {}
    for pair in sorted(pair_year.keys()):
        yearly = {}
        for yr in sorted(pair_year[pair].keys()):
            yearly[str(yr)] = summarize(pair_year[pair][yr])
        result[pair] = yearly
    classification = {}
    for pair in FOCUS_PAIRS:
        if pair not in result:
            classification[pair] = 'no_data'
            continue
        yearly = result[pair]
        pfs = []
        wrs = []
        for yr_str, data in yearly.items():
            if data is not None:
                pfs.append(data['pf'])
                wrs.append(data['wr'])
        if not pfs:
            classification[pair] = 'no_data'
        elif all(pf < 1.0 for pf in pfs) and len(pfs) >= 3:
            classification[pair] = 'structurally_bad'
        elif sum(pf < 1.0 for pf in pfs) >= len(pfs) * 0.7 and len(pfs) >= 3:
            classification[pair] = 'temporarily_bad'
        else:
            classification[pair] = 'inconclusive'
    focus_result = {p: result.get(p, {}) for p in FOCUS_PAIRS}
    print(f"  Classified {len(FOCUS_PAIRS)} focus pairs:")
    for p in FOCUS_PAIRS:
        print(f"    {p}: {classification.get(p, 'unknown')}")
    return {
        'all_pairs_yearly': result,
        'focus_pairs': focus_result,
        'classification': classification,
    }


# ═══════════════════════════════════════════════════════════════
# PHASE 5f — SESSION HOURLY BREAKDOWN (London hours)
# ═══════════════════════════════════════════════════════════════

def phase5f_session_hourly(trades):
    print("\n[5f] Session hourly breakdown (London)...")
    london_trades = [t for t in trades if t.entry_session in ('london_only', 'overlap')]
    hourly = defaultdict(list)
    for t in london_trades:
        hourly[t.entry_hour].append(t)
    def summarize(subset):
        if not subset:
            return None
        pnls = np.array([t.pnl for t in subset])
        w = int(np.sum(pnls > 0)); l_ = int(np.sum(pnls <= 0))
        gw = float(np.sum(pnls[pnls > 0])) if w > 0 else 0
        gl = float(np.abs(np.sum(pnls[pnls <= 0]))) if l_ > 0 else 0
        return {
            'trades': len(subset), 'wr': round(w / len(subset) * 100, 2) if subset else 0,
            'pf': round(gw / gl, 2) if gl > 0 else 99.0,
            'expectancy': round(float(np.mean(pnls)), 2),
        }
    result = {}
    for h in range(6, 13):
        result[str(h)] = summarize(hourly.get(h, []))
    print(f"  London session hours covered: {sorted(hourly.keys())}")
    return result


# ═══════════════════════════════════════════════════════════════
# PHASE 5g — MAJOR vs CROSS COMPARISON
# ═══════════════════════════════════════════════════════════════

def phase5g_major_vs_cross(trades):
    print("\n[5g] Major vs cross comparison...")
    def summarize(subset):
        if not subset:
            return None
        pnls = np.array([t.pnl for t in subset])
        w = int(np.sum(pnls > 0)); l_ = int(np.sum(pnls <= 0))
        gw = float(np.sum(pnls[pnls > 0])) if w > 0 else 0
        gl = float(np.abs(np.sum(pnls[pnls <= 0]))) if l_ > 0 else 0
        return {
            'trades': len(subset), 'wr': round(w / len(subset) * 100, 2) if subset else 0,
            'pf': round(gw / gl, 2) if gl > 0 else 99.0,
            'expectancy': round(float(np.mean(pnls)), 2),
            'pnl': round(float(np.sum(pnls)), 2),
        }
    majors = [t for t in trades if t.pair in MAJORS]
    crosses = [t for t in trades if t.pair not in MAJORS]
    result = {
        'majors': summarize(majors),
        'crosses': summarize(crosses),
        'by_session_pair_type': {},
    }
    session_types = ['london_only', 'overlap', 'ny_only']
    for st in session_types:
        maj_st = [t for t in trades if t.pair in MAJORS and t.entry_session == st]
        cro_st = [t for t in trades if t.pair not in MAJORS and t.entry_session == st]
        result['by_session_pair_type'][f'{st}+major'] = summarize(maj_st)
        result['by_session_pair_type'][f'{st}+cross'] = summarize(cro_st)
    print(f"  Majors: {len(majors)}t, Crosses: {len(crosses)}t")
    for key, val in result['by_session_pair_type'].items():
        if val:
            print(f"    {key}: {val['trades']}t PF={val['pf']} WR={val['wr']}%")
    return result


# ═══════════════════════════════════════════════════════════════
# PHASE 5h — BLOCK BOOTSTRAP (candidate hypothesis CIs)
# ═══════════════════════════════════════════════════════════════

def phase5h_bootstrap(trades, n_iter=5000):
    print(f"\n[5h] Block bootstrap ({n_iter} iterations)...")
    candidate = [t for t in trades
                 if t.entry_session in ('london_only', 'overlap')
                 and t.pair in MAJORS
                 and t.trend_regime == 'strong_trend']
    if not candidate:
        print("  No candidate trades found!")
        return {'error': 'no_candidate_trades'}
    pnls = np.array([t.pnl for t in candidate])
    n = len(pnls)
    np.random.seed(42)
    results = {'independent': [], 'daily': [], 'weekly': []}
    def calc_stats(arr):
        w = int(np.sum(arr > 0)); l_ = int(np.sum(arr <= 0))
        gw = float(np.sum(arr[arr > 0])) if w > 0 else 0
        gl = float(np.abs(np.sum(arr[arr <= 0]))) if l_ > 0 else 0
        return {
            'pf': round(gw / gl, 2) if gl > 0 else 99.0,
            'wr': round(w / len(arr) * 100, 2) if len(arr) > 0 else 0,
            'mean_trade': round(float(np.mean(arr)), 2),
        }
    for _ in range(n_iter):
        idx = np.random.choice(n, size=n, replace=True)
        results['independent'].append(calc_stats(pnls[idx]))
    dates = np.array([t.entry_ts.date() if hasattr(t.entry_ts, 'date') else t.entry_ts for t in candidate])
    unique_dates = np.unique(dates)
    date_groups = {d: pnls[dates == d] for d in unique_dates}
    date_keys = list(date_groups.keys())
    n_dates = len(date_keys)
    for _ in range(n_iter):
        sampled_dates = np.random.choice(date_keys, size=n_dates, replace=True)
        sampled_pnl = np.concatenate([date_groups[d] for d in sampled_dates])
        results['daily'].append(calc_stats(sampled_pnl))
    iso_weeks = []
    for d in unique_dates:
        iso_week = pd.Timestamp(d).isocalendar()
        iso_weeks.append(f"{iso_week[0]}-W{iso_week[1]:02d}")
    unique_weeks = list(set(iso_weeks))
    week_map = {}
    for i, d in enumerate(unique_dates):
        w = iso_weeks[i]
        if w not in week_map:
            week_map[w] = []
        week_map[w].append(pnls[i])
    week_keys = list(week_map.keys())
    n_weeks = len(week_keys)
    for _ in range(n_iter):
        sampled_weeks = np.random.choice(week_keys, size=n_weeks, replace=True)
        sampled_pnl = np.concatenate([week_map[w] for w in sampled_weeks])
        results['weekly'].append(calc_stats(sampled_pnl))
    summary = {}
    for block_type in ['independent', 'daily', 'weekly']:
        pf_arr = np.array([r['pf'] for r in results[block_type]])
        wr_arr = np.array([r['wr'] for r in results[block_type]])
        mt_arr = np.array([r['mean_trade'] for r in results[block_type]])
        summary[block_type] = {
            'pf_ci_95': [round(float(np.percentile(pf_arr, 2.5)), 2), round(float(np.percentile(pf_arr, 97.5)), 2)],
            'wr_ci_95': [round(float(np.percentile(wr_arr, 2.5)), 2), round(float(np.percentile(wr_arr, 97.5)), 2)],
            'mean_trade_ci_95': [round(float(np.percentile(mt_arr, 2.5)), 2), round(float(np.percentile(mt_arr, 97.5)), 2)],
            'pf_median': round(float(np.median(pf_arr)), 2),
            'wr_median': round(float(np.median(wr_arr)), 2),
            'mean_trade_median': round(float(np.median(mt_arr)), 2),
        }
    print(f"  Candidate trades: {n}")
    for bt in ['independent', 'daily', 'weekly']:
        s = summary[bt]
        print(f"  {bt}: PF CI=[{s['pf_ci_95'][0]}, {s['pf_ci_95'][1]}], WR CI=[{s['wr_ci_95'][0]}, {s['wr_ci_95'][1]}]")
    return {'candidate_count': n, 'iterations': n_iter, 'summary': summary}


# ═══════════════════════════════════════════════════════════════
# PHASE 5i — COST STRESS TEST (slippage sensitivity)
# ═══════════════════════════════════════════════════════════════

def phase5i_cost_stress(pdata, trades):
    print("\n[5i] Cost stress test (slippage sensitivity)...")
    slippages = [0.3, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    candidate_filter = lambda t: (t.entry_session in ('london_only', 'overlap') and
                                  t.pair in MAJORS and
                                  t.trend_regime == 'strong_trend')
    candidate_trades = [t for t in trades if candidate_filter(t)]
    candidate_entry_bars = set((t.pair, t.entry_bar) for t in candidate_trades)
    result = {}
    for slp in slippages:
        stressed_trades = []
        for t in trades:
            if (t.pair, t.entry_bar) in candidate_entry_bars:
                original_entry = t.entry
                original_exit = t.exit_price
                if t.trend == 1:
                    new_entry = original_entry + slp * t.pip
                    new_exit = original_exit - slp * t.pip
                else:
                    new_entry = original_entry - slp * t.pip
                    new_exit = original_exit + slp * t.pip
                if t.trend == 1:
                    gross = (new_exit - new_entry) / t.pip * t.pv * t.lot
                else:
                    gross = (new_entry - new_exit) / t.pip * t.pv * t.lot
                new_pnl = gross - t.commission
                stressed_t = Trade(
                    pair=t.pair, trend=t.trend, entry=new_entry, sl=t.sl, tp=t.tp,
                    lot=t.lot, pip=t.pip, pv=t.pv, spread=t.spread,
                    entry_bar=t.entry_bar, entry_ts=t.entry_ts,
                    exit_price=new_exit, exit_ts=t.exit_ts,
                    pnl=new_pnl, gross_pnl=gross, cost=t.cost,
                    commission=t.commission, exit_reason=t.exit_reason,
                    is_win=(new_pnl > 0),
                    entry_session=t.entry_session, exit_session=t.exit_session,
                    entry_hour=t.entry_hour, entry_dow=t.entry_dow,
                    year=t.year, month=t.month,
                    regime=t.regime, day_of_week=t.day_of_week,
                    holding_bars=t.holding_bars,
                    max_adverse_pips=t.max_adverse_pips,
                    max_favorable_pips=t.max_favorable_pips,
                    atr_pct_at_entry=t.atr_pct_at_entry,
                    rv_at_entry=t.rv_at_entry,
                    dist_ema200=t.dist_ema200, dist_ema50=t.dist_ema50,
                    trend_regime=t.trend_regime, vol_regime=t.vol_regime,
                )
                stressed_trades.append(stressed_t)
        if stressed_trades:
            m_s = _compute(stressed_trades, f'slippage_{slp}')
            result[str(slp)] = m_s
        else:
            result[str(slp)] = None
    print(f"  Tested {len(slippages)} slippage levels on {len(candidate_trades)} candidate trades")
    for slp, res in result.items():
        if res:
            print(f"    Slippage={slp}: PF={res['profit_factor']}, WR={res['win_rate']}%, PnL={res['net_pnl']}")
    return result


# ═══════════════════════════════════════════════════════════════
# MAIN BLOCK
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import time
    t0 = time.time()
    print("=" * 60)
    print("MR PHASE 5 — FORENSIC ANALYSIS")
    print("=" * 60)
    os.makedirs('/root/that/logs', exist_ok=True)
    START = pd.Timestamp('2018-01-01', tz='UTC')
    END = pd.Timestamp('2026-06-01', tz='UTC')
    print("\nLoading data...")
    pdata = load_pair_data_aligned(START, END)
    print(f"Loaded {len(pdata)} pairs")

    print("\nRunning causal simulation (baseline)...")
    trades_causal, mdd_c, bal_c = run_sim(pdata, vol_mode='causal')
    add_mfe_mae(trades_causal, pdata)
    baseline_metrics = _compute(trades_causal, 'causal_baseline')
    print(f"Baseline: {len(trades_causal)} trades, PF={baseline_metrics['profit_factor']}, WR={baseline_metrics['win_rate']}%")

    phase5a_result = phase5a_regime_comparison(pdata)
    phase5b_result = phase5b_temporal_profile(trades_causal, pdata)
    phase5c_result = phase5c_exit_investigation(trades_causal, pdata)
    phase5d_result = phase5d_winner_fingerprint(trades_causal, pdata)
    phase5e_result = phase5e_pair_stability(trades_causal)
    phase5f_result = phase5f_session_hourly(trades_causal)
    phase5g_result = phase5g_major_vs_cross(trades_causal)
    phase5h_result = phase5h_bootstrap(trades_causal)
    phase5i_result = phase5i_cost_stress(pdata, trades_causal)

    all_results = {
        'phase': 5,
        'timestamp': pd.Timestamp.now().isoformat(),
        'elapsed_seconds': round(time.time() - t0, 1),
        'data_range': {'start': str(START), 'end': str(END), 'pairs': len(pdata)},
        'baseline': baseline_metrics,
        'phase5a_regime_comparison': phase5a_result,
        'phase5b_temporal_profile': phase5b_result,
        'phase5c_exit_investigation': phase5c_result,
        'phase5d_winner_fingerprint': phase5d_result,
        'phase5e_pair_stability': phase5e_result,
        'phase5f_session_hourly': phase5f_result,
        'phase5g_major_vs_cross': phase5g_result,
        'phase5h_bootstrap': phase5h_result,
        'phase5i_cost_stress': phase5i_result,
    }

    out_path = '/root/that/logs/mr_phase5_metrics.json'
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Elapsed: {all_results['elapsed_seconds']}s")
    print(f"  Baseline: {len(trades_causal)} trades, PF={baseline_metrics['profit_factor']}, WR={baseline_metrics['win_rate']}%, PnL={baseline_metrics['net_pnl']}")
    if phase5h_result.get('summary'):
        for bt in ['independent', 'daily', 'weekly']:
            s = phase5h_result['summary'].get(bt)
            if s:
                print(f"  Bootstrap ({bt}): PF CI={s['pf_ci_95']}, WR CI={s['wr_ci_95']}")
    print("=" * 60)
