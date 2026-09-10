"""
NestQuant Live Execution Runner — Signal → Order → Modify → Close
==================================================================
Polls MT5 for new bars, generates signals, and executes real orders
when LIVE_MODE is enabled. Manages position lifecycle including:
  - Entry via market orders
  - SL/TP modification (breakeven, trailing)
  - Position close on max hold or signal exit
  - Kill switch enforcement
  - Full audit logging
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from nestquant.execution.contracts import Direction, OrderRequest, TradeIntent, RiskDecision
from nestquant.execution.shadow.health import HealthMonitor
from nestquant.execution.shadow.kill_switch import KillSwitch
from nestquant.execution.shadow.logger import ShadowLogger
from nestquant.execution.shadow.signal_generator import (
    LOOKBACK,
    ATR_PERIOD,
    ATR_SL_MULT,
    RRR,
    MAX_HOLD_DAYS,
    BREAKEVEN_RATIO,
    TIMEFRAME,
    ShadowCausalSignalGenerator,
    ShadowSignalRecord,
)
from nestquant.execution.shadow.state import ShadowState
from nestquant.execution.shadow.wine_flask_adapter import WineFlaskExecutionAdapter
from nestquant.execution.risk_guard import RiskGuard, RiskGuardConfig
from nestquant.config.constitution import CONSTITUTION

logger = logging.getLogger(__name__)

MAGIC_NUMBER = 20260831  # Unique ID for NestQuant orders


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class LiveExecutionRunner:
    """Polls MT5 for new bars, generates signals, and executes real orders.

    Lifecycle:
      1. Poll for new completed bars (4h)
      2. Feed bar history to signal generator
      3. If signal fires → build OrderRequest → execute via adapter
      4. Manage open positions: breakeven, trailing stop, max hold exit
      5. Kill switch enforcement on every bar
      6. Full audit trail via JSONL logging
    """

    def __init__(
        self,
        adapter: WineFlaskExecutionAdapter,
        pairs: list[str],
        poll_interval: int = 5,
        log_dir: str = "logs/shadow_live",
        risk_per_trade: float = CONSTITUTION.risk_per_trade_pct,
        initial_balance: float = 200.0,
        enable_execution: bool = False,
    ) -> None:
        self.adapter = adapter
        self.pairs = pairs
        self.poll_interval = poll_interval
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.risk_per_trade = risk_per_trade
        self.initial_balance = initial_balance
        self.enable_execution = enable_execution

        self.state = ShadowState(str(self.log_dir / "state.json"))
        self.health = HealthMonitor()
        self.kill_switch = KillSwitch(str(self.log_dir / "kill_switch"))
        self.logger = ShadowLogger(str(self.log_dir))

        self.generator = ShadowCausalSignalGenerator()

        # Risk gate — constitution-derived, enforced on every signal
        risk_config = RiskGuardConfig(
            account_balance=initial_balance,
            risk_pct=risk_per_trade,
        )
        self.risk_guard = RiskGuard(config=risk_config)

        self._iteration = 0
        self._open_positions: dict[str, dict] = {}  # pair → position info
        self._order_count = 0
        self._filled_count = 0
        self._rejected_count = 0
        self._risk_rejected_count = 0
        self._closed_count = 0

    def _is_weekend_gap(self, current_broker: datetime, last_broker: datetime) -> bool:
        delta = (current_broker - last_broker).total_seconds()
        return delta > 48 * 3600

    def _compute_lot_size(self, entry: float, sl: float) -> float:
        """Compute lot size based on risk percentage and SL distance."""
        risk_amount = self.initial_balance * self.risk_per_trade
        sl_distance = abs(entry - sl)
        if sl_distance <= 0:
            return 0.01

        if "JPY" in str(self.pairs[0]) if self.pairs else False:
            pip_value = 0.01
        else:
            pip_value = 0.0001

        sl_pips = sl_distance / pip_value
        if sl_pips <= 0:
            return 0.01

        lot_size = risk_amount / (sl_pips * 10)
        lot_size = max(0.01, round(lot_size, 2))
        return min(lot_size, 1.0)

    def _check_position_exits(self, pair: str, bar: dict) -> Optional[str]:
        """Check if an open position should be exited."""
        pos = self._open_positions.get(pair)
        if not pos:
            return None

        bar_time = _parse_iso(bar["time"])
        open_time = _parse_iso(pos["open_time"])
        bars_held = (bar_time - open_time).total_seconds() / (4 * 3600)

        current_high = bar.get("high", 0)
        current_low = bar.get("low", 0)
        entry = pos["entry_price"]
        direction = pos["direction"]
        sl = pos["sl"]
        tp = pos["tp"]

        # Check TP hit
        if direction == "BUY" and current_high >= tp:
            return "TP"
        if direction == "SELL" and current_low <= tp:
            return "TP"

        # Check SL hit
        if direction == "BUY" and current_low <= sl:
            return "SL"
        if direction == "SELL" and current_high >= sl:
            return "SL"

        # Check max hold (42 bars = 7 days)
        if bars_held >= 42:
            return "MAX_HOLD"

        # Breakeven: move SL to entry when price has moved BREAKEVEN_RATIO * ATR
        atr = pos.get("atr", 0)
        be_level = BREAKEVEN_RATIO * atr
        if direction == "BUY" and current_high >= entry + be_level:
            if sl < entry:
                return "BREAKEVEN"
        if direction == "SELL" and current_low <= entry - be_level:
            if sl > entry:
                return "BREAKEVEN"

        return None

    def _manage_position(self, pair: str, bar: dict) -> None:
        """Manage open position: breakeven, trailing stop."""
        pos = self._open_positions.get(pair)
        if not pos:
            return

        entry = pos["entry_price"]
        direction = pos["direction"]
        atr = pos.get("atr", 0)
        be_level = BREAKEVEN_RATIO * atr

        current_high = bar.get("high", 0)
        current_low = bar.get("low", 0)

        # Breakeven adjustment
        if direction == "BUY" and current_high >= entry + be_level:
            if pos["sl"] < entry:
                new_sl = entry
                ticket = pos.get("ticket")
                if ticket and self.enable_execution:
                    self.adapter.modify_position(ticket, sl=new_sl)
                pos["sl"] = new_sl
                self.logger.log_infrastructure(
                    "INFO",
                    f"BREAKEVEN: {pair} SL moved to {new_sl:.5f}",
                    impact="POSITIVE",
                )

        if direction == "SELL" and current_low <= entry - be_level:
            if pos["sl"] > entry:
                new_sl = entry
                ticket = pos.get("ticket")
                if ticket and self.enable_execution:
                    self.adapter.modify_position(ticket, sl=new_sl)
                pos["sl"] = new_sl
                self.logger.log_infrastructure(
                    "INFO",
                    f"BREAKEVEN: {pair} SL moved to {new_sl:.5f}",
                    impact="POSITIVE",
                )

    def _execute_signal(self, signal: ShadowSignalRecord) -> None:
        """Convert signal to order and execute — RISK GATE ENFORCED."""
        # Build TradeIntent for risk evaluation
        intent = TradeIntent(
            pair=signal.symbol,
            direction=Direction.BUY if signal.direction == "BUY" else Direction.SELL,
            signal_strength=1.0,
            entry_price=signal.expected_entry,
            stop_loss=signal.expected_sl,
            take_profit=signal.expected_tp,
            strategy="breakout",
            policy_version="constitution-1.0.0",
            timestamp=datetime.now(timezone.utc),
        )

        # RISK GATE — evaluate before any order
        risk_decision = self.risk_guard.evaluate(intent)

        if not risk_decision.approved:
            self._risk_rejected_count += 1
            self.logger.log_infrastructure(
                "WARNING",
                f"RISK_REJECTED: {signal.direction} {signal.symbol} "
                f"reason={risk_decision.reason}",
                impact="ORDER_BLOCKED",
            )
            return

        # Build OrderRequest with risk-approved lot size
        request = OrderRequest(
            pair=signal.symbol,
            direction=Direction.BUY if signal.direction == "BUY" else Direction.SELL,
            lot_size=risk_decision.lot_size,
            entry_price=signal.expected_entry,
            stop_loss=signal.expected_sl,
            take_profit=signal.expected_tp,
            policy_version=signal.research_run_id,
        )

        self._order_count += 1

        # Log intended order
        self.logger.log_intended_order(
            signal=signal,
            order_type="MARKET" if self.enable_execution else "SHADOW_MARKET",
            entry_price=request.entry_price,
            sl_price=request.stop_loss,
            tp_price=request.take_profit,
            lot_size=request.lot_size,
        )

        if not self.enable_execution:
            self.logger.log_infrastructure(
                "INFO",
                f"SHADOW ONLY: {signal.direction} {signal.symbol} "
                f"lot={request.lot_size} SL={request.stop_loss:.5f} TP={request.take_profit:.5f}",
                impact="NO_IMPACT",
            )
            return

        # Execute real order
        try:
            result = self.adapter.execute(request)
            if result.is_filled:
                self._filled_count += 1
                self._open_positions[signal.symbol] = {
                    "ticket": int(result.order_id) if result.order_id else None,
                    "direction": signal.direction,
                    "entry_price": result.fill_price,
                    "stop_price": request.stop_loss,
                    "tp": request.take_profit,
                    "sl": request.stop_loss,
                    "atr": signal.atr_at_signal,
                    "open_time": signal.timestamp,
                    "signal_id": signal.signal_id,
                }
                self.logger.log_infrastructure(
                    "INFO",
                    f"FILLED: {signal.direction} {signal.symbol} @ {result.fill_price:.5f} "
                    f"slippage={result.slippage_pips:.1f}pips ticket={result.order_id}",
                    impact="POSITIVE",
                )
            else:
                self._rejected_count += 1
                self.logger.log_infrastructure(
                    "WARNING",
                    f"REJECTED: {signal.direction} {signal.symbol} "
                    f"reason={result.rejection_reason}",
                    impact="NEGATIVE",
                )
        except Exception as e:
            self._rejected_count += 1
            self.logger.log_infrastructure(
                "ERROR",
                f"EXECUTION ERROR: {signal.symbol} {e}",
                impact="NEGATIVE",
            )

    def _close_position(self, pair: str, reason: str) -> None:
        """Close an open position."""
        pos = self._open_positions.pop(pair, None)
        if not pos:
            return

        self._closed_count += 1

        if not self.enable_execution:
            self.logger.log_infrastructure(
                "INFO",
                f"SHADOW CLOSE: {pair} reason={reason}",
                impact="NO_IMPACT",
            )
            return

        ticket = pos.get("ticket")
        if ticket:
            try:
                direction_int = 0 if pos["direction"] == "BUY" else 1
                self.adapter.close_position(
                    ticket=ticket,
                    symbol=pair,
                    volume=pos.get("lot_size", 0.01),
                    direction=direction_int,
                )
                self.logger.log_infrastructure(
                    "INFO",
                    f"CLOSED: {pair} ticket={ticket} reason={reason}",
                    impact="POSITIVE" if reason in ("TP", "BREAKEVEN") else "NEUTRAL",
                )
            except Exception as e:
                self.logger.log_infrastructure(
                    "ERROR",
                    f"CLOSE ERROR: {pair} {e}",
                    impact="NEGATIVE",
                )

    def _poll_once(self) -> dict:
        """Single polling iteration across all pairs."""
        iteration_report = {
            "iteration": self._iteration,
            "bars_observed": 0,
            "bars_processed": 0,
            "signals_generated": 0,
            "executions_attempted": 0,
            "executions_filled": 0,
            "positions_closed": 0,
        }

        for pair in self.pairs:
            # Poll for new bar
            try:
                bar = self.adapter.get_last_completed_bar(pair, TIMEFRAME)
                if bar is None:
                    continue

                iteration_report["bars_observed"] += 1

                # Check for duplicate
                last = self.state.get_last_bar(pair)
                if last and bar.time == last:
                    continue

                # Check for weekend gap
                if last:
                    last_dt = _parse_iso(last)
                    bar_dt = _parse_iso(bar.time)
                    if self._is_weekend_gap(bar_dt, last_dt):
                        self.logger.log_infrastructure(
                            "INFO",
                            f"WEEKEND GAP: {pair} {last} → {bar.time}",
                            impact="NO_IMPACT",
                        )

                self.state.set_last_bar(pair, bar.time)
                iteration_report["bars_processed"] += 1

                # Log bar
                self.logger.log_bar(pair, bar)

                # Health update
                self.health.record_bar(pair, bar.time)

                # Manage existing position
                self._manage_position(pair, {
                    "time": bar.time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                })

                # Check position exits
                exit_reason = self._check_position_exits(pair, {
                    "time": bar.time,
                    "high": bar.high,
                    "low": bar.low,
                })
                if exit_reason:
                    self._close_position(pair, exit_reason)
                    iteration_report["positions_closed"] += 1

                # Generate signal
                try:
                    history = self.adapter.fetch_history(pair, TIMEFRAME, count=200)
                    if history is None or len(history) < LOOKBACK + ATR_PERIOD:
                        continue

                    signal = self.generator.generate(history, pair)
                    if signal:
                        iteration_report["signals_generated"] += 1
                        self.logger.log_signal(signal)

                        # Check if already have position in this pair
                        if pair not in self._open_positions:
                            self._execute_signal(signal)
                            iteration_report["executions_attempted"] += 1
                            if self.enable_execution:
                                iteration_report["executions_filled"] += 1

                except Exception as e:
                    self.logger.log_infrastructure(
                        "WARNING",
                        f"Signal generation failed for {pair}: {e}",
                        impact="NO_IMPACT",
                    )

            except Exception as e:
                self.logger.log_infrastructure(
                    "WARNING",
                    f"Bar polling failed for {pair}: {e}",
                    impact="NO_IMPACT",
                )

        self._iteration += 1
        return iteration_report

    def run(self, iterations: int | None = None) -> dict:
        """Main execution loop.

        Args:
            iterations: Stop after N iterations. None = run forever.
        """
        self.logger.log_lifecycle("STARTED", {
            "mode": "LIVE_EXECUTION" if self.enable_execution else "SHADOW",
            "pairs": len(self.pairs),
            "adapter": self.adapter.name,
            "risk_per_trade": self.risk_per_trade,
            "risk_source": "constitution",
            "magic": MAGIC_NUMBER,
        })

        start_time = time.time()

        try:
            while iterations is None or self._iteration < iterations:
                # Kill switch check
                if self.kill_switch.is_active():
                    self.logger.log_lifecycle("KILL_SWITCH", {"iteration": self._iteration})
                    break

                report = self._poll_once()
                self.logger.log_infrastructure(
                    "INFO",
                    f"Iteration {self._iteration}: "
                    f"observed={report['bars_observed']} "
                    f"processed={report['bars_processed']} "
                    f"signals={report['signals_generated']} "
                    f"filled={report['executions_filled']} "
                    f"closed={report['positions_closed']}",
                    impact="NO_IMPACT",
                )

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            self.logger.log_lifecycle("INTERRUPTED", {"iteration": self._iteration})
        except Exception as e:
            self.logger.log_lifecycle("ERROR", {"error": str(e), "iteration": self._iteration})
        finally:
            # Close remaining positions on shutdown
            if self.enable_execution and self._open_positions:
                for pair in list(self._open_positions.keys()):
                    self._close_position(pair, "SHUTDOWN")

        elapsed = time.time() - start_time

        self.logger.log_lifecycle("STOPPED", {
            "iterations": self._iteration,
            "elapsed_seconds": round(elapsed, 1),
            "orders_submitted": self._order_count,
            "orders_filled": self._filled_count,
            "orders_rejected": self._rejected_count,
            "risk_rejected": self._risk_rejected_count,
            "positions_closed": self._closed_count,
        })

        return {
            "iterations": self._iteration,
            "elapsed_seconds": round(elapsed, 1),
            "orders_submitted": self._order_count,
            "orders_filled": self._filled_count,
            "orders_rejected": self._rejected_count,
            "risk_rejected": self._risk_rejected_count,
            "positions_closed": self._closed_count,
            "health": self.health.snapshot(),
        }
