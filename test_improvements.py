"""
Improvement test — runs full-period sims (2022-2026), extracts OOS results.
This ensures proper account buildup from IS before measuring OOS.
"""
import pickle, numpy as np, pandas as pd, time
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}
MR_RISK=0.035; MR_RR=2.2
TF_RISK=0.022; BREAKOUT_ZONE=0.005; TRAIL_ATR_MULT=2.5; TF_MAX_HOLD=100; TF_MIN_HOLD=8; TF_TIME_STOP=30
CORR_THRESHOLD=0.85; MAX_SAME_CURRENCY=2

def igs(ts, sessions=SESSIONS):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in sessions.items():
        if s2<=h<e: return True
    return False

def get_currencies(pair):
    return pair.split('/')

def check_currency_overlap(open_positions, new_pair):
    new_base, new_quote = get_currencies(new_pair)
    currency_count = {}
    for pos in open_positions:
        b, q = get_currencies(pos['pair'])
        currency_count[b] = currency_count.get(b, 0) + 1
        currency_count[q] = currency_count.get(q, 0) + 1
    return currency_count.get(new_base, 0) >= MAX_SAME_CURRENCY or currency_count.get(new_quote, 0) >= MAX_SAME_CURRENCY

def load_data():
    pdata={}; close_series={}
    for pair in PAIRS:
        pk=PAIR_FILES[pair]
        try:
            with open(f'/root/data/{pk}.pkl','rb') as f: raw=pickle.load(f)
        except: continue
        ts_raw=raw[pair]; ts=ts_raw.index; c=ts_raw['close'].values.astype(float)
        h_=ts_raw['high'].values.astype(float); l_=ts_raw['low'].values.astype(float)
        sp=SPREAD.get(pair,1.0); pip=0.01 if 'JPY' not in pair else 0.01; pv=pip*100000
        ema200=pd.Series(c).ewm(span=200,adjust=False).mean().values
        ema50=pd.Series(c).ewm(span=50,adjust=False).mean().values
        atr=pd.Series(np.maximum(h_-l_,np.maximum(abs(h_-np.roll(c,1)),abs(l_-np.roll(c,1))))).ewm(span=14,adjust=False).mean().values
        daily=ts_raw.resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        pdata[pair]={'ts':ts,'c':c,'h':h_,'lo':l_,'e200':ema200,'e50':ema50,'atr':atr,'pip':pip,'pv':pv,'spread':sp,'daily':daily,'n':len(ts)}
        close_series[pair]=pd.Series(c,index=ts)
    price_df = pd.DataFrame(close_series)
    corr_matrix = price_df.pct_change().dropna().corr()
    return pdata, corr_matrix

def run_sim(pdata, corr_matrix, tf_enabled=True, mr_risk=MR_RISK, exclude_pairs=None, exclude_hours=None, sessions=None):
    if exclude_pairs is None: exclude_pairs = set()
    if exclude_hours is None: exclude_hours = set()
    if sessions is None: sessions = SESSIONS
    active_pairs = [p for p in PAIRS if p not in exclude_pairs]
    ref_pair=max(active_pairs, key=lambda p: pdata[p]['n'])
    ref=pdata[ref_pair]; n_bars=ref['n']
    bal=ACC; peak=ACC; mdd=0; open_pos=[]; pnls=[]; daily_sb=ACC; daily_d=None
    n_mr=0; n_tf=0; n_corr_skip=0
    # OOS boundaries
    oos_start=pd.Timestamp('2025-01-01').tz_localize('UTC')
    oos_end=pd.Timestamp('2026-07-19').tz_localize('UTC')
    oos_pnls=[]; oos_bal_start=None; oos_bal_end=None; oos_peak=0; oos_mdd=0
    for i in range(250, n_bars-1):
        ts_now=ref['ts'][i]; today=ts_now.date()
        if daily_d!=today: daily_d=today; daily_sb=bal
        if daily_sb>0 and (daily_sb-bal)/daily_sb>=0.05:
            for pos in open_pos:
                pd_=pdata.get(pos['pair'])
                if pd_ is None or i>=pd_['n']: continue
                ep=pd_['c'][i]-(pos['spread']*0.5+0.3)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*pos['trend']/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl)
                if ts_now>=oos_start: oos_pnls.append(pnl)
            open_pos.clear(); continue
        remaining=[]
        for pos in open_pos:
            pd_=pdata.get(pos['pair'])
            if pd_ is None or i>=pd_['n']: remaining.append(pos); continue
            bar_lo=pd_['lo'][i]; bar_hi=pd_['h'][i]; bar_cl=pd_['c'][i]
            tr=pos['trend']; sl=pos['sl']; tp=pos['tp']; closed=False; regime=pos['regime']
            pnl=0
            if tr==1 and bar_lo<=sl:
                pnl=(sl-pos['entry'])/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            elif tr==-1 and bar_hi>=sl:
                pnl=(pos['entry']-sl)/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            if not closed and tr==1 and bar_hi>=tp:
                pnl=(tp-pos['entry'])/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            elif not closed and tr==-1 and bar_lo<=tp:
                pnl=(pos['entry']-tp)/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            if not closed and regime=='tf' and (i-pos['bar'])>=TF_MIN_HOLD:
                cur_atr=pd_['atr'][i]
                if not np.isnan(cur_atr) and cur_atr>0:
                    if tr==1:
                        new_sl=bar_cl-TRAIL_ATR_MULT*cur_atr
                        if new_sl>sl: pos['sl']=new_sl
                    else:
                        new_sl=bar_cl+TRAIL_ATR_MULT*cur_atr
                        if new_sl<sl: pos['sl']=new_sl
            if not closed and regime=='mr' and not igs(ref['ts'][i], sessions):
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            if not closed and regime=='tf' and (i-pos['bar'])>=TF_TIME_STOP and (i-pos['bar'])<TF_MAX_HOLD:
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            if not closed and regime=='tf' and (i-pos['bar'])>=TF_MAX_HOLD:
                ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                bal+=pnl; pnls.append(pnl); closed=True
            if not closed and regime=='tf':
                ev=pd_['e200'][i]
                if not np.isnan(ev) and abs(bar_cl-ev)/ev<BREAKOUT_ZONE*0.4:
                    ep=bar_cl-(pos['spread']*0.5+0.3)*pos['pip'] if tr==1 else bar_cl+(pos['spread']*0.5+0.3)*pos['pip']
                    pnl=(ep-pos['entry'])*tr/pos['pip']*pos['pv']*pos['lot']-pos['lot']*COMMISSION
                    bal+=pnl; pnls.append(pnl); closed=True
            if pnl!=0 and ts_now>=oos_start: oos_pnls.append(pnl)
            if not closed: remaining.append(pos)
        open_pos=remaining
        bal=max(bal,1.0)
        if bal>peak: peak=bal
        dd=(peak-bal)/peak if peak>0 else 0
        if dd>mdd: mdd=dd
        # Track OOS balance
        if ts_now>=oos_start and ts_now<=oos_end:
            if oos_bal_start is None: oos_bal_start=bal
            oos_bal_end=bal
            if bal>oos_peak: oos_peak=bal
            ood=(oos_peak-bal)/oos_peak if oos_peak>0 else 0
            if ood>oos_mdd: oos_mdd=ood
        if not igs(ts_now, sessions): continue
        active_pos = [pos['pair'] for pos in open_pos]
        for pair in active_pairs:
            if len(open_pos)>=20: break
            if any(p['pair']==pair for p in open_pos): continue
            if check_currency_overlap(open_pos, pair): n_corr_skip+=1; continue
            pd_=pdata.get(pair)
            if pd_ is None or i>=pd_['n']: continue
            c_val=pd_['c'][i]; ev=pd_['e200'][i]; e5=pd_['e50'][i]; cur_atr=pd_['atr'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            pip=pd_['pip']
            if active_pos:
                skip_pair=False
                for open_pair in active_pos:
                    if pair in corr_matrix.columns and open_pair in corr_matrix.columns:
                        corr_val=corr_matrix.loc[pair,open_pair]
                        if not np.isnan(corr_val) and abs(corr_val)>CORR_THRESHOLD:
                            skip_pair=True; n_corr_skip+=1; break
                if skip_pair: continue
            if ts_now.hour in exclude_hours: continue
            dist_from_ema=(c_val-ev)/ev
            if abs(dist_from_ema) < BREAKOUT_ZONE:
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
                sz=ps.compute_position_size(pair=pair,side='BUY' if tr==1 else 'SELL',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=mr_risk,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':tr,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'mr'})
                n_mr+=1
            elif tf_enabled and dist_from_ema > BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr>0:
                if c_val<=e5: continue
                recent_high=max(pd_['h'][max(0,i-20):i])
                if c_val<=recent_high*1.002: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if not dg: continue
                entry_fill=c_val+(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill-TRAIL_ATR_MULT*cur_atr
                tp=entry_fill+2.5*TRAIL_ATR_MULT*cur_atr
                sl_dist=abs(entry_fill-sl)
                if sl_dist<2*pip: continue
                sz=ps.compute_position_size(pair=pair,side='BUY',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=TF_RISK,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})
                n_tf+=1
            elif tf_enabled and dist_from_ema < -BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr>0:
                if c_val>=e5: continue
                recent_low=min(pd_['lo'][max(0,i-20):i])
                if c_val>=recent_low*0.998: continue
                d_ts=pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg=pd_['daily'].loc[d_ts,'close']>pd_['daily'].loc[d_ts,'open']
                if dg: continue
                entry_fill=c_val-(pd_['spread']*0.5+0.3)*pip
                sl=entry_fill+TRAIL_ATR_MULT*cur_atr
                tp=entry_fill-2.5*TRAIL_ATR_MULT*cur_atr
                sl_dist=abs(sl-entry_fill)
                if sl_dist<2*pip: continue
                sz=ps.compute_position_size(pair=pair,side='SELL',entry_price=entry_fill,sl_price=sl,account_balance_usd=bal,risk_pct=TF_RISK,leverage=LEV,margin_safety=0.5,snap=SNAP,lot_step=0.01,min_lot=0.01,max_lot=10.0,existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':-1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})
                n_tf+=1
    # OOS stats
    if not oos_pnls or oos_bal_start is None: return None, None
    ow=sum(1 for p in oos_pnls if p>0); ol=sum(1 for p in oos_pnls if p<=0)
    ogw=sum(p for p in oos_pnls if p>0); ogl=abs(sum(p for p in oos_pnls if p<=0))
    # ~18 months OOS
    oos_nm=18.5
    oos={
        'n':len(oos_pnls), 'w':ow, 'l':ol,
        'wr': ow/(ow+ol)*100 if (ow+ol)>0 else 0,
        'pf': ogw/ogl if ogl>0 else 99,
        'mdd': oos_mdd*100,
        'bal_start': oos_bal_start, 'bal_end': oos_bal_end,
        'avg_pnl': np.mean(oos_pnls),
        'avg_win': np.mean([p for p in oos_pnls if p>0]) if ow>0 else 0,
        'avg_loss': np.mean([p for p in oos_pnls if p<=0]) if ol>0 else 0,
        'tpm': len(oos_pnls)/oos_nm,
        'monthly_approx': len(oos_pnls)/oos_nm * np.mean(oos_pnls) / oos_bal_start * 100 if oos_bal_start>0 else 0,
        'mr': n_mr, 'tf': n_tf,
    }
    # Full period stats
    fw=sum(1 for p in pnls if p>0); fl=sum(1 for p in pnls if p<=0)
    fgw=sum(p for p in pnls if p>0); fgl=abs(sum(p for p in pnls if p<=0))
    fnm=max((ref['ts'][min(n_bars-1,len(ref['ts'])-1)]-ref['ts'][250]).days/30.4375,1)
    full={
        'n':len(pnls), 'wr': fw/(fw+fl)*100 if (fw+fl)>0 else 0,
        'pf': fgw/fgl if fgl>0 else 99, 'mdd': mdd*100,
        'final': bal, 'avg_pnl': np.mean(pnls),
        'tpm': len(pnls)/fnm,
    }
    return oos, full

print("="*80)
print("  IMPROVEMENT TEST — OOS (2025-2026), full IS buildup", flush=True)
print("="*80, flush=True)

print("\n  Loading data...", flush=True)
t0=time.time()
pdata, corr_matrix = load_data()
print(f"  Loaded in {time.time()-t0:.1f}s\n", flush=True)

scenarios = [
    ("0: Baseline (MR+TF)", dict()),
    ("1: MR Only", dict(tf_enabled=False)),
    ("2: MR Only, London", dict(tf_enabled=False, sessions={'london':(7,16)})),
    ("3: MR Only, London, 5% risk", dict(tf_enabled=False, mr_risk=0.05, sessions={'london':(7,16)})),
    ("4: MR Only, Lon, NoBadHrs", dict(tf_enabled=False, sessions={'london':(7,16)}, exclude_hours={11,21})),
    ("5: MR Only, Lon, NoWeak", dict(tf_enabled=False, sessions={'london':(7,16)}, exclude_pairs={'AUD/CAD','NZD/USD','AUD/JPY'})),
    ("6: MR Only, Lon, 5%, NoWeak", dict(tf_enabled=False, mr_risk=0.05, sessions={'london':(7,16)}, exclude_pairs={'AUD/CAD','NZD/USD','AUD/JPY'})),
]

results = {}
for name, params in scenarios:
    print(f"  {name}...", end='', flush=True)
    t0=time.time()
    oos, full = run_sim(pdata, corr_matrix, **params)
    elapsed=time.time()-t0
    results[name] = (oos, full)
    if oos:
        ev_pct = oos['avg_pnl'] / oos['bal_start'] * 100
        print(f" {elapsed:.0f}s | OOS: {oos['n']}t WR={oos['wr']:.1f}% PF={oos['pf']:.1f} MDD={oos['mdd']:.2f}% AvgP&L=${oos['avg_pnl']:.0f} EV={ev_pct:.1f}%", flush=True)
    else:
        print(f" {elapsed:.0f}s | NO TRADES", flush=True)

print("\n" + "="*80)
print("  OOS RESULTS (2025-2026)")
print("="*80)
print(f"\n  {'Scenario':<35s} {'Trades':>6s} {'WR%':>6s} {'PF':>5s} {'MDD%':>6s} {'AvgP&L':>8s} {'EV%':>6s} {'$/mo':>9s} {'BalEnd':>12s}")
print(f"  {'-'*35} {'-'*6} {'-'*6} {'-'*5} {'-'*6} {'-'*8} {'-'*6} {'-'*9} {'-'*12}")
for name, (oos, full) in results.items():
    if oos is None:
        print(f"  {name:<35s} {'NONE':>6s}")
    else:
        ev_pct = oos['avg_pnl'] / oos['bal_start'] * 100
        monthly_val = oos['avg_pnl'] * oos['tpm']
        print(f"  {name:<35s} {oos['n']:>6d} {oos['wr']:>5.1f}% {oos['pf']:>5.1f} {oos['mdd']:>5.2f}% ${oos['avg_pnl']:>7,.0f} {ev_pct:>5.1f}% ${monthly_val:>8,.0f} ${oos['bal_end']:>11,.0f}")

print("\n" + "="*80)
print("  FULL PERIOD (2022-2026)")
print("="*80)
print(f"\n  {'Scenario':<35s} {'Trades':>6s} {'WR%':>6s} {'PF':>5s} {'MDD%':>6s} {'AvgP&L':>8s} {'Final$':>12s}")
print(f"  {'-'*35} {'-'*6} {'-'*6} {'-'*5} {'-'*6} {'-'*8} {'-'*12}")
for name, (oos, full) in results.items():
    if full is None:
        print(f"  {name:<35s} {'NONE':>6s}")
    else:
        print(f"  {name:<35s} {full['n']:>6d} {full['wr']:>5.1f}% {full['pf']:>5.1f} {full['mdd']:>5.2f}% ${full['avg_pnl']:>7,.0f} ${full['final']:>11,.0f}")
