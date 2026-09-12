#!/usr/bin/env python3
"""
Validate shadow signal fidelity against S6C Variant B causal baseline.

Efficient batch comparison: precomputes swing/ATR series once per pair and
scans for breakout signals, then compares shadow production batch vs the
research causal batch (same logic as scripts/phase_s6_causal_swing_check.py).

Criteria per S7 Protocol §1: signal fidelity >=95% = PASS.

Usage:
  python scripts/validate_shadow_fidelity.py
  python scripts/validate_shadow_fidelity.py --pairs EUR/USD GBP/USD
  python scripts/validate_shadow_fidelity.py --json  # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import os
os.environ.setdefault("NESTQUANT_SKIP_LIVE_CHECK", "1")
os.environ.setdefault("NESTQUANT_SKIP_DASHBOARD_CHECK", "1")

import numpy as np
import pandas as pd

from nestquant.core.data.loader import DataLoader
from nestquant.core.tooling.indicators.atr import calculate_atr
from nestquant.core.tooling.indicators.swing import swing_high_series, swing_low_series

# Import S6C causal helpers without side-effects
import importlib.util

def _load_s6c_module():
    p = Path("scripts/phase_s6_causal_swing_check.py")
    if not p.exists():
        p = Path(__file__).parent / "phase_s6_causal_swing_check.py"
    spec = importlib.util.spec_from_file_location("s6c", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _shadow_batch_fast(df: pd.DataFrame, lookback=5, atr_period=14, sl_mult=2.0, rrr=3.5):
    """Fast O(n) shadow batch using precomputed series (matches ShadowCausalSignalGenerator)."""
    sh = swing_high_series(df, lookback)
    sl = swing_low_series(df, lookback)
    atr = calculate_atr(df, atr_period)
    close = df["close"].values
    sh_v = sh.values
    sl_v = sl.values
    atr_v = atr.values
    out = []
    warmup = lookback * 2 + atr_period + 2
    for i in range(warmup, len(df)):
        prev_sh = sh_v[i-1]
        prev_sl = sl_v[i-1]
        c = close[i]
        pc = close[i-1]
        a = atr_v[i]
        if np.isnan(prev_sh) or np.isnan(prev_sl) or np.isnan(a) or a <= 0:
            continue
        if pc <= prev_sh < c:
            out.append((df.index[i], "BUY", float(prev_sh), float(c), float(a)))
        elif pc >= prev_sl > c:
            out.append((df.index[i], "SELL", float(prev_sl), float(c), float(a)))
    return out

def _research_causal_batch_fast(df: pd.DataFrame, s6c_mod):
    """Fast research-causal batch using S6C numpy helpers but O(n) scan."""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    # Use S6C's causal swing helper (returns sh, sl, raw...)
    sh, sl, _, _ = s6c_mod.compute_rolling_swing_levels_causal(close, high, low, 5)
    # ATR via S6C's imported S6 module (Wilder)
    s6 = s6c_mod.load_s6_module()
    atr = s6.compute_atr_independent(high, low, close, 14)
    out = []
    warmup = 5 * 2 + 14 + 2
    for i in range(warmup, len(df)):
        prev_sh = sh[i-1]
        prev_sl = sl[i-1]
        c = close[i]
        pc = close[i-1]
        a = atr[i]
        if np.isnan(prev_sh) or np.isnan(prev_sl) or np.isnan(a) or a <= 0:
            continue
        if pc <= prev_sh < c:
            out.append((df.index[i], "BUY", float(prev_sh), float(c), float(a)))
        elif pc >= prev_sl > c:
            out.append((df.index[i], "SELL", float(prev_sl), float(c), float(a)))
    return out

def main():
    ap = argparse.ArgumentParser(description="Validate shadow fidelity vs Variant B")
    ap.add_argument("--pairs", nargs="*", default=None)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dl = DataLoader(data_dir=args.data_dir)
    pairs = args.pairs
    if pairs is None:
        # Default to 20 validated from S6C
        jpath = Path("research_data/s6c/S6C_causal_swing_results.json")
        if jpath.exists():
            try:
                pairs = json.loads(jpath.read_text())["config"]["pairs_loaded"]
            except Exception:
                pairs = None
        if not pairs:
            from nestquant.core.configuration.settings import get_config
            pairs = list(get_config().universe.all_pairs[:20])

    s6c = _load_s6c_module()

    per_pair = {}
    total_common = total_shadow = total_research = 0
    t0 = time.perf_counter()
    for pair in pairs:
        df = dl.load_pair(pair, timeframe=args.timeframe)
        if df is None or len(df) == 0:
            per_pair[pair] = {"error": "no data"}
            continue
        df = df.sort_index()
        shadow = _shadow_batch_fast(df)
        research = _research_causal_batch_fast(df, s6c)
        # Compare (timestamp, direction) sets
        s_set = set((ts, d) for ts, d, *_ in shadow)
        r_set = set((ts, d) for ts, d, *_ in research)
        common = len(s_set & r_set)
        fidelity = (common / max(len(r_set), 1)) * 100.0
        per_pair[pair] = {
            "research_signals": len(r_set),
            "shadow_signals": len(s_set),
            "common": common,
            "fidelity_pct": round(fidelity, 2),
            "shadow_only": len(s_set - r_set),
            "research_only": len(r_set - s_set),
        }
        total_common += common
        total_shadow += len(s_set)
        total_research += len(r_set)

    elapsed = time.perf_counter() - t0
    overall = (total_common / max(total_research, 1)) * 100.0
    verdict = "PASS" if overall >= 95.0 else ("WARN" if overall >= 90.0 else "FAIL")

    payload = {
        "baseline": "S6C-2026-001 Variant B (causal)",
        "timeframe": args.timeframe,
        "pairs": pairs,
        "total_research_signals": total_research,
        "total_shadow_signals": total_shadow,
        "common": total_common,
        "overall_fidelity_pct": round(overall, 2),
        "verdict": verdict,
        "elapsed_seconds": round(elapsed, 2),
        "per_pair": per_pair,
        "criteria": ">=95% PASS, 90-95% WARN, <90% FAIL per S7 Protocol §1",
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Overall fidelity: {overall:.2f}% ({total_common}/{total_research}) — {verdict}")
        print(f"Shadow total {total_shadow}, Research total {total_research}, elapsed {elapsed:.1f}s")
        for pair, r in per_pair.items():
            if "error" in r:
                print(f"  {pair}: ERROR {r['error']}")
            else:
                flag = "" if r["fidelity_pct"] >= 95 else " *"
                print(f"  {pair:10s} research={r['research_signals']:4d} shadow={r['shadow_signals']:4d} common={r['common']:4d} fidelity={r['fidelity_pct']:5.2f}%{flag}")

    sys.exit(0 if verdict == "PASS" else (1 if verdict == "WARN" else 2))

if __name__ == "__main__":
    main()
