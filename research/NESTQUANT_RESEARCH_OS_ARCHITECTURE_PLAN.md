# NestQuant Research OS Architecture Plan

> **Version:** 0.1.0  
> **Date:** 2026-09-21  
> **Status:** Architecture Review  
> **Scope:** Common Research OS for all NestQuant research strategies  
> **Constraint:** Document only — no code changes

---

## 1. Executive Summary

This document specifies the architecture for a common NestQuant Research OS (ROS) that serves as shared infrastructure for all research strategies. The ROS is NOT a standalone system — it is the backbone that R2.1, R2.2, and future strategies consume.

**Key Design Decisions:**

- **Alternating IS/OOS blocks are mandatory architecture**, not optional add-on
- **R2.1 must NOT expand its own isolated infrastructure** — it consumes the common ROS
- **Equity-curve continuity across IS→OOS transitions** is resolved at the Portfolio/Account layer
- **Metrics are specifications** (§11a-11i), not suggestions — each classified MVP/later/research-specific/execution-specific/optional
- **Needle is transport only** — no write/execute capabilities, human remains control point

---

## 2. System Purpose and Philosophy

### 2.1 What the Research OS Is

The NestQuant Research OS is a **common infrastructure layer** that provides:

- Data acquisition, validation, and provenance tracking
- Backtesting engines with realistic cost modeling
- Walk-forward validation with alternating IS/OOS blocks
- Statistical robustness testing (bootstrap, Monte Carlo)
- Research ledger and experiment lifecycle management
- Metrics calculation and aggregation
- Integration boundaries with production NQTS

### 2.2 What the Research OS Is NOT

- It is NOT a strategy itself
- It is NOT a replacement for production NQTS
- It is NOT a research methodology (that's in `core/governance/RESEARCH_OPERATING_SYSTEM.md`)
- It is NOT a decision-making system (humans decide)

### 2.3 Core Principles

1. **Evidence determines progression** — not methodology changes after results
2. **Causality is mandatory** — future data never affects past forecasts
3. **Alternating IS/OOS is the validation backbone** — every experiment uses it
4. **Research stays isolated from production** — no accidental deployment
5. **Metrics are specifications** — each classified by lifecycle stage

---

## 3. Repository Architecture

### 3.1 Current Structure (Verified)

```
/root/that/
├── core/
│   ├── architecture/        # Architecture reports and decisions
│   ├── configuration/       # Settings, constitution, frozen parameters
│   ├── contracts/           # Execution contracts, cost models
│   ├── data/                # DataLoader (pickle-based OHLCV)
│   ├── governance/          # ROS, strategy lifecycle, policies
│   ├── knowledge/           # Experiment tracker, lessons learned
│   └── tooling/             # Logger, indicators, utilities
├── production/
│   ├── execution/           # Risk guard, orchestration, base executor
│   ├── monitoring/          # Equity tracker, architecture (4-layer)
│   ├── notifications/       # Event bus, Telegram, dedup
│   ├── portfolio/           # Position sizer
│   ├── risk/                # Circuit breakers
│   ├── signals/             # Base signal, breakout signal
│   └── strategy/            # Lifecycle, trade management
├── research/
│   ├── shared/              # Common research infrastructure
│   │   ├── analytics/       # ResearchAnalyzer, monthly stats
│   │   ├── backtest/        # Metrics, comparison
│   │   ├── costs/           # Cost model
│   │   ├── engines/         # BacktestEngine, RegimeBacktestEngine
│   │   ├── regime/          # ADX, hybrid, labels, tabfm
│   │   └── zscore/          # Z-score normalization
│   ├── experiments/         # 35 experiment scripts
│   │   └── strategy2/       # R2.1 experiment design and code
│   ├── current/             # Active research
│   ├── proposed/            # Proposed research
│   └── results/             # Experiment outputs
├── tests/                   # Test suite
└── archive/                 # Historical, deprecated
```

### 3.2 Architecture Compliance

Per `core/architecture/REPOSITORY_ARCHITECTURE.md`:
- `production/` may import from `core/` (platform equivalents)
- `research/` may import from `core/` (platform equivalents)
- `production/` MUST NOT import from `research/`
- `research/` MUST NOT import from `production/` (with one exception: `production/monitoring/percentiles.py` is used by `research/shared/analytics/`)

---

## 4. Core Infrastructure

### 4.1 Contracts (`core/contracts/`)

**Execution Pipeline:**
```
TradeIntent → RiskDecision → OrderRequest → ExecutionResult
```

- `TradeIntent`: Pair, direction, entry, SL, TP, lot size
- `RiskDecision`: Approved/rejected with reason
- `OrderRequest`: Execution-ready order
- `ExecutionResult`: Fill price, slippage, latency, status

**Cost Model:**
```
MarketData → NormalizedMarketData → CostModel → CostBreakdown
```

- `MarketData`: Raw OHLCV + spread
- `NormalizedMarketData`: Z-score normalized features
- `CostModel`: Spread, commission, slippage estimates
- `CostBreakdown`: Per-trade cost decomposition

### 4.2 Configuration (`core/configuration/`)

**Frozen Parameters (constitution.py):**
- Risk limits: 0.15%/trade, 3 positions, 0.10 lots
- Circuit breakers: 3% daily loss, 8% drawdown
- Strategy parameters: lookback=5, ATR=14, mult=2.0, RRR=3.5

**Runtime Configuration (settings.py):**
- `UniverseConfig`: Pairs, timeframes, data sources
- `StrategyConfig`: Signal parameters, lifecycle settings
- `RiskConfig`: Position limits, exposure controls
- `DataConfig`: Data sources, cache settings

### 4.3 Data Layer (`core/data/`)

**DataLoader:**
- Pickle-based OHLCV storage
- Pair-specific data files
- Date-range slicing
- Missing data detection

**Data Validation (per ROS Gate 1):**
- Chronological ordering
- Duplicate detection
- Missing observations
- OHLC consistency
- Weekend gap handling

### 4.4 Tooling (`core/tooling/`)

- `logger.py`: Structured logging (GFT dispute evidence)
- `indicators/`: Session detection, technical indicators
- `utils/`: General utilities

---

## 5. Research Pipeline Architecture

### 5.1 Lifecycle Stages (from `core/governance/STRATEGY_LIFECYCLE.md`)

```
IDEA → PROPOSED_RESEARCH → CURRENT_RESEARCH → BACKTEST → COST_MODEL
→ ROBUSTNESS → OUT_OF_SAMPLE → WALK_FORWARD/STRESS → COMPLEMENTARITY
→ STRATEGY_IDENTITY → IMPLEMENTATION → PARITY → SHADOW → DEMO
→ BLUE/GREEN → CANARY → CONTROLLED_LIVE → PROMOTION
```

### 5.2 ROS Gates (from `core/governance/RESEARCH_OPERATING_SYSTEM.md`)

| Gate | Name | Purpose |
|------|------|---------|
| G0 | Research Definition | Hypothesis is falsifiable and testable |
| G1 | Data Integrity | Dataset is suitable for research |
| G2 | Apparatus & Causality | Implementation faithfully executes protocol |
| G3 | Cheap Falsification | Hypothesis deserves further investigation |
| G4 | Primary Causal OOS | Phenomenon survives unseen chronological data |
| G5 | Temporal Robustness | Effect is not localized to specific periods |
| G6 | Statistical Robustness | Effect survives reasonable perturbations |
| G7 | Replication | Result survives independent variation |
| G8 | Economic Relevance | Statistically significant → economically useful |
| G9 | NQTS Integration Test | Candidate improves frozen baseline |

### 5.3 Experiment State Machine

```
PROPOSED → SPECIFIED → DATA_VALIDATED → APPARATUS_VALIDATED
→ CHEAP_SCREEN → CAUSAL_OOS → TEMPORAL_ROBUSTNESS
→ STATISTICAL_ROBUSTNESS → REPLICATED → NQTS_MAPPED
→ INTEGRATION_TESTED → PROMOTION_CANDIDATE

Terminal states: KILLED, ARCHIVED, INCONCLUSIVE
```

---

## 6. Alternating IS/OOS Pipeline

### 6.1 Architecture (Mandatory)

The alternating IS/OOS block pipeline is the **validation backbone** of the Research OS. It is NOT an optional add-on.

**Structure:**
```
Partition A: [IS] [OOS] [IS] [OOS] [IS] [OOS]
Partition B: [OOS] [IS] [OOS] [IS] [OOS] [IS]
```

Every block is evaluated in both IS and OOS roles across partitions.

### 6.2 Block Sizes

Per ROS §12, block size is a **robustness dimension**, not an optimization variable:

1. Weekly (5 bars at 4H)
2. Monthly (~20 bars)
3. Quarterly (~60 bars)
4. Semiannual (~120 bars)
5. Annual (~240 bars)

### 6.3 Equity-Curve Continuity

**Problem:** When transitioning from IS→OOS, equity curves must be continuous. A new IS block cannot start with a fresh account balance.

**Solution:** The Portfolio/Account layer maintains:
- Running balance across all blocks
- Per-block P&L attribution
- Continuous equity curve with block boundaries marked
- Separate IS/OOS metrics computed on the continuous curve

**Implementation:** `research/shared/backtest/metrics.py` must track:
- `block_id`: Which IS/OOS block
- `block_type`: "IS" or "OOS"
- `running_balance`: Balance at block start
- `block_pnl`: P&L during this block
- `cumulative_equity`: Continuous equity curve

### 6.4 Walk-Forward Validation

**Pipeline:**
```
For each block:
  1. Load data for block period
  2. If IS block: fit model, generate signals
  3. If OOS block: apply frozen model, generate signals
  4. Execute through BacktestEngine
  5. Record metrics with block_id and block_type
  6. Append to continuous equity curve
```

**Key invariant:** OOS blocks NEVER re-fit the model. The model is frozen at the end of the preceding IS block.

---

## 7. Engine Architecture

### 7.1 Engine Hierarchy

```
BaseEngine (ABC)
├── BacktestEngine          # Single-pass backtest
├── RegimeBacktestEngine    # Regime-conditional backtest
└── WalkForwardEngine       # Alternating IS/OOS (new)
```

### 7.2 BaseEngine (`research/shared/engines/base_engine.py`)

**State machine:**
```
INIT → RUNNING → STOPPED → ERROR
```

**Methods:**
- `start()`: Initialize engine
- `process_bar(bar)`: Process single OHLCV bar
- `stop()`: Finalize and compute results
- `get_results()`: Return engine results

### 7.3 BacktestEngine (`research/shared/engines/backtest_engine.py`)

**Configuration:**
```python
BacktestConfig:
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.02
    max_open_trades: int = 1
    commission_per_lot: float = 6.0
    spread_pips: float = 1.0
    slippage_pips: float = 0.1
```

**Features:**
- Trade lifecycle management (open, close, SL/TP)
- BreakerSuite integration (circuit breakers)
- Balance tracking and drawdown calculation

### 7.4 RegimeBacktestEngine (`research/shared/engines/regime_backtest_engine.py`)

- Extends BacktestEngine with regime awareness
- Uses regime classifiers (ADX, hybrid, labels)
- Regime-conditional signal generation

### 7.5 WalkForwardEngine (New — to be built)

**Purpose:** Alternating IS/OOS block pipeline

**Configuration:**
```python
WalkForwardConfig:
    block_sizes: list[int]  # e.g., [5, 20, 60, 120, 240]
    is_oos_pattern: list[str]  # e.g., ["IS", "OOS", "IS", "OOS"]
    model_refit_frequency: int  # Blocks between model refits
    equity_continuity: bool = True
```

**Pipeline:**
```
1. Partition data into blocks
2. For each block:
   a. Determine block_type (IS/OOS)
   b. If IS: fit model, record model state
   c. If OOS: load frozen model from last IS block
   d. Generate signals through BacktestEngine
   e. Record metrics with block metadata
   f. Append to continuous equity curve
3. Aggregate metrics across blocks
4. Compute robustness statistics
```

---

## 8. Signal Architecture

### 8.1 Signal Hierarchy

```
BaseSignal (ABC)
├── BreakoutSignal          # Production: 5-bar swing, ATR 14
├── ZScoreMRSignal          # Research: z-score mean reversion
└── [Future signals]        # Strategy 2 candidates
```

### 8.2 BaseSignal (`production/signals/base.py`)

**Interface:**
```python
class BaseSignal(ABC):
    def generate(self, bar: MarketData) -> SignalResult
    def reset(self) -> None
```

**SignalResult:**
```python
SignalResult:
    signal: str  # "BUY", "SELL", "HOLD"
    strength: float  # 0.0 to 1.0
    metadata: dict  # Signal-specific data
```

### 8.3 BreakoutSignal (`production/signals/breakout.py`)

**Parameters (frozen):**
- `lookback`: 5 bars
- `atr_period`: 14
- `atr_multiplier`: 2.0
- `risk_reward_ratio`: 3.5

**Logic:**
- 5-bar swing high/low breakout
- ATR-based stop loss (2x ATR)
- RRR-based take profit (3.5x risk)

---

## 9. Portfolio and Execution Architecture

### 9.1 Position Sizing (`production/portfolio/position_sizer.py`)

**Interface:**
```python
def calculate_position_size(
    risk_per_trade: float,
    stop_distance_pips: float,
    pip_value: float,
    account_balance: float
) -> float
```

**Constraints:**
- Max positions: 3
- Max lots per trade: 0.10
- Max total exposure: 3.0 lots

### 9.2 Risk Guard (`production/execution/risk_guard.py`)

**Evaluation:**
```python
class RiskEvaluator:
    def evaluate(self, intent: TradeIntent) -> RiskDecision
```

**Checks:**
- Per-trade risk limit
- Position count limit
- Exposure limit
- Daily loss limit
- Drawdown limit

### 9.3 Execution Orchestration (`production/execution/orchestration.py`)

**Pipeline:**
```
TradeIntent → RiskEvaluator → OrderRequest → Executor → ExecutionResult
```

### 9.4 Equity-Curve Continuity (ROS Integration)

**Problem:** R2.1 and future strategies need continuous equity curves across IS/OOS transitions.

**Solution:** The Portfolio layer provides:
- `EquityTracker`: Maintains running balance
- `BlockAttribution`: Per-block P&L breakdown
- `ContinuousCurve`: Equity curve with block boundaries

**Interface:**
```python
class EquityTracker:
    def start_block(self, block_id: str, block_type: str) -> None
    def record_trade(self, trade: Trade) -> None
    def end_block(self) -> BlockResult
    def get_continuous_curve(self) -> pd.Series
```

---

## 10. Risk Management Architecture

### 10.1 Circuit Breakers (`production/risk/circuit_breakers.py`)

**BreakerSuite:**
- `pause`: Temporary trading halt
- `hard_stop`: Permanent stop until manual review

**Triggers:**
- Daily loss > 3%
- Drawdown > 8%
- Consecutive losses threshold

### 10.2 Risk Parameters (Frozen)

```python
CONSTITUTION = {
    "risk_per_trade": 0.0015,  # 0.15%
    "max_positions": 3,
    "max_lots_per_trade": 0.10,
    "max_total_exposure": 3.0,
    "daily_loss_limit": 0.03,  # 3%
    "drawdown_limit": 0.08,    # 8%
    "max_trades_per_day": 4,
}
```

---

## 11. Metrics and Analytics

### 11.1 Metrics Classification (Mandatory)

Each metric is classified by lifecycle stage relevance:

| ID | Metric | Classification | MVP? | Description |
|----|--------|---------------|------|-------------|
| 11a | Sharpe Ratio | Research-Specific | Yes | Risk-adjusted return |
| 11b | Sortino Ratio | Research-Specific | Yes | Downside risk-adjusted return |
| 11c | Maximum Drawdown | Research-Specific | Yes | Worst peak-to-trough |
| 11d | Win Rate | Research-Specific | Yes | Fraction of winning trades |
| 11e | Profit Factor | Research-Specific | Yes | Gross profit / gross loss |
| 11f | Expectancy | Research-Specific | Yes | Average trade P&L |
| 11g | Block Hit Rate | Research-Specific | Yes | % of OOS blocks beating baseline |
| 11h | Pair Consistency | Research-Specific | Yes | % of pairs with positive effect |
| 11i | Regime Consistency | Research-Specific | Yes | % of regimes where effect survives |
| 11j | Latency | Execution-Specific | No | Order execution latency |
| 11k | Slippage | Execution-Specific | No | Actual vs expected fill |
| 11l | Fill Rate | Execution-Specific | No | % of orders filled |
| 11m | Turnover | Optional | No | Trading frequency |
| 11n | Exposure | Optional | No | Average position size |
| 11o | Tail Loss | Optional | No | 5th percentile loss |
| 11p | Transaction-Cost-Adjusted Return | Research-Specific | Yes | Return after all costs |

### 11.2 Metrics Calculation (`research/shared/backtest/metrics.py`)

**BacktestMetrics:**
```python
@dataclass
class BacktestMetrics:
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    expectancy: float
    total_trades: int
    # Block-level metrics
    block_hit_rate: float
    pair_consistency: float
    regime_consistency: float
```

**calculate_metrics(trades, equity_curve) → BacktestMetrics**

### 11.3 Research Analysis (`research/shared/analytics/research_analysis.py`)

**ResearchAnalyzer:**
- `analyze_monthly_stats()`: Monthly PnL, DD, consecutive losses distributions
- `analyze_drawdown_episodes()`: Reconstruct drawdown episodes
- `analyze_consecutive_losses()`: Loss streak analysis
- `analyze_risk_scaling()`: Risk-scaled DD analysis
- `analyze_monte_carlo()`: Monte Carlo simulation percentiles
- `analyze_year_by_year()`: Year-by-year stats

---

## 12. Monitoring Architecture

### 12.1 Four-Layer Architecture (`production/monitoring/architecture.py`)

```
Layer 1 — Observation
    Collect raw facts. No decisions.

Layer 2 — Statistical Engine
    Calculate distributions, percentiles, rolling stats.
    Still no trading decisions.

Layer 3 — Monitoring Classification
    Classify observations into states:
        NORMAL / ELEVATED / WARNING / EXTREME

Layer 4 — Decision Engine
    Combine classifications into trading decisions.
    Hard safety limits bypass statistical classification.
```

### 12.2 Metric States

```python
class MetricState(Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    WARNING = "WARNING"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"
```

### 12.3 Classification Logic

```python
def classify_percentile(value, percentiles, direction):
    """
    HIGH_IS_BAD: < p75 = NORMAL, p75-p90 = ELEVATED, p90-p95 = WARNING, > p95 = EXTREME
    LOW_IS_BAD: > p25 = NORMAL, p10-p25 = ELEVATED, p5-p10 = WARNING, < p5 = EXTREME
    """
```

---

## 13. Configuration Management

### 13.1 Configuration Hierarchy

```
CONSTITUTION (frozen, immutable)
├── Risk parameters
├── Strategy parameters
└── Circuit breaker thresholds

SETTINGS (runtime configurable)
├── Universe (pairs, timeframes)
├── Data sources
├── Execution mode
└── Logging level

EXPERIMENT (per-experiment)
├── Hypothesis
├── Methodology
├── Validation protocol
└── Kill/promotion criteria
```

### 13.2 Configuration Loading

```python
# Core settings
from nestquant.core.configuration.settings import (
    UniverseConfig, StrategyConfig, RiskConfig, DataConfig
)

# Frozen constitution
from nestquant.core.configuration.constitution import CONSTITUTION
```

---

## 14. Research Operating System (ROS)

### 14.1 ROS Specification

Full specification in `core/governance/RESEARCH_OPERATING_SYSTEM.md` (1104 lines).

### 14.2 Key Requirements

1. **Pre-registration:** Hypothesis, mechanism, observable, null/alternative, universe, timeframe, horizons, models, baselines, metrics, validation, kill criteria — all defined before results.

2. **Falsification Before Optimization:** Cheap falsification precedes expensive optimization.

3. **Causality Is Mandatory:** `ŷ_{t+h} = f(X_{≤t})` — no future data leakage.

4. **Replication Before Promotion:** Result must survive variation in time, instrument, regime, model, data.

5. **No Opportunistic Model Expansion:** Models declared before experiment.

6. **Production Isolation:** Research never modifies production.

### 14.3 Research Card

Every hypothesis must have a Research Card with:
- Research ID, Hypothesis ID
- Hypothesis, Mechanism, Observable
- Null/Alternative hypotheses
- Universe, Timeframe, Horizons
- Models, Baselines, Costs
- Dataset, Validation, Metrics
- Kill/Promotion criteria

---

## 15. R2.1 Integration Requirements

### 15.1 R2.1 Scope

R2.1 investigates conditional volatility in 4H FX markets:
- Does conditional volatility contain stable OOS predictive information?
- Can it improve NQTS position sizing, risk limits, circuit breakers, stop placement?

### 15.2 R2.1 Must Consume (NOT Build)

| Component | Source | R2.1 Usage |
|-----------|--------|------------|
| Data loading | `core/data/loader.py` | Load 4H OHLCV |
| Backtest engine | `research/shared/engines/backtest_engine.py` | Run backtests |
| Cost model | `research/shared/costs/model.py` | Apply transaction costs |
| Metrics | `research/shared/backtest/metrics.py` | Calculate performance |
| Walk-forward | WalkForwardEngine (new) | Alternating IS/OOS |
| Experiment tracking | `core/knowledge/experiment_tracker.py` | Record results |
| Monitoring architecture | `production/monitoring/architecture.py` | Classify metrics |

### 15.3 R2.1 Must NOT Build

- Its own backtest engine (use common)
- Its own cost model (use common)
- Its own metrics calculation (use common)
- Its own data loading (use common)
- Its own walk-forward pipeline (use common)

### 15.4 R2.1 Experiment Design

Per `research/experiments/strategy2/R2.1_EXPERIMENT_DESIGN.md`:

**Baselines:**
1. Naive (yesterday's volatility)
2. Rolling window (W ∈ {12, 24, 48, 96})
3. EWMA (λ ∈ {0.94, 0.97})

**Models:**
1. GARCH(1,1)
2. GJR-GARCH(1,1)
3. HAR-RV
4. [Model family declared before experiment]

**Horizons:**
- 1 bar (4h), 3 bars (12h), 6 bars (24h), 12 bars (48h)

**Metrics:**
- MAE, RMSE, relative improvement vs baseline
- Block hit rate, pair consistency, regime consistency

---

## 16. Needle Integration

### 16.1 Needle Role

Needle is a **transport/orchestration layer** only:
- Locates reports
- Copies to clipboard
- Transfers feedback
- Never makes independent decisions
- Never writes to codebase

### 16.2 Handoff Workflow

```
OpenCode → writes report → /root/Needle/handoff/latest_report.md
Human → runs `needle report` → copies to clipboard
Human → pastes into ChatGPT/Claude → reviewer provides feedback
Human → pastes feedback into reviewer_feedback.md
Human → runs `needle feedback` → copies to clipboard
Human → pastes into OpenCode → OpenCode continues
```

### 16.3 Constraint

- Needle tools remain READ-ONLY
- No write, execute, or destructive capabilities
- Human remains the control point

---

## 17. Testing Strategy

### 17.1 Test Categories

```
tests/
├── core/              # Configuration, contracts, data
├── production/        # Execution, monitoring, signals
├── research/          # Engines, metrics, analytics
├── integration/       # End-to-end pipeline tests
├── causality/         # Data leakage prevention
├── regression/        # Known-good result verification
├── synthetic/         # Controlled data tests
└── unit/              # Component-level tests
```

### 17.2 Test Requirements

Per ROS Gate 2:
- 100% of critical causality tests must pass
- No exceptions
- Future data cannot affect past forecasts
- OOS data cannot affect model fitting
- Normalization fitted only on training data

### 17.3 Running Tests

```bash
cd /root/nestquant
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 -m pytest tests/ -v
```

---

## 18. Deployment Architecture

### 18.1 VPS Deployment

```
/root/nestquant/                     # VPS repo root
├── production/
│   ├── deployment/
│   │   ├── run_live_shadow.py       # Runner entry point
│   │   └── nqts-dashboard.service   # Systemd service
│   └── dashboard/                   # Next.js dashboard
└── logs/                            # Runtime logs
```

### 18.2 Services

| Service | Command | Status |
|---------|---------|--------|
| Dashboard | `systemctl status nqts-dashboard` | active |
| Runner | `pgrep -f run_live_shadow` | RUNNING |
| MT5 Bridge | Flask at `http://127.0.0.1:5001` | connected |

### 18.3 Runner Start Command

```bash
cd /root/nestquant
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  nohup python3 -u production/deployment/run_live_shadow.py \
  --use-wine-flask --api-url http://127.0.0.1:5001 \
  --pairs EUR/USD GBP/USD USD/JPY ... \
  --timeframe 4h --poll 60 \
  --log-dir /root/nestquant/logs/shadow_live &
```

---

## 19. Implementation Roadmap

### 19.1 MVP Components (Must Have)

| # | Component | Priority | Depends On |
|---|-----------|----------|------------|
| 1 | WalkForwardEngine | High | BacktestEngine |
| 2 | EquityCurve continuity | High | EquityTracker |
| 3 | Block metrics (11a-11i) | High | BacktestEngine |
| 4 | Experiment state machine | High | ExperimentTracker |
| 5 | Research Card schema | Medium | Configuration |
| 6 | Causality tests | High | Synthetic data |

### 19.2 Needed Later

| # | Component | Priority | Depends On |
|---|-----------|----------|------------|
| 7 | Monte Carlo engine | Medium | BacktestEngine |
| 8 | Bootstrap engine | Medium | BacktestEngine |
| 9 | Regime-aware walk-forward | Low | RegimeBacktestEngine |
| 10 | Cross-pair analysis | Low | Metrics |
| 11 | Dashboard integration | Low | Monitoring |

### 19.3 Research-Specific

| # | Component | Priority | Depends On |
|---|-----------|----------|------------|
| 12 | Volatility model zoo | Medium | R2.1 |
| 13 | HAR-RV implementation | Medium | R2.1 |
| 14 | GARCH/GJR-GARCH | Medium | R2.1 |

### 19.4 Execution-Specific

| # | Component | Priority | Depends On |
|---|-----------|----------|------------|
| 15 | Latency tracking | Low | Execution |
| 16 | Slippage analysis | Low | Execution |
| 17 | Fill rate metrics | Low | Execution |

### 19.5 Optional

| # | Component | Priority | Depends On |
|---|-----------|----------|------------|
| 18 | Turnover metrics | Low | Metrics |
| 19 | Exposure metrics | Low | Portfolio |
| 20 | Tail loss metrics | Low | Metrics |

---

## 20. Open Questions

1. **WalkForwardEngine location:** Should it be in `research/shared/engines/` or a new `research/shared/validation/` directory?

2. **Equity curve continuity:** Should the EquityTracker live in `research/shared/backtest/` or `core/`?

3. **Experiment state machine:** Should it be in `core/knowledge/` or `research/shared/`?

4. **R2.1 model fitting:** Where should the IS model fitting logic live? In the WalkForwardEngine or in R2.1-specific code?

5. **Metrics aggregation:** Should block-level metrics be computed by the WalkForwardEngine or by the metrics module?

6. **Research Card storage:** JSON files in `research/experiments/`? Or a more structured approach?

---

## Appendix A: File Reference

| File | Purpose |
|------|---------|
| `core/contracts/execution_contracts.py` | TradeIntent, RiskDecision, OrderRequest, ExecutionResult |
| `core/contracts/zscore_contracts.py` | MarketData, NormalizedMarketData, CostModel, CostBreakdown |
| `core/configuration/settings.py` | UniverseConfig, StrategyConfig, RiskConfig, DataConfig |
| `core/configuration/constitution.py` | Frozen CONSTITUTION risk parameters |
| `core/data/loader.py` | DataLoader (pickle-based OHLCV) |
| `core/governance/RESEARCH_OPERATING_SYSTEM.md` | Full ROS specification (1104 lines) |
| `core/governance/STRATEGY_LIFECYCLE.md` | 18-stage strategy lifecycle |
| `core/knowledge/experiment_tracker.py` | Experiment state tracking |
| `production/signals/base.py` | BaseSignal, SignalResult |
| `production/signals/breakout.py` | BreakoutSignal (production) |
| `production/execution/risk_guard.py` | RiskGuard (per-trade risk) |
| `production/execution/orchestration.py` | ExecutionCoordinator Protocol |
| `production/portfolio/position_sizer.py` | Position sizing |
| `production/risk/circuit_breakers.py` | BreakerSuite |
| `production/monitoring/architecture.py` | 4-layer monitoring, MetricState, classify_percentile |
| `production/strategy/lifecycle/contracts.py` | TradeGeometry, PositionLifecycleState |
| `research/shared/engines/base_engine.py` | BaseEngine ABC, EngineState |
| `research/shared/engines/backtest_engine.py` | BacktestEngine, BacktestConfig, Trade |
| `research/shared/engines/regime_backtest_engine.py` | RegimeBacktestEngine |
| `research/shared/backtest/metrics.py` | BacktestMetrics, calculate_metrics |
| `research/shared/costs/model.py` | Cost model |
| `research/shared/analytics/research_analysis.py` | ResearchAnalyzer |
| `research/experiment.py` | ExperimentConfig, git commit tracking |
| `research/experiments/strategy2/R2.1_EXPERIMENT_DESIGN.md` | R2.1 experiment design |
| `research/STRATEGY2_CHARTER.md` | Strategy 2 research charter |

---

*End of NestQuant Research OS Architecture Plan*
