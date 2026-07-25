"""
Optimization: Find config meeting 25% monthly EV with <10% MDD.
Tests: risk %, session window, time stop, breakout strategy.
"""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500
BASE_SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}
CORR_THRESHOLD=0.85; MAX_SAME_CURRENCY=2

# Load data once
pdata={}; close_series={}
for pair in PAIRS:
    pk=PAIR_FILES[pair]
    with open(f'/root/data/{pk}.pkl','rb') as f: raw=pickle.load(f)
    df=raw.get(pair)
    if df is None: continue
    idx=pd.to_datetime(df.index); idx=idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
    df.index=idx; df=df[df.index>='2022-01-01']; df=df[df.index<='2026-07-19']
    if len(df)<500: continue
    pip=ps.pip_size_for_pair(pair); pv=ps.pip_value_per_lot(pair,SNAP)
    d30=df[['open','high','low','close','volume']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna(subset=['close'])
    d4h=df[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
    daily=df[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
    e200=d4h['close'].ewm(span=200,adjust=False).mean()
    e50=d4h['close'].ewm(span=50,adjust=False).mean()
    tr1=d4h['high']-d4h['low']; tr2=abs(d4h['high']-d4h['close'].shift(1)); tr3=abs(d4h['low']-d4h['close'].shift(1))
    tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
    atr_4h=tr.rolling(14).mean()
    pdata[pair]={'c':d30['close'].values,'h':d30['high'].values,'lo':d30['low'].values,'o':d30['open'].values,'ts':d30.index,'n':len(d30),
        'e200':e200.reindex(d30.index,method='ffill').values,'e50':e50.reindex(d30.index,method='ffill').values,
        'atr':atr_4h.reindex(d30.index,method='ffill').values,'daily':daily,'pip':pip,'pv':pv,'spread':BASE_SPREAD.get(pair,2.0)}
    close_series[pair]=d30['close']

ref_pair=max(pdata.keys(), key=lambda p: pdata[p]['n'])
ref=pdata[ref_pair]; n_bars=ref['n']
price_df=pd.DataFrame(close_series); returns_full=price_df.pct_change().dropna(); corr_matrix=returns_full.corr()

def run_config(mr_risk, tf_risk, bk_risk, entry_start, entry_end, close_hour, tf_time_stop, use_breakout, label, period='full'):
    def igs(ts):
        h,d=ts.hour,ts.dayofweek
        if d==4 and h>=20: return False
        if d==0 and h<3: return False
        if d>=5: return False
        return entry_start<=h<entry_end
    def is_session(ts):
        return entry_start<=ts.hour<=close_hour

    bal=ACC; peak=ACC; mdd=0; open_pos=[]; wins=0; losses=0; total_pnl=0; win_sum=0; loss_sum=0
    daily_d=None; daily_sb=ACC; monthly_pnl={}; n_trades=0

    start_date=pd.Timestamp('2022-01-01',tz='UTC') if period=='full' else pd.Timestamp('2025-01-01',tz='UTC')
    end_date=pd.Timestamp('2026-07-19',tz='UTC')

    for i in range(250, n_bars-1):
        ts_now=ref['ts'][i]
        if ts_now<start_date or ts_now>end_date: continue
        today=ts_now.date(); month_key=(ts_now.year, ts_now.month)
        if daily_d!=today: daily_d=today; daily_sb=bal
        if daily_sb>0 and (daily_sb-bal)/daily_sb>=0.05:
            for pos in open_pos:
                pd_=pdata.get(pos['pair'])
                if pd_ is None or i>=pd_['n']: continue
                ep=pd_['c'][i]-(pos['spread']*0.5+0.3)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl
            open_pos.clear(); continue

        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_cl=pd_['c'][i]; tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False; regime=pos['regime']

            if (tr==1 and pd_['lo'][i]<=sl) or (tr==-1 and pd_['h'][i]>=sl):
                pnl=(sl-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl; closed=True
            if not closed and ((tr==1 and pd_['h'][i]>=tp) or (tr==-1 and pd_['lo'][i]<=tp)):
                pnl=(tp-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl; closed=True

            # TF trailing
            if not closed and regime=='tf' and (i-pos['bar'])>=8:
                cur_atr=pd_['atr'][i]
                if not np.isnan(cur_atr) and cur_atr>0:
                    new_sl=bar_cl-2.5*cur_atr if tr==1 else bar_cl+2.5*cur_atr
                    if (tr==1 and new_sl>sl) or (tr==-1 and new_sl<sl): pos['sl']=new_sl

            # Session close (MR only)
            if not closed and regime=='mr' and not is_session(ts_now):
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl; closed=True

            # TF time stop
            if not closed and regime=='tf' and (i-pos['bar'])>=tf_time_stop and (i-pos['bar'])<100:
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl; closed=True

            # TF max hold
            if not closed and regime=='tf' and (i-pos['bar'])>=100:
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl; closed=True

            # TF trend reversal
            if not closed and regime=='tf':
                ev=pd_['e200'][i]
                if not np.isnan(ev) and abs(bar_cl-ev)/ev<0.002:
                    ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                    pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                    bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                    if pnl>0: win_sum+=pnl
                    else: loss_sum+=pnl
                    monthly_pnl[month_key]=monthly_pnl.get(month_key,0)+pnl; closed=True

            if not closed: remaining.append(pos)
        open_pos=remaining
        bal=max(bal,1.0)
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd

        if not igs(ts_now): continue
        active_pairs=[pos['pair'] for pos in open_pos]
        for pair in PAIRS:
            if len(open_pos)>=20: break
            if any(p['pair']==pair for p in open_pos): continue
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_['n']: continue
            nb,nq=pair.split('/'); cc={}
            for pos in open_pos:
                b,q=pos['pair'].split('/'); cc[b]=cc.get(b,0)+1; cc[q]=cc.get(q,0)+1
            if cc.get(nb,0)>=MAX_SAME_CURRENCY or cc.get(nq,0)>=MAX_SAME_CURRENCY: continue
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]; cur_atr=pd_['atr'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            skip_pair=False
            for op in active_pairs:
                if pair in corr_matrix.columns and op in corr_matrix.columns:
                    cv=corr_matrix.loc[pair,op]
                    if not np.isnan(cv) and abs(cv)>CORR_THRESHOLD: skip_pair=True; break
            if skip_pair: continue
            pip=pd_['pip']; dist=(c_val-ev)/ev

            # MR
            if abs(dist)<0.005:
                tr_=1 if c_val>ev else -1
                if tr_==1 and c_val<e5*0.995: continue
                if tr_==-1 and c_val>e5*1.005: continue
                if tr_==1:
                    if max(pd_['h'][max(0,i-20):i])<=c_val*1.002: continue
                else:
                    if min(pd_['lo'][max(0,i-20):i])>=c_val*0.998: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if tr_==1 and not dg: continue
                if tr_==-1 and dg: continue
                sl_=ev*(1-0.005) if tr_==1 else ev*(1+0.005)
                sl_dist=abs(c_val-sl_)
                if sl_dist<2*pip: continue
                tp_=c_val+sl_dist*2.2 if tr_==1 else c_val-sl_dist*2.2
                ef=c_val+(pd_['spread']*0.5+0.3)*pip if tr_==1 else c_val-(pd_['spread']*0.5+0.3)*pip
                sz=ps.compute_position_size(pair=pair,side='BUY' if tr_==1 else 'SELL',entry_price=ef,sl_price=sl_,account_balance_usd=bal,risk_pct=mr_risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':tr_,'entry':ef,'sl':sl_,'tp':tp_,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'mr'})
                n_trades+=1

            # TF LONG
            elif dist>0.005 and not np.isnan(cur_atr) and cur_atr>0:
                if c_val<=e5: continue
                if c_val<=max(pd_['h'][max(0,i-20):i])*1.002: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if not dg: continue
                ef=c_val+(pd_['spread']*0.5+0.3)*pip
                sl_=ef-2.5*cur_atr; tp_=ef+2.5*2.5*cur_atr
                sl_dist=abs(ef-sl_)
                if sl_dist<2*pip: continue
                sz=ps.compute_position_size(pair=pair,side='BUY',entry_price=ef,sl_price=sl_,account_balance_usd=bal,risk_pct=tf_risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':1,'entry':ef,'sl':sl_,'tp':tp_,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})
                n_trades+=1

            # TF SHORT
            elif dist<-0.005 and not np.isnan(cur_atr) and cur_atr>0:
                if c_val>=e5: continue
                if c_val>=min(pd_['lo'][max(0,i-20):i])*0.998: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if dg: continue
                ef=c_val-(pd_['spread']*0.5+0.3)*pip
                sl_=ef+2.5*cur_atr; tp_=ef-2.5*2.5*cur_atr
                sl_dist=abs(sl_-ef)
                if sl_dist<2*pip: continue
                sz=ps.compute_position_size(pair=pair,side='SELL',entry_price=ef,sl_price=sl_,account_balance_usd=bal,risk_pct=tf_risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':-1,'entry':ef,'sl':sl_,'tp':tp_,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})
                n_trades+=1

    total=wins+losses
    wr=wins/total*100 if total>0 else 0
    pf=win_sum/abs(loss_sum) if loss_sum!=0 else 0
    months=sorted(monthly_pnl.keys())
    pnls=[monthly_pnl[m] for m in months]
    nm=len(pnls)
    if nm==0: return None
    avg_m=np.mean(pnls)
    compound=(bal/ACC)**(1/nm)-1 if nm>0 else 0
    profitable=sum(1 for p in pnls if p>0)
    downside=np.sqrt(np.mean([p**2 for p in pnls if p<0])) if any(p<0 for p in pnls) else 1
    sortino=avg_m/downside

    return {
        'label':label,'trades':total,'tpm':total/max(nm,1),'wr':wr,'pf':pf,'mdd':mdd*100,
        'final':bal,'return':(bal/ACC-1)*100,'months':nm,'profitable':profitable,
        'avg_monthly':avg_m,'compound':compound*100,'sortino':sortino,
    }

print("="*80)
print("  OPTIMIZATION: 25% MONTHLY EV + <10% MDD")
print("="*80)

configs = [
    # (mr_risk, tf_risk, bk_risk, entry_start, entry_end, close_hour, tf_time_stop, use_breakout, label)
    # Baseline
    (0.035, 0.022, 0.018, 7, 20, 20, 100, False, "Baseline (original)"),
    # London only
    (0.035, 0.022, 0.018, 7, 16, 16, 100, False, "London only, no time stop"),
    # London + time stop
    (0.035, 0.022, 0.018, 7, 16, 16, 30, False, "London + TS30"),
    # Lower risk
    (0.020, 0.015, 0.012, 7, 16, 16, 30, False, "Low risk (2% MR, 1.5% TF)"),
    # Higher risk
    (0.050, 0.030, 0.025, 7, 16, 16, 30, False, "High risk (5% MR, 3% TF)"),
    # Very high risk
    (0.075, 0.045, 0.035, 7, 16, 16, 30, False, "V.High risk (7.5% MR, 4.5% TF)"),
    # Max risk
    (0.100, 0.060, 0.045, 7, 16, 16, 30, False, "Max risk (10% MR, 6% TF)"),
    # London 7-14 (tighter)
    (0.035, 0.022, 0.018, 7, 14, 14, 30, False, "London 7-14 + TS30"),
    # London 7-12 (morning only)
    (0.035, 0.022, 0.018, 7, 12, 12, 30, False, "London 7-12 + TS30"),
    # High risk + London tight
    (0.075, 0.045, 0.035, 7, 14, 14, 30, False, "7.5% risk + London 7-14"),
    # Very high + London tight
    (0.100, 0.060, 0.045, 7, 14, 14, 30, False, "10% risk + London 7-14"),
]

results=[]
for cfg in configs:
    mr_risk, tf_risk, bk_risk, entry_start, entry_end, close_hour, tf_time_stop, use_breakout, label = cfg
    r=run_config(mr_risk, tf_risk, bk_risk, entry_start, entry_end, close_hour, tf_time_stop, use_breakout, label, 'oos')
    if r:
        r['mr_risk']=mr_risk*100; r['tf_risk']=tf_risk*100
        results.append(r)
        meets='✅' if r['compound']>=25 and r['mdd']<10 else '❌'
        print(f"  {meets} {label:40s} | WR={r['wr']:.1f}% PF={r['pf']:.1f} MDD={r['mdd']:.1f}% Mo={r['compound']:.1f}% Final=${r['final']:,.0f}")

print("\n" + "="*80)
print("  MEETING CONSTRAINTS (25%+ monthly, <10% MDD)")
print("="*80)
for r in results:
    if r['compound']>=25 and r['mdd']<10:
        print(f"\n  ✅ {r['label']}")
        print(f"     WR={r['wr']:.1f}% PF={r['pf']:.1f} MDD={r['mdd']:.1f}%")
        print(f"     Monthly: {r['compound']:.1f}% | Final: ${r['final']:,.0f}")
        print(f"     Trades: {r['trades']} ({r['tpm']:.0f}/mo) Sortino: {r['sortino']:.2f}")

if not any(r['compound']>=25 and r['mdd']<10 for r in results):
    print("\n  No config meets both constraints.")
    print("\n  Best by monthly return:")
    best=sorted(results, key=lambda x: x['compound'], reverse=True)[:3]
    for r in best:
        print(f"    {r['label']:40s} | Mo={r['compound']:.1f}% MDD={r['mdd']:.1f}%")
    print("\n  Best by MDD (under 10%):")
    low_mdd=[r for r in results if r['mdd']<10]
    low_mdd.sort(key=lambda x: x['compound'], reverse=True)
    for r in low_mdd[:3]:
        print(f"    {r['label']:40s} | Mo={r['compound']:.1f}% MDD={r['mdd']:.1f}%")
