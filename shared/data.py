import logging
from typing import Sequence

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, str], pd.DataFrame] = {}


def clear_cache() -> None:
    _cache.clear()


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    return df


# =========================================================================
# BATCH PREFETCH — download all tickers in one yf.download() call
# =========================================================================

def _split_batch(
    raw: pd.DataFrame, tickers: list[str], interval: str,
) -> None:
    """Split a multi-ticker yf.download() result and populate _cache."""
    if raw.empty:
        return

    if isinstance(raw.columns, pd.MultiIndex):
        # Multi-ticker: columns are (field, ticker)
        available = raw.columns.get_level_values(1).unique().tolist()
        for ticker in tickers:
            if ticker in available:
                try:
                    df_t = raw.xs(ticker, level=1, axis=1).copy()
                    df_t.dropna(how="all", inplace=True)
                    if not df_t.empty:
                        _cache[(ticker, interval)] = df_t
                except KeyError:
                    pass
    else:
        # Single ticker: columns are just fields
        df_t = raw.copy()
        df_t = _flatten_columns(df_t)
        df_t.dropna(how="all", inplace=True)
        if not df_t.empty and len(tickers) == 1:
            _cache[(tickers[0], interval)] = df_t


def prefetch_daily(tickers: Sequence[str], cfg: dict) -> None:
    """Batch-download daily data for all tickers in one HTTP call."""
    period = cfg["strategy"]["data_period_daily"]
    uncached = [t for t in tickers if (t, "1d") not in _cache]
    if not uncached:
        return
    logger.info("Batch-downloading daily data for %d tickers (period=%s)", len(uncached), period)
    raw = yf.download(
        uncached, period=period, interval="1d",
        auto_adjust=True, prepost=True, progress=False, group_by="ticker",
    )
    _split_batch(raw, uncached, "1d")
    logger.info("Batch daily download complete — cached %d tickers",
                sum(1 for t in uncached if (t, "1d") in _cache))


def prefetch_weekly(tickers: Sequence[str], cfg: dict) -> None:
    """Batch-download weekly data for all tickers in one HTTP call."""
    period = cfg["strategy"].get("data_period_weekly", "2y")
    uncached = [t for t in tickers if (t, "1wk") not in _cache]
    if not uncached:
        return
    logger.info("Batch-downloading weekly data for %d tickers (period=%s)", len(uncached), period)
    raw = yf.download(
        uncached, period=period, interval="1wk",
        auto_adjust=True, prepost=True, progress=False, group_by="ticker",
    )
    _split_batch(raw, uncached, "1wk")
    logger.info("Batch weekly download complete — cached %d tickers",
                sum(1 for t in uncached if (t, "1wk") in _cache))


def prefetch_h1(tickers: Sequence[str], cfg: dict) -> None:
    """Batch-download H1 data for all tickers in one HTTP call."""
    period = cfg["strategy"]["data_period_h1"]
    uncached = [t for t in tickers if (t, "1h") not in _cache]
    if not uncached:
        return
    logger.info("Batch-downloading H1 data for %d tickers (period=%s)", len(uncached), period)
    raw = yf.download(
        uncached, period=period, interval="1h",
        auto_adjust=True, prepost=True, progress=False, group_by="ticker",
    )
    _split_batch(raw, uncached, "1h")
    logger.info("Batch H1 download complete — cached %d tickers",
                sum(1 for t in uncached if (t, "1h") in _cache))


def prefetch_all(tickers: Sequence[str], cfg: dict, include_h1: bool = True) -> None:
    """Prefetch daily + weekly + H1 for all tickers and shared symbols (benchmark, VIX)."""
    benchmark = cfg.get("benchmark", "")
    all_tickers = list(dict.fromkeys(list(tickers) + [benchmark, "^VIX"]))
    prefetch_daily(all_tickers, cfg)
    prefetch_weekly(all_tickers, cfg)
    if include_h1:
        prefetch_h1(all_tickers, cfg)


def get_daily(ticker: str, cfg: dict) -> pd.DataFrame:
    cache_key = (ticker, "1d")
    if cache_key in _cache:
        logger.info("Using cached daily data for %s", ticker)
        return _cache[cache_key]

    period = cfg["strategy"]["data_period_daily"]
    logger.info("Downloading daily data for %s (period=%s)", ticker, period)
    try:
        df = yf.download(
            ticker, period=period, interval="1d",
            auto_adjust=True, prepost=True, progress=False,
        )
        df = _flatten_columns(df)
        if df.empty:
            logger.warning("No daily data returned for %s", ticker)
        _cache[cache_key] = df
        return df
    except Exception:
        logger.exception("Failed to download daily data for %s", ticker)
        return pd.DataFrame()


def get_weekly(ticker: str, cfg: dict) -> pd.DataFrame:
    cache_key = (ticker, "1wk")
    if cache_key in _cache:
        logger.info("Using cached weekly data for %s", ticker)
        return _cache[cache_key]

    period = cfg["strategy"].get("data_period_weekly", "2y")
    logger.info("Downloading weekly data for %s (period=%s)", ticker, period)
    try:
        df = yf.download(
            ticker, period=period, interval="1wk",
            auto_adjust=True, prepost=True, progress=False,
        )
        df = _flatten_columns(df)
        if df.empty:
            logger.warning("No weekly data returned for %s", ticker)
        _cache[cache_key] = df
        return df
    except Exception:
        logger.exception("Failed to download weekly data for %s", ticker)
        return pd.DataFrame()


def get_h1(ticker: str, cfg: dict) -> pd.DataFrame:
    cache_key = (ticker, "1h")
    if cache_key in _cache:
        logger.info("Using cached H1 data for %s", ticker)
        return _cache[cache_key]

    period = cfg["strategy"]["data_period_h1"]
    logger.info("Downloading H1 data for %s (period=%s)", ticker, period)
    try:
        df = yf.download(
            ticker, period=period, interval="1h",
            auto_adjust=True, prepost=True, progress=False,
        )
        df = _flatten_columns(df)
        if df.empty:
            logger.warning("No H1 data returned for %s", ticker)
        _cache[cache_key] = df
        return df
    except Exception:
        logger.exception("Failed to download H1 data for %s", ticker)
        return pd.DataFrame()


def get_premarket_change(ticker: str) -> float:
    logger.info("Fetching premarket change for %s", ticker)
    try:
        df = yf.download(
            ticker, period="2d", interval="1m",
            auto_adjust=True, prepost=True, progress=False,
        )
        df = _flatten_columns(df)
        if df.empty or len(df) < 2:
            return 0.0
        latest_price = df["Close"].iloc[-1]
        dates = df.index.normalize().unique()
        if len(dates) < 2:
            return 0.0
        prev_day = dates[-2]
        prev_day_data = df[df.index.normalize() == prev_day]
        if prev_day_data.empty:
            return 0.0
        prev_close = prev_day_data["Close"].iloc[-1]
        if prev_close == 0:
            return 0.0
        return float((latest_price - prev_close) / prev_close * 100)
    except Exception:
        logger.exception("Failed to get premarket change for %s", ticker)
        return 0.0
