# Phase 2 Report: Data Acquisition & Validation

**Date:** 2026-08-11
**Status:** Complete
**Baseline:** Commit 3dfd779

---

## 1. Candidate Market-Data Sources

| Source | Instruments | Timestamp | Bid/Ask | History | Cost |
|---|---|---|---|---|---|
| **Dukascopy** | 1000+ FX pairs, commodities, indices | UTC, millisecond | Yes | 1990s–present | Free |
| Polygon.io | Major FX pairs | ET (Unix ms) | Yes | 2009–present | Free tier limited |
| TraderMade | Major/minor FX | GMT/UTC | Mid-price only | Minute: 2013+ | Free tier limited |
| FastForex | Major FX pairs | UTC | Yes | Up to 55 years | Paid |
| Open Exchange Rates | 170+ currencies | UTC | No (midpoint) | 2010+ (minute requires VIP) | Free tier limited |
| MetaTrader 4/5 | Broker-dependent | Broker server time | Yes | 1–5 years | Free with broker |

---

## 2. Candidate News-Data Sources

| Source | Coverage | Fields | Timestamp | API | Cost |
|---|---|---|---|---|---|
| **ForexFactory** | 2007+ | Currency, impact, actual, forecast, previous | Event time (America/Chicago) | No official API | Free |
| Investing.com | 2000+ | Currency, importance, actual, forecast, previous | Event time | No official API | Free |
| MQL5 Calendar | 2010+ | Currency, importance, actual, forecast, previous | Server time | Community API | Free |
| FXStreet | 2007+ | Currency, importance, actual, forecast, previous | UTC | Community API | Free |
| HuggingFace Dataset | 2007–2025-04-07 | Full event data | Asia/Tehran | CSV download | Free |

---

## 3. Source Comparison

### Market Data Ranking

1. **Dukascopy** — Bank-grade quality, bid/ask, millisecond UTC timestamps, free, widely validated
2. Polygon.io — Good quality but limited FX coverage, ET timezone
3. TraderMade — Good but no bid/ask, limited minute history
4. FastForex — Good but commercial, less community validation
5. MT4/5 — Avoid: documented timestamp/gap quality issues

### News Data Ranking

1. **ForexFactory (weekly export)** — De facto standard, widely used
2. **HuggingFace Dataset** — Pre-scraped 2007–2025, consistent format
3. FXStreet — Good but less comprehensive
4. MQL5 — Tied to MT ecosystem
5. Investing.com — Anti-scraping measures

---

## 4. Selected Sources and Justification

### Market Data: Dukascopy

**Reasoning:**
- Bank-grade data quality from a Swiss-regulated broker
- Bid/ask available — critical for realistic spread modeling
- Millisecond timestamp precision in UTC (no DST ambiguity)
- Coverage from 1990s to present
- Python library available (`dukascopy-python`)
- Free for research use
- Most widely validated free FX data source in the quant community

### News Data: ForexFactory (primary) + HuggingFace (historical)

**Reasoning:**
- ForexFactory is the de facto standard for FX economic calendar data
- HuggingFace dataset provides pre-scraped historical coverage 2007–2025
- For recent/live data, ForexFactory weekly exports available
- Timestamp semantics need verification but are well-documented

---

## 5. Data Schema

### Market Data (Dukascopy format)

```
timestamp: datetime64[ms, UTC]   # Bar open time
open: float64                     # Bid open
high: float64                     # Bid high
low: float64                      # Bid low
close: float64                    # Bid close
volume: float64                   # Tick volume
```

### News Data (ForexFactory format)

```
timestamp_utc: datetime64[ms, UTC]  # Information availability time
source: str                          # "forexfactory"
currency: str                        # e.g. "USD"
event_name: str                      # e.g. "Non-Farm Employment Change"
impact: str                          # "high" | "medium" | "low"
forecast: str | None
previous: str | None
actual: str | None
```

---

## 6. Timestamp Semantics

### Market Data
- Dukascopy timestamps are **UTC** — no DST ambiguity
- Bar timestamp represents the **open time** of the bar
- Tick data has millisecond precision

### News Data
- **Event time** ≠ **Information availability time**
- ForexFactory shows the scheduled release time
- Actual release may be delayed by seconds to minutes
- For backtesting: use event time + buffer or publication timestamp
- HuggingFace dataset timestamps are in Asia/Tehran timezone (UTC+3:30/4:30)

---

## 7. Timezone Conventions

- All market data: **UTC**
- All timestamps stored as **timezone-aware UTC**
- News timestamps: converted to UTC before storage
- Session definitions: London 07:00–16:00 UTC, New York 12:00–21:00 UTC, Asian 23:00–08:00 UTC

---

## 8. Small-Sample Acquisition Results

### Dukascopy EUR/USD (2025-01-01 to 2025-01-03)
- File: `research_data/samples/dukascopy_EUR_USD_2025-01-01_2025-01-03.parquet`
- Bars: 1,496
- Columns: open, high, low, close, volume
- Timezone: UTC
- Validation: **ALL CHECKS PASSED**

### Existing Pickle Sample (EUR/USD, 7 days)
- File: `research_data/samples/sample_EUR_USD_7d.parquet`
- Bars: 7,165
- Columns: open, high, low, close, volume
- Timezone: UTC
- Validation: 7/8 checks passed (gap check flagged weekend gaps — expected)

### ForexFactory Weekly Export
- File: `research_data/samples/forexfactory_thisweek.json`
- Events: 74
- Currency coverage: JPY, USD, EUR, GBP, CAD, etc.
- Format: JSON with title, country, date, impact, forecast, previous

---

## 9. Validation Results

### Dukascopy Sample
| Check | Result |
|---|---|
| Timestamp order | PASS |
| Duplicate timestamps | PASS (0) |
| Gap detection | PASS |
| OHLC integrity | PASS |
| Missing values | PASS |
| Price values | PASS |
| Bid/ask | N/A (mid-price format) |
| Timezone UTC | PASS |

### Existing Pickle Sample
| Check | Result |
|---|---|
| Timestamp order | PASS |
| Duplicate timestamps | PASS (0) |
| Gap detection | FAIL (6 gaps — weekend market closures) |
| OHLC integrity | PASS |
| Missing values | PASS |
| Price values | PASS |
| Bid/ask | N/A |
| Timezone UTC | PASS |

---

## 10. Data-Quality Problems Discovered

1. **Weekend gaps in existing data** — Expected behavior, not a defect. Gap detection threshold needs adjustment for 24/5 FX market.
2. **No bid/ask in existing data** — Existing pickle files contain only mid-price OHLCV. Dukascopy sample also uses mid-price format (bid-side by default).
3. **ForexFactory timestamp ambiguity** — Event time vs. actual release time not distinguishable in weekly export.

---

## 11. Provenance/Reproducibility Procedure

Every downloaded dataset includes a provenance record:

```json
{
  "source": "dukascopy",
  "dataset_id": "EUR/USD-2025-01",
  "filename": "dukascopy_EUR_USD_2025-01-01_2025-01-03.parquet",
  "retrieval_timestamp": "2026-08-11T...",
  "url": null,
  "date_range": ["2025-01-01", "2025-01-03"],
  "instruments": ["EUR/USD"],
  "timeframe": "1min",
  "timezone": "UTC",
  "checksum_sha256": "...",
  "notes": ""
}
```

Raw data stored separately from processed/derived data.

---

## 12. Market/News Alignment Findings

- News events from current week (2026-08) cannot align with market data from 2025-01
- This is **expected** — demonstrates the need for time-matched datasets
- Alignment test framework works correctly
- For proper alignment, market and news data must cover the same date range
- News events have no "actual" values in ForexFactory weekly export (only scheduled events)

---

## 13. Known Limitations

1. **Existing data has no bid/ask** — Only mid-price OHLCV available
2. **Dukascopy free tier rate limits** — Bulk downloads need batching
3. **ForexFactory no official API** — Weekly exports only cover current week
4. **News timestamp precision** — Event time vs. actual release time uncertain
5. **No tick data** — Minute bars only for initial research
6. **Volume is tick volume** — Not real transaction volume
7. **Weekend gaps** — Expected for FX market, not a data defect

---

## 14. Recommendation for Full Research Dataset

1. **Use existing pickle data** for initial pipeline validation (20 pairs, 2016–2026)
2. **Download Dukascopy minute data with bid/ask** for selected pairs as reference
3. **Use HuggingFace ForexFactory dataset** for historical news events (2007–2025)
4. **Validate timestamp alignment** between market and news data
5. **Store raw data separately** from normalized/derived data
6. **Record provenance** for every dataset

---

## 15. Files Created/Modified

| File | Purpose |
|---|---|
| `data/__init__.py` | Package init |
| `data/acquisition.py` | Data download and provenance |
| `data/validation.py` | Extended data validation |
| `data/news.py` | News data acquisition and alignment |
| `tests/unit/test_data.py` | 17 data validation tests |
| `docs/DATA_SOURCE_COMPARISON.md` | Full source comparison |
| `research_data/samples/` | Downloaded samples |

---

## 16. Tests

| Category | Count | Status |
|---|---|---|
| New data tests | 17 | All pass |
| Pre-existing tests | 255 | All pass |
| **Total** | **272** | **All pass** |
| **Lint** | **0 errors** | Clean |

---

## 17. Remaining Risks

1. **News data may need scraping** — ForexFactory weekly exports are limited
2. **Bid/ask availability** — Need to verify Dukascopy provides separate bid/ask bars
3. **Timestamp alignment** — Needs larger overlapping date ranges
4. **Data volume** — Full dataset will be large (20 pairs × 10 years × minute bars)

---

## 18. Recommended Next Step

**Phase 3: Feature Engineering Pipeline**

1. Wire existing pickle data through the Phase 1 feature engine
2. Validate Z-score computation on real data
3. Test regime classification on real data
4. Verify causality on real market data (not synthetic)
5. Basic statistical analysis of Z-score distribution
