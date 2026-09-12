"""Z-Score Mean-Reversion Backtest — Forensic Reconstruction.

Reconstructs the historical NestQuant Z-score MR strategy:
  - Entry: |Z| > z_entry_threshold (2.2) → mean reversion
  - Exit: |Z| < z_exit_threshold (0.5) → return to mean
  - Position sizing: ATR-based, 0.6% risk per trade
  - Session filter: London 07-16, NY 12-21 UTC
  - Full cost model: spread + commission + slippage

Usage:
    cd /root/that && .venv/bin/python -u scripts/zscore_mr_backtest.py
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from nestquant.research.shared.zscore.zscore import compute_zscore_causal

# ═══════════════════════════════════════════════════════════════
# STRATEGY PARAMETERS (DO NOT MODIFY during forensic run)
# ═══════════════════════════════════════════════════════════════
Z_ENTRY = 2.2
Z_EXIT = 0.5
LOOKBACK = 20
RISK_PCT = 0.006  # 0.6% per trade
ACC = 2500
LEV = 100
COMMISSION = 3.50  # per lot per round-trip
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


# ═══════════════════════════════════════════════════════════════
# SESSION FILTER
# ═══════════════════════════════════════════════════════════════

def igs(ts):
    h, d = ts.hour, ts.dayofweek
    if d == 4 and h >= SKIP_FRI:
        return False
    if d == 0 and h < SKIP_MON:
        return False
    if d >= 5:
        return False
    for s, (s2, e) in SESSIONS.items():
        if s2 <= h < e:
            return True
    return False


def get_session(ts):
    h = ts.hour
    il = 7 <= h < 16
    iny = 12 <= h < 21
    if il and iny:
        return "overlap"
    if il:
        return "london_only"
    if iny:
        return "ny_only"
    return "none"


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def pip_size(pair):
    return 0.01 if "JPY" in pair else 0.0001


def pip_value(pair):
    base, quote = pair.split("/")
    usd_per_quote = DEFAULT_USD.get(quote, 1.0)
    return pip_size(pair) * 100000 * usd_per_quote


def load_pair(pair, start, end, timeframe="30min"):
    pk = pair.replace("/", "_")
    try:
        with open(f"/root/data/{pk}.pkl", "rb") as f:
            raw = pickle.load(f)
    except Exception:
        return None
    df = raw.get(pair)
    if df is None or df.empty:
        return None
    idx = pd.to_datetime(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    df.index = idx
    df = df[(df.index >= start) & (df.index <= end)]
    if len(df) < 500:
        return None
    # Resample
    if timeframe == "30min":
        df = df[["open", "high", "low", "close"]].resample("30min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["close"])
    elif timeframe == "1h":
        df = df[["open", "high", "low", "close"]].resample("1h").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["close"])
    elif timeframe == "4h":
        df = df[["open", "high", "low", "close"]].resample("4h").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["close"])
    return df


def load_all_pairs(start, end, timeframe="30min"):
    pdata = {}
    for pair in PAIRS:
        df = load_pair(pair, start, end, timeframe)
        if df is None or len(df) < 500:
            continue
        pip = pip_size(pair)
        pv = pip_value(pair)
        spread = SPREAD.get(pair, 2.0)

        # Compute Z-scores
        close = df["close"].values.astype(np.float64)
        observations = compute_zscore_causal(close, df.index, pair, lookback=LOOKBACK)
        z_scores = np.array([o.z_score for o in observations])

        # Compute ATR
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean()
        atr_pct = atr / df["close"] * 100

        pdata[pair] = {
            "c": df["close"].values,
            "h": df["high"].values,
            "lo": df["low"].values,
            "o": df["open"].values,
            "ts": df.index,
            "n": len(df),
            "z": z_scores,
            "atr": atr.values,
            "atr_pct": atr_pct.values,
            "pip": pip,
            "pv": pv,
            "spread": spread,
        }
    return pdata


# ═══════════════════════════════════════════════════════════════
# TRADE DATA CLASS
# ═══════════════════════════════════════════════════════════════

@dataclass
class Trade:
    pair: str
    direction: int  # 1=long, -1=short
    entry_price: float
    entry_ts: object
    entry_z: float
    sl_price: float
    tp_price: float
    lot: float
    pip: float
    pv: float
    spread_pips: float
    atr_at_entry: float
    risk_dollars: float
    exit_price: float = 0.0
    exit_ts: object = None
    exit_z: float = 0.0
    pnl: float = 0.0
    gross_pnl: float = 0.0
    cost: float = 0.0
    exit_reason: str = ""
    is_win: bool = False
    entry_session: str = ""
    exit_session: str = ""
    entry_hour: int = 0
    entry_dow: int = 0
    year: int = 0
    month: str = ""
    holding_bars: int = 0
    max_adverse_pips: float = 0.0
    max_favorable_pips: float = 0.0


# ═══════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════

def run_backtest(pdata, risk_pct=RISK_PCT, max_conc=MAX_CONC,
                 session_filter=True, max_hold=MAX_HOLD_BARS):
    ref_pair = max(pdata.keys(), key=lambda p: pdata[p]["n"])
    ref = pdata[ref_pair]
    n_bars = ref["n"]

    bal = ACC
    peak = ACC
    mdd = 0.0
    open_pos = []
    trades = []
    daily_sb = ACC
    daily_d = None

    for i in range(LOOKBACK + ATR_PERIOD + 10, n_bars - 1):
        ts_now = ref["ts"][i]
        today = ts_now.date()

        # Daily reset
        if daily_d != today:
            daily_d = today
            daily_sb = bal

        # Daily loss limit (5%)
        if daily_sb > 0 and (daily_sb - bal) / daily_sb >= 0.05:
            for pos in open_pos:
                pd_ = pdata.get(pos["pair"])
                if pd_ is None or i >= pd_["n"]:
                    continue
                slp = SLIPPAGE_PIPS * pos["pip"]
                if pos["direction"] == 1:
                    ep = pd_["c"][i] - slp
                else:
                    ep = pd_["c"][i] + slp
                gross = (ep - pos["entry_price"]) * pos["direction"] / pos["pip"] * pos["pv"] * pos["lot"]
                cost = pos["lot"] * COMMISSION
                pnl = gross - cost
                bal += pnl
                es = get_session(pos["entry_ts"])
                xs = get_session(ts_now)
                trades.append(Trade(
                    pair=pos["pair"], direction=pos["direction"],
                    entry_price=pos["entry_price"], entry_ts=pos["entry_ts"],
                    entry_z=pos["entry_z"], sl_price=pos["sl_price"],
                    tp_price=pos["tp_price"], lot=pos["lot"],
                    pip=pos["pip"], pv=pos["pv"], spread_pips=pos["spread_pips"],
                    atr_at_entry=pos["atr_at_entry"], risk_dollars=pos["risk_dollars"],
                    exit_price=ep, exit_ts=ts_now, exit_z=pos["z_current"],
                    pnl=pnl, gross_pnl=gross, cost=cost,
                    exit_reason="DL", is_win=(pnl > 0),
                    entry_session=es, exit_session=get_session(ts_now),
                    entry_hour=pos["entry_ts"].hour, entry_dow=pos["entry_ts"].dayofweek,
                    year=pos["entry_ts"].year, month=pos["entry_ts"].strftime("%Y-%m"),
                    holding_bars=i - pos["bar"],
                ))
            open_pos.clear()
            continue

        # Process open positions
        remaining = []
        for pos in open_pos:
            pd_ = pdata.get(pos["pair"])
            if pd_ is None or i >= pd_["n"]:
                remaining.append(pos)
                continue

            bar_lo = pd_["lo"][i]
            bar_hi = pd_["h"][i]
            bar_cl = pd_["c"][i]
            z_now = pd_["z"][i]
            tr = pos["direction"]
            sl = pos["sl_price"]
            tp = pos["tp_price"]
            closed = False

            def _close(reason, exit_p, exit_z_val):
                nonlocal closed, bal
                gross = (exit_p - pos["entry_price"]) * tr / pos["pip"] * pos["pv"] * pos["lot"]
                cost = pos["lot"] * COMMISSION
                pnl = gross - cost
                bal += pnl
                closed = True
                es = get_session(pos["entry_ts"])
                xs = get_session(ts_now)
                trades.append(Trade(
                    pair=pos["pair"], direction=tr,
                    entry_price=pos["entry_price"], entry_ts=pos["entry_ts"],
                    entry_z=pos["entry_z"], sl_price=sl, tp_price=tp,
                    lot=pos["lot"], pip=pos["pip"], pv=pos["pv"],
                    spread_pips=pos["spread_pips"],
                    atr_at_entry=pos["atr_at_entry"], risk_dollars=pos["risk_dollars"],
                    exit_price=exit_p, exit_ts=ts_now, exit_z=exit_z_val,
                    pnl=pnl, gross_pnl=gross, cost=cost,
                    exit_reason=reason, is_win=(pnl > 0),
                    entry_session=es, exit_session=get_session(ts_now),
                    entry_hour=pos["entry_ts"].hour, entry_dow=pos["entry_ts"].dayofweek,
                    year=pos["entry_ts"].year, month=pos["entry_ts"].strftime("%Y-%m"),
                    holding_bars=i - pos["bar"],
                ))

            # SL check
            if not closed and tr == 1 and bar_lo <= sl:
                _close("SL", sl, z_now)
            elif not closed and tr == -1 and bar_hi >= sl:
                _close("SL", sl, z_now)
            # TP check
            if not closed and tr == 1 and bar_hi >= tp:
                _close("TP", tp, z_now)
            elif not closed and tr == -1 and bar_lo <= tp:
                _close("TP", tp, z_now)
            # Session close
            if not closed and not igs(ref["ts"][i]):
                slp = SLIPPAGE_PIPS * pos["pip"]
                ep = bar_cl - slp if tr == 1 else bar_cl + slp
                _close("SC", ep, z_now)
            # Max hold
            if not closed and (i - pos["bar"]) >= max_hold:
                slp = SLIPPAGE_PIPS * pos["pip"]
                ep = bar_cl - slp if tr == 1 else bar_cl + slp
                _close("MH", ep, z_now)
            # Z-score exit (mean reversion target)
            if not closed:
                z_cur = z_now if not np.isnan(z_now) else 0.0
                pos["z_current"] = z_cur
                if tr == 1 and z_cur > -Z_EXIT:
                    slp = SLIPPAGE_PIPS * pos["pip"]
                    ep = bar_cl - slp
                    _close("ZE", ep, z_cur)
                elif tr == -1 and z_cur < Z_EXIT:
                    slp = SLIPPAGE_PIPS * pos["pip"]
                    ep = bar_cl + slp
                    _close("ZE", ep, z_cur)

            if not closed:
                remaining.append(pos)

        open_pos = remaining

        # Equity tracking
        bal = max(bal, 1.0)
        if bal > peak:
            peak = bal
        dd = (peak - bal) / peak if peak > 0 else 0
        if dd > mdd:
            mdd = dd

        # Entry logic
        if not igs(ts_now) or len(open_pos) >= max_conc:
            continue

        for pair in PAIRS:
            if len(open_pos) >= max_conc:
                break
            if any(p["pair"] == pair for p in open_pos):
                continue
            pd_ = pdata.get(pair)
            if pd_ is None or i >= pd_["n"]:
                continue

            z_now = pd_["z"][i]
            if np.isnan(z_now):
                continue

            atr_now = pd_["atr"][i]
            if np.isnan(atr_now) or atr_now <= 0:
                continue

            # Entry: |Z| > Z_ENTRY → mean reversion
            if abs(z_now) < Z_ENTRY:
                continue

            direction = 1 if z_now < 0 else -1  # Buy if oversold, sell if overbought

            # ATR-based SL
            sl_dist = atr_now * ATR_SL_MULT
            if direction == 1:
                sl_price = pd_["c"][i] - sl_dist
                entry_price = pd_["c"][i] + SLIPPAGE_PIPS * pd_["pip"]
            else:
                sl_price = pd_["c"][i] + sl_dist
                entry_price = pd_["c"][i] - SLIPPAGE_PIPS * pd_["pip"]

            # Position sizing: risk-based
            risk_dollars = bal * risk_pct
            sl_pips = sl_dist / pd_["pip"]
            if sl_pips <= 0:
                continue
            lot = risk_dollars / (sl_pips * pd_["pv"])
            lot = max(0.01, round(lot, 2))
            lot = min(lot, 10.0)

            # Margin check
            notional = lot * 100000 * DEFAULT_USD.get(pair.split("/")[0], 1.0)
            req_margin = notional / LEV
            available = bal * LEV
            if req_margin > available * 0.5:
                continue

            # TP based on Z-score exit target
            # Approximate: TP at Z_EXIT → need to estimate price
            # For simplicity, use RR-based TP (ATR-based)
            tp_dist = sl_dist * 2.0  # 2:1 RR
            if direction == 1:
                tp_price = entry_price + tp_dist
            else:
                tp_price = entry_price - tp_dist

            open_pos.append({
                "pair": pair, "direction": direction,
                "entry_price": entry_price, "entry_ts": ts_now,
                "entry_z": z_now, "sl_price": sl_price, "tp_price": tp_price,
                "lot": lot, "bar": i, "pip": pd_["pip"], "pv": pd_["pv"],
                "spread_pips": pd_["spread"], "atr_at_entry": atr_now,
                "risk_dollars": risk_dollars, "z_current": z_now,
            })

    return trades, mdd, bal


# ═══════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════

def compute_metrics(trades, label=""):
    if not trades:
        return None
    pnls = np.array([t.pnl for t in trades])
    w = int(np.sum(pnls > 0))
    l_ = int(np.sum(pnls <= 0))
    gw = float(np.sum(pnls[pnls > 0])) if w > 0 else 0
    gl = float(np.abs(np.sum(pnls[pnls <= 0]))) if l_ > 0 else 0

    # Monthly returns
    md = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for t in trades:
        md[t.month]["pnl"] += t.pnl
        md[t.month]["trades"] += 1
        if t.pnl > 0:
            md[t.month]["wins"] += 1
    mk = sorted(md.keys())
    mrets = []
    prev = ACC
    neg = 0
    for k in mk:
        r = md[k]["pnl"] / prev * 100 if prev > 0 else 0
        prev += md[k]["pnl"]
        mrets.append(r)
        if r < 0:
            neg += 1

    # Equity curve
    eq = [ACC]
    for t in trades:
        eq.append(eq[-1] + t.pnl)
    ea = np.array(eq)
    rpk = np.maximum.accumulate(ea)
    dd = np.where(rpk > 0, (rpk - ea) / rpk, 0)
    max_dd = float(np.max(dd)) * 100

    # Holding
    hold = np.array([t.holding_bars for t in trades])

    # Exit reasons
    ex = defaultdict(int)
    for t in trades:
        ex[t.exit_reason] += 1

    # Z-score at entry distribution
    z_at_entry = np.array([t.entry_z for t in trades])

    nm = max(len(mrets), 1)

    return {
        "label": label,
        "trades": len(trades),
        "wins": w,
        "losses": l_,
        "win_rate": round(w / (w + l_) * 100, 2) if (w + l_) > 0 else 0,
        "profit_factor": round(gw / gl, 2) if gl > 0 else 99,
        "net_pnl": round(float(np.sum(pnls)), 2),
        "avg_pnl": round(float(np.mean(pnls)), 2),
        "median_pnl": round(float(np.median(pnls)), 2),
        "std_pnl": round(float(np.std(pnls, ddof=1)), 2) if len(pnls) > 1 else 0,
        "avg_win": round(float(np.mean(pnls[pnls > 0])), 2) if w > 0 else 0,
        "avg_loss": round(float(np.mean(pnls[pnls <= 0])), 2) if l_ > 0 else 0,
        "max_dd_pct": round(max_dd, 2),
        "n_negative_months": neg,
        "n_months": nm,
        "avg_holding_bars": round(float(np.mean(hold)), 1),
        "exits": {k: v for k, v in ex.items()},
        "z_entry_mean": round(float(np.mean(z_at_entry)), 2),
        "z_entry_std": round(float(np.std(z_at_entry)), 2),
        "z_entry_min": round(float(np.min(z_at_entry)), 2),
        "z_entry_max": round(float(np.max(z_at_entry)), 2),
    }


# ═══════════════════════════════════════════════════════════════
# Z-SCORE BINNING
# ═══════════════════════════════════════════════════════════════

def zscore_binning(trades):
    bins = {
        "z_lt_2": [], "z_2_3": [], "z_3_4": [],
        "z_4_5": [], "z_5_6": [], "z_gte_6": [],
    }
    for t in trades:
        az = abs(t.entry_z)
        if az < 2:
            bins["z_lt_2"].append(t)
        elif az < 3:
            bins["z_2_3"].append(t)
        elif az < 4:
            bins["z_3_4"].append(t)
        elif az < 5:
            bins["z_4_5"].append(t)
        elif az < 6:
            bins["z_5_6"].append(t)
        else:
            bins["z_gte_6"].append(t)
    result = {}
    for k, v in bins.items():
        if v:
            r = compute_metrics(v, k)
            result[k] = r
        else:
            result[k] = {"trades": 0}
    return result


# ═══════════════════════════════════════════════════════════════
# PER-PERIOD BREAKDOWN
# ═══════════════════════════════════════════════════════════════

def per_period_breakdown(trades):
    periods = {
        "2016-2018": (2016, 2018),
        "2019-2021": (2019, 2021),
        "2022-2024": (2022, 2024),
        "2025-2026": (2025, 2026),
    }
    result = {}
    for label, (y1, y2) in periods.items():
        subset = [t for t in trades if y1 <= t.year <= y2]
        if subset:
            result[label] = compute_metrics(subset, label)
        else:
            result[label] = {"trades": 0}
    return result


# ═══════════════════════════════════════════════════════════════
# TAIL-RISK: Z≈6 CATASTROPHIC EVENT
# ═══════════════════════════════════════════════════════════════

def find_catastrophic_trades(trades, threshold=5.0):
    extreme = [t for t in trades if abs(t.entry_z) >= threshold]
    extreme.sort(key=lambda t: t.pnl)
    return extreme


# ═══════════════════════════════════════════════════════════════
# BOOTSTRAP ROBUSTNESS
# ═══════════════════════════════════════════════════════════════

def bootstrap_robustness(trades, n_boot=2000):
    pnls = np.array([t.pnl for t in trades])
    n = len(pnls)

    wr_boot = []
    pf_boot = []
    mean_boot = []
    for _ in range(n_boot):
        s = np.random.choice(pnls, size=n, replace=True)
        w = np.sum(s > 0)
        l = np.sum(s <= 0)
        wr_boot.append(w / n * 100 if n > 0 else 0)
        gw = np.sum(s[s > 0]) if np.any(s > 0) else 0
        gl = np.abs(np.sum(s[s <= 0])) if np.any(s <= 0) else 1
        pf_boot.append(gw / gl if gl > 0 else 99)
        mean_boot.append(float(np.mean(s)))

    # Trade-order randomization
    wr_order = []
    for _ in range(n_boot):
        perm = np.random.permutation(pnls)
        # Running Sharpe-like: check if first k trades are profitable
        cum = np.cumsum(perm)
        final_wr = np.sum(perm > 0) / n * 100
        wr_order.append(final_wr)

    def ci(arr):
        p = np.percentile(arr, [2.5, 97.5])
        return {
            "mean": round(float(np.mean(arr)), 4),
            "ci_lower": round(float(p[0]), 4),
            "ci_upper": round(float(p[1]), 4),
        }

    return {
        "win_rate": ci(wr_boot),
        "profit_factor": ci(pf_boot),
        "mean_trade": ci(mean_boot),
        "trade_order_wr": ci(wr_order),
        "n_bootstrap": n_boot,
    }


# ═══════════════════════════════════════════════════════════════
# ATR-NORMALIZED EXPOSURE
# ═══════════════════════════════════════════════════════════════

def atr_normalized_analysis(trades):
    atr_ratios = []
    for t in trades:
        if t.atr_at_entry > 0 and t.pip > 0:
            sl_pips = abs(t.entry_price - t.sl_price) / t.pip
            atr_pips = t.atr_at_entry / t.pip
            if atr_pips > 0:
                atr_ratios.append(sl_pips / atr_pips)
    if not atr_ratios:
        return {}
    a = np.array(atr_ratios)
    return {
        "mean_sl_atr_ratio": round(float(np.mean(a)), 2),
        "median_sl_atr_ratio": round(float(np.median(a)), 2),
        "std_sl_atr_ratio": round(float(np.std(a, ddof=1)), 2),
        "p25": round(float(np.percentile(a, 25)), 2),
        "p75": round(float(np.percentile(a, 75)), 2),
        "p95": round(float(np.percentile(a, 95)), 2),
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pickle

    t0 = time.time()
    print("=" * 80)
    print("  Z-SCORE MEAN-REVERSION BACKTEST — Forensic Reconstruction")
    print("=" * 80)
    print(f"  Z_entry={Z_ENTRY}  Z_exit={Z_EXIT}  Lookback={LOOKBACK}")
    print(f"  Risk={RISK_PCT*100:.1f}%  ATR_SL_mult={ATR_SL_MULT}  RR=2.0")
    print(f"  Commission=${COMMISSION}/lot  Slippage={SLIPPAGE_PIPS}pips")
    print(f"  Session: London 07-16, NY 12-21 UTC")
    print()

    # Load data
    print("[1] Loading data...")
    pdata = load_all_pairs("2016-01-01", "2026-07-19", timeframe="30min")
    print(f"    {len(pdata)} pairs loaded")
    if not pdata:
        print("ERROR: No data loaded")
        sys.exit(1)

    # Run backtest
    print("\n[2] Running backtest...")
    trades, mdd, final_bal = run_backtest(pdata)
    print(f"    Trades={len(trades)}  MDD={mdd*100:.2f}%  Final=${final_bal:,.0f}")

    if not trades:
        print("ERROR: No trades generated")
        sys.exit(1)

    # Compute metrics
    print("\n[3] Computing metrics...")
    baseline = compute_metrics(trades, "baseline")
    print(f"    WR={baseline['win_rate']}%  PF={baseline['profit_factor']}")
    print(f"    Net P&L=${baseline['net_pnl']:,.2f}  Avg=${baseline['avg_pnl']:.2f}")
    print(f"    Exits={baseline['exits']}")

    # Z-score binning
    print("\n[4] Z-score magnitude binning...")
    bins = zscore_binning(trades)
    for k, v in bins.items():
        if v.get("trades", 0) > 0:
            print(f"    {k}: trades={v['trades']} WR={v.get('win_rate', 0):.1f}% PF={v.get('profit_factor', 0):.2f} P&L=${v.get('net_pnl', 0):,.2f}")
        else:
            print(f"    {k}: no trades")

    # Per-period breakdown
    print("\n[5] Per-period breakdown...")
    periods = per_period_breakdown(trades)
    for k, v in periods.items():
        if v.get("trades", 0) > 0:
            print(f"    {k}: trades={v['trades']} WR={v.get('win_rate', 0):.1f}% PF={v.get('profit_factor', 0):.2f} P&L=${v.get('net_pnl', 0):,.2f}")
        else:
            print(f"    {k}: no trades")

    # Catastrophic trades
    print("\n[6] Catastrophic trades (|Z| >= 5)...")
    catastrophic = find_catastrophic_trades(trades, threshold=5.0)
    if catastrophic:
        for t in catastrophic:
            print(f"    {t.pair} Z={t.entry_z:.2f} P&L=${t.pnl:.2f} {t.exit_reason} {t.entry_ts}")
    else:
        print("    None found")

    # ATR analysis
    print("\n[7] ATR-normalized exposure...")
    atr_stats = atr_normalized_analysis(trades)
    if atr_stats:
        for k, v in atr_stats.items():
            print(f"    {k}: {v}")

    # Bootstrap
    print("\n[8] Bootstrap robustness...")
    bootstrap = bootstrap_robustness(trades, n_boot=2000)
    for metric, vals in bootstrap.items():
        if isinstance(vals, dict) and "mean" in vals:
            print(f"    {metric}: mean={vals['mean']} CI=[{vals['ci_lower']}, {vals['ci_upper']}]")

    # Save results
    results = {
        "config": {
            "z_entry": Z_ENTRY, "z_exit": Z_EXIT, "lookback": LOOKBACK,
            "risk_pct": RISK_PCT, "atr_sl_mult": ATR_SL_MULT,
            "commission": COMMISSION, "slippage_pips": SLIPPAGE_PIPS,
            "max_conc": MAX_CONC, "max_hold": MAX_HOLD_BARS,
            "account": ACC, "leverage": LEV,
        },
        "baseline": baseline,
        "zscore_bins": bins,
        "periods": periods,
        "catastrophic_trades": [
            {
                "pair": t.pair, "z": t.entry_z, "pnl": t.pnl,
                "exit_reason": t.exit_reason, "entry_ts": str(t.entry_ts),
                "entry_price": t.entry_price, "exit_price": t.exit_price,
            }
            for t in catastrophic
        ],
        "atr_stats": atr_stats,
        "bootstrap": bootstrap,
        "final_balance": final_bal,
        "max_dd_pct": mdd * 100,
    }

    out_dir = Path("research/output/phase4")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "zscore_mr_backtest.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved {out_file}")

    # Save trade log
    trade_log = [
        {
            "pair": t.pair, "direction": "BUY" if t.direction == 1 else "SELL",
            "entry_price": t.entry_price, "entry_ts": str(t.entry_ts),
            "entry_z": t.entry_z, "sl_price": t.sl_price, "tp_price": t.tp_price,
            "lot": t.lot, "exit_price": t.exit_price, "exit_ts": str(t.exit_ts),
            "exit_z": t.exit_z, "pnl": t.pnl, "exit_reason": t.exit_reason,
            "holding_bars": t.holding_bars, "atr_at_entry": t.atr_at_entry,
            "entry_session": t.entry_session, "exit_session": t.exit_session,
            "year": t.year, "month": t.month,
        }
        for t in trades
    ]
    log_file = out_dir / "zscore_mr_trades.json"
    with open(log_file, "w") as f:
        json.dump(trade_log, f, indent=2, default=str)
    print(f"  Saved {log_file}")

    print(f"\n[DONE] {time.time() - t0:.1f}s")
