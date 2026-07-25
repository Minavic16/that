"""
COMBINED STRATEGY: MR + TF (Complementary Regimes)
MR: Price NEAR 4H EMA200 → mean reversion (session close exit)
TF: Price FAR from 4H EMA200 → trend following (trailing stop exit)

Same core indicators, different regime detection, different exits.
"""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}

# MR params
MR_RISK=0.050
MR_RR=2.0

# TF params
TF_RISK=0.035
BREAKOUT_ZONE=0.005
TRAIL_ATR_MULT=2.0
TF_MAX_HOLD=100
TF_MIN_HOLD=6

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

def run_sim(start, end, max_conc=8):
    pdata={}
    for pair in PAIRS:
        pk=pair.replace('/','_')
        with open(f'/root/data/{pk}.pkl','rb') as f: raw=pickle.load(f)
        df=raw.get(pair)
        if df is None: continue
        idx=pd.to_datetime(df.index); idx=idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index=idx; df=df[df.index>=start]; df=df[df.index<=end]
        if len(df)<500: continue
        pip=ps.pip_size_for_pair(pair); pv=ps.pip_value_per_lot(pair,SNAP)
        d30=df[['open','high','low','close','volume']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna(subset=['close'])
        d4h=df[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        daily=df[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        e200=d4h['close'].ewm(span=200,adjust=False).mean()
        e50=d4h['close'].ewm(span=50,adjust=False).mean()

        # 4H ATR
        tr1=d4h['high']-d4h['low']
        tr2=abs(d4h['high']-d4h['close'].shift(1))
        tr3=abs(d4h['low']-d4h['close'].shift(1))
        tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
        atr_4h=tr.rolling(14).mean()

        pdata[pair]={
            'c':d30['close'].values,'h':d30['high'].values,'lo':d30['low'].values,
            'o':d30['open'].values,'ts':d30.index,'n':len(d30),
            'e200':e200.reindex(d30.index,method='ffill').values,
            'e50':e50.reindex(d30.index,method='ffill').values,
            'atr':atr_4h.reindex(d30.index,method='ffill').values,
            'daily':daily,'pip':pip,'pv':pv,'spread':SPREAD.get(pair,2.0),
        }

    if not pdata: return None
    ref_pair=max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref=pdata[ref_pair]; n_bars=ref['n']

    bal=ACC; peak=ACC; mdd=0; open_pos=[]; pnls=[]; daily_sb=ACC; daily_d=None
    n_mr_sl=0; n_mr_tp=0; n_mr_sc=0; n_tf_sl=0; n_tf_tp=0; n_tf_sc=0; n_tf_mh=0; n_dl=0
    mr_trades=0; tf_trades=0

    for i in range(250, n_bars-1):
        ts_now=ref['ts'][i]
        today=ts_now.date()
        if daily_d!=today: daily_d=today; daily_sb=bal

        # Daily loss limit (5% for higher returns)
        if daily_sb>0 and (daily_sb-bal)/daily_sb>=0.05:
            for pos in open_pos:
                pd_=pdata.get(pos['pair'])
                if pd_ is None or i>=pd_['n']: continue
                ep=pd_['c'][i]-(pos['spread']*0.5+0.3)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_dl+=1
            open_pos.clear(); continue

        # --- EXITS ---
        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_lo=pd_['lo'][i]; bar_hi=pd_['h'][i]; bar_cl=pd_['c'][i]
            tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False
            regime=pos['regime']

            # Stop loss
            if tr==1 and bar_lo<=sl:
                pnl=(sl-pos['entry'])/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl)
                if regime=='mr': n_mr_sl+=1
                else: n_tf_sl+=1
                closed=True
            elif tr==-1 and bar_hi>=sl:
                pnl=(pos['entry']-sl)/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl)
                if regime=='mr': n_mr_sl+=1
                else: n_tf_sl+=1
                closed=True

            # Take profit
            if not closed and tr==1 and bar_hi>=tp:
                pnl=(tp-pos['entry'])/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl)
                if regime=='mr': n_mr_tp+=1
                else: n_tf_tp+=1
                closed=True
            elif not closed and tr==-1 and bar_lo<=tp:
                pnl=(pos['entry']-tp)/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl)
                if regime=='mr': n_mr_tp+=1
                else: n_tf_tp+=1
                closed=True

            # TF: TRAILING STOP
            if not closed and regime=='tf' and (i-pos['bar'])>=TF_MIN_HOLD:
                cur_atr=pd_['atr'][i]
                if not np.isnan(cur_atr) and cur_atr>0:
                    if tr==1:
                        new_sl=bar_cl-TRAIL_ATR_MULT*cur_atr
                        if new_sl>sl: pos['sl']=new_sl
                    else:
                        new_sl=bar_cl+TRAIL_ATR_MULT*cur_atr
                        if new_sl<sl: pos['sl']=new_sl

            # MR: SESSION CLOSE EXIT
            if not closed and regime=='mr' and not igs(ref['ts'][i]):
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_mr_sc+=1; closed=True

            # TF: MAX HOLD EXIT
            if not closed and regime=='tf' and (i-pos['bar'])>=TF_MAX_HOLD:
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_tf_mh+=1; closed=True

            # TF: TREND REVERSAL (price returns to EMA200)
            if not closed and regime=='tf':
                ev=pd_['e200'][i]
                if not np.isnan(ev):
                    dist_pct=abs(bar_cl-ev)/ev
                    if dist_pct<BREAKOUT_ZONE*0.4:  # Exit earlier
                        ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                        pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                        bal+=pnl; pnls.append(pnl); n_tf_sc+=1; closed=True

            if not closed: remaining.append(pos)
        open_pos=remaining

        bal=max(bal,1.0)
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd

        # --- ENTRIES ---
        if not igs(ts_now) or len(open_pos)>=max_conc: continue
        for pair in PAIRS:
            if len(open_pos)>=max_conc: break
            if any(p['pair']==pair for p in open_pos): continue
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_['n']: continue
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]; cur_atr=pd_['atr'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            pip=pd_['pip']

            dist_from_ema=(c_val-ev)/ev

            # ==========================================
            # REGIME DETECTION
            # ==========================================

            if abs(dist_from_ema) < BREAKOUT_ZONE:
                # === MR REGIME: Price near EMA200 ===
                tr=1 if c_val>ev else -1
                if tr==1 and c_val<e5*0.997: continue  # Tighter EMA50 filter
                if tr==-1 and c_val>e5*1.003: continue
                if tr==1:
                    if not (c_val<ev*1.004 and c_val>ev*0.996): continue  # Tighter zone
                    if max(pd_['h'][max(0,i-20):i])<=c_val*1.003: continue  # Bigger pullback required
                else:
                    if not (c_val>ev*0.996 and c_val<ev*1.004): continue
                    if min(pd_['lo'][max(0,i-20):i])>=c_val*0.997: continue

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
                sz=ps.compute_position_size(pair=pair,side='BUY' if tr==1 else 'SELL',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=MR_RISK,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':tr,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'mr'})
                mr_trades+=1

            elif dist_from_ema > BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr>0:
                # === TF REGIME: Price above EMA200 ===
                if c_val<=e5: continue
                recent_high=max(pd_['h'][max(0,i-20):i])
                if c_val<=recent_high*1.002: continue  # Bigger breakout required
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if not dg: continue

                entry_fill=c_val+(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill-TRAIL_ATR_MULT*cur_atr
                tp=entry_fill+2.5*TRAIL_ATR_MULT*cur_atr  # 2.5x target
                sl_dist=abs(entry_fill-sl)
                if sl_dist<2*pip: continue
                sz=ps.compute_position_size(pair=pair,side='BUY',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=TF_RISK,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})
                tf_trades+=1

            elif dist_from_ema < -BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr>0:
                # === TF REGIME: Price below EMA200 ===
                if c_val>=e5: continue
                recent_low=min(pd_['lo'][max(0,i-20):i])
                if c_val>=recent_low*0.998: continue  # Bigger breakout required
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if dg: continue

                entry_fill=c_val-(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill+TRAIL_ATR_MULT*cur_atr
                tp=entry_fill-2.5*TRAIL_ATR_MULT*cur_atr  # 2.5x target
                sl_dist=abs(sl-entry_fill)
                if sl_dist<2*pip: continue
                sz=ps.compute_position_size(pair=pair,side='SELL',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=TF_RISK,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':-1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})
                tf_trades+=1

    if not pnls: return None
    w=sum(1 for p in pnls if p>0); l=sum(1 for p in pnls if p<=0)
    gw=sum(p for p in pnls if p>0); gl=abs(sum(p for p in pnls if p<=0))
    nm=max((ref['ts'][min(n_bars-1,len(ref['ts'])-1)]-ref['ts'][250]).days/30.4375,1)

    return {
        'n':len(pnls), 'w':w, 'l':l,
        'wr': w/(w+l)*100 if (w+l)>0 else 0,
        'pf': gw/gl if gl>0 else 99,
        'mdd': mdd*100,
        'final': bal, 'total_return': (bal/ACC-1)*100,
        'avg_pnl': np.mean(pnls),
        'avg_win': np.mean([p for p in pnls if p>0]) if w>0 else 0,
        'avg_loss': np.mean([p for p in pnls if p<=0]) if l>0 else 0,
        'tpm': len(pnls)/nm,
        'monthly_approx': len(pnls)/nm * np.mean(pnls) / ACC * 100,
        'cagr': ((bal/ACC)**(1/nm)-1)*100,
        'mr_trades': mr_trades, 'tf_trades': tf_trades,
        'exits': {'MR_SL':n_mr_sl,'MR_TP':n_mr_tp,'MR_SC':n_mr_sc,'TF_SL':n_tf_sl,'TF_TP':n_tf_tp,'TF_SC':n_tf_sc,'TF_MH':n_tf_mh,'DL':n_dl},
    }

def pr(r, label):
    print(f"\n  {label}")
    print(f"    Trades={r['n']:,} ({r['tpm']:.0f}/mo) WR={r['wr']:.1f}% PF={r['pf']:.1f} MDD={r['mdd']:.2f}%")
    print(f"    Final=${r['final']:,.0f} Return={r['total_return']:.1f}% CAGR={r['cagr']:.1f}%")
    print(f"    AvgP&L=${r['avg_pnl']:.2f} AvgWin=${r['avg_win']:.2f} AvgLoss=${r['avg_loss']:.2f}")
    print(f"    MR trades: {r['mr_trades']}, TF trades: {r['tf_trades']}")
    print(f"    Exits={r['exits']}")

print("="*80)
print("  COMBINED: MR + TF (Complementary Regimes)")
print("  MR: Near EMA200 → session close exit | TF: Far from EMA200 → trailing stop")
print("="*80)

r = run_sim('2018-01-01','2026-07-19', max_conc=10)
if r: pr(r, "FULL PERIOD (2018-2026)")

print()
is_r = run_sim('2018-01-01','2022-12-31', max_conc=10)
oos_r = run_sim('2023-01-01','2026-07-19', max_conc=10)
if is_r: pr(is_r, "IS  (2018-2022)")
if oos_r: pr(oos_r, "OOS (2023-2026)")
if is_r and oos_r:
    print(f"\n    WR drop: {is_r['wr']-oos_r['wr']:.1f}pp")
