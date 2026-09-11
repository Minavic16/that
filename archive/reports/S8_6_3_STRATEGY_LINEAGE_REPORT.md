# S8.6.3 — Strategy Research Lineage and Deployment Reconciliation

**Date:** 2026-09-04
**Status:** Complete — Gate Decision: RED
**Predecessor:** S8.6.2 Monitoring Architecture Consolidation
**Code Changes:** None (investigation only)

---

## 1. Executive Conclusion

**NestQuant currently has no validated historical performance population for the exact strategy it intends to deploy.**

The investigation proved:

1. **Breakeven and max-hold are PROVEN EXECUTED** in every research population (S0, S5.5, S6A). They are not phantom parameters — they materially affect trade outcomes.

2. **The deployed `breakout.py` does NOT implement either feature.** This creates a research/deployment lineage break.

3. **NO historical population exactly matches the deployed strategy.** All research was conducted with BE/MH enabled.

4. **Raw OHLCV data is unavailable** (excluded by `.gitignore`), preventing re-runs without BE/MH.

5. **No trade-level records exist** for any population — only aggregate statistics.

**This is the real gate.** Not C7. Not monitoring calibration. The strategy identity must be resolved before any further progress.

**Gate: RED** — deployment strategy lacks historical validation.

---

## 2. Complete Research-to-Deployment Lineage

```
phase_s0_breakout_reassessment.py
    │
    ├── simulate() [line 90]
    │   ├── breakeven: bool = True  ← DEFAULT ON
    │   ├── max_bars = MAX_HOLD_DAYS * 6 = 42 bars
    │   ├── BE: close_[i] - entry >= 0.8 * risk → sl = entry  [line 156-158]
    │   ├── MH: bars_held >= 42 → exit at close  [line 146-151]
    │   └── All calls use defaults (breakeven=True, trailing=True)
    │
    └── Output: S0_breakout_results.json (1002 trades, 73% WR)

phase_s5_5_failure_analysis.py
    │
    ├── simulate_realistic() [line 141]
    │   ├── MAX_HOLD_DAYS = 7  ← HARDCODED (no toggle)
    │   ├── BREAKEVEN_RATIO = 0.8  ← HARDCODED (no toggle)
    │   ├── max_bars = 7 * 6 = 42 bars
    │   ├── BE: close_[i] - entry >= 0.8 * risk → sl = entry  [line 214-215]
    │   ├── MH: bars_held >= 42 → exit at close  [line 206-208]
    │   └── No parameter to disable BE/MH
    │
    └── Output: S5_5_failure_analysis.json (15321 trades, 35.9% monthly WR)

phase_s6_adaptive_risk.py
    │
    ├── simulate_with_risk_scaling() [line 146]
    │   ├── MAX_HOLD_DAYS = 7  ← HARDCODED (same as S5.5)
    │   ├── BREAKEVEN_RATIO = 0.8  ← HARDCODED (same as S5.5)
    │   ├── max_bars = 42 bars
    │   ├── BE: close_[i] - entry >= 0.8 * risk → sl = entry  [line 224-225]
    │   ├── MH: bars_held >= 42 → exit at close  [line 216-218]
    │   └── Only difference from S5.5: risk_mults parameter
    │
    └── Output: S6_adaptive_risk_challenge.json (15321 trades, WR=35.7%)

signals/breakout.py  ← DEPLOYED
    │
    ├── generate() [line 44]
    │   ├── NO breakeven parameter
    │   ├── NO max_hold parameter
    │   ├── NO trailing parameter
    │   ├── Signal only (no trade management)
    │   └── Returns SignalResult (direction, entry, SL, TP)
    │
    └── Gap: No trade simulation logic at all
```

### Critical Lineage Break

The research scripts (`phase_s0`, `phase_s5_5`, `phase_s6`) contain **complete backtest engines** with entry, SL, TP, breakeven, max-hold, and trailing logic.

The deployed `signals/breakout.py` contains **only signal generation** — no trade management.

The trade management that WILL be used in live trading has not been validated against any historical population.

---

## 3. Evidence: BE/MH Were Actually Executed

### 3.1 Breakeven Execution Proof

**S0** (`phase_s0_breakout_reassessment.py:156-158`):
```python
if breakeven and sl_price < entry_price and risk > 0:
    if (close_[i] - entry_price) / pip >= BREAKEVEN_RATIO * risk:
        sl_price = entry_price
```
- `breakeven` defaults to `True` (line 93)
- Called as `simulate(sigs[p], p, sl_mult=ATR_SL_MULT, rrr=RRR, cost_pips=0.0)` — no `breakeven=False` override
- **VERDICT: Executed on every trade**

**S5.5** (`phase_s5_5_failure_analysis.py:214-215`):
```python
if (close_[i] - entry_price) / pip >= breakeven_ratio * risk:
    sl_price = entry_price
```
- `breakeven_ratio=BREAKEVEN_RATIO=0.8` (line 34, hardcoded)
- No toggle to disable
- **VERDICT: Executed on every trade**

**S6** (`phase_s6_adaptive_risk.py:224-225`):
- Identical code to S5.5
- **VERDICT: Executed on every trade**

### 3.2 Max Hold Execution Proof

**S0** (`phase_s0_breakout_reassessment.py:146-151`):
```python
if bars_held >= max_bars and risk > 0:
    pnl = (close_[i] - entry_price) / pip - total_cost
    # ... record trade, exit
```
- `max_bars = MAX_HOLD_DAYS * 6 = 42` bars (4h timeframe → 7 days)
- **VERDICT: Executed when holding period exceeded**

**S5.5** (`phase_s5_5_failure_analysis.py:206-208`):
```python
elif bars_held >= max_bars and risk > 0:
    exit_price = close_[i]
    exit_reason = "MH"
```
- **VERDICT: Executed, exit reason recorded as "MH"**

**S6** (`phase_s6_adaptive_risk.py:216-218`):
- Identical to S5.5
- **VERDICT: Executed**

### 3.3 Trailing Stop Execution Proof

**S0** (`phase_s0_breakout_reassessment.py:152-155`):
```python
if trailing:
    new_sl = sl_[i - 1] if not np.isnan(sl_[i - 1]) else sl_price
    if new_sl > sl_price:
        sl_price = new_sl
```
- `trailing: bool = True` (line 93, default)
- Moves SL to confirmed swing low/high when favorable
- **VERDICT: Executed on every trade**

**S5.5** (`phase_s5_5_failure_analysis.py:210-212`):
- Same trailing logic (without the `if trailing:` guard — always on)
- **VERDICT: Always executed**

---

## 4. Strategy Variant Identity Table

| Parameter | Variant A (S0/S5.5/S6A) | Variant B (deployed breakout.py) |
|-----------|------------------------|----------------------------------|
| Entry | Swing breakout | Swing breakout |
| Timeframe | 4h | Not specified in code |
| Instruments | 28 pairs (all) | 7 pairs (settings) |
| ATR period | 14 | 14 |
| ATR SL mult | 2.0 | 2.0 |
| RRR | 3.5 | 3.5 |
| Lookback | 5 | 5 |
| **Breakeven** | **0.8R (ON)** | **Not implemented** |
| **Max hold** | **7 days (42 bars)** | **Not implemented** |
| **Trailing** | **Swing-based (ON)** | **Not implemented** |
| Session filter | None | None |
| Macro filter | None | None |
| News filter | None | None |
| Cost model | Spread + slippage + commission | None specified |
| **Trade mgmt** | **Full (entry/SL/TP/BE/MH/trail)** | **Signal only (no trade mgmt)** |

**Variant A and Variant B are NOT the same strategy.**

Variant A has three additional trade management mechanisms (BE, MH, trailing) that fundamentally alter:
- Win rate (BE reduces losses → higher WR)
- Average win (BE caps some wins → lower avg win)
- Holding time (MH forces exits → shorter holds)
- Trade frequency (MH frees capital → more trades)
- Drawdown profile (BE limits downside → shallower DDs)

---

## 5. Research Population Mapping

| Population | Variant | BE | MH | Trailing | Source |
|-----------|---------|-----|-----|----------|--------|
| S0 | A | 0.8R | 7d | Swing | `phase_s0_breakout_reassessment.py` |
| S5.5 | A | 0.8R | 7d | Swing | `phase_s5_5_failure_analysis.py` |
| S6A | A | 0.8R | 7d | Swing | `phase_s6_adaptive_risk.py` |
| Deployed | B | OFF | OFF | OFF | `signals/breakout.py` |

**No population matches Variant B.**

---

## 6. Why Were BE/MH Introduced?

### 6.1 Git History

The git log shows:
```
6adc810 chore: checkpoint S0-S6 research state + execution architecture
4abb039 chore: checkpoint recovered NestQuant research state
5dd3841 Initial NestQuant baseline
```

The commit message for `6adc810` says:
> S0: Breakout reassessment (1002 trades, 73% WR, PF=5.32)
> S5.5: Failure analysis (regime transitions → false breakouts)
> S6: Adaptive risk (0.30% risk recommended, 24 tests pass)

**BE/MH were present from the earliest recoverable state.** There is no commit that shows "introduced breakeven" or "added max_hold". They were part of the original research implementation.

### 6.2 Research Reports

- `S5_5_FAILURE_REPORT.md`: "WHY DOES THE STRATEGY LOSE?" — S5.5 investigated failure modes of the BE/MH-enabled strategy
- `S6_ADAPTIVE_RISK_REPORT.md`: S6 investigated risk scaling for the same BE/MH-enabled strategy
- Both reports treat BE/MH as integral parts of the strategy, not temporary additions

### 6.3 Assessment

BE/MH were introduced as **core trade management features** of the breakout strategy. They are:
- Part of the original strategy design
- Consistent across all research phases (S0 through S6)
- Never toggled off in any research run
- Never documented as temporary or experimental

**They are not research artifacts. They are validated strategy components.**

---

## 7. Raw Data Recovery Investigation

### 7.1 Search Results

| Location | Result |
|----------|--------|
| `/root/data/*.pkl` | **NOT FOUND** — directory does not exist |
| `/root/that/data/` | **NOT FOUND** |
| `/sdcard/*.pkl` | **NOT FOUND** |
| `/tmp/*.pkl` | **NOT FOUND** |
| Git repository | `*.pkl` excluded by `.gitignore` |

### 7.2 .gitignore Analysis

```
# Trading/runtime data
*.pkl
*.tar.gz
```

**Raw OHLCV data was never committed to version control.** The `.gitignore` explicitly excludes `.pkl` files.

### 7.3 Impact

Without raw data:
- Cannot re-run backtests without BE/MH
- Cannot generate Variant B population
- Cannot validate the deployed strategy
- Cannot produce trade-level records

### 7.4 Recovery Options

1. **Locate original data source** (Dukascopy downloads, MT5 data cache)
2. **Re-download** from data provider
3. **Check MT5 bridge** for cached data on VPS
4. **Check Docker volumes** for data containers

---

## 8. Trade-Level Artifact Recovery

### 8.1 What Exists

| Artifact | Location | Strategy | Trade-level? |
|----------|----------|----------|-------------|
| S0 results | `S0_breakout_results.json` | Variant A | **NO** (aggregate per year/variant) |
| S5.5 stats | `S5_5_failure_analysis.json` | Variant A | **NO** (monthly aggregates) |
| S6 stats | `S6_adaptive_risk_challenge.json` | Variant A | **NO** (aggregate only) |
| Phase 11 trades | `phase11_trade_results.csv` | Z-Score (different strategy) | YES (114K rows) |
| Phase 4 trades | `zscore_mr_trades.json` | Z-Score (different strategy) | YES (74K trades) |

### 8.2 What Does NOT Exist

- No trade-level records for S0/S5.5/S6A
- No equity curves for S0/S5.5/S6A
- No R-multiple sequences for S0/S5.5/S6A
- No per-trade PnL for any breakout variant

### 8.3 Impact

Without trade-level records:
- Cannot compute precise rolling WR distributions
- Cannot compute rolling EV distributions
- Cannot perform exact DD clustering analysis
- Cannot calibrate monitoring thresholds precisely

---

## 9. Drawdown Representation Audit

### 9.1 Current Conventions

| Location | Convention | Example |
|----------|-----------|---------|
| `S6_adaptive_risk_challenge.json` | `max_dd_pips`: **negative** | -1804.68 |
| `S6_adaptive_risk_challenge.json` | `max_dd_r`: **positive** | 19.61 |
| `S5_5_failure_analysis.json` | `max_dd` (monthly): **negative** | -1193.87 |
| `monitoring/equity_tracker.py` | `drawdown_pct`: **negative** | Uses `(peak - equity) / peak * 100` |
| `risk/circuit_breakers.py` | `current_dd`: **positive** | `(peak - equity) / peak * 100` |
| `monitoring/dd_clustering.py` | DD depth: **positive** | `(peak - trough) / peak` |

### 9.2 The Bug This Caused

S8.6.1 reported P95 monthly max DD = 164 pips. Since values were negative, P95 = -164 (mildest), not severe. The direction was inverted.

### 9.3 Recommended Canonical Convention

**Internal representation: drawdown_magnitude >= 0 (positive = worse)**

```
0R = no drawdown
5R = moderate DD
10R = significant DD
20R = severe DD (S6A max)
```

Percentile interpretation becomes intuitive:
- P50 = median DD magnitude
- P95 = severe DD
- P99 = extreme DD

This prevents the class of bug found in S8.6.1.

---

## 10. Reproducibility Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Strategy identity documented | ✅ | Canonical identity established |
| Config hash covers all parameters | ❌ | Hash includes phantom BE/MH |
| Raw data available | ❌ | Excluded by .gitignore |
| Trade-level records exist | ❌ | Only aggregates |
| Backtest scripts available | ✅ | But require raw data |
| BE/MH execution proven | ✅ | Code-level trace complete |
| Re-run possible | ❌ | Without raw data |

**The research is reproducible in principle but NOT in practice on the current system.**

---

## 11. Resolution Paths

### Path A: Deploy the Historically Validated Strategy

**Action**: Implement breakeven (0.8R), max hold (7d), and trailing in `breakout.py`.

| Aspect | Assessment |
|--------|-----------|
| Scientific validity | **HIGH** — matches validated population |
| Reproducibility | **HIGH** — S6A baseline applies |
| Implementation risk | **LOW** — known features, known behavior |
| Research cost | **NONE** — already researched |
| Monitoring calibration | **S6A baselines become valid** |
| Time required | **Short** — implement 3 features |

**Risk**: Adds features that change WR from ~36% to ~73% (S0 comparison). The live strategy would look very different from what was discussed in S8.6.1 monitoring calibration.

### Path B: Re-run Without BE/MH

**Action**: Restore raw data, modify scripts to disable BE/MH, re-run backtest.

| Aspect | Assessment |
|--------|-----------|
| Scientific validity | **MEDIUM** — new population, needs full validation |
| Reproducibility | **LOW** — requires data restoration |
| Implementation risk | **MEDIUM** — untested variant |
| Research cost | **HIGH** — full S0-S6 re-run needed |
| Time required | **Weeks** — data acquisition + re-run + validation |

**Risk**: The no-BE/no-MH variant may not have an edge. WR drops significantly without BE.

### Path C: Locate Another Matching Population

**Action**: Search for historical data where BE/MH were disabled.

| Aspect | Assessment |
|--------|-----------|
| Scientific validity | **UNKNOWN** — depends on what's found |
| Reproducibility | **UNKNOWN** |
| Implementation risk | **UNKNOWN** |
| Research cost | **UNKNOWN** |
| Time required | **Unknown** |

**Risk**: Unlikely to exist. All known research used BE/MH.

---

## 12. Gate Decision

### S8.6.3 STRATEGY LINEAGE RECONCILIATION: **RED**

**RED** — deployment strategy lacks historical validation.

**Rationale:**
- ✅ BE/MH proven executed in all research populations
- ✅ Lineage from research to deployment traced
- ✅ Drawdown convention bug identified
- ✅ Raw data location determined (not available)
- ❌ NO historical population matches the deployed strategy
- ❌ Raw data unavailable for re-runs
- ❌ No trade-level records exist
- ❌ Deployment has no validated baseline
- ❌ Config hash includes phantom parameters

**The deployed strategy (no BE/MH) has never been researched.**

**Do not proceed to C7. Do not modify breaker thresholds. Do not enable live trading.**

The strategy identity must be resolved first:
- **Path A** (recommended unless investigation reveals otherwise): Implement BE/MH in breakout.py, making S6A the valid baseline
- **Path B** (if no-BE/no-MH is intentional): Restore data, re-run, validate from scratch

---

*End of S8.6.3 Strategy Research Lineage Report*
