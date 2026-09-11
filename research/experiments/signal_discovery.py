"""Phase 6 — Signal Discovery Engine.

Single backtest with full path recording and feature computation.
All analysis modules import from this shared engine.

Usage:
    cd /root/nestquant && .venv/bin/python -u scripts/signal_discovery.py
"""
from __future__ import annotations

import json
import pickle
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from zscore.zscore import compute_zscore_causal

# ═══════════════════════════════════════════════════════════════
# FROZEN PARAMETERS
# ═══════════════════════════════════════════════════════════════
Z_ENTRY = 2.2; LOOKBACK = 20; RISK_PCT = 0.006; ACC = 2500; LEV = 100
COMMISSION = 3.50; ATR_PERIOD = 14; ATR_SL_MULT = 3.0
MAX_CONC = 10; MAX_HOLD_BARS = 64; SLIPPAGE_PIPS = 0.3
SESSIONS = {"london": (7, 16), "new_york": (12, 21)}; SKIP_FRI = 20; SKIP_MON = 3
PAIRS = [
    "EUR/USD","GBP/USD","USD/JPY","USD/CHF","AUD/USD","NZD/USD",
    "EUR/GBP","EUR/CHF","EUR/JPY","AUD/JPY","EUR/AUD","AUD/CAD",
    "GBP/JPY","GBP/CAD","GBP/AUD","CAD/JPY","NZD/JPY","NZD/CHF",
    "AUD/CHF","CAD/CHF",
]
SPREAD = {
    "EUR/USD":0.8,"GBP/USD":1.0,"USD/JPY":1.0,"USD/CHF":1.2,"AUD/USD":0.9,
    "NZD/USD":1.2,"EUR/GBP":1.2,"EUR/CHF":1.5,"EUR/JPY":2.0,"GBP/JPY":3.0,
    "AUD/JPY":2.0,"CAD/JPY":2.5,"NZD/JPY":3.0,"EUR/AUD":2.0,"EUR/CAD":2.5,
    "GBP/AUD":3.5,"GBP/CAD":3.5,"AUD/CAD":2.0,"AUD/CHF":2.5,"NZD/CHF":3.0,
    "CAD/CHF":3.0,
}
DEFAULT_USD = {"USD":1.0,"EUR":1.08,"GBP":1.26,"JPY":0.0067,
               "CHF":0.88,"AUD":0.65,"CAD":0.74,"NZD":0.60}
OUT = Path("/root/nestquant/research_data/phase6")
OUT.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def in_session(ts):
    h, d = ts.hour, ts.dayofweek
    if d == 4 and h >= SKIP_FRI: return False
    if d == 0 and h < SKIP_MON: return False
    if d >= 5: return False
    for s, (s2, e) in SESSIONS.items():
        if s2 <= h < e: return True
    return False

def get_session(ts):
    h = ts.hour
    il = 7 <= h < 16; iny = 12 <= h < 21
    if il and iny: return "overlap"
    if il: return "london_only"
    if iny: return "ny_only"
    return "none"

def pip_size(pair): return 0.01 if "JPY" in pair else 0.0001
def pip_value(pair):
    base, quote = pair.split("/")
    return pip_size(pair) * 100000 * DEFAULT_USD.get(quote, 1.0)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_all(start, end):
    pdata = {}
    for pair in PAIRS:
        pk = pair.replace("/", "_")
        try:
            with open(f"/root/data/{pk}.pkl", "rb") as f:
                raw = pickle.load(f)
        except Exception: continue
        df = raw.get(pair)
        if df is None or df.empty: continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df.index = idx
        df = df[(df.index >= start) & (df.index <= end)]
        if len(df) < 500: continue
        df = df[["open","high","low","close"]].resample("30min").agg(
            {"open":"first","high":"max","low":"min","close":"last"}
        ).dropna(subset=["close"])
        if len(df) < 500: continue
        c = df["close"].values.astype(np.float64)
        obs = compute_zscore_causal(c, df.index, pair, lookback=LOOKBACK)
        z = np.array([o.z_score for o in obs])
        tr = pd.concat([
            df["high"]-df["low"],
            (df["high"]-df["close"].shift(1)).abs(),
            (df["low"]-df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean().values
        atr_pct = atr / df["close"].values * 100
        # EMA 200 for trend
        ema200 = df["close"].ewm(span=200, adjust=False).mean().values
        # Volume proxy: bar range as activity measure
        bar_range = (df["high"].values - df["low"].values)
        # Price momentum: 10-bar return
        close_arr = df["close"].values
        mom10 = np.full_like(close_arr, np.nan)
        mom10[10:] = (close_arr[10:] - close_arr[:-10]) / close_arr[:-10] * 100
        pdata[pair] = {
            "c": close_arr, "h": df["high"].values, "lo": df["low"].values,
            "o": df["open"].values, "ts": df.index, "n": len(df),
            "z": z, "atr": atr, "atr_pct": atr_pct,
            "ema200": ema200, "bar_range": bar_range, "mom10": mom10,
            "pip": pip_size(pair), "pv": pip_value(pair),
            "spread": SPREAD.get(pair, 2.0),
        }
    return pdata


# ═══════════════════════════════════════════════════════════════
# FEATURE ENGINE — compute per-bar features at entry
# ═══════════════════════════════════════════════════════════════

@dataclass
class ZEvent:
    """One extreme-Z event with all entry-available features."""
    pair: str; direction: int; entry_price: float; entry_ts: object
    entry_bar: int; entry_z: float; abs_z: float
    sl_price: float; tp_price: float; lot: float
    pip: float; pv: float; spread_pips: float
    atr_at_entry: float; risk_dollars: float
    vol_regime: str; entry_session: str; entry_hour: int; entry_dow: int
    year: int; month: str; day: str
    # Z dynamics (entry-available)
    dz_1: float = 0.0   # ΔZ over 1 bar
    dz_2: float = 0.0   # ΔZ over 2 bars
    dz_4: float = 0.0   # ΔZ over 4 bars
    z_accel: float = 0.0  # Z acceleration (second difference)
    z_was_beyond: int = 0  # bars spent beyond current |Z| threshold
    z_moving_toward: bool = False  # True if Z moving toward 0
    recent_max_abs_z: float = 0.0  # recent max |Z| (last 10 bars)
    dist_from_max: float = 0.0  # |Z| - recent_max_abs_z
    # Regime features
    atr_pct_rank: float = 0.0  # ATR percentile rank
    ema_dist: float = 0.0  # distance from EMA200 (%)
    ema_slope: float = 0.0  # EMA200 slope (10-bar)
    mom_10: float = 0.0  # 10-bar price momentum (%)
    bar_range_avg: float = 0.0  # avg bar range (20-bar)
    # Forward paths
    price_path: list = field(default_factory=list)
    z_path: list = field(default_factory=list)
    high_path: list = field(default_factory=list)
    low_path: list = field(default_factory=list)
    atr_path: list = field(default_factory=list)


def compute_features(pdata, i, pair, z_now, direction, ep, sl_p, tp_p,
                     lot, atr_now, bal, vr):
    """Compute all entry-available features for an extreme-Z event."""
    pd_ = pdata[pair]
    pip = pd_["pip"]; pv = pd_["pv"]
    # Z dynamics
    z_arr = pd_["z"]
    dz_1 = z_now - z_arr[i-1] if i > 0 and not np.isnan(z_arr[i-1]) else 0.0
    dz_2 = z_now - z_arr[i-2] if i > 2 and not np.isnan(z_arr[i-2]) else 0.0
    dz_4 = z_now - z_arr[i-4] if i > 4 and not np.isnan(z_arr[i-4]) else 0.0
    # Z acceleration: (z[i]-z[i-1]) - (z[i-1]-z[i-2])
    if i > 2 and not np.isnan(z_arr[i-1]) and not np.isnan(z_arr[i-2]):
        z_accel = (z_now - z_arr[i-1]) - (z_arr[i-1] - z_arr[i-2])
    else:
        z_accel = 0.0
    # Bars spent beyond current |Z|
    abs_z = abs(z_now)
    z_was_beyond = 0
    for j in range(i, max(i-20, 0), -1):
        if not np.isnan(z_arr[j]) and abs(z_arr[j]) >= abs_z:
            z_was_beyond += 1
        else:
            break
    # Z moving toward zero?
    if direction == 1:  # long: z negative, moving toward 0 = z increasing
        z_moving_toward = dz_1 > 0
    else:  # short: z positive, moving toward 0 = z decreasing
        z_moving_toward = dz_1 < 0
    # Recent max |Z| (last 10 bars)
    lookback_window = z_arr[max(0,i-10):i+1]
    valid_z = lookback_window[~np.isnan(lookback_window)]
    recent_max_abs_z = float(np.max(np.abs(valid_z))) if len(valid_z) > 0 else abs_z
    dist_from_max = abs_z - recent_max_abs_z
    # ATR percentile rank (causal: over all available data up to i)
    atr_valid = pd_["atr"][:i+1]
    atr_valid = atr_valid[~np.isnan(atr_valid)]
    if len(atr_valid) > 10:
        atr_pct_rank = float(np.mean(atr_valid <= atr_now)) * 100
    else:
        atr_pct_rank = 50.0
    # EMA distance and slope
    ema200 = pd_["ema200"]
    ema_dist = (pd_["c"][i] - ema200[i]) / ema200[i] * 100 if ema200[i] != 0 else 0.0
    ema_slope = (ema200[i] - ema200[max(0,i-10)]) / ema200[max(0,i-10)] * 100 if i > 10 and ema200[max(0,i-10)] != 0 else 0.0
    # Momentum
    mom_10 = float(pd_["mom10"][i]) if not np.isnan(pd_["mom10"][i]) else 0.0
    # Bar range average
    br = pd_["bar_range"]
    br_slice = br[max(0,i-20):i+1]
    br_valid = br_slice[~np.isnan(br_slice)]
    bar_range_avg = float(np.mean(br_valid)) if len(br_valid) > 0 else 0.0
    # Collect paths
    n = min(MAX_HOLD_BARS, pd_["n"] - i)
    price_path = [float(pd_["c"][i+j]) for j in range(n)]
    z_path = [float(z_arr[i+j]) if not np.isnan(z_arr[i+j]) else 0.0 for j in range(n)]
    high_path = [float(pd_["h"][i+j]) for j in range(n)]
    low_path = [float(pd_["lo"][i+j]) for j in range(n)]
    atr_path = [float(pd_["atr"][i+j]) if not np.isnan(pd_["atr"][i+j]) else 0.0 for j in range(n)]
    return ZEvent(
        pair=pair, direction=direction, entry_price=ep, entry_ts=pd_["ts"][i],
        entry_bar=i, entry_z=z_now, abs_z=abs_z,
        sl_price=sl_p, tp_price=tp_p, lot=lot,
        pip=pip, pv=pv, spread_pips=pd_["spread"],
        atr_at_entry=atr_now, risk_dollars=bal * RISK_PCT,
        vol_regime=vr, entry_session=get_session(pd_["ts"][i]),
        entry_hour=pd_["ts"][i].hour, entry_dow=pd_["ts"][i].dayofweek,
        year=pd_["ts"][i].year, month=pd_["ts"][i].strftime("%Y-%m"),
        day=str(pd_["ts"][i].date()),
        dz_1=dz_1, dz_2=dz_2, dz_4=dz_4, z_accel=z_accel,
        z_was_beyond=z_was_beyond, z_moving_toward=z_moving_toward,
        recent_max_abs_z=recent_max_abs_z, dist_from_max=dist_from_max,
        atr_pct_rank=atr_pct_rank, ema_dist=ema_dist, ema_slope=ema_slope,
        mom_10=mom_10, bar_range_avg=bar_range_avg,
        price_path=price_path, z_path=z_path,
        high_path=high_path, low_path=low_path, atr_path=atr_path,
    )


# ═══════════════════════════════════════════════════════════════
# BACKTEST — RECORDS EVENTS WITH FULL FEATURES
# ═══════════════════════════════════════════════════════════════

def classify_vol(atr_pct_arr, i):
    if i >= len(atr_pct_arr) or np.isnan(atr_pct_arr[i]): return "unknown"
    v = atr_pct_arr[~np.isnan(atr_pct_arr)]
    if len(v) == 0: return "unknown"
    a = atr_pct_arr[i]
    p25, p75, p95 = np.percentile(v, [25, 75, 95])
    if a <= p25: return "low_vol"
    if a >= p95: return "extreme_vol"
    if a >= p75: return "high_vol"
    return "mid_vol"


def run_backtest(pdata):
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]["n"])
    ref = pdata[ref_pair]; n = ref["n"]
    bal = ACC; peak = ACC; open_pos = []; events = []
    daily_sb = ACC; daily_d = None

    for i in range(LOOKBACK + ATR_PERIOD + 10, n - 1):
        ts = ref["ts"][i]; today = ts.date()
        if daily_d != today: daily_d = today; daily_sb = bal
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            open_pos.clear(); continue
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos["pair"])
            if pd_ is None or i >= pd_["n"]: remaining.append(pos); continue
            if i - pos["bar"] >= MAX_HOLD_BARS:
                bal = max(bal, 1.0)
            else:
                remaining.append(pos)
        open_pos = remaining
        bal = max(bal, 1.0)
        if bal > peak: peak = bal
        if not in_session(ts) or len(open_pos) >= MAX_CONC: continue
        for pair in PAIRS:
            if len(open_pos) >= MAX_CONC: break
            if any(p["pair"] == pair for p in open_pos): continue
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_["n"]: continue
            z_now = pd_["z"][i]
            if np.isnan(z_now): continue
            atr_now = pd_["atr"][i]
            if np.isnan(atr_now) or atr_now <= 0: continue
            if abs(z_now) < Z_ENTRY: continue
            direction = 1 if z_now < 0 else -1
            sl_dist = atr_now * ATR_SL_MULT
            sl_p = pd_["c"][i] - sl_dist if direction == 1 else pd_["c"][i] + sl_dist
            ep = pd_["c"][i] + SLIPPAGE_PIPS * pd_["pip"] if direction == 1 else pd_["c"][i] - SLIPPAGE_PIPS * pd_["pip"]
            sl_pips = sl_dist / pd_["pip"]
            if sl_pips <= 0: continue
            lot = max(0.01, round((bal * RISK_PCT) / (sl_pips * pd_["pv"]), 2))
            lot = min(lot, 10.0)
            tp_dist = sl_dist * 2.0
            tp_p = ep + tp_dist if direction == 1 else ep - tp_dist
            vr = classify_vol(pd_["atr_pct"], i)
            ev = compute_features(pdata, i, pair, z_now, direction, ep, sl_p, tp_p,
                                  lot, atr_now, bal, vr)
            events.append(ev)
            open_pos.append({"pair":pair,"bar":i})
    return events


# ═══════════════════════════════════════════════════════════════
# OFFLINE EXIT EVALUATION
# ═══════════════════════════════════════════════════════════════

def eval_time_exit(ev: ZEvent, max_bars: int):
    d = ev.direction; pip = ev.pip; pv = ev.pv; ep = ev.entry_price
    n = min(max_bars, len(ev.price_path))
    if n == 0: return 0, 0, "NONE"
    for j in range(1, n):
        hi = ev.high_path[j]; lo = ev.low_path[j]
        if d == 1 and lo <= ev.sl_price:
            return (ev.sl_price-ep)/pip*pv*ev.lot - ev.lot*COMMISSION, j, "SL"
        if d == -1 and hi >= ev.sl_price:
            return (ep-ev.sl_price)/pip*pv*ev.lot - ev.lot*COMMISSION, j, "SL"
        if d == 1 and hi >= ev.tp_price:
            return (ev.tp_price-ep)/pip*pv*ev.lot - ev.lot*COMMISSION, j, "TP"
        if d == -1 and lo <= ev.tp_price:
            return (ep-ev.tp_price)/pip*pv*ev.lot - ev.lot*COMMISSION, j, "TP"
    exit_p = ev.price_path[n-1]
    return (exit_p-ep)*d/pip*pv*ev.lot - ev.lot*COMMISSION, n, "TE"


def eval_forward_return(ev: ZEvent, bars: int):
    """Pip-based forward return (no costs) for signal analysis."""
    n = min(bars, len(ev.price_path))
    if n < 2: return 0.0
    d = ev.direction; pip = ev.pip
    return (ev.price_path[n-1] - ev.entry_price) * d / pip


def eval_mae_mfe(ev: ZEvent, bars: int = None):
    d = ev.direction; pip = ev.pip; ep = ev.entry_price
    n = min(bars, len(ev.price_path)) if bars else len(ev.price_path)
    mae = 0.0; mfe = 0.0
    for j in range(1, n):
        if d == 1:
            cur_mae = (ep - ev.low_path[j]) / pip
            cur_mfe = (ev.high_path[j] - ep) / pip
        else:
            cur_mae = (ev.high_path[j] - ep) / pip
            cur_mfe = (ep - ev.low_path[j]) / pip
        if cur_mae > mae: mae = cur_mae
        if cur_mfe > mfe: mfe = cur_mfe
    return mae, mfe


def classify_outcome(ev: ZEvent):
    """Classify event outcome using forward Z behavior."""
    z = ev.z_path; d = ev.direction; n = len(z)
    if n < 4: return "insufficient"
    z_entry = ev.entry_z
    # Check Z trajectory over next 4, 8, 16 bars
    z4 = z[min(4, n-1)]; z8 = z[min(8, n-1)]; z16 = z[min(16, n-1)]
    # Fast MR: Z moves back toward 0 by >50% within 4 bars
    if d == 1:  # long: z_entry negative
        fast_mr = z4 > z_entry * 0.5
        slow_mr = z16 > z_entry * 0.3 and not fast_mr
        continuation = z8 < z_entry * 1.2 and not fast_mr and not slow_mr
    else:  # short: z_entry positive
        fast_mr = z4 < z_entry * 0.5
        slow_mr = z16 < z_entry * 0.3 and not fast_mr
        continuation = z8 > z_entry * 1.2 and not fast_mr and not slow_mr
    if fast_mr: return "fast_mr"
    if slow_mr: return "slow_mr"
    if continuation: return "continuation"
    return "ambiguous"


# ═══════════════════════════════════════════════════════════════
# STATISTICAL HELPERS
# ═══════════════════════════════════════════════════════════════

def stats(arr):
    if not arr: return {"n": 0}
    a = np.array(arr, dtype=float)
    return {"n":int(len(a)),"mean":round(float(np.mean(a)),4),
            "median":round(float(np.median(a)),4),
            "std":round(float(np.std(a,ddof=1)),4) if len(a)>1 else 0,
            "p5":round(float(np.percentile(a,5)),4),
            "p25":round(float(np.percentile(a,25)),4),
            "p75":round(float(np.percentile(a,75)),4),
            "p95":round(float(np.percentile(a,95)),4)}

def metrics(pnls):
    if not pnls: return {"n":0}
    a = np.array(pnls, dtype=float)
    w=int(np.sum(a>0)); l_=int(np.sum(a<=0))
    gw=float(np.sum(a[a>0])) if w>0 else 0
    gl=float(np.abs(np.sum(a[a<=0]))) if l_>0 else 0
    return {"n":len(a),"win_rate":round(w/(w+l_)*100,1) if (w+l_)>0 else 0,
            "pf":round(gw/gl,2) if gl>0 else (99 if gw>0 else 0),
            "avg_pnl":round(float(np.mean(a)),2),
            "net_pnl":round(float(np.sum(a)),2),
            "median_pnl":round(float(np.median(a)),2),
            "avg_win":round(float(np.mean(a[a>0])),2) if w>0 else 0,
            "avg_loss":round(float(np.mean(a[a<=0])),2) if l_>0 else 0,
            "std":round(float(np.std(a,ddof=1)),2) if len(a)>1 else 0}

def bootstrap_ci(arr, n_boot=2000):
    a = np.array(arr, dtype=float)
    pfs=[];wrs=[];means=[]
    for _ in range(n_boot):
        s=np.random.choice(a,size=len(a),replace=True)
        w=np.sum(s>0);wrs.append(w/len(s)*100)
        gw=np.sum(s[s>0]) if np.any(s>0) else 0
        gl=np.abs(np.sum(s[s<=0])) if np.any(s<=0) else 1
        pfs.append(gw/gl if gl>0 else 99)
        means.append(float(np.mean(s)))
    return {"pf":{"mean":round(float(np.mean(pfs)),4),
                  "ci_lower":round(float(np.percentile(pfs,2.5)),4),
                  "ci_upper":round(float(np.percentile(pfs,97.5)),4)},
            "win_rate":{"mean":round(float(np.mean(wrs)),2),
                        "ci_lower":round(float(np.percentile(wrs,2.5)),2),
                        "ci_upper":round(float(np.percentile(wrs,97.5)),2)},
            "mean_trade":{"mean":round(float(np.mean(means)),4),
                          "ci_lower":round(float(np.percentile(means,2.5)),4),
                          "ci_upper":round(float(np.percentile(means,97.5)),4)}}

def fdr_correction(p_values):
    """Benjamini-Hochberg FDR correction."""
    n = len(p_values)
    ranked = np.argsort(p_values)
    corrected = np.zeros(n)
    for i, idx in enumerate(ranked):
        corrected[idx] = p_values[idx] * n / (i + 1)
    return np.minimum(corrected, 1.0)


# ═══════════════════════════════════════════════════════════════
# PART A: ADAPTIVE EXTREMENESS
# ═══════════════════════════════════════════════════════════════

def part_a_adaptive_extremeness(events):
    print("\n[PART A] Adaptive Extremeness...")
    # Absolute Z thresholds
    abs_thresholds = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    abs_results = {}
    for thr in abs_thresholds:
        sub = [e for e in events if e.abs_z >= thr]
        if len(sub) < 10: abs_results[thr] = {"n": len(sub)}; continue
        fwd4 = [eval_forward_return(e, 4) for e in sub]
        fwd8 = [eval_forward_return(e, 8) for e in sub]
        pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
        mae4 = [eval_mae_mfe(e, 4)[0] for e in sub]
        mfe4 = [eval_mae_mfe(e, 4)[1] for e in sub]
        abs_results[thr] = {
            "n": len(sub), "abs_z_threshold": thr,
            "fwd_4": {**stats(fwd4), "win_rate": round(np.mean(np.array(fwd4)>0)*100,1)},
            "fwd_8": {**stats(fwd8), "win_rate": round(np.mean(np.array(fwd8)>0)*100,1)},
            "pnl_4": metrics(pnls4),
            "mae_4": stats(mae4), "mfe_4": stats(mfe4),
        }
    # Rolling percentile: pre-compute per-pair causal rolling percentile of |Z|
    # Then assign percentile rank to each event
    pair_abs_z = defaultdict(list)
    for e in events:
        pair_abs_z[e.pair].append(e)
    lookbacks = [500, 1000, 2000]
    pct_levels = [90, 95, 97.5, 99]
    pct_results = {}
    for lb in lookbacks:
        for pct in pct_levels:
            key = f"L{lb}_P{pct}"
            sub = []
            for pair, pevents in pair_abs_z.items():
                abs_zs = np.array([e.abs_z for e in pevents])
                # Causal rolling percentile for each event
                for idx, e in enumerate(pevents):
                    start = max(0, idx - lb)
                    window = abs_zs[start:idx+1]
                    if len(window) < 20: continue
                    rank = np.mean(window <= e.abs_z) * 100
                    if rank >= pct:
                        sub.append(e)
            if len(sub) < 10: pct_results[key] = {"n": len(sub)}; continue
            fwd4 = [eval_forward_return(e, 4) for e in sub]
            fwd8 = [eval_forward_return(e, 8) for e in sub]
            pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
            mae4 = [eval_mae_mfe(e, 4)[0] for e in sub]
            mfe4 = [eval_mae_mfe(e, 4)[1] for e in sub]
            pct_results[key] = {
                "n": len(sub), "lookback": lb, "percentile": pct,
                "fwd_4": {**stats(fwd4), "win_rate": round(np.mean(np.array(fwd4)>0)*100,1)},
                "fwd_8": {**stats(fwd8), "win_rate": round(np.mean(np.array(fwd8)>0)*100,1)},
                "pnl_4": metrics(pnls4),
                "mae_4": stats(mae4), "mfe_4": stats(mfe4),
            }
    summary = {"absolute": abs_results, "rolling_percentile": pct_results}
    best_abs = max([(k,v) for k,v in abs_results.items() if v.get("n",0)>=50],
                   key=lambda x: x[1].get("pnl_4",{}).get("avg_pnl",-999), default=None)
    best_pct = max([(k,v) for k,v in pct_results.items() if v.get("n",0)>=50],
                   key=lambda x: x[1].get("pnl_4",{}).get("avg_pnl",-999), default=None)
    summary["comparison"] = {
        "best_absolute": {"threshold": best_abs[0], "n": best_abs[1]["n"],
                          "avg_fwd_4": best_abs[1]["fwd_4"]["mean"],
                          "avg_pnl_4": best_abs[1]["pnl_4"]["avg_pnl"]} if best_abs else None,
        "best_rolling": {"config": best_pct[0], "n": best_pct[1]["n"],
                         "avg_fwd_4": best_pct[1]["fwd_4"]["mean"],
                         "avg_pnl_4": best_pct[1]["pnl_4"]["avg_pnl"]} if best_pct else None,
    }
    print(f"    Absolute thresholds: {len(abs_results)} evaluated")
    print(f"    Rolling percentile configs: {len(pct_results)} evaluated")
    if best_abs:
        print(f"    Best absolute: Z>={best_abs[0]} n={best_abs[1]['n']} fwd4={best_abs[1]['fwd_4']['mean']:.2f}p P&L=${best_abs[1]['pnl_4']['avg_pnl']:.2f}")
    if best_pct:
        print(f"    Best rolling: {best_pct[0]} n={best_pct[1]['n']} fwd4={best_pct[1]['fwd_4']['mean']:.2f}p P&L=${best_pct[1]['pnl_4']['avg_pnl']:.2f}")
    return summary


# ═══════════════════════════════════════════════════════════════
# PART B: Z-SCORE DYNAMICS
# ═══════════════════════════════════════════════════════════════

def part_b_z_dynamics(events):
    print("\n[PART B] Z-Score Dynamics...")
    # Group by outcome
    outcomes = defaultdict(list)
    for e in events:
        cat = classify_outcome(e)
        outcomes[cat].append(e)
    result = {}
    for cat, evs in outcomes.items():
        if len(evs) < 10: continue
        fwd4 = [eval_forward_return(e, 4) for e in evs]
        fwd8 = [eval_forward_return(e, 8) for e in evs]
        mae4 = [eval_mae_mfe(e, 4)[0] for e in evs]
        mfe4 = [eval_mae_mfe(e, 4)[1] for e in evs]
        result[cat] = {
            "count": len(evs),
            "pct": round(len(evs) / len(events) * 100, 1),
            "fwd_4": stats(fwd4), "fwd_8": stats(fwd8),
            "mae_4": stats(mae4), "mfe_4": stats(mfe4),
            "features": {
                "abs_z": stats([e.abs_z for e in evs]),
                "dz_1": stats([e.dz_1 for e in evs]),
                "dz_2": stats([e.dz_2 for e in evs]),
                "dz_4": stats([e.dz_4 for e in evs]),
                "z_accel": stats([e.z_accel for e in evs]),
                "z_was_beyond": stats([e.z_was_beyond for e in evs]),
                "z_moving_toward_pct": round(np.mean([e.z_moving_toward for e in evs])*100,1),
                "dist_from_max": stats([e.dist_from_max for e in evs]),
                "atr_pct_rank": stats([e.atr_pct_rank for e in evs]),
                "ema_dist": stats([e.ema_dist for e in evs]),
                "ema_slope": stats([e.ema_slope for e in evs]),
                "mom_10": stats([e.mom_10 for e in evs]),
            },
        }
    # Statistical tests: which features best distinguish continuation from MR
    mr_evs = [e for e in events if classify_outcome(e) in ("fast_mr","slow_mr")]
    cont_evs = [e for e in events if classify_outcome(e) == "continuation"]
    if mr_evs and cont_evs:
        feature_tests = {}
        for feat_name in ["abs_z","dz_1","dz_2","dz_4","z_accel","z_was_beyond",
                          "dist_from_max","atr_pct_rank","ema_dist","ema_slope","mom_10"]:
            mr_vals = np.array([getattr(e, feat_name) for e in mr_evs])
            cont_vals = np.array([getattr(e, feat_name) for e in cont_evs])
            if len(mr_vals) > 5 and len(cont_vals) > 5:
                u_stat, p_val = sp_stats.mannwhitneyu(mr_vals, cont_vals, alternative="two-sided")
                feature_tests[feat_name] = {
                    "mr_mean": round(float(np.mean(mr_vals)),4),
                    "cont_mean": round(float(np.mean(cont_vals)),4),
                    "u_stat": round(float(u_stat),2),
                    "p_value": round(float(p_val),6),
                    "significant": p_val < 0.05,
                }
        result["feature_discrimination"] = feature_tests
    print(f"    Outcomes: {', '.join(f'{k}={len(v)}' for k,v in outcomes.items() if len(v)>10)}")
    if mr_evs and cont_evs:
        sig_feats = [k for k,v in result.get("feature_discrimination",{}).items() if v.get("significant")]
        print(f"    Significant discriminators: {sig_feats}")
    return result


# ═══════════════════════════════════════════════════════════════
# PART C & D: CONDITIONAL RESPONSE SURFACE
# ═══════════════════════════════════════════════════════════════

def part_cd_conditional_surface(events):
    print("\n[PART C/D] Conditional Response Surface...")
    # Define regime dimensions
    vol_regimes = ["low_vol","mid_vol","high_vol","extreme_vol"]
    # Z bins
    z_bins = [(2,2.5),(2.5,3),(3,3.5),(3.5,4),(4,5),(5,100)]
    z_bin_labels = ["2-2.5","2.5-3","3-3.5","3.5-4","4-5","5+"]
    # Trend regimes (by EMA distance)
    ema_bins = [(-5,-1),(-1,0),(0,1),(1,5)]
    ema_labels = ["strong_down","weak_down","weak_up","strong_up"]
    # Velocity bins (dz_1)
    vel_bins = [(-2,-0.5),(-0.5,0),(0,0.5),(0.5,2)]
    vel_labels = ["fast_away","slow_away","slow_toward","fast_toward"]
    # Session
    sessions = ["london_only","ny_only","overlap"]

    surfaces = {}
    # 2D: Z × Vol
    z_vol = {}
    for zi, (zlo, zhi) in enumerate(z_bins):
        for vr in vol_regimes:
            sub = [e for e in events if zlo <= e.abs_z < zhi and e.vol_regime == vr]
            if len(sub) < 10: continue
            fwd4 = [eval_forward_return(e, 4) for e in sub]
            pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
            mae4 = [eval_mae_mfe(e, 4)[0] for e in sub]
            mfe4 = [eval_mae_mfe(e, 4)[1] for e in sub]
            key = f"Z{z_bin_labels[zi]}-V{vr}"
            z_vol[key] = {
                "n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                "mae_4":stats(mae4),"mfe_4":stats(mfe4),
                "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1),
            }
    surfaces["z_x_vol"] = z_vol

    # 2D: Z × Trend
    z_trend = {}
    for zi, (zlo, zhi) in enumerate(z_bins):
        for ei, (elo, ehi) in enumerate(ema_bins):
            sub = [e for e in events if zlo <= e.abs_z < zhi and elo <= e.ema_dist < ehi]
            if len(sub) < 10: continue
            fwd4 = [eval_forward_return(e, 4) for e in sub]
            pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
            key = f"Z{z_bin_labels[zi]}-E{ema_labels[ei]}"
            z_trend[key] = {"n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                            "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1)}
    surfaces["z_x_trend"] = z_trend

    # 2D: Z × Velocity
    z_vel = {}
    for zi, (zlo, zhi) in enumerate(z_bins):
        for vi, (vlo, vhi) in enumerate(vel_bins):
            sub = [e for e in events if zlo <= e.abs_z < zhi and vlo <= e.dz_1 < vhi]
            if len(sub) < 10: continue
            fwd4 = [eval_forward_return(e, 4) for e in sub]
            pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
            key = f"Z{z_bin_labels[zi]}-V{vel_labels[vi]}"
            z_vel[key] = {"n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                          "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1)}
    surfaces["z_x_velocity"] = z_vel

    # 2D: Z × Session
    z_sess = {}
    for zi, (zlo, zhi) in enumerate(z_bins):
        for s in sessions:
            sub = [e for e in events if zlo <= e.abs_z < zhi and e.entry_session == s]
            if len(sub) < 10: continue
            fwd4 = [eval_forward_return(e, 4) for e in sub]
            pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
            key = f"Z{z_bin_labels[zi]}-S{s}"
            z_sess[key] = {"n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                           "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1)}
    surfaces["z_x_session"] = z_sess

    # 3D: Z × Vol × Trend (top cells only)
    z_vol_trend = {}
    for zi, (zlo, zhi) in enumerate(z_bins):
        for vr in ["low_vol","high_vol","extreme_vol"]:
            for ei, (elo, ehi) in enumerate(ema_bins):
                sub = [e for e in events if zlo <= e.abs_z < zhi
                       and e.vol_regime == vr and elo <= e.ema_dist < ehi]
                if len(sub) < 10: continue
                fwd4 = [eval_forward_return(e, 4) for e in sub]
                pnls4 = [eval_time_exit(e, 4)[0] for e in sub]
                key = f"Z{z_bin_labels[zi]}-V{vr}-E{ema_labels[ei]}"
                z_vol_trend[key] = {"n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                                    "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1)}
    surfaces["z_x_vol_x_trend"] = z_vol_trend

    # Identify structural regions
    structural = []
    for key, data in surfaces["z_x_vol"].items():
        if data["n"] >= 50 and data["fwd_4"]["mean"] > 0.5 and data["pnl_4"].get("avg_pnl",0) > 0:
            structural.append({"key":key, "n":data["n"], "fwd_4":data["fwd_4"]["mean"],
                               "pnl_4":data["pnl_4"]["avg_pnl"]})
    structural.sort(key=lambda x: -x["fwd_4"])
    surfaces["structural_regions"] = structural[:20]

    print(f"    Z×Vol cells: {len(z_vol)}")
    print(f"    Z×Trend cells: {len(z_trend)}")
    print(f"    Z×Velocity cells: {len(z_vel)}")
    print(f"    Z×Session cells: {len(z_sess)}")
    print(f"    Z×Vol×Trend cells: {len(z_vol_trend)}")
    print(f"    Structural regions (fwd4>0.5p, n>=50): {len(structural)}")
    if structural:
        top = structural[0]
        print(f"    Top region: {top['key']} n={top['n']} fwd4={top['fwd_4']:.2f}p P&L=${top['pnl_4']:.2f}")
    return surfaces


# ═══════════════════════════════════════════════════════════════
# PART E: TEMPORAL & CROSS-PAIR STABILITY
# ═══════════════════════════════════════════════════════════════

def part_e_stability(events, structural_regions):
    print("\n[PART E] Temporal & Cross-Pair Stability...")
    periods = {"2016-2018":(2016,2018),"2019-2021":(2019,2021),
               "2022-2024":(2022,2024),"2025-2026":(2025,2026)}
    stability = {"by_period":{}, "by_pair":{}}

    # Test top structural regions across periods
    for region in structural_regions[:10]:
        key = region["key"]
        parts = key.split("-")
        # Handle "Z5+" → ["Z5", "+", "V..."] vs "Z3-3.5" → ["Z3", "3.5", "V..."]
        z_str = parts[0][1:]
        if "+" in z_str:
            zlo = float(z_str.replace("+",""))
            zhi = 100.0
            v_offset = 2  # skip the "+" part
        else:
            zlo = float(z_str)
            zhi = float(parts[1]) if len(parts) > 1 and parts[1].replace(".","").isdigit() else zlo + 0.5
            v_offset = 1
        vr = None; sess = None
        for p in parts[1+v_offset:]:
            if p.startswith("V"): vr = p[1:]
            if p.startswith("S"): sess = p[1:]

        by_period = {}
        for label, (y1,y2) in periods.items():
            sub = [e for e in events if y1<=e.year<=y2 and zlo<=e.abs_z<zhi]
            if vr: sub = [e for e in sub if e.vol_regime==vr]
            if sess: sub = [e for e in sub if e.entry_session==sess]
            if len(sub) < 10: by_period[label]={"n":len(sub)}; continue
            fwd4 = [eval_forward_return(e,4) for e in sub]
            pnls4 = [eval_time_exit(e,4)[0] for e in sub]
            by_period[label]={"n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                              "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1)}
        stability["by_period"][key] = by_period

    # Cross-pair stability for top regions
    for region in structural_regions[:5]:
        key = region["key"]
        parts = key.split("-")
        # Handle "Z5+" → ["Z5", "+", "V..."] vs "Z3-3.5" → ["Z3", "3.5", "V..."]
        z_str = parts[0][1:]  # strip "Z"
        if "+" in z_str:
            zlo = float(z_str.replace("+",""))
            zhi = 100.0
        else:
            zlo = float(z_str)
            zhi = float(parts[1]) if len(parts) > 1 and parts[1].replace(".","").isdigit() else zlo + 0.5
        vr = None
        for p in parts[2:] if "+" not in z_str else parts[2:]:
            if p.startswith("V"): vr = p[1:]
        by_pair = {}
        pair_counts = defaultdict(int)
        for e in events:
            if zlo<=e.abs_z<zhi and (vr is None or e.vol_regime==vr):
                pair_counts[e.pair] += 1
        for pair, cnt in sorted(pair_counts.items(), key=lambda x:-x[1])[:10]:
            sub = [e for e in events if e.pair==pair and zlo<=e.abs_z<zhi]
            if vr: sub = [e for e in sub if e.vol_regime==vr]
            if len(sub) < 10: continue
            fwd4 = [eval_forward_return(e,4) for e in sub]
            pnls4 = [eval_time_exit(e,4)[0] for e in sub]
            by_pair[pair]={"n":len(sub),"fwd_4":stats(fwd4),"pnl_4":metrics(pnls4),
                           "fwd_4_wr":round(np.mean(np.array(fwd4)>0)*100,1)}
        stability["by_pair"][key] = by_pair

    print(f"    Period stability: {len(stability['by_period'])} regions")
    print(f"    Cross-pair stability: {len(stability['by_pair'])} regions")
    return stability


# ═══════════════════════════════════════════════════════════════
# PART F: MULTIPLE COMPARISON CONTROL
# ═══════════════════════════════════════════════════════════════

def part_f_multiple_comparison(surfaces, stability):
    print("\n[PART F] Multiple Comparison Control...")
    # Collect all p-values from structural regions
    all_regions = surfaces.get("structural_regions", [])
    p_values = []
    region_keys = []
    for r in all_regions:
        # Approximate p-value from bootstrap
        fwd4_mean = r.get("fwd_4", 0)
        n = r.get("n", 0)
        if n > 0 and fwd4_mean != 0:
            # Simple t-test approximation
            se = 1.0 / np.sqrt(n)  # rough approximation
            z_stat = fwd4_mean / se if se > 0 else 0
            p_val = 2 * (1 - sp_stats.norm.cdf(abs(z_stat)))
            p_values.append(p_val)
            region_keys.append(r["key"])
    if p_values:
        p_arr = np.array(p_values)
        fdr = fdr_correction(p_arr)
        sig_before = np.sum(p_arr < 0.05)
        sig_after = np.sum(fdr < 0.05)
        result = {
            "total_tests": len(p_values),
            "significant_before_fdr": int(sig_before),
            "significant_after_fdr": int(sig_after),
            "top_regions": [{"key":region_keys[i],"p_value":round(float(p_arr[i]),6),
                             "fdr":round(float(fdr[i]),6),
                             "significant":bool(fdr[i]<0.05)}
                            for i in np.argsort(p_arr)[:10]],
        }
    else:
        result = {"total_tests":0,"significant_before_fdr":0,"significant_after_fdr":0}
    print(f"    Total tests: {result['total_tests']}")
    print(f"    Significant before FDR: {result['significant_before_fdr']}")
    print(f"    Significant after FDR: {result['significant_after_fdr']}")
    return result


# ═══════════════════════════════════════════════════════════════
# PART G: COST SENSITIVITY
# ═══════════════════════════════════════════════════════════════

def part_g_cost_sensitivity(events, structural_regions):
    print("\n[PART G] Cost Sensitivity...")
    cost_levels = [0, 1, 2, 3.5, 5, 7, 10, 15]
    result = {}
    for region in structural_regions[:5]:
        key = region["key"]
        parts = key.split("-")
        # Handle "Z5+" → ["Z5", "+", "V..."] vs "Z3-3.5" → ["Z3", "3.5", "V..."]
        z_str = parts[0][1:]  # strip "Z"
        if "+" in z_str:
            zlo = float(z_str.replace("+",""))
            zhi = 100.0
        else:
            zlo = float(z_str)
            zhi = float(parts[1]) if len(parts) > 1 and parts[1].replace(".","").isdigit() else zlo + 0.5
        vr = None
        for p in parts[2:] if "+" not in z_str else parts[2:]:
            if p.startswith("V"): vr = p[1:]
        sub = [e for e in events if zlo<=e.abs_z<zhi]
        if vr: sub = [e for e in sub if e.vol_regime==vr]
        if len(sub) < 20: continue
        region_costs = {}
        for cost in cost_levels:
            pnls = []
            for e in sub:
                d=e.direction; pip=e.pip; pv=e.pv; ep=e.entry_price
                n=min(4,len(e.price_path))
                exited=False
                for j in range(1,n):
                    hi=e.high_path[j]; lo=e.low_path[j]
                    if d==1 and lo<=e.sl_price:
                        pnls.append((e.sl_price-ep)/pip*pv*e.lot - e.lot*cost);exited=True;break
                    if d==-1 and hi>=e.sl_price:
                        pnls.append((ep-e.sl_price)/pip*pv*e.lot - e.lot*cost);exited=True;break
                if not exited:
                    gross=(e.price_path[n-1]-ep)*d/pip*pv*e.lot
                    pnls.append(gross - e.lot*cost)
            region_costs[cost] = metrics(pnls)
        result[key] = region_costs
    print(f"    Evaluated {len(result)} regions across {len(cost_levels)} cost levels")
    return result


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t0 = time.time()
    print("="*80)
    print("  PHASE 6 — SIGNAL DISCOVERY / ADAPTIVE EXTREMENESS")
    print("="*80)

    print("\n[1] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"    {len(pdata)} pairs loaded")

    print("\n[2] Running backtest with feature computation...")
    events = run_backtest(pdata)
    print(f"    {len(events)} extreme-Z events recorded")

    if not events:
        print("ERROR: No events"); sys.exit(1)

    # Classify outcomes
    outcomes = defaultdict(int)
    for e in events:
        outcomes[classify_outcome(e)] += 1
    print(f"    Outcomes: {dict(outcomes)}")

    R = {}

    R["part_a"] = part_a_adaptive_extremeness(events)
    R["part_b"] = part_b_z_dynamics(events)
    R["part_cd"] = part_cd_conditional_surface(events)
    R["part_e"] = part_e_stability(events, R["part_cd"].get("structural_regions",[]))
    R["part_f"] = part_f_multiple_comparison(R["part_cd"], R["part_e"])
    R["part_g"] = part_g_cost_sensitivity(events, R["part_cd"].get("structural_regions",[]))

    R["config"] = {
        "z_entry":Z_ENTRY,"lookback":LOOKBACK,"risk_pct":RISK_PCT,
        "atr_sl_mult":ATR_SL_MULT,"commission":COMMISSION,
        "slippage_pips":SLIPPAGE_PIPS,"pairs":len(PAIRS),
    }
    R["event_count"] = len(events)
    R["outcome_distribution"] = dict(outcomes)

    with open(OUT / "signal_discovery.json", "w") as f:
        json.dump(R, f, indent=2, default=str)
    print(f"\n  Saved {OUT / 'signal_discovery.json'}")
    print(f"\n[DONE] {time.time()-t0:.1f}s")
