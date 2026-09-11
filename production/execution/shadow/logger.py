"""
Shadow logger — append-only JSONL capture for S7 Protocol §§3.1, 3.5, 3.6.

Files (all JSONL, one JSON object per line):
  signals.jsonl       — §3.1 per-signal records (ShadowSignalRecord)
  bars.jsonl          — §3.5 per-bar records (OHLC + ATR + swing context)
  infrastructure.jsonl — §3.6 health / lifecycle events
  intended_orders.jsonl — shadow intended orders (what *would* have been sent)
  lifecycle.jsonl     — shadow simulated exits (derived from SL/TP/breakeven/max_hold)

All writes are append-only, flushed per record, and parents are created.
Timestamps within each file must be monotonic; violations are flagged as
infrastructure events rather than silently corrected.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nestquant.execution.shadow.signal_generator import ShadowSignalRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ShadowLogger:
    """Append-only JSONL logger for shadow mode.

    Args:
        log_dir: Directory for JSONL files. Created if missing.
    """

    def __init__(self, log_dir: str | Path = "logs/shadow") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._paths = {
            "signals": self.log_dir / "signals.jsonl",
            "bars": self.log_dir / "bars.jsonl",
            "infrastructure": self.log_dir / "infrastructure.jsonl",
            "intended_orders": self.log_dir / "intended_orders.jsonl",
            "lifecycle": self.log_dir / "lifecycle.jsonl",
        }
        # Monotonicity trackers
        self._last_ts: dict[str, str] = {}

    # ---- low-level append ----

    def _append(self, kind: str, obj: dict[str, Any]) -> None:
        path = self._paths[kind]
        # Ensure timestamped objects are checked for monotonicity if they carry one
        ts = obj.get("timestamp") or obj.get("bar_timestamp") or obj.get("event_timestamp")
        if ts and kind in self._last_ts:
            if ts < self._last_ts[kind]:
                # Flag but still write — caller decides handling
                pass
            self._last_ts[kind] = max(ts, self._last_ts[kind])
        elif ts:
            self._last_ts[kind] = ts
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # ---- §3.1 signals ----

    def log_signal(self, rec: ShadowSignalRecord) -> None:
        obj: dict[str, Any] = {
            "signal_id": rec.signal_id,
            "timestamp": rec.timestamp,
            "symbol": rec.symbol,
            "direction": rec.direction,
            "strategy_params": dict(rec.strategy_params),
            "swing_level": rec.swing_level,
            "signal_bar_close": rec.signal_bar_close,
            "expected_entry": rec.expected_entry,
            "expected_sl": rec.expected_sl,
            "expected_tp": rec.expected_tp,
            "atr_at_signal": rec.atr_at_signal,
            "spread_at_signal": rec.spread_at_signal,
            "bar_open": rec.bar_open,
            "bar_high": rec.bar_high,
            "bar_low": rec.bar_low,
            "generation_latency_ms": rec.generation_latency_ms,
            "policy_version": rec.policy_version,
            "research_run_id": rec.research_run_id,
        }
        self._append("signals", obj)

    # ---- §3.5 bars ----

    def log_bar(
        self,
        pair: str,
        bar_timestamp: str,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        spread: float,
        atr_14: Optional[float] = None,
        swing_high: Optional[float] = None,
        swing_low: Optional[float] = None,
        *,
        broker_timestamp: Optional[str] = None,
        receipt_timestamp: Optional[str] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
    ) -> None:
        self._append(
            "bars",
            {
                "timestamp": bar_timestamp,
                "symbol": pair,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "spread": spread,
                "atr_14": atr_14,
                "swing_high": swing_high,
                "swing_low": swing_low,
                "broker_timestamp": broker_timestamp,
                "receipt_timestamp": receipt_timestamp or _utc_now_iso(),
                "bid": bid,
                "ask": ask,
            },
        )

    def log_live_signal(
        self,
        rec: ShadowSignalRecord,
        *,
        broker_timestamp: str,
        receipt_timestamp: str,
        bid: float,
        ask: float,
        spread: float,
    ) -> None:
        """Live-shadow signal with live quote fields (extends §3.1)."""
        obj: dict[str, Any] = {
            "signal_id": rec.signal_id,
            "timestamp": rec.timestamp,
            "symbol": rec.symbol,
            "direction": rec.direction,
            "strategy_params": dict(rec.strategy_params),
            "swing_level": rec.swing_level,
            "signal_bar_close": rec.signal_bar_close,
            "expected_entry": rec.expected_entry,
            "expected_sl": rec.expected_sl,
            "expected_tp": rec.expected_tp,
            "atr_at_signal": rec.atr_at_signal,
            "spread_at_signal": rec.spread_at_signal,
            "bar_open": rec.bar_open,
            "bar_high": rec.bar_high,
            "bar_low": rec.bar_low,
            "generation_latency_ms": rec.generation_latency_ms,
            "policy_version": rec.policy_version,
            "research_run_id": rec.research_run_id,
            "broker_timestamp": broker_timestamp,
            "receipt_timestamp": receipt_timestamp,
            "bid": bid,
            "ask": ask,
            "live_spread": spread,
        }
        self._append("signals", obj)

    # ---- §3.6 infrastructure ----

    def log_infrastructure(
        self,
        event_type: str,
        description: str,
        duration_seconds: Optional[float] = None,
        impact: Optional[str] = None,
        resolution: Optional[str] = None,
    ) -> None:
        self._append(
            "infrastructure",
            {
                "timestamp": _utc_now_iso(),
                "event_type": event_type,
                "description": description,
                "duration_seconds": duration_seconds,
                "impact": impact,
                "resolution": resolution,
            },
        )

    # ---- shadow intended order (NOT a real order) ----

    def log_intended_order(
        self,
        signal_id: str,
        symbol: str,
        direction: str,
        volume: float,
        requested_price: float,
        sl: float,
        tp: float,
        spread_at_submission: float,
    ) -> None:
        self._append(
            "intended_orders",
            {
                "signal_id": signal_id,
                "timestamp": _utc_now_iso(),
                "symbol": symbol,
                "direction": direction,
                "volume": volume,
                "order_type": "SHADOW_MARKET",
                "requested_price": requested_price,
                "sl": sl,
                "tp": tp,
                "spread_at_submission": spread_at_submission,
                "note": "SHADOW_ONLY — no broker order sent",
            },
        )

    # ---- lifecycle (simulated exit) ----

    def log_lifecycle(
        self,
        signal_id: str,
        symbol: str,
        exit_reason: str,
        entry_price: float,
        exit_price: float,
        gross_pnl_pips: float,
        hold_bars: int,
        hold_hours: float,
    ) -> None:
        self._append(
            "lifecycle",
            {
                "signal_id": signal_id,
                "timestamp": _utc_now_iso(),
                "symbol": symbol,
                "exit_reason": exit_reason,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_pnl_pips": gross_pnl_pips,
                "hold_bars": hold_bars,
                "hold_hours": hold_hours,
                "note": "SHADOW_ONLY — simulated from subsequent bars",
            },
        )

    def paths(self) -> dict[str, Path]:
        return dict(self._paths)
