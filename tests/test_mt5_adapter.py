"""
Tests for nestquant.execution.mt5_adapter module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from nestquant.execution.adapter import AdapterValidationError
from nestquant.execution.contracts import (
    Direction,
    ExecutionResult,
    ExecutionStatus,
    OrderRequest,
)
from nestquant.execution.mt5_adapter import (
    MT5ExecutionAdapter,
    nestquant_to_mt5_symbol,
    mt5_to_nestquant_symbol,
)
from nestquant.execution.mt5_client import MT5Client, MT5Response, MT5ConnectionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_request(**overrides) -> OrderRequest:
    defaults = dict(
        pair="EUR/USD",
        direction=Direction.BUY,
        lot_size=0.10,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1150,
        policy_version="1.0.0",
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)


def _success_response(**overrides) -> MT5Response:
    defaults = dict(
        ok=True,
        data={
            "status": "success",
            "ticket": 12345,
            "price": 1.1002,
            "volume": 0.10,
        },
        status_code=200,
    )
    defaults.update(overrides)
    if "data" in overrides and isinstance(overrides["data"], dict):
        defaults["data"] = overrides["data"]
    return MT5Response(**defaults)


def _error_response(error: str = "Error", status_code: int = 200) -> MT5Response:
    return MT5Response(
        ok=False,
        data={"status": "error", "error": error},
        error=error,
        status_code=status_code,
    )


def _mock_client(**method_returns) -> MT5Client:
    """Create a mock MT5Client with configurable method returns."""
    client = MagicMock(spec=MT5Client)
    for method, return_val in method_returns.items():
        getattr(client, method).return_value = return_val
    return client


# ---------------------------------------------------------------------------
# Symbol conversion
# ---------------------------------------------------------------------------


class TestSymbolConversion:
    def test_nestquant_to_mt5_eurusd(self):
        assert nestquant_to_mt5_symbol("EUR/USD") == "EURUSD"

    def test_nestquant_to_mt5_gbpjpy(self):
        assert nestquant_to_mt5_symbol("GBP/JPY") == "GBPJPY"

    def test_nestquant_to_mt5_audnzd(self):
        assert nestquant_to_mt5_symbol("AUD/NZD") == "AUDNZD"

    def test_mt5_to_nestquant_eurusd(self):
        assert mt5_to_nestquant_symbol("EURUSD") == "EUR/USD"

    def test_mt5_to_nestquant_gbpjpy(self):
        assert mt5_to_nestquant_symbol("GBPJPY") == "GBP/JPY"

    def test_mt5_to_nestquant_unknown(self):
        # Unknown symbol returned as-is
        assert mt5_to_nestquant_symbol("XYZXYZ") == "XYZXYZ"

    def test_roundtrip(self):
        pairs = ["EUR/USD", "GBP/JPY", "AUD/NZD", "USD/CAD"]
        for pair in pairs:
            mt5_sym = nestquant_to_mt5_symbol(pair)
            back = mt5_to_nestquant_symbol(mt5_sym)
            assert back == pair


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestMT5ExecutionAdapterConstruction:
    def test_default_construction(self):
        adapter = MT5ExecutionAdapter()
        assert adapter.name == "mt5"
        assert adapter.client is not None

    def test_custom_client(self):
        client = MT5Client(base_url="http://custom:9999")
        adapter = MT5ExecutionAdapter(client=client)
        assert adapter.client is client
        assert adapter.client.base_url == "http://custom:9999"

    def test_custom_magic_and_deviation(self):
        adapter = MT5ExecutionAdapter(magic=12345, deviation=20)
        assert adapter._magic == 12345
        assert adapter._deviation == 20

    def test_repr(self):
        adapter = MT5ExecutionAdapter(magic=42, deviation=5)
        r = repr(adapter)
        assert "MT5ExecutionAdapter" in r
        assert "42" in r
        assert "5" in r


# ---------------------------------------------------------------------------
# Successful execution
# ---------------------------------------------------------------------------


class TestSuccessfulExecution:
    def test_market_buy_fills(self):
        client = _mock_client(
            send_order=_success_response(
                data={
                    "status": "success",
                    "ticket": 12345,
                    "price": 1.1002,
                    "volume": 0.10,
                }
            )
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_filled
        assert result.order_id == "12345"
        assert result.fill_price == 1.1002
        assert result.status == ExecutionStatus.FILLED

    def test_market_sell_fills(self):
        client = _mock_client(
            send_order=_success_response(
                data={
                    "status": "success",
                    "ticket": 12346,
                    "price": 1.2805,
                    "volume": 0.05,
                }
            )
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(
            _valid_request(
                pair="GBP/USD",
                direction=Direction.SELL,
                lot_size=0.05,
                entry_price=1.2800,
                stop_loss=1.2850,
                take_profit=1.2650,
            )
        )

        assert result.is_filled
        assert result.order_id == "12346"
        assert result.fill_price == 1.2805

    def test_slippage_calculation(self):
        client = _mock_client(
            send_order=_success_response(
                data={
                    "status": "success",
                    "ticket": 12347,
                    "price": 1.1003,  # 3 pips above requested 1.1000
                    "volume": 0.10,
                }
            )
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request(entry_price=1.1000))

        assert result.is_filled
        # 0.0003 price diff / 0.0001 pip = 3.0 pips
        assert result.slippage_pips == pytest.approx(3.0, abs=0.01)

    def test_zero_slippage(self):
        client = _mock_client(
            send_order=_success_response(
                data={
                    "status": "success",
                    "ticket": 12348,
                    "price": 1.1000,
                    "volume": 0.10,
                }
            )
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request(entry_price=1.1000))

        assert result.slippage_pips == 0.0

    def test_client_receives_correct_params(self):
        client = _mock_client(send_order=_success_response())
        adapter = MT5ExecutionAdapter(client=client, magic=42, deviation=15)

        adapter.execute(
            _valid_request(
                pair="GBP/JPY",
                direction=Direction.SELL,
                lot_size=0.05,
                entry_price=190.0,
                stop_loss=190.5,
                take_profit=189.0,
            )
        )

        call_kwargs = client.send_order.call_args[1]
        assert call_kwargs["symbol"] == "GBPJPY"
        assert call_kwargs["direction"] == "SELL"
        assert call_kwargs["volume"] == 0.05
        assert call_kwargs["sl"] == 190.5
        assert call_kwargs["tp"] == 189.0
        assert call_kwargs["magic"] == 42
        assert call_kwargs["deviation"] == 15


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_broker_rejection_insufficient_margin(self):
        client = _mock_client(
            send_order=_error_response("Not enough money")
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_rejected
        assert "Not enough money" in result.rejection_reason

    def test_broker_rejection_invalid_price(self):
        client = _mock_client(
            send_order=_error_response("Invalid price")
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_rejected
        assert "Invalid price" in result.rejection_reason

    def test_broker_rejection_invalid_stops(self):
        client = _mock_client(
            send_order=_error_response("Invalid stops")
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_rejected

    def test_broker_rejection_market_closed(self):
        client = _mock_client(
            send_order=_error_response("Market closed")
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_rejected

    def test_unknown_error_is_execution_error(self):
        client = _mock_client(
            send_order=_error_response("Something unexpected happened")
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_error
        assert not result.is_filled
        assert not result.is_rejected

    def test_connection_error_returns_error(self):
        client = MagicMock(spec=MT5Client)
        client.send_order.side_effect = MT5ConnectionError("Connection refused")

        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_error
        assert "Connection failed" in result.rejection_reason

    def test_missing_ticket_in_response(self):
        client = _mock_client(
            send_order=MT5Response(
                ok=True,
                data={"status": "success"},
                status_code=200,
            )
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())

        assert result.is_error
        assert "Missing fill data" in result.rejection_reason


# ---------------------------------------------------------------------------
# Validation boundary
# ---------------------------------------------------------------------------


class TestValidationBoundary:
    def test_min_lot_size_rejected(self):
        adapter = MT5ExecutionAdapter()
        with pytest.raises(AdapterValidationError) as exc_info:
            adapter.execute(_valid_request(lot_size=0.001))
        assert "minimum lot size" in str(exc_info.value).lower()

    def test_valid_lot_size_accepted(self):
        client = _mock_client(send_order=_success_response())
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request(lot_size=0.01))
        assert result.is_filled

    def test_large_lot_size_accepted(self):
        """No max lot enforcement at adapter level — broker handles this."""
        client = _mock_client(send_order=_success_response())
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request(lot_size=10.0))
        assert result.is_filled


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_healthy(self):
        client = _mock_client(
            health=_response(ok=True, data={"status": "success", "mt5_connected": True})
        )
        adapter = MT5ExecutionAdapter(client=client)
        assert adapter.health_check() is True

    def test_unhealthy(self):
        client = _mock_client(
            health=_response(ok=False, error="MT5 not connected")
        )
        adapter = MT5ExecutionAdapter(client=client)
        assert adapter.health_check() is False

    def test_connection_failure(self):
        client = MagicMock(spec=MT5Client)
        client.health.side_effect = MT5ConnectionError("No route")
        adapter = MT5ExecutionAdapter(client=client)
        assert adapter.health_check() is False


# ---------------------------------------------------------------------------
# Account info
# ---------------------------------------------------------------------------


class TestAccountInfo:
    def test_get_account_info(self):
        account_data = {
            "balance": 5000000,
            "equity": 5001234.56,
            "margin": 1234.56,
            "leverage": 100,
        }
        client = _mock_client(
            get_account_info=_response(ok=True, data=account_data)
        )
        adapter = MT5ExecutionAdapter(client=client)
        info = adapter.get_account_info()
        assert info is not None
        assert info["balance"] == 5000000

    def test_get_account_info_failure(self):
        client = _mock_client(
            get_account_info=_response(ok=False, error="Not connected")
        )
        adapter = MT5ExecutionAdapter(client=client)
        info = adapter.get_account_info()
        assert info is None


# ---------------------------------------------------------------------------
# Get positions
# ---------------------------------------------------------------------------


class TestGetPositions:
    def test_get_positions(self):
        positions = [
            {"ticket": 1, "symbol": "EURUSD", "volume": 0.1},
            {"ticket": 2, "symbol": "GBPUSD", "volume": 0.05},
        ]
        client = _mock_client(
            get_positions=_response(ok=True, data={"positions": positions})
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.get_positions()
        assert len(result) == 2

    def test_get_positions_empty(self):
        client = _mock_client(
            get_positions=_response(ok=True, data={"positions": []})
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.get_positions()
        assert result == []

    def test_get_positions_failure(self):
        client = _mock_client(
            get_positions=_response(ok=False, error="Timeout")
        )
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.get_positions()
        assert result == []


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_execution_adapter_protocol(self):
        from nestquant.execution.orchestration import ExecutionAdapter
        adapter = MT5ExecutionAdapter()
        assert isinstance(adapter, ExecutionAdapter)

    def test_satisfies_base_adapter(self):
        from nestquant.execution.adapter import BaseExecutionAdapter
        adapter = MT5ExecutionAdapter()
        assert isinstance(adapter, BaseExecutionAdapter)

    def test_execute_returns_execution_result(self):
        client = _mock_client(send_order=_success_response())
        adapter = MT5ExecutionAdapter(client=client)
        result = adapter.execute(_valid_request())
        assert isinstance(result, ExecutionResult)


# ---------------------------------------------------------------------------
# No forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.execution.mt5_adapter as mod
        source = open(mod.__file__).read()
        # Only check actual import lines, not docstrings
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "MetaTrader5" not in line
            assert "import mt5" not in line

    def test_no_research_import(self):
        import nestquant.execution.mt5_adapter as mod
        source = open(mod.__file__).read()
        assert "from nestquant.research" not in source
        assert "import nestquant.research" not in source

    def test_no_strategy_import(self):
        import nestquant.execution.mt5_adapter as mod
        source = open(mod.__file__).read()
        assert "from nestquant.zscore" not in source
        assert "import nestquant.zscore" not in source

    def test_no_logging(self):
        import nestquant.execution.mt5_adapter as mod
        source = open(mod.__file__).read()
        assert "import logging" not in source
        assert "logger" not in source

    def test_no_monitoring(self):
        import nestquant.execution.mt5_adapter as mod
        source = open(mod.__file__).read()
        assert "import telemetry" not in source
        assert "send_alert" not in source
        assert "notify" not in source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response(**kwargs) -> MT5Response:
    """Create an MT5Response with defaults."""
    defaults = {"ok": True, "data": {}, "status_code": 200}
    defaults.update(kwargs)
    return MT5Response(**defaults)
