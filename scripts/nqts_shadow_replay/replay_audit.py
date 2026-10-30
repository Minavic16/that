#!/usr/bin/env python3
"""NQTS post-first-9 signal shadow replay — ANALYSIS ONLY (read-only).

Counterfactual: if each signal after the first 9 had actually been executed
under the current NQTS execution/backtesting rules, what would have happened?

Rules implemented by REUSING unchanged, imported components:
- Fills/exits: frozen research execution core (ExecutionSimulator) —
  SL-before-TP ordering, half-spread + slippage entry, exit slippage,
  commission, risk-based sizing with 0.01 lot floor.
- Entry gates: production RiskGuard (constitution limits: 4 trades/day,
  3 concurrent, 0.15%/trade, 3% daily loss, 8% drawdown, 0.10 lots/pair,
  3.0 lots total) at the live runner's balance of 200, plus
  live_executor's one-position-per-pair rule.

Never contacts the broker/bridge. Never writes outside this directory.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from nestquant.core.contracts.execution_contracts import Direction, TradeIntent
from nestquant.core.tooling.indicators.session import is_active_session
from nestquant.production.execution.risk_guard import RiskGuard, RiskGuardConfig
from nestquant.research.shared.execution import (
    BacktestConfig,
    ExecutionSimulator,
    SignalIntent,
)

# --- safety: capture (never send) any risk-block notification -------------
import nestquant.production.notifications.signal_notifier as _sn

RISK_BLOCKS_CAPTURED: list[str] = []


def _capture_block(reason: str) -> bool:
    RISK_BLOCKS_CAPTURED.append(reason)
    return True


_sn.send_risk_block_alert = _capture_block
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
EV = HERE / "evidence"

INITIAL_BALANCE = 200.0          # LiveExecutionRunner default initial_balance
MAX_CONCURRENT = 3               # CONSTITUTION.max_concurrent_positions
SLIPPAGE_PIPS = 0.1              # frozen BacktestConfig default
COMMISSION_PER_LOT = 6.0         # frozen BacktestConfig default
SPREAD_MAX_PLAUSIBLE_PIPS = 5.0  # above this -> recorded tick spread is a
                                 # quote artifact; use frozen default 1.0p
FROZEN_FALLBACK_SPREAD_PIPS = 1.0
LABEL_CLOSE_OFFSET_H = 1         # true UTC close = recorded label + 1h
LABEL_OPEN_OFFSET_H = 3          # true UTC open  = recorded label - 3h
FIRST_9 = 9
MAX_HOLD_BARS = 42               # live_executor: MAX_HOLD_DAYS=7 * 6 bars/day


def p(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def proof_tol(pair: str) -> float:
    """Continuity/open proofs allow <=0.1 pip serialization rounding."""
    return pip_size(pair) / 10.0 + 1e-12


def grid_next(label: str) -> str:
    return (pd.Timestamp(label) + pd.Timedelta(hours=4)).isoformat()


def true_close(label: str) -> datetime:
    dt = pd.Timestamp(label) + pd.Timedelta(hours=LABEL_CLOSE_OFFSET_H)
    if dt.tzinfo is None:
        dt = dt.tz_localize(timezone.utc)
    return dt.to_pydatetime()


def true_open(label: str) -> datetime:
    dt = pd.Timestamp(label) - pd.Timedelta(hours=LABEL_OPEN_OFFSET_H)
    if dt.tzinfo is None:
        dt = dt.tz_localize(timezone.utc)
    return dt.to_pydatetime()


# --------------------------------------------------------------------------
# Evidence load
# --------------------------------------------------------------------------

def load_jsonl(name: str) -> list[dict]:
    return [json.loads(x) for x in (EV / name).read_text().splitlines() if x.strip()]


SIGNALS = load_jsonl("signals.jsonl")
ORDERS = {o["signal_id"]: o for o in load_jsonl("intended_orders.jsonl")}
BARS = load_jsonl("bars.jsonl")
STATE = json.loads((EV / "state.json").read_text())
METRICS = json.loads((EV / "metrics.json").read_text())
ZERO_ORDERS = json.loads((EV / "orders_submitted_count.json").read_text())

BARS_BY_PAIR: dict[str, dict[str, dict]] = {}
for _b in BARS:
    BARS_BY_PAIR.setdefault(_b["symbol"], {})[_b["timestamp"]] = _b


FX_MAP = {"EUR": "EUR/USD", "GBP": "GBP/USD", "AUD": "AUD/USD",
          "NZD": "NZD/USD", "CHF": "USD/CHF", "CAD": "USD/CAD",
          "JPY": "USD/JPY"}


def fx_rate_at(ccy: str, label: str) -> tuple[float, str, str]:
    """Return (rate_to_usd, fx_pair, rate_bar_label) using last bar <= label."""
    if ccy == "USD":
        return 1.0, "USD", "n/a"
    pair = FX_MAP[ccy]
    best = None
    for ts in BARS_BY_PAIR.get(pair, {}):
        if ts <= label and (best is None or ts > best):
            best = ts
    if best is None:
        raise SystemExit(f"no FX bar for {pair} at/before {label}")
    close = BARS_BY_PAIR[pair][best]["close"]
    if pair.endswith("/USD"):
        return close, pair, best
    return 1.0 / close, pair, best   # USD/CHF, USD/CAD, USD/JPY


def to_usd(amount: float, ccy: str, label: str) -> tuple[float, float, str, str]:
    r, fp, bl = fx_rate_at(ccy, label)
    return amount * r, r, fp, bl


def cycle_bar(pair: str, order_ts: str) -> Optional[dict]:
    ot = p(order_ts)
    hits = [
        b for b in BARS
        if b["symbol"] == pair
        and abs((p(b["receipt_timestamp"]) - ot).total_seconds()) < 3.0
    ]
    if len(hits) > 1:
        raise SystemExit(f"{pair}: ambiguous cycle bars ({len(hits)})")
    return hits[0] if hits else None


# --------------------------------------------------------------------------
# Signal records
# --------------------------------------------------------------------------

@dataclass
class Sig:
    idx: int
    population: str
    signal_id: str
    symbol: str
    direction: str
    entry: float
    sl: float
    tp: float
    atr: float
    record_ts: str
    order_ts: str
    bar_label: str
    spread_recorded_pips: float
    spread_used_pips: float
    spread_fallback: bool
    tick_bid: float
    tick_ask: float
    resolution: str
    warnings: list[str] = field(default_factory=list)


def resolve_signal_bar(sig: dict, order: dict) -> tuple[str, str, list[str]]:
    """Return (bar_label, method, warnings). Fail-closed."""
    warns: list[str] = []
    pair, sid = sig["symbol"], sig["signal_id"]
    order_t = p(order["timestamp"])
    cyc = cycle_bar(pair, order["timestamp"])
    ts = sig["timestamp"]
    if ts not in (None, "NaT"):
        label = ts
        if label not in BARS_BY_PAIR.get(pair, {}):
            raise SystemExit(f"{sid}: recorded signal bar {label} not in bars")
        dev = abs(BARS_BY_PAIR[pair][label]["open"] - sig["bar_open"])
        if dev > proof_tol(pair):
            raise SystemExit(
                f"{sid}: recorded-timestamp open-equality proof failed "
                f"dev={dev}")
        method = (f"recorded signal timestamp (in bars), "
                  f"open-equality proof dev={dev:g}")
        return label, method, warns
    if cyc is None:
        raise SystemExit(f"{sid}: NaT record but no cycle bar within 3s")
    label = grid_next(cyc["timestamp"])
    t0, t1 = pd.Timestamp(cyc["timestamp"]), pd.Timestamp(label)
    t = t0 + pd.Timedelta(hours=4)
    while t < t1:
        if t.weekday() >= 5:
            raise SystemExit(f"{sid}: grid crosses weekend — resolution unsafe")
        t += pd.Timedelta(hours=4)
    if label in BARS_BY_PAIR[pair]:
        dev = abs(BARS_BY_PAIR[pair][label]["open"] - sig["bar_open"])
        if dev > proof_tol(pair):
            raise SystemExit(f"{sid}: open-equality proof failed for {label} dev={dev}")
        method = (f"cycle {cyc['timestamp']} +4h grid + open-equality proof "
                  f"dev={dev:g}")
    else:
        dev = abs(cyc["close"] - sig["bar_open"])
        if dev > proof_tol(pair):
            raise SystemExit(f"{sid}: continuity proof failed dev={dev}")
        method = (f"cycle {cyc['timestamp']} +4h grid + continuity proof "
                  f"(bar incomplete) dev={dev:g}")
        warns.append("signal_bar_not_completed_at_snapshot")
    return label, method, warns


def build_population() -> list[Sig]:
    out: list[Sig] = []
    for i, sig in enumerate(SIGNALS, 1):
        sid = sig["signal_id"]
        if sid not in ORDERS:
            raise SystemExit(f"{sid}: missing intended order")
        order = ORDERS[sid]
        pair = sig["symbol"]
        label, method, warns = resolve_signal_bar(sig, order)
        cyc = cycle_bar(pair, order["timestamp"])
        if cyc is None:
            raise SystemExit(f"{sid}: no cycle bar")
        unit = pip_size(pair)
        rec_spread = float(cyc["spread"]) / unit
        used, fallback = rec_spread, False
        if rec_spread > SPREAD_MAX_PLAUSIBLE_PIPS:
            used = FROZEN_FALLBACK_SPREAD_PIPS
            fallback = True
            warns.append(
                f"recorded_tick_spread_{rec_spread:.1f}pips_implausible"
                f"_frozen_default_{FROZEN_FALLBACK_SPREAD_PIPS}pips_used"
            )
        if float(order["spread_at_submission"]) / unit > SPREAD_MAX_PLAUSIBLE_PIPS:
            warns.append("intended_order_spread_also_implausible_same_artifact")
        if cyc.get("atr_14") is None:
            warns.append("bar_atr_14_missing_at_cycle")
        if sig["timestamp"] in (None, "NaT"):
            warns.append("record_timestamp_NaT")
        if abs((p(order["timestamp"]) - true_open(label)).total_seconds()) > 60:
            warns.append(
                f"late_entry_{(p(order['timestamp']) - true_open(label)).total_seconds()/60:.0f}min_after_bar_open"
            )
        out.append(Sig(
            idx=i, population="A" if i <= FIRST_9 else "B",
            signal_id=sid, symbol=pair, direction=sig["direction"],
            entry=float(sig["expected_entry"]), sl=float(sig["expected_sl"]),
            tp=float(sig["expected_tp"]), atr=float(sig["atr_at_signal"]),
            record_ts=str(sig["timestamp"]), order_ts=order["timestamp"],
            bar_label=label, spread_recorded_pips=rec_spread,
            spread_used_pips=used, spread_fallback=fallback,
            tick_bid=float(cyc["bid"]), tick_ask=float(cyc["ask"]),
            resolution=method, warnings=warns,
        ))
    clocks = [p(s.order_ts) for s in out]
    if clocks != sorted(clocks):
        raise SystemExit("record order not chronological — population split unsafe")
    return out


# --------------------------------------------------------------------------
# Replay engine
# --------------------------------------------------------------------------

@dataclass
class OpenRec:
    sig: Sig
    trade: Any
    first_check_label: str
    fill: float
    lot: float
    risk_dollars: float
    spread_pips: float
    entry_true: datetime
    be_armed: bool = False
    be_at: Optional[str] = None


@dataclass
class ClosedRec:
    sig: Sig
    fill: float
    lot: float
    risk_dollars: float
    spread_pips: float
    entry_true: datetime
    exit_label: str
    exit_true: datetime
    exit_reason: str
    exit_price: float
    pnl: float
    hold_hours: float
    held_bars_label: float
    r_multiple: float
    data_quality: str
    quality_notes: list[str]
    flags: dict
    mfe: float
    mae: float
    mfe_pips: float
    mae_pips: float
    pnl_usd: float = 0.0
    fx_pair: str = "USD"
    fx_rate: float = 1.0
    fx_bar_label: str = "n/a"


def pair_bars(s: Sig) -> list[dict]:
    return sorted(BARS_BY_PAIR.get(s.symbol, {}).values(), key=lambda b: b["timestamp"])


def grid_labels(start: str, end: str) -> list[str]:
    out, t = [], pd.Timestamp(start) + pd.Timedelta(hours=4)
    e = pd.Timestamp(end)
    while t < e:
        out.append(t.isoformat())
        t += pd.Timedelta(hours=4)
    return out


def run_pass(
    sigs: list[Sig],
    *,
    name: str,
    max_concurrent: int = MAX_CONCURRENT,
    session_gate: bool = False,
    entry_bar_checked: bool = True,
    spread_mode: str = "sane",     # sane | tick | zero
    feed_risk: bool = True,        # False = as-wired current runner (inert gates)
) -> dict:
    cfg = BacktestConfig(
        initial_balance=INITIAL_BALANCE,
        risk_per_trade=0.0015,
        max_open_trades=10 ** 6,   # concurrency enforced via RiskGuard instead
        commission_per_lot=COMMISSION_PER_LOT,
        spread_pips=FROZEN_FALLBACK_SPREAD_PIPS,
        slippage_pips=SLIPPAGE_PIPS,
    )
    sim = ExecutionSimulator(cfg)
    risk = RiskGuard(RiskGuardConfig(
        account_balance=INITIAL_BALANCE,
        max_concurrent_positions=max_concurrent,
    ))

    # ---- events ----
    events: list[tuple] = []
    for s in sigs:
        events.append((p(s.order_ts), 1, "entry", s.symbol, s))
    seen: set[tuple[str, str]] = set()
    for s in sigs:
        for b in pair_bars(s):
            key = (s.symbol, b["timestamp"])
            if key in seen:
                continue
            seen.add(key)
            events.append((true_close(b["timestamp"]), 0, "check", s.symbol, b))
    events.sort(key=lambda e: (e[0], e[1]))

    closed: list[ClosedRec] = []
    suppressed: list[dict] = []
    rejected: list[dict] = []
    session_blocked: list[dict] = []
    open_map: dict[str, OpenRec] = {}
    opened: list[OpenRec] = []
    cum_realized = 0.0
    usd_cum = 0.0
    usd_peak = INITIAL_BALANCE
    usd_max_dd = 0.0
    usd_max_dd_pct = 0.0
    usd_dd_period: dict = {}
    cur_date = None
    equity_curve: list[dict] = []
    peak, max_dd, max_dd_pct = INITIAL_BALANCE, 0.0, 0.0
    peak_time: Optional[datetime] = None
    dd_period: dict = {}
    in_dd_from: Optional[datetime] = None
    max_conc_seen = 0
    max_exposure = 0.0
    overlaps: list[dict] = []
    both_touch: list[dict] = []

    def upd() -> None:
        if feed_risk:
            risk.update_positions(
                [{"symbol": t.trade.pair, "volume": t.trade.lot_size}
                 for t in open_map.values()]
            )

    for ev_time, _ord, kind, pair, payload in events:
        d = ev_time.date()
        if cur_date is None:
            cur_date = d
        elif d != cur_date:
            if feed_risk:
                risk.reset_daily()
            cur_date = d

        if kind == "check":
            bar = payload
            rec = open_map.get(pair)
            if rec is not None and bar["timestamp"] < rec.first_check_label:
                continue
            if session_gate and not is_active_session(pd.Timestamp(bar["timestamp"])):
                continue
            if rec is not None:
                st = rec.trade
                hit_sl = ((st.direction == "BUY" and bar["low"] <= st.sl_price)
                          or (st.direction == "SELL" and bar["high"] >= st.sl_price))
                hit_tp = ((st.direction == "BUY" and bar["high"] >= st.tp_price)
                          or (st.direction == "SELL" and bar["low"] <= st.tp_price))
                if hit_sl and hit_tp:
                    both_touch.append({
                        "signal_id": rec.sig.signal_id, "pair": pair,
                        "bar": bar["timestamp"],
                        "frozen_order_exit": "sl", "live_executor_order_exit": "tp",
                    })
                if not rec.be_armed:
                    be = 0.8 * rec.sig.atr
                    if ((st.direction == "BUY" and bar["high"] >= rec.sig.entry + be)
                            or (st.direction == "SELL" and bar["low"] <= rec.sig.entry - be)):
                        rec.be_armed = True
                        rec.be_at = bar["timestamp"]
            df = pd.DataFrame(
                [{"open": bar["open"], "high": bar["high"],
                  "low": bar["low"], "close": bar["close"]}],
                index=pd.DatetimeIndex([pd.Timestamp(bar["timestamp"])], tz="UTC"),
            )
            for t in sim.check_exits(pair, df):
                rec = open_map.pop(pair)
                upd()
                cum_realized += t.pnl
                if feed_risk:
                    risk.record_trade_result(
                        pnl=t.pnl, equity=INITIAL_BALANCE + cum_realized,
                        slippage_pips=SLIPPAGE_PIPS,
                    )
                notes: list[str] = []
                missing = [lbl for lbl in grid_labels(rec.sig.bar_label, bar["timestamp"])
                           if pd.Timestamp(lbl).weekday() < 5
                           and lbl not in BARS_BY_PAIR[rec.sig.symbol]]
                quality = "COMPLETE" if not missing else "PARTIAL"
                if missing:
                    notes.append(f"missing_grid_bars={len(missing)}")
                mfe = mae = 0.0
                for b2 in pair_bars(rec.sig):
                    if b2["timestamp"] < rec.sig.bar_label:
                        continue
                    if b2["timestamp"] > bar["timestamp"]:
                        break
                    if t.direction == "BUY":
                        mfe = max(mfe, b2["high"] - rec.fill)
                        mae = max(mae, rec.fill - b2["low"])
                    else:
                        mfe = max(mfe, rec.fill - b2["low"])
                        mae = max(mae, b2["high"] - rec.fill)
                hold_h = (true_close(bar["timestamp"]) - rec.entry_true).total_seconds() / 3600
                held_bars = ((pd.Timestamp(bar["timestamp"]) - pd.Timestamp(rec.sig.bar_label))
                             .total_seconds() / (4 * 3600))
                flags = {
                    "be_armed_before_exit": rec.be_armed,
                    "be_armed_at_bar": rec.be_at,
                    "held_bars_label": held_bars,
                    "max_hold_would_preempt": held_bars >= MAX_HOLD_BARS,
                    "spread_fallback_used": rec.sig.spread_fallback,
                    "recorded_spread_pips": rec.sig.spread_recorded_pips,
                    "late_entry": "late_entry" in " ".join(rec.sig.warnings),
                }
                ccy = rec.sig.symbol.split("/")[1]
                pnl_usd, fx_r, fx_p, fx_b = to_usd(t.pnl, ccy, bar["timestamp"])
                usd_cum += pnl_usd
                closed.append(ClosedRec(
                    sig=rec.sig, fill=rec.fill, lot=t.lot_size,
                    risk_dollars=rec.risk_dollars, spread_pips=rec.spread_pips,
                    entry_true=rec.entry_true, exit_label=bar["timestamp"],
                    exit_true=true_close(bar["timestamp"]),
                    exit_reason=t.exit_reason, exit_price=t.exit_price,
                    pnl=t.pnl, hold_hours=hold_h, held_bars_label=held_bars,
                    r_multiple=(t.pnl / rec.risk_dollars) if rec.risk_dollars else float("nan"),
                    data_quality=quality, quality_notes=notes, flags=flags,
                    mfe=mfe, mae=mae,
                    mfe_pips=mfe / pip_size(rec.sig.symbol),
                    mae_pips=mae / pip_size(rec.sig.symbol),
                    pnl_usd=pnl_usd, fx_pair=fx_p, fx_rate=fx_r,
                    fx_bar_label=fx_b,
                ))
                bal_usd = INITIAL_BALANCE + usd_cum
                if bal_usd > usd_peak:
                    usd_peak = bal_usd
                dd_u = usd_peak - bal_usd
                dd_up = dd_u / usd_peak * 100.0 if usd_peak > 0 else 0.0
                if dd_up > usd_max_dd_pct:
                    usd_max_dd, usd_max_dd_pct = dd_u, dd_up
                    usd_dd_period = {"peak_usd": round(usd_peak, 2),
                                     "trough_at": true_close(bar["timestamp"]).isoformat(),
                                     "trough_usd": round(bal_usd, 2)}
                bal = INITIAL_BALANCE + cum_realized
                if bal > peak:
                    peak, peak_time = bal, true_close(bar["timestamp"])
                    in_dd_from = None
                dd = peak - bal
                dd_pct = dd / peak * 100.0 if peak > 0 else 0.0
                if dd > 0 and in_dd_from is None:
                    in_dd_from = true_close(bar["timestamp"])
                if dd_pct > max_dd_pct:
                    max_dd, max_dd_pct = dd, dd_pct
                    dd_period = {
                        "peak_balance_at": peak_time.isoformat() if peak_time else "start",
                        "trough_at": true_close(bar["timestamp"]).isoformat(),
                        "dd_started_at": in_dd_from.isoformat() if in_dd_from else None,
                    }
                equity_curve.append({
                    "t": true_close(bar["timestamp"]).isoformat(),
                    "event": f"exit_{t.exit_reason}", "pair": t.pair,
                    "pnl": round(t.pnl, 2), "balance": round(bal, 2),
                    "pnl_usd": round(pnl_usd, 2),
                    "balance_usd": round(bal_usd, 2),
                    "open": len(open_map),
                })

        else:  # entry
            s: Sig = payload
            if s.symbol in open_map:
                suppressed.append({"signal_id": s.signal_id, "idx": s.idx,
                                   "pair": s.symbol, "reason": "pair_occupied"})
                continue
            if session_gate and not is_active_session(pd.Timestamp(s.bar_label)):
                session_blocked.append({"signal_id": s.signal_id, "idx": s.idx,
                                        "pair": s.symbol, "label": s.bar_label})
                continue
            upd()
            intent = TradeIntent(
                pair=s.symbol,
                direction=Direction.BUY if s.direction == "BUY" else Direction.SELL,
                signal_strength=1.0,
                entry_price=s.entry, stop_loss=s.sl, take_profit=s.tp,
                strategy="breakout", policy_version="constitution-1.0.0",
                timestamp=p(s.order_ts),
            )
            decision = risk.evaluate(intent)
            if not decision.approved:
                rejected.append({"signal_id": s.signal_id, "idx": s.idx,
                                 "pair": s.symbol, "reason": decision.reason})
                continue
            # fill basis by mode (RiskGuard intent always uses expected_entry,
            # matching live_executor which builds TradeIntent from expected_entry)
            if spread_mode == "tick":
                fill_basis = s.tick_ask if s.direction == "BUY" else s.tick_bid
                cfg.spread_pips, cfg.slippage_pips = 0.0, 0.0
            elif spread_mode == "zero":
                fill_basis = s.entry
                cfg.spread_pips, cfg.slippage_pips = 0.0, 0.0
            else:
                fill_basis = s.entry
                cfg.spread_pips = s.spread_used_pips
                cfg.slippage_pips = SLIPPAGE_PIPS
            t = sim.open_trade(
                SignalIntent(pair=s.symbol, direction=s.direction, strength=1.0,
                             entry_price=fill_basis, sl_price=s.sl, tp_price=s.tp),
                pd.Timestamp(s.order_ts),
            )
            if t is None:
                rejected.append({"signal_id": s.signal_id, "idx": s.idx,
                                 "pair": s.symbol, "reason": "simulator_open_failed"})
                continue
            if abs(t.lot_size - 0.01) > 1e-9:
                raise SystemExit(f"{s.signal_id}: lot {t.lot_size} != intended 0.01")
            rec = OpenRec(
                sig=s, trade=t,
                first_check_label=s.bar_label if entry_bar_checked else grid_next(s.bar_label),
                fill=t.entry_price, lot=t.lot_size,
                risk_dollars=abs(t.entry_price - t.sl_price) * 100000 * t.lot_size,
                spread_pips=(0.0 if spread_mode in ("tick", "zero") else s.spread_used_pips),
                entry_true=p(s.order_ts),
            )
            open_map[s.symbol] = rec
            opened.append(rec)
            upd()
            if len(open_map) > max_conc_seen:
                max_conc_seen = len(open_map)
            max_exposure = max(max_exposure, sum(r.lot for r in open_map.values()))
            if len(open_map) >= 2:
                overlaps.append({
                    "t": s.order_ts,
                    "new": f"{s.symbol} {s.direction}",
                    "open": [f"{r.sig.symbol} {r.sig.direction}" for r in open_map.values()],
                })
            equity_curve.append({
                "t": s.order_ts, "event": "entry", "pair": s.symbol,
                "pnl": 0.0, "balance": round(INITIAL_BALANCE + cum_realized, 2),
                "pnl_usd": 0.0, "balance_usd": round(INITIAL_BALANCE + usd_cum, 2),
                "open": len(open_map),
            })

    # open at observation end
    open_end: list[dict] = []
    last_bar_true = max(true_close(b["timestamp"]) for b in BARS)
    for pair, rec in open_map.items():
        s = rec.sig
        bars = [b for b in pair_bars(s) if b["timestamp"] >= s.bar_label]
        last = bars[-1] if bars else None
        unreal = None
        unreal_usd = None
        fx_info = ("USD", 1.0, "n/a")
        if last is not None:
            if s.direction == "BUY":
                unreal = (last["close"] - rec.fill) * rec.lot * 100000 - COMMISSION_PER_LOT * rec.lot
            else:
                unreal = (rec.fill - last["close"]) * rec.lot * 100000 - COMMISSION_PER_LOT * rec.lot
            ccy = s.symbol.split("/")[1]
            unreal_usd, fr, fp, fb = to_usd(unreal, ccy, last["timestamp"])
            fx_info = (fp, fr, fb)
        n_checks = len([b for b in bars if b["timestamp"] >= rec.first_check_label])
        held_open = ((pd.Timestamp(last["timestamp"]) - pd.Timestamp(s.bar_label))
                     .total_seconds() / (4 * 3600)) if last is not None else 0.0
        open_end.append({
            "signal_id": s.signal_id, "idx": s.idx, "pair": s.symbol,
            "direction": s.direction, "entry_bar": s.bar_label,
            "fill": rec.fill, "lot": rec.lot,
            "unrealized": round(unreal, 4) if unreal is not None else None,
            "unrealized_usd": round(unreal_usd, 4) if unreal_usd is not None else None,
            "fx": {"pair": fx_info[0], "rate": fx_info[1], "bar": fx_info[2]},
            "mark_bar": last["timestamp"] if last else None,
            "exit_check_bars_seen": n_checks,
            "held_bars_label": held_open,
            "max_hold_would_preempt": held_open >= MAX_HOLD_BARS,
            "be_armed": rec.be_armed, "be_armed_at": rec.be_at,
            "status": "OPEN AT OBSERVATION END",
        })

    outcomes = []
    for s in sigs:
        c = next((x for x in closed if x.sig.signal_id == s.signal_id), None)
        o = next((x for x in open_end if x["signal_id"] == s.signal_id), None)
        sup = next((x for x in suppressed if x["signal_id"] == s.signal_id), None)
        rej = next((x for x in rejected if x["signal_id"] == s.signal_id), None)
        blk = next((x for x in session_blocked if x["signal_id"] == s.signal_id), None)
        if c:
            outcomes.append({"idx": s.idx, "signal_id": s.signal_id,
                             "status": "CLOSED", "exit": c.exit_reason,
                             "pnl": round(c.pnl, 4),
                             "pnl_usd": round(c.pnl_usd, 4),
                             "R": round(c.r_multiple, 3),
                             "dq": c.data_quality})
        elif o:
            outcomes.append({"idx": s.idx, "signal_id": s.signal_id,
                             "status": "OPEN AT OBSERVATION END",
                             "unrealized": o["unrealized"],
                             "unrealized_usd": o["unrealized_usd"],
                             "dq": "OPEN"})
        elif sup:
            outcomes.append({"idx": s.idx, "signal_id": s.signal_id,
                             "status": "SUPPRESSED", "reason": "pair_occupied"})
        elif blk:
            outcomes.append({"idx": s.idx, "signal_id": s.signal_id,
                             "status": "BLOCKED", "reason": "session_gate"})
        elif rej:
            outcomes.append({"idx": s.idx, "signal_id": s.signal_id,
                             "status": "NOT_OPENED", "reason": rej["reason"]})
        else:
            outcomes.append({"idx": s.idx, "signal_id": s.signal_id,
                             "status": "UNKNOWN"})

    return {
        "name": name, "max_concurrent_cfg": max_concurrent,
        "session_gate": session_gate, "entry_bar_checked": entry_bar_checked,
        "spread_mode": spread_mode, "feed_risk": feed_risk,
        "closed": closed, "open_at_end": open_end,
        "suppressed": suppressed, "rejected": rejected,
        "session_blocked": session_blocked, "both_touch": both_touch,
        "equity_curve": equity_curve, "max_dd": max_dd, "max_dd_pct": max_dd_pct,
        "dd_period": dd_period, "max_conc_seen": max_conc_seen,
        "max_exposure": max_exposure, "overlaps": overlaps,
        "final_balance": INITIAL_BALANCE + cum_realized,
        "final_balance_usd": INITIAL_BALANCE + usd_cum,
        "usd_max_dd": usd_max_dd,
        "usd_max_dd_pct": usd_max_dd_pct,
        "usd_dd_period": usd_dd_period,
        "last_market_close": last_bar_true.isoformat(),
        "outcomes": outcomes,
    }


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def stats(res: dict) -> dict:
    cl: list[ClosedRec] = res["closed"]
    pnls = [c.pnl for c in cl]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    n = len(cl)
    gp, gl = sum(wins), abs(sum(losses))
    ordered = sorted(pnls, reverse=True)
    total = sum(pnls)
    med = lambda a: float(pd.Series(a).median()) if a else None

    def top_share(k: int, base: Optional[float]) -> Optional[float]:
        if base is None or base <= 0 or not pnls:
            return None
        return round(sum(ordered[:k]) / base * 100.0, 2)

    mw = ml = cw = cl2 = 0
    for x in pnls:
        if x > 0:
            cw += 1; cl2 = 0
        elif x < 0:
            cl2 += 1; cw = 0
        else:
            cw = cl2 = 0
        mw, ml = max(mw, cw), max(ml, cl2)
    rs = [c.r_multiple for c in cl]
    by_ccy: dict[str, float] = {}
    for c in cl:
        ccy = c.sig.symbol.split("/")[1]
        by_ccy[ccy] = by_ccy.get(ccy, 0.0) + c.pnl
    pnls_usd = [c.pnl_usd for c in cl]
    wins_u = [x for x in pnls_usd if x > 0]
    losses_u = [x for x in pnls_usd if x < 0]
    total_u = sum(pnls_usd)
    gp_u, gl_u = sum(wins_u), abs(sum(losses_u))
    ordered_u = sorted(pnls_usd, reverse=True)

    def top_share_u(k: int, base: Optional[float]) -> Optional[float]:
        if base is None or base <= 0 or not pnls_usd:
            return None
        return round(sum(ordered_u[:k]) / base * 100.0, 2)

    from collections import Counter
    reasons = Counter(c.exit_reason for c in cl)
    return {
        "closed_trades": n,
        "exit_reason_counts": dict(reasons),
        "net_pnl_by_quote_currency": {k: round(v, 2) for k, v in sorted(by_ccy.items())},
        "net_pnl_usd": round(total_u, 2),
        "return_pct_on_200_usd": round(total_u / INITIAL_BALANCE * 100, 3),
        "final_balance_usd": round(res["final_balance_usd"], 2),
        "max_drawdown_usd_conv": round(res["usd_max_dd"], 2),
        "max_drawdown_pct_usd": round(res["usd_max_dd_pct"], 3),
        "drawdown_period_usd": res["usd_dd_period"],
        "avg_win_usd": round(gp_u / len(wins_u), 3) if wins_u else None,
        "avg_loss_usd": round(-gl_u / len(losses_u), 3) if losses_u else None,
        "median_trade_usd": (float(pd.Series(pnls_usd).median()) if pnls_usd else None),
        "expectancy_usd": round(total_u / n, 3) if n else None,
        "payoff_ratio_usd": (round((gp_u / len(wins_u)) / (gl_u / len(losses_u)), 3)
                             if wins_u and losses_u else None),
        "top1_share_net_usd_pct": top_share_u(1, total_u),
        "top2_share_net_usd_pct": top_share_u(2, total_u),
        "top3_share_net_usd_pct": top_share_u(3, total_u),
        "top1_share_gross_usd_pct": top_share_u(1, gp_u),
        "top3_share_gross_usd_pct": top_share_u(3, gp_u),
        "open_unrealized_usd_indicative": round(
            sum(o["unrealized_usd"] for o in res["open_at_end"]
                if o["unrealized_usd"] is not None), 2),
        "open_at_observation_end": len(res["open_at_end"]),
        "suppressed_pair_occupied": len(res["suppressed"]),
        "not_opened_risk_gate": len(res["rejected"]),
        "session_blocked": len(res["session_blocked"]),
        "total_net_pnl": round(total, 2),
        "return_pct_on_200": round(total / INITIAL_BALANCE * 100, 3),
        "final_balance": round(res["final_balance"], 2),
        "win_rate_closed_pct": round(len(wins) / n * 100, 2) if n else None,
        "profit_factor": (round(gp / gl, 3) if gl else (float("inf") if gp > 0 else None)),
        "expectancy_per_trade": round(total / n, 3) if n else None,
        "avg_win": round(gp / len(wins), 3) if wins else None,
        "avg_loss": round(-gl / len(losses), 3) if losses else None,
        "median_trade": med(pnls),
        "median_winner": med(wins),
        "median_loser": (-med([-x for x in losses])) if losses else None,
        "largest_win": round(max(pnls), 3) if pnls else None,
        "largest_loss": round(min(pnls), 3) if pnls else None,
        "payoff_ratio": (round((gp / len(wins)) / (gl / len(losses)), 3)
                         if wins and losses else None),
        "avg_hold_hours": round(sum(c.hold_hours for c in cl) / n, 2) if n else None,
        "avg_R": round(sum(rs) / len(rs), 3) if rs else None,
        "max_drawdown_usd": round(res["max_dd"], 2),
        "max_drawdown_pct": round(res["max_dd_pct"], 3),
        "drawdown_period": res["dd_period"],
        "max_win_streak": mw, "max_loss_streak": ml,
        "max_simultaneous_positions": res["max_conc_seen"],
        "max_simultaneous_exposure_lots": res["max_exposure"],
        "top1_share_net_pct": top_share(1, total),
        "top2_share_net_pct": top_share(2, total),
        "top3_share_net_pct": top_share(3, total),
        "top1_share_gross_pct": top_share(1, gp),
        "top2_share_gross_pct": top_share(2, gp),
        "top3_share_gross_pct": top_share(3, gp),
        "losing_trade_share_pct": round(len(losses) / n * 100, 2) if n else None,
        "same_bar_sl_and_tp_touches": len(res["both_touch"]),
        "last_market_close_utc": res["last_market_close"],
    }


# --------------------------------------------------------------------------
# S5: TP-first alternate recount (live_executor checks TP before SL)
# --------------------------------------------------------------------------

def s5_delta(primary: dict) -> dict:
    rows = []
    for item in primary["both_touch"]:
        c = next((x for x in primary["closed"]
                  if x.sig.signal_id == item["signal_id"]), None)
        if c is None:
            continue
        slip = SLIPPAGE_PIPS * 0.0001
        tp_fill = c.sig.tp + slip  # frozen convention: TP exits get +slippage
        if c.sig.direction == "BUY":
            pnl_tp = (tp_fill - c.fill) * c.lot * 100000 - COMMISSION_PER_LOT * c.lot
        else:
            pnl_tp = (c.fill - tp_fill) * c.lot * 100000 - COMMISSION_PER_LOT * c.lot
        rows.append({
            "signal_id": item["signal_id"], "bar": item["bar"],
            "frozen_sl_first_pnl": round(c.pnl, 2),
            "live_tp_first_pnl": round(pnl_tp, 2),
            "delta": round(pnl_tp - c.pnl, 2),
        })
    return {"count": len(rows), "affected_trades": rows,
            "net_delta_if_tp_first": round(sum(r["delta"] for r in rows), 2)}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    verify = "--verify" in argv
    sigs = build_population()
    pop_a = [s for s in sigs if s.population == "A"]
    pop_b = [s for s in sigs if s.population == "B"]

    print("=" * 78)
    print("POPULATION RESOLUTION (evidence: signals.jsonl + intended_orders + bars)")
    print("=" * 78)
    for s in sigs:
        print(f"  [{s.population}] #{s.idx:2d} {s.order_ts[:19]} {s.symbol:8s} "
              f"{s.direction:4s} B_label={s.bar_label} "
              f"spread_rec={s.spread_recorded_pips:6.2f}p used={s.spread_used_pips:4.1f}p "
              f"{'FALLBACK' if s.spread_fallback else ''}")
        if s.warnings:
            for w in s.warnings:
                print(f"        warn: {w}")
    print(f"\n  A (excluded, first {FIRST_9}): n={len(pop_a)} "
          f"{pop_a[0].order_ts} .. {pop_a[-1].order_ts}")
    print(f"  B (analyzed): n={len(pop_b)} "
          f"{pop_b[0].order_ts} .. {pop_b[-1].order_ts}")
    print(f"  B bars: {pop_b[0].bar_label} .. {pop_b[-1].bar_label}")
    print(f"  B pairs: {sorted({s.symbol for s in pop_b})}")
    print(f"  B counts: BUY={sum(1 for s in pop_b if s.direction=='BUY')} "
          f"SELL={sum(1 for s in pop_b if s.direction=='SELL')}")
    print(f"  state counters: {STATE.get('counters')}")
    print(f"  orders_submitted_count: {ZERO_ORDERS}")
    print(f"  risk-block notifications captured (should be 0 real sends): patched")

    runs: dict[str, dict] = {}
    runs["primary"] = run_pass(pop_b, name="primary: constitution gates + 1/pair, "
                                           "frozen fills, entry bar checked")
    runs["S1_session"] = run_pass(pop_b, name="S1: research-engine session gate "
                                              "(entries + exit checks)",
                                  session_gate=True)
    runs["S2_maxopen1"] = run_pass(pop_b, name="S2: max_open_trades=1 "
                                               "(frozen BacktestConfig default)",
                                   max_concurrent=1)
    runs["S3_no_entry_bar"] = run_pass(pop_b, name="S3: entry bar excluded from "
                                                   "exit checks (frozen index rule)",
                                       entry_bar_checked=False)
    runs["S7_tick_fill"] = run_pass(pop_b, name="S7: live market-order fill at "
                                                "cycle tick (ask/bid), zero cost",
                                    spread_mode="tick")
    runs["S8_zero_cost"] = run_pass(pop_b, name="S8: fill at requested "
                                                "expected_entry, zero cost",
                                    spread_mode="zero")
    runs["S9_as_wired"] = run_pass(pop_b, name="S9: RiskGuard as currently wired in "
                                               "live runner (stateful gates inert)",
                                   feed_risk=False)
    runs["S6_interleave_AB"] = run_pass(sigs, name="S6: A+B interleave (budget "
                                                   "interaction between populations)")
    runs["A_reference"] = run_pass(pop_a, name="Population A reference replay "
                                               "(same rules as primary)")

    summaries = {k: stats(v) for k, v in runs.items()}

    if verify:
        print("\n--verify: rerunning all passes for determinism ...")
        for k, v in runs.items():
            v2 = run_pass(
                pop_b if k != "A_reference" and k != "S6_interleave_AB"
                else (pop_a if k == "A_reference" else sigs),
                name=v["name"], max_concurrent=v["max_concurrent_cfg"],
                session_gate=v["session_gate"],
                entry_bar_checked=v["entry_bar_checked"],
                spread_mode=v["spread_mode"], feed_risk=v["feed_risk"],
            )
            a = json.dumps(v["outcomes"], sort_keys=True, default=str)
            b = json.dumps(v2["outcomes"], sort_keys=True, default=str)
            if a != b:
                print(f"DETERMINISM FAILURE in {k}")
                return 2
        print("determinism: OK (all passes identical on rerun)")

    # ---- ledger ----
    primary, a_ref = runs["primary"], runs["A_reference"]
    rows = []
    for s in sigs:
        src = primary if s.population == "B" else a_ref
        c = next((x for x in src["closed"] if x.sig.signal_id == s.signal_id), None)
        o = next((x for x in src["open_at_end"] if x["signal_id"] == s.signal_id), None)
        sup = next((x for x in src["suppressed"] if x["signal_id"] == s.signal_id), None)
        rej = next((x for x in src["rejected"] if x["signal_id"] == s.signal_id), None)
        row: dict[str, Any] = {
            "n": s.idx, "population": s.population, "signal_id": s.signal_id,
            "signal_time_record": s.record_ts,
            "signal_time_order_utc": s.order_ts,
            "signal_bar_label": s.bar_label, "pair": s.symbol, "dir": s.direction,
            "entry_requested": s.entry, "sl": s.sl, "tp": s.tp, "atr_at_signal": s.atr,
            "lot": 0.01,
            "spread_recorded_pips": round(s.spread_recorded_pips, 3),
            "spread_used_pips": s.spread_used_pips,
            "source": "logs/shadow_live/{signals,intended_orders}.jsonl + bars.jsonl",
            "resolution": s.resolution, "warnings": s.warnings,
        }
        if c:
            row.update({
                "status": "HYPOTHETICAL_TRADE_CLOSED",
                "entry_true_utc": c.entry_true.isoformat(),
                "entry_fill": round(c.fill, 6),
                "exit_bar": c.exit_label, "exit_true_utc": c.exit_true.isoformat(),
                "exit_reason": c.exit_reason,
                "exit_price": round(c.exit_price, 6),
                "net_pnl": round(c.pnl, 4),
                "net_pnl_usd_est": round(c.pnl_usd, 4),
                "fx": {"pair": c.fx_pair, "rate": c.fx_rate, "bar": c.fx_bar_label},
                "R": round(c.r_multiple, 3),
                "duration_hours": round(c.hold_hours, 2),
                "held_bars_label": c.held_bars_label,
                "mfe_pips": round(c.mfe_pips, 1),
                "mae_pips": round(c.mae_pips, 1),
                "data_quality": c.data_quality,
                "quality_notes": c.quality_notes,
                "flags": c.flags,
            })
        elif o:
            row.update({
                "status": "OPEN AT OBSERVATION END",
                "entry_fill": round(o["fill"], 6),
                "unrealized_pnl_indicative": o["unrealized"],
                "unrealized_pnl_usd_indicative": o["unrealized_usd"],
                "fx": o["fx"],
                "mark_bar": o["mark_bar"],
                "exit_check_bars_seen": o["exit_check_bars_seen"],
                "flags": {"be_armed": o["be_armed"], "be_armed_at_bar": o["be_armed_at"],
                          "spread_fallback_used": s.spread_fallback},
                "data_quality": "OPEN AT OBSERVATION END (not counted as win/loss)",
            })
        elif sup:
            row.update({"status": "NOT_OPENED",
                        "reason": f"gate:pair_occupied",
                        "data_quality": "N/A (signal only)"})
        elif rej:
            row.update({"status": "NOT_OPENED",
                        "reason": f"risk_gate:{rej['reason']}",
                        "data_quality": "N/A (signal only)"})
        else:
            row.update({"status": "UNKNOWN_STATUS", "data_quality": "ERROR"})
            raise SystemExit(f"signal {s.signal_id} has no status — logic bug")
        rows.append(row)

    ledger = HERE / "post9_ledger.jsonl"
    with ledger.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")

    summary_obj = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "initial_balance": INITIAL_BALANCE,
        "observation": {
            "bars_first_label": min(b["timestamp"] for b in BARS),
            "bars_last_label": max(b["timestamp"] for b in BARS),
            "last_market_close_true_utc": primary["last_market_close"],
            "state_updated": STATE.get("updated_at"),
        },
        "populations": {
            "A_excluded": {"n": len(pop_a), "first": pop_a[0].order_ts,
                           "last": pop_a[-1].order_ts},
            "B_analyzed": {"n": len(pop_b), "first": pop_b[0].order_ts,
                           "last": pop_b[-1].order_ts,
                           "pairs": sorted({s.symbol for s in pop_b}),
                           "signal_bars": [s.bar_label for s in pop_b]},
        },
        "passes": {k: {"description": runs[k]["name"], "stats": summaries[k],
                       "outcomes": runs[k]["outcomes"]} for k in runs},
        "S5_tp_first_alternate": s5_delta(primary),
        "S5_tp_first_alternate_A_reference": s5_delta(a_ref),
        "S4_passive_flags": {
            "closed_trades_hit_max_hold_42": [
                {"signal_id": c.sig.signal_id, "held_bars": c.held_bars_label,
                 "actual_exit": c.exit_reason, "pnl": round(c.pnl, 2)}
                for c in primary["closed"] if c.flags["max_hold_would_preempt"]],
            "closed_trades_be_armed_before_exit": [
                {"signal_id": c.sig.signal_id, "be_at_bar": c.flags["be_armed_at_bar"],
                 "exit": c.exit_reason}
                for c in primary["closed"] if c.flags["be_armed_before_exit"]],
            "open_trades_be_armed": [
                {"signal_id": o["signal_id"], "be_at_bar": o["be_armed_at"]}
                for o in primary["open_at_end"] if o["be_armed"]],
            "open_trades_hit_max_hold_42_so_far": [
                {"signal_id": o["signal_id"], "held_bars": o["held_bars_label"]}
                for o in primary["open_at_end"] if o["max_hold_would_preempt"]],
            "note": "flags only — P&L effect of BE/max-hold order modifications "
                    "not quantified (path-dependent)",
        },
        "overlaps_primary": primary["overlaps"],
        "equity_curve_primary": primary["equity_curve"],
        "risk_blocks_captured": RISK_BLOCKS_CAPTURED,
        "signal_resolution": [
            {"n": s.idx, "signal_id": s.signal_id, "resolution": s.resolution,
             "warnings": s.warnings} for s in sigs],
    }
    summary_path = HERE / "post9_summary.json"
    summary_path.write_text(json.dumps(summary_obj, indent=2, default=str))

    for k, sm in summaries.items():
        print("\n" + "=" * 78)
        print(f"PASS: {runs[k]['name']}")
        print("=" * 78)
        for kk, vv in sm.items():
            print(f"  {kk}: {vv}")

    print("\n" + "=" * 78)
    print("S5 (live TP-first vs frozen SL-first on same-bar both-touch bars)")
    print(json.dumps(summary_obj["S5_tp_first_alternate"], indent=2))
    print("S5 (Population A reference):")
    print(json.dumps(summary_obj["S5_tp_first_alternate_A_reference"], indent=2))
    print("S4 passive flags (primary):")
    print(json.dumps(summary_obj["S4_passive_flags"], indent=2))

    print("\nPrimary outcomes (Population B):")
    for o in primary["outcomes"]:
        print(f"  #{o['idx']:2d} {o['status']:26s} {o.get('exit',''):4s} "
              f"pnl={o.get('pnl', o.get('unrealized',''))} "
              f"R={o.get('R','')} dq={o.get('dq','')} {o.get('reason','')}")

    print(f"\nWrote {ledger}")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
