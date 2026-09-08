"""
NestQuant Trade Logger — Structured Data Capture
=================================================
Records all trade events per S7 protocol sections 3.1-3.6.

This module:
  - Records signal, order, fill, exit, bar, and infrastructure events
  - Uses JSON Lines format for append-only logging
  - Links signal_id → order_id → fill_id
  - Provides reconciliation queries
  - Is deterministic and append-only

This module does NOT:
  - Import MT5 or broker SDKs
  - Make network calls
  - Perform strategy calculations
  - Perform risk calculations
  - Modify existing records
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Record types (S7 protocol sections 3.1-3.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalRecord:
    """S7 section 3.1: Per-signal record. Extended for S8 experiment identity."""

    signal_id: str
    timestamp: str
    symbol: str
    direction: str
    strategy_params: dict[str, Any]
    swing_level: float
    signal_bar_close: float
    expected_entry: float
    expected_sl: float
    expected_tp: float
    atr_at_signal: float
    spread_at_signal: float
    # S8 experiment identity fields
    experiment_id: str = ""
    strategy_version: str = ""
    config_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderRecord:
    """S7 section 3.2: Per-order record."""

    signal_id: str
    order_id: str
    submission_timestamp: str
    symbol: str
    direction: str
    volume: float
    order_type: str
    requested_price: float
    sl: float
    tp: float
    spread_at_submission: float
    execution_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FillRecord:
    """S7 section 3.3: Per-fill record."""

    order_id: str
    fill_timestamp: str
    fill_price: float
    fill_volume: float
    actual_sl: float
    actual_tp: float
    slippage_pips: float
    commission: float
    swap: float
    fill_status: str
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExitRecord:
    """S7 section 3.4: Per-exit record."""

    order_id: str
    exit_timestamp: str
    exit_price: float
    exit_reason: str
    gross_pnl_pips: float
    gross_pnl_currency: float
    trading_costs: float
    net_pnl_pips: float
    net_pnl_currency: float
    hold_duration_hours: float
    hold_duration_bars: int
    slippage_at_exit_pips: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BarRecord:
    """S7 section 3.5: Per-bar record."""

    timestamp: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float
    atr_14: Optional[float] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InfrastructureRecord:
    """S7 section 3.6: Infrastructure event record."""

    timestamp: str
    event_type: str
    description: str
    duration_seconds: Optional[float] = None
    impact: Optional[str] = None
    resolution: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Trade Logger
# ---------------------------------------------------------------------------


class TradeLogger:
    """Append-only structured trade logger.

    Writes JSON Lines (.jsonl) files for each record type:
      - signals.jsonl
      - orders.jsonl
      - fills.jsonl
      - exits.jsonl
      - bars.jsonl
      - infrastructure.jsonl

    All records are immutable once written.
    """

    def __init__(self, log_dir: str | Path) -> None:
        """Initialize the trade logger.

        Args:
            log_dir: Directory to write log files.
        """
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._counters: dict[str, int] = {
            "signals": 0,
            "orders": 0,
            "fills": 0,
            "exits": 0,
            "bars": 0,
            "infrastructure": 0,
        }

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def _write_record(self, filename: str, record: dict[str, Any]) -> None:
        """Append a single record to a JSONL file."""
        filepath = self._log_dir / filename
        with open(filepath, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def log_signal(self, record: SignalRecord) -> None:
        """Log a signal record (S7 section 3.1)."""
        self._write_record("signals.jsonl", record.to_dict())
        self._counters["signals"] += 1

    def log_order(self, record: OrderRecord) -> None:
        """Log an order record (S7 section 3.2)."""
        self._write_record("orders.jsonl", record.to_dict())
        self._counters["orders"] += 1

    def log_fill(self, record: FillRecord) -> None:
        """Log a fill record (S7 section 3.3)."""
        self._write_record("fills.jsonl", record.to_dict())
        self._counters["fills"] += 1

    def log_exit(self, record: ExitRecord) -> None:
        """Log an exit record (S7 section 3.4)."""
        self._write_record("exits.jsonl", record.to_dict())
        self._counters["exits"] += 1

    def log_bar(self, record: BarRecord) -> None:
        """Log a bar record (S7 section 3.5)."""
        self._write_record("bars.jsonl", record.to_dict())
        self._counters["bars"] += 1

    def log_infrastructure(self, record: InfrastructureRecord) -> None:
        """Log an infrastructure event (S7 section 3.6)."""
        self._write_record("infrastructure.jsonl", record.to_dict())
        self._counters["infrastructure"] += 1

    # ------------------------------------------------------------------
    # Convenience factories
    # ------------------------------------------------------------------

    def create_signal(
        self,
        symbol: str,
        direction: str,
        swing_level: float,
        signal_bar_close: float,
        expected_entry: float,
        expected_sl: float,
        expected_tp: float,
        atr_at_signal: float,
        spread_at_signal: float,
        strategy_params: Optional[dict] = None,
        experiment_id: str = "",
        strategy_version: str = "",
        config_hash: str = "",
    ) -> SignalRecord:
        """Create and log a signal record."""
        record = SignalRecord(
            signal_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC).isoformat(),
            symbol=symbol,
            direction=direction,
            strategy_params=strategy_params or {},
            swing_level=swing_level,
            signal_bar_close=signal_bar_close,
            expected_entry=expected_entry,
            expected_sl=expected_sl,
            expected_tp=expected_tp,
            atr_at_signal=atr_at_signal,
            spread_at_signal=spread_at_signal,
            experiment_id=experiment_id,
            strategy_version=strategy_version,
            config_hash=config_hash,
        )
        self.log_signal(record)
        return record

    def create_order(
        self,
        signal_id: str,
        order_id: str,
        symbol: str,
        direction: str,
        volume: float,
        requested_price: float,
        sl: float,
        tp: float,
        spread_at_submission: float,
        execution_latency_ms: float,
        order_type: str = "MARKET",
    ) -> OrderRecord:
        """Create and log an order record."""
        record = OrderRecord(
            signal_id=signal_id,
            order_id=order_id,
            submission_timestamp=datetime.now(UTC).isoformat(),
            symbol=symbol,
            direction=direction,
            volume=volume,
            order_type=order_type,
            requested_price=requested_price,
            sl=sl,
            tp=tp,
            spread_at_submission=spread_at_submission,
            execution_latency_ms=execution_latency_ms,
        )
        self.log_order(record)
        return record

    def create_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_volume: float,
        actual_sl: float,
        actual_tp: float,
        slippage_pips: float,
        commission: float = 0.0,
        swap: float = 0.0,
        fill_status: str = "FILLED",
        rejection_reason: Optional[str] = None,
    ) -> FillRecord:
        """Create and log a fill record."""
        record = FillRecord(
            order_id=order_id,
            fill_timestamp=datetime.now(UTC).isoformat(),
            fill_price=fill_price,
            fill_volume=fill_volume,
            actual_sl=actual_sl,
            actual_tp=actual_tp,
            slippage_pips=slippage_pips,
            commission=commission,
            swap=swap,
            fill_status=fill_status,
            rejection_reason=rejection_reason,
        )
        self.log_fill(record)
        return record

    def create_exit(
        self,
        order_id: str,
        exit_price: float,
        exit_reason: str,
        gross_pnl_pips: float,
        gross_pnl_currency: float,
        trading_costs: float,
        net_pnl_pips: float,
        net_pnl_currency: float,
        hold_duration_hours: float,
        hold_duration_bars: int,
        slippage_at_exit_pips: float = 0.0,
    ) -> ExitRecord:
        """Create and log an exit record."""
        record = ExitRecord(
            order_id=order_id,
            exit_timestamp=datetime.now(UTC).isoformat(),
            exit_price=exit_price,
            exit_reason=exit_reason,
            gross_pnl_pips=gross_pnl_pips,
            gross_pnl_currency=gross_pnl_currency,
            trading_costs=trading_costs,
            net_pnl_pips=net_pnl_pips,
            net_pnl_currency=net_pnl_currency,
            hold_duration_hours=hold_duration_hours,
            hold_duration_bars=hold_duration_bars,
            slippage_at_exit_pips=slippage_at_exit_pips,
        )
        self.log_exit(record)
        return record

    def log_infrastructure_event(
        self,
        event_type: str,
        description: str,
        duration_seconds: Optional[float] = None,
        impact: Optional[str] = None,
        resolution: Optional[str] = None,
    ) -> InfrastructureRecord:
        """Create and log an infrastructure event."""
        record = InfrastructureRecord(
            timestamp=datetime.now(UTC).isoformat(),
            event_type=event_type,
            description=description,
            duration_seconds=duration_seconds,
            impact=impact,
            resolution=resolution,
        )
        self.log_infrastructure(record)
        return record

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def _read_jsonl(self, filename: str) -> list[dict[str, Any]]:
        """Read all records from a JSONL file."""
        filepath = self._log_dir / filename
        if not filepath.exists():
            return []
        records = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def get_signals(self) -> list[dict]:
        return self._read_jsonl("signals.jsonl")

    def get_orders(self) -> list[dict]:
        return self._read_jsonl("orders.jsonl")

    def get_fills(self) -> list[dict]:
        return self._read_jsonl("fills.jsonl")

    def get_exits(self) -> list[dict]:
        return self._read_jsonl("exits.jsonl")

    def get_infrastructure_events(self) -> list[dict]:
        return self._read_jsonl("infrastructure.jsonl")

    def count_records(self) -> dict[str, int]:
        """Return count of records per type."""
        return {
            "signals": len(self.get_signals()),
            "orders": len(self.get_orders()),
            "fills": len(self.get_fills()),
            "exits": len(self.get_exits()),
            "infrastructure": len(self.get_infrastructure_events()),
        }

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile(self) -> dict[str, Any]:
        """Reconcile signal → order → fill → exit chains.

        Returns reconciliation report with orphan detection.
        """
        signals = self.get_signals()
        orders = self.get_orders()
        fills = self.get_fills()
        exits = self.get_exits()

        signal_ids = {s["signal_id"] for s in signals}
        order_ids = {o["order_id"] for o in orders}
        fill_order_ids = {f["order_id"] for f in fills}
        exit_order_ids = {e["order_id"] for e in exits}

        # Build signal_id → order_id mapping
        signal_to_order: dict[str, str] = {}
        for o in orders:
            signal_to_order[o["signal_id"]] = o["order_id"]

        # Orphan detection
        orphan_orders = order_ids - fill_order_ids  # orders without fills
        orphan_fills = fill_order_ids - exit_order_ids  # fills without exits
        unmatched_signals = signal_ids - set(signal_to_order.keys())

        return {
            "total_signals": len(signals),
            "total_orders": len(orders),
            "total_fills": len(fills),
            "total_exits": len(exits),
            "signal_to_order_rate": (
                len(signal_to_order) / len(signals) if signals else 0.0
            ),
            "fill_rate": len(fill_order_ids) / len(order_ids) if order_ids else 0.0,
            "exit_rate": len(exit_order_ids) / len(fill_order_ids) if fill_order_ids else 0.0,
            "orphan_orders": list(orphan_orders),
            "orphan_fills": list(orphan_fills),
            "unmatched_signals": list(unmatched_signals),
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Get a summary of logged data."""
        exits = self.get_exits()
        fills = self.get_fills()

        total_pnl = sum(e.get("net_pnl_currency", 0) for e in exits)
        total_trades = len(exits)
        winners = [e for e in exits if e.get("net_pnl_currency", 0) > 0]
        losers = [e for e in exits if e.get("net_pnl_currency", 0) <= 0]

        return {
            "record_counts": self.count_records(),
            "total_exits": total_trades,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": len(winners) / total_trades if total_trades > 0 else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl_per_trade": total_pnl / total_trades if total_trades > 0 else 0.0,
            "total_slippage_pips": sum(
                f.get("slippage_pips", 0) for f in fills
            ),
            "total_commission": sum(
                f.get("commission", 0) for f in fills
            ),
        }

    def __repr__(self) -> str:
        return f"<TradeLogger(dir={self._log_dir})>"
