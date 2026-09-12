"""
Tests for nestquant.execution.trade_logger module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nestquant.production.execution.trade_logger import (
    BarRecord,
    ExitRecord,
    FillRecord,
    InfrastructureRecord,
    OrderRecord,
    SignalRecord,
    TradeLogger,
)


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------


class TestSignalRecord:
    def test_construction(self):
        r = SignalRecord(
            signal_id="sig-001",
            timestamp="2026-01-15T12:00:00+00:00",
            symbol="EURUSD",
            direction="BUY",
            strategy_params={"lookback": 5},
            swing_level=1.0950,
            signal_bar_close=1.1000,
            expected_entry=1.1002,
            expected_sl=1.0950,
            expected_tp=1.1150,
            atr_at_signal=0.0050,
            spread_at_signal=0.0002,
        )
        assert r.signal_id == "sig-001"
        assert r.symbol == "EURUSD"
        d = r.to_dict()
        assert d["signal_id"] == "sig-001"
        assert d["strategy_params"] == {"lookback": 5}

    def test_frozen(self):
        r = SignalRecord(
            signal_id="sig-001", timestamp="t", symbol="EURUSD",
            direction="BUY", strategy_params={}, swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        )
        with pytest.raises(AttributeError):
            r.signal_id = "changed"


class TestOrderRecord:
    def test_construction(self):
        r = OrderRecord(
            signal_id="sig-001",
            order_id="ord-001",
            submission_timestamp="2026-01-15T12:00:01+00:00",
            symbol="EURUSD",
            direction="BUY",
            volume=0.1,
            order_type="MARKET",
            requested_price=1.1002,
            sl=1.0950,
            tp=1.1150,
            spread_at_submission=0.0002,
            execution_latency_ms=150.0,
        )
        assert r.order_id == "ord-001"
        assert r.execution_latency_ms == 150.0


class TestFillRecord:
    def test_construction(self):
        r = FillRecord(
            order_id="ord-001",
            fill_timestamp="2026-01-15T12:00:01+00:00",
            fill_price=1.1003,
            fill_volume=0.1,
            actual_sl=1.0950,
            actual_tp=1.1150,
            slippage_pips=0.1,
            commission=3.50,
            swap=0.0,
            fill_status="FILLED",
        )
        assert r.fill_price == 1.1003
        assert r.fill_status == "FILLED"

    def test_rejection(self):
        r = FillRecord(
            order_id="ord-002",
            fill_timestamp="2026-01-15T12:00:01+00:00",
            fill_price=0.0,
            fill_volume=0.0,
            actual_sl=0.0,
            actual_tp=0.0,
            slippage_pips=0.0,
            commission=0.0,
            swap=0.0,
            fill_status="REJECTED",
            rejection_reason="Not enough money",
        )
        assert r.fill_status == "REJECTED"
        assert r.rejection_reason == "Not enough money"


class TestExitRecord:
    def test_construction(self):
        r = ExitRecord(
            order_id="ord-001",
            exit_timestamp="2026-01-16T12:00:00+00:00",
            exit_price=1.1150,
            exit_reason="TP",
            gross_pnl_pips=148.0,
            gross_pnl_currency=1480.0,
            trading_costs=7.0,
            net_pnl_pips=141.0,
            net_pnl_currency=1410.0,
            hold_duration_hours=24.0,
            hold_duration_bars=6,
            slippage_at_exit_pips=0.05,
        )
        assert r.exit_reason == "TP"
        assert r.net_pnl_currency == 1410.0


class TestBarRecord:
    def test_construction(self):
        r = BarRecord(
            timestamp="2026-01-15T12:00:00+00:00",
            symbol="EURUSD",
            open=1.1000,
            high=1.1050,
            low=1.0980,
            close=1.1020,
            volume=1500,
            spread=0.0002,
        )
        assert r.close == 1.1020

    def test_optional_fields(self):
        r = BarRecord(
            timestamp="t", symbol="EURUSD",
            open=1.0, high=1.0, low=1.0, close=1.0, volume=100, spread=0.001,
            atr_14=0.005, swing_high=1.005, swing_low=0.995,
        )
        assert r.atr_14 == 0.005
        assert r.swing_high == 1.005


class TestInfrastructureRecord:
    def test_construction(self):
        r = InfrastructureRecord(
            timestamp="2026-01-15T12:00:00+00:00",
            event_type="DISCONNECT",
            description="MT5 connection lost",
            duration_seconds=30.0,
            impact="MISSED_SIGNAL",
            resolution="auto-reconnect",
        )
        assert r.event_type == "DISCONNECT"
        assert r.duration_seconds == 30.0


# ---------------------------------------------------------------------------
# TradeLogger writing
# ---------------------------------------------------------------------------


class TestTradeLoggerWriting:
    def test_log_signal(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = SignalRecord(
            signal_id="sig-001", timestamp="t", symbol="EURUSD",
            direction="BUY", strategy_params={}, swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        )
        logger.log_signal(record)

        assert (tmp_path / "signals.jsonl").exists()
        lines = (tmp_path / "signals.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["signal_id"] == "sig-001"

    def test_log_order(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = OrderRecord(
            signal_id="sig-001", order_id="ord-001",
            submission_timestamp="t", symbol="EURUSD",
            direction="BUY", volume=0.1, order_type="MARKET",
            requested_price=1.1, sl=1.0, tp=1.2,
            spread_at_submission=0.001, execution_latency_ms=100,
        )
        logger.log_order(record)

        lines = (tmp_path / "orders.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1

    def test_log_fill(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = FillRecord(
            order_id="ord-001", fill_timestamp="t",
            fill_price=1.1, fill_volume=0.1,
            actual_sl=1.0, actual_tp=1.2,
            slippage_pips=0.1, commission=3.5,
            swap=0.0, fill_status="FILLED",
        )
        logger.log_fill(record)

        lines = (tmp_path / "fills.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1

    def test_log_exit(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = ExitRecord(
            order_id="ord-001", exit_timestamp="t",
            exit_price=1.2, exit_reason="TP",
            gross_pnl_pips=100, gross_pnl_currency=1000,
            trading_costs=7, net_pnl_pips=93,
            net_pnl_currency=930, hold_duration_hours=24,
            hold_duration_bars=6, slippage_at_exit_pips=0.05,
        )
        logger.log_exit(record)

        lines = (tmp_path / "exits.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1

    def test_log_infrastructure(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        logger.log_infrastructure_event(
            event_type="STARTUP",
            description="MT5 initialized",
        )

        lines = (tmp_path / "infrastructure.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1

    def test_multiple_records(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        for i in range(5):
            logger.log_signal(SignalRecord(
                signal_id=f"sig-{i}", timestamp="t", symbol="EURUSD",
                direction="BUY", strategy_params={}, swing_level=1.0,
                signal_bar_close=1.0, expected_entry=1.0,
                expected_sl=0.9, expected_tp=1.1,
                atr_at_signal=0.01, spread_at_signal=0.001,
            ))

        lines = (tmp_path / "signals.jsonl").read_text().strip().split("\n")
        assert len(lines) == 5

    def test_append_mode(self, tmp_path: Path):
        logger1 = TradeLogger(tmp_path)
        logger1.log_signal(SignalRecord(
            signal_id="sig-001", timestamp="t", symbol="EURUSD",
            direction="BUY", strategy_params={}, swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        ))

        logger2 = TradeLogger(tmp_path)
        logger2.log_signal(SignalRecord(
            signal_id="sig-002", timestamp="t", symbol="GBPUSD",
            direction="SELL", strategy_params={}, swing_level=1.2,
            signal_bar_close=1.2, expected_entry=1.2,
            expected_sl=1.3, expected_tp=1.1,
            atr_at_signal=0.02, spread_at_signal=0.002,
        ))

        lines = (tmp_path / "signals.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# TradeLogger convenience factories
# ---------------------------------------------------------------------------


class TestConvenienceFactories:
    def test_create_signal(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = logger.create_signal(
            symbol="EURUSD",
            direction="BUY",
            swing_level=1.0950,
            signal_bar_close=1.1000,
            expected_entry=1.1002,
            expected_sl=1.0950,
            expected_tp=1.1150,
            atr_at_signal=0.0050,
            spread_at_signal=0.0002,
        )
        assert record.signal_id is not None
        assert len(record.signal_id) > 0
        assert record.symbol == "EURUSD"

    def test_create_order(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = logger.create_order(
            signal_id="sig-001",
            order_id="12345",
            symbol="EURUSD",
            direction="BUY",
            volume=0.1,
            requested_price=1.1002,
            sl=1.0950,
            tp=1.1150,
            spread_at_submission=0.0002,
            execution_latency_ms=150,
        )
        assert record.order_id == "12345"

    def test_create_fill(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = logger.create_fill(
            order_id="12345",
            fill_price=1.1003,
            fill_volume=0.1,
            actual_sl=1.0950,
            actual_tp=1.1150,
            slippage_pips=0.1,
        )
        assert record.fill_status == "FILLED"

    def test_create_exit(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        record = logger.create_exit(
            order_id="12345",
            exit_price=1.1150,
            exit_reason="TP",
            gross_pnl_pips=148.0,
            gross_pnl_currency=1480.0,
            trading_costs=7.0,
            net_pnl_pips=141.0,
            net_pnl_currency=1410.0,
            hold_duration_hours=24.0,
            hold_duration_bars=6,
        )
        assert record.exit_reason == "TP"


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------


class TestQueryMethods:
    def test_get_signals_empty(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        assert logger.get_signals() == []

    def test_get_signals(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        logger.create_signal(
            symbol="EURUSD", direction="BUY", swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        )
        signals = logger.get_signals()
        assert len(signals) == 1
        assert signals[0]["symbol"] == "EURUSD"

    def test_count_records(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        logger.create_signal(
            symbol="EURUSD", direction="BUY", swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        )
        logger.create_order(
            signal_id="sig-001", order_id="12345",
            symbol="EURUSD", direction="BUY", volume=0.1,
            requested_price=1.0, sl=0.9, tp=1.1,
            spread_at_submission=0.001, execution_latency_ms=100,
        )
        counts = logger.count_records()
        assert counts["signals"] == 1
        assert counts["orders"] == 1
        assert counts["fills"] == 0


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class TestReconciliation:
    def test_empty_reconciliation(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        report = logger.reconcile()
        assert report["total_signals"] == 0
        assert report["total_orders"] == 0

    def test_full_chain_reconciliation(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)

        # Signal
        sig = logger.create_signal(
            symbol="EURUSD", direction="BUY", swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        )

        # Order
        logger.create_order(
            signal_id=sig.signal_id, order_id="12345",
            symbol="EURUSD", direction="BUY", volume=0.1,
            requested_price=1.0, sl=0.9, tp=1.1,
            spread_at_submission=0.001, execution_latency_ms=100,
        )

        # Fill
        logger.create_fill(
            order_id="12345", fill_price=1.0001,
            fill_volume=0.1, actual_sl=0.9, actual_tp=1.1,
            slippage_pips=0.1,
        )

        # Exit
        logger.create_exit(
            order_id="12345", exit_price=1.1,
            exit_reason="TP", gross_pnl_pips=100,
            gross_pnl_currency=1000, trading_costs=7,
            net_pnl_pips=93, net_pnl_currency=930,
            hold_duration_hours=24, hold_duration_bars=6,
        )

        report = logger.reconcile()
        assert report["total_signals"] == 1
        assert report["total_orders"] == 1
        assert report["total_fills"] == 1
        assert report["total_exits"] == 1
        assert report["signal_to_order_rate"] == 1.0
        assert report["fill_rate"] == 1.0
        assert report["exit_rate"] == 1.0
        assert report["orphan_orders"] == []
        assert report["orphan_fills"] == []
        assert report["unmatched_signals"] == []

    def test_orphan_detection(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)

        # Signal without order
        sig1 = logger.create_signal(
            symbol="EURUSD", direction="BUY", swing_level=1.0,
            signal_bar_close=1.0, expected_entry=1.0,
            expected_sl=0.9, expected_tp=1.1,
            atr_at_signal=0.01, spread_at_signal=0.001,
        )

        # Order without fill
        sig2 = logger.create_signal(
            symbol="GBPUSD", direction="SELL", swing_level=1.2,
            signal_bar_close=1.2, expected_entry=1.2,
            expected_sl=1.3, expected_tp=1.1,
            atr_at_signal=0.02, spread_at_signal=0.002,
        )
        logger.create_order(
            signal_id=sig2.signal_id, order_id="67890",
            symbol="GBPUSD", direction="SELL", volume=0.05,
            requested_price=1.2, sl=1.3, tp=1.1,
            spread_at_submission=0.002, execution_latency_ms=200,
        )

        report = logger.reconcile()
        assert sig1.signal_id in report["unmatched_signals"]
        assert "67890" in report["orphan_orders"]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_empty_summary(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)
        s = logger.summary()
        assert s["total_exits"] == 0
        assert s["win_rate"] == 0.0

    def test_summary_with_exits(self, tmp_path: Path):
        logger = TradeLogger(tmp_path)

        # Winning trade
        logger.create_exit(
            order_id="1", exit_price=1.1, exit_reason="TP",
            gross_pnl_pips=100, gross_pnl_currency=1000,
            trading_costs=7, net_pnl_pips=93,
            net_pnl_currency=930, hold_duration_hours=24,
            hold_duration_bars=6,
        )

        # Losing trade
        logger.create_exit(
            order_id="2", exit_price=1.0, exit_reason="SL",
            gross_pnl_pips=-50, gross_pnl_currency=-500,
            trading_costs=7, net_pnl_pips=-57,
            net_pnl_currency=-570, hold_duration_hours=12,
            hold_duration_bars=3,
        )

        s = logger.summary()
        assert s["total_exits"] == 2
        assert s["winning_trades"] == 1
        assert s["losing_trades"] == 1
        assert s["win_rate"] == 0.5
        assert s["total_pnl"] == 360  # 930 - 570
        assert s["avg_pnl_per_trade"] == 180.0


# ---------------------------------------------------------------------------
# No forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.production.execution.trade_logger as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "MetaTrader5" not in line

    def test_no_network_calls(self):
        import nestquant.production.execution.trade_logger as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "import requests" not in line
            assert "import httpx" not in line
