"""
NestQuant FX Strategy — Configuration
=======================================
Consolidated configuration using pydantic-settings.
"""

from __future__ import annotations

import multiprocessing as _mp
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Load .env file
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


@dataclass(frozen=True)
class UniverseConfig:
    """Universe and pair definitions."""

    currencies: tuple[str, ...] = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")

    all_pairs: tuple[str, ...] = (
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD",
        "AUD/USD", "NZD/USD", "EUR/GBP", "EUR/JPY", "EUR/CHF",
        "EUR/CAD", "EUR/AUD", "EUR/NZD", "GBP/JPY", "GBP/CHF",
        "GBP/CAD", "GBP/AUD", "GBP/NZD", "CHF/JPY", "CAD/JPY",
        "AUD/JPY", "NZD/JPY", "AUD/CAD", "AUD/CHF", "AUD/NZD",
        "NZD/CAD", "NZD/CHF", "CAD/CHF",
    )

    tradeable_pairs: tuple[str, ...] = (
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
        "NZD/USD", "EUR/JPY", "GBP/JPY",
    )

    quick_test_pairs: tuple[str, ...] = (
        "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
        "AUD/USD", "NZD/USD", "EUR/JPY", "GBP/JPY",
    )


@dataclass(frozen=True)
class StrategyConfig:
    """Strategy parameters."""

    macro_tf: str = "4h"
    macro_ema_period: int = 200
    atr_period: int = 14
    atr_sl_multiplier: float = 3.0
    rrr: float = 2.0
    min_divergence: float = 10.0
    breakeven_ratio: float = 1.5
    enable_macro_filter: bool = True
    risk_per_trade: float = 0.03
    commission_per_lot: float = 6.0
    min_lot_size: float = 0.01
    max_lot_size: float = 1.0
    max_leverage: int = 2000
    max_margin_usage_pct: float = 0.75


@dataclass(frozen=True)
class SpreadConfig:
    """Spread model per pair (Exness Standard Account)."""

    spreads: dict[str, float] = field(default_factory=lambda: {
        "EUR/USD": 0.8,
        "GBP/USD": 1.0,
        "USD/JPY": 1.0,
        "USD/CHF": 1.2,
        "USD/CAD": 1.4,
        "AUD/USD": 0.9,
        "NZD/USD": 1.2,
        "EUR/JPY": 1.6,
        "GBP/JPY": 2.0,
    })
    default_spread_pips: float = 0.5
    slippage_pips: float = 0.1


@dataclass(frozen=True)
class RiskConfig:
    """Risk management settings."""

    initial_balance: float = 200.0
    max_dd_pct: float = 55.0
    dd_reduce_threshold: float = 30.0
    dd_reduced_risk: float = 0.02
    enable_recovery: bool = True
    dynamic_lot_scaling: bool = True
    max_open_trades: int = 1
    max_per_currency_block: int = 1
    max_position_risk_pct: float = 1.0
    enable_hard_stops: bool = False
    block_same_direction_reentry: bool = True
    correlation_enabled: bool = True
    correlation_window: int = 20
    correlation_threshold: float = 0.70


@dataclass(frozen=True)
class MeanReversionConfig:
    """Mean Reversion strategy parameters."""

    atr_mult: float = 1.0
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    rsi_exit_buy: int = 50
    rsi_exit_sell: int = 50
    adx_period: int = 14
    adx_threshold: int = 25
    enable_dynamic_lot: bool = True


@dataclass(frozen=True)
class SessionConfig:
    """Session and time filter settings."""

    open_utc: int = 7
    close_utc: int = 21
    max_entry_hour: int = 21
    scale_sl_at_session_close: bool = True
    close_minutes_before: int = 30
    skip_monday_open: bool = False
    skip_friday_close: bool = True


@dataclass(frozen=True)
class NewsConfig:
    """News filter settings."""

    buffer_minutes: int = 120
    filter_levels: tuple[str, ...] = ("High", "Medium")
    csv_path: Optional[str] = None


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Circuit breaker thresholds."""

    winrate_20: float = 0.40
    winrate_30: float = 0.45
    slippage_consecutive: float = 4.8
    slippage_consecutive_count: int = 3
    slippage_avg_10: float = 6.0
    dd_pace_soft_dd: float = 6.0
    dd_pace_soft_trades: int = 5
    dd_pace_hard_dd: float = 8.5
    dd_pace_hard_trades: int = 10
    pf_trailing: float = 1.0
    pf_window: int = 20


@dataclass(frozen=True)
class LiveEngineConfig:
    """Live engine settings."""

    growth_target: float = 100.0
    max_lot: float = 0.20
    max_trades: int = 15
    log_dir: str = "/root/logs"


@dataclass(frozen=True)
class DashboardConfig:
    """Dashboard settings."""

    port: int = 8080
    host: str = "0.0.0.0"
    users_db: Optional[str] = None


@dataclass(frozen=True)
class AlertConfig:
    """Alerting settings."""

    enabled: bool = True
    webhook_url: str = "sAkuxb8g7YGGJ_l0EjfSbw"
    webhook_type: str = "ntfy"


@dataclass(frozen=True)
class DataConfig:
    """Data settings."""

    data_dir: str = ""
    mt5_data_cache: str = ""
    mt5_bars_to_fetch: int = 100000
    timeframe: str = "1h"
    timeframes: tuple[str, ...] = ("1min", "5min", "15min", "30min", "1h", "4h")
    primary_tf: str = "1h"
    macro_tf: str = "4h"


@dataclass(frozen=True)
class TradingConfig:
    """Trading settings (Z-score strategy thresholds)."""

    z_entry_threshold: float = 2.2
    z_exit_threshold: float = 0.5


@dataclass
class NestQuantConfig:
    """Root configuration for NestQuant."""

    universe: UniverseConfig = field(default_factory=UniverseConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    spread: SpreadConfig = field(default_factory=SpreadConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    mean_reversion: MeanReversionConfig = field(default_factory=MeanReversionConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    live_engine: LiveEngineConfig = field(default_factory=LiveEngineConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)
    data: DataConfig = field(default_factory=DataConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)

    # Environment detection
    on_kaggle: bool = field(default_factory=lambda: os.path.exists("/kaggle"))
    on_gcp: bool = field(default_factory=lambda: not os.path.exists("/kaggle") and os.path.exists("/etc") and not os.path.exists("C:\\"))
    on_windows: bool = field(default_factory=lambda: os.name == "nt")
    on_linux: bool = field(default_factory=lambda: os.name != "nt")

    # Parallelism
    n_cpus: int = field(default_factory=_mp.cpu_count)
    backtest_n_jobs: int = field(default_factory=lambda: int(os.getenv("BACKTEST_N_JOBS", str(max(1, _mp.cpu_count() - 2)))))
    download_workers: int = field(default_factory=lambda: int(os.getenv("DOWNLOAD_WORKERS", str(min(8, _mp.cpu_count())))))

    # Output
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Trade log schema
    trade_log_columns: tuple[str, ...] = (
        "timestamp", "account", "pair", "direction", "entry_price",
        "fill_price", "slippage_pips", "lot_size", "pnl", "equity_after",
        "dd_pct", "exit_reason", "regime_at_entry", "breaker_trigger",
        "breaker_value",
    )

    def __post_init__(self) -> None:
        """Set computed paths after initialization."""
        # Set data paths relative to this file's directory
        root_dir = Path(__file__).parent.parent.parent
        if not self.data.data_dir:
            object.__setattr__(self, "data", DataConfig(
                data_dir=str(root_dir / "data"),
                mt5_data_cache=str(root_dir / "data" / "mt5_matrix_pool.pkl"),
                mt5_bars_to_fetch=self.data.mt5_bars_to_fetch,
            ))
        if not self.dashboard.users_db:
            object.__setattr__(self, "dashboard", DashboardConfig(
                port=self.dashboard.port,
                host=self.dashboard.host,
                users_db=str(root_dir / "users.json"),
            ))
        if not self.news.csv_path:
            object.__setattr__(self, "news", NewsConfig(
                buffer_minutes=self.news.buffer_minutes,
                filter_levels=self.news.filter_levels,
                csv_path=str(root_dir / "master_news_calendar.csv"),
            ))


# ── Singleton ─────────────────────────────────────────────────────────────────
_config: Optional[NestQuantConfig] = None


def get_config() -> NestQuantConfig:
    """Get or create the singleton config instance."""
    global _config
    if _config is None:
        _config = NestQuantConfig()
    return _config


# ── Legacy compatibility aliases ──────────────────────────────────────────────
# These allow existing code to import from config without changes during migration

def _get_config_value(attr: str, default=None):
    """Get a config value, supporting both old and new import styles."""
    config = get_config()
    parts = attr.split(".")
    obj = config
    for part in parts:
        obj = getattr(obj, part, None)
        if obj is None:
            return default
    return obj


# Legacy environment variables
ON_KAGGLE = os.path.exists("/kaggle")
ON_GCP = not ON_KAGGLE and os.path.exists("/etc") and not os.path.exists("C:\\")
ON_WINDOWS = os.name == "nt"
ON_LINUX = not ON_WINDOWS
MT5_PATH = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

# Legacy config values
CURRENCIES = list(UniverseConfig().currencies)
ALL_PAIRS = list(UniverseConfig().all_pairs)
TRADEABLE_PAIRS = list(UniverseConfig().tradeable_pairs)
QUICK_TEST_PAIRS = list(UniverseConfig().quick_test_pairs)
QUICK_TEST_BARS = 50000

# Legacy strategy values
MACRO_TF = "4h"
MACRO_EMA_PERIOD = 200
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 3.0
RRR = 2.0
MIN_DIVERGENCE = 10.0
BREAKEVEN_RATIO = 1.5
ENABLE_MACRO_FILTER = True
ENABLE_REGIME_FLIP = True
REGIME_ATR_MULTIPLIER = 2.0
REGIME_LOOKBACK = 20
BACKTEST_N_JOBS = 1
RISK_PER_TRADE = 0.03
COMMISSION_PER_LOT = 6.0
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 1.0
MAX_LEVERAGE = 2000
MAX_MARGIN_USAGE_PCT = 0.75

# Legacy spread values
SPREAD_PIPS = SpreadConfig().spreads
DEFAULT_SPREAD_PIPS = 0.5
SLIPPAGE_PIPS = 0.1

# Legacy portfolio values
MAX_OPEN_TRADES = 1
MAX_PER_CURRENCY_BLOCK = 1

# Legacy Z-score values
Z_ENTRY_THRESHOLD = float(os.getenv("Z_ENTRY_THRESHOLD", "2.2"))
Z_EXIT_THRESHOLD = float(os.getenv("Z_EXIT_THRESHOLD", "0.5"))

# Legacy MR values
MR_ATR_MULT = float(os.getenv("MR_ATR_MULT", "1.0"))
MR_RSI_PERIOD = int(os.getenv("MR_RSI_PERIOD", "14"))
MR_RSI_OVERSOLD = int(os.getenv("MR_RSI_OVERSOLD", "30"))
MR_RSI_OVERBOUGHT = int(os.getenv("MR_RSI_OVERBOUGHT", "70"))
MR_RSI_EXIT_BUY = int(os.getenv("MR_RSI_EXIT_BUY", "50"))
MR_RSI_EXIT_SELL = int(os.getenv("MR_RSI_EXIT_SELL", "50"))
MR_ADX_PERIOD = int(os.getenv("MR_ADX_PERIOD", "14"))
MR_ADX_THRESHOLD = int(os.getenv("MR_ADX_THRESHOLD", "25"))
MR_ENABLE_DYNAMIC_LOT = os.getenv("MR_ENABLE_DYNAMIC_LOT", "true").lower() == "true"

# Legacy session values
SESSION_OPEN_UTC = int(os.getenv("SESSION_OPEN_UTC", "7"))
SESSION_CLOSE_UTC = int(os.getenv("SESSION_CLOSE_UTC", "21"))
MAX_ENTRY_HOUR = int(os.getenv("MAX_ENTRY_HOUR", "21"))
SCALE_SL_AT_SESSION_CLOSE = True
SESSION_CLOSE_MINUTES_BEFORE = 30
SKIP_MONDAY_OPEN = False
SKIP_FRIDAY_CLOSE = True

# Legacy news values
NEWS_BUFFER_MINUTES = 120
NEWS_FILTER_LEVELS = ["High", "Medium"]

# Legacy risk values
INITIAL_BALANCE = 200
FLOATING_LOSS_KILL_THRESHOLD = -15.0  # Hard close all at -$15 floating loss
MAX_DD_PCT = 55.0
DD_REDUCE_THRESHOLD = 30.0
DD_REDUCED_RISK = 0.02
ENABLE_RECOVERY = True
DYNAMIC_LOT_SCALING = True

# Legacy position management
BLOCK_SAME_DIRECTION_REENTRY = True
MAX_POSITION_RISK_PCT = 1.0
ENABLE_HARD_STOPS = False

# Legacy correlation
CORRELATION_ENABLED = True
CORRELATION_WINDOW = 20
CORRELATION_THRESHOLD = 0.70

# Legacy data paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MT5_DATA_CACHE = os.path.join(DATA_DIR, "mt5_matrix_pool.pkl")
MT5_BARS_TO_FETCH = 100000

# Legacy cTrader credentials
CTRADER_CLIENT_ID = os.getenv("CTRADER_CLIENT_ID", "")
CTRADER_CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET", "")
CTRADER_DEMO_CLIENT_ID = os.getenv("CTRADER_DEMO_CLIENT_ID", "")
CTRADER_DEMO_CLIENT_SECRET = os.getenv("CTRADER_DEMO_CLIENT_SECRET", "")
CTRADER_REDIRECT_URI = os.getenv(
    "CTRADER_REDIRECT_URI", "https://panama-crowbar-effort.ngrok-free.dev/ctrader/callback"
)
CTRADER_ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN", "")
CTRADER_ACCOUNT_ID = os.getenv("CTRADER_ACCOUNT_ID", "")
CTRADER_USE_LIVE = os.getenv("CTRADER_USE_LIVE", "false").lower() == "true"
CTRADER_AUTO_RECONNECT = True

# Legacy multi-account
ACCOUNTS_YAML = os.getenv("ACCOUNTS_YAML", "/root/accounts.yaml")

# Legacy circuit breaker
CB_WINRATE_20 = 0.40
CB_WINRATE_30 = 0.45
CB_SLIPPAGE_CONSECUTIVE = 4.8
CB_SLIPPAGE_CONSECUTIVE_COUNT = 3
CB_SLIPPAGE_AVG_10 = 6.0
CB_DD_PACE_SOFT_DD = 6.0
CB_DD_PACE_SOFT_TRADES = 5
CB_DD_PACE_HARD_DD = 8.5
CB_DD_PACE_HARD_TRADES = 10
CB_PF_TRAILING = 1.0
CB_PF_WINDOW = 20

# Legacy trade log
TRADE_LOG_COLUMNS = list(NestQuantConfig().trade_log_columns)

# Legacy live engine
LIVE_GROWTH_TARGET = float(os.getenv("LIVE_GROWTH_TARGET", "100.0"))
LIVE_MAX_LOT = float(os.getenv("LIVE_MAX_LOT", "0.20"))
LIVE_MAX_TRADES = int(os.getenv("LIVE_MAX_TRADES", "15"))
LIVE_LOG_DIR = os.getenv("LIVE_LOG_DIR", "/root/logs")

# Legacy alerting
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "true").lower() == "true"
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "sAkuxb8g7YGGJ_l0EjfSbw")
ALERT_WEBHOOK_TYPE = os.getenv("ALERT_WEBHOOK_TYPE", "ntfy")

# Legacy dashboard
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
DASHBOARD_USERS_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")
NEWS_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_news_calendar.csv")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")

# Legacy currency strength
STRENGTH_LOOKBACKS = [(5, 0.50), (10, 0.30), (20, 0.20)]
STRENGTH_NORMALIZE_WINDOW = 100
STRENGTH_TOP_N = 3
STRENGTH_MIN_DIVERGENCE = 5.0


# ── Startup guards ───────────────────────────────────────────────────────────
def _fail_if_missing_live_creds():
    """Raise RuntimeError if any cTrader credential needed for live trading
    is missing. Tests / backtests / dry-run smoke tests can bypass by setting
    NESTQUANT_SKIP_LIVE_CHECK=1 before importing config.
    """
    if os.getenv("NESTQUANT_SKIP_LIVE_CHECK", "0") == "1":
        return
    missing = [
        name for name, val in [
            ("CTRADER_CLIENT_ID", CTRADER_CLIENT_ID),
            ("CTRADER_CLIENT_SECRET", CTRADER_CLIENT_SECRET),
            ("CTRADER_ACCESS_TOKEN", CTRADER_ACCESS_TOKEN),
            ("CTRADER_ACCOUNT_ID", CTRADER_ACCOUNT_ID),
        ] if not val
    ]
    if CTRADER_ACCOUNT_ID in ("", "0"):
        if "CTRADER_ACCOUNT_ID" not in missing:
            missing.append("CTRADER_ACCOUNT_ID (cannot be 0)")
    if missing:
        raise RuntimeError(
            "NestQuant live trading requires these env vars: "
            + ", ".join(missing)
            + ". Set them in .env or disable with NESTQUANT_SKIP_LIVE_CHECK=1."
        )


def _fail_if_dashboard_secret_missing():
    """Without DASHBOARD_SECRET we silently fall back to a weak password hash.
    Fail loudly instead — the dashboard serves hashed user credentials.
    Backtests / engine runs can bypass with NESTQUANT_SKIP_DASHBOARD_CHECK=1.
    """
    if os.getenv("NESTQUANT_SKIP_DASHBOARD_CHECK", "0") == "1":
        return
    if not DASHBOARD_SECRET or len(DASHBOARD_SECRET) < 16:
        raise RuntimeError(
            "DASHBOARD_SECRET env var must be set (>=16 chars) before starting the "
            "dashboard. Otherwise password hashes are unsecure. Bypass with "
            "NESTQUANT_SKIP_DASHBOARD_CHECK=1 for tests."
        )
