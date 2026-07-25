"""
Time-Based Stop Analysis
Tracks bars-held for every trade (MR + TF), analyzes winners vs losers,
and tests different time-stop thresholds to find optimal parameter.
"""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD','EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY','USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD','EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY','AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}

MR_RISK=0.035; MR_RR=2.2
TF_RISK=0.022; BREAKOUT_ZONE=0.005; TRAIL_ATR_MULT=2.5; TF_MAX_HOLD=100; TF_MIN_HOLD=8
CORR_THRESHOLD=0.85; MAX_SAME_CURRENCY=2

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

def get_currencies(pair):
    base, quote = pair.split('/')
    return base, quote

def check_currency_overlap(open_positions, new_pair):
    new_base, new_quote = get_currencies(new_pair)
    currency_count = {}
    for pos in open_positions:
        b, q = get_currencies(pos['pair'])
        currency_count[b] = currency_count.get(b, 0) + 1
        currency_count[q] = currency_count.get(q, 0) + 1
    if currency_count.get(new_base, 0) >= MAX_SAME_CURRENCY:
        return True
    if currency_count.get(new_quote, 0) >= MAX_SAME_CURRENCY:
        return True
    return False


def run_sim_with_trade_log(start, end, max_conc=20):
    """Run simulation and return detailed trade log with bars_held for each trade."""
    pdata = {}
    close_series = {}

    for pair in PAIRS:
        pk = PAIR_FILES[pair]
        with open(f'/root/data/{pk}.pkl', 'rb') as f:
            raw = pickle.load(f)
        df = raw.get(pair)
        if df is None: continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index = idx
        df = df[df.index >= start]; df = df[df.index <= end]
        if len(df) < 500: continue
        pip = ps.pip_size_for_pair(pair); pv = ps.pip_value_per_lot(pair, SNAP)
        d30 = df[['open','high','low','close','volume']].resample('30min').agg({
            'open':'first','high':'max','low':'min','close':'last','volume':'sum'
        }).dropna(subset=['close'])
        d4h = df[['open','high','low','close']].resample('4h').agg({
            'open':'first','high':'max','low':'min','close':'last'
        }).dropna(subset=['close'])
        daily = df[['open','high','low','close']].resample('1D').agg({
            'open':'first','high':'max','low':'min','close':'last'
        }).dropna(subset=['close'])
        e200 = d4h['close'].ewm(span=200, adjust=False).mean()
        e50 = d4h['close'].ewm(span=50, adjust=False).mean()

        tr1 = d4h['high'] - d4h['low']
        tr2 = abs(d4h['high'] - d4h['close'].shift(1))
        tr3 = abs(d4h['low'] - d4h['close'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_4h = tr.rolling(14).mean()

        pdata[pair] = {
            'c': d30['close'].values, 'h': d30['high'].values, 'lo': d30['low'].values,
            'o': d30['open'].values, 'ts': d30.index, 'n': len(d30),
            'e200': e200.reindex(d30.index, method='ffill').values,
            'e50': e50.reindex(d30.index, method='ffill').values,
            'atr': atr_4h.reindex(d30.index, method='ffill').values,
            'daily': daily, 'pip': pip, 'pv': pv, 'spread': SPREAD.get(pair, 2.0),
        }
        close_series[pair] = d30['close']

    if not pdata: return None

    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref = pdata[ref_pair]; n_bars = ref['n']

    price_df = pd.DataFrame(close_series)
    returns_full = price_df.pct_change().dropna()
    corr_matrix = returns_full.corr()

    # Trade log: list of dicts with entry/exit details
    trade_log = []
    bal = ACC; open_pos = []
    daily_d = None; daily_sb = ACC

    for i in range(250, n_bars - 1):
        ts_now = ref['ts'][i]
        today = ts_now.date()
        if daily_d != today: daily_d = today; daily_sb = bal

        # Daily loss limit
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos['pair'])
                if pd_ is None or i >= pd_['n']: continue
                ep = pd_['c'][i] - (pos['spread']*0.5+0.3)*pos['pip'] if pos['trend']==1 else pd_['c'][i]+(pos['spread']*0.5+0.3)*pos['pip']
                pnl = (ep - pos['entry']) * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': pos['regime'], 'trend': pos['trend'],
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'daily_limit', 'entry': pos['entry'], 'exit_price': ep,
                })
            open_pos.clear(); continue

        # --- EXITS ---
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos['pair'])
            if pd_ is None or i >= pd_['n']: remaining.append(pos); continue
            bar_lo = pd_['lo'][i]; bar_hi = pd_['h'][i]; bar_cl = pd_['c'][i]
            tr = pos['trend']; sl = pos['sl']; tp = pos['tp']; closed = False
            regime = pos['regime']

            if tr == 1 and bar_lo <= sl:
                pnl = (sl - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': regime, 'trend': tr,
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'stop_loss', 'entry': pos['entry'], 'exit_price': sl,
                })
                closed = True
            elif tr == -1 and bar_hi >= sl:
                pnl = (pos['entry'] - sl) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': regime, 'trend': tr,
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'stop_loss', 'entry': pos['entry'], 'exit_price': sl,
                })
                closed = True

            if not closed and tr == 1 and bar_hi >= tp:
                pnl = (tp - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': regime, 'trend': tr,
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'take_profit', 'entry': pos['entry'], 'exit_price': tp,
                })
                closed = True
            elif not closed and tr == -1 and bar_lo <= tp:
                pnl = (pos['entry'] - tp) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': regime, 'trend': tr,
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'take_profit', 'entry': pos['entry'], 'exit_price': tp,
                })
                closed = True

            # TF: TRAILING STOP
            if not closed and regime == 'tf' and (i - pos['bar']) >= TF_MIN_HOLD:
                cur_atr = pd_['atr'][i]
                if not np.isnan(cur_atr) and cur_atr > 0:
                    if tr == 1:
                        new_sl = bar_cl - TRAIL_ATR_MULT * cur_atr
                        if new_sl > sl: pos['sl'] = new_sl
                    else:
                        new_sl = bar_cl + TRAIL_ATR_MULT * cur_atr
                        if new_sl < sl: pos['sl'] = new_sl

            # MR: SESSION CLOSE EXIT
            if not closed and regime == 'mr' and not igs(ref['ts'][i]):
                ep = bar_cl - (pos['spread']*0.5+0.3)*pos['pip'] if tr == 1 else bar_cl + (pos['spread']*0.5+0.3)*pos['pip']
                pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': regime, 'trend': tr,
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'session_close', 'entry': pos['entry'], 'exit_price': ep,
                })
                closed = True

            # TF: MAX HOLD EXIT
            if not closed and regime == 'tf' and (i - pos['bar']) >= TF_MAX_HOLD:
                ep = bar_cl - (pos['spread']*0.5+0.3)*pos['pip'] if tr == 1 else bar_cl + (pos['spread']*0.5+0.3)*pos['pip']
                pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl
                trade_log.append({
                    'pair': pos['pair'], 'regime': regime, 'trend': tr,
                    'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                    'pnl': pnl, 'reason': 'max_hold', 'entry': pos['entry'], 'exit_price': ep,
                })
                closed = True

            # TF: TREND REVERSAL
            if not closed and regime == 'tf':
                ev = pd_['e200'][i]
                if not np.isnan(ev):
                    dist_pct = abs(bar_cl - ev) / ev
                    if dist_pct < BREAKOUT_ZONE * 0.4:
                        ep = bar_cl - (pos['spread']*0.5+0.3)*pos['pip'] if tr == 1 else bar_cl + (pos['spread']*0.5+0.3)*pos['pip']
                        pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                        bal += pnl
                        trade_log.append({
                            'pair': pos['pair'], 'regime': regime, 'trend': tr,
                            'entry_bar': pos['bar'], 'exit_bar': i, 'bars_held': i - pos['bar'],
                            'pnl': pnl, 'reason': 'trend_reversal', 'entry': pos['entry'], 'exit_price': ep,
                        })
                        closed = True

            if not closed: remaining.append(pos)
        open_pos = remaining

        bal = max(bal, 1.0)

        # --- ENTRIES ---
        if not igs(ts_now): continue

        active_pairs = [pos['pair'] for pos in open_pos]

        for pair in PAIRS:
            if len(open_pos) >= max_conc: break
            if any(p['pair'] == pair for p in open_pos): continue
            if check_currency_overlap(open_pos, pair): continue

            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_['n']: continue
            c_val = pd_['c'][i]; ev = pd_['e200'][i]; e5 = pd_['e50'][i]; cur_atr = pd_['atr'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            pip = pd_['pip']

            # Correlation check
            skip_pair = False
            for open_pair in active_pairs:
                if pair in corr_matrix.columns and open_pair in corr_matrix.columns:
                    corr_val = corr_matrix.loc[pair, open_pair]
                    if not np.isnan(corr_val) and abs(corr_val) > CORR_THRESHOLD:
                        skip_pair = True; break
            if skip_pair: continue

            dist_from_ema = (c_val - ev) / ev

            if abs(dist_from_ema) < BREAKOUT_ZONE:
                tr = 1 if c_val > ev else -1
                if tr == 1 and c_val < e5 * 0.995: continue
                if tr == -1 and c_val > e5 * 1.005: continue
                if tr == 1:
                    if max(pd_['h'][max(0,i-20):i]) <= c_val * 1.002: continue
                else:
                    if min(pd_['lo'][max(0,i-20):i]) >= c_val * 0.998: continue

                d_ts = pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                if tr == 1 and not dg: continue
                if tr == -1 and dg: continue

                sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
                sl_dist = abs(c_val - sl)
                if sl_dist < 2 * pip: continue
                tp = c_val + sl_dist * MR_RR if tr == 1 else c_val - sl_dist * MR_RR
                entry_fill = c_val + (pd_['spread']*0.5+0.3)*pip if tr == 1 else c_val - (pd_['spread']*0.5+0.3)*pip
                sz = ps.compute_position_size(pair=pair, side='BUY' if tr==1 else 'SELL', entry_price=entry_fill, sl_price=sl, account_balance_usd=bal, risk_pct=MR_RISK, leverage=LEV, margin_safety=0.5, snap=SNAP, lot_step=0.01, min_lot=0.01, max_lot=10.0, existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':tr,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'mr'})

            elif dist_from_ema > BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr > 0:
                if c_val <= e5: continue
                recent_high = max(pd_['h'][max(0,i-20):i])
                if c_val <= recent_high * 1.002: continue
                d_ts = pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                if not dg: continue

                entry_fill = c_val + (pd_['spread']*0.5+0.3)*pip
                sl = entry_fill - TRAIL_ATR_MULT * cur_atr
                tp = entry_fill + 2.5 * TRAIL_ATR_MULT * cur_atr
                sl_dist = abs(entry_fill - sl)
                if sl_dist < 2 * pip: continue
                sz = ps.compute_position_size(pair=pair, side='BUY', entry_price=entry_fill, sl_price=sl, account_balance_usd=bal, risk_pct=TF_RISK, leverage=LEV, margin_safety=0.5, snap=SNAP, lot_step=0.01, min_lot=0.01, max_lot=10.0, existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})

            elif dist_from_ema < -BREAKOUT_ZONE and not np.isnan(cur_atr) and cur_atr > 0:
                if c_val >= e5: continue
                recent_low = min(pd_['lo'][max(0,i-20):i])
                if c_val >= recent_low * 0.998: continue
                d_ts = pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                if dg: continue

                entry_fill = c_val - (pd_['spread']*0.5+0.3)*pip
                sl = entry_fill + TRAIL_ATR_MULT * cur_atr
                tp = entry_fill - 2.5 * TRAIL_ATR_MULT * cur_atr
                sl_dist = abs(sl - entry_fill)
                if sl_dist < 2 * pip: continue
                sz = ps.compute_position_size(pair=pair, side='SELL', entry_price=entry_fill, sl_price=sl, account_balance_usd=bal, risk_pct=TF_RISK, leverage=LEV, margin_safety=0.5, snap=SNAP, lot_step=0.01, min_lot=0.01, max_lot=10.0, existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({'pair':pair,'trend':-1,'entry':entry_fill,'sl':sl,'tp':tp,'lot':sz.lot_size,'bar':i,'pip':pip,'pv':pd_['pv'],'spread':pd_['spread'],'regime':'tf'})

    # Close any remaining open positions at last bar
    for pos in open_pos:
        pd_ = pdata.get(pos['pair'])
        if pd_ is None: continue
        last_i = min(n_bars - 1, pd_['n'] - 1)
        ep = pd_['c'][last_i]
        pnl = (ep - pos['entry']) * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
        bal += pnl
        trade_log.append({
            'pair': pos['pair'], 'regime': pos['regime'], 'trend': pos['trend'],
            'entry_bar': pos['bar'], 'exit_bar': last_i, 'bars_held': last_i - pos['bar'],
            'pnl': pnl, 'reason': 'end_of_data', 'entry': pos['entry'], 'exit_price': ep,
        })

    return trade_log, bal


def analyze_time_distribution(trade_log):
    """Analyze bars_held distribution for winners vs losers."""
    print("\n" + "=" * 80)
    print("  TIME-IN-TRADE DISTRIBUTION")
    print("=" * 80)

    winners = [t for t in trade_log if t['pnl'] > 0]
    losers = [t for t in trade_log if t['pnl'] <= 0]

    for bars in [20, 40, 60, 80, 100, 150, 200]:
        w_at = sum(1 for t in winners if t['bars_held'] <= bars)
        l_at = sum(1 for t in losers if t['bars_held'] <= bars)
        total_at = w_at + l_at
        wr_at = w_at / total_at * 100 if total_at > 0 else 0
        print(f"  ≤{bars:3d} bars: {w_at:4d} winners, {l_at:4d} losers, WR={wr_at:.1f}%")

    print(f"\n  Winners:")
    wh = [t['bars_held'] for t in winners]
    if wh:
        print(f"    Mean={np.mean(wh):.1f} bars, Median={np.median(wh):.1f}, "
              f"P10={np.percentile(wh,10):.0f}, P25={np.percentile(wh,25):.0f}, "
              f"P75={np.percentile(wh,75):.0f}, P90={np.percentile(wh,90):.0f}, Max={max(wh)}")

    print(f"  Losers:")
    lh = [t['bars_held'] for t in losers]
    if lh:
        print(f"    Mean={np.mean(lh):.1f} bars, Median={np.median(lh):.1f}, "
              f"P10={np.percentile(lh,10):.0f}, P25={np.percentile(lh,25):.0f}, "
              f"P75={np.percentile(lh,75):.0f}, P90={np.percentile(lh,90):.0f}, Max={max(lh)}")

    # By regime
    for regime in ['mr', 'tf']:
        rw = [t for t in winners if t['regime'] == regime]
        rl = [t for t in losers if t['regime'] == regime]
        print(f"\n  {regime.upper()} regime:")
        if rw:
            rwh = [t['bars_held'] for t in rw]
            print(f"    Winners: n={len(rwh)}, Mean={np.mean(rwh):.1f} bars, Median={np.median(rwh):.1f}")
        if rl:
            rlh = [t['bars_held'] for t in rl]
            print(f"    Losers:  n={len(rlh)}, Mean={np.mean(rlh):.1f} bars, Median={np.median(rlh):.1f}")


def test_time_stop(trade_log, max_hold_bars, label=""):
    """Simulate what happens if we force-close trades at max_hold_bars."""
    total_w = 0; total_l = 0; total_gw = 0; total_gl = 0
    total_pnl = 0; peak = ACC; bal = ACC; mdd = 0
    closed_early = 0; early_wins = 0; early_losses = 0
    reason_counts = {}

    for t in trade_log:
        if t['bars_held'] <= max_hold_bars:
            # Normal exit — trade wasn't time-stopped
            pnl = t['pnl']
            bal += pnl
            total_pnl += pnl
            if pnl > 0:
                total_w += 1; total_gw += pnl
            else:
                total_l += 1; total_gl += abs(pnl)
            reason_counts[t['reason']] = reason_counts.get(t['reason'], 0) + 1
        else:
            # Time-stop would have closed this trade early
            closed_early += 1
            # Approximate: assume exit at max_hold_bars with entry price (worst case = SL)
            # We don't have the exact price at that bar, so we use the actual P&L as reference
            # and flag that the trade would have been cut
            pnl = t['pnl']  # actual P&L (may have been better or worse if cut early)
            if t['pnl'] > 0:
                early_wins += 1
            else:
                early_losses += 1
            reason_counts['time_stop'] = reason_counts.get('time_stop', 0) + 1

        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd

    total_trades = total_w + total_l + closed_early
    wr = total_w / total_trades * 100 if total_trades > 0 else 0
    pf = total_gw / total_gl if total_gl > 0 else 99

    print(f"\n  {label} Time-stop @ {max_hold_bars} bars ({max_hold_bars*0.5:.0f}h)")
    print(f"    Trades={total_trades:,} WR={wr:.1f}% PF={pf:.1f} MDD={mdd*100:.2f}% Final=${bal:,.0f}")
    print(f"    Closed early: {closed_early} ({early_wins} winners, {early_losses} losers)")
    print(f"    Exit reasons: {reason_counts}")
    return {'max_hold': max_hold_bars, 'wr': wr, 'pf': pf, 'mdd': mdd*100, 'final': bal, 'closed_early': closed_early, 'early_wins': early_wins, 'early_losses': early_losses}


# =================== MAIN ===================
print("=" * 80)
print("  TIME-BASED STOP ANALYSIS")
print("  Running full backtest with trade logging...")
print("=" * 80)

result = run_sim_with_trade_log('2022-01-01', '2026-07-19', max_conc=20)
if result is None:
    print("No trades found!")
    exit()

trade_log, final_bal = result
print(f"\n  Total trades: {len(trade_log)}, Final balance: ${final_bal:,.0f}")

# 1. Analyze distribution
analyze_time_distribution(trade_log)

# 2. Test different time-stop thresholds
print("\n" + "=" * 80)
print("  TIME-STOP THRESHOLD COMPARISON")
print("=" * 80)

baseline_w = sum(1 for t in trade_log if t['pnl'] > 0)
baseline_l = sum(1 for t in trade_log if t['pnl'] <= 0)
baseline_wr = baseline_w / len(trade_log) * 100 if trade_log else 0
print(f"\n  BASELINE (no time stop): {len(trade_log)} trades, WR={baseline_wr:.1f}%")

results = []
for hold in [20, 30, 40, 50, 60, 80, 100, 120, 150]:
    r = test_time_stop(trade_log, hold, "TEST")
    results.append(r)

# 3. Best option
print("\n" + "=" * 80)
print("  SUMMARY TABLE")
print("=" * 80)
print(f"  {'Hold':>5s} | {'Trades':>7s} | {'WR%':>6s} | {'PF':>5s} | {'MDD%':>6s} | {'Final':>10s} | {'Early':>6s} | {'E.Wins':>6s} | {'E.Loss':>6s}")
print(f"  {'-'*5}-+-{'-'*7}-+-{'-'*6}-+-{'-'*5}-+-{'-'*6}-+-{'-'*10}-+-{'-'*6}-+-{'-'*6}-+-{'-'*6}")
for r in results:
    print(f"  {r['max_hold']:5d} | {r['max_hold']*0.5:5.0f}h  | {r['wr']:5.1f}% | {r['pf']:5.2f} | {r['mdd']:5.2f}% | ${r['final']:>9,.0f} | {r['closed_early']:6d} | {r['early_wins']:6d} | {r['early_losses']:6d}")

# 4. MR-only time stop (more relevant since TF already has max_hold)
print("\n" + "=" * 80)
print("  MR-ONLY TIME-STOP ANALYSIS")
print("=" * 80)
mr_trades = [t for t in trade_log if t['regime'] == 'mr']
print(f"  MR trades: {len(mr_trades)}")
mr_winners = [t for t in mr_trades if t['pnl'] > 0]
mr_losers = [t for t in mr_trades if t['pnl'] <= 0]
if mr_winners:
    print(f"  MR Winners: Mean={np.mean([t['bars_held'] for t in mr_winners]):.1f} bars")
if mr_losers:
    print(f"  MR Losers:  Mean={np.mean([t['bars_held'] for t in mr_losers]):.1f} bars")

# Test MR-specific time stops
for hold in [20, 30, 40, 50, 60]:
    mr_w = sum(1 for t in mr_winners if t['bars_held'] <= hold)
    mr_l = sum(1 for t in mr_losers if t['bars_held'] <= hold)
    mr_total = mr_w + mr_l
    mr_wr = mr_w / mr_total * 100 if mr_total > 0 else 0
    mr_cut = sum(1 for t in mr_trades if t['bars_held'] > hold)
    mr_cut_w = sum(1 for t in mr_winners if t['bars_held'] > hold)
    mr_cut_l = sum(1 for t in mr_losers if t['bars_held'] > hold)
    print(f"  MR ≤{hold:3d} bars: {mr_w:4d}W {mr_l:4d}L WR={mr_wr:.1f}% | Cut: {mr_cut} ({mr_cut_w}W {mr_cut_l}L)")
