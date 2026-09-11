# Phase 1 Report: Z-Score Research Engine Foundation

**Date:** 2026-08-11
**Status:** Complete

---

## Completed

### Core Modules (new)
| Module | Purpose | File |
|---|---|---|
| `zscore/contracts.py` | All data contracts (MarketData, RegimeState, ZScoreObservation, Signal, etc.) | `zscore/contracts.py` |
| `zscore/zscore.py` | Causal rolling + expanding Z-score calculation | `zscore/zscore.py` |
| `zscore/regime.py` | Causal regime classification (trend + volatility) | `zscore/regime.py` |
| `zscore/features.py` | Causal features: ATR, realized volatility, EMA distance | `zscore/features.py` |
| `zscore/signals.py` | Signal generation skeleton (observation → candidate → executable) | `zscore/signals.py` |
| `costs/model.py` | Configurable cost model, spread application, break-even calculation | `costs/model.py` |
| `data_validation/validate.py` | OHLC data validation (duplicates, gaps, consistency) | `data_validation/validate.py` |
| `research/experiment.py` | Experiment configuration + JSON serialization + Git metadata | `research/experiment.py` |

### Pre-existing (untouched)
- `nestquant/config/settings.py`
- `nestquant/indicators/` (ATR, ADX, EMA, resampler, session, swing)
- `nestquant/signals/` (breakout, structured_entry)
- `nestquant/engines/` (backtest, regime_backtest)
- `nestquant/execution/`, `nestquant/portfolio/`, `nestquant/risk/`
- `nestquant/regime/` (adx_regime, hybrid, tabfm)
- `nestquant/backtest/`, `nestquant/data/`, `nestquant/knowledge/`
- `tests/test_*.py` (all pre-existing tests)

---

## Architecture

```
Data Ingestion → Validation → Features → Z-Score → Regime → Signals → [Backtest]
                                ↓           ↓         ↓
                          data_validation  zscore/   zscore/
                          /validate.py    zscore.py  regime.py
                                              ↓
                                         zscore/
                                         features.py
                                              ↓
                                         zscore/
                                         signals.py
                                              ↓
                                         costs/
                                         model.py
                                              ↓
                                         research/
                                         experiment.py
```

**Key design decisions:**
- Every module is causal: timestamp t uses only data ≤ t
- Regime module is decoupled from Z-score engine (replaceable)
- Signals separate observation → candidate → executable
- Cost model is configuration-driven, not hardcoded
- Experiment config is JSON-serializable for reproducibility

---

## Tests

| Category | Count | Status |
|---|---|---|
| Unit (new: zscore, features, regime, signals) | 43 | All pass |
| Regression/causality (new) | 5 | All pass |
| Smoke (new: end-to-end) | 8 | All pass |
| Pre-existing (backtest, circuits, config, engines, indicators, signals, position_sizer) | 199 | All pass |
| **Total** | **255** | **All pass** |
| **Lint (ruff)** | **0 errors** | Clean |

---

## Causality

### What has been tested for future-data leakage

1. **Z-score (rolling):** Bar t Z-score identical when bars > t are shifted, zeroed, or reversed
2. **Z-score (expanding):** Same test — bar t invariant to future data
3. **Regime classification:** Bar t trend/volatility label identical when future bars are modified
4. **ATR:** Bar t ATR identical when future highs are shifted
5. **Realized volatility:** Bar t RV identical when future closes are modified
6. **EMA distance:** Bar t EMA distance identical when future closes are modified
7. **Causality tested at multiple bar indices** (25, 50, 100, 200, 300, 400, 480)
8. **Expanding-window Z-score** has separate causality test

**No causality violations found.**

---

## Data

### Currently available
- `/root/data/*.pkl` — 20 FX pairs, minute OHLCV, 2016-01-03 to 2026-07-17
- Total size: ~3.6 GB
- Pairs: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, NZD/USD, EUR/GBP, EUR/JPY, GBP/JPY, AUD/JPY, NZD/JPY, EUR/AUD, GBP/AUD, AUD/NZD, USD/CAD, CAD/CHF, EUR/CHF, GBP/CHF, AUD/CHF, NZD/CHF

### Not yet acquired
- Higher timeframe data (H4, D1) — resampled from minute data or sourced separately
- News data — source, coverage, timestamps, licensing TBD

---

## News

### Proposed interface (not implemented)
```python
@dataclass
class NewsEvent:
    timestamp: pd.Timestamp      # when info became public
    source: str                  # e.g. "forexfactory", "investing.com"
    headline: str
    currency: str                # e.g. "USD"
    category: str                # e.g. "NFP", "CPI", "rate_decision"
    importance: int              # 1-3 scale
    actual: float | None
    forecast: float | None
    previous: float | None
```

### What still needs research
- Historical news data sources and licensing
- Timestamp accuracy (public availability vs. event time)
- Coverage gaps (not all pairs have equal news coverage)
- Whether news actually affects Z-score behavior (hypothesis to test, not assumption)

---

## Known Limitations

1. **Regime thresholds are arbitrary defaults** — not optimized for profitability, but also not validated for classification quality
2. **Signal layer is a placeholder** — uses simple mean-reversion thresholds that are NOT a proven strategy
3. **No higher-timeframe features** — only minute-based features implemented
4. **No news integration** — interface defined but not connected
5. **No end-to-end backtest** — research pipeline not yet wired together
6. **No out-of-sample validation** — not attempted in Phase 1
7. **Regime classification has no ground truth** — labels are heuristic, not validated against observable market states

---

## Next Phase (Phase 2: Data Pipeline)

Minimum next steps:

1. **Load real data into contracts** — read pickle files, validate, compute features for a single pair
2. **Compute Z-scores on real data** — verify warmup, NaN handling, output shape
3. **Classify regimes on real data** — inspect regime distribution, verify causality on real prices
4. **Generate signals on real data** — verify signal distribution, count, no execution coupling
5. **Wire experiment config** — attach Git commit, dataset version, parameters to each run
6. **Basic statistical analysis** — Z-score distribution, regime counts, signal frequency
7. **Single-pair end-to-end smoke test** — load → validate → features → zscore → regime → signals → report

**Do NOT:**
- Optimize parameters
- Run multi-pair backtest
- Claim profitability
- Connect to live trading
