import logging

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
