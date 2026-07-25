"""
MetaApi Cloud SDK Connector for MT5
Async connector using MetaApi Cloud SDK websocket connection.
Mirrors the CTraderConnector interface pattern.
"""
import os
import asyncio
import logging
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass

from metaapi_cloud_sdk import MetaApi
from metaapi_cloud_sdk.metaapi.rpc_metaapi_connection_instance import RpcMetaApiConnectionInstance
from metaapi_cloud_sdk.metaapi.models import MetatraderTradeResponse

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    error: Optional[str] = None
    slippage: float = 0.0


class MT5Connector:

    def __init__(self, token: str = "", account_id: str = "",
                 name: str = "MT5 Cloud", region: str = "asia"):
        self.token = token or os.environ.get("METAAPI_TOKEN", "")
        self.account_id = account_id or os.environ.get("METAAPI_ACCOUNT_ID", "")
        self.name = name
        self.region = region

        self.connected = False
        self._running = False
        self._listen_task: Optional[asyncio.Task] = None

        self._api: Optional[MetaApi] = None
        self._account = None
        self._connection: Optional[RpcMetaApiConnectionInstance] = None

        self._spots: Dict[str, Dict] = {}
        self._positions: List = []
        self._balance: float = 0.0
        self._equity: float = 0.0

        self._on_spot: Optional[Callable] = None
        self._on_execution: Optional[Callable] = None

    def set_spot_callback(self, cb: Callable):
        self._on_spot = cb

    def set_execution_callback(self, cb: Callable):
        self._on_execution = cb

    # ── Internal recv loop (polling for state) ──────────────────────────
    async def _recv_loop(self):
        """Periodically refresh account state while connected."""
        while self._running and self.connected:
            try:
                await self._refresh_state()
                if self._on_spot:
                    for sym, data in self._spots.items():
                        self._on_spot(sym, data.get('bid', 0), data.get('ask', 0))
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Recv loop error: {e}")
                await asyncio.sleep(1.0)

    async def _refresh_state(self):
        """Refresh balance, equity, and positions from the API."""
        if not self._connection:
            return
        try:
            acct_info = await self._connection.get_account_information()
            if acct_info:
                self._balance = acct_info.get('balance', 0.0)
                self._equity = acct_info.get('equity', 0.0)
        except Exception as e:
            logger.debug(f"Failed to get account info: {e}")
        try:
            self._positions = await self._connection.get_positions()
        except Exception as e:
            logger.debug(f"Failed to get positions: {e}")

    # ── Connect Flow ─────────────────────────────────────────────────────
    async def connect(self) -> bool:
        try:
            if not self.token:
                logger.error("No MetaApi token provided")
                return False
            if not self.account_id:
                logger.error("No MetaApi account ID provided")
                return False

            logger.info("Initializing MetaApi SDK...")
            self._api = MetaApi(self.token)

            logger.info(f"Getting account {self.account_id}...")
            self._account = await self._api.metatrader_account_api.get_account(self.account_id)

            state = self._account.state
            if state == 'DEPLOYING':
                logger.info("Account is deploying, waiting...")
                await self._account.wait_deployed()
            elif state != 'DEPLOYED':
                logger.info(f"Deploying account (state={state})...")
                await self._account.deploy()
                await self._account.wait_deployed()

            logger.info("Waiting for broker connection...")
            await self._account.wait_connected()

            logger.info("Opening RPC connection...")
            self._connection = self._account.get_rpc_connection()
            await self._connection.connect()
            await self._connection.wait_synchronized()

            self._running = True
            self.connected = True

            await self._refresh_state()
            self._listen_task = asyncio.create_task(self._recv_loop())

            logger.info(f"Connected! Balance: ${self._balance:.2f}, Equity: ${self._equity:.2f}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self):
        self._running = False
        self.connected = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None
        if self._api:
            try:
                await self._api.close()
            except Exception:
                pass
            self._api = None
        logger.info("Disconnected")

    # ── Public API ───────────────────────────────────────────────────────
    def get_balance(self) -> float:
        return self._balance

    def get_equity(self) -> float:
        return self._equity

    def get_positions(self) -> List:
        return list(self._positions)

    async def get_account_balance(self) -> float:
        await self._refresh_state()
        return self._balance

    async def get_spot(self, pair: str) -> Optional[Dict]:
        if not self._connection:
            return None
        symbol = pair.replace('/', '')
        try:
            price = await self._connection.get_symbol_price(symbol)
            if price:
                result = {'bid': price['bid'], 'ask': price['ask']}
                self._spots[symbol] = result
                return result
        except Exception as e:
            logger.error(f"Failed to get spot for {symbol}: {e}")
        return None

    async def get_symbols_prices(self, pairs: List[str]) -> Dict[str, float]:
        prices = {}
        for pair in pairs:
            spot = await self.get_spot(pair)
            if spot:
                prices[pair] = spot['bid']
        return prices

    async def place_market_order(self, symbol: str, side: str,
                                  volume: float, sl_price: float = None,
                                  tp_price: float = None,
                                  comment: str = "") -> OrderResult:
        if not self._connection:
            return OrderResult(success=False, error="Not connected")

        mt_symbol = symbol.replace('/', '')
        options = {}
        if comment:
            options['comment'] = comment

        try:
            if side.upper() == 'BUY':
                resp: MetatraderTradeResponse = await self._connection.create_market_buy_order(
                    mt_symbol, volume,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    options=options or None,
                )
            elif side.upper() == 'SELL':
                resp = await self._connection.create_market_sell_order(
                    mt_symbol, volume,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    options=options or None,
                )
            else:
                return OrderResult(success=False, error=f"Invalid side: {side}")

            numeric_code = resp.get('numericCode', -1)
            string_code = resp.get('stringCode', '')
            message = resp.get('message', '')
            order_id = resp.get('orderId') or resp.get('positionId')

            if numeric_code in (0, 10008, 10009, 10010, 10025):
                logger.info(f"Order placed: {mt_symbol} {side} vol={volume} id={order_id}")
                return OrderResult(success=True, order_id=order_id)
            else:
                error_msg = f"Code {numeric_code} ({string_code}): {message}"
                logger.error(f"Order failed: {error_msg}")
                return OrderResult(success=False, error=error_msg)

        except Exception as e:
            logger.error(f"Order error: {e}")
            return OrderResult(success=False, error=str(e))

    async def close_position(self, position_id: str, volume: float = None) -> OrderResult:
        if not self._connection:
            return OrderResult(success=False, error="Not connected")

        try:
            resp = await self._connection.close_position(str(position_id))
            numeric_code = resp.get('numericCode', -1)
            string_code = resp.get('stringCode', '')
            message = resp.get('message', '')
            order_id = resp.get('orderId') or resp.get('positionId')

            if numeric_code in (0, 10008, 10009, 10010, 10025):
                logger.info(f"Position closed: {position_id}")
                return OrderResult(success=True, order_id=order_id)
            else:
                error_msg = f"Code {numeric_code} ({string_code}): {message}"
                logger.error(f"Close failed: {error_msg}")
                return OrderResult(success=False, error=error_msg)

        except Exception as e:
            logger.error(f"Close error: {e}")
            return OrderResult(success=False, error=str(e))

    async def close_all_positions(self, symbol: str = None) -> int:
        closed = 0
        positions = list(self._positions)
        for pos in positions:
            pos_id = str(pos.get('id', ''))
            pos_symbol = pos.get('symbol', '')
            if symbol and pos_symbol.replace('/', '') != symbol.replace('/', ''):
                continue
            result = await self.close_position(pos_id)
            if result.success:
                closed += 1
        return closed

    async def modify_position(self, position_id: str,
                               sl_price: float = None,
                               tp_price: float = None) -> bool:
        if not self._connection:
            return False
        try:
            trade_params = {
                'actionType': 'POSITION_MODIFY',
                'positionId': str(position_id),
            }
            if sl_price is not None:
                trade_params['stopLoss'] = sl_price
            if tp_price is not None:
                trade_params['takeProfit'] = tp_price
            resp = await self._connection._trade(trade_params)
            numeric_code = resp.get('numericCode', -1)
            return numeric_code in (0, 10008, 10009, 10010, 10025)
        except Exception as e:
            logger.error(f"Modify error: {e}")
            return False
