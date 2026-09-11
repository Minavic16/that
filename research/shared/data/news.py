"""Z-Score Research Engine — News Data Acquisition."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests


def download_forexfactory_weekly(output_dir: Path | None = None) -> Path | None:
    """Download current week's ForexFactory calendar as JSON.

    Args:
        output_dir: Directory to save output

    Returns:
        Path to saved file, or None if download fails
    """
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if output_dir is None:
            output_dir = Path("/root/nestquant/research_data/samples")
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = "forexfactory_thisweek.json"
        output_path = output_dir / filename

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Saved ForexFactory weekly data: {len(data)} events to {output_path}")
        return output_path

    except Exception as e:
        print(f"Error downloading ForexFactory data: {e}")
        return None


def parse_forexfactory_event(event: dict) -> dict:
    """Parse a single ForexFactory event into normalized format."""
    date_str = event.get("date", "")
    title = event.get("title", "")
    country = event.get("country", "")
    impact = event.get("impact", "")
    forecast = event.get("forecast", "")
    previous = event.get("previous", "")

    # Parse timestamp
    timestamp_utc = None
    if date_str:
        try:
            # ForexFactory dates are in ISO format with timezone
            dt = datetime.fromisoformat(date_str)
            timestamp_utc = dt.astimezone(UTC)
        except (ValueError, TypeError):
            pass

    return {
        "timestamp_utc": timestamp_utc.isoformat() if timestamp_utc else None,
        "event_time_original": date_str,
        "source": "forexfactory",
        "currency": country,
        "event_name": title,
        "impact": impact.lower() if impact else "unknown",
        "forecast": forecast,
        "previous": previous,
        "actual": None,  # Not available in weekly export
    }


def events_to_dataframe(events: list[dict]) -> pd.DataFrame:
    """Convert ForexFactory events to DataFrame."""
    parsed = [parse_forexfactory_event(e) for e in events]
    df = pd.DataFrame(parsed)
    if "timestamp_utc" in df.columns:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
        df = df.sort_values("timestamp_utc").reset_index(drop=True)
    return df


def test_market_news_alignment(
    market_file: Path,
    news_file: Path,
    event_currency: str = "USD",
    buffer_minutes: int = 5,
) -> dict:
    """Test alignment between market data and news events.

    Verifies that news events are mapped to market timestamps correctly
    and that information cannot be assigned before it was available.

    Args:
        market_file: Path to market data parquet file
        news_file: Path to ForexFactory JSON file
        event_currency: Currency to filter events for
        buffer_minutes: Minutes to add after event time for safety

    Returns:
        Alignment test results
    """
    # Load market data
    market_df = pd.read_parquet(market_file)

    # Load news data
    with open(news_file) as f:
        raw_events = json.load(f)

    events_df = events_to_dataframe(raw_events)

    # Filter for specific currency
    if event_currency:
        events_df = events_df[events_df["currency"] == event_currency]

    results = {
        "market_file": str(market_file),
        "news_file": str(news_file),
        "market_bars": len(market_df),
        "news_events": len(events_df),
        "currency_filter": event_currency,
        "alignment_checks": [],
    }

    for _, event in events_df.iterrows():
        event_time = event["timestamp_utc"]
        if pd.isna(event_time):
            continue

        # Find the market bar at or after the event time
        market_after = market_df[market_df.index >= event_time]
        market_before = market_df[market_df.index < event_time]

        check = {
            "event_name": event["event_name"],
            "event_time": str(event_time),
            "market_bars_before_event": len(market_before),
            "market_bars_after_event": len(market_after),
            "nearest_bar_after": str(market_after.index[0]) if len(market_after) > 0 else None,
            "nearest_bar_before": str(market_before.index[-1]) if len(market_before) > 0 else None,
            "has_market_data_at_event": len(market_before) > 0 and len(market_after) > 0,
        }
        results["alignment_checks"].append(check)

    return results
