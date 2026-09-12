"""MR Phase 3 Forensic Analysis — Deep degradation decomposition."""
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

@dataclass
class Trade:
    pair:str; trend:int; entry:float; sl:float; tp:float
    lot:float; pip:float; pv:float; spread:float
    entry_bar:int; entry_ts:object
    exit_price:float=0.0; exit_ts:object=None
    pnl:float=0.0; gross_pnl:float=0.0; cost:float=0.0
    commission:float=0.0; exit_reason:str=''; is_win:bool=False
    session:str=''; entry_hour:int=0; year:int=0; month:str=''
    regime:dict=None; day_of_week:int=0
    holding_bars:int=0; max_adverse_pips:float=0.0; max_favorable_pips:float=0.0

def load_pair_data(start, end):
    pdata={}
    for pair in PAIRS:
        pk=pair.replace('/','_')
        try:
            with open(f'/root/data/{pk}.pkl','rb') as f: raw=pickle.load(f)
        except FileNotFoundError: continue
        df=raw.get(pair)
        if df is None: continue
        idx=pd.to_datetime(df.index)
        idx=idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index=idx; df=df[df.index>=start]; df=df[df.index<=end]
        if len(df)<500: continue
        pip=ps.pip_size_for_pair(pair); pv=ps.pip_value_per_lot(pair,SNAP)
        d30=df[['open','high','low','close']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        d4h=df[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        daily=df[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        e200=d4h['close'].ewm(span=200,adjust=False).mean()
        e50=d4h['close'].ewm(span=50,adjust=False).mean()
        tr_s=pd.concat([d30['high']-d30['low'],(d30['high']-d30['close'].shift(1)).abs(),(d30['low']-d30['close'].shift(1)).abs()],axis=1).max(axis=1)
        atr_14=tr_s.rolling(14).mean()
        atr_pct=atr_14/d30['close']*100
        ret_30m=d30['close'].pct_change()
        rv_20=ret_30m.rolling(20).std()*np.sqrt(48)
        pdata[pair]={
            'c':d30['close'].values,'h':d30['high'].values,'lo':d30['low'].values,
            'o':d30['open'].values,'ts':d30.index,'n':len(d30),
            'e200':e200.reindex(d30.index,method='ffill').values,
            'e50':e50.reindex(d30.index,method='ffill').values,
            'daily':daily,'pip':pip,'pv':pv,'spread':SPREAD.get(pair,2.0),
            'atr_pct':atr_pct.reindex(d30.index,method='ffill').values,
            'rv_20':rv_20.reindex(d30.index,method='ffill').values,
            'raw_df':df,
        }
    return pdata

def run_sim(pdata, friction='realistic', commission_override=None, slippage_override=None,
            max_conc=10, rr=2.7, risk=RISK, session_filter=True):
    if friction=='ideal': spread_m=0; slp_side=slippage_override if slippage_override is not None else 0.5
    elif friction=='realistic': spread_m=1; slp_side=slippage_override if slippage_override is not None else 0.3
    else: spread_m=2; slp_side=slippage_override if slippage_override is not None else 1.0
    commission=commission_override if commission_override is not None else 3.50
    ref_pair=max(pdata.keys(),key=lambda p:pdata[p]['n'])
    ref=pdata[ref_pair]; n_bars=ref['n']
    bal=ACC; peak=ACC; mdd=0; open_pos=[]; trades=[]
    daily_sb=ACC; daily_d=None
    def _igs(ts): return True if not session_filter else igs(ts)
    for i in range(250,n_bars-1):
        ts_now=ref['ts'][i]; today=ts_now.date()
        if daily_d!=today: daily_d=today; daily_sb=bal
        if daily_sb>0 and (daily_sb-bal)/daily_sb>=0.05:
            for pos in open_pos:
                pd_=pdata.get(pos['pair'])
                if pd_ is None or i>=pd_['n']: continue
                ep=pd_['c'][i]-(pos['spread']*0.5*spread_m+slp_side)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5*spread_m+slp_side)*pos['pip']
                gross=(ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']
                cost=pos['lot']*commission; pnl=gross-cost; bal+=pnl
                trades.append(Trade(pair=pos['pair'],trend=pos['trend'],entry=pos['entry'],sl=pos['sl'],tp=pos['tp'],lot=pos['lot'],pip=pos['pip'],pv=pos['pv'],spread=pos['spread'],entry_bar=pos['bar'],entry_ts=pos['entry_ts'],exit_price=ep,exit_ts=ts_now,pnl=pnl,gross_pnl=gross,cost=cost,commission=pos['lot']*commission,exit_reason='DL',is_win=(pnl>0),session=get_session(ts_now),entry_hour=pos['entry_ts'].hour,year=pos['entry_ts'].year,month=pos['entry_ts'].strftime('%Y-%m'),day_of_week=pos['entry_ts'].dayofweek,holding_bars=i-pos['bar']))
            open_pos.clear(); continue
        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_lo=pd_['lo'][i]; bar_hi=pd_['h'][i]; bar_cl=pd_['c'][i]
            tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False
            def _close(reason,exit_p):
                nonlocal closed,bal
                if tr==1: gross=(exit_p-pos['entry'])/pos['pip']*pos['pv']*pos['lot']
                else: gross=(pos['entry']-exit_p)/pos['pip']*pos['pv']*pos['lot']
                cost=pos['lot']*commission; pnl=gross-cost; bal+=pnl; closed=True
                trades.append(Trade(pair=pos['pair'],trend=tr,entry=pos['entry'],sl=sl,tp=tp,lot=pos['lot'],pip=pos['pip'],pv=pos['pv'],spread=pos['spread'],entry_bar=pos['bar'],entry_ts=pos['entry_ts'],exit_price=exit_p,exit_ts=ts_now,pnl=pnl,gross_pnl=gross,cost=cost,commission=pos['lot']*commission,exit_reason=reason,is_win=(pnl>0),session=get_session(ts_now),entry_hour=pos['entry_ts'].hour,year=pos['entry_ts'].year,month=pos['entry_ts'].strftime('%Y-%m'),day_of_week=pos['entry_ts'].dayofweek,holding_bars=i-pos['bar']))
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
        open_pos=remaining
        bal=max(bal,1.0)
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd
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

def classify_regime(pdata,pair,bar_idx):
    pd_=pdata.get(pair)
    if pd_ is None or bar_idx>=pd_['n']:
        return {'vol_regime':'unknown','trend_regime':'unknown','atr_pct':0,'rv':0}
    atr=pd_['atr_pct'][bar_idx]
    if np.isnan(atr): atr=0
    rv=pd_['rv_20'][bar_idx]
    if np.isnan(rv): rv=0
    valid=pd_['atr_pct'][~np.isnan(pd_['atr_pct'])]
    if len(valid)>0:
        p25=np.percentile(valid,25); p75=np.percentile(valid,75); p95=np.percentile(valid,95)
        if atr<=p25: vr='low_vol'
        elif atr>=p95: vr='extreme_vol'
        elif atr>=p75: vr='high_vol'
        else: vr='mid_vol'
    else: vr='unknown'
    c=pd_['c'][bar_idx]; e=pd_['e200'][bar_idx]
    if np.isnan(e) or e==0: tr_='unknown'
    else:
        d=abs(c-e)/e*100
        tr_='near_ema200' if d<0.1 else ('weak_trend' if d<0.3 else 'strong_trend')
    return {'vol_regime':vr,'trend_regime':tr_,'atr_pct':round(atr,6),'rv':round(rv,6)}

def add_regimes_and_mfe_mae(trades,pdata):
    for t in trades:
        pd_=pdata.get(t.pair)
        if pd_ is None:
            t.regime={'vol_regime':'unknown','trend_regime':'unknown'}; continue
        bi=np.searchsorted(pd_['ts'],t.entry_ts)
        if bi>=len(pd_['ts']): bi=len(pd_['ts'])-1
        t.regime=classify_regime(pdata,t.pair,bi)
        # MFE/MAE estimation from minute data
        raw=pd_.get('raw_df')
        if raw is not None and t.exit_ts is not None:
            mask=(raw.index>=t.entry_ts)&(raw.index<=t.exit_ts)
            seg=raw[mask]
            if len(seg)>=2:
                if t.trend==1:
                    t.max_favorable_pips=(seg['high'].max()-t.entry)/t.pip
                    t.max_adverse_pips=(t.entry-seg['low'].min())/t.pip
                else:
                    t.max_favorable_pips=(t.entry-seg['low'].min())/t.pip
                    t.max_adverse_pips=(seg['high'].max()-t.entry)/t.pip
    return trades

def m(label=''):
    """Compute comprehensive metrics from trade list."""
    def _m(trades,lbl=''):
        if not trades: return None
        pnls=np.array([t.pnl for t in trades])
        w=int(np.sum(pnls>0)); l_=int(np.sum(pnls<=0))
        gw=float(np.sum(pnls[pnls>0])); gl=float(np.abs(np.sum(pnls[pnls<=0])))
        # Monthly
        md=defaultdict(lambda:{'pnl':0.0,'trades':0,'wins':0})
        for t in trades:
            md[t.month]['pnl']+=t.pnl; md[t.month]['trades']+=1
            if t.pnl>0: md[t.month]['wins']+=1
        mk=sorted(md.keys()); mrets=[]; prev=ACC; pk=ACC; neg=0
        for k in mk:
            r=md[k]['pnl']/prev*100 if prev>0 else 0; prev+=md[k]['pnl']
            if prev>pk: pk=prev
            mrets.append(r)
            if r<0: neg+=1
        mrets=np.array(mrets) if mrets else np.array([0])
        # Equity DD
        eq=[ACC]
        for t in trades: eq.append(eq[-1]+t.pnl)
        ea=np.array(eq); rpk=np.maximum.accumulate(ea)
        dd=np.where(rpk>0,(rpk-ea)/rpk,0)
        # Holding time
        hold=np.array([t.holding_bars for t in trades]) if trades else np.array([0])
        # Exits
        ex=defaultdict(int)
        for t in trades: ex[t.exit_reason]+=1
        r={'label':lbl,'trades':len(trades),'wins':w,'losses':l_,
           'win_rate':round(w/(w+l_)*100,2) if (w+l_)>0 else 0,
           'profit_factor':round(gw/gl,2) if gl>0 else 99,
           'net_pnl':round(float(np.sum(pnls)),2),
           'avg_pnl':round(float(np.mean(pnls)),2),
           'median_pnl':round(float(np.median(pnls)),2),
           'std_pnl':round(float(np.std(pnls,ddof=1)),2) if len(pnls)>1 else 0,
           'var_pnl':round(float(np.var(pnls,ddof=1)),2) if len(pnls)>1 else 0,
           'mdd_pct':round(float(np.max(dd))*100,2),
           'mean_dd_pct':round(float(np.mean(dd))*100,2),
           'dd_var':round(float(np.var(dd,ddof=1))*10000,4) if len(dd)>1 else 0,
           'n_negative_months':neg,'n_months':len(mrets),
           'avg_holding_bars':round(float(np.mean(hold)),1),
           'median_holding_bars':round(float(np.median(hold)),1),
           'exits':{k:v for k,v in ex.items()},
           'sc_pct':round(ex.get('SC',0)/len(trades)*100,1) if trades else 0,
           'sl_pct':round(ex.get('SL',0)/len(trades)*100,1) if trades else 0,
           'tp_pct':round(ex.get('TP',0)/len(trades)*100,1) if trades else 0}
        if len(mrets)>1:
            r['monthly_mean']=round(float(np.mean(mrets)),4)
            r['monthly_median']=round(float(np.median(mrets)),4)
            r['monthly_std']=round(float(np.std(mrets,ddof=1)),4)
            r['monthly_var']=round(float(np.var(mrets,ddof=1)),4)
            r['monthly_min']=round(float(np.min(mrets)),4)
            r['monthly_max']=round(float(np.max(mrets)),4)
            r['monthly_skew']=round(float(pd.Series(mrets).skew()),4)
            r['monthly_kurt']=round(float(pd.Series(mrets).kurtosis()),4)
            for p in [1,5,10,25,75,90,95,99]:
                r[f'monthly_p{p}']=round(float(np.percentile(mrets,p)),4)
        # MAE/MFE
        mae=np.array([t.max_adverse_pips for t in trades if t.max_adverse_pips>0])
        mfe=np.array([t.max_favorable_pips for t in trades if t.max_favorable_pips>0])
        if len(mae)>0:
            r['mae_mean']=round(float(np.mean(mae)),2)
            r['mae_median']=round(float(np.median(mae)),2)
            r['mae_p95']=round(float(np.percentile(mae,95)),2)
            r['mae_max']=round(float(np.max(mae)),2)
        if len(mfe)>0:
            r['mfe_mean']=round(float(np.mean(mfe)),2)
            r['mfe_median']=round(float(np.median(mfe)),2)
            r['mfe_p95']=round(float(np.percentile(mfe,95)),2)
        return r
    return _m

def _compute(trades, label=''):
    return m()(trades, label)

# ═══════════════════════════════════════════════════════════════
# PHASE 3A: METHODOLOGY AUDIT
# ═══════════════════════════════════════════════════════════════
def phase3a_audit():
    return {
        'walk_forward_methodology': {
            'description': 'Same fixed-parameter strategy run on separate train/test data slices',
            'train_test_overlap': 'NONE — separate load_pair_data() calls',
            'parameter_optimization': 'NONE — parameters are hardcoded constants',
            'data_leakage': 'NONE — train and test use non-overlapping date ranges',
            'lookahead_bias': 'NONE — EMA/moving averages computed within each window independently',
            'survivorship_bias': 'PRESENT — all 20 pairs loaded from start; if a pair was delisted it would be excluded retroactively',
            'multiple_testing': '6 tests performed; no correction applied; but no optimization means this is less concerning',
            'key_finding': 'The walk-forward is methodologically clean but does NOT prove robustness — it proves the fixed strategy happened to work in each 1-year test window',
            'critical_caveat': 'Train/test EMAs are recomputed independently; the EMA200 in test_2021 is NOT the same as EMA200 in train_2018-2020',
            'verdict': 'PASS with caveat: walk-forward is clean but does not constitute validation of optimized parameters (no optimization occurred)',
        }
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 3B: TIME DECAY DECOMPOSITION
# ═══════════════════════════════════════════════════════════════
def phase3b_time_decay(trades):
    by_yr=defaultdict(list)
    for t in trades: by_yr[t.year].append(t)
    return {yr:_compute(ts,str(yr)) for yr,ts in sorted(by_yr.items())}

# ═══════════════════════════════════════════════════════════════
# PHASE 3C: SESSION DECOMPOSITION
# ═══════════════════════════════════════════════════════════════
def phase3c_session(trades):
    # By session
    by_s=defaultdict(list)
    for t in trades: by_s[t.session].append(t)
    sess={k:_compute(v,f'sess:{k}') for k,v in by_s.items()}
    # By day of week
    by_dow=defaultdict(list)
    for t in trades: by_dow[t.day_of_week].append(t)
    dow_names={0:'Monday',1:'Tuesday',2:'Wednesday',3:'Thursday',4:'Friday'}
    dow={dow_names.get(d,f'd{d}'):_compute(v,f'd:{d}') for d,v in sorted(by_dow.items())}
    # By hour
    by_h=defaultdict(list)
    for t in trades: by_h[t.entry_hour].append(t)
    hrs={h:_compute(v,f'h:{h}') for h,v in sorted(by_h.items())}
    # IS vs OOS by session
    is_t=[t for t in trades if t.year<=2022]
    oos_t=[t for t in trades if t.year>=2023]
    sess_is={}; sess_oos={}
    for s in ['london_only','ny_only','overlap']:
        is_st=[t for t in is_t if t.session==s]
        oos_st=[t for t in oos_t if t.session==s]
        sess_is[s]=_compute(is_st,f'is_{s}')
        sess_oos[s]=_compute(oos_st,f'oos_{s}')
    return {'by_session':sess,'by_day_of_week':dow,'by_hour':hrs,
            'is_by_session':sess_is,'oos_by_session':sess_oos}

# ═══════════════════════════════════════════════════════════════
# PHASE 3D: VOLATILITY REGIME
# ═══════════════════════════════════════════════════════════════
def phase3d_vol_regime(trades):
    vol=defaultdict(list)
    for t in trades:
        vr=(t.regime or{}).get('vol_regime','unknown')
        vol[vr].append(t)
    r={k:_compute(v,f'vol:{k}') for k,v in vol.items()}
    # Compare IS vs OOS regime distributions
    is_t=[t for t in trades if t.year<=2022]
    oos_t=[t for t in trades if t.year>=2023]
    is_vol=defaultdict(int); oos_vol=defaultdict(int)
    for t in is_t: is_vol[(t.regime or{}).get('vol_regime','unknown')]+=1
    for t in oos_t: oos_vol[(t.regime or{}).get('vol_regime','unknown')]+=1
    is_total=len(is_t); oos_total=len(oos_t)
    dist_compare={}
    for vr in set(list(is_vol.keys())+list(oos_vol.keys())):
        is_pct=is_vol[vr]/is_total*100 if is_total else 0
        oos_pct=oos_vol[vr]/oos_total*100 if oos_total else 0
        dist_compare[vr]={'is_pct':round(is_pct,1),'oos_pct':round(oos_pct,1),'change_pp':round(oos_pct-is_pct,1)}
    return {'by_regime':r,'regime_distribution':dist_compare}

# ═══════════════════════════════════════════════════════════════
# PHASE 3E: PAIR-BY-PAIR DECAY
# ═══════════════════════════════════════════════════════════════
def phase3e_pair_decay(trades):
    by_pair_yr=defaultdict(lambda:defaultdict(list))
    for t in trades: by_pair_yr[t.pair][t.year].append(t)
    # Full period
    full={pair:_compute(ts,pair) for pair,ts in {p:sum((by_pair_yr[p][y] for y in by_pair_yr[p]),[]) for p in by_pair_yr}.items()}
    # Yearly by pair
    yearly={}
    for pair in sorted(by_pair_yr.keys()):
        yearly[pair]={yr:_compute(ts,f'{pair}_{yr}') for yr,ts in sorted(by_pair_yr[pair].items())}
    # Classify pairs
    classification={}
    for pair in full:
        if full[pair] is None: continue
        yrs=list(yearly.get(pair,{}).keys())
        neg_yrs=[y for y in yrs if yearly[pair][y] and yearly[pair][y]['net_pnl']<0] if yearly.get(pair) else []
        pos_yrs=[y for y in yrs if yearly[pair][y] and yearly[pair][y]['net_pnl']>0] if yearly.get(pair) else []
        classification[pair]={
            'total_pnl':full[pair]['net_pnl'],
            'n_positive_years':len(pos_yrs),
            'n_negative_years':len(neg_yrs),
            'positive_years':pos_yrs,
            'negative_years':neg_yrs,
        }
    return {'full_period':full,'yearly':yearly,'classification':classification}

# ═══════════════════════════════════════════════════════════════
# PHASE 3F: TRADE DISTRIBUTION / EDGE CONCENTRATION
# ═══════════════════════════════════════════════════════════════
def phase3f_edge_concentration(trades):
    pnls=np.array([t.pnl for t in trades]); total=float(np.sum(pnls))
    n=len(pnls); sp=np.sort(pnls)[::-1]; sa=np.sort(pnls)
    tc={}
    for p in [1,5,10,25,50,75,90,95,99]:
        k=max(1,int(n*p/100))
        top_k=float(np.sum(sp[:k])); bot_k=float(np.sum(sa[:k]))
        tc[f'top_{p}%']={'n':k,'pnl':round(top_k,2),'pct':round(top_k/total*100,2) if total else 0}
        tc[f'bottom_{p}%']={'n':k,'pnl':round(bot_k,2),'pct':round(bot_k/total*100,2) if total else 0}
    # By year
    by_yr=defaultdict(list)
    for t in trades: by_yr[t.year].append(t)
    yr_tc={}
    for yr,ts in sorted(by_yr.items()):
        ypnls=np.array([t.pnl for t in ts]); yt=float(np.sum(ypnls))
        yn=len(ypnls); ysp=np.sort(ypnls)[::-1]
        yr_tc[yr]={}
        for p in [1,5,10]:
            k=max(1,int(yn*p/100)); s=float(np.sum(ysp[:k]))
            yr_tc[yr][f'top_{p}%']={'n':k,'pnl':round(s,2),'pct':round(s/yt*100,2) if yt else 0}
    # Robustness: exclude top trades
    robustness={}
    for cutoff_pct in [1,5,10]:
        k=int(n*cutoff_pct/100)
        reduced=trades.copy()
        # Remove top k trades by PnL
        sorted_idx=np.argsort(pnls)[::-1][:k]
        reduced=[t for i,t in enumerate(trades) if i not in sorted_idx]
        m_reduced=_compute(reduced,f'excl_top{cutoff_pct}')
        robustness[f'excl_top_{cutoff_pct}%']={'trades_removed':k,'remaining':len(reduced)}
        if m_reduced:
            robustness[f'excl_top_{cutoff_pct}%'].update({
                'pf':m_reduced['profit_factor'],'wr':m_reduced['win_rate'],
                'net_pnl':m_reduced['net_pnl'],'mdd':m_reduced['mdd_pct'],
                'avg_pnl':m_reduced['avg_pnl']
            })
    return {'trade_concentration':tc,'yearly_concentration':yr_tc,'robustness_after_removal':robustness}

# ═══════════════════════════════════════════════════════════════
# PHASE 3G: MONTHLY RETURN STABILITY
# ═══════════════════════════════════════════════════════════════
def phase3g_monthly_stability(trades):
    md=defaultdict(lambda:{'pnl':0.0,'trades':0})
    for t in trades: md[t.month]['pnl']+=t.pnl; md[t.month]['trades']+=1
    mk=sorted(md.keys()); prev=ACC
    monthly_rets=[]
    for k in mk:
        r=md[k]['pnl']/prev*100 if prev>0 else 0; prev+=md[k]['pnl']
        monthly_rets.append({'month':k,'return_pct':round(r,4),'pnl':round(md[k]['pnl'],2),'trades':md[k]['trades']})
    rets=np.array([x['return_pct'] for x in monthly_rets])
    # Full period stats
    stats={'n':len(rets),'mean':round(float(np.mean(rets)),4),'median':round(float(np.median(rets)),4),
           'std':round(float(np.std(rets,ddof=1)),4) if len(rets)>1 else 0,
           'var':round(float(np.var(rets,ddof=1)),4) if len(rets)>1 else 0,
           'min':round(float(np.min(rets)),4),'max':round(float(np.max(rets)),4),
           'skew':round(float(pd.Series(rets).skew()),4),'kurt':round(float(pd.Series(rets).kurtosis()),4)}
    for p in [1,5,10,25,75,90,95,99]:
        stats[f'p{p}']=round(float(np.percentile(rets,p)),4)
    # By sub-period
    periods={'2018_2020':(2018,2020),'2021_2022':(2021,2022),'2023_2024':(2023,2024),'2025_2026':(2025,2026)}
    sub_stats={}
    for lbl,(y1,y2) in periods.items():
        sr=[x['return_pct'] for x in monthly_rets if y1<=int(x['month'][:4])<=y2]
        if len(sr)>1:
            sa=np.array(sr)
            sub_stats[lbl]={'n':len(sa),'mean':round(float(np.mean(sa)),4),'median':round(float(np.median(sa)),4),
                'std':round(float(np.std(sa,ddof=1)),4),'min':round(float(np.min(sa)),4),'max':round(float(np.max(sa)),4),
                'skew':round(float(pd.Series(sa).skew()),4),'kurt':round(float(pd.Series(sa).kurtosis()),4)}
    return {'full_period':stats,'sub_periods':sub_stats,'monthly_returns':monthly_rets}

# ═══════════════════════════════════════════════════════════════
# PHASE 3H: DRAWDOWN STABILITY
# ═══════════════════════════════════════════════════════════════
def phase3h_drawdown(trades):
    eq=[ACC]
    for t in trades: eq.append(eq[-1]+t.pnl)
    ea=np.array(eq); rpk=np.maximum.accumulate(ea)
    dd=np.where(rpk>0,(rpk-ea)/rpk,0)
    # DD episodes
    episodes=[]; cur_start=None; cur_len=0
    for i,d in enumerate(dd):
        if d>0:
            if cur_start is None: cur_start=i
            cur_len+=1
        else:
            if cur_len>0:
                episodes.append({'start':cur_start,'length':cur_len,'max_dd':float(np.max(dd[cur_start:cur_start+cur_len]))})
                cur_start=None; cur_len=0
    if cur_len>0: episodes.append({'start':cur_start,'length':cur_len,'max_dd':float(np.max(dd[cur_start:cur_start+cur_len]))})
    dur=np.array([e['length'] for e in episodes]) if episodes else np.array([0])
    # By year
    by_yr=defaultdict(list)
    for t in trades: by_yr[t.year].append(t)
    yr_dd={}
    for yr,ts in sorted(by_yr.items()):
        eq_=[ACC]
        for t in ts: eq_.append(eq_[-1]+t.pnl)
        ea_=np.array(eq_); rpk_=np.maximum.accumulate(ea_)
        dd_=np.where(rpk_>0,(rpk_-ea_)/rpk_,0)
        yr_dd[yr]={'max_dd':round(float(np.max(dd_))*100,2),'mean_dd':round(float(np.mean(dd_))*100,2),
                   'dd_var':round(float(np.var(dd_,ddof=1))*10000,4) if len(dd_)>1 else 0,
                   'p95_dd':round(float(np.percentile(dd_,95))*100,2) if len(dd_)>0 else 0}
    return {
        'max_dd':round(float(np.max(dd))*100,2),
        'mean_dd':round(float(np.mean(dd))*100,2),
        'median_dd':round(float(np.median(dd))*100,2),
        'std_dd':round(float(np.std(dd,ddof=1))*100,2) if len(dd)>1 else 0,
        'dd_var':round(float(np.var(dd,ddof=1))*10000,4) if len(dd)>1 else 0,
        'p75_dd':round(float(np.percentile(dd,75))*100,2),
        'p90_dd':round(float(np.percentile(dd,90))*100,2),
        'p95_dd':round(float(np.percentile(dd,95))*100,2),
        'p99_dd':round(float(np.percentile(dd,99))*100,2),
        'n_episodes':len(episodes),
        'avg_duration':round(float(np.mean(dur)),1),
        'max_duration':int(np.max(dur)),
        'by_year':yr_dd,
        'note':'Measured at trade-close resolution only. True intraday DD is not captured.',
    }

# ═══════════════════════════════════════════════════════════════
# PHASE 3I: COST ROBUSTNESS GRID
# ═══════════════════════════════════════════════════════════════
def phase3i_cost_grid(pdata):
    commissions=[3.5,4.0,5.0]
    slippages=[0.1,0.3,0.5,0.75,1.0,1.25,1.5,2.0]
    grid={}
    for comm in commissions:
        for slp in slippages:
            key=f'c{comm}_s{slp}'
            ts,_,_=run_sim(pdata,friction='realistic',commission_override=comm,slippage_override=slp)
            if ts:
                r=_compute(ts,key)
                if r: r['commission']=comm; r['slippage']=slp; grid[key]=r
    # Find breakpoints
    breakpoints={'pf_below_1.0':[],'pf_below_1.2':[],'pf_below_1.5':[]}
    for k,r in grid.items():
        pf=r['profit_factor']
        if pf<1.0: breakpoints['pf_below_1.0'].append(f"c{r['commission']}_s{r['slippage']}")
        if pf<1.2: breakpoints['pf_below_1.2'].append(f"c{r['commission']}_s{r['slippage']}")
        if pf<1.5: breakpoints['pf_below_1.5'].append(f"c{r['commission']}_s{r['slippage']}")
    return {'grid':grid,'breakpoints':breakpoints}

# ═══════════════════════════════════════════════════════════════
# PHASE 3J: FILTER INVESTIGATION
# ═══════════════════════════════════════════════════════════════
def phase3j_filter(pdata, trades_with):
    # Without session filter
    trades_no,_,_=run_sim(pdata,friction='realistic',session_filter=False)
    m_with=_compute(trades_with,'with')
    m_without=_compute(trades_no,'without')
    # Analyze what hours are added without filter
    no_hours=defaultdict(int)
    for t in trades_no: no_hours[t.entry_hour]+=1
    with_hours=defaultdict(int)
    for t in trades_with: with_hours[t.entry_hour]+=1
    added={h:no_hours[h]-with_hours.get(h,0) for h in range(24)}
    # Performance by hour for trades OUTSIDE session filter
    outside_trades=[t for t in trades_no if not igs(t.entry_ts)]
    outside_m=_compute(outside_trades,'outside_session') if outside_trades else None
    return {'with':m_with,'without':m_without,'added_by_hour':dict(added),
            'outside_session_performance':outside_m,
            'note':'Cannot test news filter (no data), spread filter (cost not filter), P95/P99 slippage (no empirical data)'}

# ═══════════════════════════════════════════════════════════════
# PHASE 3K: CONDITIONAL EDGE
# ═══════════════════════════════════════════════════════════════
def phase3k_conditional_edge(trades):
    # Key combinations: vol x session, vol x pair, session x pair
    # Only economically motivated combinations
    combos=defaultdict(list)
    for t in trades:
        vr=(t.regime or{}).get('vol_regime','unknown')
        key=f"{vr}|{t.session}"
        combos[key].append(t)
    combo_results={}
    for k,ts in combos.items():
        r=_compute(ts,k)
        if r and r['trades']>=30:  # minimum trade count
            r['years']=sorted(set(t.year for t in ts))
            r['n_years']=len(r['years'])
            r['worst_year_pnl']=min((t.pnl for t in ts),default=0)
            combo_results[k]=r
    # Filter for conditions present in >=4 years
    stable={k:v for k,v in combo_results.items() if v.get('n_years',0)>=4}
    # Pair x vol (only for pairs with enough data)
    pair_vol=defaultdict(lambda:defaultdict(list))
    for t in trades:
        vr=(t.regime or{}).get('vol_regime','unknown')
        pair_vol[t.pair][vr].append(t)
    pv_results={}
    for pair in sorted(pair_vol.keys()):
        for vr in sorted(pair_vol[pair].keys()):
            ts=pair_vol[pair][vr]
            if len(ts)>=20:
                r=_compute(ts,f'{pair}|{vr}')
                if r:
                    r['years']=sorted(set(t.year for t in ts))
                    r['n_years']=len(r['years'])
                    pv_results[f'{pair}|{vr}']=r
    return {'session_x_vol':combo_results,'stable_conditions':stable,'pair_x_vol':pv_results}

# ═══════════════════════════════════════════════════════════════
# PHASE 3L: STATISTICAL SIGNIFICANCE
# ═══════════════════════════════════════════════════════════════
def phase3l_significance(trades):
    pnls=np.array([t.pnl for t in trades])
    # Bootstrap win rate
    n_boot=10000; wr_samples=[]
    for _ in range(n_boot):
        s=np.random.choice(pnls,size=len(pnls),replace=True)
        wr_samples.append(float(np.sum(s>0)/len(s)*100))
    wr_ci=np.percentile(wr_samples,[2.5,97.5])
    # Bootstrap mean trade
    mt_samples=[]
    for _ in range(n_boot):
        s=np.random.choice(pnls,size=len(pnls),replace=True)
        mt_samples.append(float(np.mean(s)))
    mt_ci=np.percentile(mt_samples,[2.5,97.5])
    # Bootstrap PF
    pf_samples=[]
    for _ in range(n_boot):
        s=np.random.choice(pnls,size=len(pnls),replace=True)
        gw=float(np.sum(s[s>0])) if np.any(s>0) else 0
        gl=float(np.abs(np.sum(s[s<=0]))) if np.any(s<=0) else 1
        pf_samples.append(gw/gl if gl>0 else 99)
    pf_ci=np.percentile(pf_samples,[2.5,97.5])
    # Monthly return bootstrap
    md=defaultdict(float)
    for t in trades: md[t.month]+=t.pnl
    monthly_pnls=np.array(list(md.values()))
    mr_samples=[]
    for _ in range(n_boot):
        s=np.random.choice(monthly_pnls,size=len(monthly_pnls),replace=True)
        mr_samples.append(float(np.mean(s)/ACC*100))
    mr_ci=np.percentile(mr_samples,[2.5,97.5])
    # Sign test: is median trade return > 0?
    median_trade=float(np.median(pnls))
    n_pos=int(np.sum(pnls>median_trade))
    n_neg=int(np.sum(pnls<median_trade))
    return {
        'win_rate':{
            'point':round(float(np.mean(pnls>0)*100),2),
            'ci_95':round(float(wr_ci[0]),2), 'ci_95_upper':round(float(wr_ci[1]),2),
            'significant':wr_ci[0]>50,
        },
        'mean_trade':{
            'point':round(float(np.mean(pnls)),2),
            'ci_95':round(float(mt_ci[0]),2), 'ci_95_upper':round(float(mt_ci[1]),2),
            'significant':mt_ci[0]>0,
        },
        'profit_factor':{
            'point':round(float(np.sum(pnls[pnls>0])/np.abs(np.sum(pnls[pnls<=0]))),2) if np.any(pnls<=0) else 99,
            'ci_95':round(float(pf_ci[0]),2), 'ci_95_upper':round(float(pf_ci[1]),2),
            'significant':pf_ci[0]>1.0,
        },
        'monthly_return':{
            'point':round(float(np.mean(monthly_pnls)/ACC*100),4),
            'ci_95':round(float(mr_ci[0]),4), 'ci_95_upper':round(float(mr_ci[1]),4),
            'significant':mr_ci[0]>0,
        },
        'n_bootstrap':n_boot,
    }

# ═══════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════
if __name__=='__main__':
    t0=time.time()
    print("="*80)
    print("  MR PHASE 3 FORENSIC ANALYSIS")
    print("="*80)

    print("\n[0] Loading data...")
    pdata=load_pair_data('2018-01-01','2026-07-19')
    print(f"    {len(pdata)} pairs")

    print("\n[B] Baseline simulation...")
    trades,mdd,bal=run_sim(pdata,friction='realistic')
    print(f"    Trades={len(trades)} MDD={mdd*100:.2f}%")
    trades=add_regimes_and_mfe_mae(trades,pdata)

    R={}

    print("\n[3A] Methodology audit...")
    R['audit']=phase3a_audit()

    print("[3B] Time decay decomposition...")
    R['time_decay']=phase3b_time_decay(trades)

    print("[3C] Session decomposition...")
    R['session']=phase3c_session(trades)

    print("[3D] Volatility regime...")
    R['vol_regime']=phase3d_vol_regime(trades)

    print("[3E] Pair-by-pair decay...")
    R['pair_decay']=phase3e_pair_decay(trades)

    print("[3F] Edge concentration...")
    R['edge_concentration']=phase3f_edge_concentration(trades)

    print("[3G] Monthly stability...")
    R['monthly_stability']=phase3g_monthly_stability(trades)

    print("[3H] Drawdown stability...")
    R['drawdown']=phase3h_drawdown(trades)

    print("[3I] Cost grid...")
    R['cost_grid']=phase3i_cost_grid(pdata)

    print("[3J] Filter investigation...")
    R['filter']=phase3j_filter(pdata,trades)

    print("[3K] Conditional edge...")
    R['conditional_edge']=phase3k_conditional_edge(trades)

    print("[3L] Statistical significance...")
    R['significance']=phase3l_significance(trades)

    R['baseline']=_compute(trades,'baseline_full')

    os.makedirs('/root/that/logs/mr_phase3',exist_ok=True)
    with open('/root/that/logs/mr_phase3_metrics.json','w') as f:
        json.dump(R,f,indent=2,default=str)
    print(f"\n  Saved /root/that/logs/mr_phase3_metrics.json")
    print(f"\n[DONE] {time.time()-t0:.1f}s")
