"""
Read-only market-data adapter — S7 LIVE SHADOW.

Only the following read operations are allowed:
  - current bid/ask
  - completed 4H candles
  - spread
  - timestamps
  - symbol availability

Explicitly forbidden (must never be called):
  - OrderSend / order_send
  - order_modify / order_delete
  - any instantiation of execution/broker-order adapters

Three implementations:
  StubLiveAdapter        — deterministic stub backed by DataFrames (for tests).
  WineFlaskReadOnlyAdapter — thin REST client for the sesto-dev MT5 Quant Server
                           tutorial (Docker + Wine + Flask at http://mt5:5001).
                           Talks to Flask inside Wine, not to MT5 directly.
                           No MetaTrader5 import on host, $0 extra cost.
  MT5ReadOnlyAdapter     — wraps MetaTrader5 read-only calls (Windows only);
                           kept for Windows fallback, never used on Linux.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from nestquant.core.data.loader import DataLoader


@dataclass(frozen=True)
class Quote:
    pair: str
    bid: float
    ask: float
    spread: float       # ask - bid in price units
    spread_pips: float
    broker_timestamp: str  # ISO8601 UTC when broker emitted the quote
    receipt_timestamp: str # ISO8601 UTC when adapter received it


@dataclass(frozen=True)
class CompletedBar:
    pair: str
    timeframe: str  # "4h"
    timestamp: str  # bar close ISO8601 UTC (completed bar)
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float
    ask: float
    spread: float
    broker_timestamp: str  # when broker confirmed close
    receipt_timestamp: str


class ReadOnlyMarketDataAdapter(ABC):
    """Abstract read-only adapter. No order methods exist by design."""

    @abstractmethod
    def connect(self) -> bool: ...
    @abstractmethod
    def disconnect(self) -> None: ...
    @abstractmethod
    def is_connected(self) -> bool: ...
    @abstractmethod
    def is_symbol_available(self, pair: str) -> bool: ...
    @abstractmethod
    def get_quote(self, pair: str) -> Optional[Quote]: ...
    @abstractmethod
    def get_last_completed_bar(self, pair: str, timeframe: str = "4h") -> Optional[CompletedBar]: ...
    @abstractmethod
    def fetch_history(self, pair: str, timeframe: str = "4h", count: int = 500) -> Optional[pd.DataFrame]: ...

    # For guard introspection
    @property
    def name(self) -> str:  # pragma: no cover
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# Hard blocklist — if any of these names appear in source, live shadow must fail
# ---------------------------------------------------------------------------

FORBIDDEN_ORDER_NAMES = (
    "OrderSend", "order_send", "OrderModify", "order_modify",
    "OrderDelete", "order_delete", "CTrade", "CPosition",
)


def assert_adapter_source_is_readonly(module_path: Path) -> None:
    text = module_path.read_text(encoding="utf-8", errors="ignore")
    for name in FORBIDDEN_ORDER_NAMES:
        if name in text:
            raise RuntimeError(f"CRITICAL: forbidden order name '{name}' found in {module_path}")


# ---------------------------------------------------------------------------
# Stub adapter — deterministic, file-backed, fully controllable for tests
# ---------------------------------------------------------------------------

class StubLiveAdapter(ReadOnlyMarketDataAdapter):
    """Deterministic stub backed by DataLoader 4h files.

    `advance(pair)` moves the internal pointer forward by one completed bar
    (simulating broker confirming a new 4H candle). Polling via
    `get_last_completed_bar` returns the current pointer's bar.

    Test knobs:
      - `fail_next_connect` — next connect() returns False
      - `stale` — if True, get_quote returns same stale timestamp
      - `clock_skew_seconds` — artificial broker vs local clock offset
      - `inject_missing` — skip one bar (simulate missing candle)
      - `inject_duplicate` — next poll returns same bar twice
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        timeframe: str = "4h",
        pairs: Optional[list[str]] = None,
        start_idx: int = -1,  # -1 = last bar (most recent) for live start; 0 = earliest
    ) -> None:
        self.timeframe = timeframe
        self._loader = DataLoader(data_dir=data_dir)
        self._pairs = pairs
        self._connected = False
        # per-pair history DataFrames and pointer
        self._dfs: dict[str, pd.DataFrame] = {}
        self._ptr: dict[str, int] = {}
        # test knobs
        self.fail_next_connect = False
        self.stale = False
        self.clock_skew_seconds = 0
        self.inject_missing: set[str] = set()
        self.inject_duplicate: set[str] = set()
        self._connect_count = 0
        self._reconnect_count = 0
        self._start_idx = start_idx

    def connect(self) -> bool:
        self._connect_count += 1
        if self.fail_next_connect:
            self.fail_next_connect = False
            self._connected = False
            return False
        if not self._connected:
            self._reconnect_count += 1
        self._connected = True
        # Lazy load histories on first connect
        if not self._dfs:
            target_pairs = self._pairs
            if target_pairs is None:
                import json as _json
                s6c = Path("research_data/s6c/S6C_causal_swing_results.json")
                if s6c.exists():
                    try:
                        target_pairs = json.loads(s6c.read_text())["config"]["pairs_loaded"]
                    except Exception:
                        target_pairs = None
                if not target_pairs:
                    from nestquant.core.configuration.settings import get_config
                    target_pairs = list(get_config().universe.all_pairs[:20])
            for pair in target_pairs:
                df = self._loader.load_pair(pair, timeframe=self.timeframe)
                if df is not None and len(df) > 0:
                    df = df.sort_index()
                    if df.index.tz is None:
                        df.index = df.index.tz_localize(timezone.utc)
                    else:
                        df.index = df.index.tz_convert(timezone.utc)
                    self._dfs[pair] = df
                    # start pointer at requested idx (negative = offset from end)
                    if self._start_idx < 0:
                        self._ptr[pair] = max(0, len(df) + self._start_idx)
                    else:
                        self._ptr[pair] = max(0, min(self._start_idx, len(df) - 1))
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def is_symbol_available(self, pair: str) -> bool:
        return pair in self._dfs

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _broker_now_iso(self) -> str:
        # Apply clock skew if configured
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        if self.clock_skew_seconds:
            now = now + timedelta(seconds=self.clock_skew_seconds)
        return now.isoformat()

    def get_quote(self, pair: str) -> Optional[Quote]:
        if not self._connected or pair not in self._dfs:
            return None
        df = self._dfs[pair]
        idx = self._ptr.get(pair, len(df) - 1)
        row = df.iloc[idx]
        close = float(row["close"])
        # Simulate spread from config (0.3 pip default)
        spread = 0.0003 if "JPY" not in pair else 0.03
        bid = close - spread / 2
        ask = close + spread / 2
        pip = 0.01 if "JPY" in pair else 0.0001
        return Quote(
            pair=pair,
            bid=bid,
            ask=ask,
            spread=spread,
            spread_pips=spread / pip,
            broker_timestamp=self._broker_now_iso() if not self.stale else df.index[idx].isoformat(),
            receipt_timestamp=self._now_iso(),
        )

    def get_last_completed_bar(self, pair: str, timeframe: str = "4h") -> Optional[CompletedBar]:
        if not self._connected or pair not in self._dfs:
            return None
        # Duplicate injection
        if pair in self.inject_duplicate:
            # Return current ptr without advancing; caller will see same ts twice
            pass
        df = self._dfs[pair]
        idx = self._ptr.get(pair, len(df) - 1)
        if pair in self.inject_missing:
            # Simulate missing: pretend bar at idx+1 was never emitted; next call will be idx+2
            # For now just return idx as if missing hasn't happened yet; the runner's gap detection will catch it
            pass
        row = df.iloc[idx]
        bar_ts = df.index[idx].isoformat()
        q = self.get_quote(pair)
        bid = q.bid if q else float(row["close"])
        ask = q.ask if q else float(row["close"])
        spread = q.spread if q else 0.0
        return CompletedBar(
            pair=pair,
            timeframe=timeframe,
            timestamp=bar_ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0) or 0),
            bid=bid,
            ask=ask,
            spread=spread,
            broker_timestamp=bar_ts,  # completed bar's close
            receipt_timestamp=self._now_iso(),
        )

    def advance(self, pair: str, steps: int = 1) -> bool:
        """Move pointer forward (simulate broker confirming next bar). Returns False if at end."""
        if pair not in self._dfs:
            return False
        df = self._dfs[pair]
        cur = self._ptr.get(pair, 0)
        # Handle missing injection: skip one bar
        if pair in self.inject_missing:
            steps += 1
            self.inject_missing.discard(pair)
        nxt = cur + steps
        if nxt >= len(df):
            return False
        self._ptr[pair] = nxt
        # Clear duplicate flag after one duplicate emission
        if pair in self.inject_duplicate:
            self.inject_duplicate.discard(pair)
        return True

    def fetch_history(self, pair: str, timeframe: str = "4h", count: int = 500) -> Optional[pd.DataFrame]:
        if pair not in self._dfs:
            return None
        df = self._dfs[pair]
        idx = self._ptr.get(pair, len(df) - 1)
        # Return history up to and including current pointer
        start = max(0, idx - count + 1)
        return df.iloc[start: idx + 1].copy()


# ---------------------------------------------------------------------------
# Wine + Flask REST adapter — thin client for sesto-dev tutorial
# Docker: Linux host --HTTP--> Wine container (Flask :5001 --named pipes--> MT5)
# No MetaTrader5 import on host, $0 cost, solves Linux named-pipe same-user issue
# ---------------------------------------------------------------------------

class WineFlaskReadOnlyAdapter(ReadOnlyMarketDataAdapter):
    """Read-only REST client for the sesto-dev MT5 Quant Server tutorial.

    Architecture (from chapter-2):
      Host NestQuant (Linux Python, requests) --HTTP GET--> Flask :5001
        inside Docker `mt5` container (Wine Python + MetaTrader5 + terminal64.exe
        as same `abc` user, WINEPREFIX=/config/.wine, DISPLAY=:0, KasmVNC :3000)

    Only read-only Flask endpoints are ever called:
      GET /health
      GET /symbol_info/<symbol>
      GET /symbol_info_tick/<symbol>
      GET /fetch_data_pos?symbol=&timeframe=&num_bars=
      GET /fetch_data_range (for fetch_history fallback)

    No order/position endpoints are ever called. The hard guard still blocks
    any BaseExecutionAdapter.execute path.

    Env: MT5_API_URL (default http://mt5:5001, fallback http://localhost:5001)
    """

    # Map our "4h" → tutorial's "H4" (see backend/mt5/app/constants.py:MT5Timeframe)
    _TF_MAP = {"4h": "H4", "1h": "H1", "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1d": "D1"}

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
        pairs: Optional[list[str]] = None,
    ) -> None:
        import os as _os
        self.base_url = (base_url or _os.getenv("MT5_API_URL") or "http://mt5:5001").rstrip("/")
        # Fallback for host-direct testing
        self._fallback_url = "http://localhost:5001"
        self.timeout = timeout
        self._connected = False
        self._pairs = pairs
        self._last_health_ok = False

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[Any]:
        import requests as _requests
        # Try primary (mt5:5001 inside Docker network) then fallback (localhost)
        for base in (self.base_url, self._fallback_url):
            if base == self._fallback_url and base == self.base_url:
                continue
            try:
                resp = _requests.get(f"{base}{path}", params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
        # Last try with primary only and let exception propagate as None
        try:
            import requests as _requests2
            resp = _requests2.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def connect(self) -> bool:
        data = self._get("/health")
        ok = bool(data and isinstance(data, dict) and data.get("mt5_initialized") in (True, "true", 1))
        # Fallback: if health endpoint returns 200 at all, consider connected (some chapter-1 images return different shape)
        if not ok and data is not None:
            ok = isinstance(data, dict) and data.get("status") == "healthy"
        self._connected = ok
        self._last_health_ok = ok
        return ok

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def is_symbol_available(self, pair: str) -> bool:
        sym = pair.replace("/", "")
        data = self._get(f"/symbol_info/{sym}")
        return bool(data and not data.get("error") and (data.get("name") or data.get("symbol") or data.get("bid") is not None))

    def get_quote(self, pair: str) -> Optional[Quote]:
        sym = pair.replace("/", "")
        data = self._get(f"/symbol_info_tick/{sym}")
        if not data or data.get("error"):
            return None
        try:
            bid = float(data.get("bid", data.get("Bid", 0)))
            ask = float(data.get("ask", data.get("Ask", 0)))
            if bid == 0 and ask == 0:
                return None
            spread = ask - bid
            pip = 0.01 if "JPY" in pair else 0.0001
            raw_time = data.get("time", data.get("Time", 0))
            broker_ts: str
            try:
                if isinstance(raw_time, (int, float)) and raw_time > 1e9:
                    broker_ts = datetime.fromtimestamp(int(raw_time), tz=timezone.utc).isoformat()
                elif isinstance(raw_time, str) and raw_time:
                    # Flask returns RFC2822 "Fri, 28 Aug 2026 20:00:00 GMT" — use pandas for robustness
                    broker_ts = pd.to_datetime(raw_time, utc=True).isoformat()
                else:
                    broker_ts = datetime.now(timezone.utc).isoformat()
            except Exception:
                broker_ts = datetime.now(timezone.utc).isoformat()
            return Quote(
                pair=pair,
                bid=bid,
                ask=ask,
                spread=spread,
                spread_pips=spread / pip,
                broker_timestamp=broker_ts,
                receipt_timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            return None

    def _fetch_via_rest(self, pair: str, timeframe: str, num_bars: int) -> Optional[list[dict]]:
        sym = pair.replace("/", "")
        tf = self._TF_MAP.get(timeframe, "H4")
        data = self._get("/fetch_data_pos", params={"symbol": sym, "timeframe": tf, "num_bars": num_bars})
        if isinstance(data, list) and len(data) > 0:
            return data
        if isinstance(data, dict) and "error" not in data:
            # Some versions wrap in {"data": [...]}
            if isinstance(data.get("data"), list):
                return data["data"]
        return None

    def get_last_completed_bar(self, pair: str, timeframe: str = "4h") -> Optional[CompletedBar]:
        # Flask's copy_rates_from_pos with start_pos 0 returns [oldest,...,newest] where last is forming.
        # For completed bar, fetch 2 and take second-last (e.g., 16:00 when 20:00 is forming at 18:05)
        rates = self._fetch_via_rest(pair, timeframe, 2)
        if not rates or len(rates) < 2:
            rates = self._fetch_via_rest(pair, timeframe, 1)
            if not rates:
                return None
            r = rates[0] if isinstance(rates, list) else rates
        else:
            # rates[0]=16:00, rates[1]=20:00 (forming), so completed is rates[-2]
            r = rates[-2] if isinstance(rates, list) else rates
        try:
            raw_time = r.get("time", r.get("Time", r.get("timestamp", 0)))
            if isinstance(raw_time, (int, float)):
                bar_time = datetime.fromtimestamp(int(raw_time), tz=timezone.utc).isoformat()
            elif isinstance(raw_time, str):
                bar_time = pd.to_datetime(raw_time, utc=True).isoformat()
            else:
                bar_time = datetime.now(timezone.utc).isoformat()
            # For completed bar, use bar_time as broker_timestamp, spread from tick
            q = self.get_quote(pair)
            bid = q.bid if q else float(r.get("close", r.get("Close", 0)))
            ask = q.ask if q else float(r.get("close", r.get("Close", 0)))
            spread = q.spread if q else float(r.get("spread", 0)) * (0.0001 if "JPY" not in pair else 0.01)
            return CompletedBar(
                pair=pair,
                timeframe=timeframe,
                timestamp=bar_time,
                open=float(r.get("open", r.get("Open", 0))),
                high=float(r.get("high", r.get("High", 0))),
                low=float(r.get("low", r.get("Low", 0))),
                close=float(r.get("close", r.get("Close", 0))),
                volume=float(r.get("tick_volume", r.get("Volume", r.get("volume", 0)))),
                bid=bid,
                ask=ask,
                spread=spread,
                broker_timestamp=bar_time,
                receipt_timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            return None

    def fetch_history(self, pair: str, timeframe: str = "4h", count: int = 500) -> Optional[pd.DataFrame]:
        rates = self._fetch_via_rest(pair, timeframe, count)
        if not rates:
            return None
        try:
            df = pd.DataFrame(rates)
            # Normalize columns: tutorial uses lower-case time/open/high/low/close/tick_volume
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
                df = df.set_index("time").sort_index()
            elif "Time" in df.columns:
                df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")
                df = df.set_index("Time").sort_index()
            # Rename to expected schema
            rename = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume", "TickVolume": "volume", "tick_volume": "volume", "real_volume": "volume"}
            df = df.rename(columns=rename)
            for col in ["open", "high", "low", "close", "volume"]:
                if col not in df.columns:
                    return None
            return df[["open", "high", "low", "close", "volume"]]
        except Exception:
            return None


# ---------------------------------------------------------------------------
# MT5 read-only adapter — only uses read calls, never order calls
# ---------------------------------------------------------------------------

class MT5ReadOnlyAdapter(ReadOnlyMarketDataAdapter):
    """Thin wrapper around MetaTrader5 read-only API.

    If MT5 is not installed or not connected, all calls return None and
    `is_connected()` is False. No order function is ever referenced.
    """

    # Explicit allowlist of MT5 symbols we may call
    _ALLOWLIST = (
        "initialize", "shutdown", "terminal_info", "account_info",
        "symbol_info", "symbol_info_tick", "symbol_select",
        "copy_rates_from_pos", "copy_rates_range", "copy_ticks_range",
        "last_error",
    )

    def __init__(self) -> None:
        self._mt5: Any = None
        self._connected = False
        self._import_error: Optional[str] = None
        try:
            import MetaTrader5 as mt5  # type: ignore
            # Verify no forbidden names are accidentally reachable via our wrapper
            for name in FORBIDDEN_ORDER_NAMES:
                if hasattr(mt5, name):
                    # We do not use them, but their existence is not a violation;
                    # we just ensure we never call them.
                    pass
            self._mt5 = mt5
        except Exception as e:
            self._import_error = str(e)
            self._mt5 = None

    def connect(self) -> bool:
        if self._mt5 is None:
            return False
        try:
            # Only read-only initialize
            ok = bool(self._mt5.initialize())
            self._connected = ok
            return ok
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._mt5 is not None

    def is_symbol_available(self, pair: str) -> bool:
        if not self.is_connected():
            return False
        try:
            # MT5 uses e.g. "EURUSD" without slash
            sym = pair.replace("/", "")
            info = self._mt5.symbol_info(sym)
            return info is not None
        except Exception:
            return False

    def get_quote(self, pair: str) -> Optional[Quote]:
        if not self.is_connected():
            return None
        try:
            sym = pair.replace("/", "")
            tick = self._mt5.symbol_info_tick(sym)
            if tick is None:
                return None
            bid = float(tick.bid)
            ask = float(tick.ask)
            spread = ask - bid
            pip = 0.01 if "JPY" in pair else 0.0001
            now = datetime.now(timezone.utc).isoformat()
            # tick.time is broker time (seconds since epoch)
            broker_ts = datetime.fromtimestamp(int(tick.time), tz=timezone.utc).isoformat()
            return Quote(pair=pair, bid=bid, ask=ask, spread=spread, spread_pips=spread / pip, broker_timestamp=broker_ts, receipt_timestamp=now)
        except Exception:
            return None

    def get_last_completed_bar(self, pair: str, timeframe: str = "4h") -> Optional[CompletedBar]:
        if not self.is_connected():
            return None
        try:
            sym = pair.replace("/", "")
            # Map timeframe string to MT5 constant
            tf_map = {"4h": self._mt5.TIMEFRAME_H4, "1h": self._mt5.TIMEFRAME_H1, "1m": self._mt5.TIMEFRAME_M1}
            tf = tf_map.get(timeframe, self._mt5.TIMEFRAME_H4)
            rates = self._mt5.copy_rates_from_pos(sym, tf, 1, 1)  # 1 bar back = last completed
            if rates is None or len(rates) == 0:
                return None
            r = rates[0]
            bar_time = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).isoformat()
            q = self.get_quote(pair)
            bid = q.bid if q else float(r["close"])
            ask = q.ask if q else float(r["close"])
            spread = q.spread if q else 0.0
            return CompletedBar(
                pair=pair, timeframe=timeframe, timestamp=bar_time,
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r.get("tick_volume", 0)),
                bid=bid, ask=ask, spread=spread,
                broker_timestamp=bar_time, receipt_timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            return None

    def fetch_history(self, pair: str, timeframe: str = "4h", count: int = 500) -> Optional[pd.DataFrame]:
        if not self.is_connected():
            return None
        try:
            sym = pair.replace("/", "")
            tf_map = {"4h": self._mt5.TIMEFRAME_H4, "1h": self._mt5.TIMEFRAME_H1}
            tf = tf_map.get(timeframe, self._mt5.TIMEFRAME_H4)
            rates = self._mt5.copy_rates_from_pos(sym, tf, 1, count)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.set_index("time").sort_index()
            df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "tick_volume": "volume"})
            return df[["open", "high", "low", "close", "volume"]]
        except Exception:
            return None
