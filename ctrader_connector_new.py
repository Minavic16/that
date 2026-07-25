"""
cTrader Open API Connector — Async TCP/Protobuf
Uses asyncio TCP with length-prefixed protobuf messages.
Single reader loop dispatches messages to pending waiters.
"""
import os
import json
import struct
import time
import uuid
import asyncio
import logging
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field

import requests

from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (
    ProtoMessage, ProtoErrorRes, ProtoHeartbeatEvent
)
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq, ProtoOAApplicationAuthRes,
    ProtoOAAccountAuthReq, ProtoOAAccountAuthRes,
    ProtoOAGetAccountListByAccessTokenReq, ProtoOAGetAccountListByAccessTokenRes,
    ProtoOATraderReq, ProtoOATraderRes,
    ProtoOAReconcileReq, ProtoOAReconcileRes,
    ProtoOAExecutionEvent,
    ProtoOASubscribeSpotsReq, ProtoOASubscribeSpotsRes,
    ProtoOASpotEvent,
    ProtoOANewOrderReq,
    ProtoOAClosePositionReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAErrorRes,
    ProtoOASymbolsListReq, ProtoOASymbolsListRes,
    ProtoOAOrderErrorEvent,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOAPosition, ProtoOAOrder, ProtoOALightSymbol
)

logger = logging.getLogger(__name__)

PROTOBUF_DEMO_HOST = "demo.ctraderapi.com"
PROTOBUF_LIVE_HOST = "live.ctraderapi.com"
PROTOBUF_PORT = 5035
TOKEN_URI = "https://openapi.ctrader.com/apps/token"

PT_HEARTBEAT = 51
PT_ERROR_OLD = 50
PT_APP_AUTH_REQ = 2100
PT_APP_AUTH_RES = 2101
PT_ACCOUNT_AUTH_REQ = 2102
PT_ACCOUNT_AUTH_RES = 2103
PT_NEW_ORDER_REQ = 2106
PT_AMEND_POSITION_SLTP_REQ = 2110
PT_CLOSE_POSITION_REQ = 2111
PT_SYMBOLS_LIST_REQ = 2114
PT_SYMBOLS_LIST_RES = 2115
PT_TRADER_REQ = 2121
PT_TRADER_RES = 2122
PT_RECONCILE_REQ = 2124
PT_RECONCILE_RES = 2125
PT_EXECUTION_EVENT = 2126
PT_SUBSCRIBE_SPOTS_REQ = 2127
PT_SUBSCRIBE_SPOTS_RES = 2128
PT_SPOT_EVENT = 2131
PT_ERROR_RES = 2142
PT_ORDER_ERROR_EVENT = 2132
PT_GET_ACCOUNTS_REQ = 2149
PT_GET_ACCOUNTS_RES = 2150


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    fill_price: Optional[float] = None
    error: Optional[str] = None
    slippage: float = 0.0


_RESP_TYPES = {
    PT_APP_AUTH_RES: ProtoOAApplicationAuthRes,
    PT_ACCOUNT_AUTH_RES: ProtoOAAccountAuthRes,
    PT_GET_ACCOUNTS_RES: ProtoOAGetAccountListByAccessTokenRes,
    PT_TRADER_RES: ProtoOATraderRes,
    PT_SYMBOLS_LIST_RES: ProtoOASymbolsListRes,
    PT_RECONCILE_RES: ProtoOAReconcileRes,
    PT_SUBSCRIBE_SPOTS_RES: ProtoOASubscribeSpotsRes,
}


class CTraderConnector:

    def __init__(self, client_id: str = "", client_secret: str = "",
                 access_token: str = "", refresh_token: str = "",
                 account_id: str = "", demo: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.account_id = account_id
        self.demo = demo

        self.connected = False
        self._reader = None
        self._writer = None
        self._running = False
        self._listen_task = None
        self._heartbeat_task = None
        self._write_lock = asyncio.Lock()
        self._last_send_time = 0.0

        self._waiters: Dict[int, asyncio.Future] = {}
        self._spots: Dict[int, Dict] = {}
        self._positions: List = []
        self._orders: List = []
        self._symbols: Dict[int, Dict] = {}
        self._symbol_names: Dict[str, int] = {}
        self._symbol_digits: Dict[int, int] = {}
        self._trader_info = None

        self._on_spot: Optional[Callable] = None
        self._on_execution: Optional[Callable] = None
        self._last_order_error: Optional[str] = None

    def set_spot_callback(self, cb: Callable):
        self._on_spot = cb

    def set_execution_callback(self, cb: Callable):
        self._on_execution = cb

    # ── TCP I/O ──────────────────────────────────────────────────────────
    async def _send_raw(self, data: bytes):
        async with self._write_lock:
            header = struct.pack('>I', len(data))
            self._writer.write(header + data)
            await self._writer.drain()
            self._last_send_time = asyncio.get_event_loop().time()

    async def _send_msg(self, msg, payload_type: int = None, client_msg_id: str = None):
        if client_msg_id is None:
            client_msg_id = str(uuid.uuid4())
        if payload_type is not None:
            outer = ProtoMessage()
            outer.payloadType = payload_type
            outer.payload = msg.SerializeToString()
            outer.clientMsgId = client_msg_id
            await self._send_raw(outer.SerializeToString())
        else:
            await self._send_raw(msg.SerializeToString())
        return client_msg_id

    async def _heartbeat_loop(self):
        """Send proactive heartbeats every 20s (matching SDK behavior)."""
        while self._running:
            await asyncio.sleep(5)
            if not self._running:
                break
            now = asyncio.get_event_loop().time()
            if now - self._last_send_time > 20:
                hb = ProtoHeartbeatEvent()
                outer = ProtoMessage()
                outer.payloadType = PT_HEARTBEAT
                outer.payload = hb.SerializeToString()
                try:
                    await self._send_raw(outer.SerializeToString())
                    logger.debug("Proactive heartbeat sent")
                except Exception:
                    break

    async def _recv_loop(self):
        """Single reader loop — dispatches all incoming messages."""
        while self._running:
            try:
                header = await self._reader.readexactly(4)
                length = struct.unpack('>I', header)[0]
                data = await self._reader.readexactly(length)

                outer = ProtoMessage()
                outer.ParseFromString(data)
                pt = outer.payloadType
                client_msg_id = outer.clientMsgId

                if pt == PT_HEARTBEAT:
                    hb = ProtoHeartbeatEvent()
                    hb.ParseFromString(outer.payload)
                    # Heartbeat reply must NOT have clientMsgId
                    outer_reply = ProtoMessage()
                    outer_reply.payloadType = PT_HEARTBEAT
                    outer_reply.payload = hb.SerializeToString()
                    await self._send_raw(outer_reply.SerializeToString())
                    logger.info("Heartbeat responded")

                elif pt == PT_SPOT_EVENT:
                    spot = ProtoOASpotEvent()
                    spot.ParseFromString(outer.payload)
                    self._spots[spot.symbolId] = {
                        'bid': spot.bid, 'ask': spot.ask,
                        'timestamp': spot.timestamp,
                    }
                    if self._on_spot:
                        sym = self._symbols.get(spot.symbolId, {}).get('name', '')
                        self._on_spot(sym, spot.bid, spot.ask)

                elif pt == PT_EXECUTION_EVENT:
                    evt = ProtoOAExecutionEvent()
                    evt.ParseFromString(outer.payload)
                    self._handle_execution(evt)
                    # Resolve waiter only on ORDER_FILLED or ORDER_REJECTED (not ORDER_ACCEPTED)
                    exec_type = evt.executionType
                    if client_msg_id and client_msg_id in self._waiters:
                        if exec_type in (3, 7, 8, 11):  # FILLED, REJECTED, CANCEL_REJECTED, PARTIAL_FILL
                            fut = self._waiters.pop(client_msg_id)
                            if not fut.done():
                                fut.set_result(outer)
                    if self._on_execution:
                        self._on_execution(evt)

                elif pt == PT_ORDER_ERROR_EVENT:
                    evt = ProtoOAOrderErrorEvent()
                    evt.ParseFromString(outer.payload)
                    logger.error(f"Order error: {evt.errorCode} desc={evt.description} orderId={evt.orderId}")
                    # Store error for callers to check
                    self._last_order_error = evt.errorCode
                    # Resolve waiter with error
                    if client_msg_id and client_msg_id in self._waiters:
                        fut = self._waiters.pop(client_msg_id)
                        if not fut.done():
                            fut.set_result(None)

                elif client_msg_id and client_msg_id in self._waiters:
                    # Match by clientMsgId
                    fut = self._waiters.pop(client_msg_id)
                    if not fut.done():
                        fut.set_result(outer)

                elif pt == PT_SUBSCRIBE_SPOTS_RES:
                    pass  # Spot subscription acknowledgments, ignore

                elif pt == PT_ERROR_RES or pt == PT_ERROR_OLD:
                    err = ProtoOAErrorRes()
                    err.ParseFromString(outer.payload)
                    logger.warning(f"API error: {err.errorCode} - {err.description}")
                    # If someone is waiting for this, resolve with None
                    for msg_id in list(self._waiters.keys()):
                        fut = self._waiters.pop(msg_id)
                        if not fut.done():
                            fut.set_result(None)
                            break

                else:
                    logger.debug(f"Unhandled message type: {pt} clientMsgId={client_msg_id}")

            except asyncio.CancelledError:
                break
            except asyncio.IncompleteReadError:
                logger.error("Connection lost")
                self._running = False
                break
            except Exception as e:
                logger.error(f"Recv error: {e}")
                await asyncio.sleep(0.1)

    async def _wait_for(self, client_msg_id: str, timeout: float = 10):
        """Wait for a response by clientMsgId. Returns parsed inner message."""
        fut = asyncio.get_event_loop().create_future()
        self._waiters[client_msg_id] = fut
        try:
            outer = await asyncio.wait_for(fut, timeout)
            if outer is None:
                return None
            # Determine the response class based on payload type
            pt = outer.payloadType
            cls = _RESP_TYPES.get(pt)
            logger.debug(f"Response: pt={pt}, clientMsgId={outer.clientMsgId}, has_payload={bool(outer.payload)}")
            if cls and outer.payload:
                inner = cls()
                inner.ParseFromString(outer.payload)
                return inner
            logger.warning(f"No parser for pt={pt} or empty payload, returning raw ProtoMessage")
            return outer
        except asyncio.TimeoutError:
            self._waiters.pop(client_msg_id, None)
            logger.error(f"Timeout waiting for clientMsgId {client_msg_id}")
            return None

    # ── Connect Flow ─────────────────────────────────────────────────────
    async def connect(self) -> bool:
        try:
            if not self.access_token:
                if not await self._refresh_token():
                    logger.error("Failed to refresh access token")
                    return False

            import ssl as _ssl
            host = PROTOBUF_DEMO_HOST if self.demo else PROTOBUF_LIVE_HOST
            logger.info(f"Connecting to {host}:{PROTOBUF_PORT} (SSL)")
            ctx = _ssl.create_default_context()
            self._reader, self._writer = await asyncio.open_connection(
                host, PROTOBUF_PORT, ssl=ctx
            )
            logger.info("TCP connected")

            self._running = True
            self._listen_task = asyncio.create_task(self._recv_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._last_send_time = asyncio.get_event_loop().time()

            if not await self._app_auth():
                return False
            if not await self._get_accounts():
                return False
            if not await self._account_auth():
                return False
            if not await self._get_trader():
                return False
            await self._get_symbols_list()
            await self._reconcile()
            await self._subscribe_spots()

            self.connected = True
            logger.info(f"Connected! Account: {self.account_id}, Balance: ${self.get_balance():.2f}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self):
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            self._writer.close()
        self.connected = False
        logger.info("Disconnected")

    # ── Auth ─────────────────────────────────────────────────────────────
    async def _refresh_token(self) -> bool:
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }
        try:
            resp = requests.post(TOKEN_URI, data=data)
            if resp.status_code == 200:
                result = resp.json()
                self.access_token = result.get("access_token", "")
                self.refresh_token = result.get("refresh_token", "")
                logger.info("Token refreshed")
                return True
            logger.error(f"Token refresh failed: {resp.text}")
            return False
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False

    async def _app_auth(self) -> bool:
        msg = ProtoOAApplicationAuthReq()
        msg.clientId = self.client_id
        msg.clientSecret = self.client_secret
        msg_id = await self._send_msg(msg, PT_APP_AUTH_REQ)
        resp = await self._wait_for(msg_id, timeout=10)
        if resp is not None:
            logger.info("App authenticated")
            return True
        return False

    async def _get_accounts(self) -> bool:
        msg = ProtoOAGetAccountListByAccessTokenReq()
        msg.accessToken = self.access_token
        msg_id = await self._send_msg(msg, PT_GET_ACCOUNTS_REQ)
        resp = await self._wait_for(msg_id, timeout=10)
        if resp is not None and hasattr(resp, 'ctidTraderAccount'):
            for acc in resp.ctidTraderAccount:
                acc_id = acc.ctidTraderAccountId
                logger.info(f"Found account: {acc_id}")
                if str(acc_id) == self.account_id:
                    return True
            if len(resp.ctidTraderAccount) > 0:
                self.account_id = str(resp.ctidTraderAccount[0].ctidTraderAccountId)
                logger.info(f"Using account: {self.account_id}")
                return True
        logger.error("No accounts found")
        return False

    async def _account_auth(self) -> bool:
        msg = ProtoOAAccountAuthReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg.accessToken = self.access_token
        msg_id = await self._send_msg(msg, PT_ACCOUNT_AUTH_REQ)
        resp = await self._wait_for(msg_id, timeout=10)
        if resp is not None:
            logger.info(f"Account {self.account_id} authenticated")
            return True
        return False

    async def _get_trader(self) -> bool:
        msg = ProtoOATraderReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg_id = await self._send_msg(msg, PT_TRADER_REQ)
        resp = await self._wait_for(msg_id, timeout=10)
        if resp is not None:
            self._trader_info = resp.trader
            logger.info(f"Balance: ${self.get_balance():.2f}")
            return True
        return False

    async def _get_symbols_list(self):
        msg = ProtoOASymbolsListReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg.includeArchivedSymbols = False
        msg_id = await self._send_msg(msg, PT_SYMBOLS_LIST_REQ)
        resp = await self._wait_for(msg_id, timeout=15)
        if resp is not None:
            for sym in resp.symbol:
                self._symbols[sym.symbolId] = {
                    'name': sym.symbolName, 'enabled': sym.enabled,
                }
                self._symbol_names[sym.symbolName] = sym.symbolId
                name = sym.symbolName
                if any(x in name for x in ['XAU', 'XAG', 'XPT', 'XPD']):
                    self._symbol_digits[sym.symbolId] = 2
                else:
                    self._symbol_digits[sym.symbolId] = 5
            logger.info(f"Loaded {len(self._symbols)} symbols")

    async def _reconcile(self):
        msg = ProtoOAReconcileReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg_id = await self._send_msg(msg, PT_RECONCILE_REQ)
        resp = await self._wait_for(msg_id, timeout=15)
        if resp is not None:
            self._positions = list(resp.position)
            self._orders = list(resp.order)
            logger.info(f"Reconciled: {len(self._positions)} positions, {len(self._orders)} orders")

    async def _subscribe_spots(self):
        msg = ProtoOASubscribeSpotsReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg.subscribeToSpotTimestamp = True
        count = 0
        for sym_id, info in self._symbols.items():
            if info['enabled']:
                msg.symbolId.append(sym_id)
                count += 1
                if count % 50 == 0:
                    await self._send_msg(msg, PT_SUBSCRIBE_SPOTS_REQ)
                    await asyncio.sleep(0.1)
                    msg = ProtoOASubscribeSpotsReq()
                    msg.ctidTraderAccountId = int(self.account_id)
                    msg.subscribeToSpotTimestamp = True
        if count % 50 != 0:
            await self._send_msg(msg, PT_SUBSCRIBE_SPOTS_REQ)

    # ── Execution Handler ────────────────────────────────────────────────
    def _handle_execution(self, evt):
        if evt.position:
            pos = evt.position
            status = pos.positionStatus
            if status in (2, 4):  # CLOSED or ERROR — remove
                self._positions = [p for p in self._positions if p.positionId != pos.positionId]
                logger.info(f"Execution: position {pos.positionId} CLOSED/ERROR (status={status}), removed from tracking")
            else:  # OPEN, CREATED — upsert
                self._positions = [p for p in self._positions if p.positionId != pos.positionId]
                self._positions.append(pos)
                logger.info(f"Execution: position {pos.positionId} status={status}, tracked ({len(self._positions)} total)")
        if evt.deal:
            deal = evt.deal
            logger.info(f"Deal: {deal.dealId} price={deal.executionPrice} side={deal.tradeSide}")

    # ── Public API ───────────────────────────────────────────────────────
    def get_balance(self) -> float:
        if self._trader_info:
            d = getattr(self._trader_info, 'moneyDigits', 0)
            return self._trader_info.balance / (10 ** d) if d else self._trader_info.balance
        return 0.0

    def get_equity(self) -> float:
        return self.get_balance()

    def get_positions(self) -> List:
        return list(self._positions)

    def get_symbol_id(self, pair: str) -> Optional[int]:
        sid = self._symbol_names.get(pair)
        if sid:
            return sid
        return self._symbol_names.get(pair.replace('/', ''))

    def get_spot(self, pair: str) -> Optional[Dict]:
        sym_id = self.get_symbol_id(pair)
        if sym_id and sym_id in self._spots:
            s = self._spots[sym_id]
            digits = self._symbol_digits.get(sym_id, 5)
            scale = 10 ** digits
            bid = s['bid'] / scale if s['bid'] > 0 else 0
            ask = s['ask'] / scale if s['ask'] > 0 else 0
            # Use the available price; if bid=0 use ask, if ask=0 use bid
            if bid > 0 and ask > 0:
                return {'bid': bid, 'ask': ask, 'mid': (bid + ask) / 2}
            elif bid > 0:
                return {'bid': bid, 'ask': bid, 'mid': bid}
            elif ask > 0:
                return {'bid': ask, 'ask': ask, 'mid': ask}
            else:
                return None
        return None

    async def get_symbols_prices(self, pairs: List[str]) -> Dict[str, float]:
        prices = {}
        for pair in pairs:
            spot = self.get_spot(pair)
            if spot:
                # Use mid price if available, else the available price
                prices[pair] = spot.get('mid', spot['bid']) if spot.get('mid', spot['bid']) > 0 else spot['ask']
        return prices

    async def place_market_order(self, symbol: str, side: str,
                                  volume: float, sl_price: float = None,
                                  tp_price: float = None,
                                  comment: str = "") -> OrderResult:
        sym_id = self.get_symbol_id(symbol)
        if not sym_id:
            return OrderResult(success=False, error=f"Unknown symbol: {symbol}")

        digits = self._symbol_digits.get(sym_id, 5)
        scale = 10 ** digits

        msg = ProtoOANewOrderReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg.symbolId = sym_id
        msg.orderType = 1  # MARKET
        msg.tradeSide = 1 if side.upper() == 'BUY' else 2
        msg.volume = int(volume * 10000000)

        if sl_price:
            msg.stopLoss = round(sl_price, digits)
        if tp_price:
            msg.takeProfit = round(tp_price, digits)
        if comment:
            msg.comment = comment

        msg_id = await self._send_msg(msg, PT_NEW_ORDER_REQ)
        logger.info(f"Order sent: {symbol} {side} vol={volume} msg_id={msg_id}")
        resp = await self._wait_for(msg_id, timeout=15)

        if resp is not None:
            if resp.payloadType == PT_EXECUTION_EVENT:
                exec_evt = ProtoOAExecutionEvent()
                exec_evt.ParseFromString(resp.payload)
                pos_id = str(exec_evt.position.positionId) if exec_evt.position else None
                if exec_evt.deal:
                    return OrderResult(
                        success=True,
                        order_id=str(exec_evt.deal.dealId),
                        position_id=pos_id,
                        fill_price=exec_evt.deal.executionPrice,
                    )
                return OrderResult(success=True, position_id=pos_id)
            else:
                logger.warning(f"Unexpected response type: {resp.payloadType}")
                return OrderResult(success=False, error=f"Unexpected response: {resp.payloadType}")
        return OrderResult(success=False, error="No response / timeout")

    async def close_position(self, position_id: str, volume: float = None) -> OrderResult:
        msg = ProtoOAClosePositionReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg.positionId = int(position_id)
        # Find position to get volume if not provided
        if volume is None:
            for pos in self._positions:
                if pos.positionId == int(position_id):
                    volume = pos.tradeData.volume / 10000000  # Convert from protocol to lots
                    break
        if volume is not None:
            msg.volume = int(volume * 10000000)

        msg_id = await self._send_msg(msg, PT_CLOSE_POSITION_REQ)
        resp = await self._wait_for(msg_id, timeout=15)

        if resp is not None:
            return OrderResult(success=True)
        return OrderResult(success=False, error="Failed to close")

    async def close_all_positions(self, symbol: str = None) -> int:
        closed = 0
        for pos in list(self._positions):
            vol = pos.tradeData.volume / 10000000
            result = await self.close_position(str(pos.positionId), volume=vol)
            if result.success:
                closed += 1
        return closed

    async def modify_position(self, position_id: str,
                               sl_price: float = None,
                               tp_price: float = None,
                               pair: str = None) -> bool:
        msg = ProtoOAAmendPositionSLTPReq()
        msg.ctidTraderAccountId = int(self.account_id)
        msg.positionId = int(position_id)
        if sl_price is not None:
            if pair:
                sym_id = self.get_symbol_id(pair)
                digits = self._symbol_digits.get(sym_id, 5) if sym_id else 5
                msg.stopLoss = round(sl_price, digits)
            else:
                msg.stopLoss = sl_price
        if tp_price is not None:
            if pair:
                sym_id = self.get_symbol_id(pair)
                digits = self._symbol_digits.get(sym_id, 5) if sym_id else 5
                msg.takeProfit = round(tp_price, digits)
            else:
                msg.takeProfit = tp_price

        msg_id = await self._send_msg(msg, PT_AMEND_POSITION_SLTP_REQ)
        resp = await self._wait_for(msg_id, timeout=10)
        if resp is not None:
            logger.info(f"Modified position {position_id}: SL={sl_price} TP={tp_price}")
            return True
        logger.warning(f"Failed to modify position {position_id}")
        return False

    async def get_account_balance(self) -> float:
        await self._get_trader()
        return self.get_balance()
