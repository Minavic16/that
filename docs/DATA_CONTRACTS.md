# Z-Score Research Engine — Data Contracts

All data structures use Python dataclasses.
All timestamps are UTC (timezone-aware).
All prices are floats. All sizes are floats.

---

## 1. MarketData (Raw Ingested)

```python
@dataclass
class MarketData:
    pair: str                    # e.g., "EUR/USD"
    timestamps: pd.DatetimeIndex # UTC, minute-level, strictly ordered
    open: np.ndarray             # float64
    high: np.ndarray             # float64
    low: np.ndarray              # float64
    close: np.ndarray            # float64
    n: int                       # len(timestamps)
```

---

## 2. InstrumentMetadata

```python
@dataclass
class InstrumentMetadata:
    pair: str                    # e.g., "EUR/USD"
    pip_size: float              # e.g., 0.0001 for non-JPY, 0.01 for JPY
    pip_value_per_lot: float     # USD value of 1 pip for 1 standard lot
    typical_spread_pips: float   # historical median spread in pips
    contract_size: int           # typically 100000
```

---

## 3. ValidatedMarketData

```python
@dataclass
class ValidationReport:
    pair: str
    total_bars: int
    duplicate_timestamps: int
    missing_bars: int
    gap_timestamps: list         # timestamps where gaps were detected
    ohlc_violations: int         # bars where high < low, close outside range, etc.
    nan_counts: dict             # column -> number of NaN values
    is_valid: bool               # overall pass/fail

@dataclass
class ValidatedMarketData:
    market_data: MarketData
    validation: ValidationReport
```

---

## 4. NormalizedMarketData

```python
@dataclass
class NormalizedMarketData:
    pair: str
    metadata: InstrumentMetadata
    timestamps: pd.DatetimeIndex  # reference pair's timeline
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    n: int
    # Higher-timeframe indicators (forward-filled to analysis timeframe)
    ema_200: np.ndarray           # from 4h bars
    ema_50: np.ndarray            # from 4h bars
    daily_open: np.ndarray        # daily bar open, forward-filled
    daily_close: np.ndarray       # daily bar close, forward-filled (research only)
    daily_direction: np.ndarray   # bool: prev_day close > open (causal)
    # Metadata
    pip: float
    pv: float                     # pip value per lot
    spread: float                 # typical spread in pips
    daily: pd.DataFrame           # daily OHLCV (for regime/research use)
```

---

## 5. FeatureSet

```python
@dataclass
class FeatureSet:
    pair: str
    timestamps: pd.DatetimeIndex
    n: int
    atr_pct: np.ndarray           # ATR-14 as percentage of price
    rv_20: np.ndarray             # 20-bar realized volatility
    dist_ema200: np.ndarray       # percentage distance from EMA-200
    dist_ema50: np.ndarray        # percentage distance from EMA-50
```

---

## 6. RegimeState

```python
@dataclass
class RegimeState:
    pair: str
    timestamp: pd.Timestamp       # the bar this regime applies to
    trend: str                    # "near_ema200" | "weak_trend" | "strong_trend"
    volatility: str               # "low_vol" | "mid_vol" | "high_vol" | "extreme_vol" | "unknown"
    atr_percentile: float         # percentile of current ATR in expanding window
    is_causal: bool               # True = uses only past data; False = research label
```

---

## 7. ZScoreObservation

```python
@dataclass
class ZScoreObservation:
    pair: str
    timestamp: pd.Timestamp
    close: float
    z_score: float                # (close - rolling_mean) / rolling_std
    rolling_mean: float
    rolling_std: float
    lookback: int                 # number of bars used in calculation
    is_causal: bool               # True = no future data used
```

---

## 8. Signal

```python
@dataclass
class Signal:
    pair: str
    timestamp: pd.Timestamp
    direction: int                # 1 = long, -1 = short
    strength: float               # signal strength (e.g., Z-score magnitude)
    entry_price: float            # suggested entry (close + spread adjustment)
    sl_price: float               # suggested stop loss
    tp_price: float               # suggested take profit
    regime: RegimeState           # regime at signal time
    z_score: ZScoreObservation    # Z-score at signal time
    metadata: dict                # additional context
```

---

## 9. CostModel

```python
@dataclass
class CostModel:
    spread_pips: float            # per-pair spread in pips
    commission_per_lot: float     # commission in USD per lot per side
    slippage_pips: float          # estimated slippage in pips
    execution_delay_bars: int     # bars between signal and fill (0 = same bar)
```

---

## 10. SimulatedOrder

```python
@dataclass
class SimulatedOrder:
    pair: str
    timestamp: pd.Timestamp
    direction: int                # 1 = long, -1 = short
    entry_price: float            # actual fill price (after spread + slippage)
    sl_price: float
    tp_price: float
    lot_size: float
    cost_model: CostModel         # costs applied
    signal: Signal                # originating signal
```

---

## 11. Trade

```python
@dataclass
class Trade:
    pair: str
    direction: int
    entry_price: float
    exit_price: float
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    sl_price: float
    tp_price: float
    lot_size: float
    pnl: float                    # net PnL in USD (after costs)
    gross_pnl: float              # PnL before costs
    cost: float                   # total transaction cost
    exit_reason: str              # "SL" | "TP" | "SC" | "MH" | "DL"
    holding_bars: int
    is_win: bool
```

---

## 12. PortfolioState

```python
@dataclass
class PortfolioState:
    initial_balance: float
    balance: float
    equity_curve: np.ndarray      # balance at each bar
    trades: list[Trade]
    open_positions: list[dict]
    peak_balance: float
    max_drawdown_pct: float
    metrics: dict                 # computed performance metrics
```

---

## Field Naming Conventions

- `*_ts` — timestamp (pd.Timestamp, UTC)
- `*_pct` — percentage value
- `*_pips` — value in pips
- `*_bars` — count of bars
- `*_lot` — position size in lots
- `n` — count of elements
- `is_*` — boolean flag
- `*_price` — price level
