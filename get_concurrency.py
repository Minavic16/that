import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS = ['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD','GBP/AUD','EUR/AUD','NZD/JPY','EUR/CAD','GBP/CAD','AUD/CHF','NZD/CHF','CAD/CHF']
EMA_200=200; EMA_50=50; MAX_HOLD=50; RR=2.7; SL_BUF=0.005; PULL=0.005; EE=0.001
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3

def load(pair):
    with open(f'/root/data/{pair.replace(chr(47),chr(95))}.pkl','rb') as f: raw=pickle.load(f)
    df=raw.get(pair); idx=pd.to_datetime(df.index); idx=idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
    df.index=idx; return df[df.index>='2018-01-01']

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d==6: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

raw=[]
for pair in PAIRS:
    data=load(pair)
    d30=data[['open','high','low','close']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
    d4h=data[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
    e200=d4h['close'].ewm(span=EMA_200,adjust=False).mean(); e50=d4h['close'].ewm(span=EMA_50,adjust=False).mean()
    e200_30=e200.reindex(d30.index,method='ffill'); e50_30=e50.reindex(d30.index,method='ffill')
    daily=data[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
    c=d30['close'].values; h=d30['high'].values; lo=d30['low'].values; ts=d30.index; n=len(c)
    i=EMA_200+50
    while i<n-MAX_HOLD:
        if not igs(ts[i]): i+=1; continue
        ev=e200_30.iloc[i]; e5=e50_30.iloc[i]
        if np.isnan(ev) or np.isnan(e5): i+=1; continue
        tr=1 if c[i]>ev else -1
        if tr==1 and c[i]<e5*0.998: i+=1; continue
        if tr==-1 and c[i]>e5*1.002: i+=1; continue
        if tr==1:
            if not (c[i]<ev*(1+PULL) and c[i]>ev*(1-PULL)): i+=1; continue
            if max(h[max(0,i-20):i])<=c[i]*1.002: i+=1; continue
        else:
            if not (c[i]>ev*(1-PULL) and c[i]<ev*(1+PULL)): i+=1; continue
            if min(lo[max(0,i-20):i])>=c[i]*0.998: i+=1; continue
        d_ts=daily.index.asof(ts[i])
        if d_ts not in daily.index: i+=1; continue
        dg=daily.loc[d_ts,'close']>daily.loc[d_ts,'open']
        if tr==1 and not dg: i+=1; continue
        if tr==-1 and dg: i+=1; continue
        ae=c[i]*(1-PULL*0.25) if tr==1 else c[i]*(1+PULL*0.25)
        sl=ev*(1-SL_BUF) if tr==1 else ev*(1+SL_BUF)
        tp=(c[i]+(c[i]-sl)*RR) if tr==1 else (c[i]-(sl-c[i])*RR)
        exit_j=i
        for j in range(i+1,min(i+MAX_HOLD,n)):
            if tr==1:
                if lo[j]<=ae*(1-EE) or lo[j]<=sl or h[j]>=tp or not igs(ts[j]): exit_j=j; break
            else:
                if h[j]>=ae*(1+EE) or h[j]>=sl or lo[j]<=tp or not igs(ts[j]): exit_j=j; break
        raw.append((pair, ts[i], ts[exit_j]))
        i+=1

# Compute concurrent positions over time
events=sorted([(t[1],1) for t in raw]+[(t[2],-1) for t in raw])
curves=[]; cur=0
for t,d in events:
    cur+=d; curves.append(cur)
arr=np.array(curves)
print(f'Concurrent position statistics:')
print(f'  Mean: {arr.mean():.1f}')
print(f'  P50: {np.percentile(arr,50):.0f}')
print(f'  P90: {np.percentile(arr,90):.0f}')
print(f'  P95: {np.percentile(arr,95):.0f}')
print(f'  P99: {np.percentile(arr,99):.0f}')
print(f'  Max: {arr.max()}')
print(f'  >5: {(arr>5).mean()*100:.1f}%')
print(f'  >10: {(arr>10).mean()*100:.1f}%')
print(f'  >20: {(arr>20).mean()*100:.1f}%')
print(f'  >30: {(arr>30).mean()*100:.1f}%')
print(f'  >50: {(arr>50).mean()*100:.1f}%')
