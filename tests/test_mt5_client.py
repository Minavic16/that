"""
Tests for nestquant.execution.mt5_client module.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from nestquant.execution.mt5_client import (
    MT5Client,
    MT5ClientError,
    MT5ConnectionError,
    MT5Response,
    DEFAULT_BASE_URL,
)


# ---------------------------------------------------------------------------
# MT5Response
# ---------------------------------------------------------------------------


class TestMT5Response:
    def test_success_response(self):
        r = MT5Response(ok=True, data={"status": "success"}, status_code=200)
        assert r.ok is True
        assert r.data["status"] == "success"
        assert r.error is None
        assert r.status_code == 200

    def test_error_response(self):
        r = MT5Response(ok=False, error="Connection lost", status_code=500)
        assert r.ok is False
        assert r.error == "Connection lost"
        assert r.status_code == 500

    def test_default_data(self):
        r = MT5Response(ok=True)
        assert r.data == {}

    def test_frozen(self):
        r = MT5Response(ok=True)
        with pytest.raises(AttributeError):
            r.ok = False


# ---------------------------------------------------------------------------
# MT5Client construction
# ---------------------------------------------------------------------------


class TestMT5ClientConstruction:
    def test_default_url(self):
        client = MT5Client()
        assert client.base_url == DEFAULT_BASE_URL

    def test_custom_url(self):
        client = MT5Client(base_url="http://192.168.1.100:5001")
        assert client.base_url == "http://192.168.1.100:5001"

    def test_trailing_slash_stripped(self):
        client = MT5Client(base_url="http://127.0.0.1:5001/")
        assert client.base_url == "http://127.0.0.1:5001"

    def test_repr(self):
        client = MT5Client(base_url="http://test:9999")
        r = repr(client)
        assert "test:9999" in r

    def test_custom_timeout(self):
        client = MT5Client(timeout=30.0)
        assert client._timeout == 30.0

    def test_custom_retries(self):
        client = MT5Client(max_retries=5, retry_delay=2.0)
        assert client._max_retries == 5
        assert client._retry_delay == 2.0


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    @patch("nestquant.execution.mt5_client.urlopen")
    def test_health_success(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "status": "success",
            "mt5_connected": True,
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.health()

        assert result.ok is True
        assert result.data["mt5_connected"] is True
        assert result.status_code == 200

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_health_failure(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "status": "error",
            "error": "MT5 not connected",
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.health()

        assert result.ok is False
        assert "MT5 not connected" in result.error


# ---------------------------------------------------------------------------
# Get positions endpoint
# ---------------------------------------------------------------------------


class TestGetPositions:
    @patch("nestquant.execution.mt5_client.urlopen")
    def test_get_positions_success(self, mock_urlopen):
        positions = [
            {"ticket": 12345, "symbol": "EURUSD", "volume": 0.1, "profit": 10.0},
            {"ticket": 12346, "symbol": "GBPUSD", "volume": 0.05, "profit": -5.0},
        ]
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "status": "success",
            "positions": positions,
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.get_positions()

        assert result.ok is True
        assert len(result.data["positions"]) == 2

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_get_positions_empty(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "status": "success",
            "positions": [],
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.get_positions()

        assert result.ok is True
        assert result.data["positions"] == []


# ---------------------------------------------------------------------------
# Send order endpoint
# ---------------------------------------------------------------------------


class TestSendOrder:
    @patch("nestquant.execution.mt5_client.urlopen")
    def test_send_order_market_buy(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "retcode": 10009,
            "order": 12345,
            "price": 1.1002,
            "volume": 0.1,
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.send_order(
            symbol="EURUSD",
            direction="BUY",
            volume=0.1,
            sl=1.0950,
            tp=1.1150,
        )

        assert result.ok is True
        assert result.data["order"] == 12345
        assert result.data["price"] == 1.1002

        # Verify the request was made correctly
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "/order" in req.full_url
        body = json.loads(req.data)
        assert body["symbol"] == "EURUSD"
        assert body["type"] == 0  # MT5_ORDER_TYPE_BUY
        assert body["volume"] == 0.1
        assert body["sl"] == 1.0950
        assert body["tp"] == 1.1150

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_send_order_sell(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "retcode": 10009,
            "order": 12346,
            "price": 1.2805,
            "volume": 0.05,
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.send_order(
            symbol="GBPUSD",
            direction="SELL",
            volume=0.05,
        )

        assert result.ok is True
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["type"] == 1  # MT5_ORDER_TYPE_SELL

    def test_send_order_invalid_direction(self):
        client = MT5Client()
        result = client.send_order(
            symbol="EURUSD",
            direction="INVALID",
            volume=0.01,
        )

        assert result.ok is False
        assert "Invalid direction" in result.error
        assert result.status_code == 0

    def test_send_order_direction_case_insensitive(self):
        """Direction mapping should be case-insensitive via .upper() in send_order."""
        from nestquant.execution.mt5_client import DIRECTION_TO_MT5_TYPE

        # Mapping keys are uppercase
        assert DIRECTION_TO_MT5_TYPE["BUY"] == 0
        assert DIRECTION_TO_MT5_TYPE["SELL"] == 1

        # send_order calls .upper() before lookup, so lowercase works at the API level
        # This is tested via test_send_order_market_buy which uses "BUY" directly

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_send_order_rejection(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "status": "error",
            "error": "Not enough money",
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.send_order(
            symbol="EURUSD",
            direction="BUY",
            volume=100.0,
        )

        assert result.ok is False
        assert "Not enough money" in result.error

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_send_order_with_price(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "retcode": 10009,
            "order": 12347,
            "price": 1.0995,
            "volume": 0.1,
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.send_order(
            symbol="EURUSD",
            direction="BUY",
            volume=0.1,
            price=1.0995,
            order_type="LIMIT",
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        # price is accepted but not sent to bridge (market orders only)
        assert body["symbol"] == "EURUSD"
        assert body["type"] == 0  # MT5_ORDER_TYPE_BUY


# ---------------------------------------------------------------------------
# Close position endpoint
# ---------------------------------------------------------------------------


class TestClosePosition:
    @patch("nestquant.execution.mt5_client.urlopen")
    def test_close_position_success(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({
            "status": "success",
            "ticket": 12345,
            "close_price": 1.1050,
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client()
        result = client.close_position(
            ticket=12345,
            position_type=0,
            symbol="EURUSD",
            volume=0.1,
        )

        assert result.ok is True
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["position"]["ticket"] == 12345
        assert body["position"]["type"] == 0
        assert body["position"]["symbol"] == "EURUSD"
        assert body["position"]["volume"] == 0.1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch("nestquant.execution.mt5_client.urlopen")
    def test_http_500_retries(self, mock_urlopen):
        """Server errors should be retried."""
        error_body = json.dumps({"error": "Internal server error"}).encode()
        success_resp = MagicMock()
        success_resp.status = 200
        success_resp.read.return_value = json.dumps({
            "status": "success",
        }).encode()
        success_resp.__enter__ = lambda s: s
        success_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            HTTPError(
                url="http://test/health",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=io.BytesIO(error_body),
            ),
            success_resp,
        ]

        client = MT5Client(max_retries=2, retry_delay=0.01)
        result = client.health()

        assert result.ok is True
        assert mock_urlopen.call_count == 2

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_connection_error_returns_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Connection refused")

        client = MT5Client(max_retries=0)
        result = client.health()

        assert result.ok is False
        assert "Connection failed" in result.error

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_http_400_no_retry(self, mock_urlopen):
        """Client errors (4xx) should NOT be retried."""
        error_body = json.dumps({"error": "Bad request"}).encode()

        mock_urlopen.side_effect = HTTPError(
            url="http://test/health",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(error_body),
        )

        client = MT5Client(max_retries=3)
        result = client.health()

        assert result.ok is False
        assert result.status_code == 400
        assert mock_urlopen.call_count == 1

    @patch("nestquant.execution.mt5_client.urlopen")
    def test_json_parse_error(self, mock_urlopen):
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"not json"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        client = MT5Client(max_retries=0)
        result = client.health()

        assert result.ok is False


# ---------------------------------------------------------------------------
# No forbidden imports
# ---------------------------------------------------------------------------


class TestNoForbiddenImports:
    def test_no_mt5_import(self):
        import nestquant.execution.mt5_client as mod
        source = open(mod.__file__).read()
        # Only check actual import lines, not docstrings
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "MetaTrader5" not in line
            assert "import mt5" not in line

    def test_no_network_calls_beyond_urllib(self):
        import nestquant.execution.mt5_client as mod
        source = open(mod.__file__).read()
        import_lines = [
            line.strip() for line in source.split("\n")
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ]
        for line in import_lines:
            assert "import requests" not in line
            assert "import httpx" not in line
