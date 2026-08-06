"""
Trade Analysis — capture every trade from the MR+TF backtest and analyze patterns.
"""
import pickle, numpy as np, pandas as pd, json
import position_sizing as ps
from pathlib import Path

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; ACC=2500; LEV=100
SESSIONS={'london':(7,16),'new_york':(12,20)}; SKIP_FRI=20; SKIP_MON=3
MR_RISK=0.035; MR_RR=2.2; TF_RISK=0.022; TF_TIME_STOP=30; TF_MAX_HOLD=100; TF_MIN_HOLD=8
BREAKOUT_ZONE=0.005; TRAIL_ATR_MULT=2.5; CORR_THRESHOLD=0.75; MAX_SAME_CURRENCY=2; SESSION_CLOSE_HOUR=20

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

# Load all pair data
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

# Run backtest and capture all trades
bal=ACC; peak=ACC; open_pos=[]; trades_log=[]
cooldown_until={p:None for p in PAIRS}

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
                bal+=pnl; open_pos.pop(pi)
                trades_log.append({**pos,'exit_price':pos['sl'],'pnl':pnl,'exit_reason':'max_hold_timeout',
                                   'exit_time':now,'bars_held':(now-pos['entry_time']).total_seconds()/1800})

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
            mr_entry_bar=i; mr_entry_time=now

        if dist<=threshold:
            if mr_state=='pending' and abs(c[i]-mr_entry)<threshold/2:
                cur=c[i]; side=1 if cur<e4h else -1
                sl=cur-1.8*a4h*side if side==1 else cur+1.8*a4h*side
                open_pos.append({'pair':pair,'side':side,'entry':cur,'sl':sl,'pip':pip,'pv':pv,
                                 'entry_time':now,'entry_bar':i,'type':'MR',
                                 'e4h':e4h,'atr4h':a4h,'dist_pct':dist/e4h*100})
                mr_state='open'

            if mr_state=='open' and not tf_paired:
                cur=c[i]
                side=1 if cur<e4h else (-1 if cur>e4h else 0)
                if side!=0:
                    tf_sl=cur-2.0*a4h*side if side==1 else cur+2.0*a4h*side
                    tf_tp=cur+2.0*a4h*side if side==1 else cur-2.0*a4h*side
                    open_pos.append({'pair':pair,'side':side,'entry':cur,'sl':tf_sl,'tp':tf_tp,'trail_sl':tf_sl,
                                     'pip':pip,'pv':pv,'entry_time':now,'entry_bar':i,'type':'TF',
                                     'highest':cur,'lowest':cur,
                                     'e4h':e4h,'atr4h':a4h,'dist_pct':dist/e4h*100})
                    tf_paired=True

        for pi in range(len(open_pos)-1,-1,-1):
            pos=open_pos[pi]
            if pos['pair']!=pair: continue
            bars=i-pos.get('entry_bar',50)
            exit=False; ep=None; exit_reason=None

            if pos.get('tp'):
                if pos['side']==1 and c[i]>=pos['tp']: exit=True; ep=pos['tp']; exit_reason='take_profit'
                elif pos['side']==-1 and c[i]<=pos['tp']: exit=True; ep=pos['tp']; exit_reason='take_profit'
            if not exit:
                if pos['side']==1 and c[i]<=pos['sl']: exit=True; ep=pos['sl']; exit_reason='stop_loss'
                elif pos['side']==-1 and c[i]>=pos['sl']: exit=True; ep=pos['sl']; exit_reason='stop_loss'
            if not exit and bars>=TF_MAX_HOLD: exit=True; ep=c[i]; exit_reason='max_hold'
            if not exit and pos.get('tp') and bars>=TF_TIME_STOP: exit=True; ep=c[i]; exit_reason='time_stop'
            if not exit and now.hour==SESSION_CLOSE_HOUR and igs(now): exit=True; ep=c[i]; exit_reason='session_close'

            if exit:
                if pos['side']==1: pnl=(pos['pv']*(ep-pos['entry']))-COMMISSION/(pos['pip']*pos['pv'])
                else: pnl=(pos['pv']*(pos['entry']-ep))-COMMISSION/(pos['pip']*pos['pv'])
                bal+=pnl; open_pos.pop(pi)
                trades_log.append({**pos,'exit_price':ep,'pnl':pnl,'exit_reason':exit_reason,
                                   'exit_time':now,'bars_held':bars})
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

# Save trade log
trades_df = pd.DataFrame(trades_log)
trades_df.to_csv('/root/logs/trade_analysis.csv', index=False)
print(f"\nTotal trades: {len(trades_df)}")
print(f"Saved to /root/logs/trade_analysis.csv")

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  TRADE ANALYSIS")
print("="*70)

wins = trades_df[trades_df['pnl'] > 0]
losses = trades_df[trades_df['pnl'] <= 0]

print(f"\n  Overall: {len(trades_df)} trades, {len(wins)} wins, {len(losses)} losses")
print(f"  WR: {len(wins)/len(trades_df)*100:.1f}%")
print(f"  Avg Win: ${wins['pnl'].mean():.2f}")
print(f"  Avg Loss: ${losses['pnl'].mean():.2f}")
print(f"  PF: {wins['pnl'].sum()/abs(losses['pnl'].sum()):.2f}")

# By Type (MR vs TF)
print(f"\n  --- By Type ---")
for t in ['MR','TF']:
    subset = trades_df[trades_df['type']==t]
    w = subset[subset['pnl']>0]
    l = subset[subset['pnl']<=0]
    if len(subset)>0:
        print(f"  {t}: {len(subset)} trades, WR={len(w)/len(subset)*100:.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():.2f}, PF={w['pnl'].sum()/abs(l['pnl'].sum()) if len(l)>0 else 999:.2f}")

# By Pair
print(f"\n  --- By Pair ---")
for pair in sorted(trades_df['pair'].unique()):
    subset = trades_df[trades_df['pair']==pair]
    w = subset[subset['pnl']>0]
    l = subset[subset['pnl']<=0]
    if len(subset)>0:
        wr = len(w)/len(subset)*100
        pf = w['pnl'].sum()/abs(l['pnl'].sum()) if len(l)>0 else 999
        print(f"  {pair:<12} {len(subset):>4} trades, WR={wr:>5.1f}%, PF={pf:>5.2f}, AvgP&L=${subset['pnl'].mean():>7.2f}")

# By Exit Reason
print(f"\n  --- By Exit Reason ---")
for reason in trades_df['exit_reason'].unique():
    subset = trades_df[trades_df['exit_reason']==reason]
    w = subset[subset['pnl']>0]
    if len(subset)>0:
        print(f"  {reason:<20} {len(subset):>4} trades, WR={len(w)/len(subset)*100:>5.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():>7.2f}, Total=${subset['pnl'].sum():>10,.2f}")

# By Entry Hour
print(f"\n  --- By Entry Hour (UTC) ---")
trades_df['entry_hour'] = pd.to_datetime(trades_df['entry_time']).dt.hour
for hour in sorted(trades_df['entry_hour'].unique()):
    subset = trades_df[trades_df['entry_hour']==hour]
    w = subset[subset['pnl']>0]
    if len(subset)>=5:
        print(f"  Hour {hour:>2}: {len(subset):>4} trades, WR={len(w)/len(subset)*100:>5.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():>7.2f}")

# By Entry Day
print(f"\n  --- By Entry Day ---")
trades_df['entry_day'] = pd.to_datetime(trades_df['entry_time']).dt.day_name()
for day in ['Monday','Tuesday','Wednesday','Thursday','Friday']:
    subset = trades_df[trades_df['entry_day']==day]
    if len(subset)>0:
        w = subset[subset['pnl']>0]
        print(f"  {day:<10} {len(subset):>4} trades, WR={len(w)/len(subset)*100:>5.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():>7.2f}")

# By Distance from EMA200
print(f"\n  --- By Distance from EMA200 ---")
trades_df['dist_bin'] = pd.cut(trades_df['dist_pct'], bins=[0,0.5,1.0,1.5,2.0,3.0,5.0,100])
for bin_name in sorted(trades_df['dist_bin'].dropna().unique()):
    subset = trades_df[trades_df['dist_bin']==bin_name]
    w = subset[subset['pnl']>0]
    if len(subset)>=5:
        print(f"  {str(bin_name):<15} {len(subset):>4} trades, WR={len(w)/len(subset)*100:>5.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():>7.2f}")

# By Bars Held
print(f"\n  --- By Holding Period ---")
trades_df['hold_bin'] = pd.cut(trades_df['bars_held'], bins=[0,5,10,20,30,50,100,200])
for bin_name in sorted(trades_df['hold_bin'].dropna().unique()):
    subset = trades_df[trades_df['hold_bin']==bin_name]
    w = subset[subset['pnl']>0]
    if len(subset)>=5:
        print(f"  {str(bin_name):<15} {len(subset):>4} trades, WR={len(w)/len(subset)*100:>5.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():>7.2f}")

# By Direction
print(f"\n  --- By Direction ---")
for side in [1, -1]:
    subset = trades_df[trades_df['side']==side]
    w = subset[subset['pnl']>0]
    if len(subset)>0:
        label = "LONG" if side==1 else "SHORT"
        print(f"  {label:<6} {len(subset):>4} trades, WR={len(w)/len(subset)*100:>5.1f}%, "
              f"AvgP&L=${subset['pnl'].mean():>7.2f}")

# Top winning and losing trades
print(f"\n  --- Top 10 Winning Trades ---")
top_w = wins.nlargest(10, 'pnl')
for _, t in top_w.iterrows():
    print(f"  {t['pair']:<12} {t['type']:<3} {'LONG' if t['side']==1 else 'SHORT':<5} "
          f"P&L=${t['pnl']:>8.2f}  {t['exit_reason']:<18} held={t['bars_held']:.0f}bars")

print(f"\n  --- Top 10 Losing Trades ---")
top_l = losses.nsmallest(10, 'pnl')
for _, t in top_l.iterrows():
    print(f"  {t['pair']:<12} {t['type']:<3} {'LONG' if t['side']==1 else 'SHORT':<5} "
          f"P&L=${t['pnl']:>8.2f}  {t['exit_reason']:<18} held={t['bars_held']:.0f}bars")

# Consecutive losses analysis
print(f"\n  --- Consecutive Losses ---")
streak=0; max_streak=0; streaks=[]
for _, t in trades_df.iterrows():
    if t['pnl']<=0:
        streak+=1
    else:
        if streak>0: streaks.append(streak)
        streak=0
if streaks:
    print(f"  Max consecutive losses: {max(streaks)}")
    print(f"  Avg consecutive losses: {np.mean(streaks):.1f}")
    print(f"  Consec loss distribution: {pd.Series(streaks).value_counts().sort_index().to_dict()}")
