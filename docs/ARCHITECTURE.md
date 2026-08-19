# Z-Score Research Engine — Architecture

## Pipeline Overview

```
Data Ingestion
  → Data Validation
    → Normalized Market Data
      → News Data (optional enrichment)
        → Feature Calculation
          → Regime Classification (causal)
            → Z-Score Calculation (causal)
              → Signal Generation
                → Execution/Cost Simulation
                  → Portfolio Accounting
                    → Research Reporting
```

Each stage receives explicit inputs and produces explicit outputs.
Stages are independently testable.
No stage may read data from a future timestamp.

---

## Stage 1: Data Ingestion

**Input:** Raw pickle files per pair (OHLCV minute bars)
**Output:** `MarketData` per pair (validated, typed, timezone-normalized)

Responsible for:
- Loading pickle files
- Parsing timestamps to UTC
- Basic type coercion

NOT responsible for:
- Validation (stage 2)
- Feature calculation (stage 4)

---

## Stage 2: Data Validation

**Input:** `MarketData` per pair
**Output:** `ValidatedMarketData` (validation report attached)

Checks:
- Timestamps are ordered (strictly monotonically increasing)
- No duplicate timestamps
- No missing bars (gap detection)
- OHLC consistency: open/high/low/close relationships
- No NaN in critical columns
- Timezone is explicit and consistent
- Session boundaries are detectable

Validation failures are logged, not silently repaired.
A validation report is attached to each pair's data.

---

## Stage 3: Normalized Market Data

**Input:** `ValidatedMarketData` per pair
**Output:** `NormalizedMarketData` (aligned to common timeline)

Responsible for:
- Aligning all pairs to a common reference timeline (merge_asof)
- Forward-filling indicators that need higher-timeframe data
- Attaching instrument metadata (pip size, pip value, spread estimate)

This is the canonical data structure consumed by all downstream stages.

---

## Stage 4: Feature Calculation

**Input:** `NormalizedMarketData`
**Output:** `FeatureSet` per bar per pair

Features (initial set):
- EMA-200 (4h timeframe, forward-filled to analysis timeframe)
- EMA-50 (4h timeframe)
- ATR-14 percentage (normalized by price)
- Realized volatility (20-bar rolling std of returns)
- Distance from EMA-200 (percentage)
- Distance from EMA-50 (percentage)

All features are causal: at timestamp t, feature values depend only on data at or before t.

Future features (not yet implemented):
- Z-score of price relative to rolling mean
- Spread behavior
- Cross-pair correlations
- News proximity features

---

## Stage 5: Regime Classification (Causal)

**Input:** `FeatureSet`
**Output:** `RegimeState` per bar per pair

Two classifications (independent dimensions):

**Trend dimension:**
- `near_ema200` (|distance| < 0.1%)
- `weak_trend` (0.1% <= |distance| < 0.3%)
- `strong_trend` (|distance| >= 0.3%)

**Volatility dimension:**
- `low_vol` (ATR percentile <= 25th, expanding window, min 200 bars)
- `mid_vol` (25th < ATR percentile < 75th)
- `high_vol` (ATR percentile >= 75th, < 95th)
- `extreme_vol` (ATR percentile >= 95th)

CRITICAL: Volatility percentiles are computed using an expanding window.
At timestamp t, only data from the first bar through t is used.
No future data contaminates the classification.

**Distinction:**
- `RegimeState.causal` — available to the strategy at decision time
- `RegimeState.research` — retrospective labels for analysis only (not yet implemented)

---

## Stage 6: Z-Score Calculation (Causal)

**Input:** `NormalizedMarketData`, `FeatureSet`, `RegimeState`
**Output:** `ZScoreObservation` per bar per pair

Z-score computation:
1. Compute rolling mean of close prices (configurable lookback)
2. Compute rolling standard deviation (same lookback)
3. Z-score = (close - rolling_mean) / rolling_std

CRITICAL: Both rolling_mean and rolling_std use expanding or rolling windows
that never look past timestamp t.

Lookback sensitivity analysis:
- Test multiple lookback windows (e.g., 20, 50, 100, 200 bars)
- Report distribution of Z-scores
- Report forward returns at each Z-score level

---

## Stage 7: Signal Generation

**Input:** `ZScoreObservation`, `RegimeState`, configuration
**Output:** `Signal` per bar per pair (or None)

Initial signal logic (placeholder — not optimized):
- LONG when Z-score < -threshold AND regime allows entry
- SHORT when Z-score > +threshold AND regime allows entry
- Session filter applied
- Daily direction filter (causal: previous day's close > open)

Signals are distinct from trades.
Signal count is reported separately from trade count.

---

## Stage 8: Execution/Cost Simulation

**Input:** `Signal`, cost model configuration
**Output:** `SimulatedOrder` per signal

Applies:
- Spread (configurable per pair)
- Commission (configurable)
- Slippage model (configurable)
- Execution delay (optional, configurable)
- Position sizing (risk-based, from existing portfolio/position_sizer.py)

Does NOT:
- Connect to any broker
- Modify any live infrastructure
- Use future data for cost estimation

---

## Stage 9: Portfolio Accounting

**Input:** `SimulatedOrder` list, market data
**Output:** `PortfolioState` (equity curve, trades, metrics)

Tracks:
- Open positions
- Closed trades (entry, exit, PnL, holding period)
- Equity curve
- Maximum drawdown
- Monthly returns
- Session-level returns

Metrics computed:
- Profit factor
- Win rate
- Expectancy (mean trade PnL)
- Sharpe ratio
- Sortino ratio
- Recovery factor
- Break-even spread/commission/slippage

---

## Stage 10: Research Reporting

**Input:** `PortfolioState`, all intermediate data
**Output:** JSON metrics file + human-readable summary

Reports:
- Full configuration snapshot
- Git commit hash
- Date range, instruments, timeframe, timezone
- Transaction cost assumptions
- Regime breakdown
- Yearly breakdown
- Session breakdown
- Causality test results
- Walk-forward results (when applicable)

---

## Separation of Concerns

| Layer | Purpose | Dependencies |
|-------|---------|-------------|
| `data/` | Ingestion, validation, normalization | pickle files |
| `features/` | Feature calculation | data layer |
| `regime/` | Regime classification | features layer |
| `zscore/` | Z-score calculation | data + features |
| `signals/` | Signal generation | zscore + regime |
| `costs/` | Cost model | configuration |
| `execution/` | Order simulation | signals + costs |
| `portfolio/` | Accounting | execution + data |
| `reporting/` | Output generation | portfolio |
| `tests/` | All test categories | all layers |

Live trading infrastructure (execution/base.py, engines/) is SEPARATE
from the research pipeline. The research pipeline never imports
live-trading code.
