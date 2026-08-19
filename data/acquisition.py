"""Z-Score Research Engine — Data Acquisition."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path("/root/nestquant/research_data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLE_DIR = DATA_DIR / "samples"


def ensure_dirs() -> None:
    """Create data directories if they don't exist."""
    for d in [DATA_DIR, RAW_DIR, PROCESSED_DIR, SAMPLE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def compute_checksum(filepath: str | Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def record_provenance(
    source: str,
    dataset_id: str,
    filename: str,
    date_range: tuple[str, str],
    instruments: list[str],
    timeframe: str,
    timezone_str: str,
    checksum: str | None = None,
    url: str | None = None,
    notes: str = "",
) -> dict:
    """Create a provenance record for a downloaded dataset."""
    return {
        "source": source,
        "dataset_id": dataset_id,
        "filename": filename,
        "retrieval_timestamp": datetime.now(UTC).isoformat(),
        "url": url,
        "date_range": list(date_range),
        "instruments": instruments,
        "timeframe": timeframe,
        "timezone": timezone_str,
        "checksum_sha256": checksum,
        "notes": notes,
    }


def save_provenance(provenance: dict, path: Path) -> None:
    """Save provenance record as JSON."""
    with open(path, "w") as f:
        json.dump(provenance, f, indent=2, default=str)


def load_existing_pair(pair_file: str | Path) -> pd.DataFrame:
    """Load an existing pickle pair file and return the DataFrame."""
    with open(pair_file, "rb") as f:
        data = json.load(f) if str(pair_file).endswith(".json") else __import__("pickle").load(f)
    if isinstance(data, dict):
        pair_name = list(data.keys())[0]
        return data[pair_name]
    return data


def download_dukascopy_sample(
    pair: str = "EUR/USD",
    start_date: str = "2025-01-01",
    end_date: str = "2025-01-07",
    output_dir: Path | None = None,
) -> Path | None:
    """Download a small Dukascopy sample using dukascopy-python.

    Args:
        pair: Instrument pair (e.g. "EUR/USD")
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        output_dir: Directory to save output

    Returns:
        Path to saved file, or None if download fails
    """
    try:
        from datetime import datetime

        import dukascopy_python
        from dukascopy_python.instruments import INSTRUMENT_FX_MAJORS_EUR_USD

        # Map pair to dukascopy instrument
        pair_map = {
            "EUR/USD": INSTRUMENT_FX_MAJORS_EUR_USD,
        }
        instrument = pair_map.get(pair)

        if instrument is None:
            print(f"No Dukascopy instrument mapping for {pair}")
            return None

        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        df = dukascopy_python.fetch(
            instrument=instrument,
            interval=dukascopy_python.INTERVAL_MIN_1,
            offer_side=dukascopy_python.OFFER_SIDE_BID,
            start=start,
            end=end,
        )

        if output_dir is None:
            output_dir = SAMPLE_DIR

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"dukascopy_{pair.replace('/', '_')}_{start_date}_{end_date}.parquet"
        output_path = output_dir / filename

        df.to_parquet(output_path)
        print(f"Saved Dukascopy sample to {output_path}")
        return output_path

    except ImportError:
        print("dukascopy-python not installed. Install with: pip install dukascopy-python")
        return None
    except Exception as e:
        print(f"Error downloading Dukascopy data: {e}")
        return None


def create_sample_from_existing(
    pair: str = "EUR/USD",
    pair_file: str | Path | None = None,
    days: int = 7,
    output_dir: Path | None = None,
) -> Path | None:
    """Create a small sample from existing pickle data.

    Args:
        pair: Pair name
        pair_file: Path to pickle file (if None, uses /root/data/)
        days: Number of days to sample
        output_dir: Directory to save output

    Returns:
        Path to saved sample
    """
    import pickle

    if pair_file is None:
        pair_file = f"/root/data/{pair.replace('/', '_')}.pkl"

    if not os.path.exists(pair_file):
        print(f"File not found: {pair_file}")
        return None

    with open(pair_file, "rb") as f:
        data = pickle.load(f)

    df = data[pair] if isinstance(data, dict) else data

    # Get last N days
    end_ts = df.index[-1]
    start_ts = end_ts - pd.Timedelta(days=days)
    sample = df[start_ts:]

    if output_dir is None:
        output_dir = SAMPLE_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"sample_{pair.replace('/', '_')}_{days}d.parquet"
    output_path = output_dir / filename

    sample.to_parquet(output_path)
    print(f"Saved sample to {output_path}: {len(sample)} bars, {sample.index[0]} to {sample.index[-1]}")
    return output_path
