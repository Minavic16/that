"""Phase 5 — Z-Score Exit Forensics.

Comprehensive analysis of exit architecture for the Z-score MR strategy.
Entry logic is FROZEN. This is exit attribution only.

Usage:
    cd /root/that && .venv/bin/python -u scripts/exit_forensics.py
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

from nestquant.research.shared.zscore.zscore import compute_zscore_causal

# ═══════════════════════════════════════════════════════════════
# FROZEN PARAMETERS
# ═══════════════════════════════════════════════════════════════
Z_ENTRY = 2.2
Z_EXIT = 0.5
LOOKBACK = 20
RISK_PCT = 0.006
ACC = 2500
LEV = 100
COMMISSION = 3.50
SESSIONS = {"london": (7, 16), "new_york": (12, 21)}
SKIP_FRI = 20
SKIP_MON = 3
ATR_PERIOD = 14
ATR_SL_MULT = 3.0
MAX_CONC = 10
MAX_HOLD_BARS = 50
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

OUT_DIR = Path("research/output/phase5")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def igs(ts):
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


def _stats(arr, label=""):
    if not arr: return {"label": label, "count": 0}
    a = np.array(arr, dtype=float)
    return {
        "label": label, "count": int(len(a)),
        "mean": round(float(np.mean(a)), 4),
        "median": round(float(np.median(a)), 4),
        "std": round(float(np.std(a, ddof=1)), 4) if len(a) > 1 else 0,
        "p5": round(float(np.percentile(a, 5)), 4),
        "p25": round(float(np.percentile(a, 25)), 4),
        "p75": round(float(np.percentile(a, 75)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
    }


def _metrics(subset, label=""):
    if not subset: return {"label": label, "count": 0}
    pnls = np.array([t.pnl for t in subset])
    w = int(np.sum(pnls > 0)); l_ = int(np.sum(pnls <= 0))
    gw = float(np.sum(pnls[pnls > 0])) if w > 0 else 0
    gl = float(np.abs(np.sum(pnls[pnls <= 0]))) if l_ > 0 else 0
    return {
        "label": label, "count": len(subset),
        "win_rate": round(w / (w + l_) * 100, 1) if (w + l_) > 0 else 0,
        "pf": round(gw / gl, 2) if gl > 0 else 99,
        "avg_pnl": round(float(np.mean(pnls)), 2),
        "net_pnl": round(float(np.sum(pnls)), 2),
        "avg_win": round(float(np.mean(pnls[pnls > 0])), 2) if w > 0 else 0,
        "avg_loss": round(float(np.mean(pnls[pnls <= 0])), 2) if l_ > 0 else 0,
    }


def _ci(arr):
    p = np.percentile(arr, [2.5, 97.5])
    return {"mean": round(float(np.mean(arr)), 4),
            "ci_lower": round(float(p[0]), 4),
            "ci_upper": round(float(p[1]), 4)}


def classify_vol(atr_pct_arr, bar_idx):
    if bar_idx >= len(atr_pct_arr): return "unknown"
    atr = atr_pct_arr[bar_idx]
    if np.isnan(atr): return "unknown"
    valid = atr_pct_arr[~np.isnan(atr_pct_arr)]
    if len(valid) == 0: return "unknown"
    p25 = np.percentile(valid, 25); p75 = np.percentile(valid, 75); p95 = np.percentile(valid, 95)
    if atr <= p25: return "low_vol"
    elif atr >= p95: return "extreme_vol"
    elif atr >= p75: return "high_vol"
    return "mid_vol"


def classify_trend(c, e200):
    if np.isnan(e200) or e200 == 0: return "unknown"
    d = abs(c - e200) / e200 * 100
    if d < 0.1: return "near_ema"
    elif d < 0.3: return "weak_trend"
    return "strong_trend"


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_all_pairs(start, end, timeframe="30min"):
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
        close = df["close"].values.astype(np.float64)
        observations = compute_zscore_causal(close, df.index, pair, lookback=LOOKBACK)
        z_scores = np.array([o.z_score for o in observations])
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean()
        atr_pct = atr / df["close"] * 100
        pip = pip_size(pair); pv = pip_value(pair)
        pdata[pair] = {
            "c": df["close"].values, "h": df["high"].values,
            "lo": df["low"].values, "o": df["open"].values,
            "ts": df.index, "n": len(df),
            "z": z_scores, "atr": atr.values, "atr_pct": atr_pct.values,
            "pip": pip, "pv": pv, "spread": SPREAD.get(pair, 2.0),
        }
    return pdata


# ═══════════════════════════════════════════════════════════════
# TRADE DATA CLASS
# ═══════════════════════════════════════════════════════════════

@dataclass
class TradePath:
    pair: str; direction: int; entry_price: float; entry_ts: object
    entry_z: float; entry_bar: int; sl_price: float; tp_price: float
    lot: float; pip: float; pv: float; spread_pips: float
    atr_at_entry: float; risk_dollars: float
    exit_price: float = 0.0; exit_ts: object = None; exit_bar: int = 0
    exit_z: float = 0.0; exit_reason: str = ""
    pnl: float = 0.0; gross_pnl: float = 0.0; cost: float = 0.0
    is_win: bool = False; holding_bars: int = 0
    entry_session: str = ""; exit_session: str = ""
    entry_hour: int = 0; entry_dow: int = 0
    year: int = 0; month: str = ""
    mae_pips: float = 0.0; mfe_pips: float = 0.0
    mae_r: float = 0.0; mfe_r: float = 0.0
    bar_to_mae: int = 0; bar_to_mfe: int = 0
    z_path: list = field(default_factory=list)
    price_path: list = field(default_factory=list)
    atr_path: list = field(default_factory=list)
    max_z_after_entry: float = 0.0; min_z_after_entry: float = 0.0
    bars_to_z_cross_entry: int = -1
    bars_to_z_1_5: int = -1; bars_to_z_1_0: int = -1
    bars_to_z_0_5: int = -1; bars_to_z_0: int = -1
    vol_regime: str = ""; trend_regime: str = ""


# ═══════════════════════════════════════════════════════════════
# BACKTEST ENGINE WITH FULL PATH RECONSTRUCTION
# ═══════════════════════════════════════════════════════════════

def _finalize(pos, exit_p, bar_i, ts_now, reason, pdata, trades):
    pd_ = pdata.get(pos["pair"])
    if pd_ is None: return
    tr = pos["direction"]; pip = pos["pip"]; entry_bar = pos["bar"]
    gross = (exit_p - pos["entry_price"]) * tr / pip * pos["pv"] * pos["lot"]
    cost = pos["lot"] * COMMISSION; pnl = gross - cost

    sl_dist_pips = abs(pos["entry_price"] - pos["sl_price"]) / pip if pip > 0 else 1
    mae_r = pos.get("mae_pips", 0) / sl_dist_pips if sl_dist_pips > 0 else 0
    mfe_r = pos.get("mfe_pips", 0) / sl_dist_pips if sl_dist_pips > 0 else 0

    end_bar = min(bar_i + 1, pd_["n"])
    z_path = []; price_path = []; atr_path = []
    entry_z = pos["entry_z"]
    max_z = -999.0; min_z = 999.0
    b_cross = -1; b0 = -1; b05 = -1; b10 = -1; b15 = -1

    for j in range(entry_bar, end_bar):
        zv = pd_["z"][j]
        z_path.append(float(zv) if not np.isnan(zv) else 0.0)
        price_path.append(float(pd_["c"][j]))
        atr_path.append(float(pd_["atr"][j]) if not np.isnan(pd_["atr"][j]) else 0.0)
        if np.isnan(zv): continue
        if zv > max_z: max_z = zv
        if zv < min_z: min_z = zv
        elapsed = j - entry_bar
        if tr == 1:
            if b0 == -1 and zv >= 0: b0 = elapsed
            if b05 == -1 and zv >= -0.5: b05 = elapsed
            if b10 == -1 and zv >= -1.0: b10 = elapsed
            if b15 == -1 and zv >= -1.5: b15 = elapsed
            if b_cross == -1 and zv >= -entry_z: b_cross = elapsed
        else:
            if b0 == -1 and zv <= 0: b0 = elapsed
            if b05 == -1 and zv <= 0.5: b05 = elapsed
            if b10 == -1 and zv <= 1.0: b10 = elapsed
            if b15 == -1 and zv <= 1.5: b15 = elapsed
            if b_cross == -1 and zv <= entry_z: b_cross = elapsed

    t = TradePath(
        pair=pos["pair"], direction=tr, entry_price=pos["entry_price"],
        entry_ts=pos["entry_ts"], entry_z=entry_z, entry_bar=entry_bar,
        sl_price=pos["sl_price"], tp_price=pos["tp_price"],
        lot=pos["lot"], pip=pip, pv=pos["pv"], spread_pips=pos["spread_pips"],
        atr_at_entry=pos["atr_at_entry"], risk_dollars=pos["risk_dollars"],
        exit_price=exit_p, exit_ts=ts_now, exit_bar=bar_i,
        exit_z=pos.get("z_current", 0.0), exit_reason=reason,
        pnl=pnl, gross_pnl=gross, cost=cost, is_win=(pnl > 0),
        holding_bars=bar_i - entry_bar,
        entry_session=get_session(pos["entry_ts"]),
        exit_session=get_session(ts_now),
        entry_hour=pos["entry_ts"].hour, entry_dow=pos["entry_ts"].dayofweek,
        year=pos["entry_ts"].year, month=pos["entry_ts"].strftime("%Y-%m"),
        mae_pips=pos.get("mae_pips", 0), mfe_pips=pos.get("mfe_pips", 0),
        mae_r=mae_r, mfe_r=mfe_r,
        bar_to_mae=pos.get("bar_to_mae", 0), bar_to_mfe=pos.get("bar_to_mfe", 0),
        z_path=z_path, price_path=price_path, atr_path=atr_path,
        max_z_after_entry=max_z if max_z > -999 else 0.0,
        min_z_after_entry=min_z if min_z < 999 else 0.0,
        bars_to_z_cross_entry=b_cross,
        bars_to_z_1_5=b15, bars_to_z_1_0=b10,
        bars_to_z_0_5=b05, bars_to_z_0=b0,
        vol_regime=pos.get("vol_regime", "unknown"),
        trend_regime=pos.get("trend_regime", "unknown"),
    )
    trades.append(t)


def run_backtest(pdata):
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]["n"])
    ref = pdata[ref_pair]; n_bars = ref["n"]
    bal = ACC; peak = ACC; mdd = 0.0; open_pos = []; trades = []
    daily_sb = ACC; daily_d = None

    for i in range(LOOKBACK + ATR_PERIOD + 10, n_bars - 1):
        ts_now = ref["ts"][i]; today = ts_now.date()
        if daily_d != today: daily_d = today; daily_sb = bal
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos["pair"])
                if pd_ is None or i >= pd_["n"]: continue
                slp = SLIPPAGE_PIPS * pos["pip"]
                ep = pd_["c"][i] - slp if pos["direction"] == 1 else pd_["c"][i] + slp
                _finalize(pos, ep, i, ts_now, "DL", pdata, trades)
            open_pos.clear(); continue

        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos["pair"])
            if pd_ is None or i >= pd_["n"]: remaining.append(pos); continue
            bar_cl = pd_["c"][i]; z_now = pd_["z"][i]; tr = pos["direction"]
            closed = False
            def _close(reason, exit_p, zv):
                nonlocal closed
                _finalize(pos, exit_p, i, ts_now, reason, pdata, trades)
                closed = True
            if not closed and tr == 1 and pd_["lo"][i] <= pos["sl_price"]:
                _close("SL", pos["sl_price"], z_now)
            elif not closed and tr == -1 and pd_["h"][i] >= pos["sl_price"]:
                _close("SL", pos["sl_price"], z_now)
            if not closed and tr == 1 and pd_["h"][i] >= pos["tp_price"]:
                _close("TP", pos["tp_price"], z_now)
            elif not closed and tr == -1 and pd_["lo"][i] <= pos["tp_price"]:
                _close("TP", pos["tp_price"], z_now)
            if not closed and not igs(ref["ts"][i]):
                slp = SLIPPAGE_PIPS * pos["pip"]
                _close("SC", bar_cl - slp if tr == 1 else bar_cl + slp, z_now)
            if not closed and (i - pos["bar"]) >= MAX_HOLD_BARS:
                slp = SLIPPAGE_PIPS * pos["pip"]
                _close("MH", bar_cl - slp if tr == 1 else bar_cl + slp, z_now)
            if not closed:
                z_cur = z_now if not np.isnan(z_now) else 0.0
                pos["z_current"] = z_cur
                if tr == 1 and z_cur > -Z_EXIT:
                    _close("ZE", bar_cl - SLIPPAGE_PIPS * pos["pip"], z_cur)
                elif tr == -1 and z_cur < Z_EXIT:
                    _close("ZE", bar_cl + SLIPPAGE_PIPS * pos["pip"], z_cur)
            if not closed:
                if tr == 1:
                    cur_mfe = (pd_["h"][i] - pos["entry_price"]) / pos["pip"]
                    cur_mae = (pos["entry_price"] - pd_["lo"][i]) / pos["pip"]
                else:
                    cur_mfe = (pos["entry_price"] - pd_["lo"][i]) / pos["pip"]
                    cur_mae = (pd_["h"][i] - pos["entry_price"]) / pos["pip"]
                if cur_mfe > pos.get("mfe_pips", 0):
                    pos["mfe_pips"] = cur_mfe; pos["bar_to_mfe"] = i - pos["bar"]
                if cur_mae > pos.get("mae_pips", 0):
                    pos["mae_pips"] = cur_mae; pos["bar_to_mae"] = i - pos["bar"]
                remaining.append(pos)
        open_pos = remaining
        bal = max(bal, 1.0)
        if bal > peak: peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd: mdd = dd

        if not igs(ts_now) or len(open_pos) >= MAX_CONC: continue
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
            sl_price = pd_["c"][i] - sl_dist if direction == 1 else pd_["c"][i] + sl_dist
            entry_price = pd_["c"][i] + SLIPPAGE_PIPS * pd_["pip"] if direction == 1 else pd_["c"][i] - SLIPPAGE_PIPS * pd_["pip"]
            sl_pips = sl_dist / pd_["pip"]
            if sl_pips <= 0: continue
            risk_dollars = bal * RISK_PCT
            lot = risk_dollars / (sl_pips * pd_["pv"])
            lot = max(0.01, round(lot, 2)); lot = min(lot, 10.0)
            notional = lot * 100000 * DEFAULT_USD.get(pair.split("/")[0], 1.0)
            if notional / LEV > bal * LEV * 0.5: continue
            tp_dist = sl_dist * 2.0
            tp_price = entry_price + tp_dist if direction == 1 else entry_price - tp_dist
            vr = classify_vol(pd_["atr_pct"], i)
            open_pos.append({
                "pair": pair, "direction": direction, "entry_price": entry_price,
                "entry_ts": ts_now, "entry_z": z_now, "bar": i,
                "sl_price": sl_price, "tp_price": tp_price, "lot": lot,
                "pip": pd_["pip"], "pv": pd_["pv"], "spread_pips": pd_["spread"],
                "atr_at_entry": atr_now, "risk_dollars": risk_dollars,
                "z_current": z_now, "mfe_pips": 0.0, "mae_pips": 0.0,
                "bar_to_mfe": 0, "bar_to_mae": 0, "vol_regime": vr,
            })
    return trades, mdd, bal


# ═══════════════════════════════════════════════════════════════
# 1. MAE/MFE ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_mae_mfe(trades):
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]
    result = {
        "wins": {
            "mae_pips": _stats([t.mae_pips for t in wins], "mae_pips"),
            "mfe_pips": _stats([t.mfe_pips for t in wins], "mfe_pips"),
            "mae_r": _stats([t.mae_r for t in wins], "mae_r"),
            "mfe_r": _stats([t.mfe_r for t in wins], "mfe_r"),
        },
        "losses": {
            "mae_pips": _stats([t.mae_pips for t in losses], "mae_pips"),
            "mfe_pips": _stats([t.mfe_pips for t in losses], "mfe_pips"),
            "mae_r": _stats([t.mae_r for t in losses], "mae_r"),
            "mfe_r": _stats([t.mfe_r for t in losses], "mfe_r"),
        },
    }
    # By entry Z
    z_bins = [(2, 3), (3, 4), (4, 5), (5, 6), (6, 100)]
    by_z = {}
    for lo, hi in z_bins:
        sub = [t for t in trades if lo <= abs(t.entry_z) < hi]
        if sub:
            by_z[f"z_{lo}_{hi}"] = {
                "count": len(sub), "win_rate": round(sum(1 for t in sub if t.is_win) / len(sub) * 100, 1),
                "mae_pips": _stats([t.mae_pips for t in sub], "mae_pips"),
                "mfe_pips": _stats([t.mfe_pips for t in sub], "mfe_pips"),
                "mae_r": _stats([t.mae_r for t in sub], "mae_r"),
                "mfe_r": _stats([t.mfe_r for t in sub], "mfe_r"),
            }
    result["by_entry_z"] = by_z
    # By pair (top 10)
    pair_counts = defaultdict(int)
    for t in trades: pair_counts[t.pair] += 1
    top_pairs = sorted(pair_counts.keys(), key=lambda p: -pair_counts[p])[:10]
    by_pair = {}
    for pair in top_pairs:
        sub = [t for t in trades if t.pair == pair]
        by_pair[pair] = {
            "count": len(sub),
            "win_rate": round(sum(1 for t in sub if t.is_win) / len(sub) * 100, 1),
            "mae_pips": _stats([t.mae_pips for t in sub], "mae_pips"),
            "mfe_pips": _stats([t.mfe_pips for t in sub], "mfe_pips"),
        }
    result["by_pair"] = by_pair
    # By exit reason
    by_exit = {}
    for ex in set(t.exit_reason for t in trades):
        sub = [t for t in trades if t.exit_reason == ex]
        by_exit[ex] = {
            "count": len(sub),
            "win_rate": round(sum(1 for t in sub if t.is_win) / len(sub) * 100, 1),
            "mae_pips": _stats([t.mae_pips for t in sub], "mae_pips"),
            "mfe_pips": _stats([t.mfe_pips for t in sub], "mfe_pips"),
            "mae_r": _stats([t.mae_r for t in sub], "mae_r"),
            "mfe_r": _stats([t.mfe_r for t in sub], "mfe_r"),
        }
    result["by_exit_reason"] = by_exit
    # By vol regime
    by_vol = {}
    for vr in set(t.vol_regime for t in trades):
        sub = [t for t in trades if t.vol_regime == vr]
        if sub:
            by_vol[vr] = {
                "count": len(sub),
                "win_rate": round(sum(1 for t in sub if t.is_win) / len(sub) * 100, 1),
                "mae_pips": _stats([t.mae_pips for t in sub], "mae_pips"),
                "mfe_pips": _stats([t.mfe_pips for t in sub], "mfe_pips"),
            }
    result["by_vol_regime"] = by_vol
    # By session
    by_sess = {}
    for s in set(t.entry_session for t in trades):
        sub = [t for t in trades if t.entry_session == s]
        if sub:
            by_sess[s] = {
                "count": len(sub),
                "win_rate": round(sum(1 for t in sub if t.is_win) / len(sub) * 100, 1),
                "mae_pips": _stats([t.mae_pips for t in sub], "mae_pips"),
                "mfe_pips": _stats([t.mfe_pips for t in sub], "mfe_pips"),
            }
    result["by_session"] = by_sess
    return result


# ═══════════════════════════════════════════════════════════════
# 2. TRADE-PATH ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_trade_paths(trades):
    mr = []; cont = []
    for t in trades:
        if t.direction == 1:
            if t.max_z_after_entry > t.entry_z: mr.append(t)
            else: cont.append(t)
        else:
            if t.min_z_after_entry < t.entry_z: mr.append(t)
            else: cont.append(t)

    further_against = []
    for t in trades:
        if t.direction == 1 and t.min_z_after_entry < t.entry_z - 1.0:
            further_against.append(t)
        elif t.direction == -1 and t.max_z_after_entry > t.entry_z + 1.0:
            further_against.append(t)
    recovered = [t for t in further_against if t.is_win]

    cross_entry = [t.bars_to_z_cross_entry for t in trades if t.bars_to_z_cross_entry >= 0]
    to_0 = [t.bars_to_z_0 for t in trades if t.bars_to_z_0 >= 0]
    to_05 = [t.bars_to_z_0_5 for t in trades if t.bars_to_z_0_5 >= 0]
    to_10 = [t.bars_to_z_1_0 for t in trades if t.bars_to_z_1_0 >= 0]
    to_15 = [t.bars_to_z_1_5 for t in trades if t.bars_to_z_1_5 >= 0]

    return {
        "z_trajectory": {
            "max_z_after_entry": _stats([t.max_z_after_entry for t in trades], "max_z"),
            "min_z_after_entry": _stats([t.min_z_after_entry for t in trades], "min_z"),
        },
        "time_to_z_targets": {
            "cross_entry": _stats(cross_entry, "cross_entry"),
            "to_z_0": _stats(to_0, "to_z_0"),
            "to_z_0_5": _stats(to_05, "to_z_0_5"),
            "to_z_1_0": _stats(to_10, "to_z_1_0"),
            "to_z_1_5": _stats(to_15, "to_z_1_5"),
        },
        "classification": {
            "mean_reverting": {
                "count": len(mr), "pct": round(len(mr) / len(trades) * 100, 1) if trades else 0,
                "win_rate": round(sum(1 for t in mr if t.is_win) / len(mr) * 100, 1) if mr else 0,
                "avg_pnl": round(float(np.mean([t.pnl for t in mr])), 2) if mr else 0,
                "avg_mfe": round(float(np.mean([t.mfe_pips for t in mr])), 2) if mr else 0,
                "avg_mae": round(float(np.mean([t.mae_pips for t in mr])), 2) if mr else 0,
            },
            "continuation": {
                "count": len(cont), "pct": round(len(cont) / len(trades) * 100, 1) if trades else 0,
                "win_rate": round(sum(1 for t in cont if t.is_win) / len(cont) * 100, 1) if cont else 0,
                "avg_pnl": round(float(np.mean([t.pnl for t in cont])), 2) if cont else 0,
                "avg_mfe": round(float(np.mean([t.mfe_pips for t in cont])), 2) if cont else 0,
                "avg_mae": round(float(np.mean([t.mae_pips for t in cont])), 2) if cont else 0,
            },
        },
        "recovery_after_adverse": {
            "count": len(further_against),
            "pct_of_total": round(len(further_against) / len(trades) * 100, 1) if trades else 0,
            "recovery_rate": round(len(recovered) / len(further_against) * 100, 1) if further_against else 0,
            "avg_pnl": round(float(np.mean([t.pnl for t in further_against])), 2) if further_against else 0,
        },
    }


# ═══════════════════════════════════════════════════════════════
# 3. HOLDING-TIME ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_holding_time(trades):
    buckets = {
        "lt_15m": (0, 0), "15_30m": (1, 1), "30_60m": (2, 3),
        "1_2h": (4, 7), "2_4h": (8, 15), "4_8h": (16, 31),
        "8_24h": (32, 47), "gt_24h": (48, 9999),
    }
    result = {}
    for name, (lo, hi) in buckets.items():
        sub = [t for t in trades if lo <= t.holding_bars <= hi]
        if not sub: result[name] = {"count": 0}; continue
        m = _metrics(sub, name)
        mae = np.array([t.mae_pips for t in sub])
        mfe = np.array([t.mfe_pips for t in sub])
        m["mae_mean"] = round(float(np.mean(mae)), 2)
        m["mfe_mean"] = round(float(np.mean(mfe)), 2)
        m["mfe_mae_ratio"] = round(float(np.mean(mfe) / np.mean(mae)), 2) if np.mean(mae) > 0 else 0
        result[name] = m
    return result


# ═══════════════════════════════════════════════════════════════
# 4. EXIT COMPONENT ATTRIBUTION
# ═══════════════════════════════════════════════════════════════

def evaluate_exit_variants(trades, pdata):
    baseline = _metrics(trades, "current")
    no_sc = [t for t in trades if t.exit_reason != "SC"]
    no_tp = [t for t in trades if t.exit_reason != "TP"]
    no_sl = [t for t in trades if t.exit_reason != "SL"]
    no_ze = [t for t in trades if t.exit_reason != "ZE"]

    # Estimate what happens if ZE removed
    ze_trades = [t for t in trades if t.exit_reason == "ZE"]
    other = [t for t in trades if t.exit_reason != "ZE"]
    est_pnls = []
    for t in ze_trades:
        sl_dist = abs(t.entry_price - t.sl_price) / t.pip if t.pip > 0 else 1
        if t.mae_r > 0.5:
            est_pnl = -sl_dist * t.pv * t.lot * 0.7 - t.lot * COMMISSION
        else:
            est_pnl = t.pnl * 0.8
        est_pnls.append(est_pnl)
    est_all = np.concatenate([np.array([t.pnl for t in other]), np.array(est_pnls)])
    w = int(np.sum(est_all > 0)); l_ = int(np.sum(est_all <= 0))
    gw = float(np.sum(est_all[est_all > 0])) if w > 0 else 0
    gl = float(np.abs(np.sum(est_all[est_all <= 0]))) if l_ > 0 else 0
    no_ze_est = {
        "label": "no_z_exit_estimated", "count": len(trades),
        "ze_trades_affected": len(ze_trades),
        "win_rate": round(w / (w + l_) * 100, 1) if (w + l_) > 0 else 0,
        "pf": round(gw / gl, 2) if gl > 0 else 99,
        "avg_pnl": round(float(np.mean(est_all)), 2),
        "net_pnl": round(float(np.sum(est_all)), 2),
    }
    return {
        "current": baseline, "no_z_exit": no_ze_est,
        "no_session_close": _metrics(no_sc, "no_session_close"),
        "no_tp": _metrics(no_tp, "no_tp"),
        "no_sl": _metrics(no_sl, "no_sl"),
    }


# ═══════════════════════════════════════════════════════════════
# 5. COUNTERFACTUAL EXIT ANALYSIS
# ═══════════════════════════════════════════════════════════════

def counterfactual_exits(trades):
    result = {}
    # Fixed time exits
    for max_bars in [4, 8, 16, 32, 48]:
        sub = [t for t in trades if t.holding_bars <= max_bars]
        result[f"time_exit_{max_bars}bars"] = _metrics(sub, f"time_{max_bars}")
    # MFE protection: exit if MFE >= 1R then final < 0.5R
    protected = []
    for t in trades:
        sl_dist = abs(t.entry_price - t.sl_price) / t.pip if t.pip > 0 else 1
        mfe_r = t.mfe_pips / sl_dist if sl_dist > 0 else 0
        final_r = t.pnl / (sl_dist * t.pv * t.lot) if (sl_dist * t.pv * t.lot) > 0 else 0
        if mfe_r >= 1.0 and final_r < 0.5:
            # Would have protected at ~0.5R
            t2 = TradePath(**{k: v for k, v in t.__dict__.items()})
            t2.pnl = 0.5 * sl_dist * t.pv * t.lot - t.lot * COMMISSION
            t2.exit_reason = "MFE_PROTECT"
            protected.append(t2)
        else:
            protected.append(t)
    result["mfe_protection_1R"] = _metrics(protected, "mfe_protection_1R")
    # ATR trailing
    trailing = []
    for t in trades:
        if t.mfe_pips > 0 and t.atr_at_entry > 0:
            atr_pips = t.atr_at_entry / t.pip
            trail_dist = 2.0 * atr_pips
            if t.mfe_pips - t.mae_pips > trail_dist:
                t2 = TradePath(**{k: v for k, v in t.__dict__.items()})
                t2.pnl = (t.mfe_pips - trail_dist) * t.pv * t.lot - t.lot * COMMISSION
                t2.exit_reason = "TRAIL"; trailing.append(t2)
            else:
                trailing.append(t)
        else:
            trailing.append(t)
    result["atr_trailing_2x"] = _metrics(trailing, "atr_trailing_2x")
    # MAE stop at 1.5R
    adjusted = []
    for t in trades:
        if t.mae_r > 1.5:
            sl_dist = abs(t.entry_price - t.sl_price) / t.pip if t.pip > 0 else 1
            t2 = TradePath(**{k: v for k, v in t.__dict__.items()})
            t2.pnl = -1.5 * sl_dist * t.pv * t.lot - t.lot * COMMISSION
            t2.exit_reason = "MAE_STOP"; adjusted.append(t2)
        else:
            adjusted.append(t)
    result["mae_stop_1_5R"] = _metrics(adjusted, "mae_stop_1_5R")
    return result


# ═══════════════════════════════════════════════════════════════
# 6. CRITICAL HYPOTHESIS: MR vs CONTINUATION
# ═══════════════════════════════════════════════════════════════

def test_mr_vs_continuation(trades):
    mr = []; cont = []
    for t in trades:
        if t.direction == 1:
            if t.max_z_after_entry > t.entry_z: mr.append(t)
            else: cont.append(t)
        else:
            if t.min_z_after_entry < t.entry_z: mr.append(t)
            else: cont.append(t)

    cont_recovered = [t for t in cont if t.is_win]

    # ATR expansion for continuation trades
    atr_exp_r = []; atr_exp_n = []
    for t in cont:
        if t.atr_path and len(t.atr_path) > 1 and t.atr_path[0] > 0:
            expansion = t.atr_path[-1] / t.atr_path[0]
            if t.is_win: atr_exp_r.append(expansion)
            else: atr_exp_n.append(expansion)

    result = {
        "mean_reverting": {
            "count": len(mr),
            "pct": round(len(mr) / len(trades) * 100, 1) if trades else 0,
            "win_rate": round(sum(1 for t in mr if t.is_win) / len(mr) * 100, 1) if mr else 0,
            "avg_pnl": round(float(np.mean([t.pnl for t in mr])), 2) if mr else 0,
        },
        "continuation": {
            "count": len(cont),
            "pct": round(len(cont) / len(trades) * 100, 1) if trades else 0,
            "win_rate": round(sum(1 for t in cont if t.is_win) / len(cont) * 100, 1) if cont else 0,
            "avg_pnl": round(float(np.mean([t.pnl for t in cont])), 2) if cont else 0,
        },
        "continuation_recovery": {
            "recovered": len(cont_recovered),
            "rate": round(len(cont_recovered) / len(cont) * 100, 1) if cont else 0,
        },
        "atr_expansion": {
            "when_recovered": _stats(atr_exp_r, "atr_expansion"),
            "when_not_recovered": _stats(atr_exp_n, "atr_expansion"),
        },
    }
    if mr and cont:
        mr_pnls = np.array([t.pnl for t in mr])
        cont_pnls = np.array([t.pnl for t in cont])
        t_stat, p_val = sp_stats.mannwhitneyu(mr_pnls, cont_pnls, alternative="greater")
        result["mannwhitney"] = {
            "t_stat": round(float(t_stat), 2),
            "p_value": round(float(p_val), 6),
            "significant_005": p_val < 0.05,
        }
    return result


# ═══════════════════════════════════════════════════════════════
# 7. ROBUSTNESS CHECKS
# ═══════════════════════════════════════════════════════════════

def robustness_checks(trades):
    periods = {"2016-2018": (2016, 2018), "2019-2021": (2019, 2021),
               "2022-2024": (2022, 2024), "2025-2026": (2025, 2026)}
    by_period = {}
    for label, (y1, y2) in periods.items():
        sub = [t for t in trades if y1 <= t.year <= y2]
        m = _metrics(sub, label)
        if sub:
            m["mae_mean"] = round(float(np.mean([t.mae_pips for t in sub])), 2)
            m["mfe_mean"] = round(float(np.mean([t.mfe_pips for t in sub])), 2)
        by_period[label] = m

    pair_counts = defaultdict(int)
    for t in trades: pair_counts[t.pair] += 1
    top_pairs = sorted(pair_counts.keys(), key=lambda p: -pair_counts[p])[:10]
    by_pair = {p: _metrics([t for t in trades if t.pair == p], p) for p in top_pairs}

    pnls = np.array([t.pnl for t in trades]); n = len(pnls)
    wr_b = []; pf_b = []; mean_b = []
    for _ in range(2000):
        s = np.random.choice(pnls, size=n, replace=True)
        w = np.sum(s > 0); wr_b.append(w / n * 100)
        gw = np.sum(s[s > 0]) if np.any(s > 0) else 0
        gl = np.abs(np.sum(s[s <= 0])) if np.any(s <= 0) else 1
        pf_b.append(gw / gl if gl > 0 else 99)
        mean_b.append(float(np.mean(s)))

    sorted_pnls = np.sort(pnls)
    trim_1 = pnls[(pnls >= sorted_pnls[int(n * 0.01)]) & (pnls <= sorted_pnls[int(n * 0.99)])]
    trim_5 = pnls[(pnls >= sorted_pnls[int(n * 0.05)]) & (pnls <= sorted_pnls[int(n * 0.95)])]

    return {
        "by_period": by_period, "by_pair": by_pair,
        "bootstrap": {"win_rate": _ci(wr_b), "profit_factor": _ci(pf_b), "mean_trade": _ci(mean_b)},
        "outlier_sensitivity": {
            "full": _metrics(trades, "full"),
            "trim_1pct": {"count": len(trim_1), "avg_pnl": round(float(np.mean(trim_1)), 2)},
            "trim_5pct": {"count": len(trim_5), "avg_pnl": round(float(np.mean(trim_5)), 2)},
        },
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t0 = time.time()
    print("=" * 80)
    print("  PHASE 5 — Z-SCORE EXIT FORENSICS")
    print("=" * 80)

    print("\n[1] Loading data...")
    pdata = load_all_pairs("2016-01-01", "2026-07-19")
    print(f"    {len(pdata)} pairs loaded")

    print("\n[2] Running backtest with full path reconstruction...")
    trades, mdd, final_bal = run_backtest(pdata)
    print(f"    Trades={len(trades)} MDD={mdd*100:.2f}%")

    if not trades:
        print("ERROR: No trades"); sys.exit(1)

    baseline = _metrics(trades, "baseline")
    print(f"    WR={baseline['win_rate']}% PF={baseline['pf']} P&L=${baseline['net_pnl']:,.2f}")
    exits = defaultdict(int)
    for t in trades: exits[t.exit_reason] += 1
    print(f"    Exits: {dict(exits)}")

    R = {}

    print("\n[3] MAE/MFE analysis...")
    R["mae_mfe"] = analyze_mae_mfe(trades)
    print(f"    Wins: MAE={R['mae_mfe']['wins']['mae_pips']['mean']}p MFE={R['mae_mfe']['wins']['mfe_pips']['mean']}p")
    print(f"    Losses: MAE={R['mae_mfe']['losses']['mae_pips']['mean']}p MFE={R['mae_mfe']['losses']['mfe_pips']['mean']}p")

    print("\n[4] Trade-path analysis...")
    R["trade_paths"] = analyze_trade_paths(trades)
    mr = R["trade_paths"]["classification"]["mean_reverting"]
    cont = R["trade_paths"]["classification"]["continuation"]
    print(f"    MR: {mr['count']} ({mr['pct']}%) WR={mr['win_rate']}% P&L=${mr['avg_pnl']}")
    print(f"    CONT: {cont['count']} ({cont['pct']}%) WR={cont['win_rate']}% P&L=${cont['avg_pnl']}")
    rec = R["trade_paths"]["recovery_after_adverse"]
    print(f"    Recovery after adverse: {rec['recovery_rate']}% ({rec['count']} trades)")

    print("\n[5] Holding-time analysis...")
    R["holding_time"] = analyze_holding_time(trades)
    for k, v in R["holding_time"].items():
        if v.get("count", 0) > 0:
            print(f"    {k}: n={v['count']} WR={v.get('win_rate',0)}% PF={v.get('pf',0)} MFE/MAE={v.get('mfe_mae_ratio',0)}")

    print("\n[6] Exit component attribution...")
    R["exit_attribution"] = evaluate_exit_variants(trades, pdata)
    for k, v in R["exit_attribution"].items():
        if v.get("count", 0) > 0:
            print(f"    {k}: n={v['count']} WR={v.get('win_rate',0)}% PF={v.get('pf',0)} P&L=${v.get('net_pnl',0):,.2f}")

    print("\n[7] Counterfactual exits...")
    R["counterfactual"] = counterfactual_exits(trades)
    for k, v in R["counterfactual"].items():
        if v.get("count", 0) > 0:
            print(f"    {k}: n={v['count']} WR={v.get('win_rate',0)}% PF={v.get('pf',0)} P&L=${v.get('net_pnl',0):,.2f}")

    print("\n[8] MR vs continuation hypothesis...")
    R["mr_vs_continuation"] = test_mr_vs_continuation(trades)
    mw = R["mr_vs_continuation"].get("mannwhitney", {})
    if mw:
        print(f"    Mann-Whitney p={mw['p_value']} significant={mw['significant_005']}")

    print("\n[9] Robustness checks...")
    R["robustness"] = robustness_checks(trades)
    for k, v in R["robustness"]["by_period"].items():
        if v.get("count", 0) > 0:
            print(f"    {k}: n={v['count']} WR={v.get('win_rate',0)}% PF={v.get('pf',0)} MAE={v.get('mae_mean',0)}p MFE={v.get('mfe_mean',0)}p")
    bs = R["robustness"]["bootstrap"]
    print(f"    Bootstrap PF: {bs['profit_factor']['mean']} CI=[{bs['profit_factor']['ci_lower']}, {bs['profit_factor']['ci_upper']}]")

    # Save
    R["baseline"] = baseline
    R["config"] = {
        "z_entry": Z_ENTRY, "z_exit": Z_EXIT, "lookback": LOOKBACK,
        "risk_pct": RISK_PCT, "atr_sl_mult": ATR_SL_MULT,
        "commission": COMMISSION, "slippage_pips": SLIPPAGE_PIPS,
    }
    with open(OUT_DIR / "exit_forensics.json", "w") as f:
        json.dump(R, f, indent=2, default=str)
    print(f"\n  Saved {OUT_DIR / 'exit_forensics.json'}")
    print(f"\n[DONE] {time.time() - t0:.1f}s")
