"""Track max consecutive losses and drawdown stats at 3.5% risk"""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; ACC=2500
SESSIONS={'london':(7,16),'new_york':(12,20)}; SKIP_FRI=20; SKIP_MON=3
BREAKOUT_ZONE=0.005; TRAIL_ATR_MULT=2.5; MAX_SAME_CURRENCY=2; SESSION_CLOSE_HOUR=20

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

pdata={}
for pair in PAIRS:
    pk=PAIR_FILES[pair]
    try:
        with open(f'/root/data/{pk}.pkl','rb') as f: raw=pickle.load(f)
        df=raw.get(pair)
        if df is None: continue
        idx=pd.to_datetime(df.index); idx=idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index=idx; df=df[df.index>='2022-01-01']; df=df[df.index<='2026-07-24']
        if len(df)<500: continue
        pip=ps.pip_size_for_pair(pair); pv=ps.pip_value_per_lot(pair,SNAP)
        d30=df[['open','high','low','close','volume']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna(subset=['close'])
        d4h=df[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        e200=d4h['close'].ewm(span=200,adjust=False).mean()
        tr1=d4h['high']-d4h['low']; tr2=abs(d4h['high']-d4h['close'].shift(1)); tr3=abs(d4h['low']-d4h['close'].shift(1))
        tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1); atr_4h=tr.rolling(14).mean()
        pdata[pair]={'c':d30['close'].values,'h':d30['high'].values,'lo':d30['low'].values,'t':d30.index,
                      'e200':e200.values,'atr4h':atr_4h.values,'e200t':e200.index,'pip':pip,'pv':pv}
    except: pass

print(f"Loaded {len(pdata)} pairs")

bal=ACC; peak=ACC; open_pos=[]; max_dd=0
tw=0; tl=0; cl=0; mc=0; ws=0; mws=0; pw=0.0; pl=0.0
pnl_list=[]; cooldown_until={p:None for p in PAIRS}
dd_events=[]  # (peak, trough, dd%, trades_in_dd, consec_losses)

for pair in pdata:
    d=pdata[pair]; c=d['c']; h=d['h']; lo=d['lo']; ts=d['t']
    pip=d['pip']; pv=d['pv']
    e200=d['e200']; e200t=d['e200t']; atr4h=d['atr4h']
    mr_state=None; tf_paired=False
    base_prices={i:c[i] for i in range(len(c)) if i<50}

    def g4h(t):
        valid=e200t[e200t<=t]
        return e200[-len(valid)] if len(valid)>0 else None, atr4h[-len(valid)] if len(valid)>0 else None

    for i in range(50,len(c)):
        now=ts[i]
        if not igs(now): continue

        for pi in range(len(open_pos)-1,-1,-1):
            pos=open_pos[pi]
            if now-pos['entry_time']>=pd.Timedelta(hours=16*12):
                pnl=(pos['pv']*(pos['sl']-pos['entry']) if pos['side']==1 else pos['pv']*(pos['entry']-pos['sl']))-COMMISSION/(pos['pip']*pos['pv'])
                bal+=pnl; open_pos.pop(pi); pnl_list.append(pnl)
                if pnl>0: tw+=1; pw+=pnl; cl=0; ws+=1
                else: tl+=1; pl+=pnl; cl+=1; ws=0
                if cl>mc: mc=cl
                if ws>mws: mws=ws

        e4h,a4h=g4h(now)
        if e4h is None or a4h is None: continue
        dist=abs(c[i]-e4h); threshold=e4h*BREAKOUT_ZONE
        if cooldown_until.get(pair) and now<cooldown_until[pair]: continue
        total_risk=sum(abs(op['sl']-op['entry'])*op['pv']*0.01 for op in open_pos if op['pair']==pair)
        if total_risk>bal*0.04: continue
        same_curr=[p for p in open_pos if any(cc in p['pair'] for cc in [pair[:3],pair[-3:]])]
        if len(same_curr)>=MAX_SAME_CURRENCY: continue

        if dist>threshold and mr_state is None and not tf_paired:
            cur=c[i]; side=1 if cur<e4h else -1
            mr_state='pending'; mr_entry=cur; mr_sl=cur-1.8*a4h*side if side==1 else cur+1.8*a4h*side

        if dist<=threshold:
            if mr_state=='pending' and abs(c[i]-mr_entry)<threshold/2:
                cur=c[i]; side=1 if cur<e4h else -1
                open_pos.append({'pair':pair,'side':side,'entry':cur,'sl':cur-1.8*a4h*side if side==1 else cur+1.8*a4h*side,'pip':pip,'pv':pv,'entry_time':now,'entry_bar':i})
                mr_state='open'

            if mr_state=='open' and not tf_paired:
                cur=c[i]
                side=1 if cur<e4h else (-1 if cur>e4h else 0)
                if side!=0:
                    tf_sl=cur-2.0*a4h*side if side==1 else cur+2.0*a4h*side
                    tf_tp=cur+2.0*a4h*side if side==1 else cur-2.0*a4h*side
                    open_pos.append({'pair':pair,'side':side,'entry':cur,'sl':tf_sl,'tp':tf_tp,'trail_sl':tf_sl,'pip':pip,'pv':pv,'entry_time':now,'entry_bar':i,'highest':cur,'lowest':cur})
                    tf_paired=True

        for pi in range(len(open_pos)-1,-1,-1):
            pos=open_pos[pi]
            if pos['pair']!=pair: continue
            bars=i-pos.get('entry_bar',50)
            exit=False; ep=None

            if pos.get('tp'):
                if pos['side']==1 and c[i]>=pos['tp']: exit=True; ep=pos['tp']
                elif pos['side']==-1 and c[i]<=pos['tp']: exit=True; ep=pos['tp']
            if not exit:
                if pos['side']==1 and c[i]<=pos['sl']: exit=True; ep=pos['sl']
                elif pos['side']==-1 and c[i]>=pos['sl']: exit=True; ep=pos['sl']
            if not exit and bars>=100: exit=True; ep=c[i]
            if not exit and pos.get('tp') and bars>=30: exit=True; ep=c[i]
            if not exit and now.hour==SESSION_CLOSE_HOUR and igs(now): exit=True; ep=c[i]

            if exit:
                pnl=(pos['pv']*(ep-pos['entry']) if pos['side']==1 else pos['pv']*(pos['entry']-ep))-COMMISSION/(pos['pip']*pos['pv'])
                bal+=pnl; open_pos.pop(pi); pnl_list.append(pnl)
                if pnl>0: tw+=1; pw+=pnl; cl=0; ws+=1
                else: tl+=1; pl+=pnl; cl+=1; ws=0
                if cl>mc: mc=cl
                if ws>mws: mws=ws
                cooldown_until[pair]=now+pd.Timedelta(minutes=30)
            else:
                if pos.get('tp'):
                    if pos['side']==1:
                        if h[i]>pos.get('highest',pos['entry']): pos['highest']=h[i]
                        new_trail=pos['highest']-TRAIL_ATR_MULT*a4h
                        if new_trail>pos['sl']: pos['sl']=new_trail
                    else:
                        if lo[i]<pos.get('lowest',pos['entry']): pos['lowest']=lo[i]
                        new_trail=pos['lowest']+TRAIL_ATR_MULT*a4h
                        if new_trail<pos['sl']: pos['sl']=new_trail

        if bal>peak: peak=bal
        dd=(peak-bal)/peak*100 if peak>0 else 0
        if dd>max_dd: max_dd=dd

total=tw+tl
print()
print("="*60)
print("  DRAWDOWN ANALYSIS AT 3.5% RISK")
print("="*60)
print(f"  Total trades: {total}")
print(f"  Wins: {tw}, Losses: {tl}")
print(f"  WR: {tw/total*100:.1f}%")
print(f"  Max consecutive losses: {mc}")
print(f"  Max win streak: {mws}")
print(f"  Max DD: {max_dd:.2f}%")
print()
print(f"  === DD Math ===")
print(f"  Each loss costs ~3.5% of current equity")
print(f"  Max consecutive losses: {mc}")
print(f"  Simple DD estimate: {mc} x 3.5% = {mc*3.5:.1f}%")
print(f"  Actual max DD (with compounding): {max_dd:.2f}%")
print(f"  DD / 3.5% risk = {max_dd/3.5:.1f} loss-equivalent trades")
print()
print(f"  === To reach exactly 10% DD ===")
print(f"  At 3.5% risk: need {10/3.5:.1f} consecutive loss-equivalent")
print(f"  Currently max DD = {max_dd:.1f}% (max consec loss = {mc})")
if max_dd < 10:
    print(f"  DD {max_dd:.1f}% is BELOW 10% — strategy currently safe")
else:
    print(f"  DD {max_dd:.1f}% EXCEEDS 10% — too risky at this level")
print()

# Also check how many trades to recover from DD
print(f"  === Recovery Math ===")
print(f"  After {mc} consecutive losses at 3.5%:")
loss_mult = (1-0.035)**mc
print(f"    Balance = {loss_mult*100:.1f}% of peak")
print(f"    To recover: need {(1/loss_mult - 1)*100:.1f}% gain from trough")
avg_win = pw/tw if tw else 0
avg_loss = pl/tl if tl else 0
if avg_win > 0:
    trades_to_recover = abs(pl/tl*mc) / avg_win if avg_win else 999
    print(f"    Avg win: ${avg_win:.2f}, Avg loss: ${avg_loss:.2f}")
    print(f"    Trades to recover: ~{trades_to_recover:.0f} wins (assuming avg win)")

# Monthly trade frequency
print()
print(f"  === Time Context ===")
months = total / 47  # ~47 trades/mo
print(f"  ~{47} trades/month")
print(f"  {mc} consecutive losses would take ~{mc/47*30:.0f} days if back-to-back")
print(f"  But losses are distributed: avg gap between losses = {total/max(tl,1):.1f} trades")
