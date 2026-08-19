"""MR Baseline Forensic Analysis — read-only reproduction of test_final_scalper.py logic with full metrics."""
import pickle, json, sys, os
import numpy as np
import pandas as pd
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional

sys.path.insert(0, '/root')
import position_sizing as ps

# Config (exact copy from test_final_scalper.py)
PAIRS=['EUR/CHF','GBP/USD','AUD/JPY','EUR/USD','USD/CHF','GBP/JPY','USD/JPY','AUD/USD','NZD/USD','EUR/GBP','CAD/JPY','AUD/CAD','GBP/AUD','EUR/AUD','NZD/JPY','EUR/CAD','GBP/CAD','AUD/CHF','NZD/CHF','CAD/CHF']
DEFAULT_USD={'USD':1.0,'EUR':1.08,'GBP':1.26,'JPY':0.0067,'CHF':0.88,'AUD':0.65,'CAD':0.74,'NZD':0.60}
SNAP=ps.QuoteSnapshot(usd_value=DEFAULT_USD)
LEV=100; ACC=2500; RISK=0.020
SESSIONS={'london':(7,16),'new_york':(12,21)}; SKIP_FRI=20; SKIP_MON=3
SPREAD={'EUR/USD':0.8,'GBP/USD':1.0,'USD/JPY':1.0,'USD/CHF':1.2,'AUD/USD':0.9,'NZD/USD':1.2,'EUR/GBP':1.2,'EUR/CHF':1.5,'EUR/JPY':2.0,'GBP/JPY':3.0,'AUD/JPY':2.0,'CAD/JPY':2.5,'NZD/JPY':3.0,'EUR/AUD':2.0,'EUR/CAD':2.5,'GBP/AUD':3.5,'GBP/CAD':3.5,'AUD/CAD':2.0,'AUD/CHF':2.5,'NZD/CHF':3.0,'CAD/CHF':3.0}


def igs(ts):
    h, d = ts.hour, ts.dayofweek
    if d == 4 and h >= SKIP_FRI: return False
    if d == 0 and h < SKIP_MON: return False
    if d >= 5: return False
    for s, (s2, e) in SESSIONS.items():
        if s2 <= h < e: return True
    return False


@dataclass
class Trade:
    pair: str
    trend: int
    entry: float
    sl: float
    tp: float
    lot: float
    pip: float
    pv: float
    spread: float
    entry_bar: int
    entry_ts: pd.Timestamp
    exit_price: float = 0.0
    exit_ts: object = None
    pnl: float = 0.0
    gross_pnl: float = 0.0
    cost: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    commission: float = 0.0
    exit_reason: str = ''
    is_win: bool = False


def load_pair_data(start, end):
    pdata = {}
    for pair in PAIRS:
        pk = pair.replace('/', '_')
        try:
            with open(f'/root/data/{pk}.pkl', 'rb') as f:
                raw = pickle.load(f)
        except FileNotFoundError:
            continue
        df = raw.get(pair)
        if df is None: continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
        df.index = idx
        df = df[df.index >= start]; df = df[df.index <= end]
        if len(df) < 500: continue
        pip = ps.pip_size_for_pair(pair); pv = ps.pip_value_per_lot(pair, SNAP)
        d30 = df[['open','high','low','close']].resample('30min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        d4h = df[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        daily = df[['open','high','low','close']].resample('1D').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna(subset=['close'])
        e200 = d4h['close'].ewm(span=200, adjust=False).mean()
        e50 = d4h['close'].ewm(span=50, adjust=False).mean()
        pdata[pair] = {
            'c': d30['close'].values, 'h': d30['high'].values, 'lo': d30['low'].values,
            'o': d30['open'].values, 'ts': d30.index, 'n': len(d30),
            'e200': e200.reindex(d30.index, method='ffill').values,
            'e50': e50.reindex(d30.index, method='ffill').values,
            'daily': daily, 'pip': pip, 'pv': pv, 'spread': SPREAD.get(pair, 2.0),
        }
    return pdata


def run_forensic_sim(pdata, friction='realistic', commission_override=None, slippage_override=None,
                     max_conc=10, rr=2.7, risk=RISK, block_entries=False):
    if friction == 'ideal': spread_m = 0; slp_side = slippage_override if slippage_override is not None else 0.5
    elif friction == 'realistic': spread_m = 1; slp_side = slippage_override if slippage_override is not None else 0.3
    else: spread_m = 2; slp_side = slippage_override if slippage_override is not None else 1.0
    commission = commission_override if commission_override is not None else 3.50

    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]['n'])
    ref = pdata[ref_pair]; n_bars = ref['n']

    bal = ACC; peak = ACC; mdd = 0; open_pos = []
    trades = []
    daily_sb = ACC; daily_d = None
    n_sl=0; n_tp=0; n_sc=0; n_mh=0; n_dl=0; n_rej=0

    for i in range(250, n_bars - 1):
        ts_now = ref['ts'][i]
        today = ts_now.date()
        if daily_d != today: daily_d = today; daily_sb = bal

        # Daily loss limit
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos['pair'])
                if pd_ is None or i >= pd_['n']: continue
                ep = pd_['c'][i] - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if pos['trend'] == 1 else pd_['c'][i] + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                gross = (ep - pos['entry']) * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission
                sp_cost = pos['spread'] * 0.5 * spread_m * pos['pip'] * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot'] if pos['trend'] == 1 else pos['spread'] * 0.5 * spread_m * pos['pip'] * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot']
                sl_cost = slp_side * pos['pip'] * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot'] if pos['trend'] == 1 else slp_side * pos['pip'] * pos['trend'] / pos['pip'] * pos['pv'] * pos['lot']
                pnl = gross - cost
                bal += pnl; n_dl += 1
                trades.append(Trade(pair=pos['pair'], trend=pos['trend'], entry=pos['entry'], sl=pos['sl'], tp=pos['tp'],
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=ep, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    spread_cost=abs(sp_cost), slippage_cost=abs(sl_cost), commission=pos['lot']*commission,
                    exit_reason='DL', is_win=(pnl > 0)))
            open_pos.clear(); continue

        # Manage open positions
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos['pair'])
            if pd_ is None or i >= pd_['n']: remaining.append(pos); continue
            bar_lo = pd_['lo'][i]; bar_hi = pd_['h'][i]; bar_cl = pd_['c'][i]
            tr = pos['trend']; sl = pos['sl']; tp = pos['tp']; closed = False

            if tr == 1 and bar_lo <= sl:
                gross = (sl - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost
                bal += pnl; n_sl += 1; closed = True
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=sl, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot']*commission, exit_reason='SL', is_win=(pnl > 0)))
            elif tr == -1 and bar_hi >= sl:
                gross = (pos['entry'] - sl) / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost
                bal += pnl; n_sl += 1; closed = True
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=sl, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot']*commission, exit_reason='SL', is_win=(pnl > 0)))
            if not closed and tr == 1 and bar_hi >= tp:
                gross = (tp - pos['entry']) / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost
                bal += pnl; n_tp += 1; closed = True
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=tp, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot']*commission, exit_reason='TP', is_win=(pnl > 0)))
            elif not closed and tr == -1 and bar_lo <= tp:
                gross = (pos['entry'] - tp) / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost
                bal += pnl; n_tp += 1; closed = True
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=tp, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot']*commission, exit_reason='TP', is_win=(pnl > 0)))
            if not closed and not igs(ref['ts'][i]):
                ep = bar_cl - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if tr == 1 else bar_cl + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                gross = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost
                bal += pnl; n_sc += 1; closed = True
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=ep, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot']*commission, exit_reason='SC', is_win=(pnl > 0)))
            if not closed and (i - pos['bar']) >= 50:
                ep = bar_cl - (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip'] if tr == 1 else bar_cl + (pos['spread'] * 0.5 * spread_m + slp_side) * pos['pip']
                gross = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot']
                cost = pos['lot'] * commission; pnl = gross - cost
                bal += pnl; n_mh += 1; closed = True
                trades.append(Trade(pair=pos['pair'], trend=tr, entry=pos['entry'], sl=sl, tp=tp,
                    lot=pos['lot'], pip=pos['pip'], pv=pos['pv'], spread=pos['spread'],
                    entry_bar=pos['bar'], entry_ts=pos['entry_ts'],
                    exit_price=ep, exit_ts=ts_now, pnl=pnl, gross_pnl=gross, cost=cost,
                    commission=pos['lot']*commission, exit_reason='MH', is_win=(pnl > 0)))
            if not closed: remaining.append(pos)
        open_pos = remaining

        bal = max(bal, 1.0)
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd

        if block_entries: continue
        if not igs(ts_now) or len(open_pos) >= max_conc: continue
        for pair in PAIRS:
            if len(open_pos) >= max_conc: break
            if any(p['pair'] == pair for p in open_pos): continue
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_['n']: continue
            c_val = pd_['c'][i]; ev = pd_['e200'][i]; e5 = pd_['e50'][i]
            if np.isnan(ev) or np.isnan(e5): continue
            tr = 1 if c_val > ev else -1
            if tr == 1 and c_val < e5 * 0.998: continue
            if tr == -1 and c_val > e5 * 1.002: continue
            if tr == 1:
                if not (c_val < ev * 1.005 and c_val > ev * 0.995): continue
                if max(pd_['h'][max(0, i-20):i]) <= c_val * 1.002: continue
            else:
                if not (c_val > ev * 0.995 and c_val < ev * 1.005): continue
                if min(pd_['lo'][max(0, i-20):i]) >= c_val * 0.998: continue
            d_ts = pd_['daily'].index.asof(ts_now)
            if d_ts not in pd_['daily'].index: continue
            dg = pd_['daily'].loc[d_ts, 'close'] > pd_['daily'].loc[d_ts, 'open']
            if tr == 1 and not dg: continue
            if tr == -1 and dg: continue

            pip = pd_['pip']
            sl = ev * (1 - 0.005) if tr == 1 else ev * (1 + 0.005)
            sl_dist = abs(c_val - sl)
            if sl_dist < 2 * pip: continue
            tp = c_val + sl_dist * rr if tr == 1 else c_val - sl_dist * rr
            entry_fill = c_val + (pd_['spread'] * 0.5 * spread_m + slp_side) * pip if tr == 1 else c_val - (pd_['spread'] * 0.5 * spread_m + slp_side) * pip
            sz = ps.compute_position_size(pair=pair, side='BUY' if tr == 1 else 'SELL', entry_price=entry_fill, sl_price=sl, account_balance_usd=bal, risk_pct=risk, leverage=LEV, margin_safety=0.5, snap=SNAP, lot_step=0.01, min_lot=0.01, max_lot=10.0, existing_margin_used=0.0)
            if not sz.ok: n_rej += 1; continue
            open_pos.append({'pair': pair, 'trend': tr, 'entry': entry_fill, 'sl': sl, 'tp': tp,
                'lot': sz.lot_size, 'bar': i, 'pip': pip, 'pv': pd_['pv'],
                'spread': pd_['spread'], 'entry_ts': ts_now})

    if not trades: return None
    return _compute_metrics(trades, ref, n_bars, mdd)


def _compute_metrics(trades, ref, n_bars, mdd):
    pnls = np.array([t.pnl for t in trades])
    gross_pnls = np.array([t.gross_pnl for t in trades])
    costs = np.array([t.cost for t in trades])

    w = int(np.sum(pnls > 0)); l = int(np.sum(pnls <= 0))
    gw = float(np.sum(pnls[pnls > 0])); gl = float(np.abs(np.sum(pnls[pnls <= 0])))
    nm = max((ref['ts'][min(n_bars-1, len(ref['ts'])-1)] - ref['ts'][250]).days / 30.4375, 1)

    # Monthly returns by trade close month
    monthly_data = defaultdict(lambda: {'pnl': 0.0, 'trades': 0, 'wins': 0, 'gross_pnl': 0.0, 'cost': 0.0})
    for t in trades:
        if t.exit_ts is None: continue
        mkey = t.exit_ts.strftime('%Y-%m')
        monthly_data[mkey]['pnl'] += t.pnl
        monthly_data[mkey]['trades'] += 1
        monthly_data[mkey]['gross_pnl'] += t.gross_pnl
        monthly_data[mkey]['cost'] += t.cost
        if t.pnl > 0: monthly_data[mkey]['wins'] += 1

    month_keys = sorted(monthly_data.keys())
    monthly_rets = []
    monthly_table = []
    prev_eq = ACC; running_eq = ACC; peak_eq = ACC
    mdd_series = []
    equity_at_close = []  # running equity after each trade

    for t in trades:
        running_eq += t.pnl
        equity_at_close.append(running_eq)

    # Build equity curve from trades for drawdown analysis
    eq_arr = np.array([ACC] + equity_at_close)
    running_peak = np.maximum.accumulate(eq_arr)
    dd_arr = np.where(running_peak > 0, (running_peak - eq_arr) / running_peak, 0)

    for mk in month_keys:
        md = monthly_data[mk]
        ret_pct = md['pnl'] / prev_eq * 100 if prev_eq > 0 else 0
        wr = md['wins'] / md['trades'] * 100 if md['trades'] > 0 else 0
        prev_eq += md['pnl']
        if prev_eq > peak_eq: peak_eq = prev_eq
        dd_m = (peak_eq - prev_eq) / peak_eq if peak_eq > 0 else 0
        mdd_series.append(dd_m)
        monthly_rets.append(ret_pct)
        monthly_table.append({
            'month': mk, 'return_pct': round(ret_pct, 4),
            'net_pnl': round(md['pnl'], 2), 'trades': md['trades'],
            'win_rate': round(wr, 1), 'mdd_pct': round(dd_m * 100, 2),
            'gross_pnl': round(md['gross_pnl'], 2), 'cost': round(md['cost'], 2)
        })

    monthly_rets = np.array(monthly_rets)
    mdd_series = np.array(mdd_series)
    trade_returns = pnls  # per-trade $ PnL

    # Drawdown series statistics
    dd_nonzero = dd_arr[dd_arr > 0]
    n_dd_episodes = 0
    dd_durations = []
    current_dd_len = 0
    for d in dd_arr:
        if d > 0:
            current_dd_len += 1
        else:
            if current_dd_len > 0:
                dd_durations.append(current_dd_len)
                n_dd_episodes += 1
            current_dd_len = 0
    if current_dd_len > 0:
        dd_durations.append(current_dd_len)
        n_dd_episodes += 1

    dd_dur_arr = np.array(dd_durations) if dd_durations else np.array([0])

    # Exits count
    exit_counts = defaultdict(int)
    for t in trades:
        exit_counts[t.exit_reason] += 1

    # Cost breakdown
    total_commission = float(np.sum([t.commission for t in trades]))
    total_spread_cost = float(np.sum([t.spread_cost for t in trades]))
    total_slippage_cost = float(np.sum([t.slippage_cost for t in trades]))
    total_cost = float(np.sum(costs))
    total_gross = float(np.sum(gross_pnls))
    total_net = float(np.sum(pnls))

    # Pair breakdown
    pair_data = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0, 'cost': 0.0, 'spread_values': []})
    for t in trades:
        pair_data[t.pair]['trades'] += 1
        pair_data[t.pair]['pnl'] += t.pnl
        pair_data[t.pair]['cost'] += t.cost
        pair_data[t.pair]['spread_values'].append(t.spread)
        if t.pnl > 0: pair_data[t.pair]['wins'] += 1

    pair_stats = {}
    for pair, pd_ in pair_data.items():
        pair_stats[pair] = {
            'trades': pd_['trades'],
            'win_rate': round(pd_['wins'] / pd_['trades'] * 100, 1) if pd_['trades'] > 0 else 0,
            'net_pnl': round(pd_['pnl'], 2),
            'cost': round(pd_['cost'], 2),
            'mean_spread_pips': round(np.mean(pd_['spread_values']), 2)
        }

    # Exit reason breakdown
    exit_breakdown = {}
    for reason in ['SL', 'TP', 'SC', 'MH', 'DL']:
        cnt = exit_counts.get(reason, 0)
        exit_breakdown[reason] = {
            'count': cnt,
            'pct': round(cnt / len(trades) * 100, 1) if trades else 0,
            'total_pnl': round(sum(t.pnl for t in trades if t.exit_reason == reason), 2)
        }

    result = {
        'summary': {
            'trades': len(trades),
            'wins': w, 'losses': l,
            'win_rate': round(w / (w + l) * 100, 2) if (w + l) > 0 else 0,
            'profit_factor': round(gw / gl, 2) if gl > 0 else 99,
            'mdd_pct': round(mdd * 100, 2),
            'final_balance': round(float(equity_at_close[-1]), 2) if equity_at_close else ACC,
            'total_return_pct': round((equity_at_close[-1] / ACC - 1) * 100, 2) if equity_at_close else 0,
            'cagr_pct': round(((equity_at_close[-1] / ACC) ** (1/nm) - 1) * 100, 2) if equity_at_close and nm > 0 else 0,
            'months': round(nm, 1),
            'trades_per_month': round(len(trades) / nm, 1) if nm > 0 else 0,
            'avg_pnl': round(float(np.mean(pnls)), 2),
            'avg_win': round(float(np.mean(pnls[pnls > 0])), 2) if w > 0 else 0,
            'avg_loss': round(float(np.mean(pnls[pnls <= 0])), 2) if l > 0 else 0,
        },
        'costs': {
            'total_cost': round(total_cost, 2),
            'total_commission': round(total_commission, 2),
            'total_spread_cost_approx': round(total_spread_cost, 2),
            'total_slippage_cost_approx': round(total_slippage_cost, 2),
            'cost_per_trade': round(total_cost / len(trades), 2) if trades else 0,
            'commission_per_trade': round(total_commission / len(trades), 2) if trades else 0,
            'pct_of_gross': round(total_cost / total_gross * 100, 2) if total_gross > 0 else 0,
        },
        'monthly_returns': monthly_table,
        'monthly_stats': {},
        'drawdown': {},
        'trade_return_stats': {},
        'variance_stability': {},
        'exit_breakdown': exit_breakdown,
        'pair_stats': pair_stats,
    }

    if len(monthly_rets) > 0:
        result['monthly_stats'] = {
            'mean': round(float(np.mean(monthly_rets)), 4),
            'median': round(float(np.median(monthly_rets)), 4),
            'std': round(float(np.std(monthly_rets, ddof=1)), 4) if len(monthly_rets) > 1 else 0,
            'min': round(float(np.min(monthly_rets)), 4),
            'max': round(float(np.max(monthly_rets)), 4),
            'p1': round(float(np.percentile(monthly_rets, 1)), 4),
            'p5': round(float(np.percentile(monthly_rets, 5)), 4),
            'p10': round(float(np.percentile(monthly_rets, 10)), 4),
            'p25': round(float(np.percentile(monthly_rets, 25)), 4),
            'p75': round(float(np.percentile(monthly_rets, 75)), 4),
            'p90': round(float(np.percentile(monthly_rets, 90)), 4),
            'p95': round(float(np.percentile(monthly_rets, 95)), 4),
            'p99': round(float(np.percentile(monthly_rets, 99)), 4),
            'skewness': round(float(pd.Series(monthly_rets).skew()), 4) if len(monthly_rets) > 2 else 0,
            'kurtosis': round(float(pd.Series(monthly_rets).kurtosis()), 4) if len(monthly_rets) > 3 else 0,
            'cv': round(float(np.std(monthly_rets, ddof=1) / abs(np.mean(monthly_rets))), 4) if len(monthly_rets) > 1 and np.mean(monthly_rets) != 0 else 0,
            'n_months': len(monthly_rets),
            # Lower tail (bad-month risk)
            'p1_label': 'Worst 1% of months',
            'p5_label': 'Worst 5% of months',
            # Upper tail
            'p95_label': 'Best 5% of months',
            'p99_label': 'Best 1% of months',
        }

    if len(dd_arr) > 0:
        result['drawdown'] = {
            'max_dd_pct': round(float(np.max(dd_arr)) * 100, 4),
            'mean_dd_pct': round(float(np.mean(dd_arr)) * 100, 4),
            'median_dd_pct': round(float(np.median(dd_arr)) * 100, 4),
            'std_dd_pct': round(float(np.std(dd_arr, ddof=1)) * 100, 4) if len(dd_arr) > 1 else 0,
            'var_dd_pct_sq': round(float(np.var(dd_arr, ddof=1)) * 10000, 6) if len(dd_arr) > 1 else 0,
            'p75_dd_pct': round(float(np.percentile(dd_arr, 75)) * 100, 4),
            'p90_dd_pct': round(float(np.percentile(dd_arr, 90)) * 100, 4),
            'p95_dd_pct': round(float(np.percentile(dd_arr, 95)) * 100, 4),
            'p99_dd_pct': round(float(np.percentile(dd_arr, 99)) * 100, 4),
            'max_dd_duration_bars': int(np.max(dd_dur_arr)),
            'mean_dd_duration_bars': round(float(np.mean(dd_dur_arr)), 1),
            'median_dd_duration_bars': int(np.median(dd_dur_arr)),
            'n_episodes': n_dd_episodes,
            'n_exceed_1pct': int(np.sum(dd_arr > 0.01)),
            'n_exceed_2pct': int(np.sum(dd_arr > 0.02)),
            'n_exceed_3pct': int(np.sum(dd_arr > 0.03)),
            'n_exceed_5pct': int(np.sum(dd_arr > 0.05)),
            'n_exceed_10pct': int(np.sum(dd_arr > 0.10)),
            'measured_from': 'running equity peak (peak-to-trough via balance peak)',
        }

    # Trade return stats
    if len(pnls) > 0:
        result['trade_return_stats'] = {
            'mean': round(float(np.mean(pnls)), 2),
            'median': round(float(np.median(pnls)), 2),
            'std': round(float(np.std(pnls, ddof=1)), 2),
            'min': round(float(np.min(pnls)), 2),
            'max': round(float(np.max(pnls)), 2),
            'skewness': round(float(pd.Series(pnls).skew()), 4),
            'kurtosis': round(float(pd.Series(pnls).kurtosis()), 4),
        }

    if len(monthly_rets) > 0:
        result['variance_stability'] = {
            'monthly_return_variance': round(float(np.var(monthly_rets, ddof=1)), 6),
            'monthly_return_std': round(float(np.std(monthly_rets, ddof=1)), 4),
            'trade_return_variance': round(float(np.var(pnls, ddof=1)), 2),
            'trade_return_std': round(float(np.std(pnls, ddof=1)), 2),
            'drawdown_variance': round(float(np.var(dd_arr, ddof=1)) * 10000, 6),
            'drawdown_std': round(float(np.std(dd_arr, ddof=1)) * 100, 4),
            'cv_monthly_returns': round(float(np.std(monthly_rets, ddof=1) / abs(np.mean(monthly_rets))), 4) if np.mean(monthly_rets) != 0 else 'inf',
            'monthly_skewness': round(float(pd.Series(monthly_rets).skew()), 4) if len(monthly_rets) > 2 else 0,
            'monthly_kurtosis': round(float(pd.Series(monthly_rets).kurtosis()), 4) if len(monthly_rets) > 3 else 0,
            'trade_skewness': round(float(pd.Series(pnls).skew()), 4) if len(pnls) > 2 else 0,
            'trade_kurtosis': round(float(pd.Series(pnls).kurtosis()), 4) if len(pnls) > 3 else 0,
        }

    return result


def cost_sensitivity_analysis(pdata):
    """Run 6 cost scenarios as requested."""
    scenarios = {
        'A_baseline': {'commission_override': None, 'slippage_override': None, 'friction': 'realistic', 'label': 'A: Current baseline ($3.50/lot, 0.3 pip slp, 1x spread)'},
        'B_4comm': {'commission_override': 4.0, 'slippage_override': None, 'friction': 'realistic', 'label': 'B: $4 round-turn commission'},
        'C_real_s_p95': {'commission_override': None, 'slippage_override': None, 'friction': 'realistic', 'label': 'C: Realistic spread + fixed slippage (no empirical P95)'},
        'D_real_s_p99': {'commission_override': None, 'slippage_override': None, 'friction': 'stressed', 'label': 'D: Stressed spread + stressed slippage (no empirical P99)'},
        'E_4comm_p95': {'commission_override': 4.0, 'slippage_override': None, 'friction': 'realistic', 'label': 'E: $4 commission + realistic friction'},
        'F_4comm_p99': {'commission_override': 4.0, 'slippage_override': None, 'friction': 'stressed', 'label': 'F: $4 commission + stressed friction'},
    }
    results = {}
    for key, cfg in scenarios.items():
        print(f"  Running {cfg['label']}...")
        r = run_forensic_sim(pdata, friction=cfg['friction'], commission_override=cfg['commission_override'],
                             slippage_override=cfg['slippage_override'])
        if r:
            results[key] = {
                'label': cfg['label'],
                'trades': r['summary']['trades'],
                'win_rate': r['summary']['win_rate'],
                'net_pnl': r['summary']['final_balance'] - ACC,
                'profit_factor': r['summary']['profit_factor'],
                'final_balance': r['summary']['final_balance'],
                'max_dd_pct': r['summary']['mdd_pct'],
                'mean_monthly_return': r['monthly_stats'].get('mean', 0),
                'median_monthly_return': r['monthly_stats'].get('median', 0),
                'p5_monthly': r['monthly_stats'].get('p5', 0),
                'p95_monthly': r['monthly_stats'].get('p95', 0),
                'p99_monthly': r['monthly_stats'].get('p99', 0),
            }
    return results


def filter_effectiveness(pdata):
    """Run with and without session filter to measure its effect."""
    print("  Running WITH session filter (baseline)...")
    r_with = run_forensic_sim(pdata, friction='realistic')
    print("  Running WITHOUT session filter (block_entries=False but igs always True)...")
    # We need a custom sim that skips the igs check for entries only
    # Easiest: patch igs to always return True, but only for entry block
    # Instead, run with block_entries=True won't work. Let's do a direct comparison.
    # We'll modify igs temporarily to always True for entries
    import types
    original_igs = globals()['igs']
    globals()['igs'] = lambda ts: True
    r_without_session = run_forensic_sim(pdata, friction='realistic')
    globals()['igs'] = original_igs

    if r_with and r_without_session:
        tw = r_with['summary']['trades']
        wo = r_without_session['summary']['trades']
        return {
            'session_filter': {
                'description': 'London(7-16) + New York(12-21) + Fri cutoff 20h + Mon skip before 3h + Sat/Sun skip',
                'trades_with': tw,
                'trades_without': wo,
                'trades_removed': wo - tw,
                'pct_removed': round((wo - tw) / wo * 100, 1) if wo > 0 else 0,
                'net_pnl_with': r_with['summary']['final_balance'] - ACC,
                'net_pnl_without': r_without_session['summary']['final_balance'] - ACC,
                'pf_with': r_with['summary']['profit_factor'],
                'pf_without': r_without_session['summary']['profit_factor'],
                'mdd_with': r_with['summary']['mdd_pct'],
                'mdd_without': r_without_session['summary']['mdd_pct'],
            },
            'spread_filter': {
                'exists': False,
                'note': 'Spread is applied as entry/exit COST, not as a trade BLOCKING filter',
                'implementation': 'SPREAD dict defines pips per pair; applied as cost at entry fill and exit fill',
            },
            'weekend_filter': {
                'exists': True,
                'note': 'Same as session filter: d>=5 returns False; part of igs()',
            },
            'news_filter': {
                'exists': False,
                'note': 'NOT IMPLEMENTED / NOT TESTABLE WITH CURRENT DATA',
                'data_requirement': 'News event timestamps with currency/country impact scores',
            },
            'p95_slippage_filter': {
                'exists': False,
                'note': 'ABSENT — only fixed 0.3 pip slippage (realistic) or 1.0 pip (stressed)',
            },
            'p99_slippage_filter': {
                'exists': False,
                'note': 'ABSENT — only fixed slippage model',
            },
        }
    return None


if __name__ == '__main__':
    print("=" * 80)
    print("  MR BASELINE FORENSIC ANALYSIS")
    print("=" * 80)

    print("\n[1] Loading data (2018-01-01 to 2026-07-19)...")
    pdata = load_pair_data('2018-01-01', '2026-07-19')
    print(f"    Loaded {len(pdata)} pairs")

    print("\n[2] Running baseline forensic simulation...")
    baseline = run_forensic_sim(pdata, friction='realistic')
    if baseline:
        print(f"    Trades={baseline['summary']['trades']} WR={baseline['summary']['win_rate']}% "
              f"PF={baseline['summary']['profit_factor']} MDD={baseline['summary']['mdd_pct']}%")
        print(f"    Final=${baseline['summary']['final_balance']:,.0f} Return={baseline['summary']['total_return_pct']}%")

    print("\n[3] Running cost sensitivity analysis...")
    cost_sens = cost_sensitivity_analysis(pdata)

    print("\n[4] Running filter effectiveness analysis...")
    filters = filter_effectiveness(pdata)

    # Save JSON
    os.makedirs('/root/nestquant/logs', exist_ok=True)
    output = {
        'baseline': baseline,
        'cost_sensitivity': cost_sens,
        'filter_effectiveness': filters,
    }
    with open('/root/nestquant/logs/mr_baseline_metrics.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print("\n  Saved /root/nestquant/logs/mr_baseline_metrics.json")

    print("\n[DONE]")
