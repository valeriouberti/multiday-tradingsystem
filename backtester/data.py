"""Historical data fetching for backtesting with start/end date ranges.

Supports two layers of caching:
  1. In-memory dict cache (within a single process run)
  2. Optional disk cache (parquet files in .cache/yfinance/) for repeated runs
     on the same historical range (e.g., montecarlo iterations).

Disk cache is enabled by default for historical fetches and can be disabled
by setting the environment variable YFINANCE_DISK_CACHE=0.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Sequence

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, str, str, str], pd.DataFrame] = {}

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "yfinance")
DISK_CACHE_ENABLED = os.environ.get("YFINANCE_DISK_CACHE", "1") != "0"


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    return df


def _disk_path(ticker: str, interval: str, start: str, end: str) -> str:
    safe = ticker.replace("^", "_caret_").replace(".", "_").replace("-", "_")
    return os.path.join(CACHE_DIR, f"{safe}_{interval}_{start}_{end}.parquet")


def _read_disk(ticker: str, interval: str, start: str, end: str) -> pd.DataFrame | None:
    if not DISK_CACHE_ENABLED:
        return None
    path = _disk_path(ticker, interval, start, end)
    if os.path.exists(path):
        try:
            df = pd.read_parquet(path)
            logger.debug("Disk cache hit: %s %s", ticker, interval)
            return df
        except Exception:
            logger.debug("Corrupt disk cache for %s, re-downloading", ticker)
            os.remove(path)
    return None


def _write_disk(df: pd.DataFrame, ticker: str, interval: str, start: str, end: str) -> None:
    if not DISK_CACHE_ENABLED or df.empty:
        return
    path = _disk_path(ticker, interval, start, end)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_parquet(path)
    except Exception:
        logger.debug("Failed to write disk cache for %s", ticker)


def warmup_start(start: str, extra_bars: int = 100) -> str:
    """Push start date back by extra_bars calendar days to allow indicator warmup."""
    dt = datetime.strptime(start, "%Y-%m-%d")
    # ~1.5x calendar days per trading day to be safe
    warmup_dt = dt - timedelta(days=int(extra_bars * 1.5))
    return warmup_dt.strftime("%Y-%m-%d")


def fetch_historical(
    ticker: str, start: str, end: str, interval: str = "1d"
) -> pd.DataFrame:
    cache_key = (ticker, interval, start, end)
    if cache_key in _cache:
        return _cache[cache_key]

    # Try disk cache
    disk_df = _read_disk(ticker, interval, start, end)
    if disk_df is not None:
        _cache[cache_key] = disk_df
        return disk_df

    logger.info("Downloading %s data for %s (%s to %s)", interval, ticker, start, end)
    try:
        df = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=True,
            prepost=True,
            progress=False,
        )
        df = _flatten_columns(df)
        if df.empty:
            logger.warning("No %s data returned for %s", interval, ticker)
        _cache[cache_key] = df
        _write_disk(df, ticker, interval, start, end)
        return df
    except Exception:
        logger.exception("Failed to download %s data for %s", interval, ticker)
        return pd.DataFrame()


def fetch_weekly_historical(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch weekly data. Pushes start back 2 years for EMA(50) warmup."""
    dt = datetime.strptime(start, "%Y-%m-%d")
    weekly_start = (dt - timedelta(days=730)).strftime("%Y-%m-%d")
    return fetch_historical(ticker, weekly_start, end, interval="1wk")


# =========================================================================
# BATCH PREFETCH — download all tickers in one yf.download() call
# =========================================================================

def _weekly_start(start: str) -> str:
    dt = datetime.strptime(start, "%Y-%m-%d")
    return (dt - timedelta(days=730)).strftime("%Y-%m-%d")


def prefetch_historical(
    tickers: Sequence[str], start: str, end: str,
) -> None:
    """Batch-download daily + weekly data for all tickers.

    Populates both in-memory and disk caches. Subsequent calls to
    fetch_historical() / fetch_weekly_historical() will hit the cache.
    """
    ws = _weekly_start(start)

    for interval, s in [("1d", start), ("1wk", ws)]:
        # Only download tickers not already cached (memory or disk)
        uncached = []
        for t in tickers:
            key = (t, interval, s, end)
            if key in _cache:
                continue
            disk_df = _read_disk(t, interval, s, end)
            if disk_df is not None:
                _cache[key] = disk_df
                continue
            uncached.append(t)

        if not uncached:
            logger.info("All %d tickers already cached for %s", len(tickers), interval)
            continue

        logger.info(
            "Batch-downloading %s data for %d tickers (%s to %s)",
            interval, len(uncached), s, end,
        )
        try:
            raw = yf.download(
                uncached, start=s, end=end, interval=interval,
                auto_adjust=True, prepost=True, progress=False,
                group_by="ticker",
            )
        except Exception:
            logger.exception("Batch download failed for %s, falling back to individual", interval)
            continue

        if raw.empty:
            continue

        if isinstance(raw.columns, pd.MultiIndex) and len(uncached) > 1:
            available = raw.columns.get_level_values(0).unique().tolist()
            for ticker in uncached:
                if ticker in available:
                    try:
                        df_t = raw[ticker].copy()
                        df_t.dropna(how="all", inplace=True)
                        if not df_t.empty:
                            key = (ticker, interval, s, end)
                            _cache[key] = df_t
                            _write_disk(df_t, ticker, interval, s, end)
                    except KeyError:
                        pass
        elif len(uncached) == 1:
            df_t = _flatten_columns(raw.copy())
            df_t.dropna(how="all", inplace=True)
            if not df_t.empty:
                key = (uncached[0], interval, s, end)
                _cache[key] = df_t
                _write_disk(df_t, uncached[0], interval, s, end)

        cached_count = sum(1 for t in uncached if (t, interval, s, end) in _cache)
        logger.info("Batch %s complete — cached %d/%d tickers", interval, cached_count, len(uncached))


def clear_cache() -> None:
    _cache.clear()


def clear_disk_cache() -> None:
    """Remove all parquet files from disk cache."""
    if os.path.isdir(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".parquet"):
                os.remove(os.path.join(CACHE_DIR, f))
        logger.info("Disk cache cleared")
