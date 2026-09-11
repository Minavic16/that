# MR Data Requirements — Historical MR Baseline Reproduction

**Date:** 2026-08-09
**Source:** `/tmp/test_final_scalper.py` (recovered from git commit `df508eb`)

---

## A. Data Expected by test_final_scalper.py

### Directory & Naming
- **Directory:** `/root/data/`
- **File pattern:** `{PAIR}.pkl` where PAIR has `/` replaced with `_`
- **Example:** `EUR_USD.pkl`, `GBP_JPY.pkl`, `AUD_CHF.pkl`

### File Format
- Python pickle (`.pkl`)
- Contains a `dict` with one key per pair
- Key = pair string (e.g., `EUR/USD`)
- Value = `pandas.DataFrame`

### DataFrame Schema
```
Index:  DatetimeIndex (UTC timezone-aware, name='timestamp')
Columns: open, high, low, close, volume
```

### Timeframe
- **Source data:** Minute-level bars (the script resamples internally)
- **Resampled to:**
  - 30-minute bars (primary signal timeframe)
  - 4-hour bars (EMA200/EMA50 trend filter)
  - Daily bars (daily candle direction filter)

### Required Pairs (20)
```
EUR/CHF  GBP/USD  AUD/JPY  EUR/USD  USD/CHF  GBP/JPY  USD/JPY
AUD/USD  NZD/USD  EUR/GBP  CAD/JPY  AUD/CAD  GBP/AUD  EUR/AUD
NZD/JPY  EUR/CAD  GBP/CAD  AUD/CHF  NZD/CHF  CAD/CHF
```

### Date Range
- **Full period backtest:** 2018-01-01 to 2026-07-19
- **In-sample (IS):** 2018-01-01 to 2022-12-31
- **Out-of-sample (OOS):** 2023-01-01 to 2026-07-19
- **Minimum per pair:** 500 bars of 30-minute data (~10.4 days)

### Dependencies
- `position_sizing.py` (QuoteSnapshot, pip_size_for_pair, pip_value_per_lot, compute_position_size)
- `pickle`, `numpy`, `pandas`

---

## B. Data Found on VPS

### Location
`/root/data_pre2016/` — 28 .pkl files, 2.3 GB total

### Pair Coverage: 20/20 required pairs present + 8 extras
```
AUD/CAD  AUD/CHF  AUD/JPY  AUD/NZD  AUD/USD  CAD/CHF  CAD/JPY  CHF/JPY
EUR/AUD  EUR/CAD  EUR/CHF  EUR/GBP  EUR/JPY  EUR/NZD  EUR/USD
GBP/AUD  GBP/CAD  GBP/CHF  GBP/JPY  GBP/NZD  GBP/USD
NZD/CAD  NZD/CHF  NZD/JPY  NZD/USD  USD/CAD  USD/CHF  USD/JPY
```

### Date Coverage
- **Earliest start:** 2012-01-02 (EUR/JPY)
- **Latest end:** 2015-12-31 (all pairs)
- **Typical range:** 2012-01-11 to 2015-12-31
- **Total rows per pair:** ~1.8M minute bars

### Schema Compatibility
| Attribute | Required | Found | Match? |
|-----------|----------|-------|--------|
| Format | pickle dict | pickle dict | YES |
| Key format | `EUR/USD` | `EUR/USD` | YES |
| Index type | DatetimeIndex UTC | DatetimeIndex UTC | YES |
| Columns | open, high, low, close | open, high, low, close, volume | YES (superset) |
| Timeframe | Minute-level | Minute-level | YES |

---

## C. Compatibility Assessment

### What MATCHES
- File format (pickle dict with pair keys) ✓
- DataFrame schema (OHLC columns, UTC DatetimeIndex) ✓
- All 20 required pairs present ✓
- Minute-level granularity ✓
- Extra `volume` column is harmless (script uses only open/high/low/close) ✓

### What DOES NOT MATCH
- **Date range gap: 4 years missing (2016-01-01 to 2017-12-31)**
- **Date range gap: 8.5 years missing (2018-01-01 to 2026-07-19)**
- **The existing data covers 2012-2015 only. The backtest requires 2018-2026.**

---

## D. Missing Data

### Critical Gap
The backtest window is **2018-01-01 to 2026-07-19** (8.5 years).

The existing data ends at **2015-12-31**.

**Missing:** All data from 2016-01-01 through 2026-07-19.

### Impact
- Without 2016+ data, the script will find 0 bars matching the `start='2018-01-01'` filter
- All pairs will be skipped (row count < 500 after date filter)
- The backtest will return `None` for all runs
- **The historical MR baseline CANNOT be reproduced with existing data alone**

---

## E. Exact Dataset Required to Reproduce the Baseline

### Minimum Dataset
- **Directory:** `/root/data/`
- **20 .pkl files** (one per required pair)
- **Date range:** 2018-01-01 to 2026-07-19 (minimum), ideally 2016-01-01 to 2026-07-19 for continuity
- **Timeframe:** Minute-level OHLC bars
- **Format:** pickle dict with pair key → DataFrame (open, high, low, close columns, UTC DatetimeIndex)
- **Size estimate:** ~2.3 GB per 4 years of minute data for 28 pairs → ~5 GB for 8.5 years

### Optional but Useful
- Data from 2016-2017 to bridge the gap between existing pre-2016 data and the 2018+ backtest window
- Would allow running the backtest on the full 2012-2026 range for additional validation

---

## F. Recommended Source / Next Acquisition Step

### Option 1: Download from cTrader (if account is active)
- `refresh_data.py` already implements cTrader data download
- Run with `--count 50000` to get ~3.5 years of minute data per pair
- Requires active cTrader access token (present in `/root/.env`)

### Option 2: Download from free data providers
- **Dukascopy:** Free historical minute data via `jpy` library or direct HTTP
- **TrueFX:** Free tick/minute data (registration required)
- **Yahoo Finance:** Limited minute data (only ~60 days for FX)

### Option 3: Synthesize from existing data
- The pre-2016 data has correct format/schema
- Could be used for a shorter backtest window (2012-2015) to validate the MR engine
- Would produce different results than the original 2018-2026 baseline

### Recommended Path
1. **First:** Try cTrader download via `refresh_data.py` (infrastructure already exists)
2. **Fallback:** Dukascopy minute data download script
3. **Interim:** Run a short backtest on 2012-2015 pre-2016 data to validate MR engine correctness before obtaining full dataset

---

## G. Git Status

```
nestquant/ (commit 4abb039)
  Clean working tree — no uncommitted changes
```

### File recovered from git history for reference
```
/test_final_scalper.py → recovered from git commit df508eb
  (was deleted during VPS cleanup, restored to /tmp/ for analysis)
```
