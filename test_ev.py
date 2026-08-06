"""
Realistic EV — FIXED sizing on $2,500 account, no compounding.
EV = (WR × AvgWin$) + ((1-WR) × AvgLoss$)
"""
import pickle, numpy as np, pandas as pd, time, sys
sys.path.insert(0,'/root')
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}
MR_RISK=0.035; MR_RR=2.2; TF_RISK=0.022; BREAKOUT_ZONE=0.005
TRAIL_ATR_MULT=2.5; TF_MAX_HOLD=100; TF_MIN_HOLD=8; TF_TIME_STOP=30
CORR_THRESHOLD=0.85; MAX_SAME_CURRENCY=2

def igs(ts, sessions=SESSIONS):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in sessions.items():
        if s2<=h<e: return True
    return False

def check_currency_overlap(open_positions, new_pair):
    nb,nq = new_pair.split('/')
    cc={}
    for p in open_positions:
        b,q=p['pair'].split('/')
        cc[b]=cc.get(b,0)+1; cc[q]=cc.get(q,0)+1
    return cc.get(nb,0)>=MAX_SAME_CURRENCY or cc.get(nq,0)>=MAX_SAME_CURRENCY

def calc_lot(pair, risk_pct, sl_dist_price):
    pip=ps.pip_size_for_pair(pair)
    risk_usd=ACC*risk_pct; sl_pips=sl_dist_price/pip
    if sl_pips<=0: return 0
    return round(risk_usd/(sl_pips*ps.pip_value_per_lot(pair,SNAP)),2)

def load_data():
    pdata={}; close_series={}
    for pair in PAIRS:
        try:
            with open(f'/root/data/{PAIR_FILES[pair]}.pkl','rb') as f: raw=pickle.load(f)
        except: continue
        ts_raw=raw[pair]; ts=ts_raw.index; c=ts_raw['close'].values.astype(float)
        h_=ts_raw['high'].values.astype(float); l_=ts_raw['low'].values.astype(float)
        sp=SPREAD.get(pair,1.0);         pip=ps.pip_size_for_pair(pair); pv=ps.pip_value_per_lot(pair,SNAP)
        ema200=pd.Series(c).ewm(span=200,adjust=False).mean().values
        ema50=pd.Series(c).ewm(span=50,adjust=False).mean().values
        atr=pd.Series(np.maximum(h_-l_,np.maximum(abs(h_-np.roll(c,1)),abs(l_-np.roll(c,1))))).ewm(span=14,adjust=False).mean().values
        daily=ts_raw.resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        pdata[pair]={'ts':ts,'c':c,'h':h_,'lo':l_,'e200':ema200,'e50':ema50,'atr':atr,'pip':pip,'pv':pv,'spread':sp,'daily':daily,'n':len(ts)}
        close_series[pair]=pd.Series(c,index=ts)
    corr_matrix=pd.DataFrame(close_series).pct_change().dropna().corr()
    return pdata, corr_matrix

def run_sim(pdata, corr_matrix, tf_enabled=True, mr_risk=MR_RISK, sessions=None, exclude_pairs=None, exclude_hours=None):
    if sessions is None: sessions=SESSIONS
    if exclude_pairs is None: exclude_pairs=set()
    if exclude_hours is None: exclude_hours=set()
    active_pairs=[p for p in PAIRS if p not in exclude_pairs]
    ref_pair=max(active_pairs, key=lambda p: pdata[p]['n'])
    ref=pdata[ref_pair]; n_bars=ref['n']
    open_pos=[]; pnls=[]; daily_d=None; daily_sb=ACC
    oos_start=pd.Timestamp('2025-01-01').tz_localize('UTC')
    oos_pnls=[]; peak=ACC; mdd=0; oos_peak=ACC; oos_mdd=0; oos_bal_start=None

    def close_position(pos, exit_price, bar_i, reason):
        tr=pos['trend']
        pnl=(exit_price-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
        pnls.append(pnl)
        ts_now=pos_ts[bar_i]
        if ts_now>=oos_start: oos_pnls.append(pnl)
        return pnl

    for i in range(250, n_bars-1):
        ts_now=ref['ts'][i]
        pos_ts=ref['ts']
        today=ts_now.date()
        if daily_d!=today:
            daily_d=today
            daily_sb=ACC+sum(pnls)

        # EXITS first
        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_lo=pd_['lo'][i]; bar_hi=pd_['h'][i]; bar_cl=pd_['c'][i]
            tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; regime=pos['regime']
            closed=False; exit_price=None; exit_reason=''

            if tr==1 and bar_lo<=sl: exit_price=sl; exit_reason='sl'
            elif tr==-1 and bar_hi>=sl: exit_price=sl; exit_reason='sl'
            if exit_price is None and tr==1 and bar_hi>=tp: exit_price=tp; exit_reason='tp'
            elif exit_price is None and tr==-1 and bar_lo<=tp: exit_price=tp; exit_reason='tp'

            if exit_price is None and regime=='tf' and (i-pos['bar'])>=TF_MIN_HOLD:
                cur_atr=pd_['atr'][i]
                if not np.isnan(cur_atr) and cur_atr>0:
                    if tr==1:
                        nsl=bar_cl-TRAIL_ATR_MULT*cur_atr
                        if nsl>sl: pos['sl']=nsl
                    else:
                        nsl=bar_cl+TRAIL_ATR_MULT*cur_atr
                        if nsl<sl: pos['sl']=nsl

            if exit_price is None and regime=='mr' and not igs(ref['ts'][i], sessions):
                spread_slip=(pos['spread']*0.5+0.3)*pos['pip']
                exit_price=bar_cl-spread_slip if tr==1 else bar_cl+spread_slip
                exit_reason='sc'

            if exit_price is None and regime=='tf' and (i-pos['bar'])>=TF_TIME_STOP and (i-pos['bar'])<TF_MAX_HOLD:
                spread_slip=(pos['spread']*0.5+0.3)*pos['pip']
                exit_price=bar_cl-spread_slip if tr==1 else bar_cl+spread_slip
                exit_reason='ts'

            if exit_price is None and regime=='tf' and (i-pos['bar'])>=TF_MAX_HOLD:
                spread_slip=(pos['spread']*0.5+0.3)*pos['pip']
                exit_price=bar_cl-spread_slip if tr==1 else bar_cl+spread_slip
                exit_reason='mh'

            if exit_price is None and regime=='tf':
                ev=pd_['e200'][i]
                if not np.isnan(ev) and abs(bar_cl-ev)/ev<BREAKOUT_ZONE*0.4:
                    spread_slip=(pos['spread']*0.5+0.3)*pos['pip']
                    exit_price=bar_cl-spread_slip if tr==1 else bar_cl+spread_slip
                    exit_reason='tr'

            if exit_price is not None:
                close_position(pos, exit_price, i, exit_reason)
            else:
                remaining.append(pos)
        open_pos=remaining

        # Daily loss limit
        cum_pnl=sum(pnls)
        bal=ACC+cum_pnl
        if bal<1: bal=1
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd

        # OOS tracking
        if ts_now>=oos_start:
            if oos_bal_start is None: oos_bal_start=ACC
            oos_cum=sum(oos_pnls); oos_bal=ACC+oos_cum
            if oos_bal>oos_peak: oos_peak=oos_bal
            ood=(oos_peak-oos_bal)/oos_peak if oos_peak>0 else 0
            if ood>oos_mdd: oos_mdd=ood

        if not igs(ts_now, sessions): continue
        active_pos=[pos['pair'] for pos in open_pos]
        for pair in active_pairs:
            if len(open_pos)>=20: break
            if any(p['pair']==pair for p in open_pos): continue
            if check_currency_overlap(open_pos, pair): continue
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_['n']: continue
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]; cur_atr=pd_['atr'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            pip=pd_['pip']
            if active_pos:
                skip=False
                for op in active_pos:
                    if pair in corr_matrix.columns and op in corr_matrix.columns:
                        cv=corr_matrix.loc[pair,op]
                        if not np.isnan(cv) and abs(cv)>CORR_THRESHOLD: skip=True; break
                if skip: continue
            if ts_now.hour in exclude_hours: continue
            dist_from_ema=(c_val-ev)/ev

            if abs(dist_from_ema)<BREAKOUT_ZONE:
                tr=1 if c_val>ev else -1
                if tr==1 and c_val<e5*0.995: continue
                if tr==-1 and c_val>e5*1.005: continue
                if tr==1:
                    if max(pd_['h'][max(0,i-20):i])<=c_val*1.002: continue
                else:
                    if min(pd_['lo'][max(0,i-20):i])>=c_val*0.998: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if tr==1 and not dg: continue
                if tr==-1 and dg: continue
                sl=ev*(1-0.005) if tr==1 else ev*(1+0.005)
                sl_dist=abs(c_val-sl)
                if sl_dist<2*pip: continue
                tp=c_val+sl_dist*MR_RR if tr==1 else c_val-sl_dist*MR_RR
                entry_fill=c_val+(pd_['spread']*0.5+0.3)*pip if tr==1 else c_val-(pd_['spread']*0.5+0.3)*pip
                lot=calc_lot(pair, mr_risk, sl_dist)
                if lot<=0: continue
                open_pos.append({'pair':pair,'trend':tr,'entry':entry_fill,'sl':sl,'tp':tp,'lot':lot,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'mr'})

            elif tf_enabled and dist_from_ema>BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr>0:
                if c_val<=e5: continue
                if c_val<=max(pd_['h'][max(0,i-20):i])*1.002: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                if not (pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']): continue
                entry_fill=c_val+(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill-TRAIL_ATR_MULT*cur_atr
                tp=entry_fill+2.5*TRAIL_ATR_MULT*cur_atr
                sl_dist=abs(entry_fill-sl)
                if sl_dist<2*pip: continue
                lot=calc_lot(pair, TF_RISK, sl_dist)
                if lot<=0: continue
                open_pos.append({'pair':pair,'trend':1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':lot,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})

            elif tf_enabled and dist_from_ema<-BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr>0:
                if c_val>=e5: continue
                if c_val>=min(pd_['lo'][max(0,i-20):i])*0.998: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                if pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']: continue
                entry_fill=c_val-(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill+TRAIL_ATR_MULT*cur_atr
                tp=entry_fill-2.5*TRAIL_ATR_MULT*cur_atr
                sl_dist=abs(sl-entry_fill)
                if sl_dist<2*pip: continue
                lot=calc_lot(pair, TF_RISK, sl_dist)
                if lot<=0: continue
                open_pos.append({'pair':pair,'trend':-1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':lot,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})

    if not pnls: return None, None
    fw=sum(1 for p in pnls if p>0); fl=sum(1 for p in pnls if p<=0)
    fgw=sum(p for p in pnls if p>0); fgl=abs(sum(p for p in pnls if p<=0))
    fnm=max((ref['ts'][min(n_bars-1,len(ref['ts'])-1)]-ref['ts'][250]).days/30.4375,1)
    full={'n':len(pnls),'wr':fw/(fw+fl)*100,'pf':fgw/fgl if fgl>0 else 99,
          'mdd':mdd*100,'total_pnl':sum(pnls),'avg':np.mean(pnls),
          'avg_win':np.mean([p for p in pnls if p>0]) if fw>0 else 0,
          'avg_loss':np.mean([p for p in pnls if p<=0]) if fl>0 else 0,
          'tpm':len(pnls)/fnm,
          'ev':(fw/(fw+fl))*np.mean([p for p in pnls if p>0])+(fl/(fw+fl))*np.mean([p for p in pnls if p<=0]) if (fw+fl)>0 else 0}
    if not oos_pnls: return full, None
    ow=sum(1 for p in oos_pnls if p>0); ol=sum(1 for p in oos_pnls if p<=0)
    ogw=sum(p for p in oos_pnls if p>0); ogl=abs(sum(p for p in oos_pnls if p<=0))
    oos_nm=18.5
    oos_ev=(ow/(ow+ol))*np.mean([p for p in oos_pnls if p>0])+(ol/(ow+ol))*np.mean([p for p in oos_pnls if p<=0]) if (ow+ol)>0 else 0
    oos={'n':len(oos_pnls),'wr':ow/(ow+ol)*100,'pf':ogw/ogl if ogl>0 else 99,
         'mdd':oos_mdd*100,'total_pnl':sum(oos_pnls),'avg':np.mean(oos_pnls),
         'avg_win':np.mean([p for p in oos_pnls if p>0]) if ow>0 else 0,
         'avg_loss':np.mean([p for p in oos_pnls if p<=0]) if ol>0 else 0,
         'tpm':len(oos_pnls)/oos_nm,'ev':oos_ev}
    return full, oos

print("="*80)
print("  REALISTIC EV — FIXED SIZING on $2,500")
print("="*80, flush=True)
print("\n  Loading...", flush=True)
t0=time.time()
pdata, corr_matrix=load_data()
print(f"  Loaded in {time.time()-t0:.1f}s\n", flush=True)

scenarios=[
    ("0: Baseline (MR+TF)", dict()),
    ("1: MR Only", dict(tf_enabled=False)),
    ("2: MR Only, London", dict(tf_enabled=False, sessions={'london':(7,16)})),
    ("3: MR Only, London, 2%", dict(tf_enabled=False, mr_risk=0.02, sessions={'london':(7,16)})),
    ("4: MR Only, London, 1%", dict(tf_enabled=False, mr_risk=0.01, sessions={'london':(7,16)})),
]
all_results={}
for name, params in scenarios:
    print(f"  {name}...", end='', flush=True)
    t0=time.time()
    full,oos=run_sim(pdata, corr_matrix, **params)
    elapsed=time.time()-t0
    all_results[name]=(full,oos)
    if full:
        fev_pct=full['ev']/ACC*100
        print(f" {elapsed:.0f}s FULL:{full['n']}t WR={full['wr']:.1f}% PF={full['pf']:.1f} MDD={full['mdd']:.1f}% EV=${full['ev']:,.0f} ({fev_pct:.1f}%)")
    else:
        print(f" {elapsed:.0f}s NO TRADES")
    if oos:
        oev_pct=oos['ev']/ACC*100
        mo=oos['ev']*oos['tpm']; mo_pct=mo/ACC*100
        print(f"          OOS:{oos['n']}t WR={oos['wr']:.1f}% PF={oos['pf']:.1f} MDD={oos['mdd']:.1f}% EV=${oos['ev']:,.0f} ({oev_pct:.1f}%) $/mo=${mo:,.0f} ({mo_pct:.1f}%)")

print(f"\n{'='*80}")
print(f"  SUMMARY — EV per trade on $2,500")
print(f"{'='*80}")
print(f"\n  {'Scenario':<30s} {'T':>5s} {'WR%':>6s} {'PF':>5s} {'MDD%':>6s} {'EV$':>9s} {'EV%':>7s} {'$/mo':>10s} {'MoEV%':>8s}")
print(f"  {'-'*30} {'-'*5} {'-'*6} {'-'*5} {'-'*6} {'-'*9} {'-'*7} {'-'*10} {'-'*8}")
for name,(f,o) in all_results.items():
    if f and o:
        mo=o['ev']*o['tpm']; mp=mo/ACC*100
        print(f"  {name:<30s} {o['n']:>5d} {o['wr']:>5.1f}% {o['pf']:>5.1f} {o['mdd']:>5.1f}% ${o['ev']:>8,.0f} {o['ev']/ACC*100:>6.1f}% ${mo:>9,.0f} {mp:>7.1f}%")
    elif f:
        print(f"  {name:<30s} FULL:{f['n']}t EV=${f['ev']:,.0f} OOS:none")
    else:
        print(f"  {name:<30s} NO TRADES")
