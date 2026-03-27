"""Historical data fetching for backtesting with start/end date ranges."""

import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, str, str, str], pd.DataFrame] = {}


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    return df


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
        return df
    except Exception:
        logger.exception("Failed to download %s data for %s", interval, ticker)
        return pd.DataFrame()


def fetch_weekly_historical(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch weekly data. Pushes start back 2 years for EMA(50) warmup."""
    dt = datetime.strptime(start, "%Y-%m-%d")
    weekly_start = (dt - timedelta(days=730)).strftime("%Y-%m-%d")
    return fetch_historical(ticker, weekly_start, end, interval="1wk")


def clear_cache() -> None:
    _cache.clear()
