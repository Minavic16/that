"""MR Phase 2 Forensic Analysis — 12 investigations of edge robustness. OPTIMIZED."""
import pickle, json, sys, os, time, warnings
import numpy as np
import pandas as pd
from collections import defaultdict
from dataclasses import dataclass
warnings.filterwarnings('ignore')

import position_sizing as ps

PAIRS=['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD','GBP/AUD','EUR/AUD','NZD/JPY','EUR/CAD','GBP/CAD','AUD/CHF','NZD/CHF','CAD/CHF']
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
LEV=100; ACC=2500; RISK=0.020
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'GBP/JPY':3.0,'AUD/JPY':2.0,'CAD/JPY':2.5,'NZD/JPY':3.0,'EUR/AUD':2.0,'EUR/CAD':2.5,'GBP/AUD':3.5,'GBP/CAD':3.5,'AUD/CAD':2.0,'AUD/CHF':2.5,'NZD/CHF':3.0,'CAD/CHF':3.0}

def igs(ts):
    h, d = ts.hour, ts.dayofweek
    if d == 4 and h >= SKIP_FRI: return False
    if d == 0 and h < SKIP_MON: return False
    if d >= 5: return False
    for s, (s2, e) in SESSIONS.items():
        if s2 <= h < e: return True
    return False

def get_session(ts):
    h = ts.hour
    il = 7 <= h < 16; iny = 12 <= h < 21
    if il and iny: return 'overlap'
    if il: return 'london_only'
    if iny: return 'ny_only'
    return 'none'

@dataclass
class Trade:
    pair: str; trend: int; entry: float; sl: float; tp: float
    lot: float; pip: float; pv: float; spread: float
    entry_bar: int; entry_ts: object
    exit_price: float = 0.0; exit_ts: object = None
    pnl: float = 0.0; gross_pnl: float = 0.0; cost: float = 0.0
    commission: float = 0.0; exit_reason: str = ''; is_win: bool = False
    session: str = ''; entry_hour: int = 0; year: int = 0; month: str = ''
    regime: dict = None

def load_pair_data(start, end):
    pdata = {}
    for pair in PAIRS:
        pk = pair.replace('/', '_')
        try:
            with open(f'/root/data/{pk}.pkl', 'rb') as f: raw = pickle.load(f)
        except FileNotFoundError: continue
        df = raw.get(pair)
        if df is None: continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index = idx; df = df[df.index >= start]; df = df[df.index <= end]
        if len(df) < 500: continue
        pip = ps.pip_size_for_pair(pair); pv = ps.pip_value_per_lot(pair, SNAP)
        d30 = df[['open','high','low','close']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        d4h = df[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        daily = df[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        e200 = d4h['close'].ewm(span=200, adjust=False).mean()
        e50 = d4h['close'].ewm(span=50, adjust=False).mean()
        tr_s = pd.concat([d30['high']-d30['low'], (d30['high']-d30['close'].shift(1)).abs(), (d30['low']-d30['close'].shift(1)).abs()], axis=1).max(axis=1)
        atr_14 = tr_s.rolling(14).mean()
        atr_pct = atr_14 / d30['close'] * 100
        ret_30m = d30['close'].pct_change()
        rv_20 = ret_30m.rolling(20).std() * np.sqrt(48)
        pdata[pair] = {
            'c': d30['close'].values, 'h': d30['high'].values, 'lo': d30['low'].values,
            'o': d30['open'].values, 'ts': d30.index, 'n': len(d30),
            'e200': e200.reindex(d30.index, method='ffill').values,
            'e50': e50.reindex(d30.index, method='ffill').values,
            'daily': daily, 'pip': pip, 'pv': pv, 'spread': SPREAD.get(pair, 2.0),
            'atr_pct': atr_pct.reindex(d30.index, method='ffill').values,
            'rv_20': rv_20.reindex(d30.index, method='ffill').values,
            'raw_df': df,
        }
    return pdata

def run_sim_trades(pdata, friction='realistic', commission_override=None, slippage_override=None,
                   max_conc=10, rr=2.7, risk=RISK, block_entries=False, session_filter=True):
    if friction == 'ideal': spread_m = 0; slp_side = slippage_override if slippage_override is not None else 0.5
    elif friction == 'realistic': spread_m = 1; slp_side = slippage_override if slippage_override is not None else 0.3
    else: spread_m = 2; slp_side = slippage_override if slippage_override is not None else 1.0
    commission = commission_override if commission_override is not None else 3.50
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref = pdata[ref_pair]; n_bars = ref['n']
    bal = ACC; peak = ACC; mdd = 0; open_pos = []; trades = []
    daily_sb = ACC; daily_d = None
    def _igs(ts): return True if not session_filter else igs(ts)
    for i in range(250, n_bars - 1):
        ts_now = ref['ts'][i]; today = ts_now.date()
        if daily_d != today: daily_d = today; daily_sb = bal
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos['pair'])
                if pd_ is None or i >= pd_['n']: continue
                ep = pd_['c'][i] - (pos['spread']*0.5*spread_m+slp_side)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5*spread_m+slp_side)*pos['pip']
                gross = (ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']
                cost = pos['lot']*commission; pnl = gross-cost; bal+=pnl
                trades.append(Trade(pair=pos['pair'],trend=pos['trend'],entry=pos['entry'],sl=pos['sl'],tp=pos['tp'],lot=pos['lot'],pip=pos['pip'],pv=pos['pv'],spread=pos['spread'],entry_bar=pos['bar'],entry_ts=pos['entry_ts'],exit_price=ep,exit_ts=ts_now,pnl=pnl,gross_pnl=gross,cost=cost,commission=pos['lot']*commission,exit_reason='DL',is_win=(pnl>0),session=get_session(ts_now),entry_hour=pos['entry_ts'].hour,year=pos['entry_ts'].year,month=pos['entry_ts'].strftime('%Y-%m')))
            open_pos.clear(); continue
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos['pair'])
            if pd_ is None or i >= pd_['n']: remaining.append(pos); continue
            bar_lo=pd_['lo'][i]; bar_hi=pd_['h'][i]; bar_cl=pd_['c'][i]
            tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False
            def _close(reason, exit_p):
                nonlocal closed, bal
                if tr==1: gross=(exit_p-pos['entry'])/pos['pip']*pos['pv']*pos['lot']
                else: gross=(pos['entry']-exit_p)/pos['pip']*pos['pv']*pos['lot']
                cost=pos['lot']*commission; pnl=gross-cost; bal+=pnl; closed=True
                trades.append(Trade(pair=pos['pair'],trend=tr,entry=pos['entry'],sl=sl,tp=tp,lot=pos['lot'],pip=pos['pip'],pv=pos['pv'],spread=pos['spread'],entry_bar=pos['bar'],entry_ts=pos['entry_ts'],exit_price=exit_p,exit_ts=ts_now,pnl=pnl,gross_pnl=gross,cost=cost,commission=pos['lot']*commission,exit_reason=reason,is_win=(pnl>0),session=get_session(ts_now),entry_hour=pos['entry_ts'].hour,year=pos['entry_ts'].year,month=pos['entry_ts'].strftime('%Y-%m')))
            if not closed and tr==1 and bar_lo<=sl: _close('SL',sl)
            elif not closed and tr==-1 and bar_hi>=sl: _close('SL',sl)
            if not closed and tr==1 and bar_hi>=tp: _close('TP',tp)
            elif not closed and tr==-1 and bar_lo<=tp: _close('TP',tp)
            if not closed and not _igs(ref['ts'][i]):
                ep=bar_cl-(pos['spread']*0.5*spread_m+slp_side)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5*spread_m+slp_side)*pos['pip']
                _close('SC',ep)
            if not closed and (i-pos['bar'])>=50:
                ep=bar_cl-(pos['spread']*0.5*spread_m+slp_side)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5*spread_m+slp_side)*pos['pip']
                _close('MH',ep)
            if not closed: remaining.append(pos)
        open_pos = remaining
        bal=max(bal,1.0)
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd
        if block_entries: continue
        if not _igs(ts_now) or len(open_pos)>=max_conc: continue
        for pair in PAIRS:
            if len(open_pos)>=max_conc: break
            if any(p['pair']==pair for p in open_pos): continue
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_['n']: continue
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            tr=1 if c_val>ev else -1
            if tr==1 and c_val<e5*0.998: continue
            if tr==-1 and c_val>e5*1.002: continue
            if tr==1:
                if not (c_val<ev*1.005 and c_val>ev*0.995): continue
                if max(pd_['h'][max(0,i-20):i])<=c_val*1.002: continue
            else:
                if not (c_val>ev*0.995 and c_val<ev*1.005): continue
                if min(pd_['lo'][max(0,i-20):i])>=c_val*0.998: continue
            d_ts=pd_['daily'].index.asof(ts_now)
            if d_ts not in pd_['daily'].index: continue
            dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
            if tr==1 and not dg: continue
            if tr==-1 and dg: continue
            pip=pd_['pip']; sl=ev*(1-0.005) if tr==1 else ev*(1+0.005)
            sl_dist=abs(c_val-sl)
            if sl_dist<2*pip: continue
            tp=c_val+sl_dist*rr if tr==1 else c_val-sl_dist*rr
            ef=c_val+(pd_['spread']*0.5*spread_m+slp_side)*pip if tr==1 else c_val-(pd_['spread']*0.5*spread_m+slp_side)*pip
            sz=ps.compute_position_size(pair=pair,side='BUY' if tr==1 else 'SELL',entry_price=ef,sl_price=sl,account_balance_usd=bal,risk_pct=risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
            if not sz.ok: continue
            open_pos.append({'pair':pair,'trend':tr,'entry':ef,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'entry_ts':ts_now})
    return trades, mdd, bal


def compute_metrics(trades, label=''):
    if not trades: return None
    pnls = np.array([t.pnl for t in trades])
    w=int(np.sum(pnls>0)); l=int(np.sum(pnls<=0))
    gw=float(np.sum(pnls[pnls>0])); gl=float(np.abs(np.sum(pnls[pnls<=0])))
    monthly_data = defaultdict(lambda: {'pnl':0.0,'trades':0,'wins':0})
    for t in trades:
        monthly_data[t.month]['pnl']+=t.pnl; monthly_data[t.month]['trades']+=1
        if t.pnl>0: monthly_data[t.month]['wins']+=1
    mkeys=sorted(monthly_data.keys()); mrets=[]; prev=ACC; pk=ACC; neg=0
    for mk in mkeys:
        md=monthly_data[mk]; r=md['pnl']/prev*100 if prev>0 else 0
        prev+=md['pnl'];
        if prev>pk: pk=prev
        mrets.append(r)
        if r<0: neg+=1
    mrets=np.array(mrets) if mrets else np.array([0])
    eq=[ACC]
    for t in trades: eq.append(eq[-1]+t.pnl)
    ea=np.array(eq); rpk=np.maximum.accumulate(ea)
    dd=np.where(rpk>0,(rpk-ea)/rpk,0)
    # exits
    ex=defaultdict(int)
    for t in trades: ex[t.exit_reason]+=1
    r={'label':label,'trades':len(trades),'wins':w,'losses':l,
       'win_rate':round(w/(w+l)*100,2) if (w+l)>0 else 0,
       'profit_factor':round(gw/gl,2) if gl>0 else 99,
       'net_pnl':round(float(np.sum(pnls)),2),
       'avg_pnl':round(float(np.mean(pnls)),2),
       'median_pnl':round(float(np.median(pnls)),2),
       'mdd_pct':round(float(np.max(dd))*100,2),
       'mean_dd_pct':round(float(np.mean(dd))*100,2),
       'dd_variance':round(float(np.var(dd,ddof=1))*10000,4) if len(dd)>1 else 0,
       'n_negative_months':neg,'n_months':len(mrets),
       'exits':{k:v for k,v in ex.items()}}
    if len(mrets)>1 and mrets[0]!=0:
        r['monthly_mean']=round(float(np.mean(mrets)),4)
        r['monthly_median']=round(float(np.median(mrets)),4)
        r['monthly_std']=round(float(np.std(mrets,ddof=1)),4)
        r['monthly_variance']=round(float(np.var(mrets,ddof=1)),4)
        r['monthly_min']=round(float(np.min(mrets)),4)
        r['monthly_max']=round(float(np.max(mrets)),4)
        if len(mrets)>=5:
            r['monthly_p5']=round(float(np.percentile(mrets,5)),4)
            r['monthly_p95']=round(float(np.percentile(mrets,95)),4)
            r['monthly_p99']=round(float(np.percentile(mrets,99)),4)
    return r


def classify_regime(pdata, pair, bar_idx):
    pd_=pdata.get(pair)
    if pd_ is None or bar_idx>=pd_['n']:
        return {'vol_regime':'unknown','trend_regime':'unknown'}
    atr=pd_['atr_pct'][bar_idx]
    if np.isnan(atr): atr=0
    valid=pd_['atr_pct'][~np.isnan(pd_['atr_pct'])]
    if len(valid)>0:
        p25=np.percentile(valid,25); p75=np.percentile(valid,75)
        vr='low_vol' if atr<=p25 else ('high_vol' if atr>=p75 else 'mid_vol')
    else: vr='unknown'
    c=pd_['c'][bar_idx]; e=pd_['e200'][bar_idx]
    if np.isnan(e) or e==0: tr_='unknown'
    else:
        d=abs(c-e)/e*100
        tr_='near_ema200' if d<0.1 else ('weak_trend' if d<0.3 else 'strong_trend')
    return {'vol_regime':vr,'trend_regime':tr_}


def add_regimes(trades, pdata):
    for t in trades:
        pd_=pdata.get(t.pair)
        if pd_ is None: t.regime={'vol_regime':'unknown','trend_regime':'unknown'}; continue
        bi=np.searchsorted(pd_['ts'],t.entry_ts)
        if bi>=len(pd_['ts']): bi=len(pd_['ts'])-1
        t.regime=classify_regime(pdata,t.pair,bi)
    return trades


def inv1_time_decay(trades):
    by_yr=defaultdict(list)
    for t in trades: by_yr[t.year].append(t)
    return {yr:compute_metrics(ts,str(yr)) for yr,ts in sorted(by_yr.items()) if compute_metrics(ts,str(yr))}


def inv2_regime(trades):
    vol=defaultdict(list); trend=defaultdict(list)
    for t in trades:
        r=t.regime or {'vol_regime':'unknown','trend_regime':'unknown'}
        vol[r.get('vol_regime','unknown')].append(t)
        trend[r.get('trend_regime','unknown')].append(t)
    return {'by_vol':{k:compute_metrics(v,f'vol:{k}') for k,v in vol.items() if compute_metrics(v)},
            'by_trend':{k:compute_metrics(v,f'trend:{k}') for k,v in trend.items() if compute_metrics(v)}}


def inv3_pairs(trades):
    by_p=defaultdict(list)
    for t in trades: by_p[t.pair].append(t)
    total_pnl=sum(t.pnl for t in trades)
    r={}
    for p,ts in sorted(by_p.items()):
        m=compute_metrics(ts,p)
        if m:
            m['pct_total_pnl']=round(m['net_pnl']/total_pnl*100,2) if total_pnl else 0
            m['pct_trades']=round(m['trades']/len(trades)*100,2)
            r[p]=m
    sorted_p=sorted(r.items(),key=lambda x:x[1]['net_pnl'],reverse=True)
    cum=0; top=[]
    for p,m in sorted_p:
        cum+=m['net_pnl']
        top.append({'pair':p,'pnl':m['net_pnl'],'cum_pct':round(cum/total_pnl*100,2)})
    return {'by_pair':r,'top_contributors':top,'total_pnl':round(total_pnl,2)}


def inv4_sessions(trades):
    by_s=defaultdict(list)
    for t in trades: by_s[t.session].append(t)
    sess={k:compute_metrics(v,f'sess:{k}') for k,v in by_s.items() if compute_metrics(v)}
    by_h=defaultdict(list)
    for t in trades: by_h[t.entry_hour].append(t)
    hrs={h:compute_metrics(v,f'h:{h}') for h,v in sorted(by_h.items()) if compute_metrics(v)}
    return {'by_session':sess,'by_hour':hrs}


def inv5_session_filter(pdata, trades_with, trades_without):
    mw=compute_metrics(trades_with,'with'); mwo=compute_metrics(trades_without,'without')
    # hourly wr for with-filter
    hw={}
    for h in range(24):
        ht=[t for t in trades_with if t.entry_hour==h]
        if ht:
            wr=sum(1 for t in ht if t.pnl>0)/len(ht)*100
            hw[h]={'trades':len(ht),'win_rate':round(wr,1),'avg_pnl':round(float(np.mean([t.pnl for t in ht])),2)}
    return {'with_filter':mw,'without_filter':mwo,'hourly_with_filter':hw}


def inv6_cost_sensitivity(pdata):
    scens=[
        ('baseline',3.5,0.3),('comm_4',4.0,0.3),('comm_5',5.0,0.3),
        ('comm_7',7.0,0.3),('comm_10',10.0,0.3),
        ('slp_0.5',3.5,0.5),('slp_0.8',3.5,0.8),('slp_1.0',3.5,1.0),
        ('slp_1.5',3.5,1.5),('slp_2.0',3.5,2.0),
        ('combined_mod',5.0,1.0),('combined_heavy',7.0,1.5),('combined_extreme',10.0,2.0),
    ]
    r={}
    for label,comm,slp in scens:
        ts,_,_=run_sim_trades(pdata,friction='realistic',commission_override=comm,slippage_override=slp)
        m=compute_metrics(ts,label)
        if m: m['commission']=comm; m['slippage_pip']=slp; r[label]=m
    return r


def inv7_intratrade_dd(pdata, trades):
    adv=[]
    for t in trades:
        pd_=pdata.get(t.pair)
        if pd_ is None: continue
        raw=pd_.get('raw_df')
        if raw is None: continue
        mask=(raw.index>=t.entry_ts)&(raw.index<=t.exit_ts)
        seg=raw[mask]
        if len(seg)<2: continue
        pip=t.pip
        if t.trend==1: adv.append(max(0,(t.entry-seg['low'].min())/pip))
        else: adv.append(max(0,(seg['high'].max()-t.entry)/pip))
    if not adv: return {'note':'No data'}
    a=np.array(adv)
    return {'n':len(a),'mean':round(float(np.mean(a)),2),'median':round(float(np.median(a)),2),
            'p75':round(float(np.percentile(a,75)),2),'p90':round(float(np.percentile(a,90)),2),
            'p95':round(float(np.percentile(a,95)),2),'p99':round(float(np.percentile(a,99)),2),
            'max':round(float(np.max(a)),2),'min':round(float(np.min(a)),2),
            'note':'UPPER BOUND — bar low/high, not tick data'}


def inv8_walkforward(pdata):
    splits=[
        ('2021','2018-01-01','2020-12-31','2021-01-01','2021-12-31'),
        ('2022','2019-01-01','2021-12-31','2022-01-01','2022-12-31'),
        ('2023','2020-01-01','2022-12-31','2023-01-01','2023-12-31'),
        ('2024','2021-01-01','2023-12-31','2024-01-01','2024-12-31'),
        ('2025','2022-01-01','2024-12-31','2025-01-01','2025-12-31'),
        ('2026','2023-01-01','2025-12-31','2026-01-01','2026-07-19'),
    ]
    r={}
    for yr,ts,te,ttste,tte in splits:
        pd_t=load_pair_data(ts,te)
        if pd_t:
            tr,_,_=run_sim_trades(pd_t)
            mt=compute_metrics(tr,f'train_{yr}')
        else: mt=None
        pd_s=load_pair_data(ttste,tte)
        if pd_s:
            tr,_,_=run_sim_trades(pd_s)
            ms=compute_metrics(tr,f'test_{yr}')
        else: ms=None
        r[f'test_{yr}']={'train':mt,'test':ms,'train_period':f'{ts} to {te}','test_period':f'{ttste} to {tte}'}
    return r


def inv9_oos(trades):
    is_t=[t for t in trades if t.year<=2022]
    oos_t=[t for t in trades if t.year>=2023]
    is_m=compute_metrics(is_t,'IS'); oos_m=compute_metrics(oos_t,'OOS')
    deg={}
    if is_m and oos_m:
        for k in ['win_rate','profit_factor','avg_pnl','monthly_mean','monthly_median']:
            iv=is_m.get(k,0); ov=oos_m.get(k,0)
            ch=(ov-iv)/abs(iv)*100 if iv else 0
            deg[k]={'is':iv,'oos':ov,'change_pct':round(ch,1),'direction':'worse' if ov<iv else 'better'}
    return {'is':is_m,'oos':oos_m,'degradation':deg}


def inv10_edge_concentration(trades):
    pnls=np.array([t.pnl for t in trades]); total=float(np.sum(pnls))
    sp=np.sort(pnls)[::-1]; n=len(pnls)
    tc={}
    for p in [1,5,10]:
        k=max(1,int(n*p/100)); s=float(np.sum(sp[:k]))
        tc[f'top_{p}%']={'n':k,'pnl':round(s,2),'pct_total':round(s/total*100,2) if total else 0}
    sa=np.sort(pnls)
    for p in [1,5,10]:
        k=max(1,int(n*p/100)); s=float(np.sum(sa[:k]))
        tc[f'bottom_{p}%']={'n':k,'pnl':round(s,2),'pct_total':round(s/total*100,2) if total else 0}
    mp=defaultdict(float)
    for t in trades: mp[t.month]+=t.pnl
    sm=sorted(mp.items(),key=lambda x:x[1],reverse=True)
    tp=sum(v for _,v in sm)
    mc={}
    for p in [1,5,10]:
        k=max(1,int(len(sm)*p/100)); s=sum(v for _,v in sm[:k])
        mc[f'top_{p}%_months']={'n':k,'pnl':round(s,2),'pct_total':round(s/tp*100,2) if tp else 0}
    yp=defaultdict(float)
    for t in trades: yp[t.year]+=t.pnl
    return {'trade_concentration':tc,'monthly_concentration':mc,'yearly_pnl':{str(y):round(v,2) for y,v in sorted(yp.items())},'total_pnl':round(total,2)}


def inv11_exit_mechanism(trades):
    by_ex=defaultdict(list)
    for t in trades: by_ex[t.exit_reason].append(t)
    return {r:compute_metrics(by_ex.get(r,[]),f'exit:{r}') for r in ['SL','TP','SC','MH','DL']}


def inv12_pair_regime(trades):
    pv=defaultdict(lambda:defaultdict(list)); pt=defaultdict(lambda:defaultdict(list))
    for t in trades:
        r=t.regime or {'vol_regime':'unknown','trend_regime':'unknown'}
        pv[t.pair][r.get('vol_regime','unknown')].append(t)
        pt[t.pair][r.get('trend_regime','unknown')].append(t)
    vi={p:{vr:compute_metrics(ts) for vr,ts in vs.items() if compute_metrics(ts)} for p,vs in sorted(pv.items())}
    ti={p:{tr:compute_metrics(ts) for tr,ts in ts_.items() if compute_metrics(ts)} for p,ts_ in sorted(pt.items())}
    return {'pair_x_vol':vi,'pair_x_trend':ti}


if __name__=='__main__':
    t0=time.time()
    print("="*80)
    print("  MR PHASE 2 FORENSIC ANALYSIS")
    print("="*80)

    print("\n[0] Loading data...")
    pdata=load_pair_data('2018-01-01','2026-07-19')
    print(f"    {len(pdata)} pairs loaded")

    print("\n[B] Baseline simulation (with session filter)...")
    trades,mdd,bal=run_sim_trades(pdata,friction='realistic')
    print(f"    Trades={len(trades)} MDD={mdd*100:.2f}% Final=${bal:,.0f}")
    trades=add_regimes(trades,pdata)

    print("[B] Without session filter...")
    trades_no,mdd_no,bal_no=run_sim_trades(pdata,friction='realistic',session_filter=False)
    print(f"    Trades={len(trades_no)} MDD={mdd_no*100:.2f}%")
    trades_no=add_regimes(trades_no,pdata)

    R={}

    print("\n[1] Time Decay...")
    R['inv1']=inv1_time_decay(trades)

    print("[2] Regime Analysis...")
    R['inv2']=inv2_regime(trades)

    print("[3] Pair Contribution...")
    R['inv3']=inv3_pairs(trades)

    print("[4] Session Contribution...")
    R['inv4']=inv4_sessions(trades)

    print("[5] Session Filter...")
    R['inv5']=inv5_session_filter(pdata,trades,trades_no)

    print("[6] Cost Sensitivity (13 scenarios)...")
    R['inv6']=inv6_cost_sensitivity(pdata)

    print("[7] Intratrade DD...")
    R['inv7']=inv7_intratrade_dd(pdata,trades)

    print("[8] Walk-Forward (6 splits)...")
    R['inv8']=inv8_walkforward(pdata)

    print("[9] OOS Analysis...")
    R['inv9']=inv9_oos(trades)

    print("[10] Edge Concentration...")
    R['inv10']=inv10_edge_concentration(trades)

    print("[11] Exit Mechanism...")
    R['inv11']=inv11_exit_mechanism(trades)

    print("[12] Pair x Regime...")
    R['inv12']=inv12_pair_regime(trades)

    R['baseline']=compute_metrics(trades,'baseline')

    os.makedirs('/root/that/logs/mr_phase2',exist_ok=True)
    with open('/root/that/logs/mr_phase2_metrics.json','w') as f:
        json.dump(R,f,indent=2,default=str)
    print(f"\n  Saved /root/that/logs/mr_phase2_metrics.json")
    print(f"\n[DONE] {time.time()-t0:.1f}s")
