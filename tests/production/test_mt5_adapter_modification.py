"""
NestQuant S8.6.8 — MT5 Adapter Modification Tests
====================================================

Mocked tests for MT5ExecutionAdapter.modify_position_stop().
Tests success, rejection, connection failure, and invalid ticket scenarios.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


import pytest
from nestquant.production.strategy.lifecycle.contracts import ModificationResult, PositionModificationRequest
from nestquant.production.execution.mt5_adapter import MT5ExecutionAdapter
from nestquant.production.execution.mt5_client import MT5Client, MT5Response


class TestMT5ClientModifyPosition:
    """Test MT5Client.modify_position() sends correct payload."""

    def test_modify_sends_ticket_and_sl(self):
        """Verify payload contains ticket and sl."""
        client = MT5Client(base_url="http://localhost:5001")
        client._request = MagicMock(return_value=MT5Response(
            ok=True, data={"result": {"retcode": 10009, "sl": 1.0980}},
            error=None, status_code=200,
        ))

        client.modify_position(ticket=12345, sl=1.0980)

        client._request.assert_called_once_with("POST", "/modify_position", {
            "position": 12345,
            "sl": 1.0980,
        })

    def test_modify_with_tp(self):
        """Verify payload includes tp when provided."""
        client = MT5Client(base_url="http://localhost:5001")
        client._request = MagicMock(return_value=MT5Response(
            ok=True, data={"result": {"retcode": 10009}},
            error=None, status_code=200,
        ))

        client.modify_position(ticket=12345, sl=1.0980, tp=1.1070)

        call_args = client._request.call_args
        payload = call_args[0][2]
        assert payload["sl"] == 1.0980
        assert payload["tp"] == 1.1070


class TestMT5AdapterModifyPositionStop:
    """Test MT5ExecutionAdapter.modify_position_stop() with mocked client."""

    def setup_method(self):
        self.client = MagicMock(spec=MT5Client)
        self.adapter = MT5ExecutionAdapter(client=self.client, magic=0, deviation=10)

    def test_successful_modification(self):
        """Happy path: broker confirms modification."""
        self.client.modify_position.return_value = MT5Response(
            ok=True,
            data={"result": {"retcode": 10009, "sl": 1.0980}},
            error=None,
            status_code=200,
        )

        request = PositionModificationRequest(
            trade_id="12345", symbol="EURUSD",
            new_sl=1.0980, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)

        assert result.success is True
        assert result.requested_sl == 1.0980
        assert result.broker_sl == 1.0980
        assert result.sl_matches is True

    def test_broker_rejection(self):
        """Broker rejects modification (invalid stops)."""
        self.client.modify_position.return_value = MT5Response(
            ok=True,
            data={"result": {"retcode": 10014, "comment": "Invalid stops"}},
            error=None,
            status_code=200,
        )

        request = PositionModificationRequest(
            trade_id="12345", symbol="EURUSD",
            new_sl=1.0980, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)

        assert result.success is False
        assert "retcode 10014" in result.error

    def test_connection_failure(self):
        """MT5 bridge unreachable."""
        from nestquant.production.execution.mt5_client import MT5ConnectionError
        self.client.modify_position.side_effect = MT5ConnectionError("Connection refused")

        request = PositionModificationRequest(
            trade_id="12345", symbol="EURUSD",
            new_sl=1.0980, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)

        assert result.success is False
        assert "Connection failed" in result.error

    def test_bridge_error_response(self):
        """Bridge returns HTTP error."""
        self.client.modify_position.return_value = MT5Response(
            ok=False,
            data={},
            error="Bridge internal error",
            status_code=500,
        )

        request = PositionModificationRequest(
            trade_id="12345", symbol="EURUSD",
            new_sl=1.0980, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)

        assert result.success is False
        assert "Bridge internal error" in result.error

    def test_invalid_ticket(self):
        """Non-numeric ticket string."""
        request = PositionModificationRequest(
            trade_id="not_a_number", symbol="EURUSD",
            new_sl=1.0980, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)

        assert result.success is False
        assert "Invalid ticket" in result.error

    def test_connection_error_not_caught(self):
        """MT5ConnectionError is properly caught."""
        from nestquant.production.execution.mt5_client import MT5ConnectionError
        self.client.modify_position.side_effect = MT5ConnectionError("timeout")

        request = PositionModificationRequest(
            trade_id="12345", symbol="EURUSD",
            new_sl=1.0980, reason="trailing",
        )
        result = self.adapter.modify_position_stop(request)

        assert result.success is False
        assert result.error is not None
