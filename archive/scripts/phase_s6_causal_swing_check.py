"""
Phase S6C: Causal Swing Lookahead Quantification — Frozen S6 Breakout Config

Experiment ID: S6C-2026-001

Purpose
-------
The S0-S6 research signal (`generate_signal_mechanism`) reads swing levels from
a centered-window detector that is forward-filled WITHOUT an availability shift.
A swing at bar j is only confirmable at the close of bar j+lookback, yet the
research code can reference swings with j+lookback > decision bar i.

This script QUANTIFIES the impact. It does NOT repair or optimize anything:
- Variant A ("research"): byte-identical frozen S6 logic, imported unmodified.
- Variant B ("causal"):   identical detection rule, but a swing becomes usable
                          only at bar j+lookback (shift-by-availability).
Both variants run through the SAME imported `simulate_with_risk_scaling`
(flat risk, COST_SCENARIOS["base"]) so the ONLY difference is swing causality.

Outputs: research_data/s6c/S6C_causal_swing_results.json (+ .md report)
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))  # makes `nestquant` package importable

DATA_DIR = Path("/root/data")
OUT_DIR = REPO_ROOT / "research_data" / "s6c"

EXPERIMENT_ID = "S6C-2026-001"
SPLIT_DATE = pd.Timestamp("2024-01-01")  # S3/S4 fresh holdout boundary


# ---------------------------------------------------------------------------
# Load frozen research module (unmodified)
# ---------------------------------------------------------------------------

def load_s6_module():
    path = Path(__file__).resolve().parent / "phase_s6_adaptive_risk.py"
    spec = importlib.util.spec_from_file_location("phase_s6_research", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["phase_s6_research"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Variant B: causal swing levels (identical rule, shifted availability)
# ---------------------------------------------------------------------------

def compute_rolling_swing_levels_causal(close, high, low, lookback):
    """Same centered-window detection as research; availability delayed by
    `lookback` bars: a swing at bar j enters the ffilled level stream at j+lookback."""
    n = len(close)
    raw_high = np.full(n, np.nan)
    raw_low = np.full(n, np.nan)
    for i in range(lookback, n - lookback):
        wh = high[i - lookback:i + lookback + 1]
        wl = low[i - lookback:i + lookback + 1]
        if high[i] == np.max(wh):
            raw_high[i] = high[i]
        if low[i] == np.min(wl):
            raw_low[i] = low[i]

    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    for j in range(n):
        if not np.isnan(raw_high[j]) and j + lookback < n:
            sh[j + lookback] = raw_high[j]
        if not np.isnan(raw_low[j]) and j + lookback < n:
            sl[j + lookback] = raw_low[j]
    for i in range(1, n):
        if np.isnan(sh[i]):
            sh[i] = sh[i - 1]
        if np.isnan(sl[i]):
            sl[i] = sl[i - 1]
    return sh, sl, raw_high, raw_low


def generate_signal_mechanism_causal(df, s6, lookback=None, atr_period=None):
    """Body-identical to s6.generate_signal_mechanism except swing source."""
    lookback = int(lookback if lookback is not None else s6.LOOKBACK)
    atr_period = int(atr_period if atr_period is not None else s6.ATR_PERIOD)
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    open_ = df["open"].values
    swing_high, swing_low, _, _ = compute_rolling_swing_levels_causal(
        close, high, low, lookback)
    atr = s6.compute_atr_independent(high, low, close, atr_period)
    n = len(close)
    signal = np.zeros(n, dtype=int)
    displacement_atr = np.zeros(n)
    warmup = lookback * 2 + atr_period + 1
    for i in range(warmup, n):
        if atr[i] <= 0:
            continue
        prev_sh = swing_high[i - 1]
        prev_sl = swing_low[i - 1]
        if np.isnan(prev_sh) or np.isnan(prev_sl):
            continue
        if close[i - 1] <= prev_sh < close[i]:
            signal[i] = 1
            displacement_atr[i] = (close[i] - prev_sh) / atr[i]
        elif close[i - 1] >= prev_sl > close[i]:
            signal[i] = -1
            displacement_atr[i] = (prev_sl - close[i]) / atr[i]
    return pd.DataFrame({
        "signal": signal, "displacement_atr": displacement_atr,
        "swing_high": swing_high, "swing_low": swing_low,
        "atr": atr, "open": open_, "high": high, "low": low, "close": close,
    }, index=df.index)


# ---------------------------------------------------------------------------
# Signal-level diff helpers
# ---------------------------------------------------------------------------

def signal_records(sig_df: pd.DataFrame) -> list[tuple[pd.Timestamp, int]]:
    s = sig_df["signal"].values
    idx = sig_df.index
    return [(idx[i], int(s[i])) for i in range(len(s)) if s[i] != 0]


def count_unconfirmed_usages(sig_df: pd.DataFrame, raw_high, raw_low, lookback) -> int:
    """Signals whose referenced swing was not yet confirmable at decision time."""
    sig = sig_df["signal"].values
    idx = sig_df.index
    pos = {ts: k for k, ts in enumerate(idx)}
    violations = 0
    for ts, direction in signal_records(sig_df):
        i = pos[ts]
        raw = raw_high if direction == 1 else raw_low
        j = i - 1
        while j >= 0 and np.isnan(raw[j]):
            j -= 1
        if j >= 0 and j + lookback > i:
            violations += 1
    return violations


def diff_signals(a_recs, b_recs, idx, lookback):
    """Classify A signals under B: kept (same bar+dir), delayed (same dir within
    lookback bars), lost (no match). Also count B-only new signals."""
    a_set = set(a_recs)
    b_set = set(b_recs)
    b_times_by_dir = {}
    for ts, d in b_recs:
        b_times_by_dir.setdefault(d, set()).add(ts)

    freq = pd.infer_freq(idx)
    step = pd.tseries.frequencies.to_offset(freq if freq else "4h")
    common, delayed, lost = 0, 0, 0
    horizon = step * lookback
    for ts, d in a_recs:
        if (ts, d) in b_set:
            common += 1
            continue
        if any(ts < t <= ts + horizon for t in b_times_by_dir.get(d, ())):
            delayed += 1
        else:
            lost += 1
    b_only = len(b_recs) - len(b_set & a_set)
    return {
        "total_a": len(a_recs),
        "total_b": len(b_recs),
        "kept_identical_bar_and_dir": common,
        "delayed_within_lookback": delayed,
        "lost_no_b_equivalent": lost,
        "b_only_new": b_only,
        "affected_pct": round(100.0 * (delayed + lost) / max(len(a_recs), 1), 2),
    }


# ---------------------------------------------------------------------------
# Trade/metric comparison
# ---------------------------------------------------------------------------

def period_metrics(trades, s6, label):
    """Full-sample plus pre/post holdout-split breakdown."""
    out = {"full": dict(s6.sim_metrics_extended(trades, label))}
    for name, mask_fn in (
        ("train_to_2023", lambda t: t["entry_time"] < SPLIT_DATE),
        ("holdout_2024_plus", lambda t: t["entry_time"] >= SPLIT_DATE),
    ):
        sub = [t for t in trades if mask_fn(t)]
        m = dict(s6.sim_metrics_extended(sub, f"{label}_{name}"))
        out[name] = m
    return out


def exit_reason_mix(trades):
    mix: dict[str, int] = {}
    for t in trades:
        mix[t["exit_reason"]] = mix.get(t["exit_reason"], 0) + 1
    return mix


def summarize(trades, s6):
    m = s6.sim_metrics_extended(trades, "")
    return {
        "n_trades": m.get("n", len(trades)),
        "win_rate": m.get("win_rate"),
        "profit_factor": m.get("profit_factor"),
        "avg_pnl_pips_expectancy": m.get("avg_pnl_pips"),
        "total_net_pnl_pips": round(sum(t["pnl_pips"] for t in trades), 2),
        "max_dd_r": m.get("max_dd_r"),
        "max_loss_streak": m.get("max_loss_streak"),
        "losing_months": m.get("losing_months"),
        "exit_reason_mix": exit_reason_mix(trades),
    }


def swing_series_divergence(sig_a, sig_b):
    """Share of bars where the effective swing levels differ between variants
    (attribution evidence: these bars drive trailing-stop/level differences)."""
    n = len(sig_a)
    dh = int((sig_a["swing_high"].values != sig_b["swing_high"].values).sum())
    dl = int((sig_a["swing_low"].values != sig_b["swing_low"].values).sum())
    return {"high_diff_bars_pct": round(100.0 * dh / n, 3),
            "low_diff_bars_pct": round(100.0 * dl / n, 3)}


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def load_pair_4h(s6) -> tuple[dict[str, pd.DataFrame], list[str]]:
    pair_4h: dict[str, pd.DataFrame] = {}
    missing = []
    for pair in s6.ALL_PAIRS:
        fp = DATA_DIR / f"{pair.replace('/', '_')}.pkl"
        if not fp.exists():
            fp = DATA_DIR / "4h" / f"{pair.replace('/', '_')}.pkl"
        if not fp.exists():
            missing.append(pair)
            continue
        raw = pd.read_pickle(fp)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, pd.DataFrame) and "close" in v.columns:
                    df = v.copy()
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    agg = {"open": "first", "high": "max", "low": "min",
                           "close": "last", "volume": "sum"}
                    pair_4h[k] = df.resample("4h").agg(agg).dropna()
        elif isinstance(raw, pd.DataFrame):
            df = raw.copy()
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            agg = {"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"}
            pair_4h[pair] = df.resample("4h").agg(agg).dropna()
    return pair_4h, missing


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    s6 = load_s6_module()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pair_4h, missing = load_pair_4h(s6)
    print(f"Loaded {len(pair_4h)} pairs; missing: {missing}")

    per_pair = {}
    trades_a_all, trades_b_all = [], []
    violation_counts = {}

    for p, df in pair_4h.items():
        # Variant A: frozen research logic (imported, unmodified)
        sig_a = s6.generate_signal_mechanism(df)
        # Variant B: identical logic, causal swing availability
        sig_b = generate_signal_mechanism_causal(df, s6)

        trades_a = s6.simulate_with_risk_scaling(
            sig_a, p, s6.COST_SCENARIOS["base"], None)
        trades_b = s6.simulate_with_risk_scaling(
            sig_b, p, s6.COST_SCENARIOS["base"], None)

        trades_a_all.extend(trades_a)
        trades_b_all.extend(trades_b)

        _, _, raw_h, raw_l = compute_rolling_swing_levels_causal(
            df["close"].values, df["high"].values, df["low"].values, s6.LOOKBACK)

        a_recs, b_recs = signal_records(sig_a), signal_records(sig_b)
        per_pair[p] = {
            "signals_a": len(a_recs),
            "signals_b": len(b_recs),
            "diff": diff_signals(a_recs, b_recs, df.index, s6.LOOKBACK),
            "swing_series_divergence": swing_series_divergence(sig_a, sig_b),
            "unconfirmed_swing_signals_a": count_unconfirmed_usages(
                sig_a, raw_h, raw_l, s6.LOOKBACK),
            "metrics_a": summarize(trades_a, s6),
            "metrics_b": summarize(trades_b, s6),
        }
        violation_counts[p] = per_pair[p]["unconfirmed_swing_signals_a"]
        d = per_pair[p]["diff"]
        print(f"  {p}: sigA={d['total_a']} sigB={d['total_b']} "
              f"kept={d['kept_identical_bar_and_dir']} "
              f"delayed={d['delayed_within_lookback']} "
              f"lost={d['lost_no_b_equivalent']} "
              f"unconfirmed={per_pair[p]['unconfirmed_swing_signals_a']}")

    # Aggregate signal diff = sum of per-pair diffs (records are pair-local;
    # timestamps collide across pairs so global sets would be invalid)
    agg_keys = ("total_a", "total_b", "kept_identical_bar_and_dir",
                "delayed_within_lookback", "lost_no_b_equivalent", "b_only_new")
    agg_diff = {k: sum(per_pair[p]["diff"][k] for p in per_pair)
                for k in agg_keys} if per_pair else {}
    if agg_diff:
        agg_diff["affected_pct"] = round(
            100.0 * (agg_diff["delayed_within_lookback"]
                     + agg_diff["lost_no_b_equivalent"])
            / max(agg_diff["total_a"], 1), 2)

    results = {
        "experiment_id": EXPERIMENT_ID,
        "purpose": "Quantify impact of causal swing availability on frozen S6 config",
        "git_commit": git_commit(),
        "config": {
            "lookback": s6.LOOKBACK, "atr_period": s6.ATR_PERIOD,
            "atr_sl_mult": s6.ATR_SL_MULT, "rrr": s6.RRR,
            "max_hold_days": s6.MAX_HOLD_DAYS,
            "breakeven_ratio": s6.BREAKEVEN_RATIO,
            "cost_scenario": "base",
            "risk": "flat (risk_mults=None)",
            "pairs_loaded": sorted(pair_4h.keys()),
            "pairs_missing": missing,
        },
        "variant_definitions": {
            "A_research": "frozen S6 generate_signal_mechanism (imported unmodified)",
            "B_causal": "identical detection; swing usable only from bar j+lookback",
        },
        "aggregate": {
            "signal_diff": agg_diff,
            "unconfirmed_swing_signals_total_A": int(sum(violation_counts.values())),
            "metrics_A": summarize(trades_a_all, s6),
            "metrics_B": summarize(trades_b_all, s6),
            "periods_A": period_metrics(trades_a_all, s6, "A"),
            "periods_B": period_metrics(trades_b_all, s6, "B"),
        },
        "per_pair": per_pair,
    }

    with open(OUT_DIR / "S6C_causal_swing_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)

    ma, mb = results["aggregate"]["metrics_A"], results["aggregate"]["metrics_B"]
    lines = [
        f"# {EXPERIMENT_ID}: Causal Swing Lookahead Quantification",
        "",
        f"- Git commit: `{results['git_commit']}`",
        f"- Pairs loaded: {len(pair_4h)} | missing: {missing}",
        f"- Config: frozen S6 (lookback={s6.LOOKBACK}, atr={s6.ATR_PERIOD}, "
        f"slmult={s6.ATR_SL_MULT}, rrr={s6.RRR}), base costs, flat risk",
        "",
        "| Metric | A research | B causal |",
        "|---|---|---|",
        f"| Signals affected | {agg_diff.get('affected_pct')}% delayed/lost |"
        f" unconfirmed usage: {results['aggregate']['unconfirmed_swing_signals_total_A']} |",
        f"| Trades | {ma['n_trades']} | {mb['n_trades']} |",
        f"| Win rate | {ma['win_rate']} | {mb['win_rate']} |",
        f"| Profit factor | {ma['profit_factor']} | {mb['profit_factor']} |",
        f"| Expectancy (pip/trade) | {ma['avg_pnl_pips_expectancy']} | {mb['avg_pnl_pips_expectancy']} |",
        f"| Total net pnl (pip) | {ma['total_net_pnl_pips']} | {mb['total_net_pnl_pips']} |",
        f"| Max DD (R) | {ma['max_dd_r']} | {mb['max_dd_r']} |",
        "",
        "See JSON for per-pair and period breakdowns.",
    ]
    with open(OUT_DIR / "S6C_REPORT.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    print(json.dumps({"A": ma, "B": mb}, indent=2, default=str))
    print(f"\nSaved results to {OUT_DIR}")


if __name__ == "__main__":
    main()
