"""
NestQuant FX Strategy — Configuration
========================================
GCP-ready: paths use os.path.join, MT5 is optional.
"""

import multiprocessing as _mp
import os

# Load .env file
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

# ── Environment Detection ─────────────────────────────────────────────────────
ON_KAGGLE = os.path.exists("/kaggle")
ON_GCP = not ON_KAGGLE and os.path.exists("/etc") and not os.path.exists("C:\\")
ON_WINDOWS = os.name == "nt"
ON_LINUX = not ON_WINDOWS

# ── MT5 (optional — only for live trading) ────────────────────────────────────
MT5_PATH = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

# ── Parallelism ────────────────────────────────────────────────────────────────
N_CPUS = _mp.cpu_count()
BACKTEST_N_JOBS = int(os.getenv("BACKTEST_N_JOBS", str(max(1, N_CPUS - 2))))
DOWNLOAD_WORKERS = int(os.getenv("DOWNLOAD_WORKERS", str(min(8, N_CPUS))))

# ── Universe ──────────────────────────────────────────────────────────────────
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]

ALL_PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "USD/CAD",
    "AUD/USD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/JPY",
    "EUR/CHF",
    "EUR/CAD",
    "EUR/AUD",
    "EUR/NZD",
    "GBP/JPY",
    "GBP/CHF",
    "GBP/CAD",
    "GBP/AUD",
    "GBP/NZD",
    "CHF/JPY",
    "CAD/JPY",
    "AUD/JPY",
    "NZD/JPY",
    "AUD/CAD",
    "AUD/CHF",
    "AUD/NZD",
    "NZD/CAD",
    "NZD/CHF",
    "CAD/CHF",
]

TRADEABLE_PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD",
    "NZD/USD",
    "EUR/JPY",
    "GBP/JPY",
]

# ── Currency Strength ─────────────────────────────────────────────────────────
STRENGTH_LOOKBACKS = [(5, 0.50), (10, 0.30), (20, 0.20)]
STRENGTH_NORMALIZE_WINDOW = 100
STRENGTH_TOP_N = 3
STRENGTH_MIN_DIVERGENCE = 5.0

# ── Strategy — System B Trend-Follow with TF Scaling ───────────────────────────
MACRO_TF = "4h"  # Macro trend anchor timeframe
MACRO_EMA_PERIOD = 200  # EMA period for macro trend determination
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 3.0  # Stop loss = ATR × multiplier
RRR = 2.0  # Reward:risk ratio (TP = SL × RRR)
MIN_DIVERGENCE = 10.0  # Minimum currency strength divergence for entry
BREAKEVEN_RATIO = 1.5  # Move SL to entry when R:R reaches this (1.5:1)
ENABLE_MACRO_FILTER = True  # Only trade in direction of 4H EMA-200 trend
RISK_PER_TRADE = 0.03  # 3% risk per trade (validated via clean-room MC)
COMMISSION_PER_LOT = 6.0  # Pepperstone $6/lot round-turn ($0.06/0.01 lot)
MIN_LOT_SIZE = 0.01
MAX_LOT_SIZE = 1.0  # Allow lots to scale with account growth
MAX_LEVERAGE = 2000  # Exness Standard max leverage
MAX_MARGIN_USAGE_PCT = 0.75  # Max 75% of equity as margin

# ── Slippage / Spread Model (Exness Standard Account) ──────────────────────────
# Standard account: no commission, spread-only. Costs are spread × pip_value × lots.
# These are typical spreads during liquid hours (London/NY overlap):
SPREAD_PIPS = {
    "EUR/USD": 0.8,
    "GBP/USD": 1.0,
    "USD/JPY": 1.0,
    "USD/CHF": 1.2,
    "USD/CAD": 1.4,
    "AUD/USD": 0.9,
    "NZD/USD": 1.2,
    "EUR/JPY": 1.6,
    "GBP/JPY": 2.0,
}
DEFAULT_SPREAD_PIPS = 0.5
SLIPPAGE_PIPS = 0.1  # Per side slippage in pips

# ── Correlation / Portfolio Limits ─────────────────────────────────────────────
MAX_OPEN_TRADES = 1
MAX_PER_CURRENCY_BLOCK = 1

# ── Z-Score Strategy Thresholds ────────────────────────────────────────────────
Z_ENTRY_THRESHOLD = float(os.getenv("Z_ENTRY_THRESHOLD", "2.2"))
Z_EXIT_THRESHOLD = float(os.getenv("Z_EXIT_THRESHOLD", "0.5"))

# ── MR (Mean Reversion) Strategy — RSI+ADX ────────────────────────────────────
MR_ATR_MULT = float(os.getenv("MR_ATR_MULT", "1.0"))
MR_RSI_PERIOD = int(os.getenv("MR_RSI_PERIOD", "14"))
MR_RSI_OVERSOLD = int(os.getenv("MR_RSI_OVERSOLD", "30"))
MR_RSI_OVERBOUGHT = int(os.getenv("MR_RSI_OVERBOUGHT", "70"))
MR_RSI_EXIT_BUY = int(os.getenv("MR_RSI_EXIT_BUY", "50"))
MR_RSI_EXIT_SELL = int(os.getenv("MR_RSI_EXIT_SELL", "50"))
MR_ADX_PERIOD = int(os.getenv("MR_ADX_PERIOD", "14"))
MR_ADX_THRESHOLD = int(os.getenv("MR_ADX_THRESHOLD", "25"))
MR_ENABLE_DYNAMIC_LOT = os.getenv("MR_ENABLE_DYNAMIC_LOT", "true").lower() == "true"

# ── Session Filter ────────────────────────────────────────────────────────────
SESSION_OPEN_UTC = int(os.getenv("SESSION_OPEN_UTC", "7"))
SESSION_CLOSE_UTC = int(os.getenv("SESSION_CLOSE_UTC", "21"))
MAX_ENTRY_HOUR = int(os.getenv("MAX_ENTRY_HOUR", "21"))
SCALE_SL_AT_SESSION_CLOSE = True  # Tighten SLs as session close approaches (gap protection)
SESSION_CLOSE_MINUTES_BEFORE = 30  # Start scaling SL 30 min before session close (18:30 UTC)
SKIP_MONDAY_OPEN = False
SKIP_FRIDAY_CLOSE = True

# ── News Filter ────────────────────────────────────────────────────────────────
NEWS_BUFFER_MINUTES = 120

NEWS_FILTER_LEVELS = ["High", "Medium"]

# ── Risk ────────────────────────────────────────────────────────────────────
INITIAL_BALANCE = 200  # $200 starting equity (avoids minimum-lot constraint)
MAX_DD_PCT = 55.0  # Circuit breaker at 55% DD (P99 max DD = 49.1%)
DD_REDUCE_THRESHOLD = 30.0  # Reduce risk when DD exceeds 30%
DD_REDUCED_RISK = 0.02  # 2% risk during elevated DD
ENABLE_RECOVERY = True
DYNAMIC_LOT_SCALING = True  # Scale lot by account equity (3% risk)

# ── Position Management ────────────────────────────────────────────────────────
BLOCK_SAME_DIRECTION_REENTRY = True
MAX_POSITION_RISK_PCT = 1.0  # Effectively disabled
ENABLE_HARD_STOPS = False  # No hard stops

# ── Dynamic Correlation Guard ──────────────────────────────────────────────────
CORRELATION_ENABLED = True  # Enable rolling correlation checks
CORRELATION_WINDOW = 20  # Trading days for rolling pair correlation
CORRELATION_THRESHOLD = 0.70  # Block new entry if |r| > this AND same direction

# ── Data ───────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MT5_DATA_CACHE = os.path.join(DATA_DIR, "mt5_matrix_pool.pkl")
MT5_BARS_TO_FETCH = 100000

# ── cTrader Live Trading ─────────────────────────────────────────────────────────
# ⚠ Read from env ONLY — no defaults. Load .env (above) and require these in
# the environment before the live engine starts; the live/DualEngine startup
# checks below will raise a clear error if missing.
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

# ── Multi-Account Config (YAML) ──────────────────────────────────────────────────
ACCOUNTS_YAML = os.getenv("ACCOUNTS_YAML", "/root/accounts.yaml")

# ── Circuit Breaker Thresholds (Account A only) ─────────────────────────────────
CB_WINRATE_20 = 0.40  # Pause if WR < 40% over rolling 20 trades
CB_WINRATE_30 = 0.45  # Pause if WR < 45% over rolling 30 trades
CB_SLIPPAGE_CONSECUTIVE = 4.8  # Pause if 3 consecutive trades > this many pips
CB_SLIPPAGE_CONSECUTIVE_COUNT = 3
CB_SLIPPAGE_AVG_10 = 6.0  # Pause if rolling 10-trade avg slippage > this
CB_DD_PACE_SOFT_DD = 6.0  # Soft pause if DD > 6% before trade 5
CB_DD_PACE_SOFT_TRADES = 5
CB_DD_PACE_HARD_DD = 8.5  # Hard stop if DD > 8.5% before trade 10
CB_DD_PACE_HARD_TRADES = 10
CB_PF_TRAILING = 1.0  # Pause if trailing 20-trade PF < 1.0
CB_PF_WINDOW = 20

# ── Trade Log Schema ────────────────────────────────────────────────────────────
TRADE_LOG_COLUMNS = [
    "timestamp",
    "account",
    "pair",
    "direction",
    "entry_price",
    "fill_price",
    "slippage_pips",
    "lot_size",
    "pnl",
    "equity_after",
    "dd_pct",
    "exit_reason",
    "regime_at_entry",
    "breaker_trigger",
    "breaker_value",
]

# ── Live Engine Settings ────────────────────────────────────────────────────────
LIVE_GROWTH_TARGET = float(os.getenv("LIVE_GROWTH_TARGET", "100.0"))
LIVE_MAX_LOT = float(os.getenv("LIVE_MAX_LOT", "0.20"))
LIVE_MAX_TRADES = int(os.getenv("LIVE_MAX_TRADES", "15"))
LIVE_LOG_DIR = os.getenv("LIVE_LOG_DIR", "/root/logs")

# ── Alerting (Free via ntfy.sh) ───────────────────────────────────────────────────
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "true").lower() == "true"
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "sAkuxb8g7YGGJ_l0EjfSbw")
ALERT_WEBHOOK_TYPE = os.getenv("ALERT_WEBHOOK_TYPE", "ntfy")

# ── Dashboard Auth ──────────────────────────────────────────────────────────────
# Secret salt for password hashing — read from env ONLY. Startup check below
# raises if DASHBOARD_SECRET is not set, so we never silently use a weak default.
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "")
DASHBOARD_USERS_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

# ── News Filter ─────────────────────────────────────────────────────────────────
# Absolute path so the news filter loads regardless of CWD (systemd unit,
# bash launcher from another dir, etc.). The prior relative path silently
# disabled the filter whenever CWD != repo root.
NEWS_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_news_calendar.csv")

# ── Output ─────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")

# ── Quick Test Mode (fewer pairs, shorter period for smoke test) ──────────────
QUICK_TEST_PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "NZD/USD",
    "EUR/JPY",
    "GBP/JPY",
]
QUICK_TEST_BARS = 50000


# ── Startup guards ───────────────────────────────────────────────────────────
# These run at import time and *fail loudly* in any process that imports
# `config` and would otherwise silently trade/broker/salt without secrets.
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
    # Account ID "0" / "" are treated as missing — matches the dual_engine
    # _connect_client path which would otherwise loop retries on id=0.
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
