"""Phase 5 — Exit Response Surface.

Single backtest with full path recording. All exit configurations
are evaluated offline from recorded paths (O(1) backtests).

Usage:
    cd /root/nestquant && .venv/bin/python -u scripts/exit_surface.py
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
# FROZEN PARAMETERS (entry logic — DO NOT CHANGE)
# ═══════════════════════════════════════════════════════════════
Z_ENTRY = 2.2
LOOKBACK = 20
RISK_PCT = 0.006
ACC = 2500
LEV = 100
COMMISSION = 3.50
SESSIONS = {"london": (7, 16), "new_york": (12, 21)}
SKIP_FRI = 20; SKIP_MON = 3
ATR_PERIOD = 14
ATR_SL_MULT = 3.0
MAX_CONC = 10
MAX_HOLD_BARS = 200  # large — we evaluate exits offline
SLIPPAGE_PIPS = 0.3

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "NZD/USD",
    "EUR/GBP", "EUR/CHF", "EUR/JPY", "AUD/JPY", "EUR/AUD", "AUD/CAD",
    "GBP/JPY", "GBP/CAD", "GBP/AUD", "CAD/JPY", "NZD/JPY", "NZD/CHF",
    "AUD/CHF", "CAD/CHF",
]
SPREAD = {
    "EUR/USD": 0.8, "GBP/USD": 1.0, "USD/JPY": 1.0, "USD/CHF": 1.2,
    "AUD/USD": 0.9, "NZD/USD": 1.2, "EUR/GBP": 1.2, "EUR/CHF": 1.5,
    "EUR/JPY": 2.0, "GBP/JPY": 3.0, "AUD/JPY": 2.0, "CAD/JPY": 2.5,
    "NZD/JPY": 3.0, "EUR/AUD": 2.0, "EUR/CAD": 2.5, "GBP/AUD": 3.5,
    "GBP/CAD": 3.5, "AUD/CAD": 2.0, "AUD/CHF": 2.5, "NZD/CHF": 3.0,
    "CAD/CHF": 3.0,
}
DEFAULT_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.26, "JPY": 0.0067,
               "CHF": 0.88, "AUD": 0.65, "CAD": 0.74, "NZD": 0.60}

OUT = Path("/root/nestquant/research_data/phase5")
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

def pip_size(pair):
    return 0.01 if "JPY" in pair else 0.0001

def pip_value(pair):
    base, quote = pair.split("/")
    return pip_size(pair) * 100000 * DEFAULT_USD.get(quote, 1.0)

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
        except Exception:
            continue
        df = raw.get(pair)
        if df is None or df.empty: continue
        idx = pd.to_datetime(df.index)
        idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        df.index = idx
        df = df[(df.index >= start) & (df.index <= end)]
        if len(df) < 500: continue
        df = df[["open", "high", "low", "close"]].resample("30min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["close"])
        if len(df) < 500: continue
        c = df["close"].values.astype(np.float64)
        obs = compute_zscore_causal(c, df.index, pair, lookback=LOOKBACK)
        z = np.array([o.z_score for o in obs])
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean().values
        atr_pct = (atr / df["close"].values * 100)
        pdata[pair] = {
            "c": df["close"].values, "h": df["high"].values,
            "lo": df["low"].values, "o": df["open"].values,
            "ts": df.index, "n": len(df),
            "z": z, "atr": atr, "atr_pct": atr_pct,
            "pip": pip_size(pair), "pv": pip_value(pair),
            "spread": SPREAD.get(pair, 2.0),
        }
    return pdata


# ═══════════════════════════════════════════════════════════════
# BACKTEST — RECORDS FULL PATHS, NO EXITS APPLIED
# ═══════════════════════════════════════════════════════════════

@dataclass
class RawTrade:
    pair: str; direction: int; entry_price: float; entry_ts: object
    entry_z: float; entry_bar: int; sl_price: float; tp_price: float
    lot: float; pip: float; pv: float; spread_pips: float
    atr_at_entry: float; risk_dollars: float
    vol_regime: str; entry_session: str; entry_hour: int; entry_dow: int
    year: int; month: str; day: int
    # Paths recorded bar-by-bar (relative to entry)
    price_path: list = field(default_factory=list)
    z_path: list = field(default_factory=list)
    atr_path: list = field(default_factory=list)
    high_path: list = field(default_factory=list)
    low_path: list = field(default_factory=list)
    ts_path: list = field(default_factory=list)


def run_raw_backtest(pdata):
    """Single pass: record every trade's full path. No exit logic."""
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]["n"])
    ref = pdata[ref_pair]; n = ref["n"]
    bal = ACC; peak = ACC; open_pos = []; trades = []
    daily_sb = ACC; daily_d = None

    for i in range(LOOKBACK + ATR_PERIOD + 10, n - 1):
        ts = ref["ts"][i]; today = ts.date()
        if daily_d != today: daily_d = today; daily_sb = bal
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos["pair"])
                if pd_ is None or i >= pd_["n"]: continue
                _close_trade(pos, pd_, i, ts, "DL", trades, bal)
            open_pos.clear(); continue

        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos["pair"])
            if pd_ is None or i >= pd_["n"]: remaining.append(pos); continue
            # Record path bar
            pos["price_path"].append(float(pd_["c"][i]))
            pos["z_path"].append(float(pd_["z"][i]) if not np.isnan(pd_["z"][i]) else 0.0)
            pos["atr_path"].append(float(pd_["atr"][i]) if not np.isnan(pd_["atr"][i]) else 0.0)
            pos["high_path"].append(float(pd_["h"][i]))
            pos["low_path"].append(float(pd_["lo"][i]))
            pos["ts_path"].append(str(ts))
            # Hard exit at 200 bars (data limit)
            if i - pos["bar"] >= MAX_HOLD_BARS:
                _close_trade(pos, pd_, i, ts, "MAX", trades, bal)
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
            risk_d = bal * RISK_PCT
            lot = risk_d / (sl_pips * pd_["pv"])
            lot = max(0.01, round(lot, 2)); lot = min(lot, 10.0)
            tp_dist = sl_dist * 2.0
            tp_p = ep + tp_dist if direction == 1 else ep - tp_dist
            vr = classify_vol(pd_["atr_pct"], i)
            open_pos.append({
                "pair": pair, "direction": direction, "entry_price": ep,
                "entry_ts": ts, "entry_z": z_now, "bar": i,
                "sl_price": sl_p, "tp_price": tp_p, "lot": lot,
                "pip": pd_["pip"], "pv": pd_["pv"], "spread_pips": pd_["spread"],
                "atr_at_entry": atr_now, "risk_dollars": risk_d,
                "vol_regime": vr, "entry_session": get_session(ts),
                "entry_hour": ts.hour, "entry_dow": ts.dayofweek,
                "year": ts.year, "month": ts.strftime("%Y-%m"), "day": str(ts.date()),
                "price_path": [float(pd_["c"][i])],
                "z_path": [float(z_now) if not np.isnan(z_now) else 0.0],
                "atr_path": [float(atr_now) if not np.isnan(atr_now) else 0.0],
                "high_path": [float(pd_["h"][i])],
                "low_path": [float(pd_["lo"][i])],
                "ts_path": [str(ts)],
            })
    # Close remaining
    for pos in open_pos:
        pd_ = pdata.get(pos["pair"])
        if pd_ is None: continue
        _close_trade(pos, pd_, n - 1, ref["ts"][n - 1], "END", trades, bal)
    return trades


def _close_trade(pos, pd_, bar_i, ts, reason, trades, bal):
    """Convert raw position to RawTrade with path data."""
    tr = pos["direction"]; pip = pos["pip"]
    ep = pos["entry_price"]
    # Use close price as exit (approximation for path recording)
    exit_p = pd_["c"][min(bar_i, pd_["n"] - 1)]
    sl_dist_pips = abs(ep - pos["sl_price"]) / pip if pip > 0 else 1

    t = RawTrade(
        pair=pos["pair"], direction=tr, entry_price=ep,
        entry_ts=pos["entry_ts"], entry_z=pos["entry_z"], entry_bar=pos["bar"],
        sl_price=pos["sl_price"], tp_price=pos["tp_price"],
        lot=pos["lot"], pip=pip, pv=pos["pv"], spread_pips=pos["spread_pips"],
        atr_at_entry=pos["atr_at_entry"], risk_dollars=pos["risk_dollars"],
        vol_regime=pos["vol_regime"], entry_session=pos["entry_session"],
        entry_hour=pos["entry_hour"], entry_dow=pos["entry_dow"],
        year=pos["year"], month=pos["month"], day=pos["day"],
        price_path=pos["price_path"], z_path=pos["z_path"],
        atr_path=pos["atr_path"], high_path=pos["high_path"],
        low_path=pos["low_path"], ts_path=pos["ts_path"],
    )
    trades.append(t)


# ═══════════════════════════════════════════════════════════════
# OFFLINE EXIT EVALUATION ENGINE
# ═══════════════════════════════════════════════════════════════

def eval_time_exit(t: RawTrade, max_bars: int):
    """Evaluate fixed-time exit. Returns (pnl, exit_bar, exit_reason)."""
    d = t.direction; pip = t.pip; pv = t.pv; ep = t.entry_price
    sl_dist = abs(ep - t.sl_price)
    sl_pips = sl_dist / pip if pip > 0 else 1
    n = min(max_bars, len(t.price_path))
    if n == 0: return 0, 0, "NONE"
    # Check each bar for SL/TP hit before time exit
    for j in range(1, n):
        hi = t.high_path[j]; lo = t.low_path[j]
        if d == 1 and lo <= t.sl_price:
            gross = (t.sl_price - ep) / pip * pv * t.lot
            return gross - t.lot * COMMISSION, j, "SL"
        if d == -1 and hi >= t.sl_price:
            gross = (ep - t.sl_price) / pip * pv * t.lot
            return gross - t.lot * COMMISSION, j, "SL"
        if d == 1 and hi >= t.tp_price:
            gross = (t.tp_price - ep) / pip * pv * t.lot
            return gross - t.lot * COMMISSION, j, "TP"
        if d == -1 and lo <= t.tp_price:
            gross = (ep - t.tp_price) / pip * pv * t.lot
            return gross - t.lot * COMMISSION, j, "TP"
    # Time exit at close
    exit_p = t.price_path[n - 1]
    gross = (exit_p - ep) * d / pip * pv * t.lot
    return gross - t.lot * COMMISSION, n, "TE"


def eval_z_exit(t: RawTrade, z_threshold: float):
    """Evaluate Z-score exit. Returns (pnl, exit_bar, exit_reason)."""
    d = t.direction; pip = t.pip; pv = t.pv; ep = t.entry_price
    n = len(t.z_path)
    for j in range(1, n):
        zv = t.z_path[j]
        hi = t.high_path[j]; lo = t.low_path[j]
        # Check SL/TP first
        if d == 1 and lo <= t.sl_price:
            return (t.sl_price - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "SL"
        if d == -1 and hi >= t.sl_price:
            return (ep - t.sl_price) / pip * pv * t.lot - t.lot * COMMISSION, j, "SL"
        if d == 1 and hi >= t.tp_price:
            return (t.tp_price - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "TP"
        if d == -1 and lo <= t.tp_price:
            return (ep - t.tp_price) / pip * pv * t.lot - t.lot * COMMISSION, j, "TP"
        # Z exit
        if d == 1 and zv > -z_threshold:
            exit_p = t.price_path[j]
            return (exit_p - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "ZE"
        if d == -1 and zv < z_threshold:
            exit_p = t.price_path[j]
            return (exit_p - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "ZE"
    exit_p = t.price_path[-1]
    return (exit_p - ep) * d / pip * pv * t.lot - t.lot * COMMISSION, n, "MAX"


def eval_sl_exit(t: RawTrade, atr_mult: float):
    """Evaluate stop-loss at given ATR multiple. Returns (pnl, exit_bar, exit_reason)."""
    d = t.direction; pip = t.pip; pv = t.pv; ep = t.entry_price
    if t.atr_at_entry <= 0: return 0, 0, "NONE"
    sl_dist = t.atr_at_entry * atr_mult
    sl_p = ep - sl_dist if d == 1 else ep + sl_dist
    n = len(t.price_path)
    for j in range(1, n):
        hi = t.high_path[j]; lo = t.low_path[j]
        if d == 1 and lo <= sl_p:
            return (sl_p - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "SL"
        if d == -1 and hi >= sl_p:
            return (ep - sl_p) / pip * pv * t.lot - t.lot * COMMISSION, j, "SL"
    exit_p = t.price_path[-1]
    return (exit_p - ep) * d / pip * pv * t.lot - t.lot * COMMISSION, n, "MAX"


def eval_combo_exit(t: RawTrade, max_bars: int, z_threshold: float, atr_mult: float,
                    session_close: bool = True, entry_ts=None):
    """Evaluate combined exit: time + Z + SL + session close."""
    d = t.direction; pip = t.pip; pv = t.pv; ep = t.entry_price
    if t.atr_at_entry <= 0: return 0, 0, "NONE"
    sl_dist = t.atr_at_entry * atr_mult
    sl_p = ep - sl_dist if d == 1 else ep + sl_dist
    n = len(t.price_path)
    for j in range(1, n):
        zv = t.z_path[j]
        hi = t.high_path[j]; lo = t.low_path[j]
        # SL
        if d == 1 and lo <= sl_p:
            return (sl_p - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "SL"
        if d == -1 and hi >= sl_p:
            return (ep - sl_p) / pip * pv * t.lot - t.lot * COMMISSION, j, "SL"
        # Z exit
        if d == 1 and zv > -z_threshold:
            return (t.price_path[j] - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "ZE"
        if d == -1 and zv < z_threshold:
            return (t.price_path[j] - ep) / pip * pv * t.lot - t.lot * COMMISSION, j, "ZE"
        # Time exit
        if j >= max_bars:
            return (t.price_path[j] - ep) * d / pip * pv * t.lot - t.lot * COMMISSION, j, "TE"
    exit_p = t.price_path[-1]
    return (exit_p - ep) * d / pip * pv * t.lot - t.lot * COMMISSION, n, "MAX"


def compute_mae_mfe(t: RawTrade, max_bars: int = None):
    """Compute MAE/MFE in pips and ATR units over trade life."""
    d = t.direction; pip = t.pip; ep = t.entry_price
    atr0 = t.atr_at_entry if t.atr_at_entry > 0 else 1.0
    n = min(max_bars, len(t.price_path)) if max_bars else len(t.price_path)
    mae_p = 0.0; mfe_p = 0.0; bar_mae = 0; bar_mfe = 0
    z_entry = t.entry_z; max_z = z_entry; min_z = z_entry
    for j in range(1, n):
        if d == 1:
            cur_mae = (ep - t.low_path[j]) / pip
            cur_mfe = (t.high_path[j] - ep) / pip
        else:
            cur_mae = (t.high_path[j] - ep) / pip
            cur_mfe = (ep - t.low_path[j]) / pip
        if cur_mae > mae_p: mae_p = cur_mae; bar_mae = j
        if cur_mfe > mfe_p: mfe_p = cur_mfe; bar_mfe = j
        zv = t.z_path[j]
        if zv > max_z: max_z = zv
        if zv < min_z: min_z = zv
    sl_dist_pips = abs(ep - t.sl_price) / pip if pip > 0 else 1
    return {
        "mae_pips": mae_p, "mfe_pips": mfe_p,
        "mae_atr": mae_p * pip / atr0, "mfe_atr": mfe_p * pip / atr0,
        "mae_r": mae_p / sl_dist_pips if sl_dist_pips > 0 else 0,
        "mfe_r": mfe_p / sl_dist_pips if sl_dist_pips > 0 else 0,
        "bar_to_mae": bar_mae, "bar_to_mfe": bar_mfe,
        "max_z": max_z, "min_z": min_z,
    }


def classify_mr_cont(t: RawTrade):
    """Classify trade as mean-reverting or continuation."""
    if t.direction == 1:
        return "mr" if t.z_path[-1] > t.entry_z else "cont"
    else:
        return "mr" if t.z_path[-1] < t.entry_z else "cont"


def is_winner_at(t: RawTrade, bar: int):
    """Check if trade is winning at given bar."""
    if bar >= len(t.price_path): return False
    d = t.direction; ep = t.entry_price; pip = t.pip; pv = t.pv
    gross = (t.price_path[bar] - ep) * d / pip * pv * t.lot
    return gross > t.lot * COMMISSION


# ═══════════════════════════════════════════════════════════════
# STATISTICAL HELPERS
# ═══════════════════════════════════════════════════════════════

def stats(arr):
    if not arr: return {"n": 0}
    a = np.array(arr, dtype=float)
    return {
        "n": int(len(a)), "mean": round(float(np.mean(a)), 4),
        "median": round(float(np.median(a)), 4),
        "std": round(float(np.std(a, ddof=1)), 4) if len(a) > 1 else 0,
        "p5": round(float(np.percentile(a, 5)), 4),
        "p25": round(float(np.percentile(a, 25)), 4),
        "p75": round(float(np.percentile(a, 75)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
    }


def metrics(pnls):
    if not pnls: return {"n": 0}
    a = np.array(pnls, dtype=float)
    w = int(np.sum(a > 0)); l_ = int(np.sum(a <= 0))
    gw = float(np.sum(a[a > 0])) if w > 0 else 0
    gl = float(np.abs(np.sum(a[a <= 0]))) if l_ > 0 else 0
    return {
        "n": len(a), "win_rate": round(w / (w + l_) * 100, 1) if (w + l_) > 0 else 0,
        "pf": round(gw / gl, 2) if gl > 0 else (99 if gw > 0 else 0),
        "avg_pnl": round(float(np.mean(a)), 2),
        "net_pnl": round(float(np.sum(a)), 2),
        "median_pnl": round(float(np.median(a)), 2),
        "avg_win": round(float(np.mean(a[a > 0])), 2) if w > 0 else 0,
        "avg_loss": round(float(np.mean(a[a <= 0])), 2) if l_ > 0 else 0,
        "std": round(float(np.std(a, ddof=1)), 2) if len(a) > 1 else 0,
        "sharpe": round(float(np.mean(a) / np.std(a, ddof=1) * np.sqrt(252)), 2) if len(a) > 1 and np.std(a) > 0 else 0,
    }


def bootstrap_ci(arr, n_boot=2000):
    a = np.array(arr, dtype=float)
    pfs = []; wrs = []; means = []
    for _ in range(n_boot):
        s = np.random.choice(a, size=len(a), replace=True)
        w = np.sum(s > 0); wrs.append(w / len(s) * 100)
        gw = np.sum(s[s > 0]) if np.any(s > 0) else 0
        gl = np.abs(np.sum(s[s <= 0])) if np.any(s <= 0) else 1
        pfs.append(gw / gl if gl > 0 else 99)
        means.append(float(np.mean(s)))
    return {
        "pf": {"mean": round(float(np.mean(pfs)), 4),
               "ci_lower": round(float(np.percentile(pfs, 2.5)), 4),
               "ci_upper": round(float(np.percentile(pfs, 97.5)), 4)},
        "win_rate": {"mean": round(float(np.mean(wrs)), 2),
                     "ci_lower": round(float(np.percentile(wrs, 2.5)), 2),
                     "ci_upper": round(float(np.percentile(wrs, 97.5)), 2)},
        "mean_trade": {"mean": round(float(np.mean(means)), 4),
                       "ci_lower": round(float(np.percentile(means, 2.5)), 4),
                       "ci_upper": round(float(np.percentile(means, 97.5)), 4)},
    }


def slippage_sensitivity(trades, exit_fn, base_slip, slip_range):
    """Test exit strategy under different slippage assumptions."""
    results = {}
    for slip in slip_range:
        pnls = []
        for t in trades:
            pnl, bar, reason = exit_fn(t)
            # Adjust for different slippage
            slip_adj = (slip - base_slip) * t.pip * 100000 * DEFAULT_USD.get(t.pair.split("/")[0], 1.0) * t.lot * 0.0001
            pnls.append(pnl - slip_adj)
        results[slip] = metrics(pnls)
    return results


# ═══════════════════════════════════════════════════════════════
# 1. TIME-EXIT RESPONSE SURFACE
# ═══════════════════════════════════════════════════════════════

def time_exit_surface(trades, horizons):
    """Evaluate fixed-time exits across a grid of horizons."""
    result = {}
    for h in horizons:
        pnls = []; bars = []; reasons = defaultdict(int)
        for t in trades:
            pnl, bar, reason = eval_time_exit(t, h)
            pnls.append(pnl); bars.append(bar); reasons[reason] += 1
        m = metrics(pnls)
        m["avg_bars"] = round(float(np.mean(bars)), 1)
        m["reasons"] = dict(reasons)
        m["horizon_bars"] = h
        m["horizon_hours"] = round(h * 0.5, 1)
        result[h] = m
    return result


# ═══════════════════════════════════════════════════════════════
# 2. MAE/MFE SURFACE
# ═══════════════════════════════════════════════════════════════

def mae_mfe_surface(trades):
    """Compute MAE/MFE distributions by category and ATR thresholds."""
    winners = []; losers = []; mr_list = []; cont = []
    for t in trades:
        mm = compute_mae_mfe(t)
        cat = classify_mr_cont(t)
        # Determine if eventual winner (using 4-bar time exit as reference)
        pnl4, _, _ = eval_time_exit(t, 4)
        is_win = pnl4 > 0
        rec = {**mm, "pair": t.pair, "vol_regime": t.vol_regime,
               "entry_session": t.entry_session, "category": cat,
               "is_winner_4bar": is_win, "entry_z": t.entry_z,
               "atr_at_entry": t.atr_at_entry, "year": t.year}
        if is_win: winners.append(rec)
        else: losers.append(rec)
        if cat == "mr": mr_list.append(rec)
        else: cont.append(rec)

    atr_thresholds = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    exceedance = {}
    for thr in atr_thresholds:
        w_exceed = sum(1 for r in winners if r["mae_atr"] > thr)
        l_exceed = sum(1 for r in losers if r["mae_atr"] > thr)
        exceedance[f"atr_{thr}"] = {
            "winners_exceed": round(w_exceed / len(winners) * 100, 1) if winners else 0,
            "losers_exceed": round(l_exceed / len(losers) * 100, 1) if losers else 0,
        }

    # Time-to-MFE for winners
    ttmfe_win = [r["bar_to_mfe"] for r in winners if r["bar_to_mfe"] > 0]
    ttmfe_lose = [r["bar_to_mfe"] for r in losers if r["bar_to_mfe"] > 0]

    return {
        "winners": {
            "count": len(winners),
            "mae_pips": stats([r["mae_pips"] for r in winners]),
            "mfe_pips": stats([r["mfe_pips"] for r in winners]),
            "mae_atr": stats([r["mae_atr"] for r in winners]),
            "mfe_atr": stats([r["mfe_atr"] for r in winners]),
            "mae_r": stats([r["mae_r"] for r in winners]),
            "mfe_r": stats([r["mfe_r"] for r in winners]),
            "bar_to_mfe": stats(ttmfe_win),
        },
        "losers": {
            "count": len(losers),
            "mae_pips": stats([r["mae_pips"] for r in losers]),
            "mfe_pips": stats([r["mfe_pips"] for r in losers]),
            "mae_atr": stats([r["mae_atr"] for r in losers]),
            "mfe_atr": stats([r["mfe_atr"] for r in losers]),
            "mae_r": stats([r["mae_r"] for r in losers]),
            "mfe_r": stats([r["mfe_r"] for r in losers]),
            "bar_to_mfe": stats(ttmfe_lose),
        },
        "mr Trades": {
            "count": len(mr_list),
            "mae_pips": stats([r["mae_pips"] for r in mr_list]),
            "mfe_pips": stats([r["mfe_pips"] for r in mr_list]),
            "mae_atr": stats([r["mae_atr"] for r in mr_list]),
            "mfe_atr": stats([r["mfe_atr"] for r in mr_list]),
        },
        "continuation": {
            "count": len(cont),
            "mae_pips": stats([r["mae_pips"] for r in cont]),
            "mfe_pips": stats([r["mfe_pips"] for r in cont]),
            "mae_atr": stats([r["mae_atr"] for r in cont]),
            "mfe_atr": stats([r["mfe_atr"] for r in cont]),
        },
        "atr_exceedance": exceedance,
    }


# ═══════════════════════════════════════════════════════════════
# 3. EXIT-TIMING / INFORMATION DECAY
# ═══════════════════════════════════════════════════════════════

def information_decay(trades, horizons):
    """For each horizon: MR captured, continuation identified, remaining MFE/MAE."""
    result = {}
    for h in horizons:
        mr_captured = 0; cont_identified = 0
        remaining_mfe = []; remaining_mae = []
        future_recovery = 0; future_cont = 0
        total_mr = sum(1 for t in trades if classify_mr_cont(t) == "mr")
        total_cont = sum(1 for t in trades if classify_mr_cont(t) != "mr")
        for t in trades:
            cat = classify_mr_cont(t)
            n = len(t.z_path)
            if h >= n: continue
            z_at_h = t.z_path[h]
            d = t.direction
            # MR captured: Z has moved back toward entry by horizon
            if cat == "mr":
                if d == 1 and z_at_h > t.entry_z * 0.5:
                    mr_captured += 1
                elif d == -1 and z_at_h < t.entry_z * 0.5:
                    mr_captured += 1
            # Continuation identified: Z has moved further away
            if cat != "mr":
                if d == 1 and z_at_h < t.entry_z * 1.2:
                    cont_identified += 1
                elif d == -1 and z_at_h > t.entry_z * 1.2:
                    cont_identified += 1
            # Remaining MFE/MAE after horizon
            mm = compute_mae_mfe(t, max_bars=min(h + 20, n))
            remaining_mfe.append(mm["mfe_pips"])
            remaining_mae.append(mm["mae_pips"])
        result[h] = {
            "mr_captured_pct": round(mr_captured / total_mr * 100, 1) if total_mr > 0 else 0,
            "cont_identified_pct": round(cont_identified / total_cont * 100, 1) if total_cont > 0 else 0,
            "remaining_mfe_pips": stats(remaining_mfe),
            "remaining_mae_pips": stats(remaining_mae),
        }
    return result


# ═══════════════════════════════════════════════════════════════
# 4. Z-EXIT SURFACE
# ═══════════════════════════════════════════════════════════════

def z_exit_surface(trades, z_thresholds):
    """Evaluate Z-score exits across a grid of thresholds."""
    result = {}
    for zt in z_thresholds:
        pnls = []; bars = []; reasons = defaultdict(int)
        for t in trades:
            pnl, bar, reason = eval_z_exit(t, zt)
            pnls.append(pnl); bars.append(bar); reasons[reason] += 1
        m = metrics(pnls)
        m["avg_bars"] = round(float(np.mean(bars)), 1)
        m["reasons"] = dict(reasons)
        m["z_threshold"] = zt
        result[zt] = m
    return result


# ═══════════════════════════════════════════════════════════════
# 5. STOP-LOSS SURFACE
# ═══════════════════════════════════════════════════════════════

def sl_surface(trades, atr_multiples):
    """Evaluate stop-loss at different ATR multiples."""
    result = {}
    for mult in atr_multiples:
        pnls = []; bars = []; reasons = defaultdict(int)
        winners_stopped = 0; cont_caught = 0
        total_w = 0; total_cont = 0
        for t in trades:
            cat = classify_mr_cont(t)
            if cat == "mr": total_w += 1
            else: total_cont += 1
            pnl, bar, reason = eval_sl_exit(t, mult)
            pnls.append(pnl); bars.append(bar); reasons[reason] += 1
            if reason == "SL" and cat == "mr": winners_stopped += 1
            if reason == "SL" and cat != "mr": cont_caught += 1
        m = metrics(pnls)
        m["avg_bars"] = round(float(np.mean(bars)), 1)
        m["reasons"] = dict(reasons)
        m["atr_mult"] = mult
        m["winners_stopped_pct"] = round(winners_stopped / total_w * 100, 1) if total_w > 0 else 0
        m["cont_caught_pct"] = round(cont_caught / total_cont * 100, 1) if total_cont > 0 else 0
        result[mult] = m
    return result


# ═══════════════════════════════════════════════════════════════
# 6. SESSION/OVERNIGHT EFFECT
# ═══════════════════════════════════════════════════════════════

def session_effect(trades):
    """Compare session exit variants."""
    # Variant A: forced session exit (current — max 50 bars ≈ 25h)
    pnls_a = [eval_time_exit(t, 50)[0] for t in trades]
    # Variant B: no forced session exit (max 200 bars = ~100h)
    pnls_b = [eval_time_exit(t, 200)[0] for t in trades]
    # Variant C: session exit conditional on Z magnitude
    pnls_c = []
    for t in trades:
        if abs(t.entry_z) >= 4.0:
            pnl, _, _ = eval_time_exit(t, 200)  # hold longer for strong signals
        else:
            pnl, _, _ = eval_time_exit(t, 50)
        pnls_c.append(pnl)
    # Variant D: session exit conditional on volatility
    pnls_d = []
    for t in trades:
        if t.vol_regime in ("low_vol", "mid_vol"):
            pnl, _, _ = eval_time_exit(t, 50)
        else:
            pnl, _, _ = eval_time_exit(t, 200)
        pnls_d.append(pnl)
    # Variant E: no session close for overlap session
    pnls_e = []
    for t in trades:
        if t.entry_session == "overlap":
            pnl, _, _ = eval_time_exit(t, 200)
        else:
            pnl, _, _ = eval_time_exit(t, 50)
        pnls_e.append(pnl)
    return {
        "forced_session_exit": metrics(pnls_a),
        "no_forced_exit": metrics(pnls_b),
        "conditional_on_z": metrics(pnls_c),
        "conditional_on_vol": metrics(pnls_d),
        "conditional_on_session": metrics(pnls_e),
    }


# ═══════════════════════════════════════════════════════════════
# 7. REGIME CONDITIONING
# ═══════════════════════════════════════════════════════════════

def regime_conditioning(trades, horizons, sl_mults):
    """Surfaces by regime."""
    # By Z magnitude
    z_bins = [(2, 3), (3, 4), (4, 5), (5, 100)]
    by_z = {}
    for lo, hi in z_bins:
        sub = [t for t in trades if lo <= abs(t.entry_z) < hi]
        if not sub: continue
        by_z[f"{lo}_{hi}"] = time_exit_surface(sub, horizons)
    # By vol regime
    by_vol = {}
    for vr in set(t.vol_regime for t in trades):
        sub = [t for t in trades if t.vol_regime == vr]
        if sub: by_vol[vr] = time_exit_surface(sub, horizons)
    # By session
    by_sess = {}
    for s in set(t.entry_session for t in trades):
        sub = [t for t in trades if t.entry_session == s]
        if sub: by_sess[s] = time_exit_surface(sub, horizons)
    # By pair (top 6)
    pc = defaultdict(int)
    for t in trades: pc[t.pair] += 1
    top = sorted(pc.keys(), key=lambda p: -pc[p])[:6]
    by_pair = {}
    for p in top:
        sub = [t for t in trades if t.pair == p]
        by_pair[p] = time_exit_surface(sub, horizons)
    return {"by_z": by_z, "by_vol": by_vol, "by_session": by_sess, "by_pair": by_pair}


# ═══════════════════════════════════════════════════════════════
# 8. ROBUSTNESS
# ═══════════════════════════════════════════════════════════════

def robustness(trades, horizons):
    """Period splits, pair dispersion, bootstrap, outlier sensitivity."""
    periods = {"2016-2018": (2016, 2018), "2019-2021": (2019, 2021),
               "2022-2024": (2022, 2024), "2025-2026": (2025, 2026)}
    by_period = {}
    for label, (y1, y2) in periods.items():
        sub = [t for t in trades if y1 <= t.year <= y2]
        if sub: by_period[label] = time_exit_surface(sub, horizons)

    # Cross-pair dispersion at key horizons
    pc = defaultdict(list)
    for t in trades: pc[t.pair].append(t)
    pair_results = {}
    for p, ptrades in pc.items():
        if len(ptrades) < 100: continue
        pair_results[p] = time_exit_surface(ptrades, [4, 8, 16, 32])

    # Bootstrap for key horizons
    boot = {}
    for h in [4, 8, 16, 32]:
        pnls = [eval_time_exit(t, h)[0] for t in trades]
        boot[h] = bootstrap_ci(pnls)

    # Outlier sensitivity
    all_pnls_4 = np.array([eval_time_exit(t, 4)[0] for t in trades])
    sorted_p = np.sort(all_pnls_4)
    n = len(sorted_p)
    trim_1 = all_pnls_4[(all_pnls_4 >= sorted_p[int(n*0.01)]) & (all_pnls_4 <= sorted_p[int(n*0.99)])]
    trim_5 = all_pnls_4[(all_pnls_4 >= sorted_p[int(n*0.05)]) & (all_pnls_4 <= sorted_p[int(n*0.95)])]
    outlier = {
        "full_4bar": metrics(all_pnls_4.tolist()),
        "trim_1pct": {"n": len(trim_1), "avg_pnl": round(float(np.mean(trim_1)), 2)},
        "trim_5pct": {"n": len(trim_5), "avg_pnl": round(float(np.mean(trim_5)), 2)},
    }
    return {"by_period": by_period, "by_pair": pair_results, "bootstrap": boot, "outlier": outlier}


# ═══════════════════════════════════════════════════════════════
# 9. COST SENSITIVITY
# ═══════════════════════════════════════════════════════════════

def cost_sensitivity(trades, horizons):
    """PF and EV at different cost levels for key horizons."""
    cost_levels = [0, 1, 2, 3.5, 5, 7, 10, 15]
    result = {}
    for h in [4, 8, 16, 32]:
        result[h] = {}
        for cost in cost_levels:
            pnls = []
            for t in trades:
                d = t.direction; pip = t.pip; pv = t.pv; ep = t.entry_price
                n = min(h, len(t.price_path))
                # Check SL/TP first
                exited = False
                for j in range(1, n):
                    hi = t.high_path[j]; lo = t.low_path[j]
                    if d == 1 and lo <= t.sl_price:
                        pnls.append((t.sl_price - ep) / pip * pv * t.lot - t.lot * cost)
                        exited = True; break
                    if d == -1 and hi >= t.sl_price:
                        pnls.append((ep - t.sl_price) / pip * pv * t.lot - t.lot * cost)
                        exited = True; break
                if not exited:
                    exit_p = t.price_path[n - 1]
                    gross = (exit_p - ep) * d / pip * pv * t.lot
                    pnls.append(gross - t.lot * cost)
            result[h][cost] = metrics(pnls)
    return result


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

HORIZONS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64]
Z_THRESHOLDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
SL_MULTS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

if __name__ == "__main__":
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 5 — EXIT RESPONSE SURFACE")
    print("=" * 80)

    print("\n[1] Loading data...")
    pdata = load_all("2016-01-01", "2026-07-19")
    print(f"    {len(pdata)} pairs loaded")

    print("\n[2] Running single backtest with full path recording...")
    trades = run_raw_backtest(pdata)
    print(f"    {len(trades)} trades recorded")
    if not trades:
        print("ERROR: No trades"); sys.exit(1)

    R = {}

    print("\n[3] Time-exit response surface...")
    R["time_surface"] = time_exit_surface(trades, HORIZONS)
    for h in [1, 2, 4, 8, 16, 32, 48, 64]:
        m = R["time_surface"][h]
        print(f"    {h:2d} bars ({m['horizon_hours']:5.1f}h): n={m['n']:5d} WR={m['win_rate']:5.1f}% PF={m['pf']:5.2f} P&L=${m['net_pnl']:>10,.2f} avg_bars={m['avg_bars']:5.1f}")

    print("\n[4] MAE/MFE surface...")
    R["mae_mfe"] = mae_mfe_surface(trades)
    w = R["mae_mfe"]["winners"]; l = R["mae_mfe"]["losers"]
    print(f"    Winners (n={w['count']}): MAE={w['mae_pips']['mean']}p ({w['mae_atr']['mean']} ATR) MFE={w['mfe_pips']['mean']}p ({w['mfe_atr']['mean']} ATR)")
    print(f"    Losers  (n={l['count']}): MAE={l['mae_pips']['mean']}p ({l['mae_atr']['mean']} ATR) MFE={l['mfe_pips']['mean']}p ({l['mfe_atr']['mean']} ATR)")
    print("    ATR exceedance:")
    for thr, v in R["mae_mfe"]["atr_exceedance"].items():
        print(f"      {thr}: winners={v['winners_exceed']}% losers={v['losers_exceed']}%")

    print("\n[5] Information decay...")
    R["decay"] = information_decay(trades, HORIZONS)
    for h in [1, 2, 4, 8, 16, 32]:
        d = R["decay"][h]
        print(f"    {h:2d} bars: MR captured={d['mr_captured_pct']}% CONT identified={d['cont_identified_pct']}% remaining MFE={d['remaining_mfe_pips']['mean']}p")

    print("\n[6] Z-exit surface...")
    R["z_surface"] = z_exit_surface(trades, Z_THRESHOLDS)
    for zt in Z_THRESHOLDS:
        m = R["z_surface"][zt]
        print(f"    Z>{zt:5.2f}: n={m['n']:5d} WR={m['win_rate']:5.1f}% PF={m['pf']:5.2f} P&L=${m['net_pnl']:>10,.2f} avg_bars={m['avg_bars']:5.1f}")

    print("\n[7] Stop-loss surface...")
    R["sl_surface"] = sl_surface(trades, SL_MULTS)
    for mult in SL_MULTS:
        m = R["sl_surface"][mult]
        print(f"    {mult:4.2f}x ATR: n={m['n']:5d} WR={m['win_rate']:5.1f}% PF={m['pf']:5.2f} P&L=${m['net_pnl']:>10,.2f} W_stopped={m.get('winners_stopped_pct',0):5.1f}% CONT_caught={m.get('cont_caught_pct',0):5.1f}%")

    print("\n[8] Session/overnight effect...")
    R["session"] = session_effect(trades)
    for k, v in R["session"].items():
        print(f"    {k:30s}: n={v['n']:5d} WR={v['win_rate']:5.1f}% PF={m['pf']:5.2f} P&L=${v['net_pnl']:>10,.2f}")

    print("\n[9] Regime conditioning...")
    R["regime"] = regime_conditioning(trades, HORIZONS, SL_MULTS)
    print("    Done")

    print("\n[10] Robustness checks...")
    R["robustness"] = robustness(trades, HORIZONS)
    for period, surfaces in R["robustness"]["by_period"].items():
        m4 = surfaces.get(4, {}); m8 = surfaces.get(8, {})
        print(f"    {period}: 4bar PF={m4.get('pf',0)} P&L=${m4.get('net_pnl',0):,.2f} | 8bar PF={m8.get('pf',0)} P&L=${m8.get('net_pnl',0):,.2f}")
    bh = R["robustness"]["bootstrap"]
    for h in [4, 8, 16]:
        b = bh.get(h, {}).get("pf", {})
        print(f"    Bootstrap {h}bar: PF={b.get('mean',0)} CI=[{b.get('ci_lower',0)}, {b.get('ci_upper',0)}]")
    out = R["robustness"]["outlier"]
    print(f"    Outlier: full={out['full_4bar']['avg_pnl']} trim1={out['trim_1pct']['avg_pnl']} trim5={out['trim_5pct']['avg_pnl']}")

    print("\n[11] Cost sensitivity...")
    R["cost"] = cost_sensitivity(trades, HORIZONS)
    for h in [4, 8, 16, 32]:
        costs = R["cost"][h]
        line = f"    {h:2d}bar:"
        for c in [0, 3.5, 7, 15]:
            m = costs.get(c, {})
            line += f" ${c}PF={m.get('pf',0):.2f}"
        print(line)

    # Save
    R["config"] = {
        "z_entry": Z_ENTRY, "lookback": LOOKBACK, "risk_pct": RISK_PCT,
        "atr_sl_mult": ATR_SL_MULT, "commission": COMMISSION,
        "slippage_pips": SLIPPAGE_PIPS, "pairs": len(PAIRS),
    }
    R["trade_count"] = len(trades)
    with open(OUT / "exit_surface.json", "w") as f:
        json.dump(R, f, indent=2, default=str)
    print(f"\n  Saved {OUT / 'exit_surface.json'}")
    print(f"\n[DONE] {time.time() - t0:.1f}s")
