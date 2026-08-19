# Phase 3 — Research Audit Report (Updated)

**Date:** 2026-08-12 (updated from 2026-08-06)
**Auditor:** opencode
**Scope:** Methodological audit of Phase 3 research
**Status:** RESOLVED — all blocking issues fixed

---

## 1. Findings Summary

| Issue | Severity | Status | Resolution |
|---|---|---|---|
| Regime causality violation in prepare_pair() | HIGH | **FIXED** | Fenwick-tree streaming percentiles, fully causal |
| Pair count: report says 19, data has 20 | MEDIUM | **FIXED** | Corrected to 20 throughout |
| "Statistically significant" without proper inference | HIGH | **FIXED** | Newey-West HAC standard errors added |
| Temporal stability generalized from 5 pairs | MEDIUM | **FIXED** | Claim qualified to tested pairs |
| Binned monotonicity violated in 3/5 pairs | MEDIUM | **FIXED** | Claim qualified |
| Forward return timing mismatch | LOW | Documented | Entry at close[t] assumed |
| Cost model one-way vs mid-to-mid return | LOW | Documented | One-way assumption stated |
| Overlapping returns inflate apparent N | HIGH | **FIXED** | HAC SEs account for autocorrelation |
| Z-score computation bug (extreme values) | HIGH | **FIXED** | Numba-accelerated with std threshold |
| Regime computation too slow (O(n^2)) | HIGH | **FIXED** | Fenwick tree O(n log n), 58s/pair |

---

## 2. Causality Audit (Updated)

### 2.1 Regime Classification — FIXED

**Previous violation:** `prepare_pair()` used windowed `classify_regime()` with EMA resetting at each window boundary.

**Current implementation:** `classify_regime_chunked()` uses a Fenwick tree for exact streaming percentile computation. At bar i, the percentile is computed from ATR values in [0..i] only — no future data is used. EMA and ATR are computed on the full series causally.

**Verification:** 7 regime causality tests pass:
- `test_regime_invariant_to_future_data` — modifying future data does not change past labels
- `test_regime_future_data_invariance_chunked` — same for chunked version
- `test_regime_window_vs_full_series` — chunked version self-consistent across chunk sizes
- `test_ema_continuity_across_chunks` — EMA matches direct computation
- `test_atr_continuity_across_chunks` — ATR matches direct computation
- `test_regime_labels_multiple_test_points` — causality holds at multiple test points
- `test_regime_labels_invariant_to_chunk_size` — different chunk sizes produce identical labels

**Verdict:** PASS — regime classification is fully causal.

### 2.2 Z-Score Calculation — FIXED

**Previous:** Pure Python loop creating 3.9M dataclass objects. Some bars with std=2.28e-16 produced extreme z-scores (|z| > 10^12).

**Current:** Numba-accelerated `_zscore_causal_core()` with std threshold of 1e-10. Extreme z-scores eliminated. All 5 Z-score causality tests pass.

**Verdict:** PASS — Z-scores are causal and numerically stable.

### 2.3 Forward Returns — CAUSAL (unchanged)

Forward returns are computed as `fr[:n-h] = (close[h:] - close[:n-h]) / close[:n-h]`. This is the correct definition of a forward return. **PASS.**

---

## 3. Statistical Inference Audit (Updated)

### 3.1 Overlapping Returns — NOW ADDRESSED

**Previous:** No formal statistical test. Overlapping returns treated as independent.

**Current:** Newey-West HAC standard errors implemented in `cost_sensitivity.py`:
```python
def newey_west_hac(x, max_lags=None):
    # Bartlett kernel, automatic lag selection
    # max_lags = int(4 * (n/100)^(2/9))
```

**Results:** HAC SEs are ~2x larger than naive SEs, reflecting autocorrelation. Even after correction, the mean-reversion effect is highly significant (|z| > 10 for most regimes).

### 3.2 Effective Sample Size

With 60-bar overlapping returns:
- N_nominal: ~3.9M per pair
- N_effective: ~65K (N/60) to ~130K (N/30)
- The effect remains significant after adjustment

### 3.3 Multiple Testing

20 pairs × 6 horizons = 120 tests. The consistent direction (all negative correlations) across all 120 tests is strong evidence against multiple-testing artifact. However, the magnitude of the effect should be interpreted with this in mind.

---

## 4. Claim-by-Claim Evidence Classification (Updated)

### "statistically significant"
**Classification: A (demonstrated)**
Newey-West HAC standard errors confirm significance. For weak_trend×high_vol: z-stat = 21.3 (HAC), highly significant.

### "universal" / "all 20 pairs"
**Classification: A (demonstrated)**
All 20 analyzed pairs show negative correlation. The claim is restricted to the 20 pairs analyzed.

### "temporally stable"
**Classification: B (qualified)**
Temporal stability is demonstrated for the 5 pairs in `phase3_core.json`. Not verified for all 20 pairs. Claim now qualified.

### "monotonic"
**Classification: B (qualified)**
Monotonicity holds for negative Z bins but is violated in extreme positive Z bins for 3/5 pairs. Claim now qualified.

### "regime-dependent"
**Classification: A (demonstrated)**
weak_trend×high_vol has 3x larger gross edge than near_ema×mid_vol. Demonstrated across all 20 pairs with HAC inference.

### "too weak to overcome costs"
**Classification: A (demonstrated)**
Best regime (weak_trend×high_vol) breaks even at 0.95 pips. Realistic costs are 1.0+ pips. Negative expectancy confirmed with HAC z-tests.

---

## 5. Code Quality Audit (New)

### 5.1 Numba Acceleration

Both `_zscore_causal_core()` and `_classify_regime_core()` use `@njit(cache=True)` for JIT compilation. First-run compilation takes ~3s; subsequent runs use cached machine code.

### 5.2 Performance

| Operation | Before | After | Speedup |
|---|---|---|---|
| Z-score (3.9M bars) | ~300s (Python loop) | ~5s (numba) | 60x |
| Regime classification (3.9M bars) | ~90min (bisect) | ~58s (Fenwick+numba) | 93x |
| Full prepare_pair (one pair) | ~360s | ~60s | 6x |

### 5.3 Test Coverage

- 279/279 tests pass
- 12 causality tests (5 Z-score + 7 regime)
- 8 smoke tests (end-to-end pipeline)
- Lint clean (ruff)

---

## 6. Required Corrections (All Completed)

### Must fix (all done):

1. **Pair count:** Changed "19 pairs" to "20 pairs" throughout ✓
2. **Statistical significance:** Newey-West HAC standard errors added ✓
3. **Temporal stability:** Claim qualified to tested pairs ✓
4. **Binned monotonicity:** Claim qualified ✓
5. **Regime causality:** Fixed with Fenwick tree ✓

### Should fix (done):

6. **Forward return timing:** Documented in reports ✓
7. **Cost model:** Documented in reports ✓
8. **Z-score numerical stability:** Fixed with std threshold ✓

### Nice to have:

9. **Multiple testing:** Noted in reports
10. **Subsample validation:** Not implemented (future work)
11. **Out-of-sample:** Not implemented (future work)

---

## 7. Can Phase 3 Be Considered Complete?

**Yes — with the following caveats.**

The Phase 3 research:
1. Identifies a real, regime-dependent statistical phenomenon
2. Quantifies it with proper causal methodology
3. Demonstrates it does not survive realistic transaction costs
4. Uses HAC-corrected statistical inference
5. Passes all causality and regression tests
6. Is reproducible (commit, data, configuration documented)

**Caveats:**
- Multiple testing across 20 pairs × 6 horizons not formally corrected
- Out-of-sample validation not performed
- Block bootstrap not implemented (HAC used instead)

**The core conclusion is robust:** Z-score mean-reversion exists as a weak, regime-dependent statistical effect but does not survive realistic transaction costs. The corrections in this update affect the precision and honesty of the claims, not the fundamental finding.

---

## Appendix: Key Data Files

| File | Description |
|---|---|
| `research_data/phase3/regime_analysis.json` | Per-pair regime breakdown, all horizons |
| `research_data/phase3/cost_sensitivity.json` | Per-regime cost sensitivity with HAC inference |
| `research_data/phase3/all_pairs_summary.json` | Z-score summary (20 pairs) |
| `research_data/phase3/phase3_core.json` | Detailed per-pair Z-score results |
| `PHASE_3_ZSCORE_RESEARCH_REPORT.md` | Updated research report |
| `PHASE_3_REGIME_ANALYSIS.md` | New regime analysis report |
| `PHASE_3_AUDIT_REPORT.md` | This audit report |
