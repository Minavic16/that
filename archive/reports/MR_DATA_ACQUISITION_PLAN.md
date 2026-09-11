# MR Data Acquisition Plan

**Date:** 2026-08-09
**Goal:** Obtain minute-level FX data for 2016-01-01 through 2026-07-19 to reproduce the MR baseline

---

## A. Existing Acquisition Infrastructure

### refresh_data.py (cTrader)
- Uses `ctrader_connector.CTraderClient` (from `__pycache__`)
- Fetches H1 or M30 trendbars via cTrader Open API
- Requires authenticated access token (present in `/root/.env`)
- Outputs to `/root/data/{PAIR}.pkl`
- **Limitation:** cTrader trendbar history is limited — typically only last few thousand bars
- **Verdict:** NOT suitable for bulk historical download. Only useful for live data refresh.

### dukascopy-python (v4.0.1)
- Installed at `/usr/local/lib/python3.12/dist-packages/dukascopy_python`
- Free, no authentication required
- Fetches from Dukascopy Bank SA public data feed
- Supports minute-level data (INTERVAL_MIN_1)
- **Verdict: PRIMARY acquisition tool — confirmed working**

---

## B. Dukascopy Feasibility

### API Signature
```python
from dukascopy_python import fetch, INTERVAL_MIN_1, OFFER_SIDE_BID
df = fetch(instrument, interval, offer_side, start, end, limit=30000)
```

### Instrument Format
- **Required:** `EUR/USD` format (slash-separated, uppercase)
- **All 20 pairs tested — confirmed working:**
  EUR/CHF, GBP/USD, AUD/JPY, EUR/USD, USD/CHF, GBP/JPY, USD/JPY,
  AUD/USD, NZD/USD, EUR/GBP, CAD/JPY, AUD/CAD, GBP/AUD, EUR/AUD,
  NZD/JPY, EUR/CAD, GBP/CAD, AUD/CHF, NZD/CHF, CAD/CHF

### DataFrame Output
```
Index:   DatetimeIndex (UTC, name='timestamp')
Columns: open, high, low, close, volume (5 columns)
Format:  float64 OHLC, float64 volume
```

### Tested Performance
| Range | Bars | Time | Memory |
|-------|------|------|--------|
| 1 day (2024-01-01 to 2024-01-02) | 57 | <1s | <1 MB |
| 1 year (2023) | 371,105 | 10.3s | 17 MB |
| 2 years (2022-2024) | 743,984 | 17.4s | 34 MB |
| 10.5 years (2016-2026) | 3,928,770 | 94.6s | 180 MB |

### Key Observations
- `limit=30000` is per-request internal pagination limit — library handles it automatically
- No rate limiting observed for sequential calls
- Data starts from first trading day of the year (2016-01-03 for 2016 start)
- All major FX pairs available
- Weekend gaps present (expected — no FX trading Sat/Sun)

---

## C. cTrader Feasibility

### Status
- `ctrader_open_api` v0.9.2 installed
- `ctrader_connector_new.py` exists but is for live trading (no bulk download)
- `refresh_data.py` uses older `ctrader_connector.CTraderClient` from `__pycache__`
- Token exists in `/root/.env`: `CTRADER_ACCESS_TOKEN=NKsh6vAW...`

### Limitations
- cTrader trendbar API typically limited to ~1000-5000 bars per request
- H1 bars only → would need M30 or M1 from a different endpoint
- Not designed for bulk historical download
- Requires active demo/live account

### Verdict
**NOT recommended for bulk historical data.** Dukascopy is faster, free, and confirmed working.

---

## D. Existing Data Discovered

### /root/data_pre2016/ (28 files, 2.3 GB)
- **Date range:** 2012-01-02 to 2015-12-31
- **All 20 required pairs present** + 8 extras (AUD/NZD, CHF/JPY, EUR/NZD, GBP/NZD, NZD/CAD, USD/CAD)
- **Schema:** pickle dict → DataFrame (open, high, low, close, volume, UTC DatetimeIndex)
- **Format:** Identical to what test_final_scalper.py expects

### Compatibility Note
The pre-2016 data has identical schema to what Dukascopy produces. Both can coexist:
- Pre-2016 data: 2012-2015 (already on VPS)
- Dukascopy data: 2016-2026 (to be downloaded)
- Combined: 2012-2026

---

## E. Exact Missing Period

```
Missing: 2016-01-01 through 2026-07-19
Duration: 10 years, 6 months, 18 days
First trading day: 2016-01-03 (Monday)
Last trading day: 2026-07-17 (Friday)
```

---

## F. Required Pairs (20)

```
EUR/CHF  GBP/USD  AUD/JPY  EUR/USD  USD/CHF  GBP/JPY  USD/JPY
AUD/USD  NZD/USD  EUR/GBP  CAD/JPY  AUD/CAD  GBP/AUD  EUR/AUD
NZD/JPY  EUR/CAD  GBP/CAD  AUD/CHF  NZD/CHF  CAD/CHF
```

---

## G. Storage Estimate

| Metric | Value |
|--------|-------|
| Bars per pair per year | ~371,000 |
| Total bars (20 pairs × 10.5 years) | ~63,700,000 |
| Memory per pair (full period) | ~180 MB |
| Pickle size per pair (estimated) | ~200 MB |
| Total disk for 2016-2026 data | ~4 GB |
| Disk available on VPS | 83 GB |
| **Verdict** | **Well within capacity** |

---

## H. Recommended Acquisition Method

### Primary: Dukascopy (dukascopy-python)

**Why:**
1. Free, no authentication
2. All 20 pairs confirmed working
3. Minute-level data (INTERVAL_MIN_1)
4. Full 2016-2026 range confirmed (3.9M bars in 95s per pair)
5. Schema matches existing pre-2016 data format
6. Can download full range in one call per pair

### Acquisition Script Design
```python
# Pseudocode for download script
for each pair in PAIRS:
    df = fetch(pair, INTERVAL_MIN_1, OFFER_SIDE_BID,
               datetime(2016,1,1), datetime(2026,7,19))
    save to /root/data/{PAIR}.pkl as {pair: df}
```

### Output Location
- `/root/data/` directory (must be created)
- Files: `{PAIR}.pkl` (e.g., `EUR_USD.pkl`)
- Format: pickle dict with pair key → DataFrame
- Compatible with test_final_scalper.py's expected input

---

## I. Recommended Chunking / Retry Strategy

### Option 1: Full Range Per Pair (Recommended)
- Download 2016-2026 in one call per pair
- 20 calls total
- ~95s per call → ~32 minutes total
- Simple, fewer failure points

### Option 2: Year-by-Year Chunks (Safer)
- Download each year separately (2016, 2017, ..., 2026)
- 9 years × 20 pairs = 180 calls
- ~10s per call → ~30 minutes total
- Allows resuming from last successful year
- Better for retry on failure

### Recommended: Option 2 (Year-by-Year)
- Safer for long-running downloads
- Easy to resume if interrupted
- Can validate each chunk before saving
- Can skip years already downloaded

### Retry Strategy
- `max_retries=7` (dukascopy-python default)
- On failure: wait 5s, retry up to 7 times
- On persistent failure: skip pair+year, log error, continue
- After all downloads: validate each file

### Rate Limiting
- No explicit rate limit needed (Dukascopy is public feed)
- Add 1s sleep between pairs as courtesy
- No sleep needed between year chunks for same pair

---

## J. Data Validation Checks (Post-Acquisition)

### 1. Schema Validation
```python
for each .pkl file:
    assert isinstance(data, dict)
    assert pair_key in data
    df = data[pair_key]
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= {'open', 'high', 'low', 'close'}
    assert df.index.tz is not None  # UTC aware
    assert df.index.name == 'timestamp'
```

### 2. Date Range Validation
```python
for each pair:
    assert df.index[0] >= '2016-01-01'
    assert df.index[-1] >= '2026-07-01'
    assert len(df) >= 2_000_000  # ~5.5 years of minute bars minimum
```

### 3. Data Quality Checks
```python
for each pair:
    assert not df['close'].isna().any()  # no NaN closes
    assert (df['high'] >= df['low']).all()  # high >= low
    assert (df['high'] >= df['open']).all()  # high >= open
    assert (df['high'] >= df['close']).all()  # high >= close
    assert (df['low'] <= df['open']).all()   # low <= open
    assert (df['low'] <= df['close']).all()  # low <= close
    assert (df['volume'] >= 0).all()  # non-negative volume
```

### 4. Reproduce Smoke Test
```python
# After download, run a short backtest on 2016 data only
python3 -c "
from test_final_scalper import run_sim
r = run_sim('2016-01-01', '2016-12-31', friction='realistic', max_conc=10)
print(r)
"
```

---

## K. Risks / Blockers

| Risk | Severity | Mitigation |
|------|----------|------------|
| Dukascopy feed unavailable | Low | Public feed, highly available. Retry with backoff. |
| Network interruption mid-download | Medium | Year-by-year chunking allows resume. Track completed pairs. |
| Data gaps in Dukascopy feed | Low | Validate date coverage after download. Fill gaps if needed. |
| Pickle format mismatch | Low | Schema validated against pre-2016 data. Identical structure. |
| Disk space | None | 4 GB needed, 83 GB available. |
| Dukascopy rate limiting | Low | 1s sleep between pairs. Year-by-year is already slow enough. |
| Weekend/holiday gaps | None | Expected behavior. Script handles missing bars via resample. |

### No Known Blockers
- All 20 pairs confirmed working
- Full date range confirmed available
- Dukascopy-python installed and functional
- Disk space sufficient
- No authentication required

---

## L. Git Status

```
nestquant/ (commit 4abb039)
  ?? MR_DATA_REQUIREMENTS.md  (untracked, from previous task)
```
