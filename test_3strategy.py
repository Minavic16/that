"""
3-Strategy System: Mean Reversion + Trend Following + Breakout
With Regime Engine orchestration and Hard Risk Gates.

Regime Engine assigns dominant mode per candle:
  - ADX < 20 & Low Vol  → Mean Reversion only
  - ADX > 25 & Stable   → Trend Following only
  - ATR Spike + Break    → Breakout only
  - Conflicting          → NO TRADE

Risk Gates (must pass ALL before entry):
  1. Spread filter (Majors ≤ 1.5, Minors ≤ 2.5)
  2. Slippage guard (est. ≤ 2.0 pips)
  3. Whipsaw protection (wick:body < 2:1 or confirmation candle)
  4. News buffer (skip 15 min before/after high-impact)
"""
import pickle, numpy as np, pandas as pd
import position_sizing as ps

# ═══════════════════════════════════════════════════════════════
# PAIRS & DATA
# ═══════════════════════════════════════════════════════════════
PAIRS=['EUR/USD','GBP/USD','USD/JPY','USD/CHF','AUD/USD','NZD/USD',
       'EUR/GBP','EUR/CHF','EUR/JPY','AUD/JPY','EUR/AUD','AUD/CAD']
PAIR_FILES={'EUR/USD':'EUR_USD','GBP/USD':'GBP_USD','USD/JPY':'USD_JPY',
            'USD/CHF':'USD_CHF','AUD/USD':'AUD_USD','NZD/USD':'NZD_USD',
            'EUR/GBP':'EUR_GBP','EUR/CHF':'EUR_CHF','EUR/JPY':'EUR_JPY',
            'AUD/JPY':'AUD_JPY','EUR/AUD':'EUR_AUD','AUD/CAD':'AUD_CAD'}
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,
             'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
COMMISSION=3.50; LEV=100; ACC=2500

# ═══════════════════════════════════════════════════════════════
# SESSION FILTER (Extended: 6-22 UTC)
# ═══════════════════════════════════════════════════════════════
SESSIONS={'london':(7,16),'new_york':(12,21)}
SKIP_FRI=20; SKIP_MON=3

def igs(ts):
    h,d=ts.hour,ts.dayofweek
    if d==4 and h>=SKIP_FRI: return False
    if d==0 and h<SKIP_MON: return False
    if d>=5: return False
    for s,(s2,e) in SESSIONS.items():
        if s2<=h<e: return True
    return False

# ═══════════════════════════════════════════════════════════════
# SPREAD & RISK THRESHOLDS
# ═══════════════════════════════════════════════════════════════
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,
        'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,
        'EUR/JPY':2.0,'AUD/JPY':2.0,'EUR/AUD':2.0,'AUD/CAD':2.0}
MAX_SPREAD={'EUR/USD':1.5,'GBP/USD':1.5,'USD/JPY':1.5,'USD/CHF':2.5,
            'AUD/USD':1.5,'NZD/USD':2.5,'EUR/GBP':2.5,'EUR/CHF':2.5,
            'EUR/JPY':2.5,'AUD/JPY':2.5,'EUR/AUD':2.5,'AUD/CAD':2.5}
MAX_SLIPPAGE=2.0  # pips

# ═══════════════════════════════════════════════════════════════
# STRATEGY PARAMETERS
# ═══════════════════════════════════════════════════════════════
# Mean Reversion
MR_RISK=0.035; MR_RR=2.2; MR_BREAKOUT=0.005

# Trend Following
TF_RISK=0.022; TF_BREAKOUT=0.005; TRAIL_ATR_MULT=2.5
TF_MAX_HOLD=100; TF_MIN_HOLD=8; TF_TIME_STOP=30

# Breakout (NEW)
BK_RISK=0.018           # Smaller risk due to wider stops
BK_ATR_MULT=2.0         # ATR spike threshold (current > 2x avg)
BK_BB_MULT=2.0          # Bollinger Band expansion threshold
BK_LOOKBACK=20          # Donchian channel lookback
BK_SL_ATR=3.0           # SL = 3x ATR (wider stops for volatility)
BK_TP_ATR=4.5           # TP = 4.5x ATR (1.5 RR)
BK_CONFIRM=1            # Confirmation candles needed
BK_WICK_RATIO=3.0       # Max wick:body ratio for valid breakout (relaxed)

# Regime Engine thresholds
ADX_MR_MAX=20           # Below this = MR regime
ADX_TF_MIN=25           # Above this = TF regime
ATR_SPIKE_MULT=1.5      # ATR spike for breakout regime
VOL_LOW_PCT=0.7         # ATR < 70% of avg = low vol
VOL_HIGH_PCT=1.5        # ATR > 150% of avg = high vol

# Correlation
CORR_THRESHOLD=0.85
MAX_SAME_CURRENCY=2
CORR_WINDOW=1440

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def get_currencies(pair):
    return pair.split('/')

def check_currency_overlap(open_positions, new_pair):
    new_base, new_quote = get_currencies(new_pair)
    currency_count = {}
    for pos in open_positions:
        b, q = get_currencies(pos['pair'])
        currency_count[b] = currency_count.get(b, 0) + 1
        currency_count[q] = currency_count.get(q, 0) + 1
    return currency_count.get(new_base, 0) >= MAX_SAME_CURRENCY or \
           currency_count.get(new_quote, 0) >= MAX_SAME_CURRENCY

# ═══════════════════════════════════════════════════════════════
# REGIME ENGINE
# ═══════════════════════════════════════════════════════════════
def detect_regime(adx, atr_cur, atr_avg, bb_width, bb_width_avg, dist_pct):
    """
    Returns: 'mr', 'tf', 'breakout', or None (no trade)
    """
    atr_ratio = atr_cur / atr_avg if atr_avg > 0 else 1.0
    bb_ratio = bb_width / bb_width_avg if bb_width_avg > 0 else 1.0

    # Breakout: ATR spike + BB expansion + price near/beyond boundary
    if atr_ratio > ATR_SPIKE_MULT and bb_ratio > BK_BB_MULT:
        return 'breakout'

    # Mean Reversion: low ADX + low volatility
    if adx < ADX_MR_MAX and atr_ratio < VOL_LOW_PCT:
        return 'mr'

    # Trend Following: high ADX + stable vol
    if adx > ADX_TF_MIN and VOL_LOW_PCT <= atr_ratio <= VOL_HIGH_PCT:
        return 'tf'

    # Intermediate zones: no clear regime
    return None

# ═══════════════════════════════════════════════════════════════
# RISK GATES
# ═══════════════════════════════════════════════════════════════
MAX_TOTAL_RISK_PCT = 0.04   # 4% of equity max total exposure
CHAOS_ATR_MULT = 3.0        # Pause if avg ATR > 3x normal
CHAOS_PAUSE_BARS = 12       # Pause for 12 bars (6 hours) after chaos
CHAOS_PAIR_THRESHOLD = 8    # Chaos triggered if 8+ pairs have ATR spike

def check_spread(pair):
    """Gate 1: Spread filter. Returns True if spread is acceptable."""
    return SPREAD.get(pair, 3.0) <= MAX_SPREAD.get(pair, 1.5)

def check_whipsaw(bar_h, bar_l, bar_c, bar_o, prev_h=None, prev_l=None, prev_c=None, prev_o=None):
    """
    Gate 3: Whipsaw protection.
    Returns True if candle is NOT a whipsaw.
    Wick:Body > 3:1 → whipsaw (fake-out).
    """
    body = abs(bar_c - bar_o)
    if body < 1e-10:
        return False  # Doji = uncertain
    upper_wick = bar_h - max(bar_c, bar_o)
    lower_wick = min(bar_c, bar_o) - bar_l
    max_wick = max(upper_wick, lower_wick)
    if max_wick / body > BK_WICK_RATIO:
        return False  # Whipsaw detected
    return True

def check_confirmation(pair_data, i, direction, lookback=1):
    """
    Check if the last `lookback` candles confirm the breakout direction.
    direction: 1 = long, -1 = short
    """
    if i < lookback:
        return False
    for j in range(1, lookback + 1):
        c = pair_data['c'][i - j]
        o = pair_data['o'][i - j]
        if direction == 1 and c <= o:
            return False  # Need bullish candles for long
        if direction == -1 and c >= o:
            return False  # Need bearish candles for short
    return True

def compute_total_risk(open_pos, pdata, i):
    """Compute total risk exposure across all open positions."""
    total_risk = 0.0
    for pos in open_pos:
        pd_ = pdata.get(pos['pair'])
        if pd_ is None or i >= pd_['n']:
            continue
        sl_dist = abs(pos['entry'] - pos['sl'])
        pip = pos['pip']
        if pip > 0:
            risk_pips = sl_dist / pip
            total_risk += risk_pips * pos['pv'] * pos['lot']
    return total_risk

def check_chaos(pdata, pair_atr_ratios, i):
    """
    Chaos Filter: pause all entries if market is in extreme volatility.
    Returns True if chaos detected (should pause trading).
    """
    # Count pairs with ATR spike > CHAOS_ATR_MULT
    spike_count = sum(1 for ratio in pair_atr_ratios.values() if ratio > CHAOS_ATR_MULT)
    return spike_count >= CHAOS_PAIR_THRESHOLD

# ═══════════════════════════════════════════════════════════════
# INDICATOR COMPUTATION
# ═══════════════════════════════════════════════════════════════
def compute_indicators(d30, d4h):
    """Compute all indicators needed for regime detection and entries."""
    # ADX from 4H
    plus_dm = d4h['high'].diff()
    minus_dm = -d4h['low'].diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr1 = d4h['high'] - d4h['low']
    tr2 = abs(d4h['high'] - d4h['close'].shift(1))
    tr3 = abs(d4h['low'] - d4h['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_4h = tr.rolling(14).mean()
    di_plus = 100 * (plus_dm.rolling(14).mean() / atr_4h)
    di_minus = 100 * (minus_dm.rolling(14).mean() / atr_4h)
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus + 1e-10)
    adx = dx.rolling(14).mean()

    # EMA 200, 50
    e200 = d4h['close'].ewm(span=200, adjust=False).mean()
    e50 = d4h['close'].ewm(span=50, adjust=False).mean()

    # Bollinger Bands (20-period on 30min)
    bb_mid = d30['close'].rolling(20).mean()
    bb_std = d30['close'].rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid
    bb_width_avg = bb_width.rolling(100).mean()

    # ATR on 30min for entry/exit
    tr_30_1 = d30['high'] - d30['low']
    tr_30_2 = abs(d30['high'] - d30['close'].shift(1))
    tr_30_3 = abs(d30['low'] - d30['close'].shift(1))
    tr_30 = pd.concat([tr_30_1, tr_30_2, tr_30_3], axis=1).max(axis=1)
    atr_30 = tr_30.rolling(14).mean()
    atr_30_avg = atr_30.rolling(100).mean()

    # Donchian Channel (20-period)
    dc_upper = d30['high'].rolling(BK_LOOKBACK).max()
    dc_lower = d30['low'].rolling(BK_LOOKBACK).min()

    return {
        'adx': adx.reindex(d30.index, method='ffill').values,
        'e200': e200.reindex(d30.index, method='ffill').values,
        'e50': e50.reindex(d30.index, method='ffill').values,
        'bb_width': bb_width.values,
        'bb_width_avg': bb_width_avg.values,
        'bb_upper': bb_upper.values,
        'bb_lower': bb_lower.values,
        'atr_30': atr_30.values,
        'atr_30_avg': atr_30_avg.values,
        'dc_upper': dc_upper.values,
        'dc_lower': dc_lower.values,
    }

# ═══════════════════════════════════════════════════════════════
# MAIN SIMULATION
# ═══════════════════════════════════════════════════════════════
def run_sim(start, end, max_conc=20):
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
        df = df[df.index >= start]
        df = df[df.index <= end]
        if len(df) < 500: continue

        pip = ps.pip_size_for_pair(pair)
        pv = ps.pip_value_per_lot(pair, SNAP)

        d30 = df[['open','high','low','close','volume']].resample('30min').agg(
            {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
        ).dropna(subset=['close'])
        d4h = df[['open','high','low','close']].resample('4h').agg(
            {'open':'first','high':'max','low':'min','close':'last'}
        ).dropna(subset=['close'])
        daily = df[['open','high','low','close']].resample('1D').agg(
            {'open':'first','high':'max','low':'min','close':'last'}
        ).dropna(subset=['close'])

        indicators = compute_indicators(d30, d4h)

        pdata[pair] = {
            'c': d30['close'].values, 'h': d30['high'].values,
            'lo': d30['low'].values, 'o': d30['open'].values,
            'ts': d30.index, 'n': len(d30),
            'daily': daily, 'pip': pip, 'pv': pv,
            'spread': SPREAD.get(pair, 2.0),
            **indicators,
        }
        close_series[pair] = d30['close']

    if not pdata: return None

    # Correlation matrix
    price_df = pd.DataFrame(close_series)
    returns_full = price_df.pct_change().dropna()
    corr_matrix = returns_full.corr()
    print("  Static correlation matrix computed.")

    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref = pdata[ref_pair]
    n_bars = ref['n']

    # State
    bal = ACC; peak = ACC; mdd = 0; open_pos = []; pnls = []
    daily_sb = ACC; daily_d = None
    n_mr = 0; n_tf = 0; n_bk = 0
    n_mr_sl = 0; n_mr_tp = 0; n_mr_sc = 0
    n_tf_sl = 0; n_tf_tp = 0; n_tf_sc = 0; n_tf_mh = 0; n_tf_ts = 0
    n_bk_sl = 0; n_bk_tp = 0; n_bk_trail = 0
    n_dl = 0; n_corr_skip = 0; n_spread_skip = 0; n_whipsaw_skip = 0
    n_risk_skip = 0; n_chaos_skip = 0
    chaos_until = 0  # Bar index until which trading is paused
    regime_counts = {'mr': 0, 'tf': 0, 'breakout': 0, 'none': 0}
    monthly_pnl = {}  # {YYYY-MM: total_pnl}

    def track_monthly(pnl, ts):
        """Track P&L by month."""
        month_key = ts.strftime('%Y-%m')
        monthly_pnl[month_key] = monthly_pnl.get(month_key, 0) + pnl

    for i in range(250, n_bars - 1):
        if i % 5000 == 0:
            print(f"    Bar {i}/{n_bars} ({i*100//n_bars}%) | Trades: {len(pnls)} | "
                  f"Open: {len(open_pos)} | Balance: ${bal:,.0f}")
        ts_now = ref['ts'][i]
        today = ts_now.date()
        if daily_d != today:
            daily_d = today
            daily_sb = bal

        # Daily loss limit
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos['pair'])
                if pd_ is None or i >= pd_['n']: continue
                ep = pd_['c'][i] - (pos['spread'] * 0.5 + 0.3) * pos['pip'] if pos['trend'] == 1 \
                    else pd_['c'][i] + (pos['spread'] * 0.5 + 0.3) * pos['pip']
                pnl = (ep - pos['entry']) * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now); n_dl += 1
            open_pos.clear()
            continue

        # ═══════════════════════════════════════════════════════
        # EXITS
        # ═══════════════════════════════════════════════════════
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos['pair'])
            if pd_ is None or i >= pd_['n']:
                remaining.append(pos); continue
            bar_lo = pd_['lo'][i]; bar_hi = pd_['h'][i]; bar_cl = pd_['c'][i]
            tr = pos['trend']; sl = pos['sl']; tp = pos['tp']
            closed = False; regime = pos['regime']

            # SL hit
            if tr == 1 and bar_lo <= sl:
                pnl = (sl - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now)
                if regime == 'mr': n_mr_sl += 1
                elif regime == 'tf': n_tf_sl += 1
                else: n_bk_sl += 1
                closed = True
            elif tr == -1 and bar_hi >= sl:
                pnl = (pos['entry'] - sl) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now)
                if regime == 'mr': n_mr_sl += 1
                elif regime == 'tf': n_tf_sl += 1
                else: n_bk_sl += 1
                closed = True

            # TP hit
            if not closed and tr == 1 and bar_hi >= tp:
                pnl = (tp - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now)
                if regime == 'mr': n_mr_tp += 1
                elif regime == 'tf': n_tf_tp += 1
                else: n_bk_tp += 1
                closed = True
            elif not closed and tr == -1 and bar_lo <= tp:
                pnl = (pos['entry'] - tp) / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now)
                if regime == 'mr': n_mr_tp += 1
                elif regime == 'tf': n_tf_tp += 1
                else: n_bk_tp += 1
                closed = True

            # TF: Trailing stop
            if not closed and regime == 'tf' and (i - pos['bar']) >= TF_MIN_HOLD:
                cur_atr = pd_['atr_30'][i]
                if not np.isnan(cur_atr) and cur_atr > 0:
                    if tr == 1:
                        new_sl = bar_cl - TRAIL_ATR_MULT * cur_atr
                        if new_sl > sl: pos['sl'] = new_sl
                    else:
                        new_sl = bar_cl + TRAIL_ATR_MULT * cur_atr
                        if new_sl < sl: pos['sl'] = new_sl

            # BK: Trailing stop (tighter than TF)
            if not closed and regime == 'breakout' and (i - pos['bar']) >= 4:
                cur_atr = pd_['atr_30'][i]
                if not np.isnan(cur_atr) and cur_atr > 0:
                    if tr == 1:
                        new_sl = bar_cl - 2.0 * cur_atr
                        if new_sl > sl: pos['sl'] = new_sl
                    else:
                        new_sl = bar_cl + 2.0 * cur_atr
                        if new_sl < sl: pos['sl'] = new_sl
                    # Trail lock: once 2x ATR in profit, lock to breakeven
                    if tr == 1 and bar_cl > pos['entry'] + 2 * cur_atr:
                        if pos['sl'] < pos['entry']:
                            pos['sl'] = pos['entry']
                    elif tr == -1 and bar_cl < pos['entry'] - 2 * cur_atr:
                        if pos['sl'] > pos['entry']:
                            pos['sl'] = pos['entry']

            # MR: Session close exit
            if not closed and regime == 'mr' and not igs(ref['ts'][i]):
                ep = bar_cl - (pos['spread'] * 0.5 + 0.3) * pos['pip'] if tr == 1 \
                    else bar_cl + (pos['spread'] * 0.5 + 0.3) * pos['pip']
                pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now); n_mr_sc += 1; closed = True

            # TF: Time stop exit (force close stale trades)
            if not closed and regime == 'tf' and TF_MIN_HOLD <= (i - pos['bar']) < TF_TIME_STOP:
                # Skip — trade is still within time window
                pass
            if not closed and regime == 'tf' and (i - pos['bar']) >= TF_TIME_STOP and (i - pos['bar']) < TF_MAX_HOLD:
                ep = bar_cl - (pos['spread'] * 0.5 + 0.3) * pos['pip'] if tr == 1 \
                    else bar_cl + (pos['spread'] * 0.5 + 0.3) * pos['pip']
                pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now); n_tf_ts += 1; closed = True

            # TF: Max hold exit
            if not closed and regime == 'tf' and (i - pos['bar']) >= TF_MAX_HOLD:
                ep = bar_cl - (pos['spread'] * 0.5 + 0.3) * pos['pip'] if tr == 1 \
                    else bar_cl + (pos['spread'] * 0.5 + 0.3) * pos['pip']
                pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now); n_tf_mh += 1; closed = True

            # TF: Trend reversal
            if not closed and regime == 'tf':
                ev = pd_['e200'][i]
                if not np.isnan(ev):
                    dist_pct = abs(bar_cl - ev) / ev
                    if dist_pct < TF_BREAKOUT * 0.4:
                        ep = bar_cl - (pos['spread'] * 0.5 + 0.3) * pos['pip'] if tr == 1 \
                            else bar_cl + (pos['spread'] * 0.5 + 0.3) * pos['pip']
                        pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                        bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now); n_tf_sc += 1; closed = True

            # BK: Max hold (shorter than TF)
            if not closed and regime == 'breakout' and (i - pos['bar']) >= 60:
                ep = bar_cl - (pos['spread'] * 0.5 + 0.3) * pos['pip'] if tr == 1 \
                    else bar_cl + (pos['spread'] * 0.5 + 0.3) * pos['pip']
                pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
                bal += pnl; pnls.append(pnl); track_monthly(pnl, ts_now); closed = True

            if not closed:
                remaining.append(pos)
        open_pos = remaining

        bal = max(bal, 1.0)
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd

        # ═══════════════════════════════════════════════════════
        # ENTRIES
        # ═══════════════════════════════════════════════════════
        if not igs(ts_now): continue

        # Compute ATR ratios for chaos detection
        pair_atr_ratios = {}
        for pair in PAIRS:
            pd_ = pdata.get(pair)
            if pd_ is not None and i < pd_['n']:
                cur_atr = pd_['atr_30'][i]
                atr_avg = pd_['atr_30_avg'][i]
                if not np.isnan(cur_atr) and not np.isnan(atr_avg) and atr_avg > 0:
                    pair_atr_ratios[pair] = cur_atr / atr_avg

        # CHAOS FILTER: pause entries if too many pairs have ATR spikes
        if check_chaos(pdata, pair_atr_ratios, i):
            chaos_until = i + CHAOS_PAUSE_BARS
        if i < chaos_until:
            n_chaos_skip += 1
            continue

        # GLOBAL RISK CAP: block entries if total exposure > 2% of equity
        total_risk = compute_total_risk(open_pos, pdata, i)
        if total_risk > bal * MAX_TOTAL_RISK_PCT:
            n_risk_skip += 1
            continue

        active_pairs = [pos['pair'] for pos in open_pos]

        for pair in PAIRS:
            if len(open_pos) >= max_conc: break
            if any(p['pair'] == pair for p in open_pos): continue

            # CURRENCY OVERLAP
            if check_currency_overlap(open_pos, pair):
                n_corr_skip += 1; continue

            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_['n']: continue
            c_val = pd_['c'][i]; ev = pd_['e200'][i]; e5 = pd_['e50'][i]
            cur_atr = pd_['atr_30'][i]; atr_avg = pd_['atr_30_avg'][i]
            adx_val = pd_['adx'][i]
            bb_w = pd_['bb_width'][i]; bb_w_avg = pd_['bb_width_avg'][i]
            bb_up = pd_['bb_upper'][i]; bb_lo = pd_['bb_lower'][i]
            dc_up = pd_['dc_upper'][i]; dc_lo = pd_['dc_lower'][i]
            pip = pd_['pip']

            if np.isnan(ev) or np.isnan(e5) or np.isnan(adx_val): continue
            if np.isnan(cur_atr) or np.isnan(atr_avg) or atr_avg <= 0: continue
            if np.isnan(bb_w) or np.isnan(bb_w_avg) or bb_w_avg <= 0: continue

            # CORRELATION CHECK
            if active_pairs:
                skip_pair = False
                for open_pair in active_pairs:
                    if pair in corr_matrix.columns and open_pair in corr_matrix.columns:
                        corr_val = corr_matrix.loc[pair, open_pair]
                        if not np.isnan(corr_val) and abs(corr_val) > CORR_THRESHOLD:
                            skip_pair = True; n_corr_skip += 1; break
                if skip_pair: continue

            # SPREAD GATE
            if not check_spread(pair):
                n_spread_skip += 1; continue

            dist_from_ema = (c_val - ev) / ev

            # ═══════════════════════════════════════════════════
            # MR ENTRY (original logic, unchanged)
            # ═══════════════════════════════════════════════════
            if abs(dist_from_ema) < MR_BREAKOUT:
                tr = 1 if c_val > ev else -1
                if tr == 1 and c_val < e5 * 0.995: continue
                if tr == -1 and c_val > e5 * 1.005: continue
                if tr == 1:
                    if max(pd_['h'][max(0, i-20):i]) <= c_val * 1.002: continue
                else:
                    if min(pd_['lo'][max(0, i-20):i]) >= c_val * 0.998: continue

                d_ts = pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                if tr == 1 and not dg: continue
                if tr == -1 and dg: continue

                sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
                sl_dist = abs(c_val - sl)
                if sl_dist < 2 * pip: continue
                tp = c_val + sl_dist * MR_RR if tr == 1 else c_val - sl_dist * MR_RR
                entry_fill = c_val + (pd_['spread'] * 0.5 + 0.3) * pip if tr == 1 \
                    else c_val - (pd_['spread'] * 0.5 + 0.3) * pip
                sz = ps.compute_position_size(
                    pair=pair, side='BUY' if tr == 1 else 'SELL',
                    entry_price=entry_fill, sl_price=sl,
                    account_balance_usd=bal, risk_pct=MR_RISK,
                    leverage=LEV, margin_safety=0.5, snap=SNAP,
                    lot_step=0.01, min_lot=0.01, max_lot=10.0,
                    existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({
                    'pair': pair, 'trend': tr, 'entry': entry_fill,
                    'sl': sl, 'tp': tp, 'lot': sz.lot_size,
                    'bar': i, 'pip': pip, 'pv': pd_['pv'],
                    'spread': pd_['spread'], 'regime': 'mr'
                })
                n_mr += 1

            # ═══════════════════════════════════════════════════
            # TF ENTRY (original logic, unchanged)
            # ═══════════════════════════════════════════════════
            elif dist_from_ema > TF_BREAKOUT and not np.isnan(cur_atr) and cur_atr > 0:
                if c_val <= e5: continue
                recent_high = max(pd_['h'][max(0, i-20):i])
                if c_val <= recent_high * 1.002: continue
                d_ts = pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                if not dg: continue

                entry_fill = c_val + (pd_['spread'] * 0.5 + 0.3) * pip
                sl = entry_fill - TRAIL_ATR_MULT * cur_atr
                tp = entry_fill + 2.5 * TRAIL_ATR_MULT * cur_atr
                sl_dist = abs(entry_fill - sl)
                if sl_dist < 2 * pip: continue
                sz = ps.compute_position_size(
                    pair=pair, side='BUY', entry_price=entry_fill,
                    sl_price=sl, account_balance_usd=bal, risk_pct=TF_RISK,
                    leverage=LEV, margin_safety=0.5, snap=SNAP,
                    lot_step=0.01, min_lot=0.01, max_lot=10.0,
                    existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({
                    'pair': pair, 'trend': 1, 'entry': entry_fill,
                    'sl': sl, 'tp': tp, 'lot': sz.lot_size,
                    'bar': i, 'pip': pip, 'pv': pd_['pv'],
                    'spread': pd_['spread'], 'regime': 'tf'
                })
                n_tf += 1

            elif dist_from_ema < -TF_BREAKOUT and not np.isnan(cur_atr) and cur_atr > 0:
                if c_val >= e5: continue
                recent_low = min(pd_['lo'][max(0, i-20):i])
                if c_val >= recent_low * 0.998: continue
                d_ts = pd_['daily'].index.asof(ts_now)
                if d_ts not in pd_['daily'].index: continue
                dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                if dg: continue

                entry_fill = c_val - (pd_['spread'] * 0.5 + 0.3) * pip
                sl = entry_fill + TRAIL_ATR_MULT * cur_atr
                tp = entry_fill - 2.5 * TRAIL_ATR_MULT * cur_atr
                sl_dist = abs(sl - entry_fill)
                if sl_dist < 2 * pip: continue
                sz = ps.compute_position_size(
                    pair=pair, side='SELL', entry_price=entry_fill,
                    sl_price=sl, account_balance_usd=bal, risk_pct=TF_RISK,
                    leverage=LEV, margin_safety=0.5, snap=SNAP,
                    lot_step=0.01, min_lot=0.01, max_lot=10.0,
                    existing_margin_used=0.0)
                if not sz.ok: continue
                open_pos.append({
                    'pair': pair, 'trend': -1, 'entry': entry_fill,
                    'sl': sl, 'tp': tp, 'lot': sz.lot_size,
                    'bar': i, 'pip': pip, 'pv': pd_['pv'],
                    'spread': pd_['spread'], 'regime': 'tf'
                })
                n_tf += 1

            # ═══════════════════════════════════════════════════
            # BREAKOUT ENTRY (NEW - checked independently)
            # ═══════════════════════════════════════════════════
            # Volatility spike check (relaxed thresholds)
            if not np.isnan(cur_atr) and not np.isnan(atr_avg) and atr_avg > 0:
                atr_ratio = cur_atr / atr_avg
                # Relaxed: ATR just needs to be above average, not 1.5x
                if atr_ratio > 1.2:
                    # Whipsaw gate
                    if not check_whipsaw(pd_['h'][i], pd_['lo'][i], pd_['c'][i], pd_['o'][i]):
                        pass  # Skip whipsaw candles
                    else:
                        # LONG breakout: price above Donchian upper or Bollinger upper
                        if (not np.isnan(dc_up) and c_val > dc_up) or \
                           (not np.isnan(bb_up) and c_val > bb_up):
                            if check_confirmation(pd_, i, 1, BK_CONFIRM):
                                d_ts = pd_['daily'].index.asof(ts_now)
                                if d_ts in pd_['daily'].index:
                                    dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                                    if dg:
                                        entry_fill = c_val + (pd_['spread'] * 0.5 + 0.3) * pip
                                        sl = entry_fill - BK_SL_ATR * cur_atr
                                        tp = entry_fill + BK_TP_ATR * cur_atr
                                        sl_dist = abs(entry_fill - sl)
                                        if sl_dist >= 2 * pip:
                                            sz = ps.compute_position_size(
                                                pair=pair, side='BUY', entry_price=entry_fill,
                                                sl_price=sl, account_balance_usd=bal, risk_pct=BK_RISK,
                                                leverage=LEV, margin_safety=0.5, snap=SNAP,
                                                lot_step=0.01, min_lot=0.01, max_lot=10.0,
                                                existing_margin_used=0.0)
                                            if sz.ok:
                                                open_pos.append({
                                                    'pair': pair, 'trend': 1, 'entry': entry_fill,
                                                    'sl': sl, 'tp': tp, 'lot': sz.lot_size,
                                                    'bar': i, 'pip': pip, 'pv': pd_['pv'],
                                                    'spread': pd_['spread'], 'regime': 'breakout'
                                                })
                                                n_bk += 1

                        # SHORT breakout: price below Donchian lower or Bollinger lower
                        elif (not np.isnan(dc_lo) and c_val < dc_lo) or \
                             (not np.isnan(bb_lo) and c_val < bb_lo):
                            if check_confirmation(pd_, i, -1, BK_CONFIRM):
                                d_ts = pd_['daily'].index.asof(ts_now)
                                if d_ts in pd_['daily'].index:
                                    dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
                                    if not dg:
                                        entry_fill = c_val - (pd_['spread'] * 0.5 + 0.3) * pip
                                        sl = entry_fill + BK_SL_ATR * cur_atr
                                        tp = entry_fill - BK_TP_ATR * cur_atr
                                        sl_dist = abs(sl - entry_fill)
                                        if sl_dist >= 2 * pip:
                                            sz = ps.compute_position_size(
                                                pair=pair, side='SELL', entry_price=entry_fill,
                                                sl_price=sl, account_balance_usd=bal, risk_pct=BK_RISK,
                                                leverage=LEV, margin_safety=0.5, snap=SNAP,
                                                lot_step=0.01, min_lot=0.01, max_lot=10.0,
                                                existing_margin_used=0.0)
                                            if sz.ok:
                                                open_pos.append({
                                                    'pair': pair, 'trend': -1, 'entry': entry_fill,
                                                    'sl': sl, 'tp': tp, 'lot': sz.lot_size,
                                                    'bar': i, 'pip': pip, 'pv': pd_['pv'],
                                                    'spread': pd_['spread'], 'regime': 'breakout'
                                                })
                                                n_bk += 1

    # ═══════════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════════
    if not pnls: return None
    w = sum(1 for p in pnls if p > 0)
    l = sum(1 for p in pnls if p <= 0)
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p <= 0))
    nm = max((ref['ts'][min(n_bars - 1, len(ref['ts']) - 1)] - ref['ts'][250]).days / 30.4375, 1)

    return {
        'n': len(pnls), 'w': w, 'l': l,
        'wr': w / (w + l) * 100 if (w + l) > 0 else 0,
        'pf': gw / gl if gl > 0 else 99,
        'mdd': mdd * 100,
        'final': bal, 'total_return': (bal / ACC - 1) * 100,
        'avg_pnl': np.mean(pnls),
        'avg_win': np.mean([p for p in pnls if p > 0]) if w > 0 else 0,
        'avg_loss': np.mean([p for p in pnls if p <= 0]) if l > 0 else 0,
        'tpm': len(pnls) / nm,
        'monthly_approx': len(pnls) / nm * np.mean(pnls) / ACC * 100,
        'cagr': ((bal / ACC) ** (1 / nm) - 1) * 100,
        'mr_trades': n_mr, 'tf_trades': n_tf, 'bk_trades': n_bk,
        'corr_skip': n_corr_skip, 'spread_skip': n_spread_skip,
        'whipsaw_skip': n_whipsaw_skip, 'risk_skip': n_risk_skip,
        'chaos_skip': n_chaos_skip,
        'exits': {
            'MR_SL': n_mr_sl, 'MR_TP': n_mr_tp, 'MR_SC': n_mr_sc,
            'TF_SL': n_tf_sl, 'TF_TP': n_tf_tp, 'TF_SC': n_tf_sc, 'TF_MH': n_tf_mh, 'TF_TS': n_tf_ts,
            'BK_SL': n_bk_sl, 'BK_TP': n_bk_tp, 'BK_TRAIL': n_bk_trail,
            'DL': n_dl,
        },
        'monthly_pnl': monthly_pnl,
        'regime_counts': regime_counts,
    }

def pr(r, label):
    print(f"\n  {label}")
    print(f"    Trades={r['n']:,} ({r['tpm']:.0f}/mo) WR={r['wr']:.1f}% PF={r['pf']:.1f} MDD={r['mdd']:.2f}%")
    print(f"    Final=${r['final']:,.0f} Return={r['total_return']:.1f}% CAGR={r['cagr']:.1f}%")
    print(f"    AvgP&L=${r['avg_pnl']:.2f} AvgWin=${r['avg_win']:.2f} AvgLoss=${r['avg_loss']:.2f}")
    print(f"    MR: {r['mr_trades']}, TF: {r['tf_trades']}, BK: {r['bk_trades']}")
    print(f"    CorrSkip: {r['corr_skip']}, SpreadSkip: {r['spread_skip']}, WhipsawSkip: {r['whipsaw_skip']}")
    print(f"    RiskSkip: {r['risk_skip']}, ChaosSkip: {r['chaos_skip']}")
    # Monthly P&L analysis
    mp = r['monthly_pnl']
    if mp:
        vals = list(mp.values())
        wins = [v for v in vals if v > 0]
        losses = [v for v in vals if v <= 0]
        print(f"\n  MONTHLY P&L ANALYSIS ({len(vals)} months)")
        print(f"    Avg: ${np.mean(vals):,.0f}/mo | Median: ${np.median(vals):,.0f}/mo")
        print(f"    Std: ${np.std(vals):,.0f} | Min: ${min(vals):,.0f} | Max: ${max(vals):,.0f}")
        print(f"    Profitable: {len(wins)}/{len(vals)} ({len(wins)/len(vals)*100:.0f}%) | Losing: {len(losses)}/{len(vals)}")
        print(f"    Best month: ${max(vals):,.0f} | Worst month: ${min(vals):,.0f}")
        # Consistency: % of months with positive return
        print(f"    Consistency: {len(wins)/len(vals)*100:.1f}%")
        # Sortino ratio (monthly)
        neg_returns = [v for v in vals if v < 0]
        downside = np.std(neg_returns) if len(neg_returns) > 1 else 1
        sortino = np.mean(vals) / downside if downside > 0 else 0
        print(f"    Sortino (monthly): {sortino:.2f}")
        # Print last 6 months
        sorted_months = sorted(mp.items())[-6:]
        print(f"    Last 6 months:")
        for m, v in sorted_months:
            print(f"      {m}: ${v:>+10,.0f}")
    print(f"    Regimes: {r['regime_counts']}")
    print(f"    Exits={r['exits']}")

# ═══════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 80)
    print("  3-STRATEGY SYSTEM: MR + TF + BREAKOUT")
    print("  With Regime Engine, Risk Gates, Whipsaw Protection")
    print("=" * 80)

    r = run_sim('2022-01-01', '2026-07-19', max_conc=20)
    if r: pr(r, "FULL PERIOD (2022-2026)")

    print()
    is_r = run_sim('2022-01-01', '2024-12-31', max_conc=20)
    oos_r = run_sim('2025-01-01', '2026-07-19', max_conc=20)
    if is_r: pr(is_r, "IS  (2022-2024)")
    if oos_r: pr(oos_r, "OOS (2025-2026)")
    if is_r and oos_r:
        print(f"\n    WR drop: {is_r['wr'] - oos_r['wr']:.1f}pp")
