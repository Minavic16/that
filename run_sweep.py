import pickle, json, time, sys
from pathlib import Path
import numpy as np, pandas as pd
import position_sizing as ps

PAIR_SETS = {
    '6_core': ['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY'],
    '12': ['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD'],
    '20': ['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD','GBP/AUD','EUR/AUD','NZD/JPY','EUR/CAD','GBP/CAD','AUD/CHF','NZD/CHF','CAD/CHF'],
}
RISKS = [0.0075, 0.010, 0.0125, 0.015, 0.020]
EMA_200=200; EMA_50=50; MAX_HOLD=50; RR_TARGET=2.7; SL_BUFFER=0.005; PULLBACK_PCT=0.005; EARLY_EXIT_PCT=0.001; LEVERAGE=100; ACC=2500
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRIDAY_AFTER=20; SKIP_MONDAY_BEFORE=3
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)

def load_pair(pair):
    pk=pair.replace('/','_')
    with open(f'/root/data/{pk}.pkl','rb') as f: raw=pickle.load(f)
    df=raw.get(pair)
    if df is None or df.empty: return None
    idx=pd.to_datetime(df.index)
    idx=idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
    df.index=idx; return df[df.index>='2018-01-01']

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRIDAY_AFTER: return False
    if d==0 and h<SKIP_MONDAY_BEFORE: return False
    if d==6: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

def bt(all_data, risk_pct):
    ppt={}
    for pair,data in all_data.items():
        ppt[pair]=[]
        if data is None or len(data)<EMA_200*2+100: continue
        pip=ps.pip_size_for_pair(pair); pv=ps.pip_value_per_lot(pair,SNAP)
        d30=data[['open','high','low','close']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        d4h=data[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        daily=data[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        e200=d4h['close'].ewm(span=EMA_200,adjust=False).mean()
        e50=d4h['close'].ewm(span=EMA_50,adjust=False).mean()
        e200_30=e200.reindex(d30.index,method='ffill')
        e50_30=e50.reindex(d30.index,method='ffill')
        c=d30['close'].values; h=d30['high'].values; lo=d30['low'].values; ts=d30.index; n=len(c)
        warmup=EMA_200+50
        if warmup>=n: continue
        i=warmup
        while i<n-MAX_HOLD:
            if not igs(ts[i]): i+=1; continue
            ev200=e200_30.iloc[i]; ev50=e50_30.iloc[i]
            if np.isnan(ev200) or np.isnan(ev50): i+=1; continue
            trend=1 if c[i]>ev200 else -1
            if trend==1 and c[i]<ev50*0.998: i+=1; continue
            if trend==-1 and c[i]>ev50*1.002: i+=1; continue
            if trend==1:
                if not (c[i]<ev200*(1+PULLBACK_PCT) and c[i]>ev200*(1-PULLBACK_PCT)): i+=1; continue
            else:
                if not (c[i]>ev200*(1-PULLBACK_PCT) and c[i]<ev200*(1+PULLBACK_PCT)): i+=1; continue
            if trend==1:
                if max(h[max(0,i-20):i])<=c[i]*1.002: i+=1; continue
            else:
                if min(lo[max(0,i-20):i])>=c[i]*0.998: i+=1; continue
            d_ts=daily.index.asof(ts[i])
            if d_ts not in daily.index: i+=1; continue
            dg=daily.loc[d_ts,'close']>daily.loc[d_ts,'open']
            if trend==1 and not dg: i+=1; continue
            if trend==-1 and dg: i+=1; continue
            e1=c[i]; e2=e1*(1-PULLBACK_PCT*0.5) if trend==1 else e1*(1+PULLBACK_PCT*0.5)
            ae=(e1+e2)/2; sl=ev200*(1-SL_BUFFER) if trend==1 else ev200*(1+SL_BUFFER)
            tp=(e1+(e1-sl)*RR_TARGET) if trend==1 else (e1-(sl-e1)*RR_TARGET)
            ee=ae*(1-EARLY_EXIT_PCT) if trend==1 else ae*(1+EARLY_EXIT_PCT)
            ep=None; er=None
            for j in range(i+1,min(i+MAX_HOLD,n)):
                if trend==1:
                    if lo[j]<=ee: ep=ee; er='EE'; break
                    if lo[j]<=sl: ep=sl; er='SL'; break
                    if h[j]>=tp: ep=tp; er='TP'; break
                    if not igs(ts[j]): ep=c[j]; er='SC'; break
                else:
                    if h[j]>=ee: ep=ee; er='EE'; break
                    if h[j]>=sl: ep=sl; er='SL'; break
                    if lo[j]<=tp: ep=tp; er='TP'; break
                    if not igs(ts[j]): ep=c[j]; er='SC'; break
            else:
                ep=c[min(i+MAX_HOLD,n-1)]; er='MH'
            pd2=(ep-ae) if trend==1 else (ae-ep); pips=pd2/pip
            ppt[pair].append({'pair':pair,'entry_time':ts[i],'trend':trend,'entry':ae,'sl_price':sl,'pips':pips,'pip_value_per_lot':pv,'exit_reason':er})
            i+=1
    at=[]
    for tl in ppt.values(): at.extend(tl)
    at.sort(key=lambda t:t['entry_time'])
    bal=ACC
    for t in at:
        sz=ps.compute_position_size(pair=t['pair'],side='BUY' if t['trend']==1 else 'SELL',entry_price=t['entry'],sl_price=t['sl_price'],account_balance_usd=bal,risk_pct=risk_pct,leverage=LEVERAGE,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
        lot=sz.lot_size; pnl=lot*t['pip_value_per_lot']*t['pips']-lot*t['pip_value_per_lot']*1.5
        bal=max(bal+pnl,1.0); t['pnl_usd']=pnl; t['equity_after']=bal
    return at

def met(trades):
    if not trades: return None
    trades=sorted(trades,key=lambda t:t['entry_time'])
    eq=ACC; peak=eq; mdd=0; mse=eq; mr=[]; lm=None; w=0; l=0; gw=0; gl=0
    for t in trades:
        p=t['pnl_usd']; eq+=p
        if p>0: w+=1; gw+=p
        elif p<0: l+=1; gl+=abs(p)
        if eq>peak: peak=eq
        dd=(peak-eq)/peak if peak>0 else 0
        if dd>mdd: mdd=dd
        mk=(t['entry_time'].year,t['entry_time'].month)
        if lm is None: lm=mk
        elif mk!=lm:
            mr.append((eq-mse)/mse*100 if mse>0 else 0); mse=eq; lm=mk
    if mse!=eq: mr.append((eq-mse)/mse*100 if mse>0 else 0)
    nd=(trades[-1]['entry_time']-trades[0]['entry_time']).days
    nm=max(nd/30.4375,1)
    return {'n':len(trades),'wr':w/(w+l)*100,'pf':gw/gl if gl>0 else 99,'ret':(eq/ACC-1)*100,'final':eq,'mdd':mdd*100,'mm':np.mean(mr) if mr else 0,'md':np.median(mr) if mr else 0,'p5':np.percentile(mr,5) if mr else 0,'p95':np.percentile(mr,95) if mr else 0,'tpm':len(trades)/nm}

print('Loading data...',flush=True)
all_data={}
for p in ['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD','GBP/AUD','EUR/AUD','NZD/JPY','EUR/CAD','GBP/CAD','AUD/CHF','NZD/CHF','CAD/CHF']:
    d=load_pair(p)
    if d is not None: all_data[p]=d
print(f'Loaded {len(all_data)} pairs',flush=True)

results=[]
idx=0
for sn, pairs in PAIR_SETS.items():
    subset={p:all_data.get(p) for p in pairs}
    for risk in RISKS:
        idx+=1
        t0=time.time()
        trades=bt(subset,risk)
        m=met(trades)
        el=time.time()-t0
        if m:
            print(f'[{idx}/15] {sn:<8} risk={risk*100:.2f}%  trades={m["n"]:,}({m["tpm"]:.0f}/mo)  WR={m["wr"]:.1f}%  PF={m["pf"]:.1f}  Monthly={m["mm"]:.2f}%  DD={m["mdd"]:.2f}%  Final=${m["final"]:,.0f}  {el:.1f}s',flush=True)
            results.append({'set':sn,'np':len(pairs),'risk':risk,'n':m['n'],'tpm':m['tpm'],'wr':m['wr'],'pf':m['pf'],'mm':m['mm'],'md':m['md'],'p5':m['p5'],'p95':m['p95'],'mdd':m['mdd'],'ret':m['ret'],'final':m['final']})

print('\n=== MONTHLY EV TABLE ===')
print(f'{"Set":<10}' + ''.join(f' {r*100:>5.2f}%' for r in RISKS))
for sn in PAIR_SETS:
    row=f'{sn:<10}'
    for risk in RISKS:
        m=[r for r in results if r['set']==sn and abs(r['risk']-risk)<1e-8]
        row+=f' {m[0]["mm"]:>6.2f}%' if m else f' {"N/A":>7}'
    print(row)

print('\n=== MAX DD TABLE ===')
for sn in PAIR_SETS:
    row=f'{sn:<10}'
    for risk in RISKS:
        m=[r for r in results if r['set']==sn and abs(r['risk']-risk)<1e-8]
        if m:
            d=m[0]['mdd']; row+=f' {d:>5.2f}%{"✓" if d<10 else "✗"}'
        else: row+=f' {"N/A":>7}'
    print(row)

print('\n=== BEST 5ERS CONFIGS (DD<10%) ===')
for r in sorted([x for x in results if x['mdd']<10],key=lambda x:x['mm'],reverse=True)[:8]:
    print(f'  {r["set"]:<10} risk={r["risk"]*100:.2f}%  Monthly={r["mm"]:.2f}%  DD={r["mdd"]:.2f}%  WR={r["wr"]:.1f}%  PF={r["pf"]:.1f}')

Path('/root/se_optimization_results.json').write_text(json.dumps(results,indent=2,default=str))
print('\nDone.')
