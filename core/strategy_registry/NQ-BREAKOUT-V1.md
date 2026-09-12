# NQ-BREAKOUT-V1

> **Canonical Breakout Strategy — Version 1**
> **Status:** FROZEN, CANONICAL, UNDER DEMO OBSERVATION
> **Identity:** `NQ-BREAKOUT-V1`
> **Source Commit:** `e706995`
> **Date Documented:** 2026-09-11

---

## 1. Strategy Identity

| Field | Value |
|-------|-------|
| `strategy_id` | `NQ-BREAKOUT-V1` |
| `version` | `V1` |
| `strategy_family` | `BREAKOUT` |
| `timeframe` | `4H` |
| `validation_status` | `DEMO_OBSERVATION` |
| `deployment_status` | `SHADOW` |
| `canonical` | `YES` |
| `frozen` | `YES` |
| `open_for_optimization` | `NO` |

---

## 2. Signal Generation

### 2.1 Core Signal Logic

NQ-BREAKOUT-V1 generates signals based on ATR-adjusted breakout levels. The signal generator uses recent swing highs/lows and ATR to determine entry, stop-loss, and take-profit levels.

### 2.2 Signal Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Timeframe | 4H | `signals/breakout.py` |
| Swing lookback | 5 bars | `signals/breakout.py:LOOKBACK=5` |
| ATR period | 14 | `signals/breakout.py:ATR_PERIOD=14` |
| ATR stop multiplier | 2.0 | `signals/breakout.py:ATR_SL_MULT=2.0` |
| Risk-Reward Ratio (RRR) | 3.5 | `signals/breakout.py:RRR=3.5` |

### 2.3 Direction Logic

BUY and SELL signals are generated symmetrically. There is no directional bias.

- **BUY:** Entry above current price, SL below entry, TP above entry
- **SELL:** Entry below current price, SL above entry, TP below entry

### 2.4 Entry Calculation

```
ATR = Average True Range over ATR_PERIOD bars
Swing High = Highest high over LOOKBACK bars
Swing Low = Lowest low over LOOKBACK bars

BUY Entry = Swing High + (ATR * some factor)
BUY SL = Entry - (ATR * ATR_SL_MULT)
BUY TP = Entry + (ATR * ATR_SL_MULT * RRR)

SELL Entry = Swing Low - (ATR * some factor)
SELL SL = Entry + (ATR * ATR_SL_MULT)
SELL TP = Entry - (ATR * ATR_SL_MULT * RRR)
```

### 2.5 Filters — NONE

The following filters are NOT active in V1:
- No correlation filter
- No currency-strength filter
- No session filter
- No EMA filter
- No ADX filter
- No news filter
- No regime filter

---

## 3. Trade Lifecycle

### 3.1 Lifecycle Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Breakeven activation | 0.8R | `strategy/trade_management/breakeven.py` |
| Maximum hold (time) | 7 days | `strategy/trade_management/max_hold.py` |
| Maximum hold (bars) | 42 bars (4H) | `strategy/trade_management/max_hold.py` |
| Trailing stop | Swing-based | `strategy/trade_management/trailing_stop.py` |

### 3.2 Lifecycle Behaviour

1. **Entry:** Signal fires → order submitted → fill confirmed → position tracked
2. **Breakeven:** When unrealized profit ≥ 0.8R, move SL to entry price
3. **Trailing:** Track swing highs/lows since entry; trail SL accordingly
4. **Max Hold:** If position held longer than 42 bars (7 days), force exit at market
5. **SL/TP:** Standard stop-loss and take-profit from entry geometry

### 3.3 Exit Reasons

| Reason | Description |
|--------|-------------|
| `STOP_LOSS` | SL price hit |
| `TAKE_PROFIT` | TP price hit |
| `BREAKEVEN` | SL moved to entry |
| `TRAILING_STOP` | Trailing SL hit |
| `MAX_HOLD` | Maximum holding period exceeded |
| `MANUAL` | Operator intervention |
| `KILL_SWITCH` | Emergency shutdown |

---

## 4. Risk Contract

### 4.1 Risk Parameters (CONSTITUTION)

| Parameter | Value | Source |
|-----------|-------|--------|
| Risk per trade | 0.15% equity | `config/constitution.py` |
| Max concurrent positions | 3 | `config/constitution.py` |
| Max position size per pair | 0.10 lots | `config/constitution.py` |
| Max total exposure | 3.0 lots | `config/constitution.py` |
| Max daily loss | 3% equity | `config/constitution.py` |
| Max drawdown | 8% equity | `config/constitution.py` |
| Max trades per day | 4 | `config/constitution.py` |

### 4.2 Risk Enforcement

Risk is enforced at multiple levels:
1. **Pre-trade:** `RiskGuard` validates each trade intent
2. **Prop firm:** `PropFirmGuard` validates prop firm constraints
3. **Circuit breakers:** `BreakerSuite` pauses trading on adverse conditions
4. **Kill switch:** Emergency stop via file-based sentinel

---

## 5. Execution

### 5.1 Execution Mode

| Mode | Status |
|------|--------|
| Live trading | DISABLED |
| Demo trading | ACTIVE (shadow observation) |
| Shadow | ACTIVE |

### 5.2 MT5 Integration

- MT5 HTTP bridge at `127.0.0.1:5001`
- No direct MT5 SDK import in Python
- All orders through `MT5ExecutionAdapter`
- Hard safety guard blocks order submission in shadow mode

### 5.3 Execution Safety

| Safety System | Status |
|---------------|--------|
| Kill switch | ENABLED |
| Hard guard (zero orders) | ENABLED in shadow |
| PropFirmGuard | ACTIVE |
| Circuit breakers | ACTIVE |
| Execution protection | ACTIVE |
| Demo/live separation | ENFORCED |

---

## 6. Data Requirements

| Requirement | Description |
|-------------|-------------|
| Instruments | 28 major/minor FX pairs |
| Timeframe | 4H OHLCV |
| History | Minimum 2 years for backtest |
| Source | Dukascopy / MT5 |
| Validation | Timestamp, OHLC integrity, gap detection |

---

## 7. Research Lineage

| Phase | Description |
|-------|-------------|
| S0 | Breakout strategy reassessment |
| S1 | Structural interrogation |
| S2 | Mechanism identification |
| S3 | Independent validation |
| S4 | Walk-forward sensitivity |
| S5.5 | Failure analysis |
| S6 | Adaptive risk and challenge optimization |
| S6C | Causal swing check |
| S7 | Live shadow experiment |
| S8 | Production readiness |
| S9 | Demo deployment |
| S10 | Shadow trading observation |

---

## 8. Deployment Status

| Aspect | Status |
|--------|--------|
| Shadow trading | ACTIVE |
| Demo observation | ACTIVE (14-day observation) |
| Live trading | DISABLED |
| Blue/Green role | BLUE (current trusted) |

---

## 9. Validation Evidence

Evidence packages are maintained in:
- `archive/research/reports/` — Historical phase reports
- `tests/` — Automated test suite
- `platform/strategy_registry/` — This document

---

## 10. Modification Policy

**NQ-BREAKOUT-V1 is FROZEN and NOT OPEN FOR DIRECT OPTIMIZATION.**

Any material modification MUST create a new strategy version (`NQ-BREAKOUT-V2`) and follow the complete strategy lifecycle.

Non-material changes (bug fixes, code refactoring) that preserve identical trading behaviour MAY be applied with:
1. Verification that trading behaviour is unchanged
2. Parity test confirmation
3. Code review approval
4. Documentation in change log

---

*End of NQ-BREAKOUT-V1 Canonical Identity*
