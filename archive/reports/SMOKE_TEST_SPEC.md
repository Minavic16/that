# Z-Score Research Engine — Smoke Test Specification

## Purpose

Verify the complete pipeline executes end-to-end on a SMALL dataset
and produces structurally valid output.

This is NOT a correctness test. It is a structural integrity test.

---

## Dataset

Use a minimal synthetic dataset:
- 1 pair: "TEST/USD"
- 500 bars: 2024-01-02 00:00 UTC to 2024-01-04 08:20 UTC (minute bars)
- Generated with known properties (trending up, then ranging)
- No real market data required

---

## Pipeline Steps and Assertions

### Step 1: Data Ingestion
```
Load synthetic OHLCV → MarketData
```
Assertions:
- `MarketData.n == 500`
- `timestamps.dtype` is datetime64 with UTC timezone
- `timestamps.is_monotonic_increasing` is True
- No NaN in open/high/low/close

### Step 2: Data Validation
```
MarketData → ValidatedMarketData
```
Assertions:
- `validation.is_valid is True`
- `validation.duplicate_timestamps == 0`
- `validation.ohlc_violations == 0`
- `validation.nan_counts` all zero for OHLC columns
- `validation.missing_bars == 0`

### Step 3: Normalized Market Data
```
ValidatedMarketData → NormalizedMarketData
```
Assertions:
- `normalized.n == 500`
- `normalized.pip > 0`
- `normalized.pv > 0`
- `normalized.spread > 0`
- `daily_direction` is causal: uses previous day's close > open

### Step 4: Feature Calculation
```
NormalizedMarketData → FeatureSet
```
Assertions:
- `features.n == 500`
- `features.atr_pct` has no NaN after min_history bars
- `features.rv_20` has no NaN after min_history bars
- `features.dist_ema200` has no NaN after EMA warmup

### Step 5: Regime Classification
```
FeatureSet → RegimeState per bar
```
Assertions:
- Every bar has a RegimeState
- `regime.trend in ["near_ema200", "weak_trend", "strong_trend"]`
- `regime.volatility in ["low_vol", "mid_vol", "high_vol", "extreme_vol", "unknown"]`
- First 200 bars have `volatility == "unknown"` (insufficient history)
- `regime.is_causal is True`

### Step 6: Z-Score Calculation
```
NormalizedMarketData, FeatureSet → ZScoreObservation per bar
```
Assertions:
- First `lookback` bars have no Z-score (insufficient history)
- Z-score values are finite (not NaN, not inf)
- Z-score is computed using only past data

### Step 7: Signal Generation
```
ZScoreObservation, RegimeState → Signal (or None)
```
Assertions:
- Signals have valid direction (1 or -1)
- Signals have valid entry/sl/tp prices
- Signal count is reported (may be 0)

### Step 8: Transaction Cost Simulation
```
Signal → SimulatedOrder
```
Assertions:
- Order has explicit cost breakdown
- `order.entry_price` includes spread + slippage
- `order.cost_model` is recorded

### Step 9: Trade Execution Simulation
```
SimulatedOrder → Trade
```
Assertions:
- Trade PnL is computed
- Trade has entry/exit timestamps
- Trade has exit reason
- `trade.pnl == trade.gross_pnl - trade.cost`

### Step 10: Portfolio Accounting
```
Trades → PortfolioState
```
Assertions:
- `portfolio.initial_balance > 0`
- `portfolio.balance == initial_balance + sum(trade.pnl)`
- `portfolio.equity_curve` length matches trade count + 1
- `portfolio.max_drawdown_pct >= 0`
- `portfolio.max_drawdown_pct <= 1`

### Step 11: Report Generation
```
PortfolioState → JSON report
```
Assertions:
- Report is valid JSON
- Contains required fields: trades, pf, wr, pnl, mdd
- Report is written to disk

---

## Determinism

- All random seeds set explicitly
- No floating-point non-determinism (use fixed data)
- Pipeline produces identical output on every run

---

## Implementation

```python
def test_smoke_pipeline():
    """Minimal end-to-end smoke test."""
    # Generate synthetic data
    # Run full pipeline
    # Assert all structural properties
    # Verify no future data was consumed
    # Output: PASS/FAIL with details
```
