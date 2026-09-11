# Timeframe Migration Plan — NestQuant Research Engine

**Date:** 2026-08-13
**Status:** PROPOSAL — No files modified
**Goal:** Evaluate moving primary research timeframe from 1-minute to 1H (with 4H robustness comparison), and investigate 5min/15min/30min candles.

---

## 1. Current State: Where Timeframe Assumptions Exist

### 1.1 Critical Locations (would break at non-1min)

| File | Line(s) | Assumption | Impact |
|------|---------|------------|--------|
| `scripts/download_fx_data.py` | 151 | `INTERVAL_MIN_1` hardcoded | Downloads only 1-min data |
| `indicators/resampler.py` | 21-25, 56-58 | Docstrings say "1-min OHLCV DataFrame" | Misleading but functional |
| `zscore/features.py` | 39, 52 | `sqrt(252*390)` annualization | 390 = 1-min bars in US equity day; wrong for FX and wrong for non-1min |
| `phase*_forensic_analysis.py` | 70, 69, 97, 95 | `sqrt(48)` annualization | 48 = 30-min bars per day; assumes 30min base |
| `data/loader.py` | 23, 53 | `timeframe: str = "1min"` default | Parameter exists but is **ignored** — always loads raw pickle |
| `tests/conftest.py` | 97 | `freq="1min"` in all test fixtures | Tests only validate 1-min behavior |
| `tests/unit/test_*.py` | ~30 locations | `freq="1min"` in synthetic data | Same |

### 1.2 Lookback Values That Assume 1-Minute Bars

| Parameter | Current Value | 1min Equivalent | 5min | 15min | 30min | 1H | 4H |
|-----------|--------------|-----------------|------|-------|-------|----|----|
| Z-score lookback | 20 | 20 min | 1.67h | 5h | 10h | 20h | 3.3d |
| EMA span (regime) | 200 | 3.3h | 16.7h | 2d | 4.2d | 8.3d | 33d |
| ATR period | 14 | 14 min | 1.17h | 3.5h | 7h | 14h | 2.3d |
| Breakout lookback | 5 | 5 min | 25min | 1.25h | 2.5h | 5h | 20h |
| Strength lookbacks | [5,10,20,40,80] | 5-80 min | 25min-6.7h | 1.25-13.3h | 2.5-26.7h | 5-80h | 20h-13.3d |
| Strength norm window | 100-200 | 1.67-3.3h | 8.3-16.7h | 1.4-2.8d | 2.8-5.6d | 4.2-8.3d | 17-33d |
| TabFM vol_zscore_lookback | 200 | 3.3h | 16.7h | 2d | 4.2d | 8.3d | 33d |

### 1.3 Forward Return Horizons (Bar Counts)

Current: `[5, 15, 30, 60, 120, 240]` bars

| Timeframe | Horizon in elapsed time |
|-----------|------------------------|
| 1min | 5m, 15m, 30m, 1h, 2h, 4h |
| 5min | 25m, 1.25h, 2.5h, 5h, 10h, 20h |
| 15min | 1.25h, 3.75h, 7.5h, 15h, 30h, 60h (2.5d) |
| 30min | 2.5h, 7.5h, 15h, 30h, 60h (2.5d), 120h (5d) |
| **1H** | **5h, 15h, 30h, 60h (2.5d), 120h (5d), 240h (10d)** |
| **4H** | **20h, 60h (2.5d), 120h (5d), 240h (10d), 480h (20d), 960h (40d)** |

### 1.4 Regime Parameters

| Parameter | Current (1min) | Elapsed Time |
|-----------|---------------|--------------|
| EMA span | 200 | 3.3 hours |
| ATR period | 14 | 14 minutes |
| ATR percentile window | 200 | 3.3 hours |

These are bar-count parameters. On 1H data, EMA(200) would span 8.3 days — a completely different regime detector.

### 1.5 Signal Holding Periods

| File | Parameter | Current Value |
|------|-----------|---------------|
| `config/settings.py` | `close_minutes_before` | 30 (minutes) |
| `config/settings.py` | `buffer_minutes` | 120 (minutes) |
| `config/settings.py` | `macro_tf` | "4h" |
| `config.py` | `MAX_HOLD_DAYS` | 7 (days — OK) |
| `backtest_portfolio.py` | `trade_tf` | "5min" |
| `signals/structured_entry.py` | expects 4H data | hardcoded in docstring |

### 1.6 Test Files Requiring Parameterization

| File | Lines | Issue |
|------|-------|-------|
| `tests/conftest.py` | 97 | `freq="1min"` hardcoded |
| `tests/smoke/test_end_to_end.py` | 20 | `freq='1min'` hardcoded |
| `tests/regression/test_causality.py` | 23, 118 | `freq='1min'` hardcoded |
| `tests/unit/test_zscore.py` | 16, 74, 82, 93 | `freq='1min'` hardcoded |
| `tests/unit/test_data.py` | 23, 37, 58, 73, 89, 90, 135, 162 | `freq="1min"` hardcoded |
| `tests/unit/test_regime.py` | 58, 68 | `freq="1min"` hardcoded |
| `tests/unit/test_features.py` | 105, 117 | `freq="1min"` hardcoded |
| `tests/test_indicators.py` | 123, 145, 166, 170, 172 | `freq="1min"` and `"1min"` assertions |

---

## 2. Memory Analysis: OOM Impact

### Per-Pair Memory (ZScoreResearchData)

| Timeframe | Bars/Pair | Persistent | Peak | 20-Pair Total | Fits in 7.8GB? |
|-----------|-----------|------------|------|---------------|----------------|
| 1min | 3,929,000 | 377 MB | 754 MB | 7.5 GB | **MARGINAL** (swap risk) |
| 5min | 785,800 | 75 MB | 151 MB | 1.5 GB | Yes |
| 15min | 261,933 | 25 MB | 50 MB | 503 MB | Yes |
| 30min | 130,967 | 13 MB | 25 MB | 251 MB | Yes |
| **1H** | **65,483** | **6 MB** | **13 MB** | **126 MB** | **Yes (trivially)** |
| **4H** | **16,371** | **2 MB** | **3 MB** | **31 MB** | **Yes (trivially)** |

### Key Finding

Moving to 1H reduces per-pair memory by **60x** (377 MB → 6 MB). This eliminates all OOM risk and enables loading all 20 pairs simultaneously (~250 MB total vs 7.5 GB currently).

### Hidden Accumulation in cost_sensitivity.py

The `regime_agg` dict accumulates `return_pips` arrays across all pairs/horizons:
- 1min: ~1.7 GB accumulation
- 1H: ~34 MB accumulation
- 4H: ~8 MB accumulation

---

## 3. Data Acquisition: Multi-Timeframe Support

### 3.1 Dukascopy Native Support (CONFIRMED)

The `dukascopy_python` library supports native downloads for all target timeframes:

```python
INTERVAL_MAP = {
    "1min":  dukascopy_python.INTERVAL_MIN_1,
    "5min":  dukascopy_python.INTERVAL_MIN_5,
    "15min": dukascopy_python.INTERVAL_MIN_15,
    "30min": dukascopy_python.INTERVAL_MIN_30,
    "1h":    dukascopy_python.INTERVAL_HOUR_1,
    "4h":    dukascopy_python.INTERVAL_HOUR_4,
    "1day":  dukascopy_python.INTERVAL_DAY_1,
}
```

**Recommendation:** Download natively at each timeframe rather than resampling from 1min. Saves bandwidth, storage, and memory.

### 3.2 Storage Layout Change

Current: `/root/data/{PAIR}.pkl` (one file per pair, 1min only)

Proposed: `/root/data/{timeframe}/{PAIR}.pkl` (one directory per timeframe)

```
/root/data/
  1min/EUR_USD.pkl   (180 MB, ~3.9M bars)
  5min/EUR_USD.pkl   (36 MB, ~786K bars)
  15min/EUR_USD.pkl  (12 MB, ~262K bars)
  30min/EUR_USD.pkl  (6 MB, ~131K bars)
  1h/EUR_USD.pkl     (3 MB, ~65K bars)
  4h/EUR_USD.pkl     (0.8 MB, ~16K bars)
```

Estimated total storage for all 20 pairs across all timeframes: ~1.2 GB (vs 3.6 GB for 1min alone).

### 3.3 Estimated Download Time

Dukascopy free API rate limit: ~1 request per second.

| Timeframe | Bars/Pair/Year | API Calls/Pair/Year | 20 Pairs × 10.5 Years |
|-----------|---------------|---------------------|------------------------|
| 1min | 373K | 13 | 2,730 calls (~46 min) |
| 5min | 75K | 3 | 630 calls (~11 min) |
| 15min | 25K | 1 | 210 calls (~4 min) |
| 30min | 12.5K | 1 | 210 calls (~4 min) |
| 1H | 6.3K | 1 | 210 calls (~4 min) |
| 4H | 1.6K | 1 | 210 calls (~4 min) |

Total for all 6 timeframes: ~4,200 calls (~70 minutes).

---

## 4. Research Parameter Mapping

### 4.1 Design Principle

**Keep lookbacks as bar counts.** Do NOT convert to elapsed time. The research engine should determine which bar-count lookback works best at each timeframe. This is consistent with AGENTS.md §14 (no premature optimization).

Document elapsed-time equivalents for interpretation, but the code operates on bar counts.

### 4.2 Proposed Default Parameters per Timeframe

| Parameter | 1min (current) | 5min | 15min | 30min | **1H (primary)** | **4H (robustness)** |
|-----------|---------------|------|-------|-------|-------------------|---------------------|
| Z-score lookback | 20 | 20 | 20 | 20 | 20 | 20 |
| → elapsed | 20 min | 1.7h | 5h | 10h | 20h | 3.3d |
| EMA span | 200 | 200 | 200 | 200 | 200 | 200 |
| → elapsed | 3.3h | 16.7h | 2d | 4.2d | 8.3d | 33d |
| ATR period | 14 | 14 | 14 | 14 | 14 | 14 |
| → elapsed | 14 min | 1.2h | 3.5h | 7h | 14h | 2.3d |
| Forward horizons | [5,15,30,60,120,240] | same | same | same | same | same |
| → elapsed | 5m-4h | 25m-20h | 1.2h-2.5d | 2.5h-5d | 5h-10d | 20h-40d |
| Default analysis h | 60 | 60 | 60 | 60 | 60 | 60 |
| → elapsed | 60 min | 5h | 15h | 30h | 60h (2.5d) | 240h (10d) |

### 4.3 Alternative: Time-Equivalent Lookbacks

If the goal is to preserve the same elapsed-time window across timeframes:

| Parameter | 1min | 5min | 15min | 30min | 1H | 4H |
|-----------|------|------|-------|-------|----|----|
| Z-score lookback | 20 | 4 | 2 | 1 | 1 | 1 |
| EMA span | 200 | 40 | 14 | 7 | 4 | 1 |
| ATR period | 14 | 3 | 1 | 1 | 1 | 1 |

**This is NOT recommended.** Lookback=1 on 4H is meaningless. The bar-count approach is correct — different timeframes are different experiments, not scaled versions of the same experiment.

---

## 5. Code Changes Required

### 5.1 P0 — Must Change (Research Pipeline)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 1 | Parameterize download interval | `scripts/download_fx_data.py` | Small |
| 2 | Add timeframe directory structure to storage | `scripts/download_fx_data.py`, `data/loader.py` | Small |
| 3 | Fix `DataLoader.load_pair()` to use `timeframe` param | `data/loader.py` | Small |
| 4 | Fix annualization constants (`sqrt(252*390)`) | `zscore/features.py` | Small |
| 5 | Add `timeframe` field to `ZScoreResearchData` | `research/phase3_research.py` | Small |
| 6 | Make forward return horizons configurable | `research/phase3_research.py` | Medium |
| 7 | Store timeframe metadata in pickle | `scripts/download_fx_data.py` | Small |

### 5.2 P1 — Should Change (Regime & Signals)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 8 | Add `timeframe` to `classify_regime_chunked` signature | `zscore/regime.py` | Small |
| 9 | Add `timeframe` to `prepare_pair` and propagate | `research/phase3_research.py`, scripts | Small |
| 10 | Refactor scattered resample code to use `resampler.py` | `oos_validation.py`, `backtest_gft_crisis.py`, `phase5_forensic_analysis.py`, `debug_breakout.py` | Medium |
| 11 | Extend `build_all_timeframes()` to include 1h | `indicators/resampler.py` | Small |

### 5.3 P2 — Should Change (Tests)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 12 | Parameterize test fixtures with `@pytest.fixture(params=["1min","1h"])` | All test files | Medium |
| 13 | Add timeframe-aware smoke tests | `tests/smoke/test_end_to_end.py` | Small |
| 14 | Add timeframe-aware causality tests | `tests/regression/test_causality.py` | Medium |

### 5.4 P3 — Nice to Have (Cleanup)

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 15 | Update `resampler.py` docstrings (remove "1-min" assumption) | `indicators/resampler.py` | Trivial |
| 16 | Add `timeframes` to `DataConfig` | `config/settings.py` | Small |
| 17 | Update acquisition report structure | `scripts/download_fx_data.py` | Small |
| 18 | Fix `sqrt(48)` annualization in forensic scripts | `phase*_forensic_analysis.py` | Small |

---

## 6. Test Impact Assessment

### 6.1 Tests That Would Become Invalid

| Test File | Tests | Issue |
|-----------|-------|-------|
| `test_indicators.py::test_build_all_timeframes` | Asserts `"1min" in tfs` | Would need to accept any input timeframe |
| `test_indicators.py::test_resample_ohlcv` | Assumes 1min input | OK if resampler accepts any base |
| `test_data.py` | All tests use `freq="1min"` | Need parameterized fixtures |
| `test_zscore.py` | All tests use `freq="1min"` | Need parameterized fixtures |
| `test_regime.py` | All tests use `freq="1min"` | Need parameterized fixtures |
| `test_features.py` | All tests use `freq="1min"` | Need parameterized fixtures |
| `test_causality.py` | All tests use `freq="1min"` | Need parameterized fixtures |
| `test_end_to_end.py` | Uses `freq='1min'` | Need parameterized fixtures |

### 6.2 Tests That Would Still Pass Unchanged

- `test_backtest_metrics.py` — operates on PnL arrays, no timeframe dependency
- `test_circuit_breakers.py` — operates on trade records, no timeframe dependency
- `test_config.py` — tests config loading, no timeframe dependency
- `test_exchange.py` — tests exchange abstraction, no timeframe dependency
- `test_risk.py` — tests risk calculations, no timeframe dependency
- `test_session.py` — tests session logic, uses calendar times not bars

### 6.3 Recommended Test Strategy

1. Keep existing 1-min tests as regression tests (verify backward compatibility)
2. Add `@pytest.fixture(params=["1min", "1h"])` for timeframe-sensitive tests
3. Add dedicated 1H and 4H smoke tests
4. Add cross-timeframe causality tests (verify Z-score is causal at all timeframes)

---

## 7. Causality Considerations

### 7.1 Existing Causality Guarantees (Preserved)

The following are **timeframe-agnostic** and will work at any resolution:

- `zscore.py::_zscore_causal_core()` — uses rolling window, no future data
- `regime.py::_causal_ema()` — starts at first close, causal
- `regime.py::_causal_atr()` — Wilder's smoothing, causal
- `regime.py::classify_regime_chunked()` — chunked with state carry, causal
- `phase3_research.py::prepare_pair()` — forward returns via shift, causal

### 7.2 New Causality Risks at Higher Timeframes

| Risk | Description | Mitigation |
|------|-------------|------------|
| Chunk boundary at 4H | 16K bars total; chunk_size=1000 means 16 chunks. State carry must work correctly. | Existing chunked implementation handles this. Verify with test. |
| EMA warmup at 4H | EMA(200) on 4H = 33 days. First 200 bars (8.3 days) are warmup. Only 15.5 years of usable data after warmup. | Acceptable. Document warmup period. |
| ATR warmup at 4H | ATR(14) on 4H = 2.3 days. Trivial warmup. | No issue. |
| Forward return at 4H | h=240 on 4H = 40 days. Need 40 extra bars beyond analysis window. | Ensure data range is long enough. |

### 7.3 Stateful Chunked Processing

The existing `classify_regime_chunked()` implementation already supports stateful processing across chunk boundaries:

```python
def classify_regime_chunked(close, high, low, timestamps, pair,
                            chunk_size=1000, ema_span=200, atr_period=14):
    # EMA starts at first close (stateless start)
    # ATR carries state across chunks via atr_prev
    # Each chunk processes independently with carried state
```

This works at any timeframe. No changes needed for chunked processing.

---

## 8. Proposed Implementation Sequence

### Phase A: Data Layer (1-2 days)

1. Create timeframe directory structure under `/root/data/`
2. Modify `download_fx_data.py` to accept `--timeframe` argument
3. Add `INTERVAL_MAP` mapping timeframe strings to Dukascopy constants
4. Download 1H data for all 20 pairs (~4 minutes)
5. Download 4H data for all 20 pairs (~4 minutes)
6. Optionally download 5min/15min/30min for completeness
7. Fix `DataLoader.load_pair()` to use timeframe parameter

### Phase B: Research Engine (1-2 days)

8. Fix annualization constants in `zscore/features.py`
9. Add `timeframe` field to `ZScoreResearchData`
10. Make forward return horizons a parameter (not hardcoded `[5,15,30,60,120,240]`)
11. Update `prepare_pair()` to accept and propagate timeframe
12. Update `run_regime_analysis.py` and `cost_sensitivity.py` to pass timeframe

### Phase C: Smoke Test (1 day)

13. Run Phase 3 research pipeline on 1H data (single pair: EUR/USD)
14. Verify Z-score distribution, forward returns, binned analysis, regime analysis
15. Compare 1H results qualitatively with 1min results
16. Run same pipeline on 4H data

### Phase D: Full Research Run (2-3 days)

17. Run full 20-pair regime analysis on 1H data
18. Run full 20-pair cost sensitivity analysis on 1H data
19. Run full 20-pair regime analysis on 4H data
20. Run full 20-pair cost sensitivity analysis on 4H data
21. Cross-compare 1H vs 4H vs 1min results

### Phase E: Test Updates (1 day)

22. Parameterize test fixtures
23. Add 1H-specific smoke tests
24. Verify all 279 tests pass at both 1min and 1H

---

## 9. Expected Research Outcomes

### 9.1 Hypotheses to Test

| Hypothesis | Rationale |
|------------|-----------|
| Z-score mean-reversion is stronger at 1H than 1min | Lower noise, more meaningful price discovery |
| Transaction cost impact is reduced at 1H | Fewer trades, wider holding periods, less slippage per trade |
| Regime classification is more stable at 1H | Less noise in EMA/ATR, fewer regime transitions |
| Cross-pair edge is larger at 1H | Cross pairs have wider spreads; 1H reduces adverse selection |
| The effect may become economically viable at 1H | If gross edge increases faster than costs |

### 9.2 What Would Change in the Report

If 1H results show gross edge > 1.0 pips at |z|>2, the conclusion might change from "unprofitable" to "marginally viable." If the edge shrinks at 1H, the conclusion is reinforced.

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 1H data has different microstructure | High | Medium | Compare distributions, adjust lookbacks |
| Dukascopy 1H data has gaps | Low | Low | Validate data completeness before research |
| EMA(200) on 1H is too slow | Medium | Low | Research will determine; not optimizing |
| Forward return horizons too long at 1H | Medium | Medium | Make horizons configurable; test shorter horizons |
| Existing tests break | High | Low | Parameterize fixtures; keep 1min tests as regression |

---

## 11. Decision Matrix

| Timeframe | Bars | Memory | OOM Risk | Trades/Year | Edge Estimate | Cost Impact | Recommendation |
|-----------|------|--------|----------|-------------|---------------|-------------|----------------|
| 1min | 3.9M | 377 MB/pair | HIGH | ~50K | 0.26 pips | Unprofitable | Keep for backward compat |
| 5min | 786K | 75 MB/pair | None | ~10K | TBD | TBD | Download for comparison |
| 15min | 262K | 25 MB/pair | None | ~3.3K | TBD | TBD | Download for comparison |
| 30min | 131K | 13 MB/pair | None | ~1.7K | TBD | TBD | Download for comparison |
| **1H** | **65K** | **6 MB/pair** | **None** | **~830** | **TBD** | **TBD** | **PRIMARY TARGET** |
| **4H** | **16K** | **2 MB/pair** | **None** | **~210** | **TBD** | **TBD** | **ROBUSTNESS CHECK** |

---

## 12. Summary

### What Stays the Same
- All causal guarantees (rolling windows, no future data)
- Chunked processing architecture
- Z-score calculation engine
- Regime classification logic
- Forward return computation method
- HAC standard error implementation
- BH FDR multiple testing correction

### What Changes
- Data acquisition: add `--timeframe` parameter
- Storage: directory structure by timeframe
- DataLoader: use `timeframe` parameter (currently ignored)
- Annualization constants: fix hardcoded `sqrt(252*390)`
- Tests: parameterize fixtures
- Research parameters: same bar counts, different elapsed-time equivalents

### What Gets Better
- Memory: 60x reduction (377 MB → 6 MB per pair)
- OOM risk: eliminated
- All-pairs-simultaneous processing: safe
- Data download time: 4 min per timeframe (vs 46 min for 1min)
- Storage: ~1.2 GB total (vs 3.6 GB for 1min alone)

### What Needs Investigation
- Whether Z-score mean-reversion is economically viable at 1H
- Whether regime-dependent edge is stronger at 1H
- Whether 4H confirms or contradicts 1H findings
- Optimal lookback parameters for each timeframe (via research, not optimization)
