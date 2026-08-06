"""
TF Strategy Derived from Proven MR — Complementary Regime
MR regime: price NEAR 4H EMA200 (within 0.5%) → mean reversion
TF regime: price FAR from 4H EMA200 (> 0.5%) → trend following

Same core indicators (4H EMA200, EMA50, daily candle) but opposite logic:
- MR: Buy when oversold near EMA200, exit at session close
- TF: Buy on breakout ABOVE EMA200 zone, trail stop, exit when price returns to EMA200
"""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','AUD/USD','USD/CHF','GBP/JPY','EUR/JPY','AUD/JPY']
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500; RISK=0.010
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'GBP/JPY':3.0,'AUD/JPY':2.0,'CAD/JPY':2.5,'NZD/JPY':3.0,'EUR/AUD':2.0,'EUR/CAD':2.5,'GBP/AUD':3.5,'GBP/CAD':3.5,'AUD/CAD':2.0,'AUD/CHF':2.5,'NZD/CHF':3.0,'CAD/CHF':3.0}

# TF-specific params
BREAKOUT_ZONE = 0.005    # 0.5% from EMA200 = breakout zone
TRAIL_ATR_MULT = 3.0     # Wider trailing for bigger moves
MAX_HOLD = 200           # Max 200 bars (100 hours on 30m)
MIN_HOLD = 12            # Min 12 bars (6 hours) before trailing

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

def run_sim(start, end, max_conc=5, risk=RISK):
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

        # ATR for trailing stop
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
    n_sl=0; n_tp=0; n_sc=0; n_mh=0; n_dl=0; n_rej=0; n_trail=0

    for i in range(250, n_bars-1):
        ts_now=ref['ts'][i]
        today=ts_now.date()
        if daily_d!=today: daily_d=today; daily_sb=bal

        # Daily loss limit
        if daily_sb>0 and (daily_sb-bal)/daily_sb>=0.03:
            for pos in open_pos:
                pd_=pdata.get(pos['pair'])
                if pd_ is None or i>=pd_['n']: continue
                ep=pd_['c'][i]-(pos['spread']*0.5+0.3)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_dl+=1
            open_pos.clear(); continue

        # --- EXIT LOGIC ---
        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_lo=pd_['lo'][i]; bar_hi=pd_['h'][i]; bar_cl=pd_['c'][i]
            tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False

            # Stop loss
            if tr==1 and bar_lo<=sl:
                pnl=(sl-pos['entry'])/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_sl+=1; closed=True
            elif tr==-1 and bar_hi>=sl:
                pnl=(pos['entry']-sl)/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_sl+=1; closed=True

            # Take profit
            if not closed and tr==1 and bar_hi>=tp:
                pnl=(tp-pos['entry'])/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_tp+=1; closed=True
            elif not closed and tr==-1 and bar_lo<=tp:
                pnl=(pos['entry']-tp)/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_tp+=1; closed=True

            # TRAILING STOP: Update stop to breakeven + ATR when price moves in our favor
            if not closed and (i-pos['bar']) >= MIN_HOLD:
                cur_atr = pd_['atr'][i]
                if not np.isnan(cur_atr) and cur_atr > 0:
                    if tr == 1:
                        new_sl = bar_cl - TRAIL_ATR_MULT * cur_atr
                        if new_sl > sl:
                            pos['sl'] = new_sl
                            n_trail += 1
                    else:
                        new_sl = bar_cl + TRAIL_ATR_MULT * cur_atr
                        if new_sl < sl:
                            pos['sl'] = new_sl
                            n_trail += 1

            # NO SESSION CLOSE EXIT for TF — let trends develop

            # MAX HOLD EXIT
            if not closed and (i-pos['bar'])>=MAX_HOLD:
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); n_mh+=1; closed=True

            # TF EXIT: Price returns to EMA200 zone (trend exhausted)
            if not closed:
                ev=pd_['e200'][i]
                if not np.isnan(ev):
                    dist_pct = abs(bar_cl - ev) / ev
                    if dist_pct < BREAKOUT_ZONE * 0.3:  # Price returned to near EMA200
                        ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                        pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                        bal+=pnl; pnls.append(pnl); n_sc+=1; closed=True

            if not closed: remaining.append(pos)
        open_pos=remaining

        bal=max(bal,1.0)
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd

        # --- ENTRY LOGIC (TF: Trend Following) ---
        if not igs(ts_now) or len(open_pos)>=max_conc: continue
        for pair in PAIRS:
            if len(open_pos)>=max_conc: break
            if any(p['pair']==pair for p in open_pos): continue
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_['n']: continue
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]; cur_atr=pd_['atr'][i]
            if np.isnan(ev) or np.isnan(e5) or np.isnan(cur_atr) or cur_atr==0: continue

            # TF REGIME: Price must be FAR from EMA200 (trending)
            dist_from_ema = (c_val - ev) / ev

            # LONG: Price above EMA200 by BREAKOUT_ZONE+ and above EMA50
            if dist_from_ema > BREAKOUT_ZONE and c_val > e5:
                # Confirm breakout: price broke above recent 20-bar high
                recent_high = max(pd_['h'][max(0,i-20):i])
                if c_val <= recent_high * 1.001: continue  # Not a breakout

                # Daily candle must be green (bullish)
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if not dg: continue

                # Entry
                pip=pd_['pip']
                entry_fill=c_val+(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill - TRAIL_ATR_MULT * cur_atr  # ATR-based stop
                tp=entry_fill + 3 * TRAIL_ATR_MULT * cur_atr  # 3x trailing ATR target

                sl_dist=abs(entry_fill-sl)
                if sl_dist<2*pip: continue

                sz=ps.compute_position_size(pair=pair,side='BUY',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: n_rej+=1; continue
                open_pos.append({'pair':pair,'trend':1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread']})

            # SHORT: Price below EMA200 by BREAKOUT_ZONE+ and below EMA50
            elif dist_from_ema < -BREAKOUT_ZONE and c_val < e5:
                # Confirm breakout: price broke below recent 20-bar low
                recent_low = min(pd_['lo'][max(0,i-20):i])
                if c_val >= recent_low * 0.999: continue  # Not a breakout

                # Daily candle must be red (bearish)
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if dg: continue

                # Entry
                pip=pd_['pip']
                entry_fill=c_val-(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill + TRAIL_ATR_MULT * cur_atr  # ATR-based stop
                tp=entry_fill - 3 * TRAIL_ATR_MULT * cur_atr  # 3x trailing ATR target

                sl_dist=abs(sl-entry_fill)
                if sl_dist<2*pip: continue

                sz=ps.compute_position_size(pair=pair,side='SELL',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: n_rej+=1; continue
                open_pos.append({'pair':pair,'trend':-1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread']})

    # Metrics
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
        'exits': {'SL':n_sl,'TP':n_tp,'SC':n_sc,'MH':n_mh,'DL':n_dl,'Trail':n_trail},
        'rejected': n_rej, 'n_months': nm,
    }

def pr(r, label):
    print(f"  {label}")
    print(f"    Trades={r['n']:,} ({r['tpm']:.0f}/mo) WR={r['wr']:.1f}% PF={r['pf']:.1f} MDD={r['mdd']:.2f}%")
    print(f"    Final=${r['final']:,.0f} Return={r['total_return']:.1f}% CAGR={r['cagr']:.1f}%")
    print(f"    AvgP&L=${r['avg_pnl']:.2f} AvgWin=${r['avg_win']:.2f} AvgLoss=${r['avg_loss']:.2f}")
    print(f"    Exits={r['exits']} Non-compounded monthly={r['monthly_approx']:.2f}%")

print("="*80)
print("  TF STRATEGY — Derived from Proven MR (Complementary Regime)")
print("="*80)

# Full period
r = run_sim('2018-01-01','2026-07-19', max_conc=5)
if r: pr(r, "TF FULL PERIOD (2018-2026)")

# Walk-forward
print()
is_r = run_sim('2018-01-01','2022-12-31', max_conc=5)
oos_r = run_sim('2023-01-01','2026-07-19', max_conc=5)
if is_r: pr(is_r, "IS  (2018-2022)")
if oos_r: pr(oos_r, "OOS (2023-2026)")
if is_r and oos_r:
    print(f"    WR drop: {is_r['wr']-oos_r['wr']:.1f}pp")
