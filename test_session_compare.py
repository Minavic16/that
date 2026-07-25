"""Compare London-only vs London+NY session performance."""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}
MR_RISK=0.035; MR_RR=2.2; BREAKOUT_ZONE=0.005; CORR_THRESHOLD=0.85; MAX_SAME_CURRENCY=2

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
        'atr':atr_4h.reindex(d30.index,method='ffill').values,'daily':daily,'pip':pip,'pv':pv,'spread':SPREAD.get(pair,2.0)}
    close_series[pair]=d30['close']

ref_pair=max(pdata.keys(), key=lambda p: pdata[p]['n'])
ref=pdata[ref_pair]; n_bars=ref['n']
price_df=pd.DataFrame(close_series); returns_full=price_df.pct_change().dropna(); corr_matrix=returns_full.corr()

def run_session(label, entry_start, entry_end, close_hour):
    def igs(ts):
        h,d=ts.hour,ts.dayofweek
        if d==4 and h>=20: return False
        if d==0 and h<3: return False
        if d>=5: return False
        return entry_start<=h<entry_end
    def is_session(ts):
        return entry_start<=ts.hour<=close_hour

    bal=ACC; peak=ACC; mdd=0; open_pos=[]; wins=0; losses=0; total_pnl=0; win_sum=0; loss_sum=0
    daily_d=None; daily_sb=ACC; n_corr_skip=0

    for i in range(250, n_bars-1):
        ts_now=ref['ts'][i]; today=ts_now.date()
        if daily_d!=today: daily_d=today; daily_sb=bal
        if daily_sb>0 and (daily_sb-bal)/daily_sb>=0.05:
            for pos in open_pos:
                pd_=pdata.get(pos['pair'])
                if pd_ is None or i>=pd_['n']: continue
                ep=pd_['c'][i]-(pos['spread']*0.5+0.3)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl
            open_pos.clear(); continue

        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_cl=pd_['c'][i]; tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False

            if (tr==1 and pd_['lo'][i]<=sl) or (tr==-1 and pd_['h'][i]>=sl):
                pnl=(sl-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                (win_sum if pnl>0 else loss_sum).__class__  # just to avoid lint
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                closed=True
            if not closed and ((tr==1 and pd_['h'][i]>=tp) or (tr==-1 and pd_['lo'][i]<=tp)):
                pnl=(tp-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                closed=True
            if not closed and not is_session(ts_now):
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; wins+=(1 if pnl>0 else 0); losses+=(1 if pnl<=0 else 0); total_pnl+=pnl
                if pnl>0: win_sum+=pnl
                else: loss_sum+=pnl
                closed=True
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
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            skip_pair=False
            for op in active_pairs:
                if pair in corr_matrix.columns and op in corr_matrix.columns:
                    cv=corr_matrix.loc[pair,op]
                    if not np.isnan(cv) and abs(cv)>CORR_THRESHOLD: skip_pair=True; n_corr_skip+=1; break
            if skip_pair: continue
            dist=(c_val-ev)/ev
            if abs(dist)<BREAKOUT_ZONE:
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
                if sl_dist<2*pd_['pip']: continue
                tp_=c_val+sl_dist*MR_RR if tr_==1 else c_val-sl_dist*MR_RR
                ef=c_val+(pd_['spread']*0.5+0.3)*pd_['pip'] if tr_==1 else c_val-(pd_['spread']*0.5+0.3)*pd_['pip']
                sz=ps.compute_position_size(pair=pair,side='BUY' if tr_==1 else 'SELL',entry_price=ef,sl_price=sl_,account_balance_usd=bal,risk_pct=MR_RISK,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':tr_,'entry':ef,'sl':sl_,'tp':tp_,'lot':sz.lot_size,'bar':i,'pip':pd_['pip'],'pv':pd_['pv'],'spread':pd_['spread'],'regime':'mr'})

    total=wins+losses
    wr=wins/total*100 if total>0 else 0
    pf=win_sum/abs(loss_sum) if loss_sum!=0 else 99
    avg=total_pnl/total if total>0 else 0
    avg_w=win_sum/wins if wins>0 else 0
    avg_l=loss_sum/losses if losses>0 else 0
    nm=max((ref['ts'][min(n_bars-1,len(ref['ts'])-1)]-ref['ts'][250]).days/30.4375,1)

    print(f'\n{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')
    print(f'  Trades={total} ({total/nm:.0f}/mo) WR={wr:.1f}% PF={pf:.2f} MDD={mdd*100:.1f}%')
    print(f'  Final=${bal:,.0f} Return={(bal/ACC-1)*100:.0f}%')
    print(f'  AvgP&L=${avg:.2f} AvgWin=${avg_w:.2f} AvgLoss=${avg_l:.2f}')
    print(f'  Corr skipped: {n_corr_skip}')

print("="*60)
print("  SESSION COMPARISON: LONDON ONLY vs LONDON+NY")
print("="*60)

run_session("London ONLY: enter 7-15, close 16", 7, 16, 16)
run_session("London+NY: enter 7-19, close 20 (original)", 7, 20, 20)
