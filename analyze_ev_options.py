"""
Analyze 3 strategies to boost monthly EV for Structured Entry.
Phase 1: Vectorized signal detection + bar-by-bar exit only for candidates.
"""
import pickle
import numpy as np
import pandas as pd
import time
import position_sizing as ps

BASE_PAIRS = ['EUR/CHF', 'GBP/USD', 'AUD/JPY', 'EUR/USD', 'USD/CHF', 'GBP/JPY']
ALL_PAIRS = [
    'AUD/CAD', 'AUD/CHF', 'AUD/JPY', 'AUD/NZD', 'AUD/USD', 'CAD/CHF',
    'CAD/JPY', 'CHF/JPY', 'EUR/AUD', 'EUR/CAD', 'EUR/CHF', 'EUR/GBP',
    'EUR/JPY', 'EUR/NZD', 'EUR/USD', 'GBP/AUD', 'GBP/CAD', 'GBP/CHF',
    'GBP/JPY', 'GBP/NZD', 'GBP/USD', 'NZD/CAD', 'NZD/CHF', 'NZD/JPY',
    'NZD/USD', 'USD/CAD', 'USD/CHF', 'USD/JPY'
]

EMA_200 = 200; EMA_50 = 50; RR_TARGET = 2.7; RISK_PCT = 0.0075
SL_BUFFER = 0.005; PULLBACK_PCT = 0.005; EARLY_EXIT_PCT = 0.001
LEVERAGE = 100; ACCOUNT_START = 2500
SESSIONS = {'london': (7, 16), 'new_york': (12, 21)}
SKIP_FRIDAY_AFTER = 20; SKIP_MONDAY_BEFORE = 3

DEFAULT_USD_VALUE = {
    'USD': 1.0, 'EUR': 1.08, 'GBP': 1.26, 'JPY': 0.0067,
    'CHF': 0.88, 'AUD': 0.65, 'CAD': 0.74, 'NZD': 0.60,
}
SNAP = ps.QuoteSnapshot(usd_value=DEFAULT_USD_VALUE)

_data_cache = {}
_pair_info = {}

def get_pair_info(pair):
    if pair in _pair_info:
        return _pair_info[pair]
    pip = ps.pip_size_for_pair(pair)
    pip_val = ps.pip_value_per_lot(pair, SNAP)
    _pair_info[pair] = (pip, pip_val)
    return pip, pip_val

def load_pair(pair):
    if pair in _data_cache:
        return _data_cache[pair]
    pk = pair.replace('/', '_')
    path = f'/root/data/{pk}.pkl'
    try:
        with open(path, 'rb') as f:
            raw = pickle.load(f)
        df = raw.get(pair)
        if df is None or df.empty:
            _data_cache[pair] = None; return None
        idx = pd.to_datetime(df.index)
        if idx.tz is None: idx = idx.tz_localize('UTC')
        else: idx = idx.tz_convert('UTC')
        df.index = idx
        result = df[df.index >= '2018-01-01']
        _data_cache[pair] = result
        return result
    except:
        _data_cache[pair] = None; return None


def run_signals_fast(pair, data, timeframe='30min', exit_mode='standard', max_hold=50):
    if data is None or len(data) < EMA_200 * 2 + 100:
        return []

    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    d_trade = data[['open','high','low','close']].resample(timeframe).agg(agg).dropna(subset=['close'])
    d4h = data[['open','high','low','close']].resample('4h').agg(agg).dropna(subset=['close'])
    daily = data[['open','high','low','close']].resample('1D').agg(agg).dropna(subset=['close'])

    if len(d_trade) < EMA_200 + 100:
        return []

    ema200 = d4h['close'].ewm(span=EMA_200, adjust=False).mean().reindex(d_trade.index, method='ffill').values
    ema50 = d4h['close'].ewm(span=EMA_50, adjust=False).mean().reindex(d_trade.index, method='ffill').values

    c = d_trade['close'].values
    h = d_trade['high'].values
    lo = d_trade['low'].values
    ts = d_trade.index
    n = len(c)
    pip, pip_val = get_pair_info(pair)

    # Precompute session mask
    hours = ts.hour.values
    days = ts.dayofweek.values
    session_mask = np.ones(n, dtype=bool)
    session_mask[(days == 5) | (days == 6)] = False
    session_mask[(days == 4) & (hours >= SKIP_FRIDAY_AFTER)] = False
    session_mask[(days == 0) & (hours < SKIP_MONDAY_BEFORE)] = False
    session_mask &= ((hours >= 7) & (hours < 16)) | ((hours >= 12) & (hours < 21))

    # Precompute daily green (vectorized via merge_asof)
    daily_green = np.zeros(n, dtype=bool)
    daily_idx = daily.index
    daily_close_arr = daily['close'].values
    daily_open_arr = daily['open'].values
    # Use searchsorted for speed
    ts_ns = ts.values.astype(np.int64)
    daily_ns = daily_idx.values.astype(np.int64)
    idxs = np.searchsorted(daily_ns, ts_ns, side='right') - 1
    for k in range(n):
        if idxs[k] >= 0:
            daily_green[k] = daily_close_arr[idxs[k]] > daily_open_arr[idxs[k]]

    warmup = EMA_200 + 50

    # VECTORIZED: compute all filter conditions at once
    valid = np.zeros(n, dtype=bool)
    valid[warmup:] = True
    valid &= session_mask

    # EMA200 trend
    trend = np.zeros(n, dtype=np.int8)
    valid &= ~np.isnan(ema200) & ~np.isnan(ema50)
    trend[valid] = np.where(c[valid] > ema200[valid], 1, -1)
    valid &= (trend == 1) | (trend == -1)

    # EMA50 filter
    ema50_lo = np.where(trend == 1, ema50 * 0.998, -np.inf)
    ema50_hi = np.where(trend == -1, ema50 * 1.002, np.inf)
    valid &= np.where(trend == 1, c >= ema50_lo, True)
    valid &= np.where(trend == -1, c <= ema50_hi, True)

    # Pullback zone
    pb_lo = ema200 * (1 - PULLBACK_PCT)
    pb_hi = ema200 * (1 + PULLBACK_PCT)
    valid &= (c > pb_lo) & (c < pb_hi)

    # Daily filter
    valid &= np.where(trend == 1, daily_green, ~daily_green)

    # Swing pullback: need 20-bar lookback - vectorized with rolling max/min
    h_series = pd.Series(h)
    lo_series = pd.Series(lo)
    h_roll_max = h_series.rolling(20, min_periods=1).max().values
    lo_roll_min = lo_series.rolling(20, min_periods=1).min().values
    # For trend==1: max of highs before i must be > c[i]*1.002
    # For trend==-1: min of lows before i must be < c[i]*0.998
    swing_ok = np.ones(n, dtype=bool)
    swing_ok &= np.where(trend == 1, h_roll_max > c * 1.002, True)
    swing_ok &= np.where(trend == -1, lo_roll_min < c * 0.998, True)
    valid &= swing_ok

    # Get candidate indices
    candidates = np.where(valid)[0]

    if len(candidates) == 0:
        return []

    # Now only run exit simulation for candidates
    trades = []
    pb_half = PULLBACK_PCT * 0.5

    for idx in candidates:
        i = int(idx)
        ci = c[i]
        t = int(trend[i])
        e200_val = ema200[i]

        if t == 1:
            entry1 = ci
            entry2 = ci * (1 - pb_half)
            avg_entry = (entry1 + entry2) * 0.5
            sl_price = e200_val * (1 - SL_BUFFER)
            tp_price = entry1 + (entry1 - sl_price) * RR_TARGET
            early_exit = avg_entry * (1 - EARLY_EXIT_PCT)
        else:
            entry1 = ci
            entry2 = ci * (1 + pb_half)
            avg_entry = (entry1 + entry2) * 0.5
            sl_price = e200_val * (1 + SL_BUFFER)
            tp_price = entry1 - (sl_price - entry1) * RR_TARGET
            early_exit = avg_entry * (1 + EARLY_EXIT_PCT)

        exit_price = None
        exit_reason = None
        trail_active = False
        trail_stop = 0.0
        high_since = avg_entry
        low_since = avg_entry

        end_j = min(i + max_hold, n)
        for j in range(i + 1, end_j):
            if exit_mode == 'trailing':
                if t == 1:
                    if not trail_active and c[j] >= avg_entry * 1.003:
                        trail_active = True
                    if trail_active:
                        if c[j] > high_since: high_since = c[j]
                        trail_stop = high_since * 0.9985
                    if lo[j] <= early_exit:
                        exit_price = early_exit; exit_reason = 'EARLY_EXIT'; break
                    if lo[j] <= sl_price:
                        exit_price = sl_price; exit_reason = 'SL'; break
                    if h[j] >= tp_price:
                        exit_price = tp_price; exit_reason = 'TP'; break
                    if trail_active and lo[j] <= trail_stop:
                        exit_price = trail_stop; exit_reason = 'TRAIL'; break
                    if not session_mask[j]:
                        exit_price = c[j]; exit_reason = 'SESSION_CLOSE'; break
                else:
                    if not trail_active and c[j] <= avg_entry * 0.997:
                        trail_active = True
                    if trail_active:
                        if c[j] < low_since: low_since = c[j]
                        trail_stop = low_since * 1.0015
                    if h[j] >= early_exit:
                        exit_price = early_exit; exit_reason = 'EARLY_EXIT'; break
                    if h[j] >= sl_price:
                        exit_price = sl_price; exit_reason = 'SL'; break
                    if lo[j] <= tp_price:
                        exit_price = tp_price; exit_reason = 'TP'; break
                    if trail_active and h[j] >= trail_stop:
                        exit_price = trail_stop; exit_reason = 'TRAIL'; break
                    if not session_mask[j]:
                        exit_price = c[j]; exit_reason = 'SESSION_CLOSE'; break
            else:
                if t == 1:
                    if lo[j] <= early_exit:
                        exit_price = early_exit; exit_reason = 'EARLY_EXIT'; break
                    if lo[j] <= sl_price:
                        exit_price = sl_price; exit_reason = 'SL'; break
                    if h[j] >= tp_price:
                        exit_price = tp_price; exit_reason = 'TP'; break
                    if not session_mask[j]:
                        exit_price = c[j]; exit_reason = 'SESSION_CLOSE'; break
                else:
                    if h[j] >= early_exit:
                        exit_price = early_exit; exit_reason = 'EARLY_EXIT'; break
                    if h[j] >= sl_price:
                        exit_price = sl_price; exit_reason = 'SL'; break
                    if lo[j] <= tp_price:
                        exit_price = tp_price; exit_reason = 'TP'; break
                    if not session_mask[j]:
                        exit_price = c[j]; exit_reason = 'SESSION_CLOSE'; break
        else:
            exit_price = c[min(i + max_hold - 1, n - 1)]
            exit_reason = 'MAX_HOLD'

        pips_realized = ((exit_price - avg_entry) / pip) if t == 1 else ((avg_entry - exit_price) / pip)
        trades.append({
            'pair': pair, 'entry_time': ts[i], 'trend': t,
            'entry': avg_entry, 'exit': exit_price,
            'sl_price': sl_price, 'tp_price': tp_price,
            'exit_reason': exit_reason, 'pips': pips_realized,
            'pip_value_per_lot': pip_val,
        })

    return trades


def size_and_pnl(trades, account_start=ACCOUNT_START):
    trades = sorted(trades, key=lambda t: t['entry_time'])
    running = account_start
    for t in trades:
        sizing = ps.compute_position_size(
            pair=t['pair'],
            side='BUY' if t['trend'] == 1 else 'SELL',
            entry_price=t['entry'],
            sl_price=t['sl_price'],
            account_balance_usd=running,
            risk_pct=RISK_PCT,
            leverage=LEVERAGE,
            margin_safety=0.5,
            snap=SNAP,
            lot_step=0.01, min_lot=0.01, max_lot=10.0,
            existing_margin_used=0.0,
        )
        lot = sizing.lot_size
        pnl_usd = lot * t['pip_value_per_lot'] * t['pips']
        pnl_usd -= lot * t['pip_value_per_lot'] * 1.5
        running = max(running + pnl_usd, 1.0)
        t['lot'] = lot; t['pnl_usd'] = pnl_usd; t['equity_after'] = running
    return trades


def calc_metrics(trades, account_start=ACCOUNT_START):
    if not trades: return None
    trades = sorted(trades, key=lambda t: t['entry_time'])
    eq = account_start; peak = account_start; max_dd_pct = 0.0
    monthly_start_eq = eq; monthly_returns = []; last_month = None
    wins = losses = 0; gross_win = gross_loss = 0.0; exit_counts = {}
    for t in trades:
        pnl = t['pnl_usd']; eq += pnl
        if pnl > 0: wins += 1; gross_win += pnl
        elif pnl < 0: losses += 1; gross_loss += abs(pnl)
        exit_counts[t['exit_reason']] = exit_counts.get(t['exit_reason'], 0) + 1
        if eq > peak: peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd_pct: max_dd_pct = dd
        m_key = (t['entry_time'].year, t['entry_time'].month)
        if last_month is None: last_month = m_key
        elif m_key != last_month:
            monthly_returns.append((eq - monthly_start_eq) / monthly_start_eq * 100)
            monthly_start_eq = eq; last_month = m_key
    if monthly_start_eq != eq:
        monthly_returns.append((eq - monthly_start_eq) / monthly_start_eq * 100)
    n_days = (trades[-1]['entry_time'] - trades[0]['entry_time']).days
    n_months = max(n_days / 30.4375, 1)
    return {
        'n_trades': len(trades),
        'win_rate': wins / len(trades) * 100,
        'profit_factor': gross_win / gross_loss if gross_loss > 0 else float('inf'),
        'total_return_pct': (eq / account_start - 1) * 100,
        'final_equity': eq,
        'max_dd_pct': max_dd_pct * 100,
        'monthly_mean': np.mean(monthly_returns) if monthly_returns else 0,
        'monthly_median': np.median(monthly_returns) if monthly_returns else 0,
        'monthly_p5': np.percentile(monthly_returns, 5) if monthly_returns else 0,
        'monthly_p95': np.percentile(monthly_returns, 95) if monthly_returns else 0,
        'exit_breakdown': exit_counts,
        'n_months': n_months,
        'date_range': (str(trades[0]['entry_time'].date()), str(trades[-1]['entry_time'].date())),
        'trades_per_month': len(trades) / n_months,
    }


def run_option(pairs, timeframe, exit_mode, max_hold, label):
    t0 = time.time()
    print(f'\n{"="*80}', flush=True)
    print(f'  {label}', flush=True)
    print(f'{"="*80}', flush=True)

    active_pairs = []
    for pair in pairs:
        df = load_pair(pair)
        if df is not None and len(df) > EMA_200 * 2 + 100:
            active_pairs.append(pair)
    print(f'  Pairs: {len(active_pairs)}/{len(pairs)} active', flush=True)

    all_trades = []
    for idx, pair in enumerate(active_pairs):
        df = load_pair(pair)
        trades = run_signals_fast(pair, df, timeframe, exit_mode, max_hold)
        all_trades.extend(trades)
        elapsed = time.time() - t0
        print(f'    [{idx+1}/{len(active_pairs)}] {pair}: {len(trades)} trades ({elapsed:.0f}s)', flush=True)

    if not all_trades:
        print('  No trades!', flush=True)
        return None

    t_sizing = time.time()
    all_trades = size_and_pnl(all_trades)
    m = calc_metrics(all_trades)
    print(f'  Sizing: {time.time()-t_sizing:.1f}s', flush=True)
    print(f'  Total: {m["n_trades"]} trades / {m["n_months"]:.1f} months ({time.time()-t0:.0f}s)', flush=True)
    print(f'  Trades/mo: {m["trades_per_month"]:.1f}  WR: {m["win_rate"]:.1f}%  PF: {m["profit_factor"]:.2f}', flush=True)
    print(f'  Monthly: mean={m["monthly_mean"]:.2f}%  median={m["monthly_median"]:.2f}%', flush=True)
    print(f'  P5={m["monthly_p5"]:.2f}%  P95={m["monthly_p95"]:.2f}%', flush=True)
    print(f'  MaxDD: {m["max_dd_pct"]:.2f}%  Final: ${m["final_equity"]:,.0f}', flush=True)
    print(f'  Exits: {m["exit_breakdown"]}', flush=True)
    return m


def main():
    t_start = time.time()
    print('=' * 80, flush=True)
    print('  STRUCTURED ENTRY — OPTIONS ANALYSIS', flush=True)
    print('  Target: 35%+ monthly EV with DD < 7%', flush=True)
    print('=' * 80, flush=True)

    baseline = run_option(BASE_PAIRS, '30min', 'standard', 50, 'BASELINE: 6 pairs, 30min, standard')
    option_a  = run_option(ALL_PAIRS, '30min', 'standard', 50, 'OPTION A: All 28 pairs, 30min, standard')
    option_b  = run_option(BASE_PAIRS, '15min', 'standard', 100, 'OPTION B: 6 pairs, 15min, standard')
    option_c  = run_option(BASE_PAIRS, '30min', 'trailing', 50, 'OPTION C: 6 pairs, 30min, trailing')

    print('\n' + '=' * 80, flush=True)
    print('  COMPARISON TABLE', flush=True)
    print('=' * 80, flush=True)

    models = [baseline, option_a, option_b, option_c]
    labels_s = ['Baseline', 'Opt A (26p)', 'Opt B (15m)', 'Opt C (trail)']
    tf_l = ['30min', '30min', '15min', '30min']
    ex_l = ['standard', 'standard', 'standard', 'trailing']

    def fv(m, k, f):
        if m is None: return 'N/A'
        return f.format(m[k])

    rows = [
        ('Pairs', [str(len(BASE_PAIRS)) if i != 1 else str(len(ALL_PAIRS)) for i in range(4)]),
        ('Timeframe', tf_l),
        ('Exits', ex_l),
        ('Trades/mo', [fv(m, 'trades_per_month', '{:.1f}') for m in models]),
        ('Monthly mean', [fv(m, 'monthly_mean', '{:.2f}%') for m in models]),
        ('Monthly median', [fv(m, 'monthly_median', '{:.2f}%') for m in models]),
        ('Monthly P5', [fv(m, 'monthly_p5', '{:.2f}%') for m in models]),
        ('Monthly P95', [fv(m, 'monthly_p95', '{:.2f}%') for m in models]),
        ('Max DD', [fv(m, 'max_dd_pct', '{:.2f}%') for m in models]),
        ('Win rate', [fv(m, 'win_rate', '{:.1f}%') for m in models]),
        ('Profit factor', [fv(m, 'profit_factor', '{:.2f}') for m in models]),
        ('Final equity', [fv(m, 'final_equity', '${:,.0f}') for m in models]),
    ]

    hdr = f'  {"Metric":<20} {labels_s[0]:>14} {labels_s[1]:>14} {labels_s[2]:>14} {labels_s[3]:>14}'
    print(hdr, flush=True)
    print('  ' + '-' * 72, flush=True)
    for label, vals in rows:
        print(f'  {label:<20} {vals[0]:>14} {vals[1]:>14} {vals[2]:>14} {vals[3]:>14}', flush=True)

    print(f'\n  Total runtime: {time.time()-t_start:.0f}s', flush=True)

    print('\n' + '=' * 80, flush=True)
    print('  35% MONTHLY EV TARGET CHECK', flush=True)
    print('=' * 80, flush=True)
    for name, m in [('Baseline', baseline), ('Option A', option_a),
                     ('Option B', option_b), ('Option C', option_c)]:
        if m is None:
            print(f'  {name}: NO DATA', flush=True); continue
        target_met = m['monthly_mean'] >= 35
        dd_ok = m['max_dd_pct'] < 7
        status = 'PASS' if (target_met and dd_ok) else ('PARTIAL' if target_met or dd_ok else 'FAIL')
        print(f'  {name}: EV={m["monthly_mean"]:.2f}%  DD={m["max_dd_pct"]:.2f}%  -> {status}', flush=True)
    print('=' * 80, flush=True)


if __name__ == '__main__':
    main()
