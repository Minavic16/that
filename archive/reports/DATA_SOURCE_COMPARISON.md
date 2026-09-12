# Phase 2 — Data Source Comparison

## 1. Market Data Sources

### 1.1 Dukascopy

| Attribute | Detail |
|---|---|
| **Source** | Dukascopy Bank SA (Swiss broker) |
| **Instruments** | 1000+ FX pairs, commodities, indices, crypto, bonds, ETFs |
| **Timeframe** | Tick, minute, hourly, daily, monthly |
| **Historical coverage** | 1990–2000 to present (varies by instrument) |
| **Timestamp** | UTC, millisecond precision |
| **Bid/Ask** | Yes — separate bid and ask OHLC |
| **Spread** | Derivable from bid/ask |
| **Volume** | Bid volume + ask volume (tick volume) |
| **Data quality** | High — bank-grade, institutional quality |
| **Access** | Free web export; Python library `dukascopy-python`; Node.js `dukascopy-node` |
| **Licensing** | Free for personal use; API key required for mass access |
| **Cost** | Free |
| **Known limitations** | Free tier rate-limited; tick data for long ranges can be gigabytes; some pairs have limited history |

**Assessment:** Gold standard for free historical FX data. Bank-grade quality, bid/ask available, millisecond timestamps. Best option for research.

### 1.2 Polygon.io

| Attribute | Detail |
|---|---|
| **Source** | Polygon.io |
| **Instruments** | FX major pairs (limited cross pairs) |
| **Timeframe** | 1min to daily |
| **Historical coverage** | September 2009 to present |
| **Timestamp** | Unix milliseconds, Eastern Time (ET) |
| **Bid/Ask** | Yes — aggregated from quoted bid/ask |
| **Spread** | Derivable |
| **Volume** | Yes (quote volume, not trade volume) |
| **Data quality** | Good — aggregated from institutional feeds |
| **Access** | REST API, WebSocket |
| **Licensing** | Commercial; free tier limited |
| **Cost** | Free tier: 5 API calls/min; paid from $29/month |
| **Known limitations** | Limited FX pair coverage compared to Dukascopy; ET timezone requires conversion |

### 1.3 TraderMade

| Attribute | Detail |
|---|---|
| **Source** | TraderMade |
| **Instruments** | Major and minor FX pairs |
| **Timeframe** | Tick (2016+), minute (2013+), daily (1990s+) |
| **Historical coverage** | Minute: 2013–present; Tick: 2016–present |
| **Timestamp** | GMT/UTC |
| **Bid/Ask** | Mid-price OHLC (not separate bid/ask) |
| **Spread** | Not directly available |
| **Volume** | Not available |
| **Data quality** | Good — aggregated from institutional providers |
| **Access** | REST API with API key |
| **Licensing** | Free tier limited; commercial for bulk access |
| **Cost** | Free tier: limited calls; paid plans for bulk |
| **Known limitations** | No separate bid/ask; minute data only back to 2013; no volume |

### 1.4 FastForex

| Attribute | Detail |
|---|---|
| **Source** | FastForex.io |
| **Instruments** | Major FX pairs |
| **Timeframe** | Minute, hourly, daily |
| **Historical coverage** | Up to 55 years for daily; less for minute |
| **Timestamp** | UTC |
| **Bid/Ask** | Yes — separate bid/ask OHLC |
| **Spread** | Derivable |
| **Volume** | Not available |
| **Data quality** | Good |
| **Access** | REST API |
| **Licensing** | Commercial |
| **Cost** | Paid plans |
| **Known limitations** | Newer service; less community validation |

### 1.5 Open Exchange Rates

| Attribute | Detail |
|---|---|
| **Source** | Open Exchange Rates |
| **Instruments** | 170+ currencies (cross rates) |
| **Timeframe** | 1min to monthly |
| **Historical coverage** | 2010+ for minute; longer for daily |
| **Timestamp** | UTC |
| **Bid/Ask** | No — midpoint rates only |
| **Spread** | Not available |
| **Volume** | Not available |
| **Data quality** | Good for mid-rates |
| **Access** | REST API |
| **Licensing** | Free tier limited; VIP Platinum for minute OHLC |
| **Cost** | Free tier: daily/hourly; minute OHLC requires VIP ($$$) |
| **Known limitations** | No bid/ask; minute data requires expensive plan |

### 1.6 MetaTrader 4/5 Export

| Attribute | Detail |
|---|---|
| **Source** | Any MT4/MT5 broker |
| **Instruments** | Broker-dependent |
| **Timeframe** | All (tick to monthly) |
| **Historical coverage** | Broker-dependent; often 1–5 years for M1 |
| **Timestamp** | Broker server time (NOT UTC) |
| **Bid/Ask** | Separate bid/ask bars available |
| **Spread** | Derivable |
| **Volume** | Tick volume (not real volume) |
| **Data quality** | Poor to moderate — gaps, duplicates, timestamp issues |
| **Access** | Export from MT4/MT5 terminal |
| **Licensing** | Broker-dependent |
| **Cost** | Free (with broker account) |
| **Known limitations** | **Major quality issues**: timestamp mismatches between pairs, gaps, DST problems, data reloaded on each terminal open, GMT offset changes without notice |

**Assessment:** Avoid for research. MT4/5 data has documented quality problems that make it unsuitable for rigorous backtesting.

---

## 2. News Data Sources

### 2.1 Forex Factory

| Attribute | Detail |
|---|---|
| **Source** | ForexFactory.com |
| **Coverage** | 2007+ (some scrapers report 2006) |
| **Fields** | Currency, event name, impact (high/medium/low), actual, forecast, previous |
| **Timestamp** | Event time in ForexFactory timezone (America/Chicago GMT-5) |
| **Timezone** | Configurable display; underlying time varies by scraper |
| **API** | No official API; web scraping required; community scrapers available |
| **Data format** | HTML (scraped), JSON/CSV/ICS (weekly exports) |
| **Licensing** | Terms prohibit scraping; data is publicly displayed |
| **Cost** | Free |
| **Known limitations** | Timestamp semantics unclear (event time vs. release time); scraping fragile; weekly export files only cover current week |

**Assessment:** Widely used for economic calendar research. Timestamp semantics need careful verification.

### 2.2 Investing.com

| Attribute | Detail |
|---|---|
| **Source** | Investing.com |
| **Coverage** | 2000+ (historical release data available for specific events) |
| **Fields** | Currency, event name, importance, actual, forecast, previous, date, time |
| **Timestamp** | Event time with timezone display |
| **API** | No official API; web scraping; Apify actors available |
| **Data format** | HTML (scraped) |
| **Licensing** | Terms prohibit scraping |
| **Cost** | Free |
| **Known limitations** | Anti-scraping measures; historical depth varies by event; timestamp semantics ambiguous |

### 2.3 MQL5 Calendar

| Attribute | Detail |
|---|---|
| **Source** | MQL5.com |
| **Coverage** | 2010+ |
| **Fields** | Currency, event name, importance, actual, forecast, previous |
| **Timestamp** | Server time (MetaTrader ecosystem) |
| **API** | Community API (jblanked.com/news/api) |
| **Data format** | JSON |
| **Licensing** | Community data |
| **Cost** | Free |
| **Known limitations** | Timestamp tied to MT server time; less comprehensive than FF |

### 2.4 FXStreet

| Attribute | Detail |
|---|---|
| **Source** | FXStreet.com |
| **Coverage** | 2007+ |
| **Fields** | Currency, event name, importance, actual, forecast, previous |
| **Timestamp** | UTC |
| **API** | Available via jblanked.com wrapper |
| **Data format** | JSON |
| **Licensing** | Terms vary |
| **Cost** | Free |
| **Known limitations** | Less comprehensive than Forex Factory for historical data |

### 2.5 HuggingFace Dataset

| Attribute | Detail |
|---|---|
| **Source** | Ehsanrs2/Forex_Factory_Calendar |
| **Coverage** | 2007-01-01 to 2025-04-07 |
| **Fields** | Currency, event type, impact, actual, forecast, previous, description |
| **Timestamp** | Asia/Tehran timezone |
| **Format** | CSV |
| **Licensing** | Public dataset |
| **Cost** | Free |
| **Known limitations** | Pre-scraped (no live updates); timezone is Iran time (needs conversion); depends on scraper methodology |

**Assessment:** Best option for historical news research data. Pre-scraped, consistent format, long coverage.

---

## 3. Comparison Matrix

### Market Data

| Criterion | Dukascopy | Polygon | TraderMade | FastForex | OER | MT4/5 |
|---|---|---|---|---|---|---|
| Historical depth | ★★★★★ | ★★★★ | ★★★ | ★★★★ | ★★★ | ★★ |
| Timestamp quality | ★★★★★ | ★★★★ | ★★★★ | ★★★★ | ★★★★ | ★ |
| Minute data depth | ★★★★★ | ★★★★ | ★★★ | ★★★★ | ★★ | ★★ |
| Bid/Ask availability | ★★★★★ | ★★★★ | ★ | ★★★★★ | ✗ | ★★★★ |
| Spread quality | ★★★★★ | ★★★★ | ★★ | ★★★★★ | ✗ | ★★★ |
| Volume | ★★★★ | ★★★ | ✗ | ✗ | ✗ | ★★ |
| Pair coverage | ★★★★★ | ★★ | ★★★ | ★★★ | ★★★★ | ★★★★ |
| Reproducibility | ★★★★★ | ★★★★ | ★★★★ | ★★★ | ★★★★ | ★ |
| Free access | ★★★★ | ★★ | ★★ | ★ | ★★ | ★★★★★ |
| API reliability | ★★★★ | ★★★★★ | ★★★★ | ★★★ | ★★★★★ | N/A |

### News Data

| Criterion | ForexFactory | Investing.com | MQL5 | FXStreet | HuggingFace |
|---|---|---|---|---|---|
| Historical depth | ★★★★ | ★★★★ | ★★★ | ★★★ | ★★★★★ |
| Timestamp quality | ★★★ | ★★★ | ★★ | ★★★ | ★★★ |
| Field completeness | ★★★★★ | ★★★★ | ★★★★ | ★★★★ | ★★★★★ |
| Importance levels | ★★★★★ | ★★★★★ | ★★★★ | ★★★★ | ★★★★★ |
| API access | ★ | ★ | ★★★ | ★★★ | ★★★★★ |
| Reproducibility | ★★ | ★★ | ★★★ | ★★★ | ★★★★★ |
| Licensing clarity | ★★ | ★★ | ★★★ | ★★★ | ★★★★ |

---

## 4. Selected Sources and Justification

### Market Data: Dukascopy

**Reasoning:**
1. Bank-grade data quality with documented timestamp semantics
2. Bid/ask available — critical for spread modeling
3. Millisecond timestamp precision in UTC
4. Coverage from 1990s to present
5. Python library available (`dukascopy-python`)
6. Free for research use
7. Most widely validated free FX data source in the quant community

**Risk:** Rate limits on free tier; tick data downloads can be slow. Mitigated by using minute-level aggregation.

### News Data: Forex Factory (primary) + HuggingFace dataset (historical)

**Reasoning:**
1. ForexFactory is the de facto standard for FX economic calendar data
2. HuggingFace dataset provides pre-scraped historical coverage 2007–2025
3. For live/recent data, community scrapers available
4. Timestamp semantics need verification but are well-documented by the community

**Risk:** ForexFactory has no official API; scraping may be fragile. Mitigated by using pre-scraped datasets for historical research.

---

## 5. Data Schema

### Market Data (Dukascopy)

```python
{
    "pair": str,           # e.g. "EUR/USD"
    "timestamp": datetime, # UTC, millisecond precision
    "open_bid": float,     # bid open
    "high_bid": float,     # bid high
    "low_bid": float,      # bid low
    "close_bid": float,    # bid close
    "open_ask": float,     # ask open
    "high_ask": float,     # ask high
    "low_ask": float,      # ask low
    "close_ask": float,    # ask close
    "bid_volume": float,   # tick volume on bid side
    "ask_volume": float,   # tick volume on ask side
}
```

### News Data (Forex Factory)

```python
{
    "timestamp": datetime,       # UTC — information availability time
    "event_time": str,           # original time string from source
    "source": str,               # "forexfactory"
    "currency": str,             # e.g. "USD"
    "event_name": str,           # e.g. "Non-Farm Employment Change"
    "impact": str,               # "high" | "medium" | "low"
    "actual": float | None,
    "forecast": float | None,
    "previous": float | None,
    "category": str,             # e.g. "Employment"
}
```

---

## 6. Timestamp Semantics

### Market Data

- **Dukascopy timestamps are UTC** — no DST ambiguity
- Bar timestamp represents the **open time** of the bar
- Bid and ask bars share the same timestamp
- Tick data has millisecond precision

### News Data

- **Event time** ≠ **Information availability time**
- ForexFactory shows the scheduled release time
- Actual release may be delayed by seconds to minutes
- For backtesting, use **event time + buffer** or **publication timestamp** if available
- HuggingFace dataset timestamps are in Asia/Tehran timezone (UTC+3:30 / UTC+4:30)

---

## 7. Timezone Conventions

- All market data: **UTC**
- All timestamps stored as **timezone-aware UTC**
- News timestamps: converted to UTC before storage
- Session definitions: **London** 07:00–16:00 UTC, **New York** 12:00–21:00 UTC, **Asian** 23:00–08:00 UTC

---

## 8. Known Limitations

1. **Dukascopy free tier rate limits** — bulk downloads need batching
2. **ForexFactory no official API** — scraping may break
3. **News timestamp precision** — event time vs. actual release time uncertain
4. **Existing pickle data** — already on VPS, 20 pairs, 2016–2026, minute OHLCV (no bid/ask)
5. **No tick data** — minute bars only for initial research
6. **Volume is tick volume** — not real transaction volume

---

## 9. Recommendation for Full Research Dataset

1. **Use existing pickle data** for initial pipeline validation (already available)
2. **Download Dukascopy minute data** with bid/ask for selected pairs as reference
3. **Use HuggingFace Forex Factory dataset** for historical news events
4. **Validate timestamp alignment** between market and news data
5. **Store raw data separately** from normalized/derived data
6. **Record provenance** for every dataset

---

## 10. Next Steps (Phase 2 Implementation)

1. Validate existing pickle data structure
2. Download small Dukascopy sample for one pair
3. Download small ForexFactory/HuggingFace sample
4. Build validation tooling
5. Test market/news alignment
6. Create PHASE_2_DATA_REPORT.md
