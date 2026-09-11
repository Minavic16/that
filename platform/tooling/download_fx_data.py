#!/usr/bin/env python3
"""
download_fx_data.py — Resumable Dukascopy multi-timeframe data acquisition
==========================================================================
Downloads FX data at multiple timeframes from 2016-01-01 to 2026-07-19.
Stores results in /root/data/{timeframe}/{PAIR}.pkl as pickle dicts.

Resumable: completed pair/year chunks are skipped automatically.

Usage:
    python scripts/download_fx_data.py --timeframe 1h
    python scripts/download_fx_data.py --timeframe 4h
    python scripts/download_fx_data.py --timeframe 1min
    python scripts/download_fx_data.py --timeframe 15min
"""

import argparse
import json
import logging
import os
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PAIRS = [
    'EUR/CHF', 'GBP/USD', 'AUD/JPY', 'EUR/USD', 'USD/CHF', 'GBP/JPY',
    'USD/JPY', 'AUD/USD', 'NZD/USD', 'EUR/GBP', 'CAD/JPY', 'AUD/CAD',
    'GBP/AUD', 'EUR/AUD', 'NZD/JPY', 'EUR/CAD', 'GBP/CAD', 'AUD/CHF',
    'NZD/CHF', 'CAD/CHF',
]

DATA_DIR = Path('/root/data')
LOG_DIR = Path('/root/nestquant/logs')
FAILURE_LOG = LOG_DIR / 'download_failures.jsonl'
PROGRESS_FILE = LOG_DIR / 'download_progress.json'
REPORT_FILE = LOG_DIR / 'acquisition_report.json'

START_YEAR = 2016
END_YEAR = 2026
END_DATE = datetime(2026, 7, 19, tzinfo=timezone.utc)

MAX_RETRIES = 7
RETRY_BASE_DELAY = 2.0  # seconds, doubled each retry
INTER_PAIR_DELAY = 1.0   # seconds between pairs

# Dukascopy interval mapping
TIMEFRAME_INTERVALS = {
    "1min": "INTERVAL_MIN_1",
    "5min": "INTERVAL_MIN_5",
    "15min": "INTERVAL_MIN_15",
    "30min": "INTERVAL_MIN_30",
    "1h": "INTERVAL_HOUR_1",
    "4h": "INTERVAL_HOUR_4",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('download_fx')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def log_failure(pair: str, year: int, error: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'pair': pair,
        'year': year,
        'error': error,
    }
    with open(FAILURE_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def year_range(year: int):
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    if year == END_YEAR:
        end = END_DATE
    return start, end


def validate_chunk(df: pd.DataFrame, pair: str, year: int) -> list:
    errors = []
    if len(df) == 0:
        errors.append('empty dataframe')
        return errors

    # Schema
    required_cols = {'open', 'high', 'low', 'close'}
    if not required_cols.issubset(set(df.columns)):
        errors.append(f'missing columns: {required_cols - set(df.columns)}')

    # Timezone
    if df.index.tz is None:
        errors.append('index not timezone-aware')

    # OHLC consistency
    if (df['high'] < df['low']).any():
        errors.append('high < low in some rows')
    if (df['high'] < df['open']).any():
        errors.append('high < open in some rows')
    if (df['high'] < df['close']).any():
        errors.append('high < close in some rows')
    if (df['low'] > df['open']).any():
        errors.append('low > open in some rows')
    if (df['low'] > df['close']).any():
        errors.append('low > close in some rows')

    # NaN in close
    if df['close'].isna().any():
        errors.append(f'{df["close"].isna().sum()} NaN values in close')

    # Negative volume
    if 'volume' in df.columns and (df['volume'] < 0).any():
        errors.append('negative volume')

    # Duplicate index
    if df.index.duplicated().any():
        errors.append(f'{df.index.duplicated().sum()} duplicate timestamps')

    return errors


# ---------------------------------------------------------------------------
# Main download
# ---------------------------------------------------------------------------

def download_pair_year(pair: str, year: int, interval_name: str,
                       retries: int = MAX_RETRIES) -> pd.DataFrame:
    from dukascopy_python import fetch, OFFER_SIDE_BID
    import dukascopy_python as dkp

    interval = getattr(dkp, interval_name)
    start, end = year_range(year)
    delay = RETRY_BASE_DELAY

    for attempt in range(1, retries + 1):
        try:
            df = fetch(pair, interval, OFFER_SIDE_BID, start, end, limit=30000)
            return df
        except Exception as e:
            err_msg = f'{type(e).__name__}: {str(e)[:200]}'
            if attempt < retries:
                log.warning(f'  Attempt {attempt}/{retries} failed for {pair} {year}: {err_msg}. '
                            f'Retrying in {delay:.0f}s...')
                time.sleep(delay)
                delay *= 2
            else:
                log.error(f'  FAILED {pair} {year} after {retries} attempts: {err_msg}')
                log_failure(pair, year, err_msg)
                return pd.DataFrame()


def download_all(timeframe: str = "1h"):
    interval_name = TIMEFRAME_INTERVALS.get(timeframe)
    if not interval_name:
        raise ValueError(f"Unsupported timeframe: {timeframe}. "
                         f"Supported: {list(TIMEFRAME_INTERVALS.keys())}")

    tf_dir = DATA_DIR / timeframe
    tf_dir.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()
    stats = {'downloaded': 0, 'skipped': 0, 'failed': 0, 'validated': 0, 'validation_errors': 0}

    total_chunks = len(PAIRS) * (END_YEAR - START_YEAR + 1)
    chunk_num = 0

    for pair in PAIRS:
        pair_key = pair.replace('/', '_')
        pkl_path = tf_dir / f'{pair_key}.pkl'

        # Load existing data for this pair (if any)
        existing = {}
        if pkl_path.exists():
            with open(pkl_path, 'rb') as f:
                existing = pickle.load(f)

        for year in range(START_YEAR, END_YEAR + 1):
            chunk_num += 1
            progress_key = f'{timeframe}_{pair_key}_{year}'

            # Skip if already completed
            if progress_key in progress and progress[progress_key].get('status') == 'done':
                stats['skipped'] += 1
                continue

            log.info(f'[{chunk_num}/{total_chunks}] Downloading {pair} {year} ({timeframe})...')

            df = download_pair_year(pair, year, interval_name)
            if df.empty:
                stats['failed'] += 1
                progress[progress_key] = {'status': 'failed', 'bars': 0}
                save_progress(progress)
                continue

            # Validate
            errors = validate_chunk(df, pair, year)
            if errors:
                log.warning(f'  Validation issues for {pair} {year}: {errors}')
                stats['validation_errors'] += 1
                progress[progress_key] = {'status': 'validated_with_errors', 'bars': len(df), 'errors': errors}
            else:
                stats['validated'] += 1
                progress[progress_key] = {'status': 'done', 'bars': len(df)}

            # Merge into existing
            if pair in existing:
                old_len = len(existing[pair])
                combined = pd.concat([existing[pair], df])
                combined = combined[~combined.index.duplicated(keep='last')]
                combined = combined.sort_index()
                existing[pair] = combined
                log.info(f'  MERGED {pair} {year}: {old_len} + {len(df)} -> {len(combined)} bars')
            else:
                existing[pair] = df
                log.info(f'  NEW {pair} {year}: {len(df)} bars')

            # Save after each year chunk
            with open(pkl_path, 'wb') as f:
                pickle.dump(existing, f)

            stats['downloaded'] += 1
            save_progress(progress)

        # Inter-pair delay
        time.sleep(INTER_PAIR_DELAY)

    return stats


# ---------------------------------------------------------------------------
# Validation pass
# ---------------------------------------------------------------------------

def validate_all(timeframe: str = "1h"):
    tf_dir = DATA_DIR / timeframe
    results = {}
    for pair in PAIRS:
        pair_key = pair.replace('/', '_')
        pkl_path = tf_dir / f'{pair_key}.pkl'
        if not pkl_path.exists():
            results[pair] = {'status': 'missing'}
            continue

        with open(pkl_path, 'rb') as f:
            data = pickle.load(f)

        if pair not in data:
            results[pair] = {'status': 'key_missing'}
            continue

        df = data[pair]
        errors = validate_chunk(df, pair, 0)

        # Bars by year
        bars_by_year = {}
        for year in range(START_YEAR, END_YEAR + 1):
            mask = (df.index.year == year)
            bars_by_year[year] = int(mask.sum())

        results[pair] = {
            'status': 'ok' if not errors else 'errors',
            'first': str(df.index[0]),
            'last': str(df.index[-1]),
            'total_bars': len(df),
            'bars_by_year': bars_by_year,
            'errors': errors,
        }

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def produce_report(stats: dict, validation: dict):
    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'download_stats': stats,
        'validation': validation,
    }
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)

    # Print summary
    print('\n' + '=' * 80)
    print('  ACQUISITION REPORT')
    print('=' * 80)
    print(f'\nDownload: {stats["downloaded"]} downloaded, {stats["skipped"]} skipped, '
          f'{stats["failed"]} failed')
    print(f'Validation: {stats["validated"]} clean, {stats["validation_errors"]} with errors')

    print('\nPer-Pair Summary:')
    print(f'  {"Pair":12s} {"First":>22s} {"Last":>22s} {"Bars":>10s} {"Status":>8s}')
    print(f'  {"-"*12} {"-"*22} {"-"*22} {"-"*10} {"-"*8}')
    for pair in PAIRS:
        v = validation.get(pair, {})
        if v.get('status') == 'missing':
            print(f'  {pair:12s} {"N/A":>22s} {"N/A":>22s} {"N/A":>10s} {"MISSING":>8s}')
        else:
            print(f'  {pair:12s} {v.get("first","?")[:22]:>22s} {v.get("last","?")[:22]:>22s} '
                  f'{v.get("total_bars",0):>10,} {v.get("status","?"):>8s}')
            if v.get('errors'):
                for e in v['errors']:
                    print(f'    ERROR: {e}')

    print(f'\nFull report: {REPORT_FILE}')
    print('=' * 80)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Download FX data from Dukascopy")
    parser.add_argument("--timeframe", default="1h",
                        choices=["1min", "5min", "15min", "30min", "1h", "4h"],
                        help="Data timeframe (default: 1h)")
    args = parser.parse_args()

    log.info(f'Starting Dukascopy data acquisition ({args.timeframe})')
    log.info(f'Pairs: {len(PAIRS)}, Years: {START_YEAR}-{END_YEAR}, '
             f'Output: {DATA_DIR / args.timeframe}')

    t0 = time.time()
    stats = download_all(timeframe=args.timeframe)
    elapsed = time.time() - t0
    log.info(f'Download complete in {elapsed:.0f}s')

    log.info('Running validation pass...')
    validation = validate_all(timeframe=args.timeframe)
    produce_report(stats, validation)
